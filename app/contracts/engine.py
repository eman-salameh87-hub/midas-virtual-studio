"""Engine · compile contract.

Canonical Architecture A (framework.json / two-architectures.txt role 13)
names the saved compile artifact as: exact prompt, reference order/roles,
model/version, and output format. Those sources do not publish a field-level
JSON schema. This module is the minimum typed representation of that artifact
for the current backend.

Engine compiles already-approved Brain locks/variables and Stylist scene
direction into a provider-ready instruction. It does not invent creative
decisions, select models, call a generation API, or resolve unknowns.

This is not Engine · choose models, Operator execution, or image generation.
Living Room / Magnific / OpenRouter request fields are not part of this schema.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.contracts.brain import BrainInvariant, BrainVariable
from app.contracts.job import ImageProportions, OutputView, ProductRole, Resolution
from app.contracts.reference import ReferenceAsset
from app.contracts.stylist import SelectedLayout, StylistScene, StylistViewRequirements

EngineStatus = Literal["ready", "hold"]


def _reject_blank(values: list[str], field_name: str) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} cannot contain a blank entry")


class EngineUnknown(BaseModel):
    """Unresolved fact carried forward. Compilation must not assert it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class EngineOutputFormat(BaseModel):
    """Generation output shape already defined on the job contract.

    Canonical compile artifact: "output format". Pixel dimensions, MIME type,
    and provider SDK parameters are not specified here.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    image_proportions: ImageProportions
    resolution: Resolution


class EngineCompile(BaseModel):
    """Provider-neutral compile artifact bound to one job contract revision.

    Reference order is the list order of ``references``. The adapter must keep
    that sequence and the recorded roles. ``model_id`` is the caller-recorded
    identifier used by the current execution boundary; this contract does not
    rank or choose models.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    contract_revision: int = Field(ge=1)
    brain_contract_id: str = Field(min_length=1)
    brain_revision: int = Field(ge=1)
    stylist_contract_id: str = Field(min_length=1)
    stylist_revision: int = Field(ge=1)
    product_role: ProductRole
    references: list[ReferenceAsset] = Field(min_length=1)
    locks: list[BrainInvariant] = Field(min_length=1)
    variables: list[BrainVariable]
    scene: StylistScene
    selected_layout: SelectedLayout
    hero_prominence: str = Field(min_length=1)
    requested_view: OutputView
    view_requirements: StylistViewRequirements
    output_format: EngineOutputFormat
    exact_prompt: str
    model_id: str
    unknowns: list[EngineUnknown]
    status: EngineStatus
    hold_reasons: list[str]

    @model_validator(mode="after")
    def validate_compile_artifact(self) -> "EngineCompile":
        if self.brain_contract_id != self.contract_id:
            raise ValueError("Engine compile must bind the same contract as BrainPlan")
        if self.brain_revision != self.contract_revision:
            raise ValueError("Engine compile must bind the same revision as BrainPlan")
        if self.stylist_contract_id != self.contract_id:
            raise ValueError("Engine compile must bind the same contract as StylistPlan")
        if self.stylist_revision != self.contract_revision:
            raise ValueError("Engine compile must bind the same revision as StylistPlan")

        ids = [reference.reference_id for reference in self.references]
        if len(ids) != len(set(ids)):
            raise ValueError("reference_id values must be unique")

        _reject_blank(self.hold_reasons, "hold_reasons")

        lock_names = [item.name for item in self.locks]
        if "count" not in lock_names:
            raise ValueError("Engine compile must preserve count as a lock")
        if "identity" not in lock_names:
            raise ValueError("Engine compile must preserve identity as a lock")
        if "source-supported construction" not in lock_names:
            raise ValueError(
                "Engine compile must preserve source-supported construction as a lock"
            )

        if not self.model_id.strip():
            raise ValueError("model_id must be the caller-recorded model identifier")

        if self.status == "hold":
            if not self.hold_reasons:
                raise ValueError("a held Engine compile must specify at least one hold reason")
        elif self.status == "ready":
            if self.hold_reasons:
                raise ValueError("a ready Engine compile must not have hold reasons")
            if not self.exact_prompt.strip():
                raise ValueError("a ready Engine compile must include the exact prompt")

        return self
