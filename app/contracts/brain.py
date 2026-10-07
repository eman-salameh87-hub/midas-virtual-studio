"""Brain plan contract.

Fields follow the canonical atlas Brain schema and Architecture A
responsibilities (route, modes, semantic grounding). This is a planning
artifact. It is not a Stylist board, Engine prompt, or model-selection record.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.contracts.job import PolicyMode, ProductRole

BrainStatus = Literal["ready", "hold"]
SceneMode = Literal["preserve_supplied_scene", "create_new_scene"]
RouteOperation = Literal[
    "extraction",
    "assembly",
    "scene_preservation",
    "selective_edit",
    "new_room",
    "alternate_view",
    "finishing",
    "clarification",
]
InvariantName = Literal["count", "identity", "source-supported construction"]
VariableName = Literal["room", "styling", "light", "framing", "authorised edits"]
GroundingRelation = Literal[
    "category",
    "function",
    "material",
    "provenance",
    "scene_role",
    "supporting_object",
]
GroundingBasis = Literal["observed", "published", "inferred", "decision"]


class BrainRoute(BaseModel):
    """Selected operation. Not a catalogue of per-SKU workflows."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: RouteOperation
    reason: str = Field(min_length=1)
    input_condition: str = Field(min_length=1)
    category: str = Field(min_length=1)
    product_role: ProductRole


class BrainScene(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: SceneMode


class BrainInvariant(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: InvariantName
    value: str = Field(min_length=1)
    source: str = Field(min_length=1)
    evidence_reference_id: str | None = None


class BrainVariable(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: VariableName
    value: str = Field(min_length=1)
    authorized: bool


class BrainRequiredOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    output: str = Field(min_length=1)
    acceptance_checks: list[str] = Field(min_length=1)


class BrainGrounding(BaseModel):
    """A grounded link. Inferred/decision values are not observed facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1)
    relation: GroundingRelation
    value: str = Field(min_length=1)
    basis: GroundingBasis
    evidence_reference_id: str | None = None

    @model_validator(mode="after")
    def observed_needs_evidence(self) -> "BrainGrounding":
        if self.basis in {"observed", "published"} and not self.evidence_reference_id:
            raise ValueError("observed and published grounding need an evidence reference")
        return self


class BrainUnknown(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class BrainPlan(BaseModel):
    """Persisted Brain planning artifact bound to one contract revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    contract_revision: int = Field(ge=1)
    observation_contract_id: str = Field(min_length=1)
    observation_revision: int = Field(ge=1)
    route: BrainRoute
    mode: PolicyMode
    scene: BrainScene
    invariants: list[BrainInvariant] = Field(min_length=1)
    variables: list[BrainVariable]
    required_outputs: list[BrainRequiredOutput]
    dependencies: list[str]
    capability_requirements: list[str]
    decision_reasons: list[str] = Field(min_length=1)
    grounding: list[BrainGrounding]
    unknowns: list[BrainUnknown]
    status: BrainStatus

    @model_validator(mode="after")
    def ready_plan_has_outputs(self) -> "BrainPlan":
        if self.status == "ready" and not self.required_outputs:
            raise ValueError("a ready Brain plan must name required outputs")
        if self.status == "hold" and self.route.operation != "clarification":
            raise ValueError("a held Brain plan must route to clarification")
        if self.observation_contract_id != self.contract_id:
            raise ValueError("Brain plan must bind the same contract as EyeObservation")
        if self.observation_revision != self.contract_revision:
            raise ValueError("Brain plan must bind the same revision as EyeObservation")
        names = [item.name for item in self.invariants]
        if "count" not in names:
            raise ValueError("Brain plan must keep count as an invariant")
        if "identity" not in names:
            raise ValueError("Brain plan must keep identity as an invariant")
        return self
