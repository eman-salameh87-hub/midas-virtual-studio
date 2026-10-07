"""Engine · compile execution boundary.

Builds EngineInput from persisted Job State (Contract + Eye + Brain + Stylist)
and validates an EngineCompile. This module does not choose a model, generate
an image, or call a provider gateway for rendering.
"""

from app.contracts.brain import BrainPlan
from app.contracts.engine import EngineCompile
from app.contracts.stylist import StylistPlan
from app.providers.brain import BrainEvidenceRef
from app.providers.engine import (
    EngineCompiler,
    EngineInput,
    EngineProviderRequest,
    EngineResult,
)
from app.runtime.state import JobRecord


class EngineCompileInvalidError(ValueError):
    """Compiler output failed EngineCompile validation against Job State."""


def build_engine_input(record: JobRecord) -> EngineInput:
    """Copy frozen contract, Eye, Brain, Stylist, and evidence identity."""

    if record.observation is None or record.readiness is None:
        raise ValueError("Eye must have executed before Engine compile")
    if record.brain is None or record.brain.result is None:
        raise ValueError("Brain must have executed before Engine compile")
    if record.stylist is None or record.stylist.result is None:
        raise ValueError("Stylist must have executed before Engine compile")

    evidence = [
        BrainEvidenceRef(
            reference_id=reference.reference_id,
            filename=reference.filename,
            media_type=reference.media_type,
            hash_algorithm=reference.hash_algorithm,
            content_hash=reference.content_hash,
            role=reference.role,
            bytes_available=reference.reference_id in record.reference_bytes,
        )
        for reference in record.contract.references
    ]
    return EngineInput(
        job_id=record.job_id,
        contract_id=record.contract.contract_id,
        revision=record.revision,
        contract=record.contract,
        observation=record.observation,
        brain_plan=record.brain.result,
        stylist_plan=record.stylist.result,
        evidence=evidence,
        stage=record.stage,
        state=record.state,
    )


def execute_engine(
    *,
    engine_input: EngineInput,
    model_id: str,
    compiler: EngineCompiler,
) -> EngineResult:
    """Pass the caller-supplied model id and Job State snapshot to the compiler."""

    if not model_id.strip():
        raise ValueError("model_id must be supplied by the caller")
    request = EngineProviderRequest(
        model_id=model_id,
        engine_input=engine_input,
    )
    artifact = compiler.compile(request)
    validate_engine_compile(engine_input, artifact)
    return EngineResult(
        job_id=engine_input.job_id,
        contract_id=engine_input.contract.contract_id,
        revision=engine_input.contract.revision,
        brain_contract_id=engine_input.brain_plan.contract_id,
        brain_revision=engine_input.brain_plan.contract_revision,
        stylist_contract_id=engine_input.stylist_plan.contract_id,
        stylist_revision=engine_input.stylist_plan.contract_revision,
        model_id=model_id,
        execution_status="completed",
        compile=artifact,
    )


def validate_engine_compile(engine_input: EngineInput, artifact: EngineCompile) -> None:
    """Reject compile artifacts that break upstream authority or invent evidence."""

    contract = engine_input.contract
    brain_plan = engine_input.brain_plan
    stylist_plan = engine_input.stylist_plan

    if artifact.job_id != engine_input.job_id:
        raise EngineCompileInvalidError("Engine compile job_id does not match the job")
    if (
        artifact.contract_id != contract.contract_id
        or artifact.contract_revision != contract.revision
    ):
        raise EngineCompileInvalidError(
            "Engine compile must bind the frozen job contract revision"
        )
    if (
        artifact.brain_contract_id != brain_plan.contract_id
        or artifact.brain_revision != brain_plan.contract_revision
    ):
        raise EngineCompileInvalidError("Engine compile must bind the stored BrainPlan")
    if (
        artifact.stylist_contract_id != stylist_plan.contract_id
        or artifact.stylist_revision != stylist_plan.contract_revision
    ):
        raise EngineCompileInvalidError("Engine compile must bind the stored StylistPlan")
    if artifact.product_role != stylist_plan.product_role:
        raise EngineCompileInvalidError(
            "Engine compile product_role must match the Stylist plan"
        )
    if artifact.model_id.strip() == "":
        raise EngineCompileInvalidError("Engine compile model_id must be recorded")

    expected_refs = [
        (
            item.reference_id,
            item.role,
            item.media_type,
            item.content_hash,
            item.hash_algorithm,
            item.filename,
        )
        for item in contract.references
    ]
    actual_refs = [
        (
            item.reference_id,
            item.role,
            item.media_type,
            item.content_hash,
            item.hash_algorithm,
            item.filename,
        )
        for item in artifact.references
    ]
    if actual_refs != expected_refs:
        raise EngineCompileInvalidError(
            "Engine compile must preserve contract reference order, roles, and provenance"
        )

    expected_locks = [
        (item.name, item.value, item.source, item.evidence_reference_id)
        for item in brain_plan.invariants
    ]
    actual_locks = [
        (item.name, item.value, item.source, item.evidence_reference_id)
        for item in artifact.locks
    ]
    if actual_locks != expected_locks:
        raise EngineCompileInvalidError("Engine compile must preserve Brain invariants")

    if artifact.variables != brain_plan.variables:
        raise EngineCompileInvalidError("Engine compile must preserve Brain variables")
    if artifact.scene != stylist_plan.scene:
        raise EngineCompileInvalidError("Engine compile must preserve Stylist scene")
    if artifact.selected_layout != stylist_plan.selected_layout:
        raise EngineCompileInvalidError(
            "Engine compile must preserve Stylist selected layout"
        )
    if artifact.hero_prominence != stylist_plan.hero_prominence:
        raise EngineCompileInvalidError(
            "Engine compile must preserve Stylist hero prominence"
        )
    if artifact.view_requirements != stylist_plan.view_requirements:
        raise EngineCompileInvalidError(
            "Engine compile must preserve Stylist view requirements"
        )

    if artifact.output_format.image_proportions != contract.outputs.image_proportions:
        raise EngineCompileInvalidError(
            "Engine compile output proportions must match the job contract"
        )
    if artifact.output_format.resolution != contract.outputs.resolution:
        raise EngineCompileInvalidError(
            "Engine compile output resolution must match the job contract"
        )
    if artifact.requested_view not in contract.outputs.views:
        raise EngineCompileInvalidError(
            "Engine compile requested_view must be one of the job contract views"
        )

    brain_unknown_subjects = {item.subject for item in brain_plan.unknowns}
    artifact_unknown_subjects = {item.subject for item in artifact.unknowns}
    if not brain_unknown_subjects.issubset(artifact_unknown_subjects):
        raise EngineCompileInvalidError("Engine compile must preserve Brain unknowns")

    if artifact.status == "ready" and not artifact.exact_prompt.strip():
        raise EngineCompileInvalidError(
            "a ready Engine compile must include the exact prompt"
        )


def engine_may_proceed(brain_plan: BrainPlan, stylist_plan: StylistPlan) -> bool:
    """Brain or Stylist hold means Engine does not compile as ready."""

    return brain_plan.status == "ready" and stylist_plan.status == "ready"
