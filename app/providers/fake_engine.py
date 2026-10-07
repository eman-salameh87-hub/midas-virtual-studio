"""Deterministic Engine compiler for local tests and the default compile path.

It does not call a network, generate an image, invent references, or choose a
model. It compiles Brain locks and Stylist decisions into EngineCompile.
"""

from __future__ import annotations

from app.contracts.engine import (
    EngineCompile,
    EngineOutputFormat,
    EngineUnknown,
)
from app.contracts.job import OutputView
from app.contracts.reference import ReferenceAsset
from app.providers.engine import EngineInput, EngineProviderRequest


class FakeEngineCompiler:
    """In-memory compiler. `requests` records exactly what the caller passed."""

    def __init__(self, violation: str | None = None) -> None:
        self.violation = violation
        self.requests: list[EngineProviderRequest] = []

    def compile(self, request: EngineProviderRequest) -> EngineCompile:
        self.requests.append(request)
        return compile_for(request.engine_input, model_id=request.model_id, violation=self.violation)


def compile_for(
    engine_input: EngineInput,
    *,
    model_id: str,
    violation: str | None = None,
) -> EngineCompile:
    """Build one EngineCompile bound to this EngineInput."""

    contract = engine_input.contract
    brain_plan = engine_input.brain_plan
    stylist_plan = engine_input.stylist_plan

    references = [
        ReferenceAsset(
            reference_id=item.reference_id,
            filename=item.filename,
            media_type=item.media_type,
            hash_algorithm=item.hash_algorithm,
            content_hash=item.content_hash,
            role=item.role,
        )
        for item in contract.references
    ]
    if violation == "invent_reference":
        references = list(references) + [
            ReferenceAsset(
                reference_id="ref-invented-catalogue",
                filename="invented.png",
                media_type="PNG",
                hash_algorithm="sha256",
                content_hash="ff" * 32,
                role="Inspiration / look",
            )
        ]

    locks = list(brain_plan.invariants)
    variables = list(brain_plan.variables)
    unknowns = [
        EngineUnknown(subject=item.subject, detail=item.detail)
        for item in stylist_plan.unknowns
    ]
    if not unknowns:
        unknowns = [
            EngineUnknown(subject=item.subject, detail=item.detail)
            for item in brain_plan.unknowns
        ]

    hold_reasons: list[str] = []
    if violation == "hold":
        hold_reasons.append("Engine hold requested for testing")
    if violation == "missing_critical":
        hold_reasons.append(
            "critical unknown blocks safe compilation; missing information was not fabricated"
        )
    if not contract.outputs.views:
        hold_reasons.append("requested view is missing from the job contract")

    lock_names = {item.name for item in locks}
    for required in ("count", "identity", "source-supported construction"):
        if required not in lock_names:
            hold_reasons.append(f"required Brain lock {required!r} is missing")

    if violation == "drop_locks":
        locks = [item for item in locks if item.name == "identity"]
        hold_reasons.append("required Brain locks were dropped")

    status = "hold" if hold_reasons else "ready"
    requested_view = _requested_view(contract.outputs.views, violation=violation)
    exact_prompt = ""
    if status == "ready":
        exact_prompt = _exact_prompt(
            engine_input=engine_input,
            requested_view=requested_view,
            references=references,
        )
    elif violation == "ready_with_blank_prompt":
        # Invalid READY shape used only to exercise stage validation.
        status = "ready"
        hold_reasons = []
        exact_prompt = "   "

    brain_contract_id = (
        contract.contract_id
        if violation != "mismatched_brain_contract"
        else "mismatched-brain-contract"
    )
    brain_revision = (
        brain_plan.contract_revision
        if violation != "mismatched_brain_revision"
        else brain_plan.contract_revision + 99
    )
    stylist_contract_id = (
        contract.contract_id
        if violation != "mismatched_stylist_contract"
        else "mismatched-stylist-contract"
    )
    stylist_revision = (
        stylist_plan.contract_revision
        if violation != "mismatched_stylist_revision"
        else stylist_plan.contract_revision + 99
    )

    return EngineCompile(
        job_id=engine_input.job_id,
        contract_id=contract.contract_id,
        contract_revision=contract.revision,
        brain_contract_id=brain_contract_id,
        brain_revision=brain_revision,
        stylist_contract_id=stylist_contract_id,
        stylist_revision=stylist_revision,
        product_role=stylist_plan.product_role,
        references=references,
        locks=locks,
        variables=variables,
        scene=stylist_plan.scene,
        selected_layout=stylist_plan.selected_layout,
        hero_prominence=stylist_plan.hero_prominence,
        requested_view=requested_view,
        view_requirements=stylist_plan.view_requirements,
        output_format=EngineOutputFormat(
            image_proportions=contract.outputs.image_proportions,
            resolution=contract.outputs.resolution,
        ),
        exact_prompt=exact_prompt,
        model_id=model_id,
        unknowns=unknowns,
        status=status,
        hold_reasons=hold_reasons,
    )


