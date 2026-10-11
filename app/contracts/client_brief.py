"""Local UIMidas ProposedJobContract wire models.

This is the Manual/one-by-one/batch/edit/single-item submit envelope emitted by
UIMidas/src/contract/buildJobContract.ts (contractVersion studio-jobs-v2-draft).
It is not a captured original Client Studio data-brief and is not Phase0JobContract.

Optional keys follow normalizeDraft: omitted when unset. Required keys that may
be null (category, role, evidence, productGroupId, sizeBytes, libraryKey) stay
present. Projects submit (PreparedProjectSubmission) is a different shape and
is not accepted here.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator

UIMIDAS_CONTRACT_VERSION = "studio-jobs-v2-draft"
UIMIDAS_ENDPOINT = "POST /api/studio/v2/jobs"

JobKind = Literal["new_project", "edit", "single_item"]
NewProjectMode = Literal["batch", "one_by_one"]
EditMode = Literal["choose_from_saving", "new_item"]
SingleItemRole = Literal["hero", "secondary"]
CategoryState = Literal["specified", "automatic_unknown"]
ReferenceType = Literal[
    "midas",
    "product_image",
    "other_view",
    "detail",
    "room_image",
    "previous_result",
    "inspiration",
    "specification_file",
]
ReferenceSource = Literal["local_file", "midas_library"]
ReferenceRole = Literal[
    "product",
    "additional_view",
    "detail",
    "room",
    "previous_result",
    "inspiration",
    "specification",
    "midas_reference",
]
ReferenceRelationship = Literal["same_product", "supporting_context"]
MediaKind = Literal["image", "file"]
OutputConcept = Literal[
    "white_bk",
    "lifestyle",
    "website",
    "new_composition",
    "variations",
    "create_with_this_item",
    "others",
]
OutputView = Literal[
    "category_template",
    "wide_view",
    "close_up",
    "wide_view_close_up",
    "front",
    "three_quarter",
    "side",
    "back",
    "top",
    "detail",
    "in_situ",
]
ImageProportion = Literal[
    "standard_for_category",
    "1:1",
    "4:5",
    "16:9",
    "3:4",
    "4:3",
    "9:16",
    "2:3",
]
ImageResolution = Literal[
    "standard_for_category",
    "2k",
    "4k",
    "web",
    "standard",
    "high",
    "print",
]
LightingPreference = Literal["soft_daylight", "golden_afternoon", "warm_evening"]
WallPreference = Literal[
    "white",
    "ivory",
    "sand",
    "greige",
    "taupe",
    "sage",
    "charcoal",
    "terracotta",
]
FloorPreference = Literal["light_oak", "dark_walnut", "limestone", "marble"]
InclusionChoice = Literal["suggest", "leave_out"]
MoodVibe = Literal[
    "automatic",
    "calm_natural",
    "warm_inviting",
    "refined_elegant",
    "bold_expressive",
]

_WIRE = ConfigDict(
    extra="forbid",
    frozen=True,
    populate_by_name=True,
    serialize_by_alias=True,
)


class WireModel(BaseModel):
    """Typed UIMidas JSON: extra keys forbidden; unset optional keys omitted."""

    model_config = _WIRE

    @model_serializer(mode="plain")
    def serialize_wire(self) -> dict[str, object]:
        return dump_omitting_optional_nones(self)


class DevelopmentPlaceholder(WireModel):
    status: Literal["development-placeholder"]
    value: None
    note: str = Field(min_length=1)


class NormalizedEvidence(WireModel):
    file_name: str = Field(alias="fileName", min_length=1)
    media_kind: MediaKind = Field(alias="mediaKind")
    size_bytes: int | None = Field(alias="sizeBytes")
    library_key: str | None = Field(alias="libraryKey")


class NormalizedReference(WireModel):
    id: str = Field(min_length=1)
    type: ReferenceType
    source: ReferenceSource
    role: ReferenceRole
    relationship: ReferenceRelationship
    product_group_id: str | None = Field(alias="productGroupId")
    evidence: NormalizedEvidence | None


class NormalizedPackageOutput(WireModel):
    concept: OutputConcept
    other_label: str | None = Field(default=None, alias="otherLabel")
    views: list[OutputView] | None = None
    proportion: ImageProportion | None = None
    resolution: ImageResolution | None = None
    variation_count: int | None = Field(default=None, alias="variationCount")


class NormalizedItemMetadata(WireModel):
    specific_items_combo: str | None = Field(default=None, alias="specificItemsCombo")
    additional_input_data: str | None = Field(default=None, alias="additionalInputData")
    sku: str | None = None
    dimensions: str | None = None
    colour: str | None = None
    fabric_material: str | None = Field(default=None, alias="fabricMaterial")
    item_count: int | None = Field(default=None, alias="itemCount")
    item_relationships: str | None = Field(default=None, alias="itemRelationships")
    other_pieces: str | None = Field(default=None, alias="otherPieces")


class NormalizedBriefItem(WireModel):
    id: str = Field(min_length=1)
    product_group_id: str = Field(alias="productGroupId", min_length=1)
    category_state: CategoryState = Field(alias="categoryState")
    department: str | None = None
    category: str | None = None
    subcategory: str | None = None
    references: list[NormalizedReference]
    requested_package: list[NormalizedPackageOutput] = Field(alias="requestedPackage")
    metadata: NormalizedItemMetadata | None = None


class NormalizedJob(WireModel):
    kind: JobKind | None = None
    new_project_mode: NewProjectMode | None = Field(default=None, alias="newProjectMode")
    edit_mode: EditMode | None = Field(default=None, alias="editMode")
    saved_item_id: str | None = Field(default=None, alias="savedItemId")
    single_item_role: SingleItemRole | None = Field(default=None, alias="singleItemRole")


class NormalizedPreferences(WireModel):
    use_workflow_defaults: Literal[True] | None = Field(
        default=None, alias="useWorkflowDefaults"
    )
    lighting: LightingPreference | None = None
    wall: WallPreference | None = None
    floor: FloorPreference | None = None


class NormalizedSuggestions(WireModel):
    plants: InclusionChoice | None = None
    human: InclusionChoice | None = None
    mood: MoodVibe | None = None


class NormalizedNotes(WireModel):
    description_metadata_preference: str | None = Field(
        default=None, alias="descriptionMetadataPreference"
    )
    previous_generation: str | None = Field(default=None, alias="previousGeneration")
    custom_prompting: str | None = Field(default=None, alias="customPrompting")
    fidelity: str | None = None
    styling: str | None = None
    cluttering: str | None = None
    description_checkpoint: str | None = Field(
        default=None, alias="descriptionCheckpoint"
    )
    semantic_grounding: str | None = Field(default=None, alias="semanticGrounding")


class NormalizedClientBrief(WireModel):
    job: NormalizedJob
    items: list[NormalizedBriefItem]
    preferences: NormalizedPreferences | None = None
    suggestions: NormalizedSuggestions | None = None
    notes: NormalizedNotes | None = None


class ProposedPackage(WireModel):
    item_id: str = Field(alias="itemId", min_length=1)
    product_group_id: str = Field(alias="productGroupId", min_length=1)
    outputs: list[NormalizedPackageOutput]


class ProposedJobContract(WireModel):
    """UIMidas Manual submit envelope. Discriminator: contractVersion."""

    endpoint: Literal["POST /api/studio/v2/jobs"]
    contract_version: Literal["studio-jobs-v2-draft"] = Field(alias="contractVersion")
    idempotency_key: str = Field(alias="idempotencyKey", min_length=1)
    owner_identity: DevelopmentPlaceholder = Field(alias="ownerIdentity")
    file_ids: DevelopmentPlaceholder = Field(alias="fileIds")
    limits: DevelopmentPlaceholder
    category: str | None
    role: SingleItemRole | None
    package: list[ProposedPackage]
    brief: NormalizedClientBrief

    @model_validator(mode="after")
    def version_is_the_uimidas_discriminator(self) -> "ProposedJobContract":
        if self.contract_version != UIMIDAS_CONTRACT_VERSION:
            raise ValueError("contractVersion must be studio-jobs-v2-draft")
        if self.endpoint != UIMIDAS_ENDPOINT:
            raise ValueError("endpoint must be POST /api/studio/v2/jobs")
        return self


class ClientBriefRecord(BaseModel):
    """Frozen persistence envelope.

    brief_id: immutable store key for one persisted revision. A new persist
    always gets a new brief_id. The on-disk file is not overwritten.
    contract_id: Architecture A identity, supplied by the persist caller
    (not by UIMidas). Shared across revisions of the same brief.
    revision: Architecture A revision supplied by the persist caller.
    Uniqueness of (contract_id, revision) across brief_ids is an unresolved
    identity policy and is not enforced here.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    brief_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    client_brief: ProposedJobContract
    brief_hash: str | None = None

    @model_validator(mode="after")
    def assign_brief_hash(self) -> "ClientBriefRecord":
        identity = _brief_hash_for(self)
        supplied = self.brief_hash
        if supplied is not None and supplied != identity:
            raise ValueError("brief_hash does not match the submitted client_brief")
        object.__setattr__(self, "brief_hash", identity)
        return self

    def revise(self, **updates: object) -> "ClientBriefRecord":
        """Return a new revision. The current record object stays as it is.

        A new brief_id is assigned so persisting the result cannot overwrite
        the previous revision's file.
        """

        forbidden = {"contract_id", "revision", "brief_id"} & set(updates)
        if forbidden:
            raise ValueError(
                "revise() keeps contract_id, assigns a new brief_id, and assigns the next revision"
            )
        data = self.model_dump(mode="python")
        data.pop("brief_hash", None)
        for key, value in updates.items():
            if isinstance(value, BaseModel):
                data[key] = value.model_dump(mode="python")
            else:
                data[key] = value
        data["brief_id"] = str(uuid4())
        data["revision"] = self.revision + 1
        return ClientBriefRecord.model_validate(data)


