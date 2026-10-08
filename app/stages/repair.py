"""Bounded Critique · repair planning and execution helpers.

Does not implement Repair #3. Does not choose models. Does not release.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from app.contracts.critique import LOCK_DIMENSIONS, CritiqueAssessment, CritiqueDimension
from app.contracts.engine import EngineCompile
from app.contracts.generation import GenerationOperation
from app.contracts.repair import (
    REPAIR_LIMIT,
    PreservationStatus,
    RepairAction,
    RepairLineage,
    RepairPlan,
)
from app.providers.generation import GenerationProvider
from app.providers.repair import RepairPlannerRequest
from app.runtime.state import JobRecord
from app.stages.critique import original_reference_bytes
from app.stages.operator import REQUIRED_CAPABILITIES, missing_capabilities

LOCAL_EDIT_UNSUPPORTED_REASON = (
    "local_edit is not supported by the current generation provider; "
    "scene preservation was not claimed"
)
FRESH_RENDER_UNSUPPORTED_REASON = (
    "fresh_render is not supported by the current generation provider"
)
GEOMETRY_LOCK_DIMENSIONS: frozenset[CritiqueDimension] = frozenset(
    {"inventory", "identity", "geometry"}
)


class RepairBudgetExhaustedError(ValueError):
    """Repair #3 is not allowed."""


def current_repair_count(record: JobRecord) -> int:
    return int(record.repair_count)


def repair_budget_remaining(record: JobRecord) -> bool:
    return current_repair_count(record) < REPAIR_LIMIT


def failed_findings(assessment: CritiqueAssessment) -> list:
    return [item for item in assessment.findings if item.result == "fail"]


def passing_dimensions(assessment: CritiqueAssessment) -> list[str]:
    return [item.dimension for item in assessment.findings if item.result == "pass"]


def named_repair_instructions(assessment: CritiqueAssessment) -> list[str]:
    instructions: list[str] = []
    for item in failed_findings(assessment):
        text = item.repair_instruction or item.observation
        if text.strip() and text not in instructions:
            instructions.append(text.strip())
    return instructions


def select_repair_action(assessment: CritiqueAssessment) -> RepairAction:
    """Geometry or identity corruption returns to originals. Else smallest edit."""

    fails = failed_findings(assessment)
    if not fails:
        return "hold"
    if any(item.dimension in GEOMETRY_LOCK_DIMENSIONS for item in fails):
        return "fresh_render"
    if _repeated_geometry_corruption(assessment):
        return "fresh_render"
    return "local_edit"


def _repeated_geometry_corruption(assessment: CritiqueAssessment) -> bool:
    return any(
        item.dimension == "geometry" and item.result == "fail" for item in assessment.findings
    )


def protected_scene_attributes(request: RepairPlannerRequest) -> list[str]:
    """Accepted scene facts the repair must keep. This does not rewrite the plan."""

    scene = request.stylist_plan.scene
    layout = request.stylist_plan.selected_layout
    props = [item.name for item in request.stylist_plan.supporting_props]
    attributes = [
        f"room: {scene.setting}",
        "supporting props: " + (", ".join(props) if props else "none declared"),
        f"placement: {layout.arrangement_detail}",
        f"lighting: {scene.light}",
        f"composition: {layout.focal_hierarchy}",
    ]
    for lock in request.contract.changes.room_locks:
        attributes.append(f"room lock: {lock}")
    return attributes


