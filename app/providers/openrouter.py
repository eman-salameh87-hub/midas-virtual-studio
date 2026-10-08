"""OpenRouter provider gateway.

load_settings reads connection settings and does not contact the network.

OpenRouterEyeProvider posts a caller-supplied model_id, the historical Eye
instruction, and one reference image. It does not choose a model.

OpenRouterBrainProvider uses the same chat-completions path with the
generalized Brain instruction. It does not choose a model.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any

import httpx
from dotenv import load_dotenv
from pydantic import ValidationError

from datetime import datetime, timezone

from app.contracts.brain import BrainPlan
from app.contracts.engine import EngineCompile
from app.contracts.eye import EyeObservation
from app.contracts.generation import (
    GeneratedMediaType,
    GenerationOperation,
    GenerationOutputRef,
    GenerationReceipt,
    ProviderCapability,
)
from app.contracts.critique import CritiqueAssessment
from app.contracts.stylist import StylistPlan
from app.providers.brain import BrainProviderRequest
from app.providers.brain_instruction import brain_instruction
from app.providers.critique import CritiqueProviderRequest
from app.providers.critique_instruction import critique_instruction
from app.providers.eye import EyeProviderRequest
from app.providers.generation import GenerationProviderRequest, GenerationProviderResult
from app.providers.living_room_eye_observation import (
    LivingRoomEyeMappingError,
    map_living_room_eye_json,
)
from app.providers.living_room_eye_prompt import living_room_eye_standing_prompt
from app.providers.stylist import StylistProviderRequest
from app.providers.stylist_instruction import stylist_instruction



@dataclass(frozen=True)
class OpenRouterSettings:
    """Connection settings only. No model id."""

    api_key: str
    base_url: str
    timeout_seconds: float


def load_settings() -> OpenRouterSettings:
    """Read OpenRouter connection settings. Does not contact the network."""

    load_dotenv()
    timeout_raw = os.getenv("OPENROUTER_TIMEOUT_SECONDS", "60")
    return OpenRouterSettings(
        api_key=os.getenv("OPENROUTER_API_KEY", ""),
        base_url=os.getenv(
            "OPENROUTER_BASE_URL",
            "https://openrouter.ai/api/v1",
        ),
        timeout_seconds=float(timeout_raw),
    )


@dataclass
class OpenRouterCallRecord:
    """Redacted provider-proof record. Do not store API keys here."""

    http_status: int | None = None
    response_id: str | None = None
    request_id: str | None = None
    model: str | None = None
    error_message: str | None = None
    raw_keys: list[str] = field(default_factory=list)
    message_preview: str | None = None
    parsed_payload: dict[str, Any] | None = None
    mapping_mismatches: list[str] = field(default_factory=list)


class OpenRouterEyeProvider:
    """Live Eye provider. model_id comes from the execution caller."""

    def __init__(
        self,
        settings: OpenRouterSettings,
        images: dict[str, bytes],
    ) -> None:
        self.settings = settings
        self.images = dict(images)
        self.last_call = OpenRouterCallRecord()

    def observe(self, request: EyeProviderRequest) -> EyeObservation:
        if not self.settings.api_key.strip():
            self.last_call.error_message = "OPENROUTER_API_KEY is empty"
            raise RuntimeError(self.last_call.error_message)
        payload = self._complete(request)
        try:
            observation = map_living_room_eye_json(payload, request.eye_input)
        except LivingRoomEyeMappingError as exc:
            self.last_call.mapping_mismatches = list(exc.mismatches)
            raise
        return observation

    def _complete(self, request: EyeProviderRequest) -> dict[str, Any]:
        reference = next(
            (
                item
                for item in request.eye_input.references
                if item.reference_id in self.images
            ),
            None,
        )
        if reference is None:
            raise ValueError("no image bytes were supplied for the EyeInput references")
        image = self.images[reference.reference_id]
        encoded = base64.b64encode(image).decode("ascii")
        media = {
            "JPG": "image/jpeg",
            "PNG": "image/png",
            "WebP": "image/webp",
        }.get(reference.media_type)
        if media is None:
            raise ValueError(
                f"OpenRouter Eye provider-proof accepts image media types only; "
                f"got {reference.media_type}"
            )
        user_text = "\n".join(request.messages).strip()
        if not user_text:
            user_text = "The vendor photo is attached."
        body = {
            "model": request.model_id,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": living_room_eye_standing_prompt(),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{media};base64,{encoded}",
                            },
                        },
                    ],
                },
            ],
        }
        return complete_chat_object(self.settings, body, self.last_call)


class OpenRouterBrainProvider:
    """Live Brain provider. model_id comes from the execution caller."""

    def __init__(self, settings: OpenRouterSettings) -> None:
        self.settings = settings
        self.last_call = OpenRouterCallRecord()

    def reason(self, request: BrainProviderRequest) -> BrainPlan:
        payload = self._complete(request)
        try:
            return BrainPlan.model_validate(payload)
        except ValidationError as exc:
            self.last_call.mapping_mismatches = [
                f"{'.'.join(str(part) for part in item.get('loc', ()))}: {item.get('type')}"
                for item in exc.errors()[:12]
            ]
            raise

    def _complete(self, request: BrainProviderRequest) -> dict[str, Any]:
        brain_input = request.brain_input
        user_payload = {
            "job_id": brain_input.job_id,
            "contract_id": brain_input.contract_id,
            "revision": brain_input.revision,
            "stage": brain_input.stage,
            "state": brain_input.state,
            "contract": brain_input.contract.model_dump(mode="json"),
            "observation": brain_input.observation.model_dump(mode="json"),
            "readiness": brain_input.readiness.model_dump(mode="json"),
            "evidence": [item.model_dump(mode="json") for item in brain_input.evidence],
        }
        body = {
            "model": request.model_id,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": brain_instruction(),
                },
                {
                    "role": "user",
                    "content": json.dumps(user_payload),
                },
            ],
        }
        return complete_chat_object(self.settings, body, self.last_call)


class OpenRouterStylistProvider:
    """Live Stylist provider. model_id comes from the execution caller."""

    def __init__(self, settings: OpenRouterSettings) -> None:
        self.settings = settings
        self.last_call = OpenRouterCallRecord()

    def compose(self, request: StylistProviderRequest) -> StylistPlan:
        payload = self._complete(request)
        try:
            return StylistPlan.model_validate(payload)
        except ValidationError as exc:
            self.last_call.mapping_mismatches = [
                f"{'.'.join(str(part) for part in item.get('loc', ()))}: {item.get('type')}"
                for item in exc.errors()[:12]
            ]
            raise

    def _complete(self, request: StylistProviderRequest) -> dict[str, Any]:
        stylist_input = request.stylist_input
        user_payload = {
            "job_id": stylist_input.job_id,
            "contract_id": stylist_input.contract_id,
            "revision": stylist_input.revision,
            "brain_contract_id": stylist_input.brain_plan.contract_id,
            "brain_revision": stylist_input.brain_plan.contract_revision,
            "stage": stylist_input.stage,
            "state": stylist_input.state,
            "contract": stylist_input.contract.model_dump(mode="json"),
            "observation": stylist_input.observation.model_dump(mode="json"),
            "brain_plan": stylist_input.brain_plan.model_dump(mode="json"),
            "evidence": [item.model_dump(mode="json") for item in stylist_input.evidence],
            "verified_complements": [
                item.model_dump(mode="json") for item in stylist_input.verified_complements
            ],
        }
        body = {
            "model": request.model_id,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": stylist_instruction(),
                },
                {
                    "role": "user",
                    "content": json.dumps(user_payload),
                },
            ],
        }
        return complete_chat_object(self.settings, body, self.last_call)


class OpenRouterCritiqueProvider:
    """Live Critique · assess provider. model_id comes from the execution caller."""

    def __init__(self, settings: OpenRouterSettings) -> None:
        self.settings = settings
        self.last_call = OpenRouterCallRecord()

    def assess(self, request: CritiqueProviderRequest) -> CritiqueAssessment:
        payload = self._complete(request)
        try:
            return CritiqueAssessment.model_validate(payload)
        except ValidationError as exc:
            self.last_call.mapping_mismatches = [
                f"{'.'.join(str(part) for part in item.get('loc', ()))}: {item.get('msg')}"
                for item in exc.errors()[:12]
            ]
            raise

    def _complete(self, request: CritiqueProviderRequest) -> dict[str, Any]:
        critique_input = request.critique_input
        receipt = critique_input.receipt
        output = receipt.output
        if output is None:
            raise ValueError("Critique requires a completed generation output")
        user_payload = {
            "job_id": critique_input.job_id,
            "contract_id": critique_input.contract_id,
            "contract_revision": critique_input.revision,
            "engine_contract_id": critique_input.compile.contract_id,
            "engine_revision": critique_input.compile.contract_revision,
            "generation_operation_key": critique_input.operation.operation_key,
            "generation_output_id": output.output_id,
            "stage": critique_input.stage,
            "state": critique_input.state,
            "original_reference_id": critique_input.original_reference_id,
            "locks": [item.model_dump(mode="json") for item in critique_input.compile.locks],
            "protected_identity": list(critique_input.contract.changes.protected_identity),
            "selected_count": critique_input.contract.intent.selected_count.model_dump(
                mode="json"
            ),
            "requested_view": critique_input.compile.requested_view,
            "output_format": critique_input.compile.output_format.model_dump(mode="json"),
            "observation": critique_input.observation.model_dump(mode="json"),
            "brain_invariants": [
                item.model_dump(mode="json") for item in critique_input.brain_plan.invariants
            ],
            "brain_plan": critique_input.brain_plan.model_dump(mode="json"),
            "stylist_plan": critique_input.stylist_plan.model_dump(mode="json"),
            "engine_compile": critique_input.compile.model_dump(mode="json"),
            "preferences": critique_input.contract.preferences.model_dump(mode="json"),
            "prior_generations": [
                item.model_dump(mode="json") for item in critique_input.prior_generations
            ],
            "prior_repairs": [
                item.model_dump(mode="json") for item in critique_input.prior_repairs
            ],
            "unknowns": [
                item.model_dump(mode="json") for item in critique_input.compile.unknowns
            ],
        }
        original_media = _IMAGE_MEDIA.get(request.original_media_type)
        generated_media = _IMAGE_MEDIA.get(request.generated_media_type)
        if original_media is None or generated_media is None:
            raise ValueError("Critique OpenRouter path accepts JPG, PNG, or WebP only")
        original_b64 = base64.b64encode(request.original_bytes).decode("ascii")
        generated_b64 = base64.b64encode(request.generated_bytes).decode("ascii")
        body = {
            "model": request.model_id,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": critique_instruction(),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": json.dumps(user_payload)},
                        {
                            "type": "text",
                            "text": "Original product reference. Inspect this image.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{original_media};base64,{original_b64}",
                            },
                        },
                        {
                            "type": "text",
                            "text": "Generated candidate. Inspect this image independently.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{generated_media};base64,{generated_b64}",
                            },
                        },
                    ],
                },
            ],
        }
        return complete_chat_object(self.settings, body, self.last_call)


GENERATION_CAPABILITIES: frozenset[ProviderCapability] = frozenset(
    {
        "image_generation",
        "multi_reference",
        "exact_prompt",
        "output_format",
    }
)

_IMAGE_MEDIA = {
    "JPG": "image/jpeg",
    "PNG": "image/png",
    "WebP": "image/webp",
}
_GENERATION_TIMEOUT_FLOOR = 180.0


class OpenRouterGenerationProvider:
    """Live image generation via the OpenRouter Image API.

    model_id comes from EngineCompile / GenerationOperation. Resolution and
    aspect ratio are Image API parameters, not prompt wording. This adapter
    does not choose a different model and does not resize the returned bytes.
    """

    def __init__(self, settings: OpenRouterSettings) -> None:
        self.settings = settings
        self.last_call = OpenRouterCallRecord()
        self.request_audit: dict[str, object] | None = None

    def capabilities(self) -> frozenset[ProviderCapability]:
        return GENERATION_CAPABILITIES

    def generate(self, request: GenerationProviderRequest) -> GenerationProviderResult:
        from app.providers.openrouter_images import (
            ImageRequestRejected,
            decode_image_response,
            image_catalog,
            post_image,
            prepare_image_request,
            redacted_audit,
        )

        operation = request.operation
        submitted_at = _now_iso()
        try:
            catalog = image_catalog(self.settings)
        except (httpx.TimeoutException, httpx.RequestError, RuntimeError) as exc:
            self.last_call.error_message = "OpenRouter image capability discovery failed"
            return self._hold(
                operation,
                [f"image capability discovery failed before generation: {exc.__class__.__name__}"],
            )
        capabilities = catalog.get(operation.model_id)
        if capabilities is None:
            return self._hold(
                operation,
                [
                    f"model {operation.model_id} is not in the OpenRouter Image API catalog; "
                    "no generation request was sent"
                ],
            )
        try:
            prepared = prepare_image_request(
                operation,
                request.compile,
                request.reference_bytes,
                capabilities,
            )
        except ImageRequestRejected as exc:
            return self._hold(operation, exc.reasons)
        self.request_audit = redacted_audit(prepared)
        timeout = max(self.settings.timeout_seconds, _GENERATION_TIMEOUT_FLOOR)
        try:
            data = post_image(
                self.settings,
                prepared.body,
                self.last_call,
                timeout_seconds=timeout,
            )
        except httpx.TimeoutException:
            self.last_call.error_message = "OpenRouter generation timed out"
            return self._uncertain(operation, submitted_at, self.last_call.error_message, prepared.audit)
        except httpx.RequestError as exc:
            self.last_call.error_message = (
                f"OpenRouter generation request failed: {exc.__class__.__name__}"
            )
            return self._uncertain(operation, submitted_at, self.last_call.error_message, prepared.audit)
        except RuntimeError:
            return self._completed_provider_failure(operation, submitted_at, prepared.audit)

        output_bytes, media_name = decode_image_response(data)
        media_type = _media_type_from_name(media_name, output_bytes)
        if not output_bytes or media_type is None:
            self.last_call.mapping_mismatches = ["image response data[0].b64_json was missing"]
            self.last_call.error_message = "image response data[0].b64_json was missing"
            return self._rejected(operation, submitted_at, prepared.audit, self.last_call.error_message)

        content_hash = hashlib.sha256(output_bytes).hexdigest()
        output_id = f"gen-{operation.operation_key[:12]}"
        completed_at = _now_iso()
        receipt_id = self.last_call.response_id or self.last_call.request_id
        if not receipt_id:
            receipt_id = f"openrouter-image-{content_hash[:20]}"
        return GenerationProviderResult(
            receipt=GenerationReceipt(
                operation_key=operation.operation_key,
                status="completed",
                provider_name="openrouter",
                provider_receipt_id=receipt_id,
                claimed_at=operation.claimed_at,
                submitted_at=submitted_at,
                completed_at=completed_at,
                retry_classification="do_not_retry",
                output=GenerationOutputRef(
                    output_id=output_id,
                    filename=f"{output_id}.{media_type.lower()}",
                    media_type=media_type,
                    hash_algorithm="sha256",
                    content_hash=content_hash,
                ),
                capability_checks=list(GENERATION_CAPABILITIES),
                hold_reasons=[],
                actual_model_id=self.last_call.model or operation.model_id,
                provider_request=prepared.audit,
            ),
            output_bytes=output_bytes,
        )

    def _hold(
        self,
        operation: GenerationOperation,
        reasons: list[str],
    ) -> GenerationProviderResult:
        return GenerationProviderResult(
            receipt=GenerationReceipt(
                operation_key=operation.operation_key,
                status="hold",
                provider_name="openrouter",
                provider_receipt_id=None,
                claimed_at=operation.claimed_at,
                submitted_at=None,
                completed_at=None,
                retry_classification="do_not_retry",
                output=None,
                capability_checks=list(GENERATION_CAPABILITIES),
                hold_reasons=reasons,
            ),
            output_bytes=None,
        )

    def _completed_provider_failure(
        self,
        operation: GenerationOperation,
        submitted_at: str,
        provider_request: object,
    ) -> GenerationProviderResult:
        """A finished HTTP response is not an in-flight generation.

        4xx means OpenRouter rejected the call and returned no image operation.
        5xx can still be ambiguous, so it stays reconcile-only. A RuntimeError
        before any status means the image request was not sent.
        """

        status = self.last_call.http_status
        message = self.last_call.error_message or "OpenRouter image request failed"
        if status is None:
            return self._hold(operation, [message])
        if 400 <= status < 500:
            return self._rejected(
                operation,
                submitted_at,
                provider_request,
                f"OpenRouter image HTTP {status}: {message}",
            )
        return self._uncertain(
            operation,
            submitted_at,
            f"OpenRouter image HTTP {status}: {message}",
            provider_request,
        )

    def _rejected(
        self,
        operation: GenerationOperation,
        submitted_at: str,
        provider_request: object,
        reason: str,
    ) -> GenerationProviderResult:
        return GenerationProviderResult(
            receipt=GenerationReceipt(
                operation_key=operation.operation_key,
                status="failed",
                provider_name="openrouter",
                provider_receipt_id=self.last_call.response_id or self.last_call.request_id,
                claimed_at=operation.claimed_at,
                submitted_at=submitted_at,
                completed_at=None,
                retry_classification="retry_if_never_started",
                output=None,
                capability_checks=list(GENERATION_CAPABILITIES),
                hold_reasons=[reason],
                provider_request=provider_request,  # type: ignore[arg-type]
            ),
            output_bytes=None,
        )

    def _uncertain(
        self,
        operation: GenerationOperation,
        submitted_at: str,
        detail: str,
        provider_request: object = None,
    ) -> GenerationProviderResult:
        return GenerationProviderResult(
            receipt=GenerationReceipt(
                operation_key=operation.operation_key,
                status="uncertain",
                provider_name="openrouter",
                provider_receipt_id=self.last_call.response_id or self.last_call.request_id,
                claimed_at=operation.claimed_at,
                submitted_at=submitted_at,
                completed_at=None,
                retry_classification="reconcile_only",
                output=None,
                capability_checks=list(GENERATION_CAPABILITIES),
                hold_reasons=[detail],
                provider_request=provider_request,  # type: ignore[arg-type]
            ),
            output_bytes=None,
        )


def generation_user_content(
    operation: GenerationOperation,
    compile_artifact: EngineCompile,
    reference_bytes: dict[str, bytes],
) -> list[dict[str, Any]]:
    """Build ordered multimodal content from EngineCompile. Not category-specific."""

    parts: list[dict[str, Any]] = [
        {"type": "text", "text": operation.exact_prompt},
        {
            "type": "text",
            "text": (
                f"Requested view: {operation.requested_view}. "
                f"Output format: {operation.output_format.image_proportions}, "
                f"{operation.output_format.resolution}. "
                f"Use reference images in this exact order and role."
            ),
        },
    ]
    for index, reference in enumerate(compile_artifact.references, start=1):
        parts.append(
            {
                "type": "text",
                "text": (
                    f"Reference {index}: id={reference.reference_id}; "
                    f"role={reference.role}; media={reference.media_type}; "
                    f"sha256={reference.content_hash}"
                ),
            }
        )
        media = _IMAGE_MEDIA.get(reference.media_type)
        image = reference_bytes.get(reference.reference_id)
        if media is None or not image:
            continue
        encoded = base64.b64encode(image).decode("ascii")
        parts.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media};base64,{encoded}"},
            }
        )
    return parts


def extract_message_image_urls(data: dict[str, Any]) -> list[str]:
    """Read choices[0].message.images[*].image_url.url. Empty if absent."""

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        return []
    first = choices[0]
    if not isinstance(first, dict):
        return []
    message = first.get("message")
    if not isinstance(message, dict):
        return []
    images = message.get("images")
    if not isinstance(images, list):
        return []
    urls: list[str] = []
    for item in images:
        if not isinstance(item, dict):
            continue
        image_url = item.get("image_url")
        if not isinstance(image_url, dict):
            continue
        url = image_url.get("url")
        if isinstance(url, str) and url.strip():
            urls.append(url.strip())
    return urls


def decode_generated_image(
    url: str,
    settings: OpenRouterSettings | None = None,
) -> tuple[bytes, GeneratedMediaType]:
    """Decode a data URL, or GET an https URL. Empty bytes if neither works."""

    if url.startswith("data:"):
        decoded = _decode_data_url(url)
        if decoded is None:
            return b"", "PNG"
        data, media = decoded
        return data, media
    if url.startswith("https://"):
        timeout = 60.0 if settings is None else settings.timeout_seconds
        with httpx.Client(timeout=timeout) as client:
            response = client.get(url)
        if response.status_code >= 400 or not response.content:
            return b"", "PNG"
        return response.content, _media_type_from_bytes(response.content)
    return b"", "PNG"


def _decode_data_url(url: str) -> tuple[bytes, GeneratedMediaType] | None:
    header, _, payload = url.partition(",")
    if not payload:
        return None
    try:
        data = base64.b64decode(payload)
    except ValueError:
        return None
    if not data:
        return None
    media: GeneratedMediaType = "PNG"
    if "image/jpeg" in header or "image/jpg" in header:
        media = "JPG"
    elif "image/webp" in header:
        media = "WebP"
    elif "image/png" in header:
        media = "PNG"
    else:
        media = _media_type_from_bytes(data)
    return data, media


def _media_type_from_name(media_name: str, data: bytes) -> GeneratedMediaType | None:
    if not data:
        return None
    lowered = media_name.casefold()
    if "png" in lowered:
        return "PNG"
    if "jpeg" in lowered or "jpg" in lowered:
        return "JPG"
    if "webp" in lowered:
        return "WebP"
    return _media_type_from_bytes(data)


def _media_type_from_bytes(data: bytes) -> GeneratedMediaType:
    if data.startswith(b"\x89PNG"):
        return "PNG"
    if data.startswith(b"\xff\xd8"):
        return "JPG"
    if data[8:12] == b"WEBP":
        return "WebP"
    return "PNG"


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def complete_chat(
    settings: OpenRouterSettings,
    body: dict[str, Any],
    record: OpenRouterCallRecord,
    *,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """POST /chat/completions and return the response object."""

    if not settings.api_key.strip():
        record.error_message = "OPENROUTER_API_KEY is empty"
        raise RuntimeError(record.error_message)
    url = settings.base_url.rstrip("/") + "/chat/completions"
    timeout = settings.timeout_seconds if timeout_seconds is None else timeout_seconds
    with httpx.Client(timeout=timeout) as client:
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
    data = _json_object(response.text)
    record.response_id = _optional_str(data.get("id"))
    record.model = _optional_str(data.get("model"))
    if response.status_code >= 400:
        record.error_message = _error_text(data, response.status_code)
        raise RuntimeError(record.error_message)
    return data


def complete_chat_object(
    settings: OpenRouterSettings,
    body: dict[str, Any],
    record: OpenRouterCallRecord,
) -> dict[str, Any]:
    """POST /chat/completions and parse a JSON object from the message."""

    data = complete_chat(settings, body, record)
    content = _choice_content(data)
    record.message_preview = content[:500]
    payload = _loads_object(content)
    record.parsed_payload = payload
    record.raw_keys = sorted(payload)
    return payload


def _json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("OpenRouter response was not JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("OpenRouter response JSON was not an object")
    return value


def _choice_content(data: dict[str, Any]) -> str:
    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("OpenRouter response had no choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise RuntimeError("OpenRouter choice was not an object")
    message = first.get("message")
    if not isinstance(message, dict):
        raise RuntimeError("OpenRouter choice had no message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("OpenRouter message content was empty")
    return content


def _loads_object(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("model content was not a JSON object") from exc
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise RuntimeError("model JSON was not an object")
    return value


def _error_text(data: dict[str, Any], status: int) -> str:
    error = data.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return f"OpenRouter HTTP {status}: {message}"
    return f"OpenRouter HTTP {status}"


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None
