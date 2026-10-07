"""Phase-0 immutable job contract.

Architecture A saves a versioned brief: requested and excluded pieces, allowed
changes, and an output package. Category, product role, and input condition
stay separate. A later change is a new revision of the same contract id.
The previous revision is not mutated.

Preview placeholders such as "Automatic from references", "Workflow default",
"Category template", and "Standard for category" are rejected. They are unset
states in the client snapshot, not resolved values.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.contracts.observation import Conflict, EvidenceStatement, Unknown
from app.contracts.reference import ReferenceAsset

Mode = Literal["Manual", "Projects"]
JobType = Literal["New Project", "Edit", "Single item"]
ProductRole = Literal["hero", "supporting"]
PolicyMode = Literal["fidelity-locked", "creative-room"]
InputCondition = Literal[
    "clean pack shot",
    "scene",
    "partial object",
    "annotated multi-view sheet",
    "low resolution",
    "technical document",
    "spreadsheet",
    "mixed batch",
]
RequestedOutcome = Literal[
    "White BK",
    "Lifestyle",
    "Website",
    "New Composition",
    "Variations",
    "Create with this item",
    "Others",
]
OutputView = Literal["Wide view", "Close-up", "Wide view + close-up"]
ImageProportions = Literal["Square · 1:1", "Portrait · 4:5", "Landscape · 16:9"]
Resolution = Literal["2K", "4K"]
PackageMember = Literal[
    "catalogue",
    "lifestyle",
    "alternative view",
    "detail",
    "upscale",
]
Lighting = Literal["Soft daylight", "Golden afternoon", "Warm evening"]
WallPaint = Literal[
    "White",
    "Ivory",
    "Sand",
    "Greige",
    "Taupe",
    "Sage",
    "Charcoal",
    "Terracotta",
]
FloorFinish = Literal["Light oak", "Dark walnut", "Limestone", "Marble"]
Mood = Literal[
    "Automatic",
    "Calm & natural",
    "Warm & inviting",
    "Refined & elegant",
    "Bold & expressive",
]
CountStatus = Literal["declared", "unresolved"]

_JOB_OPTIONS: dict[str, set[str]] = {
    "New Project": {"Batch", "One by one (same department)"},
    "Edit": {"Choose from saving", "New item"},
    "Single item": {"Hero", "Secondary"},
}

_UNRESOLVED_TEXT = {
    "Automatic from references",
    "Workflow default",
    "Category template",
    "Standard for category",
    "Not requested",
}

_REQUEST_SUBJECTS = {
    "lighting",
    "wall",
    "wall paint",
    "wall colour",
    "wall color",
    "floor",
    "floor finish",
    "mood",
    "mood / vibes",
    "plants",
    "human",
    "include plants",
    "include human",
}


class SelectedCount(BaseModel):
    """The client's selected count, or an explicit unresolved count."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: CountStatus
    value: int | None

    @model_validator(mode="after")
    def status_matches_value(self) -> "SelectedCount":
        if self.status == "declared":
            if self.value is None or self.value < 1:
                raise ValueError("a declared count needs an integer of at least 1")
        elif self.value is not None:
            raise ValueError("an unresolved count must not be given a number")
        return self


class ClientIntent(BaseModel):
    """What the client asked for. This is not an observed product fact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    mode: Mode
    job_type: JobType
    job_option: str = Field(min_length=1)
    requested_outcomes: list[RequestedOutcome] = Field(min_length=1)
    other_outcome: str | None = None
    requested_pieces: list[str]
    excluded_pieces: list[str]
    selected_count: SelectedCount

    @field_validator("other_outcome", mode="before")
    @classmethod
    def blank_other_outcome_is_absent(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def intent_is_resolved(self) -> "ClientIntent":
        if self.mode == "Projects":
            raise ValueError(
                "Projects mode is unresolved: its four starting sources are not named"
            )
        allowed = _JOB_OPTIONS[self.job_type]
        if self.job_option not in allowed:
            raise ValueError(
                f"job_option {self.job_option!r} is not defined for {self.job_type}"
            )
        if "Others" in self.requested_outcomes:
            if self.other_outcome is None or not self.other_outcome.strip():
                raise ValueError("Others requires an explicit other_outcome")
        elif self.other_outcome is not None:
            raise ValueError("other_outcome is only used when Others is requested")
        _reject_blank(self.requested_pieces, "requested_pieces")
        _reject_blank(self.excluded_pieces, "excluded_pieces")
        return self


class ItemClassification(BaseModel):
    """Department, category, subcategory, and product role stay separate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    department: str = Field(min_length=1)
    category: str = Field(min_length=1)
    subcategory: str = Field(min_length=1)
    product_role: ProductRole

    @model_validator(mode="after")
    def classification_is_stated(self) -> "ItemClassification":
        for name in ("department", "category", "subcategory"):
            value = getattr(self, name)
            if value.strip() in _UNRESOLVED_TEXT:
                raise ValueError(f"{name} uses an unresolved placeholder: {value}")
        return self


