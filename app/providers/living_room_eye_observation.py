"""Map a historical Living Room Eye JSON object onto EyeObservation.

This is provider-proof mapping only. Unmapped historical keys fail instead
of being rewritten into new EyeObservation fields.
"""

from __future__ import annotations

from typing import Any

from app.contracts.eye import EyeInput, EyeObservation, EyeSource

HISTORICAL_KEYS = (
    "product_category",
    "physical_items",
    "views_not_items",
    "signals",
    "colour_observed",
    "material_appearance",
    "design_locks",
    "unknowns",
    "conflicts",
)
ITEM_KEYS = ("item", "count", "role", "description")
HISTORICAL_ITEM_ROLES = {"product", "excluded", "context"}
_PREVIOUS_RESULT_ROLES = {"Previous result", "previous_result"}


class LivingRoomEyeMappingError(ValueError):
    """Historical Eye JSON could not be placed on EyeObservation."""

    def __init__(self, mismatches: list[str]) -> None:
        self.mismatches = list(mismatches)
        super().__init__("; ".join(self.mismatches))


def map_living_room_eye_json(
    payload: dict[str, Any],
    eye_input: EyeInput,
) -> EyeObservation:
    """Bind job identity from EyeInput. Map only the explicit table below.

    Explicit mappings:
    - product_category → category_candidates[].label
      confidence_basis is not in the historical JSON; it is recorded as
      'historical key product_category'
    - physical_items.role=product → items[] with item_kind=item
      historical role is not item_kind; excluded/context are not PhysicalItems
    - physical_items.description → visible_features (one entry)
    - identified_from=visible content because the standing prompt is visible-only
    - views_not_items[] → regions[] classification=inset
    - colour_observed → facts subject=colour_observed basis=observed
    - material_appearance → facts subject=material_appearance basis=observed
    - design_locks[] → facts subject=design_locks
    - unknowns[] → unknowns subject=detail=the string
    - signals[] strings → SignalReading.mark with reading=None
      Historical format is short strings; it cannot name instruction,
      view, variant, or packaging. The adapter does not invent a reading.

    Failures (no silent mapping):
    - extra or missing historical keys
    - physical_items extra or missing keys
    - role outside product|excluded|context
    - signals[] entries that are not non-empty strings
    - conflicts[] non-empty (strings cannot fill EyeConflict.claims)
    """

    mismatches: list[str] = []
    if not isinstance(payload, dict):
        raise LivingRoomEyeMappingError(
            ["historical Eye response is not a JSON object"]
        )
    extra = sorted(set(payload) - set(HISTORICAL_KEYS))
    missing = [key for key in HISTORICAL_KEYS if key not in payload]
    if extra:
        mismatches.append(f"unsupported historical keys: {extra}")
    if missing:
        mismatches.append(f"missing historical keys: {missing}")
    reference = _product_reference(eye_input, mismatches)
    if mismatches:
        raise LivingRoomEyeMappingError(mismatches)

    category = payload["product_category"]
    if not isinstance(category, str) or not category.strip():
        mismatches.append("product_category must be a non-empty string")

    items, item_mismatches = _map_items(payload["physical_items"], reference)
    mismatches.extend(item_mismatches)

    regions, region_mismatches = _string_list(
        payload["views_not_items"],
        "views_not_items",
    )
    mismatches.extend(region_mismatches)

    signals, signal_mismatches = _string_list(payload["signals"], "signals")
    mismatches.extend(signal_mismatches)

    colour = payload["colour_observed"]
    if not isinstance(colour, str) or not colour.strip():
        mismatches.append("colour_observed must be a non-empty string")
    appearance = payload["material_appearance"]
    if not isinstance(appearance, str) or not appearance.strip():
        mismatches.append("material_appearance must be a non-empty string")

    locks, lock_mismatches = _string_list(payload["design_locks"], "design_locks")
    mismatches.extend(lock_mismatches)
    unknowns, unknown_mismatches = _string_list(payload["unknowns"], "unknowns")
    mismatches.extend(unknown_mismatches)
    conflicts, conflict_mismatches = _string_list(payload["conflicts"], "conflicts")
    mismatches.extend(conflict_mismatches)
    if conflicts:
        mismatches.append(
            "conflicts[] are historical strings; EyeObservation.conflicts requires "
            "subject and at least two claims"
        )

    if mismatches:
        raise LivingRoomEyeMappingError(mismatches)

    facts = [
        {
            "subject": "colour_observed",
            "value": colour.strip(),
            "basis": "observed",
            "evidence_reference_id": reference.reference_id,
            "content_hash": reference.content_hash,
        },
        {
            "subject": "material_appearance",
            "value": appearance.strip(),
            "basis": "observed",
            "evidence_reference_id": reference.reference_id,
            "content_hash": reference.content_hash,
        },
    ]
    for lock in locks:
        facts.append(
            {
                "subject": "design_locks",
                "value": lock,
                "basis": "observed",
                "evidence_reference_id": reference.reference_id,
                "content_hash": reference.content_hash,
            }
        )
    return EyeObservation.model_validate(
        {
            "contract_id": eye_input.contract_id,
            "revision": eye_input.revision,
            "category_candidates": [
                {
                    "label": category.strip(),
                    "confidence_basis": "historical key product_category",
                    "evidence_reference_id": reference.reference_id,
                    "content_hash": reference.content_hash,
                }
            ],
            "items": items,
            "facts": facts,
            "unknowns": [
                {
                    "subject": unknown,
                    "detail": unknown,
                    "evidence_reference_id": reference.reference_id,
                }
                for unknown in unknowns
            ],
            "ambiguities": [],
            "conflicts": [],
            "parsing_limitations": [],
            "relations": [],
            "regions": [
                {
                    "name": name,
                    "classification": "inset",
                    "evidence_reference_id": reference.reference_id,
                    "content_hash": reference.content_hash,
                }
                for name in regions
            ],
            "signals": [
                {
                    "mark": mark,
                    "reading": None,
                    "evidence_reference_id": reference.reference_id,
                    "content_hash": reference.content_hash,
                }
                for mark in signals
            ],
            "shown_views": [],
            "change_log": [],
        }
    )


