"""Map a saved UIMidas studio-jobs-v2-draft brief to Phase-0 intake.

Every frontend enum is classified: mapped when the Phase-0 contract already
has the same meaning, unresolved when the UI value is a placeholder, or
unsupported when the UI value is real but Phase-0 cannot represent it.
Unrepresentable fields are reported; they are not dropped into a job.
The saved brief is never rewritten.

source_condition, change bounds, and package_members are not on the UIMidas
brief. product_role is on the brief only for single_item (role / singleItemRole).
"""

from __future__ import annotations

from typing import Any, get_args

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.client_brief import (
    EditMode,
    FloorPreference,
    ImageProportion,
    ImageResolution,
    JobKind,
    LightingPreference,
    MoodVibe,
    NewProjectMode,
    NormalizedBriefItem,
    NormalizedNotes,
    NormalizedPackageOutput,
    NormalizedReference,
    OutputConcept,
    OutputView,
    ProposedJobContract,
    ReferenceType,
    SingleItemRole,
    WallPreference,
)
from app.contracts.job import (
    ChangeBounds,
    PackageMember,
    Preferences,
    ProductRole,
    SourceCondition,
    _UNRESOLVED_TEXT,
)
from app.contracts.uimidas_execution import (
    catalogue_room_fill,
    derive_change_bounds,
    derive_package_members,
    derive_product_role,
    derive_source_condition,
    inclusion_from_brief,
    metadata_used_as_identity,
    outcomes_from_contract,
    room_is_styled,
)

BRIEF_MAPPING_UNRESOLVED = "BRIEF_MAPPING_UNRESOLVED"
UNSUPPORTED_SLICE = "UNSUPPORTED_SLICE"
UNSUPPORTED_VIEW = "UNSUPPORTED_VIEW"
UNSUPPORTED_PROPORTION = "UNSUPPORTED_PROPORTION"
UNSUPPORTED_RESOLUTION = "UNSUPPORTED_RESOLUTION"
UNSUPPORTED_REFERENCE = "UNSUPPORTED_REFERENCE"
UNREPRESENTABLE_FIELD = "UNREPRESENTABLE_FIELD"
UNRESOLVED_SOURCE_CONDITION = "UNRESOLVED_SOURCE_CONDITION"
UNRESOLVED_CHANGE_BOUNDS = "UNRESOLVED_CHANGE_BOUNDS"
UNRESOLVED_PACKAGE_MEMBERS = "UNRESOLVED_PACKAGE_MEMBERS"
UNRESOLVED_PRODUCT_ROLE = "UNRESOLVED_PRODUCT_ROLE"
UNRESOLVED_CATEGORY = "UNRESOLVED_CATEGORY"
UNRESOLVED_OUTPUT = "UNRESOLVED_OUTPUT"
UNRESOLVED_PREFERENCES = "UNRESOLVED_PREFERENCES"
UNRESOLVED_REFERENCE = "UNRESOLVED_REFERENCE"
UNRESOLVED_JOB = "UNRESOLVED_JOB"
MISSING_REFERENCE_BYTES = "MISSING_REFERENCE_BYTES"

