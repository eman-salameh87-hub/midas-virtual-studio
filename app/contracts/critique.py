"""Critique · assess contract.

Canonical role 16 inspects originals and outputs for inventory, identity,
geometry, details, appearance, placement, lighting, and composition.
This is a structured review of one completed generation. It does not repair
or release. Aesthetic quality cannot override identity, count, or
source-supported construction.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CritiqueStatus = Literal["ready", "hold"]
CritiqueOverallResult = Literal["pass", "repair_required", "hold"]
CritiqueDimension = Literal[
    "inventory",
    "identity",
    "geometry",
    "details",
    "appearance",
    "placement",
    "lighting",
    "composition",
]
CritiqueSeverity = Literal["info", "low", "medium", "high", "critical"]
CritiqueFindingResult = Literal["pass", "fail", "uncertain"]

REQUIRED_DIMENSIONS: tuple[CritiqueDimension, ...] = (
    "inventory",
    "identity",
    "geometry",
    "details",
    "appearance",
    "placement",
    "lighting",
    "composition",
)
LOCK_DIMENSIONS: frozenset[CritiqueDimension] = frozenset(
    {"inventory", "identity", "geometry"}
)


def _reject_blank(values: list[str], field_name: str) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} cannot contain a blank entry")


class CritiqueFinding(BaseModel):
    """One dimension finding. Repair is not executed from this object."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: CritiqueDimension
    severity: CritiqueSeverity
    result: CritiqueFindingResult
    observation: str = Field(min_length=1)
    expected: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    repair_instruction: str | None = None

    @model_validator(mode="after")
    def finding_is_explicit(self) -> "CritiqueFinding":
        _reject_blank(self.evidence, "evidence")
        if self.repair_instruction is not None and not self.repair_instruction.strip():
            raise ValueError("repair_instruction cannot be blank")
        if self.result == "fail" and self.severity == "info":
            raise ValueError("a failed finding cannot have info severity")
        if self.result == "pass" and self.severity == "critical":
            raise ValueError("a passing finding cannot be critical")
        return self


class CritiqueUnknown(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class CritiqueCompliance(BaseModel):
    """One non-fidelity review section. Product locks stay on CritiqueFinding."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    section: Literal["styling", "plan", "view", "scene"]
    result: CritiqueFindingResult
    observation: str = Field(min_length=1)
    expected: str = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_is_explicit(self) -> "CritiqueCompliance":
        _reject_blank(self.evidence, "evidence")
        return self


class AttributeDrift(BaseModel):
    """Difference between a planned attribute and what the image shows.

    planned is copied from the existing plan. This record does not rewrite it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    attribute: str = Field(min_length=1)
    planned: str = Field(min_length=1)
    observed: str = Field(min_length=1)
    result: Literal["drift", "match", "unknown"]
    evidence: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_is_explicit(self) -> "AttributeDrift":
        _reject_blank(self.evidence, "evidence")
        return self


class CritiqueAssessment(BaseModel):
    """Persisted Critique · assess artifact bound to one completed generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    contract_revision: int = Field(ge=1)
    engine_contract_id: str = Field(min_length=1)
    engine_revision: int = Field(ge=1)
    generation_operation_key: str = Field(min_length=1)
    generation_output_id: str = Field(min_length=1)
    status: CritiqueStatus
    overall_result: CritiqueOverallResult
    findings: list[CritiqueFinding] = Field(min_length=1)
    unknowns: list[CritiqueUnknown]
    summary: str = Field(min_length=1)
    product_fidelity: list[str] = Field(default_factory=list)
    styling_compliance: list[CritiqueCompliance] = Field(default_factory=list)
    plan_compliance: list[CritiqueCompliance] = Field(default_factory=list)
    view_compliance: list[CritiqueCompliance] = Field(default_factory=list)
    scene_compliance: list[CritiqueCompliance] = Field(default_factory=list)
    drift: list[AttributeDrift] = Field(default_factory=list)

    @model_validator(mode="after")
    def assessment_is_consistent(self) -> "CritiqueAssessment":
        if self.engine_contract_id != self.contract_id:
            raise ValueError("Critique must bind the same contract as EngineCompile")
        if self.engine_revision != self.contract_revision:
            raise ValueError("Critique must bind the same revision as EngineCompile")

        if self.overall_result == "hold" and self.status != "hold":
            raise ValueError("a hold overall_result requires status hold")
        if self.status == "hold" and self.overall_result != "hold":
            raise ValueError("a held critique must have overall_result hold")
        if self.overall_result == "pass" and self.status != "ready":
            raise ValueError("a passing critique must be ready")
        if self.overall_result == "repair_required" and self.status != "ready":
            raise ValueError("repair_required requires a ready critique status")

        if self.status == "ready":
            present = {item.dimension for item in self.findings}
            missing = [name for name in REQUIRED_DIMENSIONS if name not in present]
            if missing:
                raise ValueError(
                    "a ready critique must include findings for "
                    + ", ".join(missing)
                )

        lock_failures = [
            item
            for item in self.findings
            if item.dimension in LOCK_DIMENSIONS and item.result == "fail"
        ]
        if self.overall_result == "pass" and lock_failures:
            raise ValueError(
                "overall pass cannot override inventory, identity, or geometry failure"
            )
        lock_uncertain = [
            item
            for item in self.findings
            if item.dimension in LOCK_DIMENSIONS and item.result == "uncertain"
        ]
        if self.overall_result == "pass" and lock_uncertain:
            raise ValueError(
                "overall pass cannot ignore uncertain inventory, identity, or geometry"
            )
        if self.overall_result == "pass" and any(item.result == "drift" for item in self.drift):
            raise ValueError("overall pass cannot ignore recorded drift")
        compliance_failures = [
            item
            for item in (
                *self.styling_compliance,
                *self.plan_compliance,
                *self.view_compliance,
                *self.scene_compliance,
            )
            if item.result == "fail"
        ]
        if self.overall_result == "pass" and compliance_failures:
            raise ValueError("overall pass cannot ignore styling, plan, view, or scene failure")
        fidelity = [item.dimension for item in self.findings if item.dimension in REQUIRED_DIMENSIONS]
        if not self.product_fidelity:
            object.__setattr__(self, "product_fidelity", fidelity)
        return self
