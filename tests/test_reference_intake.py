import pytest
from pydantic import ValidationError

from app.contracts.job import Phase0JobContract
from app.runtime.references import decode_content_base64, freeze_intake_payload
from tests.png_bytes import PNG_1X1, PNG_B64, PNG_HASH


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
            "excluded_pieces": [],
            "selected_count": {"status": "declared", "value": 1},
        },
        "item": {
            "department": "Accessories",
            "category": "Bathroom",
            "subcategory": "Towels",
            "product_role": "hero",
        },
        "source_condition": {"input_condition": "annotated multi-view sheet"},
        "references": [
            {
                "reference_id": "ref-towel",
                "filename": "pixel.png",
                "media_type": "PNG",
                "hash_algorithm": "sha256",
                "content_hash": PNG_HASH,
                "role": "Product / vendor reference",
                "content_base64": PNG_B64,
            }
        ],
        "outputs": {
            "views": ["Wide view"],
            "image_proportions": "Square · 1:1",
            "resolution": "2K",
            "package_members": ["lifestyle"],
        },
        "changes": {
            "policy_mode": "fidelity-locked",
            "allowed_changes": ["styled setting"],
            "protected_identity": ["towel count"],
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
        "statements": [],
        "unknowns": [],
        "conflicts": [],
    }


def test_decode_content_base64() -> None:
    assert decode_content_base64(PNG_B64) == PNG_1X1
    assert decode_content_base64(PNG_B64 + "\n") == PNG_1X1
    with pytest.raises(ValueError, match="valid base64"):
        decode_content_base64("!!!!")


def test_freeze_keeps_identity_contract_and_stores_bytes() -> None:
    contract, stored = freeze_intake_payload(_payload())
    assert isinstance(contract, Phase0JobContract)
    assert "content_base64" not in contract.references[0].model_dump()
    assert stored["ref-towel"] == PNG_1X1
    assert contract.references[0].content_hash == PNG_HASH
    assert contract.references[0].role == "Product / vendor reference"


def test_freeze_computes_hash_when_content_hash_is_missing() -> None:
    payload = _payload()
    del payload["references"][0]["content_hash"]
    contract, stored = freeze_intake_payload(payload)
    assert stored["ref-towel"] == PNG_1X1
    assert contract.references[0].content_hash == PNG_HASH
    assert contract.references[0].hash_algorithm == "sha256"


def test_freeze_computes_hash_when_content_hash_is_blank() -> None:
    payload = _payload()
    payload["references"][0]["content_hash"] = "   "
    contract, stored = freeze_intake_payload(payload)
    assert stored["ref-towel"] == PNG_1X1
    assert contract.references[0].content_hash == PNG_HASH


def test_freeze_rejects_mismatched_content_hash() -> None:
    payload = _payload()
    payload["references"][0]["content_hash"] = "ab" * 32
    with pytest.raises(ValueError, match="content_hash"):
        freeze_intake_payload(payload)


def test_freeze_rejects_image_without_bytes() -> None:
    payload = _payload()
    del payload["references"][0]["content_base64"]
    with pytest.raises(ValueError, match="content_base64"):
        freeze_intake_payload(payload)


def test_canonical_contract_still_rejects_content_base64() -> None:
    payload = _payload()
    with pytest.raises(ValidationError):
        Phase0JobContract.model_validate(payload)
