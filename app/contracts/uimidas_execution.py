"""Derive Phase-0 engine fields from a public UIMidas brief.

These rules are for the client-brief → job adapter only. POST /api/v1/jobs
still requires a full Phase-0 intake. Callers may still send
phase0_fields_not_in_brief to override a derivation.

None of these values are written back onto the saved UIMidas brief.

Rules:
- product_role is the role of the item in this generated job. A UIMidas
  one-item brief executes as hero. Hero/Secondary on single_item stays
  job_option and is not coerced to supporting.
- package_members are engine output-family labels taken from the requested
  UIMidas outcome (and Detail view). They are not a second user choice.
- input_condition is an engine routing hint from uploaded reference types.
- policy_mode is fidelity-locked for catalogue-like outcomes and
  creative-room for styled outcomes.
- protected_identity always includes the uploaded product appearance lock,
  plus user-entered sku/colour/fabric/dimensions when present. It is not a
  free-text identity brief.
- omitted plants/human mean not requested (false). Mood defaults to Automatic.
- white-background-only jobs with no room picks use a catalogue room fill
  (Soft daylight, White, Light oak) so the engine contract is complete.
  Styled outcomes still require the user lighting/wall/floor choices.
"""

from __future__ import annotations

from app.contracts.client_brief import NormalizedBriefItem, ProposedJobContract
from app.contracts.job import ChangeBounds, PackageMember, SourceCondition

_STYLED_OUTCOMES = {
    "Lifestyle",
    "New Composition",
    "Variations",
    "Create with this item",
    "Others",
}
_CATALOGUE_OUTCOMES = {"White BK", "Website"}
_OUTCOME_TO_MEMBER: dict[str, PackageMember] = {
    "White BK": "catalogue",
    "Lifestyle": "lifestyle",
    "Website": "catalogue",
    "New Composition": "lifestyle",
    "Variations": "alternative view",
    "Create with this item": "lifestyle",
    "Others": "alternative view",
}
_WHITE_BK_ROOM = {
    "lighting": "Soft daylight",
    "wall": "White",
    "floor": "Light oak",
}
PRODUCT_APPEARANCE_LOCK = "uploaded product appearance"


def derive_product_role() -> str:
    """The item in this exploded job is the subject of the generation."""

    return "hero"


def derive_source_condition(item: NormalizedBriefItem) -> SourceCondition:
    types = {ref.type for ref in item.references}
    has_room = "room_image" in types
    has_spec = "specification_file" in types
    has_product = bool(types & {"product_image", "other_view", "detail"})
    if has_spec and (has_room or has_product):
        condition = "mixed batch"
    elif has_spec:
        condition = "technical document"
    elif has_room:
        condition = "scene"
    elif has_product:
        condition = "clean pack shot"
    else:
        condition = "mixed batch"
    return SourceCondition(input_condition=condition)


def derive_package_members(concept: str, view: str) -> list[PackageMember]:
    member = _OUTCOME_TO_MEMBER.get(concept, "alternative view")
    members: list[PackageMember] = [member]
    if view == "Detail" and "detail" not in members:
        members.append("detail")
    return members


def derive_change_bounds(
    item: NormalizedBriefItem,
    requested_outcomes: list[str],
) -> ChangeBounds:
    styled = any(outcome in _STYLED_OUTCOMES for outcome in requested_outcomes)
    protected = [PRODUCT_APPEARANCE_LOCK]
    metadata = item.metadata
    if metadata is not None:
        for value in (metadata.sku, metadata.colour, metadata.fabric_material, metadata.dimensions):
            if value and value.strip() and value.strip() not in protected:
                protected.append(value.strip())
    return ChangeBounds(
        policy_mode="creative-room" if styled else "fidelity-locked",
        allowed_changes=[],
        protected_identity=protected,
        room_locks=[],
        creative_variables=[],
    )


def room_is_styled(requested_outcomes: list[str]) -> bool:
    return any(outcome in _STYLED_OUTCOMES for outcome in requested_outcomes)


def catalogue_room_fill() -> dict[str, str]:
    return dict(_WHITE_BK_ROOM)


def inclusion_from_brief(value: str | None) -> bool:
    """suggest → True. leave_out or omitted/unspecified → not requested."""

    return value == "suggest"


_CONCEPT_LABELS = {
    "white_bk": "White BK",
    "lifestyle": "Lifestyle",
    "website": "Website",
    "new_composition": "New Composition",
    "variations": "Variations",
    "create_with_this_item": "Create with this item",
    "others": "Others",
}


def outcomes_from_contract(contract: ProposedJobContract) -> list[str]:
    names: list[str] = []
    for item in contract.brief.items:
        for output in item.requested_package:
            mapped = _CONCEPT_LABELS.get(output.concept)
            if mapped:
                names.append(mapped)
    return names


def metadata_used_as_identity(item: NormalizedBriefItem) -> set[str]:
    names = set()
    metadata = item.metadata
    if metadata is None:
        return names
    if metadata.sku:
        names.add("sku")
    if metadata.colour:
        names.add("colour")
    if metadata.fabric_material:
        names.add("fabric_material")
    if metadata.dimensions:
        names.add("dimensions")
    return names