def build_repair_plan(
    request: RepairPlannerRequest,
    *,
    action: RepairAction | None = None,
    hold_reasons: list[str] | None = None,
    status: str | None = None,
    preservation_status: PreservationStatus | None = None,
    preservation_result: str | None = None,
) -> RepairPlan:
    """Convert named Critique failures into a bounded RepairPlan."""

    assessment = request.assessment
    fails = failed_findings(assessment)
    chosen = action or select_repair_action(assessment)
    next_count = request.repair_count + 1 if chosen != "hold" else request.repair_count
    if next_count > REPAIR_LIMIT:
        chosen = "hold"
        next_count = REPAIR_LIMIT
        hold_reasons = list(hold_reasons or []) or [
            "repair budget exhausted after two attempts"
        ]
    version_from = len(request.previous_repairs) + 1
    reasons = list(hold_reasons or [])
    if chosen == "hold" and not reasons:
        reasons = ["repair held by the bounded controller"]
    plan_status = status or ("hold" if chosen == "hold" else "planned")
    original_id = request.original_reference_id
    protected = protected_scene_attributes(request)
    targeted = [item.dimension for item in fails]
    if preservation_status is None or preservation_result is None:
        derived_status, derived_result = _preservation_for(chosen, reasons)
        preservation_status = preservation_status or derived_status
        preservation_result = preservation_result if preservation_result is not None else derived_result
    return RepairPlan(
        job_id=request.job_id,
        contract_id=request.contract_id,
        contract_revision=request.revision,
        critique_generation_output_id=assessment.generation_output_id,
        critique_generation_operation_key=assessment.generation_operation_key,
        source_generation_output_id=request.generated_output_id,
        source_generation_operation_key=request.operation.operation_key,
        original_reference_id=original_id,
        repair_count=next_count if chosen != "hold" else min(next_count, REPAIR_LIMIT),
        repair_limit=REPAIR_LIMIT,
        target_regions=[item.dimension for item in fails],
        repair_instructions=named_repair_instructions(assessment),
        preserve_list=passing_dimensions(assessment),
        previous_defects=[
            f"{item.dimension}: {item.observation}" for item in fails
        ],
        required_resolution_checks=[
            f"{item.dimension}: {item.expected}" for item in fails
        ],
        action=chosen,
        model_id=request.model_id,
        status=plan_status,  # type: ignore[arg-type]
        hold_reasons=reasons if chosen == "hold" else [],
        lineage=RepairLineage(
            source_generation_output_id=request.generated_output_id,
            source_generation_operation_key=request.operation.operation_key,
            source_critique_generation_output_id=assessment.generation_output_id,
            original_reference_id=original_id,
            version_from=version_from,
            version_to=None,
            result_generation_output_id=None,
            result_generation_operation_key=None,
        ),
        operation=None,
        receipt=None,
        scene_base_reference=request.generated_output_id,
        product_authority_reference=original_id,
        protected_scene_attributes=protected,
        targeted_attributes=targeted,
        preservation_status=preservation_status,
        preservation_result=preservation_result,
    )


def _preservation_for(
    action: RepairAction, reasons: list[str]
) -> tuple[PreservationStatus, str]:
    if action == "local_edit":
        return (
            "pending",
            "local_edit will use the previous generation as the scene base "
            "and the original reference as product authority",
        )
    if action == "fresh_render":
        return (
            "not_claimed",
            "fresh_render does not preserve the previous scene; "
            "the original reference remains the product authority",
        )
    if any("local_edit" in reason for reason in reasons):
        return (
            "unsupported",
            "local_edit is unsupported; scene preservation was not claimed",
        )
    return (
        "not_claimed",
        "repair was held; scene preservation was not claimed",
    )


def local_edit_supported(provider: GenerationProvider) -> bool:
    capabilities = provider.capabilities()
    return "image_generation" in capabilities and "local_edit" in capabilities


def repair_action_supported(action: RepairAction, provider: GenerationProvider) -> bool:
    if action == "hold":
        return True
    if action == "fresh_render":
        return not missing_capabilities(provider, list(REQUIRED_CAPABILITIES))
    if action == "local_edit":
        return local_edit_supported(provider)
    return False


