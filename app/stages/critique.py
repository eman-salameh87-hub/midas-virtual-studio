"""Critique · assess execution boundary.

Inspects the original reference and completed generation against the locked
contract. Does not repair or release. Does not choose a model.
"""

from app.contracts.critique import CritiqueAssessment, LOCK_DIMENSIONS
from app.contracts.engine import EngineCompile
from app.providers.critique import (
    CritiqueInput,
    CritiqueProvider,
    CritiqueProviderRequest,
    CritiqueResult,
)
from app.runtime.artifacts import get_artifact_store, output_filename
from app.runtime.state import JobRecord


class CritiqueAssessmentInvalidError(ValueError):
    """Provider JSON parsed but failed critique validation."""


def build_critique_input(record: JobRecord) -> CritiqueInput:
    """Copy frozen contract, plans, compile, and generation identity."""

    if record.observation is None:
        raise ValueError("Eye must have executed before Critique")
    if record.brain is None or record.brain.result is None:
        raise ValueError("Brain must have executed before Critique")
    if record.stylist is None or record.stylist.result is None:
        raise ValueError("Stylist must have executed before Critique")
    if record.engine is None or record.engine.result is None:
        raise ValueError("Engine compile must have executed before Critique")
    if record.generation is None or record.generation.receipt is None:
        raise ValueError("Generation must have executed before Critique")
    receipt = record.generation.receipt
    if receipt.output is None:
        raise ValueError("Generation must include an output before Critique")

    original_id = _original_reference_id(record)
    return CritiqueInput(
        job_id=record.job_id,
        contract_id=record.contract.contract_id,
        revision=record.revision,
        contract=record.contract,
        observation=record.observation,
        brain_plan=record.brain.result,
        stylist_plan=record.stylist.result,
        compile=record.engine.result,
        operation=record.generation.operation,
        receipt=receipt,
        original_reference_id=original_id,
        generated_output_id=receipt.output.output_id,
        stage=record.stage,
        state=record.state,
    )


def execute_critique(
    *,
    critique_input: CritiqueInput,
    model_id: str,
    original_bytes: bytes,
    original_media_type: str,
    generated_bytes: bytes,
    generated_media_type: str,
    provider: CritiqueProvider,
) -> CritiqueResult:
    """Pass the caller-supplied model id and image pair to the provider."""

    if not model_id.strip():
        raise ValueError("model_id must be supplied by the caller")
    if not original_bytes:
        raise ValueError("original reference image bytes are required")
    if not generated_bytes:
        raise ValueError("generated image bytes are required")
    request = CritiqueProviderRequest(
        model_id=model_id,
        critique_input=critique_input,
        original_bytes=original_bytes,
        original_media_type=original_media_type,
        generated_bytes=generated_bytes,
        generated_media_type=generated_media_type,
    )
    assessment = provider.assess(request)
    validate_critique_assessment(critique_input, assessment)
    return CritiqueResult(
        job_id=critique_input.job_id,
        contract_id=critique_input.contract_id,
        revision=critique_input.revision,
        model_id=model_id,
        execution_status="completed",
        assessment=assessment,
    )


def validate_critique_assessment(
    critique_input: CritiqueInput, assessment: CritiqueAssessment
) -> None:
    """Reject assessments that rewrite identity or ignore lock failures."""

    if assessment.job_id != critique_input.job_id:
        raise CritiqueAssessmentInvalidError("Critique job_id does not match the job")
    if (
        assessment.contract_id != critique_input.contract_id
        or assessment.contract_revision != critique_input.revision
    ):
        raise CritiqueAssessmentInvalidError(
            "Critique must bind the frozen job contract revision"
        )
    compile_artifact = critique_input.compile
    if (
        assessment.engine_contract_id != compile_artifact.contract_id
        or assessment.engine_revision != compile_artifact.contract_revision
    ):
        raise CritiqueAssessmentInvalidError("Critique must bind the stored EngineCompile")
    if assessment.generation_operation_key != critique_input.operation.operation_key:
        raise CritiqueAssessmentInvalidError(
            "Critique must bind the claimed generation operation_key"
        )
    output = critique_input.receipt.output
    if output is None or assessment.generation_output_id != output.output_id:
        raise CritiqueAssessmentInvalidError(
            "Critique must bind the completed generation output"
        )
    lock_failures = [
        item
        for item in assessment.findings
        if item.dimension in LOCK_DIMENSIONS and item.result == "fail"
    ]
    if assessment.overall_result == "pass" and lock_failures:
        raise CritiqueAssessmentInvalidError(
            "overall pass cannot override inventory, identity, or geometry failure"
        )


def critique_may_proceed(compile_artifact: EngineCompile) -> bool:
    return compile_artifact.status == "ready" and bool(compile_artifact.exact_prompt.strip())


def generated_image_bytes(record: JobRecord) -> bytes | None:
    stored = record.generation
    if stored is None or stored.receipt is None or stored.receipt.output is None:
        return None
    output = stored.receipt.output
    data = record.reference_bytes.get(output.output_id)
    if data:
        return data
    return get_artifact_store().get_output(
        record.job_id, output_filename(output.media_type)
    )


def original_reference_bytes(record: JobRecord) -> tuple[str, bytes, str] | None:
    reference_id = _original_reference_id(record)
    data = record.reference_bytes.get(reference_id)
    if not data:
        return None
    reference = next(
        item for item in record.contract.references if item.reference_id == reference_id
    )
    return reference_id, data, reference.media_type


def _original_reference_id(record: JobRecord) -> str:
    preferred = [
        item
        for item in record.contract.references
        if item.role == "Product / vendor reference"
        and item.reference_id in record.reference_bytes
    ]
    if preferred:
        return preferred[0].reference_id
    for item in record.contract.references:
        if item.reference_id in record.reference_bytes:
            return item.reference_id
    raise ValueError("Critique requires original reference image bytes")
