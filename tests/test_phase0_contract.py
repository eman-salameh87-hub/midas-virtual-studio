import pytest
from pydantic import ValidationError

from app.contracts.job import Phase0JobContract


def _reference(
    reference_id: str = "ref-towel",
    role: str = "Product / vendor reference",
    filename: str = "towel-sheet.jpg",
) -> dict:
    return {
        "reference_id": reference_id,
        "filename": filename,
        "media_type": "JPG",
        "hash_algorithm": "sha256",
        "content_hash": "ab" * 32,
        "role": role,
    }


def _payload() -> dict:
    return {
        "contract_id": "contract-towel-1",
        "revision": 1,
        "owner_id": "owner-1",
        "intent": {
            "mode": "Manual",
            "job_type": "New Project",
            "job_option": "One by one (same department)",
            "requested_outcomes": ["Lifestyle"],
            "other_outcome": None,
            "requested_pieces": ["towel"],
            "excluded_pieces": ["inset views"],
            "selected_count": {"status": "declared", "value": 1},
        },
        "item": {
            "department": "Accessories",
            "category": "Bathroom",
            "subcategory": "Towels",
            "product_role": "hero",
        },
        "source_condition": {"input_condition": "annotated multi-view sheet"},
        "references": [_reference()],
        "outputs": {
            "views": ["Wide view"],
            "image_proportions": "Square · 1:1",
            "resolution": "2K",
            "package_members": ["lifestyle"],
        },
        "changes": {
            "policy_mode": "fidelity-locked",
            "allowed_changes": ["styled setting"],
            "protected_identity": ["towel count", "border bands"],
            "room_locks": [],
            "creative_variables": [],
        },
        "preferences": {
            "lighting": "Soft daylight",
            "wall": "Sage",
            "floor": "Limestone",
            "plants": False,
            "human": False,
            "mood": "Calm & natural",
        },
        "statements": [
            {
                "subject": "border bands",
                "value": "visible on the photographed towel",
                "basis": "observed",
                "evidence_reference_id": "ref-towel",
            }
        ],
        "unknowns": [
            {
                "subject": "fibre composition",
                "detail": "the photograph does not establish fibre or GSM",
            }
        ],
        "conflicts": [
            {
                "subject": "colour",
                "claims": ["photographed dusty-rose", "olive swatch"],
            }
        ],
    }


def test_valid_generalized_phase0_contract() -> None:
    towel = Phase0JobContract.model_validate(_payload())
    assert towel.item.category == "Bathroom"
    assert towel.item.subcategory == "Towels"
    assert towel.item.product_role == "hero"

    dining = _payload()
    dining["contract_id"] = "contract-chair-1"
    dining["item"] = {
        "department": "Home Furniture",
        "category": "Dining Rooms",
        "subcategory": "Dining Chairs",
        "product_role": "supporting",
    }
    dining["source_condition"] = {"input_condition": "clean pack shot"}
    dining["intent"]["requested_pieces"] = ["chair"]
    dining["intent"]["selected_count"] = {"status": "declared", "value": 12}
    chair = Phase0JobContract.model_validate(dining)
    assert chair.item.subcategory == "Dining Chairs"
    assert chair.item.product_role == "supporting"


def test_reference_roles_are_the_client_set_only() -> None:
    for role in (
        "Product / vendor reference",
        "Room / target space",
        "Inspiration / look",
        "Previous result",
        "Other views / pieces",
        "Specifications / Excel",
    ):
        payload = _payload()
        payload["references"] = [_reference(role=role)]
        payload["statements"] = []
        Phase0JobContract.model_validate(payload)

    for invented in ("catalogue_support", "original_product", "target_room", "owner_original"):
        payload = _payload()
        payload["references"] = [_reference(role=invented)]
        payload["statements"] = []
        with pytest.raises(ValidationError):
            Phase0JobContract.model_validate(payload)


def test_product_role_stays_separate_from_category_and_reference_role() -> None:
    payload = _payload()
    payload["references"] = [
        _reference(),
        _reference(reference_id="ref-room", filename="room.png", role="Room / target space"),
    ]
    payload["references"][1]["media_type"] = "PNG"
    contract = Phase0JobContract.model_validate(payload)
    assert contract.item.product_role == "hero"
    assert contract.item.category != contract.references[1].role
    assert contract.references[1].role == "Room / target space"

    payload["item"]["product_role"] = "Room / target space"
    with pytest.raises(ValidationError):
        Phase0JobContract.model_validate(payload)

    payload["item"]["product_role"] = "Product / set"
    with pytest.raises(ValidationError):
        Phase0JobContract.model_validate(payload)


def test_requested_choices_are_not_observed_facts() -> None:
    payload = _payload()
    payload["preferences"]["plants"] = True
    payload["statements"] = [
        {
            "subject": "plants",
            "value": "present in the source",
            "basis": "observed",
            "evidence_reference_id": "ref-towel",
        }
    ]
    with pytest.raises(ValidationError, match="requested preference"):
        Phase0JobContract.model_validate(payload)

    payload["statements"] = [
        {
            "subject": "wall colour",
            "value": "Sage",
            "basis": "observed",
            "evidence_reference_id": "ref-towel",
        }
    ]
    with pytest.raises(ValidationError, match="requested preference"):
        Phase0JobContract.model_validate(payload)

    payload["references"] = [
        _reference(),
        _reference(
            reference_id="ref-previous",
            filename="earlier.png",
            role="Previous result",
        ),
    ]
    payload["references"][1]["media_type"] = "PNG"
    payload["statements"] = [
        {
            "subject": "headboard shape",
            "value": "taken from the earlier render",
            "basis": "observed",
            "evidence_reference_id": "ref-previous",
        }
    ]
    with pytest.raises(ValidationError, match="previous result"):
        Phase0JobContract.model_validate(payload)


