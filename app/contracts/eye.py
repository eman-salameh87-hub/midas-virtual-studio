"""Eye input and Eye observation.

This is the contract between a job revision's original references and an Eye
observation. It does not call a model and it does not contain a prompt.

Reference-role vocabularies are not merged:

- create-page: the six labels on the canonical Create page
- atlas-handoff: the six ids in the canonical atlas Eye handoff

Those lists do not match. A role is accepted only inside its own vocabulary.

Fact bases are the atlas Eye handoff list: observed, published, inferred.
Unknown and conflict are separate records. Architecture wording such as
"supplied specifications" and "derived measurements" is not aliased onto
those bases.

The Living Room prompt file is historical evidence. Its sofa report and its
instruction text are not this contract.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RoleVocabulary = Literal["create-page", "atlas-handoff"]
FactBasis = Literal["observed", "published", "inferred"]
ItemKind = Literal["item", "part", "set"]
CountStatus = Literal["observed", "unresolved"]
AmbiguityStatus = Literal["resolved", "unresolved"]
RegionClassification = Literal["physical piece", "inset"]
SignalReadingKind = Literal["instruction", "view", "variant", "packaging"]
MediaType = Literal["JPG", "PNG", "WebP", "PDF", "XLS", "XLSX", "CSV"]

_CREATE_PAGE_ROLES = {
    "Product / vendor reference",
    "Room / target space",
    "Inspiration / look",
    "Previous result",
    "Other views / pieces",
    "Specifications / Excel",
}
_ATLAS_ROLES = {
    "product_identity",
    "target_room",
    "specification",
    "catalogue_support",
    "inspiration",
    "previous_result",
}
_ROLES = {
    "create-page": _CREATE_PAGE_ROLES,
    "atlas-handoff": _ATLAS_ROLES,
}
_PREVIOUS_RESULT_ROLES = {"Previous result", "previous_result"}
_SPECIFICATION_ROLES = {"Specifications / Excel", "specification"}
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
_HIDDEN_GEOMETRY = (
    "hidden geometry",
    "unseen bed",
    "unseen side",
    "unseen view",
    "guessed side",
    "hidden base",
    "not fully visible",
)
_COMPOSITION = (
    "fibre",
    "fiber",
    "composition",
    "cotton percentage",
    "gsm",
    "exact material",
)
_UNSEEN_VIEW = ("unseen view", "guessed side", "unseen side")
_SPEC_SUBJECTS = {"sku", "dimension", "dimensions"}


def _sha256(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(
            "content_hash must be an explicit lowercase sha256 hex digest; "
            "the contract does not compute one"
        )
    return value


def _blank(values: list[str], field_name: str) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} cannot contain a blank entry")


class EyeSource(BaseModel):
    """One original or reference bound into the Eye input."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reference_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    media_type: MediaType
    hash_algorithm: Literal["sha256"]
    content_hash: str
    role_vocabulary: RoleVocabulary
    role: str = Field(min_length=1)

    @field_validator("content_hash")
    @classmethod
    def hash_is_sha256(cls, value: str) -> str:
        return _sha256(value)

    @model_validator(mode="after")
    def role_stays_in_its_vocabulary(self) -> "EyeSource":
        allowed = _ROLES[self.role_vocabulary]
        if self.role not in allowed:
            raise ValueError(
                f"{self.role!r} is not in the {self.role_vocabulary} reference-role vocabulary"
            )
        return self


class EyeInput(BaseModel):
    """Originals the Eye may read, bound to one job-contract revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    references: list[EyeSource] = Field(min_length=1)

    @model_validator(mode="after")
    def reference_ids_are_unique(self) -> "EyeInput":
        ids = [reference.reference_id for reference in self.references]
        if len(ids) != len(set(ids)):
            raise ValueError("reference_id values must be unique")
        return self


class CategoryCandidate(BaseModel):
    """A category hypothesis. It is not a client request and not a final label."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1)
    confidence_basis: str = Field(min_length=1)
    evidence_reference_id: str = Field(min_length=1)
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def hash_is_sha256(cls, value: str) -> str:
        return _sha256(value)


