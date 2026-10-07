"""Deterministic Brain provider for local tests.

It does not call a network and does not choose a model.
"""

from app.contracts.brain import (
    BrainGrounding,
    BrainInvariant,
    BrainPlan,
    BrainRequiredOutput,
    BrainRoute,
    BrainScene,
    BrainUnknown,
    BrainVariable,
    RouteOperation,
    SceneMode,
)
from app.contracts.job import Phase0JobContract
from app.providers.brain import BrainInput, BrainProviderRequest


class FakeBrainProvider:
    """In-memory provider. `requests` records exactly what the caller passed."""

    def __init__(self, violation: str | None = None) -> None:
        self.violation = violation
        self.requests: list[BrainProviderRequest] = []

    def reason(self, request: BrainProviderRequest) -> BrainPlan:
        self.requests.append(request)
        return plan_for(request.brain_input, violation=self.violation)


def plan_for(brain_input: BrainInput, *, violation: str | None = None) -> BrainPlan:
    """Build one BrainPlan bound to this BrainInput."""

    contract = brain_input.contract
    observation = brain_input.observation
    evidence_id = brain_input.evidence[0].reference_id if brain_input.evidence else None
    count_value = (
        str(contract.intent.selected_count.value)
        if contract.intent.selected_count.status == "declared"
        else "unresolved"
    )
    invariants = [
        BrainInvariant(
            name="count",
            value=count_value,
            source="contract.intent.selected_count",
            evidence_reference_id=None,
        ),
        BrainInvariant(
            name="identity",
            value="; ".join(contract.changes.protected_identity),
            source="contract.changes.protected_identity",
            evidence_reference_id=evidence_id,
        ),
        BrainInvariant(
            name="source-supported construction",
            value="visible product construction from Eye",
            source="eye.items",
            evidence_reference_id=evidence_id,
        ),
    ]
    variables = [
        BrainVariable(
            name="light",
            value=contract.preferences.lighting,
            authorized=True,
        ),
        BrainVariable(
            name="styling",
            value=contract.preferences.mood,
            authorized=True,
        ),
    ]
    if contract.changes.allowed_changes:
        variables.append(
            BrainVariable(
                name="authorised edits",
                value="; ".join(contract.changes.allowed_changes),
                authorized=True,
            )
        )
    if violation == "protected_as_variable":
        variables.append(
            BrainVariable(
                name="styling",
                value=contract.changes.protected_identity[0],
                authorized=True,
            )
        )
    if violation == "drop_unknowns":
        unknowns: list[BrainUnknown] = []
    else:
        unknowns = [
            BrainUnknown(subject=item.subject, detail=item.detail)
            for item in observation.unknowns
        ]
        for item in observation.ambiguities:
            if item.status == "unresolved":
                unknowns.append(
                    BrainUnknown(
                        subject=item.subject,
                        detail="unresolved Eye ambiguity",
                    )
                )
    required = [
        BrainRequiredOutput(
            output=member,
            acceptance_checks=[
                "preserve protected identity",
                "keep user-selected count",
            ],
        )
        for member in contract.outputs.package_members
    ]
    status = "hold" if violation == "hold" else "ready"
    operation: RouteOperation = "clarification" if status == "hold" else _route(contract)
    scene_mode: SceneMode = _scene_mode(contract)
    return BrainPlan(
        job_id=brain_input.job_id,
        contract_id=contract.contract_id,
        contract_revision=contract.revision,
        observation_contract_id=observation.contract_id,
        observation_revision=observation.revision,
        route=BrainRoute(
            operation=operation,
            reason=_route_reason(contract, operation),
            input_condition=contract.source_condition.input_condition,
            category=contract.item.category,
            product_role=contract.item.product_role,
        ),
        mode=contract.changes.policy_mode,
        scene=BrainScene(mode=scene_mode),
        invariants=invariants,
        variables=variables,
        required_outputs=[] if status == "hold" else required,
        dependencies=["persisted EyeObservation", "frozen Phase-0 job contract"],
        capability_requirements=["structured planning", "identity lock"],
        decision_reasons=[
            f"policy_mode is {contract.changes.policy_mode}",
            f"requested outputs are {', '.join(contract.outputs.package_members)}",
        ],
        grounding=[
            BrainGrounding(
                subject=contract.item.subcategory,
                relation="category",
                value=f"{contract.item.department}/{contract.item.category}/{contract.item.subcategory}",
                basis="decision",
                evidence_reference_id=None,
            ),
            BrainGrounding(
                subject="visible item",
                relation="provenance",
                value=evidence_id or "contract.references",
                basis="observed" if evidence_id else "decision",
                evidence_reference_id=evidence_id,
            ),
        ],
        unknowns=unknowns,
        status=status,
    )


def _route(contract: Phase0JobContract) -> RouteOperation:
    condition = contract.source_condition.input_condition
    outcomes = set(contract.intent.requested_outcomes)
    if condition == "scene":
        return "scene_preservation"
    if "White BK" in outcomes:
        return "extraction"
    if "Lifestyle" in outcomes or "New Composition" in outcomes:
        return "new_room"
    if "Close-up" in contract.outputs.views:
        return "alternate_view"
    return "selective_edit"


def _scene_mode(contract: Phase0JobContract) -> SceneMode:
    if contract.source_condition.input_condition == "scene":
        return "preserve_supplied_scene"
    return "create_new_scene"


def _route_reason(contract: Phase0JobContract, operation: RouteOperation) -> str:
    return (
        f"{operation} from {contract.source_condition.input_condition} "
        f"× {contract.item.category} × {contract.item.product_role} "
        f"× {', '.join(contract.outputs.package_members)}"
    )