_JOB_TYPE = {
    "new_project": "New Project",
    "edit": "Edit",
    "single_item": "Single item",
}
_JOB_OPTION = {
    ("new_project", "batch"): "Batch",
    ("new_project", "one_by_one"): "One by one (same department)",
    ("edit", "choose_from_saving"): "Choose from saving",
    ("edit", "new_item"): "New item",
    ("single_item", "hero"): "Hero",
    ("single_item", "secondary"): "Secondary",
}
_OUTCOMES = {
    "white_bk": "White BK",
    "lifestyle": "Lifestyle",
    "website": "Website",
    "new_composition": "New Composition",
    "variations": "Variations",
    "create_with_this_item": "Create with this item",
    "others": "Others",
}
# Phase-0 OutputView literals whose labels match UIMidas options.ts.
_VIEWS_MAP = {
    "wide_view": "Wide view",
    "close_up": "Close-up",
    "wide_view_close_up": "Wide view + close-up",
    "front": "Front",
    "three_quarter": "Three-quarter",
    "side": "Side",
    "back": "Back",
    "top": "Top",
    "detail": "Detail",
    "in_situ": "In situ",
}
_VIEWS_UNRESOLVED = {"category_template": "Category template"}
_VIEWS_UNSUPPORTED: dict[str, str] = {}
_PROPORTIONS_MAP = {
    "1:1": "Square · 1:1",
    "4:5": "Portrait · 4:5",
    "16:9": "Landscape · 16:9",
    "3:4": "3:4",
    "4:3": "4:3",
    "9:16": "9:16",
    "2:3": "2:3",
}
_PROPORTIONS_UNRESOLVED = {"standard_for_category": "Standard for category"}
_PROPORTIONS_UNSUPPORTED: dict[str, str] = {}
_RESOLUTIONS_MAP = {"2k": "2K", "4k": "4K"}
_RESOLUTIONS_UNRESOLVED = {"standard_for_category": "Standard for category"}
_RESOLUTIONS_UNSUPPORTED = {
    "web": "Web",
    "standard": "Standard",
    "high": "High",
    "print": "Print",
}
_LIGHTING = {
    "soft_daylight": "Soft daylight",
    "golden_afternoon": "Golden afternoon",
    "warm_evening": "Warm evening",
}
_WALLS = {
    "white": "White",
    "ivory": "Ivory",
    "sand": "Sand",
    "greige": "Greige",
    "taupe": "Taupe",
    "sage": "Sage",
    "charcoal": "Charcoal",
    "terracotta": "Terracotta",
}
_FLOORS = {
    "light_oak": "Light oak",
    "dark_walnut": "Dark walnut",
    "limestone": "Limestone",
    "marble": "Marble",
}
_MOODS = {
    "automatic": "Automatic",
    "calm_natural": "Calm & natural",
    "warm_inviting": "Warm & inviting",
    "refined_elegant": "Refined & elegant",
    "bold_expressive": "Bold & expressive",
}
_REFERENCE_TYPE_TO_PHASE0 = {
    "product_image": "Product / vendor reference",
    "room_image": "Room / target space",
    "inspiration": "Inspiration / look",
    "previous_result": "Previous result",
    "other_view": "Other views / pieces",
    "specification_file": "Specifications / Excel",
}
_REFERENCE_TYPE_UNSUPPORTED = {
    "detail": "Phase-0 has no Detail reference role. The UIMidas type remains on the saved brief.",
    "midas": "Catalogue / Midas library references are not a Phase-0 reference role.",
}
_MEDIA_IMAGE = {"jpg": "JPG", "jpeg": "JPG", "png": "PNG", "webp": "WebP"}
_MEDIA_FILE = {"pdf": "PDF", "xls": "XLS", "xlsx": "XLSX", "csv": "CSV"}
_MEDIA_CANONICAL = {
    "JPG": "JPG",
    "JPEG": "JPG",
    "PNG": "PNG",
    "WEBP": "WebP",
    "PDF": "PDF",
    "XLS": "XLS",
    "XLSX": "XLSX",
    "CSV": "CSV",
}
_PHASE0_IMAGE_MEDIA = {"JPG", "PNG", "WebP"}
_PHASE0_FILE_MEDIA = {"PDF", "XLS", "XLSX", "CSV"}
_METADATA_UNREPRESENTABLE = (
    "sku",
    "dimensions",
    "colour",
    "fabric_material",
    "additional_input_data",
    "item_relationships",
)
_NOTE_FIELDS = (
    "description_metadata_preference",
    "previous_generation",
    "custom_prompting",
    "fidelity",
    "styling",
    "cluttering",
    "description_checkpoint",
    "semantic_grounding",
)