class ItemCount(BaseModel):
    """An observed count, or an explicit statement that the count is unresolved."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: CountStatus
    value: int | None

    @model_validator(mode="after")
    def status_matches_value(self) -> "ItemCount":
        if self.status == "observed":
            if self.value is None or self.value < 1:
                raise ValueError("an observed count needs an integer of at least 1")
        elif self.value is not None:
            raise ValueError("an unresolved count must not be given a number")
        return self


class PhysicalItem(BaseModel):
    """A recognized item, part, or set. Identity comes from visible content."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    item_kind: ItemKind
    count: ItemCount
    visible_features: list[str]
    identified_from: Literal["visible content", "filename", "collage"]
    evidence_reference_id: str = Field(min_length=1)
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def hash_is_sha256(cls, value: str) -> str:
        return _sha256(value)

    @model_validator(mode="after")
    def inventory_needs_visible_content(self) -> "PhysicalItem":
        _blank(self.visible_features, "visible_features")
        if self.identified_from != "visible content":
            raise ValueError(
                "a filename or collage is insufficient evidence of the physical inventory"
            )
        return self


class EyeFact(BaseModel):
    """One observed, published, or inferred statement."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1)
    value: str = Field(min_length=1)
    basis: FactBasis
    evidence_reference_id: str = Field(min_length=1)
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def hash_is_sha256(cls, value: str) -> str:
        return _sha256(value)


class EyeUnknown(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1)
    detail: str = Field(min_length=1)
    evidence_reference_id: str = Field(min_length=1)


class Ambiguity(BaseModel):
    """Competing hypotheses. Unresolved ambiguity has no chosen answer."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1)
    hypotheses: list[str] = Field(min_length=2)
    status: AmbiguityStatus
    resolution: str | None

    @model_validator(mode="after")
    def resolution_matches_status(self) -> "Ambiguity":
        _blank(self.hypotheses, "hypotheses")
        if self.status == "resolved":
            if self.resolution not in self.hypotheses:
                raise ValueError("a resolved ambiguity must name one of its hypotheses")
        elif self.resolution is not None:
            raise ValueError("an unresolved ambiguity must not choose a hypothesis")
        return self


class EyeConflict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1)
    claims: list[str] = Field(min_length=2)
    evidence_reference_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def claims_are_stated(self) -> "EyeConflict":
        _blank(self.claims, "claims")
        _blank(self.evidence_reference_ids, "evidence_reference_ids")
        return self


class ParsingLimitation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_reference_id: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class ObjectRelation(BaseModel):
    """A scene relation. A 2D relation does not certify 3D fit."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1)
    relation: str = Field(min_length=1)
    target: str = Field(min_length=1)
    basis: Literal["observed", "inferred"]
    evidence_reference_id: str = Field(min_length=1)
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def hash_is_sha256(cls, value: str) -> str:
        return _sha256(value)

    @model_validator(mode="after")
    def boxes_do_not_prove_fit(self) -> "ObjectRelation":
        text = f"{self.relation} {self.target}".casefold()
        if "3d fit" in text or "three-dimensional fit" in text:
            raise ValueError("2D evidence does not prove 3D fit")
        return self


class RegionDistinction(BaseModel):
    """Architecture distinction: an inset is not a physical piece."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    classification: RegionClassification
    evidence_reference_id: str = Field(min_length=1)
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def hash_is_sha256(cls, value: str) -> str:
        return _sha256(value)


class SignalReading(BaseModel):
    """Observed mark. A reading is the atlas role when evidence supports one.

    The atlas asks whether a mark is instruction, view, variant, or packaging.
    That is not a required label for every detected sign. Uncertain intent is
    reading=None. Competing roles belong on ambiguities, not a fifth kind.
    This list is not the inset/physical classification.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    mark: str = Field(min_length=1)
    reading: SignalReadingKind | None
    evidence_reference_id: str = Field(min_length=1)
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def hash_is_sha256(cls, value: str) -> str:
        return _sha256(value)


class ChangeLogEntry(BaseModel):
    """Temporal note. It requires more than one reference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    detail: str = Field(min_length=1)
    evidence_reference_ids: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def ids_are_stated(self) -> "ChangeLogEntry":
        _blank(self.evidence_reference_ids, "evidence_reference_ids")
        if len(set(self.evidence_reference_ids)) < 2:
            raise ValueError("a change log entry needs two distinct references")
        return self


