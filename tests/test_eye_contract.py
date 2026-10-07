import pytest
from pydantic import ValidationError

from app.contracts.eye import EyeContract, EyeInput

HASH = "ab" * 32
SPEC_HASH = "cd" * 32
PREVIOUS_HASH = "ef" * 32


def _source(
    reference_id: str = "ref-chairs",
    role: str = "Product / vendor reference",
    content_hash: str = HASH,
    filename: str = "dining-chairs.jpg",
    media_type: str = "JPG",
    role_vocabulary: str = "create-page",
) -> dict:
    return {
        "reference_id": reference_id,
        "filename": filename,
        "media_type": media_type,
        "hash_algorithm": "sha256",
        "content_hash": content_hash,
        "role_vocabulary": role_vocabulary,
        "role": role,
    }


def _fact(
    subject: str = "back posts",
    value: str = "the chair backs show upright posts",
    basis: str = "observed",
    evidence_reference_id: str = "ref-chairs",
    content_hash: str = HASH,
) -> dict:
    return {
        "subject": subject,
        "value": value,
        "basis": basis,
        "evidence_reference_id": evidence_reference_id,
        "content_hash": content_hash,
    }


def _item(
    name: str = "dining chair",
    item_kind: str = "set",
    count: int | None = 6,
    status: str = "observed",
) -> dict:
    return {
        "name": name,
        "item_kind": item_kind,
        "count": {"status": status, "value": count},
        "visible_features": ["upright back posts"],
        "identified_from": "visible content",
        "evidence_reference_id": "ref-chairs",
        "content_hash": HASH,
    }


def _payload() -> dict:
    return {
        "eye_input": {
            "contract_id": "contract-dining-1",
            "revision": 3,
            "references": [
                _source(),
                _source(
                    reference_id="ref-spec",
                    filename="chair-spec.xlsx",
                    media_type="XLSX",
                    content_hash=SPEC_HASH,
                    role="Specifications / Excel",
                ),
            ],
        },
        "observation": {
            "contract_id": "contract-dining-1",
            "revision": 3,
            "category_candidates": [
                {
                    "label": "Dining Chairs",
                    "confidence_basis": "visible seats, backs and legs",
                    "evidence_reference_id": "ref-chairs",
                    "content_hash": HASH,
                }
            ],
            "items": [
                _item(),
                _item(name="napkin ring", item_kind="item", count=4),
            ],
            "facts": [_fact()],
            "unknowns": [
                {
                    "subject": "fibre composition",
                    "detail": "the photograph does not establish fibre",
                    "evidence_reference_id": "ref-chairs",
                }
            ],
            "ambiguities": [
                {
                    "subject": "chair subtype",
                    "hypotheses": ["side chair", "armchair"],
                    "status": "unresolved",
                    "resolution": None,
                }
            ],
            "conflicts": [
                {
                    "subject": "colour",
                    "claims": ["photographed dark stain", "swatch reads lighter"],
                    "evidence_reference_ids": ["ref-chairs"],
                }
            ],
            "parsing_limitations": [
                {
                    "evidence_reference_id": "ref-chairs",
                    "detail": "the small print on the sheet was not readable",
                }
            ],
            "relations": [
                {
                    "subject": "napkin ring",
                    "relation": "rests on",
                    "target": "the tabletop shown in the sheet",
                    "basis": "observed",
                    "evidence_reference_id": "ref-chairs",
                    "content_hash": HASH,
                }
            ],
            "regions": [
                {
                    "name": "colour chip",
                    "classification": "inset",
                    "evidence_reference_id": "ref-chairs",
                    "content_hash": HASH,
                }
            ],
            "signals": [
                {
                    "mark": "circle around two chairs",
                    "reading": "instruction",
                    "evidence_reference_id": "ref-chairs",
                    "content_hash": HASH,
                }
            ],
            "shown_views": ["front"],
            "change_log": [],
        },
    }