def _requested_view(views: list[OutputView], *, violation: str | None) -> OutputView:
    if violation == "force_close_up":
        return "Close-up"
    if not views:
        return "Wide view"
    return views[0]


def _exact_prompt(
    *,
    engine_input: EngineInput,
    requested_view: OutputView,
    references: list[ReferenceAsset],
) -> str:
    """Deterministic compile text from upstream decisions only."""

    contract = engine_input.contract
    brain_plan = engine_input.brain_plan
    stylist_plan = engine_input.stylist_plan
    layout = stylist_plan.selected_layout
    scene = stylist_plan.scene
    views = stylist_plan.view_requirements

    lock_lines = [
        f"- {item.name}: {item.value} (source: {item.source})"
        for item in brain_plan.invariants
    ]
    variable_lines = [
        f"- {item.name}: {item.value} (authorized={item.authorized})"
        for item in brain_plan.variables
    ]
    reference_lines = [
        f"{index}. {item.reference_id} · role={item.role} · "
        f"media={item.media_type} · sha256={item.content_hash}"
        for index, item in enumerate(references, start=1)
    ]
    acceptance = []
    for item in brain_plan.required_outputs:
        acceptance.append(
            f"- output={item.output}; checks={'; '.join(item.acceptance_checks)}"
        )

    supporting = []
    for prop in stylist_plan.supporting_props:
        placement = prop.placement or "placement not specified"
        supporting.append(
            f"- context prop {prop.name}: {prop.purpose} ({placement}); not a Midas SKU"
        )
    for complement in stylist_plan.midas_complements:
        supporting.append(
            f"- Midas companion {complement.sku}: {complement.name}; "
            f"function={complement.function}; source={complement.source_reference}"
        )

    unknown_lines = [
        f"- do not assert {item.subject}: {item.detail}"
        for item in stylist_plan.unknowns or brain_plan.unknowns
    ]
    if not unknown_lines:
        unknown_lines = ["- no unresolved unknowns were carried forward"]

    view_lines = [f"- requested view: {requested_view}"]
    if views.wide_view_requirements:
        view_lines.append(f"- wide view: {views.wide_view_requirements}")
    if views.close_up_requirements:
        view_lines.append(f"- close-up: {views.close_up_requirements}")
    if views.detail_focus:
        view_lines.append(f"- detail focus: {views.detail_focus}")

    parts = [
        "MIDAS Engine compile instruction.",
        f"Category: {contract.item.department}/{contract.item.category}/{contract.item.subcategory}.",
        f"Product role: {stylist_plan.product_role}.",
        f"Hero prominence: {stylist_plan.hero_prominence}.",
        "Locks (must not change):",
        *lock_lines,
        "Authorized variables:",
        *variable_lines,
        "Scene:",
        f"- setting: {scene.setting}",
        f"- light: {scene.light}",
        f"- camera: {scene.camera}",
        f"- presentation: {scene.presentation}",
        f"- frame: {scene.frame}",
        "Selected layout:",
        f"- board_id: {layout.board_id}",
        f"- focal_hierarchy: {layout.focal_hierarchy}",
        f"- palette: {layout.palette}",
        f"- spacing: {layout.spacing}",
        f"- surfaces: {layout.surfaces}",
        f"- lighting: {layout.lighting}",
        f"- circulation: {layout.circulation}",
        f"- arrangement_detail: {layout.arrangement_detail}",
        f"- functional_use: {layout.functional_use}",
        "Requested view and requirements:",
        *view_lines,
        "Supporting elements:",
        *(supporting or ["- none supplied"]),
        "Reference order and roles:",
        *reference_lines,
        "Acceptance constraints:",
        *(acceptance or ["- preserve protected identity and user-selected count"]),
        "Unknowns (do not fabricate):",
        *unknown_lines,
        (
            f"Output format: proportions={contract.outputs.image_proportions}; "
            f"resolution={contract.outputs.resolution}."
        ),
        "Compile only the approved decisions above. Do not invent product facts.",
    ]
    return "\n".join(parts)