class EyeObservation(BaseModel):
    """What the Eye records. Requests and preferences are not facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    category_candidates: list[CategoryCandidate]
    items: list[PhysicalItem]
    facts: list[EyeFact]
    unknowns: list[EyeUnknown]
    ambiguities: list[Ambiguity]
    conflicts: list[EyeConflict]
    parsing_limitations: list[ParsingLimitation]
    relations: list[ObjectRelation]
    regions: list[RegionDistinction]
    signals: list[SignalReading]
    shown_views: list[str]
    change_log: list[ChangeLogEntry]

    @model_validator(mode="after")
    def views_are_shown(self) -> "EyeObservation":
        _blank(self.shown_views, "shown_views")
        for view in self.shown_views:
            if _contains_any(view, _UNSEEN_VIEW):
                raise ValueError("an unseen view is not view coverage")
        return self


class EyeContract(BaseModel):
    """Eye input and the observation bound to that same revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    eye_input: EyeInput
    observation: EyeObservation

    @model_validator(mode="after")
    def observation_matches_input(self) -> "EyeContract":
        source = self.eye_input
        observation = self.observation
        if observation.contract_id != source.contract_id or observation.revision != source.revision:
            raise ValueError(
                "the observation must bind the same contract_id and revision as the Eye input"
            )
        by_id = {reference.reference_id: reference for reference in source.references}
        inset_names = {
            region.name.casefold()
            for region in observation.regions
            if region.classification == "inset"
        }
        for item in observation.items:
            reference = _require_reference(by_id, item.evidence_reference_id, item.content_hash)
            _reject_previous_result(reference, "a physical item")
            if item.name.casefold() in inset_names:
                raise ValueError("an inset is not an additional physical item")
        for candidate in observation.category_candidates:
            reference = _require_reference(
                by_id, candidate.evidence_reference_id, candidate.content_hash
            )
            _reject_previous_result(reference, "a category candidate")
        for fact in observation.facts:
            reference = _require_reference(by_id, fact.evidence_reference_id, fact.content_hash)
            _reject_previous_result(reference, "a product fact")
            _reject_unsupported_fact(fact, reference)
        for unknown in observation.unknowns:
            _require_known_id(by_id, unknown.evidence_reference_id)
        for conflict in observation.conflicts:
            for reference_id in conflict.evidence_reference_ids:
                _require_known_id(by_id, reference_id)
        for limitation in observation.parsing_limitations:
            _require_known_id(by_id, limitation.evidence_reference_id)
        for relation in observation.relations:
            reference = _require_reference(
                by_id, relation.evidence_reference_id, relation.content_hash
            )
            _reject_previous_result(reference, "an object relation")
        for region in observation.regions:
            reference = _require_reference(
                by_id, region.evidence_reference_id, region.content_hash
            )
            _reject_previous_result(reference, "a region distinction")
        for signal in observation.signals:
            reference = _require_reference(
                by_id, signal.evidence_reference_id, signal.content_hash
            )
            _reject_previous_result(reference, "a signal reading")
        for entry in observation.change_log:
            for reference_id in entry.evidence_reference_ids:
                _require_known_id(by_id, reference_id)
        return self


def _require_known_id(by_id: dict[str, EyeSource], reference_id: str) -> EyeSource:
    reference = by_id.get(reference_id)
    if reference is None:
        raise ValueError(f"unknown reference {reference_id!r}")
    return reference


def _require_reference(
    by_id: dict[str, EyeSource], reference_id: str, content_hash: str
) -> EyeSource:
    reference = _require_known_id(by_id, reference_id)
    if reference.content_hash != content_hash:
        raise ValueError(
            f"content_hash for {reference_id!r} does not match the Eye input"
        )
    return reference


def _reject_previous_result(reference: EyeSource, record_name: str) -> None:
    if reference.role in _PREVIOUS_RESULT_ROLES:
        raise ValueError(
            f"a previous result can guide composition; it cannot support {record_name}"
        )


def _reject_unsupported_fact(fact: EyeFact, reference: EyeSource) -> None:
    subject = fact.subject.casefold().strip()
    text = f"{fact.subject} {fact.value}".casefold()
    if subject in _REQUEST_SUBJECTS:
        raise ValueError(f"{fact.subject!r} is a requested preference, not an Eye fact")
    if _contains_any(text, _HIDDEN_GEOMETRY):
        raise ValueError("hidden or unseen geometry cannot be certified")
    if _contains_any(text, _UNSEEN_VIEW):
        raise ValueError("an unseen product view cannot be inferred or observed")
    composition = _contains_any(text, _COMPOSITION)
    specification = subject in _SPEC_SUBJECTS or subject.startswith("sku")
    supplied = fact.basis == "published" and reference.role in _SPECIFICATION_ROLES
    if composition and not supplied:
        raise ValueError(
            "visual appearance does not establish exact material composition"
        )
    if specification and not supplied:
        raise ValueError(
            "SKU and dimensions are not Eye facts unless published from a specification reference"
        )


def _contains_any(text: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in text for phrase in phrases)
