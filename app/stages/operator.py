"""Operator · execute: claim, capability-check, and dispatch one generation.

Consumes a persisted EngineCompile. Does not critique, repair, or release.
Does not choose a model. An uncertain or claimed operation is not retried.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.contracts.engine import EngineCompile
from app.contracts.generation import (
    GenerationOperation,
    GenerationReceipt,
    ProviderCapability,
)
from app.providers.generation import (
    GenerationProvider,
    GenerationProviderRequest,
    GenerationProviderResult,
)
from app.runtime.pixels import (
    aspect_matches,
    aspect_token,
    expected_pixels,
    inspect_image,
    media_types_agree,
    size_matches_tier,
)
from app.runtime.state import JobRecord

REQUIRED_CAPABILITIES: tuple[ProviderCapability, ...] = (
    "image_generation",
    "multi_reference",
    "exact_prompt",
    "output_format",
)


class GenerationInvalidError(ValueError):
    """Generation receipt failed validation against the claimed operation."""


def operation_key_for(compile_artifact: EngineCompile) -> str:
    """Deterministic idempotency key for one compile artifact."""

    payload = {
        "job_id": compile_artifact.job_id,
        "contract_id": compile_artifact.contract_id,
        "contract_revision": compile_artifact.contract_revision,
        "model_id": compile_artifact.model_id,
        "exact_prompt": compile_artifact.exact_prompt,
        "reference_ids": [item.reference_id for item in compile_artifact.references],
        "reference_roles": [item.role for item in compile_artifact.references],
        "requested_view": compile_artifact.requested_view,
        "image_proportions": compile_artifact.output_format.image_proportions,
        "resolution": compile_artifact.output_format.resolution,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_generation_operation(
    record: JobRecord,
    *,
    claimed_at: str | None = None,
) -> GenerationOperation:
    compile_artifact = _require_compile(record)
    return GenerationOperation(
        job_id=record.job_id,
        contract_id=record.contract.contract_id,
        contract_revision=record.revision,
        compile_contract_id=compile_artifact.contract_id,
        compile_revision=compile_artifact.contract_revision,
        operation_key=operation_key_for(compile_artifact),
        model_id=compile_artifact.model_id,
        exact_prompt=compile_artifact.exact_prompt,
        reference_ids=[item.reference_id for item in compile_artifact.references],
        requested_view=compile_artifact.requested_view,
        output_format=compile_artifact.output_format,
        required_capabilities=list(REQUIRED_CAPABILITIES),
        claimed_at=claimed_at or _now(),
    )


def missing_capabilities(
    provider: GenerationProvider,
    required: list[ProviderCapability],
) -> list[ProviderCapability]:
    supported = provider.capabilities()
    return [item for item in required if item not in supported]


def generation_may_proceed(compile_artifact: EngineCompile) -> bool:
    return compile_artifact.status == "ready" and bool(compile_artifact.exact_prompt.strip())


def existing_operation_blocks_dispatch(receipt: GenerationReceipt | None) -> bool:
    """Uncertain, claimed, completed, and held receipts must not be re-dispatched."""

    if receipt is None:
        return False
    if receipt.status in {"claimed", "completed", "uncertain", "hold"}:
        return True
    if receipt.status == "failed" and receipt.retry_classification != "retry_if_never_started":
        return True
    return False


def execute_generation(
    *,
    operation: GenerationOperation,
    compile_artifact: EngineCompile,
    reference_bytes: dict[str, bytes],
    provider: GenerationProvider,
) -> GenerationProviderResult:
    """Capability-check then dispatch. Missing capability is HOLD, not success."""

    missing = missing_capabilities(provider, list(operation.required_capabilities))
    if missing:
        return GenerationProviderResult(
            receipt=GenerationReceipt(
                operation_key=operation.operation_key,
                status="hold",
                provider_name="none",
                provider_receipt_id=None,
                claimed_at=operation.claimed_at,
                submitted_at=None,
                completed_at=None,
                retry_classification="do_not_retry",
                output=None,
                capability_checks=[],
                hold_reasons=[
                    f"unsupported provider capability: {item}" for item in missing
                ],
            ),
            output_bytes=None,
        )

    result = provider.generate(
        GenerationProviderRequest(
            operation=operation,
            compile=compile_artifact,
            reference_bytes=dict(reference_bytes),
        )
    )
    result = apply_pixel_validation(operation, result)
    validate_generation_receipt(operation, compile_artifact, result)
    return result


def apply_pixel_validation(
    operation: GenerationOperation,
    result: GenerationProviderResult,
) -> GenerationProviderResult:
    """Record measured pixels. A size mismatch becomes HOLD and is not resized."""

    receipt = result.receipt
    if result.output_bytes is None or receipt.output is None:
        return result
    if receipt.status not in {"completed", "hold"}:
        return result

    requested_width, requested_height = expected_pixels(operation.output_format)
    measured = inspect_image(result.output_bytes)
    aspect = aspect_token(operation.output_format.image_proportions)
    dimensions_match = (
        measured.width is not None
        and measured.height is not None
        and aspect is not None
        and size_matches_tier(
            operation.output_format.resolution,
            aspect,
            measured.width,
            measured.height,
        )
    )
    format_matches = media_types_agree(receipt.output.media_type, measured)
    passed = dimensions_match and format_matches
    if passed:
        updated = receipt.model_copy(
            update={
                "format_check": "passed",
                "requested_width": requested_width,
                "requested_height": requested_height,
                "measured_width": measured.width,
                "measured_height": measured.height,
                "measured_format": measured.image_format,
                "measured_mime": measured.mime_type,
                "measured_aspect_ratio": aspect if aspect and aspect_matches(aspect, measured.width or 0, measured.height or 0) else None,
            }
        )
        return result.model_copy(update={"receipt": updated})

    reason = (
        "format_check failed: "
        f"requested {requested_width}x{requested_height}, "
        f"measured {measured.width}x{measured.height} "
        f"{measured.mime_type or 'unreadable'}; no upscale or size conversion was applied"
    )
    hold_reasons = list(receipt.hold_reasons)
    if reason not in hold_reasons:
        hold_reasons.append(reason)
    updated = receipt.model_copy(
        update={
            "status": "hold",
            "format_check": "failed",
            "requested_width": requested_width,
            "requested_height": requested_height,
            "measured_width": measured.width,
            "measured_height": measured.height,
            "measured_format": measured.image_format,
            "measured_mime": measured.mime_type,
            "measured_aspect_ratio": (
                aspect
                if aspect is not None
                and measured.width is not None
                and measured.height is not None
                and aspect_matches(aspect, measured.width, measured.height)
                else None
            ),
            "hold_reasons": hold_reasons,
            "retry_classification": "do_not_retry",
        }
    )
    return result.model_copy(update={"receipt": updated, "output_bytes": result.output_bytes})


def validate_generation_receipt(
    operation: GenerationOperation,
    compile_artifact: EngineCompile,
    result: GenerationProviderResult,
) -> None:
    receipt = result.receipt
    if receipt.operation_key != operation.operation_key:
        raise GenerationInvalidError("receipt operation_key does not match the claim")
    if receipt.claimed_at != operation.claimed_at:
        raise GenerationInvalidError("receipt claimed_at does not match the claim")
    if receipt.output is not None and result.output_bytes is not None:
        digest = hashlib.sha256(result.output_bytes).hexdigest()
        if digest != receipt.output.content_hash:
            raise GenerationInvalidError("output content_hash does not match stored bytes")
    if receipt.status == "completed":
        if result.output_bytes is None:
            raise GenerationInvalidError("completed receipt is missing output bytes")
        if receipt.format_check != "passed":
            raise GenerationInvalidError(
                "completed generation requires format_check passed"
            )
        assert receipt.output is not None
        if operation.exact_prompt != compile_artifact.exact_prompt and not (
            operation.exact_prompt.startswith(compile_artifact.exact_prompt)
            and "MIDAS bounded repair" in operation.exact_prompt
        ):
            raise GenerationInvalidError("operation exact_prompt does not match EngineCompile")
        if operation.model_id != compile_artifact.model_id:
            raise GenerationInvalidError("operation model_id does not match EngineCompile")
        if operation.requested_view != compile_artifact.requested_view:
            raise GenerationInvalidError("operation requested_view does not match EngineCompile")
        if operation.output_format != compile_artifact.output_format:
            raise GenerationInvalidError("operation output_format does not match EngineCompile")
        expected_ids = [item.reference_id for item in compile_artifact.references]
        if operation.reference_ids != expected_ids:
            raise GenerationInvalidError("operation reference order does not match EngineCompile")


def _require_compile(record: JobRecord) -> EngineCompile:
    if record.engine is None or record.engine.result is None:
        raise ValueError("Engine compile must have executed before generation")
    return record.engine.result


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