def repair_operation_key(
    compile_artifact: EngineCompile,
    *,
    repair_count: int,
    source_output_id: str,
    action: RepairAction,
) -> str:
    payload = {
        "job_id": compile_artifact.job_id,
        "contract_id": compile_artifact.contract_id,
        "contract_revision": compile_artifact.contract_revision,
        "model_id": compile_artifact.model_id,
        "repair_count": repair_count,
        "source_output_id": source_output_id,
        "action": action,
        "reference_ids": [item.reference_id for item in compile_artifact.references],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_repair_generation_operation(
    record: JobRecord,
    plan: RepairPlan,
    *,
    claimed_at: str | None = None,
) -> GenerationOperation:
    compile_artifact = record.engine.result  # type: ignore[union-attr]
    assert compile_artifact is not None
    original_id = plan.original_reference_id
    reference_ids = [item.reference_id for item in compile_artifact.references]
    if original_id not in reference_ids:
        raise ValueError("repair generation must keep the original identity reference")
    prompt = repair_exact_prompt(compile_artifact.exact_prompt, plan)
    return GenerationOperation(
        job_id=record.job_id,
        contract_id=record.contract.contract_id,
        contract_revision=record.revision,
        compile_contract_id=compile_artifact.contract_id,
        compile_revision=compile_artifact.contract_revision,
        operation_key=repair_operation_key(
            compile_artifact,
            repair_count=plan.repair_count,
            source_output_id=plan.source_generation_output_id,
            action=plan.action,
        ),
        model_id=compile_artifact.model_id,
        exact_prompt=prompt,
        reference_ids=reference_ids,
        requested_view=compile_artifact.requested_view,
        output_format=compile_artifact.output_format,
        required_capabilities=list(REQUIRED_CAPABILITIES),
        claimed_at=claimed_at or _now(),
    )


def repair_exact_prompt(compile_prompt: str, plan: RepairPlan) -> str:
    targets = "; ".join(plan.targeted_attributes or plan.target_regions) or "named defects only"
    instructions = " ".join(plan.repair_instructions)
    preserve = ", ".join(plan.preserve_list) if plan.preserve_list else "all passing dimensions"
    protected = (
        "; ".join(plan.protected_scene_attributes)
        if plan.protected_scene_attributes
        else "room, supporting props, placement, lighting, composition"
    )
    if plan.action == "local_edit":
        edit_rule = (
            "Action local_edit: change only the targeted attributes. "
            "The previous generated image is the scene base. "
            "Preserve the surrounding accepted scene."
        )
    elif plan.action == "fresh_render":
        edit_rule = (
            "Action fresh_render: this does not preserve the previous scene pixels. "
            "The original product reference remains the product authority."
        )
    else:
        edit_rule = "Action hold: do not claim a repaired image."
    return (
        f"{compile_prompt}\n\n"
        "MIDAS bounded repair. The original product reference remains the "
        "authoritative identity source. Do not replace it with a previous "
        f"generated candidate.\n"
        f"Scene base reference: {plan.scene_base_reference or 'unavailable'}.\n"
        f"Product authority reference: {plan.product_authority_reference or plan.original_reference_id}.\n"
        f"{edit_rule}\n"
        f"Repair only: {targets}.\n"
        f"Instructions: {instructions}\n"
        f"Protected scene attributes: {protected}.\n"
        f"Preserve unchanged: {preserve}.\n"
        "Do not invent new product facts. Compare unaffected protected regions "
        "again after the correction. A repaired area cannot hide a new regression."
    )


def repair_reference_bytes(record: JobRecord, plan: RepairPlan) -> dict[str, bytes]:
    """Original identity bytes always included. Candidate bytes never replace them."""

    selected: dict[str, bytes] = {}
    original = original_reference_bytes(record)
    if original is not None:
        reference_id, data, _media = original
        selected[reference_id] = data
    compile_artifact = record.engine.result if record.engine else None
    if compile_artifact is not None:
        for item in compile_artifact.references:
            data = record.reference_bytes.get(item.reference_id)
            if data:
                selected[item.reference_id] = data
    if plan.action == "local_edit" and plan.scene_base_reference:
        scene_bytes = record.reference_bytes.get(plan.scene_base_reference)
        if scene_bytes:
            selected[plan.scene_base_reference] = scene_bytes
    return selected


def previous_defects_unresolved(
    previous: CritiqueAssessment, current: CritiqueAssessment
) -> list[str]:
    previous_fails = {item.dimension for item in failed_findings(previous)}
    current_fails = {item.dimension for item in failed_findings(current)}
    return sorted(previous_fails & current_fails)


def new_regressions(
    previous: CritiqueAssessment, current: CritiqueAssessment
) -> list[str]:
    previously_pass = {item.dimension for item in previous.findings if item.result == "pass"}
    now_fail = {item.dimension for item in failed_findings(current)}
    return sorted(previously_pass & now_fail)


def lock_failures(assessment: CritiqueAssessment) -> list[str]:
    return [
        item.dimension
        for item in assessment.findings
        if item.dimension in LOCK_DIMENSIONS and item.result == "fail"
    ]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
