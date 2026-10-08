"""OpenRouter Image API mapping for one compiled generation.

Audit of the current generation path:

1. Resolution is stored on the job contract outputs.resolution and copied to
   EngineCompile.output_format.resolution, then GenerationOperation.output_format.
2. Aspect ratio is stored as outputs.image_proportions and the same output_format.
3. Output format in MIDAS is that proportion plus resolution, not a MIME type.
4. Requested view is EngineCompile.requested_view and GenerationOperation.requested_view.
5. model_id is EngineCompile.model_id and GenerationOperation.model_id.
6. Reference images are EngineCompile.references plus reference_bytes on the job.
7. Before this module, OpenRouter received model, modalities, and prompt text
   through POST /chat/completions. Aspect ratio was an optional image_config.
   Resolution was only written into the prompt.
8. The prompt still names the view, roles, and hashes. It is not the control
   for resolution or aspect ratio.
9. After the bytes return, apply_pixel_validation measures width, height, MIME,
   and format and holds a tier or ratio mismatch. It does not resize.

Image generation uses POST /api/v1/images when the selected model is in the
Image API catalog. Chat completions stay the path for Eye, Brain, Stylist,
and Critique. Quality is not a MIDAS field; resolution is the tier.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Any

import httpx

from app.contracts.engine import EngineCompile
from app.contracts.generation import GenerationOperation, SubmittedImageRequest
from app.providers.openrouter import OpenRouterCallRecord, OpenRouterSettings
from app.runtime.pixels import aspect_token

IMAGE_API_PATH = "/api/v1/images"
_IMAGE_MEDIA = {"JPG": "image/jpeg", "PNG": "image/png", "WebP": "image/webp"}
_CATALOG: dict[str, "ImageModelCapabilities"] | None = None


@dataclass(frozen=True)
class ImageModelCapabilities:
    """One model's Image API parameters. Absent fields are unsupported."""

    model_id: str
    resolutions: tuple[str, ...]
    aspect_ratios: tuple[str, ...]
    max_input_references: int | None
    max_outputs: int | None
    output_formats: tuple[str, ...] | None
    supports_resolution: bool
    supports_aspect_ratio: bool
    supports_input_references: bool
    endpoint_path: str | None = None


@dataclass(frozen=True)
class PreparedImageRequest:
    """Provider body plus the redacted audit record."""

    body: dict[str, Any]
    audit: SubmittedImageRequest
    prompt_sha256: str


class ImageRequestRejected(Exception):
    """The compiled request is outside the model's advertised capabilities."""

    def __init__(self, reasons: list[str]) -> None:
        self.reasons = reasons
        super().__init__("; ".join(reasons))


def clear_image_catalog_cache() -> None:
    global _CATALOG
    _CATALOG = None


def remember_image_catalog(catalog: dict[str, ImageModelCapabilities]) -> None:
    """Install an in-process catalog. Tests use this instead of the network."""

    global _CATALOG
    _CATALOG = dict(catalog)


def image_catalog(settings: OpenRouterSettings) -> dict[str, ImageModelCapabilities]:
    """Load GET /api/v1/images/models once per process."""

    global _CATALOG
    if _CATALOG is not None:
        return _CATALOG
    url = settings.base_url.rstrip("/") + "/images/models"
    with httpx.Client(timeout=settings.timeout_seconds) as client:
        response = client.get(
            url,
            headers={"Authorization": f"Bearer {settings.api_key}"},
        )
    if response.status_code >= 400:
        raise RuntimeError("OpenRouter image model catalog request failed")
    payload = response.json()
    rows = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise RuntimeError("OpenRouter image model catalog was not a list")
    catalog = {
        item.model_id: item
        for item in (_parse_model(row) for row in rows)
        if item is not None
    }
    _CATALOG = catalog
    return catalog