def _product_reference(
    eye_input: EyeInput,
    mismatches: list[str],
) -> EyeSource:
    usable = [
        reference
        for reference in eye_input.references
        if reference.role not in _PREVIOUS_RESULT_ROLES
    ]
    if len(usable) != 1:
        mismatches.append(
            "provider-proof mapping requires exactly one non-previous-result reference"
        )
        return eye_input.references[0]
    return usable[0]


def _map_items(
    raw: object,
    reference: EyeSource,
) -> tuple[list[dict[str, object]], list[str]]:
    mismatches: list[str] = []
    if not isinstance(raw, list):
        return [], ["physical_items must be an array"]
    items: list[dict[str, object]] = []
    for index, entry in enumerate(raw):
        prefix = f"physical_items[{index}]"
        if not isinstance(entry, dict):
            mismatches.append(f"{prefix} is not an object")
            continue
        extra = sorted(set(entry) - set(ITEM_KEYS))
        missing = [key for key in ITEM_KEYS if key not in entry]
        if extra:
            mismatches.append(f"{prefix} unsupported keys: {extra}")
        if missing:
            mismatches.append(f"{prefix} missing keys: {missing}")
            continue
        role = entry["role"]
        if role not in HISTORICAL_ITEM_ROLES:
            mismatches.append(
                f"{prefix}.role={role!r} is not historical product|excluded|context"
            )
            continue
        if role != "product":
            continue
        name = entry["item"]
        description = entry["description"]
        count = entry["count"]
        if not isinstance(name, str) or not name.strip():
            mismatches.append(f"{prefix}.item must be a non-empty string")
            continue
        if not isinstance(description, str) or not description.strip():
            mismatches.append(f"{prefix}.description must be a non-empty string")
            continue
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            mismatches.append(
                f"{prefix}.count must be a whole number of separate physical pieces"
            )
            continue
        items.append(
            {
                "name": name.strip(),
                "item_kind": "item",
                "count": {"status": "observed", "value": count},
                "visible_features": [description.strip()],
                "identified_from": "visible content",
                "evidence_reference_id": reference.reference_id,
                "content_hash": reference.content_hash,
            }
        )
    return items, mismatches


def _string_list(raw: object, field: str) -> tuple[list[str], list[str]]:
    if not isinstance(raw, list):
        return [], [f"{field} must be an array"]
    values: list[str] = []
    mismatches: list[str] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, str) or not entry.strip():
            mismatches.append(f"{field}[{index}] must be a non-empty string")
            continue
        values.append(entry.strip())
    return values, mismatches
