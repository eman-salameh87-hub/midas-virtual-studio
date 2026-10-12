import pytest

from app.contracts.eye import EyeInput
from app.providers.living_room_eye_observation import (
    LivingRoomEyeMappingError,
    map_living_room_eye_json,
)

HASH = "ab" * 32
LOGO_SIGNAL = (
    "Ashley Furniture Homestore logo in the top left corner, "
    "likely indicating the vendor or brand"
)


def _eye_input() -> EyeInput:
    return EyeInput.model_validate(
        {
            "contract_id": "contract-adapter-1",
            "revision": 1,
            "references": [
                {
                    "reference_id": "ref-bed",
                    "filename": "bed-product-reference.png",
                    "media_type": "PNG",
                    "hash_algorithm": "sha256",
                    "content_hash": HASH,
                    "role_vocabulary": "create-page",
                    "role": "Product / vendor reference",
                }
            ],
        }
    )


def _historical(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "product_category": "Bed",
        "physical_items": [
            {
                "item": "bed",
                "count": 1,
                "role": "product",
                "description": "upholstered platform with a padded headboard",
            }
        ],
        "views_not_items": [],
        "signals": [],
        "colour_observed": "grey",
        "material_appearance": "fabric upholstery",
        "design_locks": ["padded headboard"],
        "unknowns": ["hidden sides"],
        "conflicts": [],
    }
    payload.update(overrides)
    return payload


def test_historical_signal_string_is_preserved_without_a_reading() -> None:
    observation = map_living_room_eye_json(
        _historical(signals=[LOGO_SIGNAL]),
        _eye_input(),
    )

    assert len(observation.signals) == 1
    signal = observation.signals[0]
    assert signal.mark == LOGO_SIGNAL
    assert signal.reading is None
    assert signal.evidence_reference_id == "ref-bed"
    assert signal.content_hash == HASH


def test_historical_strings_cannot_establish_a_canonical_reading() -> None:
    observation = map_living_room_eye_json(
        _historical(
            signals=[
                "X mark excluding a table; this looks like an instruction",
                "green swatch that could be a variant",
            ]
        ),
        _eye_input(),
    )

    assert [signal.mark for signal in observation.signals] == [
        "X mark excluding a table; this looks like an instruction",
        "green swatch that could be a variant",
    ]
    assert all(signal.reading is None for signal in observation.signals)


def test_historical_mapping_failures_still_fail() -> None:
    with pytest.raises(LivingRoomEyeMappingError, match="unsupported historical keys"):
        map_living_room_eye_json(_historical(extra_key="no"), _eye_input())

    missing = _historical()
    del missing["unknowns"]
    with pytest.raises(LivingRoomEyeMappingError, match="missing historical keys"):
        map_living_room_eye_json(missing, _eye_input())

    with pytest.raises(LivingRoomEyeMappingError, match="physical_items"):
        map_living_room_eye_json(
            _historical(physical_items=[{"item": "bed"}]),
            _eye_input(),
        )

    with pytest.raises(LivingRoomEyeMappingError, match="conflicts"):
        map_living_room_eye_json(
            _historical(conflicts=["photo disagrees with the client colour"]),
            _eye_input(),
        )

    with pytest.raises(LivingRoomEyeMappingError, match="signals\\[0\\]"):
        map_living_room_eye_json(_historical(signals=[""]), _eye_input())

    with pytest.raises(LivingRoomEyeMappingError, match="signals\\[0\\]"):
        map_living_room_eye_json(
            _historical(signals=[{"mark": LOGO_SIGNAL, "reading": "instruction"}]),
            _eye_input(),
        )


def _assert_unrelated_eye_fields(observation) -> None:  # noqa: ANN001
    assert observation.category_candidates[0].label == "Bed"
    assert observation.items[0].name == "bed"
    assert [fact.value for fact in observation.facts if fact.subject == "colour_observed"] == [
        "grey"
    ]
    assert [
        fact.value for fact in observation.facts if fact.subject == "material_appearance"
    ] == ["fabric upholstery"]
    assert [fact.value for fact in observation.facts if fact.subject == "design_locks"] == [
        "padded headboard"
    ]
    assert observation.unknowns[0].detail == "hidden sides"
    assert observation.regions == []
    assert observation.signals == []
    assert observation.ambiguities == []
    assert observation.shown_views == []


def test_empty_conflicts_leave_unrelated_eye_fields_unchanged() -> None:
    observation = map_living_room_eye_json(_historical(), _eye_input())

    assert observation.conflicts == []
    _assert_unrelated_eye_fields(observation)


def test_structured_conflicts_map_to_eye_conflict_with_bound_evidence() -> None:
    observation = map_living_room_eye_json(
        _historical(
            conflicts=[
                {
                    "subject": "colour",
                    "claims": ["photographed grey", "client name dusty-rose"],
                }
            ]
        ),
        _eye_input(),
    )

    assert len(observation.conflicts) == 1
    conflict = observation.conflicts[0]
    assert conflict.subject == "colour"
    assert conflict.claims == ["photographed grey", "client name dusty-rose"]
    assert conflict.evidence_reference_ids == ["ref-bed"]
    _assert_unrelated_eye_fields(observation)


def test_legacy_string_conflicts_still_fail_closed() -> None:
    with pytest.raises(
        LivingRoomEyeMappingError,
        match="conflicts\\[\\] are historical strings; EyeObservation.conflicts requires "
        "subject and at least two claims",
    ):
        map_living_room_eye_json(
            _historical(conflicts=["photo disagrees with the client colour"]),
            _eye_input(),
        )


def test_mixed_and_malformed_conflicts_still_fail_closed() -> None:
    with pytest.raises(LivingRoomEyeMappingError, match="historical strings"):
        map_living_room_eye_json(
            _historical(
                conflicts=[
                    "photo disagrees with the client colour",
                    {
                        "subject": "colour",
                        "claims": ["photographed grey", "client name dusty-rose"],
                    },
                ]
            ),
            _eye_input(),
        )

    with pytest.raises(LivingRoomEyeMappingError, match="must be an object"):
        map_living_room_eye_json(
            _historical(conflicts=[12]),
            _eye_input(),
        )

    with pytest.raises(LivingRoomEyeMappingError, match="unsupported keys"):
        map_living_room_eye_json(
            _historical(
                conflicts=[
                    {
                        "subject": "colour",
                        "claims": ["photographed grey", "client name dusty-rose"],
                        "evidence_reference_ids": ["invented"],
                    }
                ]
            ),
            _eye_input(),
        )

    with pytest.raises(LivingRoomEyeMappingError, match="at least two"):
        map_living_room_eye_json(
            _historical(
                conflicts=[{"subject": "colour", "claims": ["photographed grey"]}]
            ),
            _eye_input(),
        )

    with pytest.raises(LivingRoomEyeMappingError, match="claims\\[0\\]"):
        map_living_room_eye_json(
            _historical(
                conflicts=[{"subject": "colour", "claims": ["", "client name dusty-rose"]}]
            ),
            _eye_input(),
        )