def dump_omitting_optional_nones(model: BaseModel) -> dict[str, object]:
    """JSON dict using wire aliases. Optional None keys are omitted; required nulls stay."""

    payload: dict[str, object] = {}
    for name, field in type(model).model_fields.items():
        value = getattr(model, name)
        alias = field.serialization_alias or field.alias or name
        if value is None:
            if field.is_required():
                payload[alias] = None
            continue
        if isinstance(value, BaseModel):
            payload[alias] = dump_omitting_optional_nones(value)
        elif isinstance(value, list):
            payload[alias] = [
                dump_omitting_optional_nones(item) if isinstance(item, BaseModel) else item
                for item in value
            ]
        else:
            payload[alias] = value
    return payload


def client_brief_canonical_dict(contract: ProposedJobContract) -> dict[str, object]:
    return dump_omitting_optional_nones(contract)


PROJECTS_NOT_SUPPORTED = "PROJECTS_NOT_SUPPORTED"
UNSUPPORTED_BRIEF_SCHEMA = "UNSUPPORTED_BRIEF_SCHEMA"


def classify_unsupported_brief_payload(payload: object) -> str | None:
    """Return an explicit error code for Projects or obsolete schema envelopes.

    Does not inspect or return payload values.
    """

    if not isinstance(payload, dict):
        return UNSUPPORTED_BRIEF_SCHEMA
    version = payload.get("contractVersion")
    endpoint = payload.get("endpoint")
    if version == UIMIDAS_CONTRACT_VERSION and endpoint == UIMIDAS_ENDPOINT:
        return None
    if version is not None or endpoint is not None:
        return UNSUPPORTED_BRIEF_SCHEMA
    if "categoryState" in payload and "outputs" in payload and "productGroupId" in payload:
        return PROJECTS_NOT_SUPPORTED
    return UNSUPPORTED_BRIEF_SCHEMA


def _brief_hash_for(record: "ClientBriefRecord") -> str:
    """Digest of Architecture A identity plus the UIMidas submit envelope.

    revision is not hashed, matching Phase0JobContract request_hash material.
    brief_id is a store key and is not hashed.
    """

    material = {
        "owner_id": record.owner_id,
        "contract_id": record.contract_id,
        "client_brief": client_brief_canonical_dict(record.client_brief),
    }
    encoded = json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
