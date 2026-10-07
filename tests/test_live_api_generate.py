"""Gated live generation proof. Skipped unless MIDAS_RUN_LIVE_PROVIDER_TEST=1."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.providers.fake_generation import FAKE_OUTPUT_HASH
from app.providers.openrouter import load_settings
from app.runtime.state import JOB_STORE

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bed-product-reference.png"
LIVE_FLAG = "MIDAS_RUN_LIVE_PROVIDER_TEST"
PLANNING_MODEL = "openai/gpt-4.1"
IMAGE_MODEL = "google/gemini-3.1-flash-image"
REFERENCE_ID = "ref-bed-product"


def _contract(content_hash: str, content_b64: str) -> dict:
    return {
        "contract_id": "contract-bed-http-generate-1",
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
def test_live_http_job_generate_openrouter_image() -> None:
    if os.getenv(LIVE_FLAG) != "1":
        pytest.skip(f"set {LIVE_FLAG}=1 to run the live OpenRouter generation proof")
    if not FIXTURE.is_file():
        pytest.fail(f"missing fixture {FIXTURE}")
    image = FIXTURE.read_bytes()
    content_hash = hashlib.sha256(image).hexdigest()
    content_b64 = base64.b64encode(image).decode("ascii")
    if not load_settings().api_key.strip():
        pytest.fail("OPENROUTER_API_KEY is empty")

    JOB_STORE.clear()
    client = TestClient(app)
    compile_artifact = None
    job_id = ""
    last_error = ""
    for _attempt in range(3):
        created = client.post(
            "/api/v1/jobs",
            json={"contract": _contract(content_hash, content_b64)},
        )
        assert created.status_code == 200, created.text
        job_id = created.json()["job_id"]
        eye = client.post(f"/api/v1/jobs/{job_id}/eye", json={"model_id": PLANNING_MODEL})
        if eye.status_code != 200:
            last_error = "eye: " + eye.text
            continue
        brain = client.post(
            f"/api/v1/jobs/{job_id}/brain", json={"model_id": PLANNING_MODEL}
        )
        if brain.status_code != 200:
            last_error = "brain: " + brain.text
            continue
        stylist = client.post(
            f"/api/v1/jobs/{job_id}/stylist", json={"model_id": PLANNING_MODEL}
        )
        if stylist.status_code != 200:
            last_error = "stylist: " + stylist.text
            continue
        compiled = client.post(
            f"/api/v1/jobs/{job_id}/compile", json={"model_id": IMAGE_MODEL}
        )
        if compiled.status_code != 200:
            last_error = "compile: " + compiled.text
            continue
        compile_artifact = compiled.json()["engine"]["compile"]
        break
    if compile_artifact is None:
        pytest.fail("live planning/compile did not succeed: " + last_error)
    assert compile_artifact["status"] == "ready"
    assert compile_artifact["model_id"] == IMAGE_MODEL
    assert compile_artifact["exact_prompt"]

    generated = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    if generated.status_code != 200:
        pytest.fail("live generation provider failed with " + generated.text)
    body = generated.json()
    receipt = body["generation"]["receipt"]
    operation = body["generation"]["operation"]
    if receipt is None or receipt.get("status") != "completed":
        pytest.fail(f"live generation did not return a completed receipt: {body}")
    assert operation["model_id"] == IMAGE_MODEL
    assert operation["exact_prompt"] == compile_artifact["exact_prompt"]
    assert operation["reference_ids"] == [
        item["reference_id"] for item in compile_artifact["references"]
    ]
    assert operation["output_format"] == compile_artifact["output_format"]
    output = receipt["output"]
    assert output["hash_algorithm"] == "sha256"
    assert output["content_hash"] != FAKE_OUTPUT_HASH
    stored_job = JOB_STORE.get(job_id)
    assert stored_job is not None
    generated_bytes = stored_job.reference_bytes.get(output["output_id"])
    assert generated_bytes
    assert hashlib.sha256(generated_bytes).hexdigest() == output["content_hash"]
    assert generated_bytes.startswith(b"\x89PNG") or generated_bytes.startswith(b"\xff\xd8")

    stored = client.get(f"/api/v1/jobs/{job_id}/generate")
    assert stored.status_code == 200
    assert stored.json()["generation"]["receipt"] == receipt
    repeat = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert repeat.status_code == 200
    assert repeat.json()["generation"]["receipt"]["provider_receipt_id"] == receipt[
        "provider_receipt_id"
    ]
