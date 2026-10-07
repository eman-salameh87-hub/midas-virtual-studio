"""Gated HTTP → OpenRouter Eye proof. Skipped unless MIDAS_RUN_LIVE_PROVIDER_TEST=1."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.providers.openrouter import load_settings

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bed-product-reference.png"
LIVE_FLAG = "MIDAS_RUN_LIVE_PROVIDER_TEST"
CALLER_MODEL = "openai/gpt-4.1"
REFERENCE_ID = "ref-bed-product"


def _contract(content_hash: str, content_b64: str) -> dict:
    return {
        "contract_id": "contract-bed-http-proof-1",
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
                "content_base64": content_b64,
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


@pytest.mark.live_provider
def test_live_http_job_eye_openrouter() -> None:
    if os.getenv(LIVE_FLAG) != "1":
        pytest.skip(f"set {LIVE_FLAG}=1 to run the live OpenRouter Eye proof")
    if not FIXTURE.is_file():
        pytest.fail(f"missing fixture {FIXTURE}")
    image = FIXTURE.read_bytes()
    content_hash = hashlib.sha256(image).hexdigest()
    content_b64 = base64.b64encode(image).decode("ascii")
    if not load_settings().api_key.strip():
        pytest.fail("OPENROUTER_API_KEY is empty")

    client = TestClient(app)
    created = client.post(
        "/api/v1/jobs",
        json={"contract": _contract(content_hash, content_b64)},
    )
    assert created.status_code == 200, created.text
    job_id = created.json()["job_id"]

    executed = client.post(
        f"/api/v1/jobs/{job_id}/eye",
        json={},
    )
    assert executed.status_code == 200, executed.text
    body = executed.json()
    assert body["job_id"] == job_id
    assert body["observation"]["contract_id"] == "contract-bed-http-proof-1"
    assert body["observation"]["items"]
    assert "content_base64" not in executed.text

    stored = client.get(f"/api/v1/jobs/{job_id}")
    assert stored.status_code == 200
    assert stored.json()["eye"] is not None
    assert stored.json()["eye"]["observation"] == body["observation"]
    assert "content_base64" not in stored.text

    eye = client.get(f"/api/v1/jobs/{job_id}/eye")
    assert eye.status_code == 200
    assert eye.json()["observation"] == body["observation"]
