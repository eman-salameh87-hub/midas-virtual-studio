"""Stylist execution boundary.

Builds StylistInput from persisted Job State (Contract + EyeObservation + BrainPlan)
and validates a StylistPlan.
This module does not choose a model, retrieve a catalogue, or compile an image prompt.
"""

from app.contracts.brain import BrainPlan
from app.contracts.stylist import StylistPlan
from app.providers.brain import BrainEvidenceRef
from app.providers.stylist import (
    StylistInput,
    StylistProvider,
    StylistProviderRequest,
    StylistResult,
)
from app.runtime.state import JobRecord


class StylistPlanInvalidError(ValueError):
    """Provider JSON parsed but failed Stylist plan validation."""


def build_stylist_input(record: JobRecord) -> StylistInput:
    """Copy the frozen contract, stored Eye observation, Brain plan, and evidence identity."""

    if record.observation is None or record.readiness is None:
        raise ValueError("Eye must have executed before Stylist")
    if record.brain is None or record.brain.result is None:
        raise ValueError("Brain must have executed before Stylist")

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
    return StylistInput(
        job_id=record.job_id,
        contract_id=record.contract.contract_id,
        revision=record.revision,
        contract=record.contract,
        observation=record.observation,
        brain_plan=record.brain.result,
        evidence=evidence,
        verified_complements=[],
        stage=record.stage,
        state=record.state,
    )


def execute_stylist(
    *,
    stylist_input: StylistInput,
    model_id: str,
    provider: StylistProvider,
) -> StylistResult:
    """Pass the caller-supplied model id and Job State snapshot to the provider."""

    if not model_id.strip():
        raise ValueError("model_id must be supplied by the caller")
    request = StylistProviderRequest(
        model_id=model_id,
        stylist_input=stylist_input,
    )
    plan = provider.compose(request)
    validate_stylist_plan(stylist_input, plan)
    return StylistResult(
        job_id=stylist_input.job_id,
        contract_id=stylist_input.contract.contract_id,
        revision=stylist_input.contract.revision,
        brain_contract_id=stylist_input.brain_plan.contract_id,
        brain_revision=stylist_input.brain_plan.contract_revision,
        model_id=model_id,
        execution_status="completed",
        plan=plan,
    )


def validate_stylist_plan(stylist_input: StylistInput, plan: StylistPlan) -> None:
    """Reject plans that break contract/Brain authority or fabricate evidence."""

    contract = stylist_input.contract
    brain_plan = stylist_input.brain_plan

    if plan.job_id != stylist_input.job_id:
        raise StylistPlanInvalidError("Stylist plan job_id does not match the job")
    if plan.contract_id != contract.contract_id or plan.contract_revision != contract.revision:
        raise StylistPlanInvalidError("Stylist plan must bind the frozen job contract revision")
    if (
        plan.brain_contract_id != brain_plan.contract_id
        or plan.brain_revision != brain_plan.contract_revision
    ):
        raise StylistPlanInvalidError("Stylist plan must bind the stored BrainPlan")
    if plan.product_role != contract.item.product_role:
        raise StylistPlanInvalidError("Stylist plan product_role must match the contract")

    # Verify no unverified Midas companions are introduced
    verified_skus = {c.sku for c in stylist_input.verified_complements}
    for comp in plan.midas_complements:
        if comp.sku not in verified_skus:
            # If no catalogue retrieval has verified this companion, reject
            raise StylistPlanInvalidError(
                f"Midas companion SKU {comp.sku!r} is not in verified catalogue evidence"
            )

    # Unknowns preservation
    brain_unknown_subjects = {item.subject for item in brain_plan.unknowns}
    plan_unknown_subjects = {item.subject for item in plan.unknowns}
    if not brain_unknown_subjects.issubset(plan_unknown_subjects):
        raise StylistPlanInvalidError("Stylist must preserve Brain unknowns")


def stylist_may_proceed(brain_plan: BrainPlan) -> bool:
    """Use existing Brain status. Hold means Stylist does not execute."""

    return brain_plan.status == "ready"
