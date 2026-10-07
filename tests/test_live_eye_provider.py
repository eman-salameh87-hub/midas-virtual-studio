"""Live OpenRouter Eye provider-proof. Skipped unless MIDAS_RUN_LIVE_PROVIDER_TEST=1."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from app.contracts.eye import EyeContract
from app.contracts.job import Phase0JobContract
from app.providers.living_room_eye_observation import LivingRoomEyeMappingError
from app.providers.openrouter import OpenRouterEyeProvider, OpenRouterSettings, load_settings
from app.runtime.job import execute_eye_job

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "bed-product-reference.png"
)
LIVE_FLAG = "MIDAS_RUN_LIVE_PROVIDER_TEST"
CALLER_MODEL = "openai/gpt-4.1"
REFERENCE_ID = "ref-bed-product"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _contract(content_hash: str) -> Phase0JobContract:
    return Phase0JobContract.model_validate(
        {
            "contract_id": "contract-bed-provider-proof-1",
            "revision": 1,
            "owner_id": "owner-provider-proof",
            "intent": {
                "mode": "Manual",
                "job_type": "New Project",
                "job_option": "One by one (same department)",
                "requested_outcomes": ["Lifestyle"],
                "other_outcome": None,
                "requested_pieces": ["bed"],
                "excluded_pieces": [],
                "selected_count": {"status": "declared", "value": 1},
            },
            "item": {
                "department": "Home Furniture",
                "category": "Bedroom",
                "subcategory": "Beds",
                "product_role": "hero",
            },
            "source_condition": {"input_condition": "clean pack shot"},
            "references": [
                {
                    "reference_id": REFERENCE_ID,
                    "filename": "bed-product-reference.png",
                    "media_type": "PNG",
                    "hash_algorithm": "sha256",
                    "content_hash": content_hash,
                    "role": "Product / vendor reference",
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
                "protected_identity": ["bed identity"],
                "room_locks": [],
                "creative_variables": [],
            },
            "preferences": {
                "lighting": "Soft daylight",
                "wall": "White",
                "floor": "Light oak",
                "plants": False,
                "human": False,
                "mood": "Calm & natural",
            },
            "statements": [],
            "unknowns": [],
            "conflicts": [],
        }
    )


@pytest.mark.live_provider
def test_live_openrouter_eye_provider_proof() -> None:
    if os.getenv(LIVE_FLAG) != "1":
        pytest.skip(f"set {LIVE_FLAG}=1 to run the live OpenRouter Eye proof")
    if not FIXTURE.is_file():
        pytest.fail(f"missing fixture {FIXTURE}")
    image = FIXTURE.read_bytes()
    content_hash = _sha256(image)
    contract = _contract(content_hash)
    loaded = load_settings()
    settings = OpenRouterSettings(
        api_key=loaded.api_key,
        base_url=loaded.base_url,
        timeout_seconds=max(loaded.timeout_seconds, 120),
    )
    provider = OpenRouterEyeProvider(
        settings,
        {REFERENCE_ID: image},
    )
    try:
        result = execute_eye_job(
            contract=contract,
            reference_ids=[REFERENCE_ID],
            model_id=CALLER_MODEL,
            messages=[],
            provider=provider,
        )
    except LivingRoomEyeMappingError as exc:
        _print_report(provider, content_hash, mapped=False)
        pytest.fail(
            "OpenRouter returned JSON that could not map to EyeObservation: "
            + "; ".join(exc.mismatches)
        )
    except Exception:
        _print_report(provider, content_hash, mapped=False)
        raise

    _print_report(provider, content_hash, mapped=True)
    record = provider.last_call
    assert record.http_status == 200
    assert result.contract_id == "contract-bed-provider-proof-1"
    assert result.revision == 1
    assert result.observation.contract_id == result.contract_id
    assert result.observation.revision == result.revision
    assert result.observation.items[0].evidence_reference_id == REFERENCE_ID
    assert result.observation.items[0].content_hash == content_hash
    EyeContract(eye_input=result.eye_input, observation=result.observation)


def _print_report(
    provider: OpenRouterEyeProvider,
    content_hash: str,
    *,
    mapped: bool,
) -> None:
    record = provider.last_call
    report = {
        "http_status": record.http_status,
        "response_id": record.response_id,
        "request_id": record.request_id,
        "model": record.model,
        "error_message": record.error_message,
        "historical_json_keys": record.raw_keys,
        "historical_json": record.parsed_payload,
        "message_preview": record.message_preview,
        "mapping_mismatches": record.mapping_mismatches,
        "mapped_to_eye_observation": mapped,
        "fixture_sha256": content_hash,
        "api_key_present": bool(provider.settings.api_key),
    }
    print("LIVE_EYE_PROVIDER_PROOF " + json.dumps(report, indent=2))