class SourceCondition(BaseModel):
    """Input condition from the architecture specification.

    Atlas labels such as single, selection, sheet, and multi are not accepted
    as aliases. That mapping is unresolved.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    input_condition: InputCondition


class OutputPackage(BaseModel):
    """Requested views and package members. One does not fill in the other."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    views: list[OutputView] = Field(min_length=1)
    image_proportions: ImageProportions
    resolution: Resolution
    package_members: list[PackageMember] = Field(min_length=1)


class ChangeBounds(BaseModel):
    """Allowed changes and protected identity. Nothing here is inferred."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_mode: PolicyMode
    allowed_changes: list[str]
    protected_identity: list[str] = Field(min_length=1)
    room_locks: list[str]
    creative_variables: list[str]

    @model_validator(mode="after")
    def changes_are_explicit(self) -> "ChangeBounds":
        _reject_blank(self.allowed_changes, "allowed_changes")
        _reject_blank(self.protected_identity, "protected_identity")
        _reject_blank(self.room_locks, "room_locks")
        _reject_blank(self.creative_variables, "creative_variables")
        return self


class Preferences(BaseModel):
    """Client styling requests evidenced on the Create page.

    These are requests. They are not observed properties of the product.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    lighting: Lighting
    wall: WallPaint
    floor: FloorFinish
    plants: bool
    human: bool
    mood: Mood


class Phase0JobContract(BaseModel):
    """Immutable Phase-0 job contract. Revision identity is explicit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    owner_id: str = Field(min_length=1)
    intent: ClientIntent
    item: ItemClassification
    source_condition: SourceCondition
    references: list[ReferenceAsset] = Field(min_length=1)
    outputs: OutputPackage
    changes: ChangeBounds
    preferences: Preferences
    statements: list[EvidenceStatement]
    unknowns: list[Unknown]
    conflicts: list[Conflict]

    @model_validator(mode="after")
    def references_and_statements_agree(self) -> "Phase0JobContract":
        ids = [reference.reference_id for reference in self.references]
        if len(ids) != len(set(ids)):
            raise ValueError("reference_id values must be unique")
        by_id = {reference.reference_id: reference for reference in self.references}
        for statement in self.statements:
            subject = statement.subject.casefold().strip()
            if subject in _REQUEST_SUBJECTS:
                raise ValueError(
                    f"{statement.subject!r} is a requested preference, not an evidence statement"
                )
            reference = by_id.get(statement.evidence_reference_id)
            if reference is None:
                raise ValueError(
                    f"statement cites unknown reference {statement.evidence_reference_id!r}"
                )
            if reference.role == "Previous result":
                raise ValueError(
                    "a previous result can guide composition; it cannot support a product statement"
                )
        return self

    def revise(self, **updates: object) -> "Phase0JobContract":
        """Return a new revision. The current contract object stays as it is."""

        forbidden = {"contract_id", "revision"} & set(updates)
        if forbidden:
            raise ValueError(
                "revise() keeps contract_id and assigns the next revision"
            )
        data = self.model_dump(mode="python")
        for key, value in updates.items():
            if isinstance(value, BaseModel):
                data[key] = value.model_dump(mode="python")
            else:
                data[key] = value
        data["revision"] = self.revision + 1
        return Phase0JobContract.model_validate(data)


def _reject_blank(values: list[str], field_name: str) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} cannot contain a blank entry")