def test_valid_eye_input_and_generalized_observation() -> None:
    eye_input = EyeInput.model_validate(_payload()["eye_input"])
    assert eye_input.contract_id == "contract-dining-1"
    assert eye_input.references[0].filename == "dining-chairs.jpg"
    assert eye_input.references[0].role == "Product / vendor reference"

    contract = EyeContract.model_validate(_payload())
    kinds = {item.item_kind for item in contract.observation.items}
    assert kinds == {"set", "item"}
    assert {item.name for item in contract.observation.items} == {
        "dining chair",
        "napkin ring",
    }

    accessory = _payload()
    accessory["eye_input"]["contract_id"] = "contract-ring-1"
    accessory["observation"]["contract_id"] = "contract-ring-1"
    accessory["observation"]["category_candidates"][0]["label"] = "Napkin rings"
    accessory["observation"]["items"] = [_item(name="napkin ring", item_kind="item", count=4)]
    rings = EyeContract.model_validate(accessory)
    assert rings.observation.items[0].item_kind == "item"


def test_source_identity_and_unmerged_reference_roles() -> None:
    contract = EyeContract.model_validate(_payload())
    source = contract.eye_input.references[0]
    assert source.media_type == "JPG"
    assert source.hash_algorithm == "sha256"
    assert source.role_vocabulary == "create-page"

    atlas = _payload()
    atlas["eye_input"]["references"][0]["role_vocabulary"] = "atlas-handoff"
    atlas["eye_input"]["references"][0]["role"] = "product_identity"
    EyeContract.model_validate(atlas)

    crossed = _payload()
    crossed["eye_input"]["references"][0]["role"] = "target_room"
    with pytest.raises(ValidationError, match="create-page"):
        EyeContract.model_validate(crossed)

    crossed["eye_input"]["references"][0]["role_vocabulary"] = "atlas-handoff"
    crossed["eye_input"]["references"][0]["role"] = "Room / target space"
    with pytest.raises(ValidationError, match="atlas-handoff"):
        EyeContract.model_validate(crossed)


def test_hash_and_revision_binding() -> None:
    mismatched_hash = _payload()
    mismatched_hash["observation"]["facts"][0]["content_hash"] = SPEC_HASH
    with pytest.raises(ValidationError, match="content_hash"):
        EyeContract.model_validate(mismatched_hash)

    missing_hash = _payload()
    del missing_hash["eye_input"]["references"][0]["content_hash"]
    with pytest.raises(ValidationError):
        EyeInput.model_validate(missing_hash["eye_input"])

    wrong_revision = _payload()
    wrong_revision["observation"]["revision"] = 4
    with pytest.raises(ValidationError, match="revision"):
        EyeContract.model_validate(wrong_revision)

    omitted = _payload()
    del omitted["eye_input"]["revision"]
    with pytest.raises(ValidationError):
        EyeInput.model_validate(omitted["eye_input"])


def test_observation_records_fact_unknown_ambiguity_conflict_and_limit() -> None:
    contract = EyeContract.model_validate(_payload())
    observation = contract.observation
    assert observation.facts[0].basis == "observed"
    assert observation.unknowns[0].subject == "fibre composition"
    assert observation.ambiguities[0].status == "unresolved"
    assert observation.ambiguities[0].resolution is None
    assert observation.conflicts[0].claims[0] == "photographed dark stain"
    assert "not readable" in observation.parsing_limitations[0].detail

    chosen = _payload()
    chosen["observation"]["ambiguities"][0]["status"] = "unresolved"
    chosen["observation"]["ambiguities"][0]["resolution"] = "side chair"
    with pytest.raises(ValidationError, match="unresolved ambiguity"):
        EyeContract.model_validate(chosen)

    one_claim = _payload()
    one_claim["observation"]["conflicts"][0]["claims"] = ["dark stain"]
    with pytest.raises(ValidationError):
        EyeContract.model_validate(one_claim)

    unknown_limit = _payload()
    unknown_limit["observation"]["parsing_limitations"][0]["evidence_reference_id"] = "missing"
    with pytest.raises(ValidationError, match="unknown reference"):
        EyeContract.model_validate(unknown_limit)


