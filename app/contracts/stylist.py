"""Stylist plan contract.

Fields follow canonical Architecture A Stylist responsibilities:
1. Stylist · retrieve: genuine Midas companions with dated URLs, SKU/image hashes,
   dimensions, availability, and source references.
2. Stylist · compose: candidate boards with focal hierarchy, palette, spacing,
   surfaces, lighting, circulation; selected layout; rejected alternatives;
   functional rationale.
3. Stylist · reverse role: hero/support parameterization in the scene planner,
   hero prominence, complement list, close-up and wide-view requirements,
   ensuring accessories and furniture have credible functional use.

This is a planning and composition contract. It is provider-neutral and does not
contain model-specific instructions, scoring gimmicks, or runtime prompts.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.contracts.job import ImageProportions, ProductRole

StylistStatus = Literal["ready", "hold"]


def _sha256(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(
            "image_hash must be an explicit lowercase sha256 hex digest; "
            "the contract does not compute one"
        )
    return value


def _reject_blank(values: list[str], field_name: str) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} cannot contain a blank entry")


class MidasCompanion(BaseModel):
    """A genuine retrieved Midas companion product.

    Boundary: No generic object may be labelled Midas without its source reference.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    sku: str = Field(min_length=1)
    name: str = Field(min_length=1)
    category: str | None = None
    product_url: str = Field(min_length=1)
    image_hash: str
    dimensions: str | None = None
    availability: str | None = None
    function: str = Field(min_length=1)
    material: str | None = None
    color: str | None = None
    source_reference: str = Field(min_length=1)

    @field_validator("image_hash")
    @classmethod
    def hash_is_sha256(cls, value: str) -> str:
        return _sha256(value)


class GenericContextProp(BaseModel):
    """Generic supporting prop (e.g. books, plants, mug).

    Generic props must never be claimed as Midas brand items without a source reference.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    placement: str | None = None
    is_midas_product: Literal[False] = False


class CandidateBoard(BaseModel):
    """A structured scene proposal.

    Coherent alternative with focal hierarchy, palette, spacing, surfaces,
    lighting, and circulation.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    board_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    focal_hierarchy: str = Field(min_length=1)
    palette: str = Field(min_length=1)
    spacing: str = Field(min_length=1)
    surfaces: str = Field(min_length=1)
    lighting: str = Field(min_length=1)
    circulation: str = Field(min_length=1)
    companion_skus: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def companion_skus_not_blank(self) -> "CandidateBoard":
        _reject_blank(self.companion_skus, "companion_skus")
        return self


class SelectedLayout(BaseModel):
    """The chosen layout from candidate boards with functional placement details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    board_id: str = Field(min_length=1)
    focal_hierarchy: str = Field(min_length=1)
    palette: str = Field(min_length=1)
    spacing: str = Field(min_length=1)
    surfaces: str = Field(min_length=1)
    lighting: str = Field(min_length=1)
    circulation: str = Field(min_length=1)
    arrangement_detail: str = Field(min_length=1)
    functional_use: str = Field(min_length=1)


class RejectedAlternative(BaseModel):
    """A compared but rejected scene proposal with reason."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    board_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class StylistScene(BaseModel):
    """Setting, light, camera, and presentation for the scene."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    frame: ImageProportions
    setting: str = Field(min_length=1)
    light: str = Field(min_length=1)
    camera: str = Field(min_length=1)
    presentation: str = Field(min_length=1)


class StylistViewRequirements(BaseModel):
    """Requirements across wide views, close-ups, and details."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    close_up_requirements: str | None = None
    wide_view_requirements: str | None = None
    detail_focus: str | None = None


class StylistUnknown(BaseModel):
    """Unresolved styling uncertainty or missing reference data."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class StylistPlan(BaseModel):
    """Persisted Stylist planning artifact bound to one contract revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    contract_revision: int = Field(ge=1)
    brain_contract_id: str = Field(min_length=1)
    brain_revision: int = Field(ge=1)
    product_role: ProductRole
    hero_prominence: str = Field(min_length=1)
    scene: StylistScene
    candidate_boards: list[CandidateBoard] = Field(min_length=1)
    selected_layout: SelectedLayout
    rejected_alternatives: list[RejectedAlternative]
    functional_rationale: str = Field(min_length=1)
    midas_complements: list[MidasCompanion]
    supporting_props: list[GenericContextProp]
    view_requirements: StylistViewRequirements
    risks: list[str]
    unknowns: list[StylistUnknown]
    status: StylistStatus
    hold_reasons: list[str]

    @model_validator(mode="after")
    def validate_stylist_plan(self) -> "StylistPlan":
        if self.brain_contract_id != self.contract_id:
            raise ValueError("Stylist plan must bind the same contract as BrainPlan")
        if self.brain_revision != self.contract_revision:
            raise ValueError("Stylist plan must bind the same revision as BrainPlan")

        _reject_blank(self.risks, "risks")
        _reject_blank(self.hold_reasons, "hold_reasons")

        # Board consistency
        candidate_ids = {board.board_id for board in self.candidate_boards}
        if self.selected_layout.board_id not in candidate_ids:
            raise ValueError(
                f"Selected layout board_id {self.selected_layout.board_id!r} must match one of the candidate boards"
            )

        # Rejected alternatives must reference other candidate boards
        rejected_ids = {alt.board_id for alt in self.rejected_alternatives}
        if self.selected_layout.board_id in rejected_ids:
            raise ValueError("Selected layout cannot also be listed as a rejected alternative")

        for rej_id in rejected_ids:
            if rej_id not in candidate_ids:
                raise ValueError(f"Rejected alternative {rej_id!r} is not in candidate boards")

        if len(self.candidate_boards) > 1:
            expected_rejected = candidate_ids - {self.selected_layout.board_id}
            if not expected_rejected.issubset(rejected_ids):
                raise ValueError("All non-selected candidate boards must be listed with rejection reasons")

        # Complements SKU consistency
        known_skus = {comp.sku for comp in self.midas_complements}
        for board in self.candidate_boards:
            for sku in board.companion_skus:
                if sku not in known_skus:
                    raise ValueError(
                        f"Candidate board references companion SKU {sku!r} not found in midas_complements"
                    )

        # Status validation
        if self.status == "hold":
            if not self.hold_reasons:
                raise ValueError("A held Stylist plan must specify at least one hold reason")
        elif self.status == "ready":
            if self.hold_reasons:
                raise ValueError("A ready Stylist plan must not have hold reasons")

        return self