def prepare_image_request(
    operation: GenerationOperation,
    compile_artifact: EngineCompile,
    reference_bytes: dict[str, bytes],
    capabilities: ImageModelCapabilities,
) -> PreparedImageRequest:
    """Map the compiled output onto Image API fields. Does not call the network."""

    if capabilities.model_id != operation.model_id:
        raise ImageRequestRejected(
            [
                f"model {operation.model_id} does not match capability record "
                f"{capabilities.model_id}"
            ]
        )
    resolution = operation.output_format.resolution
    aspect = aspect_token(operation.output_format.image_proportions)
    reasons: list[str] = []
    if aspect is None:
        reasons.append(
            f"requested ratio {operation.output_format.image_proportions!r} "
            f"has no provider aspect_ratio mapping for model {operation.model_id}"
        )
    if not capabilities.supports_resolution:
        reasons.append(
            f"model {operation.model_id} does not advertise resolution"
        )
    elif resolution not in capabilities.resolutions:
        reasons.append(
            f"requested resolution {resolution} is not supported by "
            f"{operation.model_id}; supported resolutions: "
            f"{', '.join(capabilities.resolutions) or 'none'}"
        )
    if aspect is not None and not capabilities.supports_aspect_ratio:
        reasons.append(
            f"model {operation.model_id} does not advertise aspect_ratio"
        )
    elif aspect is not None and aspect not in capabilities.aspect_ratios:
        reasons.append(
            f"requested ratio {aspect} is not supported by {operation.model_id}; "
            f"supported ratios: {', '.join(capabilities.aspect_ratios) or 'none'}"
        )
    references = _image_references(compile_artifact, reference_bytes, reasons)
    if (
        capabilities.max_input_references is not None
        and len(references) > capabilities.max_input_references
    ):
        reasons.append(
            f"reference count {len(references)} exceeds max input_references "
            f"{capabilities.max_input_references} for model {operation.model_id}"
        )
    if references and not capabilities.supports_input_references:
        reasons.append(
            f"model {operation.model_id} does not advertise input_references"
        )
    if reasons:
        raise ImageRequestRejected(reasons)

    assert aspect is not None
    prompt = _prompt(operation, compile_artifact)
    body: dict[str, Any] = {
        "model": operation.model_id,
        "prompt": prompt,
        "resolution": resolution,
        "aspect_ratio": aspect,
        "input_references": [
            {
                "type": "image_url",
                "image_url": {"url": item["url"]},
            }
            for item in references
        ],
    }
    if capabilities.max_outputs is not None and capabilities.max_outputs >= 1:
        body["n"] = 1
    audit = SubmittedImageRequest(
        api=IMAGE_API_PATH,
        model_id=operation.model_id,
        resolution=resolution,
        aspect_ratio=aspect,
        input_reference_count=len(references),
        reference_roles=[item["role"] for item in references],
        output_format_parameter=None,
        supported_resolutions=list(capabilities.resolutions),
        supported_aspect_ratios=list(capabilities.aspect_ratios),
        max_input_references=capabilities.max_input_references,
    )
    return PreparedImageRequest(
        body=body,
        audit=audit,
        prompt_sha256=hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
    )


