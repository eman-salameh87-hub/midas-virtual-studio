"""Brain execution boundary.

Builds BrainInput from persisted Job State and validates a BrainPlan.
This module does not choose a model, retrieve a catalogue, or compile
an image prompt.
"""

from app.contracts.brain import BrainPlan
from app.providers.brain import (
    BrainEvidenceRef,
    BrainInput,
    BrainProvider,
    BrainProviderRequest,
    BrainResult,
)
from app.runtime.state import JobRecord
from app.stages.eye import Readiness


class BrainPlanInvalidError(ValueError):
    """Provider JSON parsed but failed Brain plan validation."""


def build_brain_input(record: JobRecord) -> BrainInput:
    """Copy the frozen contract, stored Eye result, and evidence identity."""

    if record.observation is None or record.readiness is None:
        raise ValueError("Eye must have executed before Brain")
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
    return BrainInput(
        job_id=record.job_id,
        contract_id=record.contract.contract_id,
        revision=record.revision,
        contract=record.contract,
        observation=record.observation,
        readiness=record.readiness,
        evidence=evidence,
        stage=record.stage,
        state=record.state,
    )


def execute_brain(
    *,
    brain_input: BrainInput,
    model_id: str,
    provider: BrainProvider,
) -> BrainResult:
    """Pass the caller-supplied model id and Job State snapshot to the provider."""

    if not model_id.strip():
        raise ValueError("model_id must be supplied by the caller")
    request = BrainProviderRequest(
        model_id=model_id,
        brain_input=brain_input,
    )
    plan = provider.reason(request)
    validate_brain_plan(brain_input, plan)
    return BrainResult(
        job_id=brain_input.job_id,
        contract_id=brain_input.contract.contract_id,
        revision=brain_input.contract.revision,
        observation_contract_id=brain_input.observation.contract_id,
        observation_revision=brain_input.observation.revision,
        model_id=model_id,
        execution_status="completed",
        plan=plan,
    )


def validate_brain_plan(brain_input: BrainInput, plan: BrainPlan) -> None:
    """Reject plans that break contract/Eye authority or fabricate evidence."""

    contract = brain_input.contract
    observation = brain_input.observation
    if plan.job_id != brain_input.job_id:
        raise BrainPlanInvalidError("Brain plan job_id does not match the job")
    if plan.contract_id != contract.contract_id or plan.contract_revision != contract.revision:
        raise BrainPlanInvalidError("Brain plan must bind the frozen job contract revision")
    if (
        plan.observation_contract_id != observation.contract_id
        or plan.observation_revision != observation.revision
    ):
        raise BrainPlanInvalidError("Brain plan must bind the stored EyeObservation")
    if plan.mode != contract.changes.policy_mode:
        raise BrainPlanInvalidError("Brain mode must equal the contract policy_mode")
    if plan.route.input_condition != contract.source_condition.input_condition:
        raise BrainPlanInvalidError("Brain route input_condition must match the contract")
    if plan.route.category != contract.item.category:
        raise BrainPlanInvalidError("Brain route category must match the contract")
    if plan.route.product_role != contract.item.product_role:
        raise BrainPlanInvalidError("Brain route product_role must match the contract")

    allowed_outputs = set(contract.outputs.package_members) | set(contract.outputs.views)
    for item in plan.required_outputs:
        if item.output not in allowed_outputs:
            raise BrainPlanInvalidError(
                f"required output {item.output!r} is not on the job contract"
            )
        if not item.acceptance_checks:
            raise BrainPlanInvalidError("each required output needs acceptance checks")

    evidence_ids = {item.reference_id for item in brain_input.evidence}
    for item in plan.invariants:
        if item.evidence_reference_id and item.evidence_reference_id not in evidence_ids:
            raise BrainPlanInvalidError("Brain invariant cites unknown evidence")
    for item in plan.grounding:
        if item.evidence_reference_id and item.evidence_reference_id not in evidence_ids:
            raise BrainPlanInvalidError("Brain grounding cites unknown evidence")

    protected = {value.casefold() for value in contract.changes.protected_identity}
    for variable in plan.variables:
        if variable.value.casefold() in protected:
            raise BrainPlanInvalidError(
                "protected identity cannot become a creative variable"
            )
        if variable.name.casefold() in protected:
            raise BrainPlanInvalidError(
                "protected identity cannot become a creative variable"
            )

    count_invariants = [item for item in plan.invariants if item.name == "count"]
    if contract.intent.selected_count.status == "declared":
        expected = str(contract.intent.selected_count.value)
        if not any(item.value == expected for item in count_invariants):
            raise BrainPlanInvalidError("user-selected count must remain an invariant")

    unknown_subjects = {item.subject for item in observation.unknowns}
    plan_unknowns = {item.subject for item in plan.unknowns}
    if not unknown_subjects.issubset(plan_unknowns):
        raise BrainPlanInvalidError("Brain must preserve Eye unknowns")
    for ambiguity in observation.ambiguities:
        if ambiguity.status == "unresolved" and ambiguity.subject not in plan_unknowns:
            raise BrainPlanInvalidError("Brain must preserve unresolved Eye ambiguities")


def brain_may_proceed(readiness: Readiness) -> bool:
    """Use existing Eye readiness. Hold means Brain does not execute."""

    return readiness.status == "ready"