def test_revision_is_explicit_and_does_not_mutate() -> None:
    original = Phase0JobContract.model_validate(_payload())
    revised_changes = original.changes.model_copy(
        update={"allowed_changes": ["styled setting", "closer crop"]}
    )
    revised = original.revise(changes=revised_changes)

    assert original.revision == 1
    assert original.changes.allowed_changes == ["styled setting"]
    assert revised.revision == 2
    assert revised.contract_id == original.contract_id
    assert revised.changes.allowed_changes == ["styled setting", "closer crop"]

    with pytest.raises(ValidationError):
        original.revision = 2

    missing = _payload()
    del missing["revision"]
    with pytest.raises(ValidationError):
        Phase0JobContract.model_validate(missing)

    with pytest.raises(ValueError, match="next revision"):
        original.revise(revision=9)


def test_original_reference_identity_is_required() -> None:
    contract = Phase0JobContract.model_validate(_payload())
    reference = contract.references[0]
    assert reference.filename == "towel-sheet.jpg"
    assert reference.media_type == "JPG"
    assert reference.hash_algorithm == "sha256"
    assert reference.role == "Product / vendor reference"

    missing_hash = _payload()
    del missing_hash["references"][0]["content_hash"]
    with pytest.raises(ValidationError):
        Phase0JobContract.model_validate(missing_hash)

    missing_algorithm = _payload()
    del missing_algorithm["references"][0]["hash_algorithm"]
    with pytest.raises(ValidationError):
        Phase0JobContract.model_validate(missing_algorithm)

    invented_media = _payload()
    invented_media["references"][0]["media_type"] = "image/jpeg"
    with pytest.raises(ValidationError):
        Phase0JobContract.model_validate(invented_media)


def test_unknowns_and_conflicts_are_explicit() -> None:
    contract = Phase0JobContract.model_validate(_payload())
    assert contract.unknowns[0].subject == "fibre composition"
    assert contract.conflicts[0].claims == ["photographed dusty-rose", "olive swatch"]

    unresolved_count = _payload()
    unresolved_count["intent"]["selected_count"] = {"status": "unresolved", "value": None}
    Phase0JobContract.model_validate(unresolved_count)

    numbered = _payload()
    numbered["intent"]["selected_count"] = {"status": "unresolved", "value": 1}
    with pytest.raises(ValidationError, match="unresolved count"):
        Phase0JobContract.model_validate(numbered)

    one_claim = _payload()
    one_claim["conflicts"] = [{"subject": "colour", "claims": ["dusty-rose"]}]
    with pytest.raises(ValidationError):
        Phase0JobContract.model_validate(one_claim)

    as_fact = _payload()
    as_fact["statements"] = [
        {
            "subject": "colour",
            "value": "olive",
            "basis": "conflicted",
            "evidence_reference_id": "ref-towel",
        }
    ]
    with pytest.raises(ValidationError):
        Phase0JobContract.model_validate(as_fact)


def test_unsupported_and_unresolved_fields_are_rejected() -> None:
    invented = _payload()
    invented["living_room_workflow"] = "sofa-only"
    with pytest.raises(ValidationError):
        Phase0JobContract.model_validate(invented)

    model = _payload()
    model["model_id"] = "openai/gpt-4.1"
    with pytest.raises(ValidationError):
        Phase0JobContract.model_validate(model)

    placeholder = _payload()
    placeholder["item"]["category"] = "Automatic from references"
    with pytest.raises(ValidationError, match="unresolved placeholder"):
        Phase0JobContract.model_validate(placeholder)

    default_light = _payload()
    default_light["preferences"]["lighting"] = "Workflow default"
    with pytest.raises(ValidationError):
        Phase0JobContract.model_validate(default_light)

    atlas_alias = _payload()
    atlas_alias["source_condition"] = {"input_condition": "single"}
    with pytest.raises(ValidationError):
        Phase0JobContract.model_validate(atlas_alias)

    projects = _payload()
    projects["intent"]["mode"] = "Projects"
    with pytest.raises(ValidationError, match="unresolved"):
        Phase0JobContract.model_validate(projects)


def test_lifestyle_allows_omitted_or_null_other_outcome() -> None:
    payload = _payload()
    payload["intent"]["other_outcome"] = None
    contract = Phase0JobContract.model_validate(payload)
    assert contract.intent.other_outcome is None

    omitted = _payload()
    del omitted["intent"]["other_outcome"]
    omitted_contract = Phase0JobContract.model_validate(omitted)
    assert omitted_contract.intent.other_outcome is None


def test_lifestyle_treats_blank_other_outcome_as_absent() -> None:
    payload = _payload()
    payload["intent"]["other_outcome"] = ""
    contract = Phase0JobContract.model_validate(payload)
    assert contract.intent.other_outcome is None


def test_others_requires_non_empty_other_outcome() -> None:
    payload = _payload()
    payload["intent"]["requested_outcomes"] = ["Others"]
    payload["intent"]["other_outcome"] = "custom catalogue crop"
    contract = Phase0JobContract.model_validate(payload)
    assert contract.intent.other_outcome == "custom catalogue crop"

    missing = _payload()
    missing["intent"]["requested_outcomes"] = ["Others"]
    del missing["intent"]["other_outcome"]
    with pytest.raises(ValidationError, match="Others requires an explicit other_outcome"):
        Phase0JobContract.model_validate(missing)

    blank = _payload()
    blank["intent"]["requested_outcomes"] = ["Others"]
    blank["intent"]["other_outcome"] = ""
    with pytest.raises(ValidationError, match="Others requires an explicit other_outcome"):
        Phase0JobContract.model_validate(blank)