def post_image(
    settings: OpenRouterSettings,
    body: dict[str, Any],
    record: OpenRouterCallRecord,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    """POST /api/v1/images. The call record stores status and ids, not the key or bytes."""

    if not settings.api_key.strip():
        record.error_message = "OPENROUTER_API_KEY is empty"
        raise RuntimeError(record.error_message)
    url = settings.base_url.rstrip("/") + "/images"
    with httpx.Client(timeout=timeout_seconds) as client:
        response = client.post(
            url,
            headers={
                "Authorization": f"Bearer {settings.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
        )
    record.http_status = response.status_code
    record.request_id = response.headers.get("x-request-id")
    data = response.json() if response.content else {}
    if not isinstance(data, dict):
        record.error_message = "OpenRouter image response was not an object"
        raise RuntimeError(record.error_message)
    record.response_id = data.get("id") if isinstance(data.get("id"), str) else None
    record.model = data.get("model") if isinstance(data.get("model"), str) else None
    if response.status_code >= 400:
        error = data.get("error")
        message = error.get("message") if isinstance(error, dict) else None
        record.error_message = message or f"OpenRouter image HTTP {response.status_code}"
        raise RuntimeError(record.error_message)
    return data


def decode_image_response(data: dict[str, Any]) -> tuple[bytes, str]:
    """Return image bytes and a MIME type from data[0]. Never invents pixels."""

    rows = data.get("data")
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        return b"", ""
    encoded = rows[0].get("b64_json")
    if not isinstance(encoded, str) or not encoded.strip():
        return b"", ""
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError:
        return b"", ""
    media = rows[0].get("media_type")
    if not isinstance(media, str):
        media = ""
    return raw, media


def redacted_audit(prepared: PreparedImageRequest) -> dict[str, object]:
    """Settings safe to log. Omits the API key, prompt text, and image bytes."""

    return {
        "api": prepared.audit.api,
        "model": prepared.audit.model_id,
        "resolution": prepared.audit.resolution,
        "aspect_ratio": prepared.audit.aspect_ratio,
        "input_reference_count": prepared.audit.input_reference_count,
        "reference_roles": list(prepared.audit.reference_roles),
        "prompt_sha256": prepared.prompt_sha256,
        "output_format_parameter": prepared.audit.output_format_parameter,
    }


def _image_references(
    compile_artifact: EngineCompile,
    reference_bytes: dict[str, bytes],
    reasons: list[str],
) -> list[dict[str, str]]:
    prepared: list[dict[str, str]] = []
    for reference in compile_artifact.references:
        media = _IMAGE_MEDIA.get(reference.media_type)
        if media is None:
            continue
        data = reference_bytes.get(reference.reference_id)
        if not data:
            reasons.append(
                f"reference {reference.reference_id} is missing image bytes"
            )
            continue
        encoded = base64.b64encode(data).decode("ascii")
        prepared.append(
            {
                "role": reference.role,
                "reference_id": reference.reference_id,
                "url": f"data:{media};base64,{encoded}",
            }
        )
    return prepared


def _prompt(operation: GenerationOperation, compile_artifact: EngineCompile) -> str:
    lines = [
        operation.exact_prompt,
        f"Requested view: {operation.requested_view}.",
        "Reference order and roles:",
    ]
    for index, reference in enumerate(compile_artifact.references, start=1):
        lines.append(
            f"{index}. id={reference.reference_id}; role={reference.role}; "
            f"sha256={reference.content_hash}"
        )
    return "\n".join(lines)


def _parse_model(row: object) -> ImageModelCapabilities | None:
    if not isinstance(row, dict):
        return None
    model_id = row.get("id")
    if not isinstance(model_id, str) or not model_id.strip():
        return None
    parameters = row.get("supported_parameters")
    if not isinstance(parameters, dict):
        parameters = {}
    resolutions = _enum_values(parameters.get("resolution"))
    aspects = _enum_values(parameters.get("aspect_ratio"))
    output_formats = _enum_values(parameters.get("output_format"))
    endpoint = row.get("endpoints")
    return ImageModelCapabilities(
        model_id=model_id,
        resolutions=tuple(resolutions or ()),
        aspect_ratios=tuple(aspects or ()),
        max_input_references=_max_count(parameters.get("input_references")),
        max_outputs=_max_count(parameters.get("n")),
        output_formats=None if "output_format" not in parameters else tuple(output_formats or ()),
        supports_resolution="resolution" in parameters,
        supports_aspect_ratio="aspect_ratio" in parameters,
        supports_input_references="input_references" in parameters,
        endpoint_path=endpoint if isinstance(endpoint, str) else None,
    )


def _enum_values(descriptor: object) -> list[str] | None:
    if not isinstance(descriptor, dict):
        return None
    values = descriptor.get("values")
    if not isinstance(values, list):
        return None
    return [str(item) for item in values]


def _max_count(descriptor: object) -> int | None:
    if not isinstance(descriptor, dict):
        return None
    value = descriptor.get("max")
    if isinstance(value, int):
        return value
    return None