def _assert_frontend_enums_classified() -> None:
    """Fail import if a UIMidas wire enum is not handled."""

    def missing(declared: tuple[str, ...], handled: set[str], name: str) -> None:
        leftover = set(declared) - handled
        if leftover:
            raise RuntimeError(f"unclassified UIMidas {name}: {sorted(leftover)}")

    missing(get_args(JobKind), set(_JOB_TYPE), "JobKind")
    missing(get_args(NewProjectMode), {"batch", "one_by_one"}, "NewProjectMode")
    missing(get_args(EditMode), {"choose_from_saving", "new_item"}, "EditMode")
    missing(get_args(SingleItemRole), {"hero", "secondary"}, "SingleItemRole")
    missing(get_args(OutputConcept), set(_OUTCOMES), "OutputConcept")
    missing(
        get_args(OutputView),
        set(_VIEWS_MAP) | set(_VIEWS_UNRESOLVED) | set(_VIEWS_UNSUPPORTED),
        "OutputView",
    )
    missing(
        get_args(ImageProportion),
        set(_PROPORTIONS_MAP) | set(_PROPORTIONS_UNRESOLVED) | set(_PROPORTIONS_UNSUPPORTED),
        "ImageProportion",
    )
    missing(
        get_args(ImageResolution),
        set(_RESOLUTIONS_MAP) | set(_RESOLUTIONS_UNRESOLVED) | set(_RESOLUTIONS_UNSUPPORTED),
        "ImageResolution",
    )
    missing(get_args(LightingPreference), set(_LIGHTING), "LightingPreference")
    missing(get_args(WallPreference), set(_WALLS), "WallPreference")
    missing(get_args(FloorPreference), set(_FLOORS), "FloorPreference")
    missing(get_args(MoodVibe), set(_MOODS), "MoodVibe")
    missing(
        get_args(ReferenceType),
        set(_REFERENCE_TYPE_TO_PHASE0) | set(_REFERENCE_TYPE_UNSUPPORTED),
        "ReferenceType",
    )


_assert_frontend_enums_classified()


class MappingIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    field: str = Field(min_length=1)
    message: str = Field(min_length=1)


