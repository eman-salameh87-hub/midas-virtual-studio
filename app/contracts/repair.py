"""Critique · repair contract.

Canonical role 17 identifies the smallest safe correction, preserves
correct features, and requires a re-review. Architecture A uses a bounded
controller: local edit, fresh render from originals, or hold. Maximum two
image repairs. A third repair cannot be represented.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.contracts.critique import CritiqueDimension
from app.contracts.generation import GenerationOperation, GenerationReceipt

REPAIR_LIMIT: Literal[2] = 2
RepairAction = Literal["local_edit", "fresh_render", "hold"]
RepairStatus = Literal["planned", "claimed", "completed", "hold", "failed"]
RepairExecutionStatus = Literal["completed", "hold", "failed"]
PreservationStatus = Literal[
    "unrecorded",
    "pending",
    "preserved",
    "not_claimed",
    "unsupported",
    "failed",
]

LOCK_PRESERVE_DIMENSIONS: frozenset[CritiqueDimension] = frozenset(
    {"inventory", "identity", "geometry"}
)


def _reject_blank(values: list[str], field_name: str) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} cannot contain a blank entry")


class RepairLineage(BaseModel):
    """Version identity for one repair. Previous generation artifacts stay intact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_generation_output_id: str = Field(min_length=1)
    source_generation_operation_key: str = Field(min_length=1)
    source_critique_generation_output_id: str = Field(min_length=1)
    original_reference_id: str = Field(min_length=1)
    version_from: int = Field(ge=1)
    version_to: int | None = Field(default=None, ge=2)
    result_generation_output_id: str | None = None
    result_generation_operation_key: str | None = None

    @model_validator(mode="after")
    def lineage_is_forward(self) -> "RepairLineage":
        if self.version_to is not None and self.version_to <= self.version_from:
            raise ValueError("repair lineage version_to must be greater than version_from")
        if self.result_generation_output_id == self.source_generation_output_id:
            raise ValueError("a repair must produce a new generation output id")
        return self


class RepairPlan(BaseModel):
    """Bounded repair artifact. repair_count cannot exceed two."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    contract_revision: int = Field(ge=1)
    critique_generation_output_id: str = Field(min_length=1)
    critique_generation_operation_key: str = Field(min_length=1)
    source_generation_output_id: str = Field(min_length=1)
    source_generation_operation_key: str = Field(min_length=1)
    original_reference_id: str = Field(min_length=1)
    repair_count: int = Field(ge=0, le=REPAIR_LIMIT)
    repair_limit: Literal[2] = REPAIR_LIMIT
    target_regions: list[str]
    repair_instructions: list[str]
    preserve_list: list[str]
    previous_defects: list[str]
    required_resolution_checks: list[str]
    action: RepairAction
    model_id: str = Field(min_length=1)
    status: RepairStatus
    hold_reasons: list[str]
    lineage: RepairLineage
    operation: GenerationOperation | None = None
    receipt: GenerationReceipt | None = None
    scene_base_reference: str | None = None
    product_authority_reference: str | None = None
    protected_scene_attributes: list[str] = Field(default_factory=list)
    targeted_attributes: list[str] = Field(default_factory=list)
    preservation_status: PreservationStatus = "unrecorded"
    preservation_result: str = ""

    @model_validator(mode="after")
    def repair_is_bounded(self) -> "RepairPlan":
        _reject_blank(self.target_regions, "target_regions")
        _reject_blank(self.repair_instructions, "repair_instructions")
        _reject_blank(self.preserve_list, "preserve_list")
        _reject_blank(self.previous_defects, "previous_defects")
        _reject_blank(self.required_resolution_checks, "required_resolution_checks")
        _reject_blank(self.hold_reasons, "hold_reasons")
        if self.repair_count > self.repair_limit:
            raise ValueError("repair_count cannot exceed repair_limit")
        if self.repair_limit != 2:
            raise ValueError("repair_limit is fixed at two")
        if self.repair_count > 2:
            raise ValueError("Repair #3 is not allowed")
        if self.action == "hold":
            if not self.hold_reasons:
                raise ValueError("a held repair must specify at least one hold reason")
            if self.receipt is not None and self.receipt.status == "completed":
                raise ValueError("a held repair cannot claim a completed generation")
        else:
            if self.repair_count < 1:
                raise ValueError("a dispatched repair must have repair_count 1 or 2")
            if not self.repair_instructions:
                raise ValueError("a dispatched repair must name repair instructions")
            if not self.target_regions:
                raise ValueError("a dispatched repair must name target regions")
        if self.lineage.source_generation_output_id != self.source_generation_output_id:
            raise ValueError("lineage source output must match the repaired generation")
        if self.lineage.original_reference_id != self.original_reference_id:
            raise ValueError("lineage must preserve the original identity reference")
        if self.action != "hold" and self.status == "completed":
            if self.receipt is None or self.receipt.output is None:
                raise ValueError("a completed repair must include a generation output")
            if self.lineage.result_generation_output_id is None:
                raise ValueError("a completed repair must record the new output id")
        _reject_blank(self.protected_scene_attributes, "protected_scene_attributes")
        _reject_blank(self.targeted_attributes, "targeted_attributes")
        if self.preservation_status == "preserved":
            if self.action != "local_edit":
                raise ValueError("only a local_edit can record scene preservation")
            if not self.scene_base_reference or not self.product_authority_reference:
                raise ValueError(
                    "preserved repair must record scene base and product authority"
                )
            if not self.preservation_result.strip():
                raise ValueError("preserved repair must record a preservation result")
        if self.preservation_status == "unsupported" and self.status == "completed":
            raise ValueError("unsupported local edit cannot be recorded as completed")
        return self