def test_preference_previous_result_and_hidden_geometry_are_rejected() -> None:
    plants = _payload()
    plants["observation"]["facts"] = [_fact(subject="plants", value="a plant is in the frame")]
    with pytest.raises(ValidationError, match="requested preference"):
        EyeContract.model_validate(plants)

    wall = _payload()
    wall["observation"]["facts"] = [_fact(subject="wall colour", value="Sage")]
    with pytest.raises(ValidationError, match="requested preference"):
        EyeContract.model_validate(wall)

    previous = _payload()
    previous["eye_input"]["references"].append(
        _source(
            reference_id="ref-previous",
            filename="earlier.png",
            media_type="PNG",
            content_hash=PREVIOUS_HASH,
            role="Previous result",
        )
    )
    previous["observation"]["facts"] = [
        _fact(
            subject="back posts",
            value="copied from the earlier render",
            evidence_reference_id="ref-previous",
            content_hash=PREVIOUS_HASH,
        )
    ]
    with pytest.raises(ValidationError, match="previous result"):
        EyeContract.model_validate(previous)

    hidden = _payload()
    hidden["observation"]["facts"] = [
        _fact(subject="base", value="the hidden geometry is a boxed plinth")
    ]
    with pytest.raises(ValidationError, match="hidden or unseen geometry"):
        EyeContract.model_validate(hidden)

    fibre = _payload()
    fibre["observation"]["facts"] = [
        _fact(subject="material", value="fibre composition is cotton", basis="inferred")
    ]
    with pytest.raises(ValidationError, match="material composition"):
        EyeContract.model_validate(fibre)

    filename = _payload()
    filename["observation"]["items"][0]["identified_from"] = "filename"
    with pytest.raises(ValidationError, match="filename or collage"):
        EyeContract.model_validate(filename)


def test_unsupported_fields_are_rejected() -> None:
    extra_input = _payload()
    extra_input["eye_input"]["model_id"] = "openai/gpt-4.1"
    with pytest.raises(ValidationError):
        EyeContract.model_validate(extra_input)

    extra_observation = _payload()
    extra_observation["observation"]["living_room_prompt"] = "sofa set"
    with pytest.raises(ValidationError):
        EyeContract.model_validate(extra_observation)

    sku = _payload()
    sku["observation"]["facts"] = [_fact(subject="sku", value="CH-12")]
    with pytest.raises(ValidationError, match="SKU and dimensions"):
        EyeContract.model_validate(sku)

    published = _payload()
    published["observation"]["facts"] = [
        _fact(
            subject="dimensions",
            value="the specification states a 45 cm seat height",
            basis="published",
            evidence_reference_id="ref-spec",
            content_hash=SPEC_HASH,
        )
    ]
    EyeContract.model_validate(published)


def test_signals_keep_classified_uncertain_and_competing_intent() -> None:
    classified = EyeContract.model_validate(_payload())
    signal = classified.observation.signals[0]
    assert signal.mark == "circle around two chairs"
    assert signal.reading == "instruction"

    uncertain = _payload()
    uncertain["observation"]["signals"] = [
        {
            "mark": "green swatch/inset",
            "reading": None,
            "evidence_reference_id": "ref-chairs",
            "content_hash": HASH,
        }
    ]
    preserved = EyeContract.model_validate(uncertain)
    assert preserved.observation.signals[0].mark == "green swatch/inset"
    assert preserved.observation.signals[0].reading is None

    competing = _payload()
    competing["observation"]["signals"] = [
        {
            "mark": "green swatch/inset",
            "reading": None,
            "evidence_reference_id": "ref-chairs",
            "content_hash": HASH,
        }
    ]
    competing["observation"]["ambiguities"].append(
        {
            "subject": "green swatch/inset",
            "hypotheses": ["variant", "instruction"],
            "status": "unresolved",
            "resolution": None,
        }
    )
    open_readings = EyeContract.model_validate(competing)
    ambiguity = open_readings.observation.ambiguities[-1]
    assert open_readings.observation.signals[0].reading is None
    assert ambiguity.status == "unresolved"
    assert ambiguity.resolution is None
    assert ambiguity.hypotheses == ["variant", "instruction"]

    invented_kind = _payload()
    invented_kind["observation"]["signals"][0]["reading"] = "unknown"
    with pytest.raises(ValidationError):
        EyeContract.model_validate(invented_kind)

    chosen_anyway = _payload()
    chosen_anyway["observation"]["signals"] = [
        {
            "mark": "green swatch/inset",
            "reading": None,
            "evidence_reference_id": "ref-chairs",
            "content_hash": HASH,
        }
    ]
    chosen_anyway["observation"]["ambiguities"].append(
        {
            "subject": "green swatch/inset",
            "hypotheses": ["variant", "instruction"],
            "status": "unresolved",
            "resolution": "variant",
        }
    )
    with pytest.raises(ValidationError, match="unresolved ambiguity"):
        EyeContract.model_validate(chosen_anyway)