class Phase0FieldsNotInBrief(BaseModel):
    """Caller-stated Phase-0 fields that UIMidas does not collect.

    Not inferred from the saved brief. Not written back onto the brief.
    product_role here is used only when the brief has no single-item role.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    source_condition: SourceCondition
    changes: ChangeBounds
    product_role: ProductRole | None = None
    package_members: list[PackageMember] = Field(min_length=1)


class BriefMappingResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    issues: list[MappingIssue]
    intake: dict[str, Any] | None = None
    intakes: list[dict[str, Any]] = Field(default_factory=list)


class ReferenceBytes(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    reference_id: str = Field(min_length=1)
    content_base64: str = Field(min_length=1)
    media_type: str | None = None


def map_saved_brief_to_phase0_intake(
    contract: ProposedJobContract,
    *,
    owner_id: str,
    contract_id: str,
    revision: int,
    reference_files: list[ReferenceBytes],
    phase0_fields_not_in_brief: Phase0FieldsNotInBrief | None,
) -> BriefMappingResult:
    """Build one Phase-0 intake per executable view/output, or explicit issues.

    One EngineCompile / GenerationOperation can carry one requested_view and
    one output_format. Multiple UIMidas views or package rows become multiple
    intakes rather than dropping extras.
    """

    issues: list[MappingIssue] = []
    intent = _map_intent(contract, issues)
    prefs = _map_preferences(contract, issues)
    extras = phase0_fields_not_in_brief
    product_role = _map_product_role(contract, extras, issues)
    _map_notes(contract.brief.notes, issues)
    items = contract.brief.items
    if not items:
        _issue(issues, UNSUPPORTED_SLICE, "brief.items", "The brief has no items.")
        return BriefMappingResult(issues=issues, intake=None, intakes=[])

    intakes: list[dict[str, Any]] = []
    for item_index, item in enumerate(items):
        _assert_package_matches_item(contract, item, issues)
        _map_category(item, issues)
        if item_index == 0:
            _map_envelope_category(contract, item, issues)
        units = _map_output_units(item, item_index, issues)
        references = _map_references(item, reference_files, issues)
        requested_pieces = _map_item_metadata(item, issues)
        count = item.metadata.item_count if item.metadata is not None else None
        selected_count = (
            {"status": "declared", "value": count}
            if isinstance(count, int) and count >= 1
            else {"status": "unresolved", "value": None}
        )
        if units is None or references is None:
            continue
        if issues or intent is None or prefs is None or product_role is None:
            continue
        source = (
            extras.source_condition
            if extras is not None
            else derive_source_condition(item)
        )
        outcome_names = [unit["concept"] for unit in units]
        changes = extras.changes if extras is not None else derive_change_bounds(item, outcome_names)
        for unit in units:
            members = (
                list(extras.package_members)
                if extras is not None
                else derive_package_members(unit["concept"], unit["view"])
            )
            intakes.append(
                {
                    "contract_id": contract_id,
                    "revision": revision,
                    "owner_id": owner_id,
                    "intent": {
                        "mode": "Manual",
                        "job_type": intent["job_type"],
                        "job_option": intent["job_option"],
                        "requested_outcomes": [unit["concept"]],
                        "other_outcome": unit["other_outcome"],
                        "requested_pieces": requested_pieces,
                        "excluded_pieces": [],
                        "selected_count": selected_count,
                    },
                    "item": {
                        "department": item.department,
                        "category": item.category,
                        "subcategory": item.subcategory,
                        "product_role": product_role,
                    },
                    "source_condition": source.model_dump(mode="python"),
                    "references": references,
                    "outputs": {
                        "views": [unit["view"]],
                        "image_proportions": unit["proportion"],
                        "resolution": unit["resolution"],
                        "package_members": members,
                    },
                    "changes": changes.model_dump(mode="python"),
                    "preferences": prefs,
                    "statements": [],
                    "unknowns": [],
                    "conflicts": [],
                }
            )

    if issues:
        return BriefMappingResult(issues=issues, intake=None, intakes=[])
    if not intakes or intent is None or prefs is None or product_role is None:
        return BriefMappingResult(issues=issues, intake=None, intakes=[])
    return BriefMappingResult(issues=[], intake=intakes[0], intakes=intakes)


def _issue(issues: list[MappingIssue], code: str, field: str, message: str) -> None:
    issues.append(MappingIssue(code=code, field=field, message=message))


def _map_intent(contract: ProposedJobContract, issues: list[MappingIssue]) -> dict[str, str] | None:
    job = contract.brief.job
    kind = job.kind
    if kind is None:
        _issue(issues, UNRESOLVED_JOB, "brief.job.kind", "The brief has no job kind.")
        return None
    job_type = _JOB_TYPE[kind]
    if kind == "new_project":
        option_key = job.new_project_mode
    elif kind == "edit":
        option_key = job.edit_mode
    else:
        option_key = job.single_item_role
    if option_key is None:
        _issue(
            issues,
            UNRESOLVED_JOB,
            "brief.job",
            f"{job_type} is present but its job option is missing. The saved brief was not changed.",
        )
        return None
    job_option = _JOB_OPTION[(kind, option_key)]
    if kind == "edit" and job.edit_mode == "choose_from_saving" and not job.saved_item_id:
        _issue(
            issues,
            UNRESOLVED_JOB,
            "brief.job.savedItemId",
            "Edit · Choose from saving requires savedItemId. The saved brief was not changed.",
        )
        return None
    return {"job_type": job_type, "job_option": job_option}


def _assert_package_matches_item(
    contract: ProposedJobContract,
    item: NormalizedBriefItem,
    issues: list[MappingIssue],
) -> None:
    packages = [row for row in contract.package if row.item_id == item.id]
    if not packages:
        _issue(
            issues,
            UNREPRESENTABLE_FIELD,
            "package",
            f"Envelope package has no row for item {item.id!r}. The saved brief was not changed.",
        )
        return
    envelope_outputs = [output.model_dump(mode="json") for output in packages[0].outputs]
    brief_outputs = [output.model_dump(mode="json") for output in item.requested_package]
    if envelope_outputs != brief_outputs:
        _issue(
            issues,
            UNREPRESENTABLE_FIELD,
            "package.outputs",
            "Envelope package outputs do not match brief.items[].requestedPackage. "
            "The saved brief was not changed.",
        )


def _map_category(item: NormalizedBriefItem, issues: list[MappingIssue]) -> None:
    if item.category_state != "specified" or not item.department or not item.category or not item.subcategory:
        _issue(
            issues,
            UNRESOLVED_CATEGORY,
            "brief.items[0].categoryState",
            "Phase-0 requires stated department, category, and subcategory. "
            "automatic_unknown is the UIMidas placeholder for Automatic from references "
            "and is not executed. Specify all three; ids are passed through as stated.",
        )
        return
    for name, value in (
        ("department", item.department),
        ("category", item.category),
        ("subcategory", item.subcategory),
    ):
        if value.strip() in _UNRESOLVED_TEXT:
            _issue(
                issues,
                UNRESOLVED_CATEGORY,
                f"brief.items[0].{name}",
                f"{name} uses an unresolved Phase-0 placeholder.",
            )


def _map_envelope_category(
    contract: ProposedJobContract,
    item: NormalizedBriefItem,
    issues: list[MappingIssue],
) -> None:
    if contract.category is None or item.category is None:
        return
    if contract.category != item.category:
        _issue(
            issues,
            UNREPRESENTABLE_FIELD,
            "category",
            "Envelope category does not match brief.items[0].category. "
            "The saved brief was not changed.",
        )


def _map_output_units(
    item: NormalizedBriefItem,
    item_index: int,
    issues: list[MappingIssue],
) -> list[dict[str, Any]] | None:
    field = f"brief.items[{item_index}].requestedPackage"
    if not item.requested_package:
        _issue(issues, UNRESOLVED_OUTPUT, field, "Phase-0 requires at least one requested outcome.")
        return None
    units: list[dict[str, Any]] = []
    ok = True
    for index, output in enumerate(item.requested_package):
        mapped = _map_one_output(output, index, issues)
        if mapped is None:
            ok = False
            continue
        if output.variation_count is not None:
            _issue(
                issues,
                UNREPRESENTABLE_FIELD,
                f"requestedPackage[{index}].variationCount",
                "variationCount has no Phase-0 execution contract for distinct versions. "
                "The saved brief still has this value. It is not expanded into extra jobs.",
            )
            ok = False
            continue
        for view in mapped["views"]:
            units.append(
                {
                    "concept": mapped["concept"],
                    "other_outcome": mapped["other_outcome"],
                    "view": view,
                    "proportion": mapped["proportion"],
                    "resolution": mapped["resolution"],
                }
            )
    if not ok or not units:
        return None
    return units


def _map_one_output(
    output: NormalizedPackageOutput,
    index: int,
    issues: list[MappingIssue],
) -> dict[str, Any] | None:
    concept = _OUTCOMES.get(output.concept)
    if concept is None:
        _issue(
            issues,
            UNRESOLVED_OUTPUT,
            f"requestedPackage[{index}].concept",
            f"{output.concept!r} is not a Phase-0 requested outcome.",
        )
        return None
    other_outcome = None
    if output.concept == "others":
        if not output.other_label or not output.other_label.strip():
            _issue(
                issues,
                UNRESOLVED_OUTPUT,
                f"requestedPackage[{index}].otherLabel",
                "Others requires otherLabel.",
            )
            return None
        other_outcome = output.other_label.strip()
    mapped_views: list[str] = []
    failed = False
    for view in output.views or []:
        if view in _VIEWS_UNRESOLVED:
            _issue(
                issues,
                UNRESOLVED_OUTPUT,
                f"requestedPackage[{index}].views",
                f"{view!r} is the UIMidas placeholder {_VIEWS_UNRESOLVED[view]!r} "
                "and is rejected by Phase-0.",
            )
            failed = True
            continue
        if view in _VIEWS_UNSUPPORTED:
            _issue(
                issues,
                UNSUPPORTED_VIEW,
                f"requestedPackage[{index}].views",
                f"{view!r} ({_VIEWS_UNSUPPORTED[view]}) is a valid UIMidas view. "
                "Phase-0 OutputView only allows Wide view, Close-up, and Wide view + close-up.",
            )
            failed = True
            continue
        mapped = _VIEWS_MAP.get(view)
        if mapped is None:
            _issue(
                issues,
                UNSUPPORTED_VIEW,
                f"requestedPackage[{index}].views",
                f"{view!r} is not classified for Phase-0 execution.",
            )
            failed = True
            continue
        mapped_views.append(mapped)
    if not (output.views or []):
        _issue(
            issues,
            UNRESOLVED_OUTPUT,
            f"requestedPackage[{index}].views",
            "Phase-0 requires at least one mapped view.",
        )
        failed = True
    proportion_key = output.proportion or ""
    if proportion_key in _PROPORTIONS_UNRESOLVED:
        _issue(
            issues,
            UNRESOLVED_OUTPUT,
            f"requestedPackage[{index}].proportion",
            "standard_for_category is the UIMidas placeholder Standard for category.",
        )
        failed = True
        proportion = None
    elif proportion_key in _PROPORTIONS_UNSUPPORTED:
        _issue(
            issues,
            UNSUPPORTED_PROPORTION,
            f"requestedPackage[{index}].proportion",
            f"{proportion_key!r} is a valid UIMidas proportion. "
            "Phase-0 only allows Square · 1:1, Portrait · 4:5, and Landscape · 16:9.",
        )
        failed = True
        proportion = None
    else:
        proportion = _PROPORTIONS_MAP.get(proportion_key)
        if proportion is None:
            _issue(
                issues,
                UNRESOLVED_OUTPUT,
                f"requestedPackage[{index}].proportion",
                "Phase-0 requires a mapped proportion.",
            )
            failed = True
    resolution_key = output.resolution or ""
    if resolution_key in _RESOLUTIONS_UNRESOLVED:
        _issue(
            issues,
            UNRESOLVED_OUTPUT,
            f"requestedPackage[{index}].resolution",
            "standard_for_category is the UIMidas placeholder Standard for category.",
        )
        failed = True
        resolution = None
    elif resolution_key in _RESOLUTIONS_UNSUPPORTED:
        _issue(
            issues,
            UNSUPPORTED_RESOLUTION,
            f"requestedPackage[{index}].resolution",
            f"{resolution_key!r} is a valid UIMidas resolution. Phase-0 only allows 2K and 4K.",
        )
        failed = True
        resolution = None
    else:
        resolution = _RESOLUTIONS_MAP.get(resolution_key)
        if resolution is None:
            _issue(
                issues,
                UNRESOLVED_OUTPUT,
                f"requestedPackage[{index}].resolution",
                "Phase-0 requires a mapped resolution.",
            )
            failed = True
    if failed or not mapped_views or proportion is None or resolution is None:
        return None
    return {
        "concept": concept,
        "other_outcome": other_outcome,
        "views": mapped_views,
        "proportion": proportion,
        "resolution": resolution,
    }


def _map_preferences(contract: ProposedJobContract, issues: list[MappingIssue]) -> dict[str, Any] | None:
    prefs = contract.brief.preferences
    suggestions = contract.brief.suggestions
    if prefs is not None and prefs.use_workflow_defaults:
        _issue(
            issues,
            UNRESOLVED_PREFERENCES,
            "brief.preferences.useWorkflowDefaults",
            "useWorkflowDefaults is the UIMidas placeholder for Workflow default.",
        )
        return None
    lighting = _LIGHTING.get(prefs.lighting) if prefs and prefs.lighting else None
    wall = _WALLS.get(prefs.wall) if prefs and prefs.wall else None
    floor = _FLOORS.get(prefs.floor) if prefs and prefs.floor else None
    mood = _MOODS.get(suggestions.mood) if suggestions and suggestions.mood else "Automatic"
    plants = inclusion_from_brief(suggestions.plants if suggestions else None)
    human = inclusion_from_brief(suggestions.human if suggestions else None)
    if None in (lighting, wall, floor):
        if room_is_styled(outcomes_from_contract(contract)):
            _issue(
                issues,
                UNRESOLVED_PREFERENCES,
                "brief.preferences",
                "Lifestyle and other styled outcomes need lighting, wall, and floor.",
            )
            return None
        fill = catalogue_room_fill()
        lighting = lighting or fill["lighting"]
        wall = wall or fill["wall"]
        floor = floor or fill["floor"]
    payload = {
        "lighting": lighting,
        "wall": wall,
        "floor": floor,
        "plants": plants,
        "human": human,
        "mood": mood,
    }
    Preferences.model_validate(payload)
    return payload


def _map_references(
    item: NormalizedBriefItem,
    reference_files: list[ReferenceBytes],
    issues: list[MappingIssue],
) -> list[dict[str, Any]] | None:
    uploaded = {row.reference_id: row for row in reference_files}
    mapped: list[dict[str, Any]] = []
    failed = False
    for index, ref in enumerate(item.references):
        row = _map_one_reference(ref, index, uploaded, issues)
        if row is None:
            failed = True
        else:
            mapped.append(row)
    if failed or not mapped:
        if not item.references:
            _issue(
                issues,
                UNRESOLVED_REFERENCE,
                "brief.items[0].references",
                "Phase-0 requires at least one reference with identity and source bytes.",
            )
        return None
    return mapped


def _map_one_reference(
    ref: NormalizedReference,
    index: int,
    uploaded: dict[str, ReferenceBytes],
    issues: list[MappingIssue],
) -> dict[str, Any] | None:
    unsupported = _REFERENCE_TYPE_UNSUPPORTED.get(ref.type)
    if unsupported is not None:
        _issue(
            issues,
            UNSUPPORTED_REFERENCE,
            f"references[{index}].type",
            f"{ref.type!r}: {unsupported}",
        )
        return None
    role = _REFERENCE_TYPE_TO_PHASE0.get(ref.type)
    if role is None:
        _issue(
            issues,
            UNSUPPORTED_REFERENCE,
            f"references[{index}].type",
            f"{ref.type!r} is not classified for Phase-0 execution.",
        )
        return None
    if ref.source == "midas_library":
        _issue(
            issues,
            UNSUPPORTED_REFERENCE,
            f"references[{index}].source",
            "midas_library is catalogue execution and is not mapped. The saved brief was not changed.",
        )
        return None
    if ref.source != "local_file" or ref.evidence is None:
        _issue(
            issues,
            UNRESOLVED_REFERENCE,
            f"references[{index}]",
            "The reference must be a local file with evidence. Filenames are not image content.",
        )
        return None
    file_row = uploaded.get(ref.id)
    declared = (file_row.media_type if file_row is not None else None) or _media_from_name(
        ref.evidence.file_name
    )
    media = _canonical_media_type(declared)
    image = ref.evidence.media_kind == "image"
    if image and media not in _PHASE0_IMAGE_MEDIA:
        _issue(
            issues,
            UNRESOLVED_REFERENCE,
            f"references[{index}].media_type",
            "Phase-0 image intake accepts JPG, PNG, or WebP only.",
        )
        return None
    if not image and media not in _PHASE0_FILE_MEDIA:
        _issue(
            issues,
            UNRESOLVED_REFERENCE,
            f"references[{index}].media_type",
            "Phase-0 non-image intake accepts PDF, XLS, XLSX, or CSV.",
        )
        return None
    if file_row is None or not file_row.content_base64.strip():
        _issue(
            issues,
            MISSING_REFERENCE_BYTES,
            f"references[{index}]",
            f"Bytes for reference {ref.id!r} were not uploaded. Send content_base64; "
            "do not send browser paths. The saved brief was not changed.",
        )
        return None
    return {
        "reference_id": ref.id,
        "filename": ref.evidence.file_name,
        "media_type": media,
        "hash_algorithm": "sha256",
        "role": role,
        "content_base64": file_row.content_base64,
    }


def _canonical_media_type(value: str | None) -> str | None:
    if value is None:
        return None
    return _MEDIA_CANONICAL.get(value.strip().upper())


def _media_from_name(filename: str) -> str | None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return _MEDIA_IMAGE.get(ext) or _MEDIA_FILE.get(ext)


def _map_product_role(
    contract: ProposedJobContract,
    extras: Phase0FieldsNotInBrief | None,
    issues: list[MappingIssue],
) -> str | None:
    from_brief = contract.brief.job.single_item_role
    from_envelope = contract.role
    if from_brief and from_envelope and from_brief != from_envelope:
        _issue(
            issues,
            UNREPRESENTABLE_FIELD,
            "role",
            "Envelope role does not match brief.job.singleItemRole. The saved brief was not changed.",
        )
        return None
    extra_role = extras.product_role if extras is not None else None
    if extra_role:
        return extra_role
    return derive_product_role()


def _map_item_metadata(item: NormalizedBriefItem, issues: list[MappingIssue]) -> list[str]:
    pieces: list[str] = []
    metadata = item.metadata
    if metadata is None:
        return pieces
    if metadata.specific_items_combo:
        pieces.append(metadata.specific_items_combo)
    if metadata.other_pieces:
        pieces.append(metadata.other_pieces)
    identity_fields = metadata_used_as_identity(item)
    for name in _METADATA_UNREPRESENTABLE:
        if name in identity_fields:
            continue
        value = getattr(metadata, name)
        if value:
            _issue(
                issues,
                UNREPRESENTABLE_FIELD,
                f"brief.items[0].metadata.{_alias(name)}",
                "Phase-0 ItemClassification has no slot for this metadata field. "
                "The saved brief still contains it.",
            )
    return pieces


def _map_notes(notes: NormalizedNotes | None, issues: list[MappingIssue]) -> None:
    if notes is None:
        return
    for name in _NOTE_FIELDS:
        value = getattr(notes, name)
        if value:
            _issue(
                issues,
                UNREPRESENTABLE_FIELD,
                f"brief.notes.{_alias(name)}",
                "Phase-0JobContract has no notes field. The saved brief still contains this value.",
            )


def _alias(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])