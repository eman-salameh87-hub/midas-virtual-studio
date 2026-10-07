import json
from fastapi.testclient import TestClient

from app.api.jobs import get_brain_provider, get_eye_provider, get_stylist_provider
from app.contracts.job import Phase0JobContract
from app.main import app
from app.providers.fake_brain import FakeBrainProvider
from app.providers.fake_eye import FakeEyeProvider
from app.providers.fake_stylist import FakeStylistProvider
from app.runtime.state import JOB_STORE
from tests.png_bytes import PNG_B64, PNG_HASH

HASH = PNG_HASH
CALLER_MODEL = "caller-supplied-model"


def _contract() -> Phase0JobContract:
    return Phase0JobContract.model_validate(
        {
            "contract_id": "contract-towel-api-stylist-1",
            "revision": 1,
            "owner_id": "owner-api-stylist",
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
                    "content_hash": HASH,
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
    )


def _client() -> TestClient:
    JOB_STORE.clear()
    app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider("ready")
    app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()
    app.dependency_overrides[get_stylist_provider] = lambda: FakeStylistProvider()
    return TestClient(app)


def _seed_job(client: TestClient) -> str:
    contract_data = _contract().model_dump(mode="python")
    contract_data["references"][0]["content_base64"] = PNG_B64
    res = client.post("/api/v1/jobs", json={"contract": contract_data})
    assert res.status_code == 200, res.text
    job_id = res.json()["job_id"]

    eye_res = client.post(f"/api/v1/jobs/{job_id}/eye", json={"model_id": CALLER_MODEL})
    assert eye_res.status_code == 200, eye_res.text

    brain_res = client.post(f"/api/v1/jobs/{job_id}/brain", json={"model_id": CALLER_MODEL})
    assert brain_res.status_code == 200, brain_res.text

    return job_id


def test_post_and_get_job_stylist() -> None:
    client = _client()
    job_id = _seed_job(client)

    # POST stylist
    res = client.post(
        f"/api/v1/jobs/{job_id}/stylist",
        json={"model_id": CALLER_MODEL},
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["job_id"] == job_id
    assert data["stage"] == "stylist"
    assert data["state"] == "ready"
    assert data["stylist"]["model_id"] == CALLER_MODEL
    assert data["stylist"]["execution_status"] == "completed"
    assert data["stylist"]["plan"]["product_role"] == "hero"

    # GET stylist
    get_res = client.get(f"/api/v1/jobs/{job_id}/stylist")
    assert get_res.status_code == 200, get_res.text
    get_data = get_res.json()
    assert get_data["job_id"] == job_id
    assert get_data["stylist"]["plan"] == data["stylist"]["plan"]

    # GET status includes stylist_available: true
    status_res = client.get(f"/api/v1/jobs/{job_id}/status")
    assert status_res.status_code == 200
    assert status_res.json()["stylist_available"] is True


def test_stylist_not_found() -> None:
    client = _client()
    res = client.post("/api/v1/jobs/missing-job/stylist", json={"model_id": CALLER_MODEL})
    assert res.status_code == 404
    assert res.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_stylist_owner_mismatch() -> None:
    client = _client()
    job_id = _seed_job(client)
    res = client.post(
        f"/api/v1/jobs/{job_id}/stylist",
        json={"model_id": CALLER_MODEL},
        params={"owner_id": "wrong-owner"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "JOB_OWNER_MISMATCH"


def test_stylist_revision_mismatch() -> None:
    client = _client()
    job_id = _seed_job(client)
    res = client.post(
        f"/api/v1/jobs/{job_id}/stylist",
        json={"model_id": CALLER_MODEL},
        params={"revision": 99},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "REVISION_MISMATCH"


def test_stylist_brain_not_run() -> None:
    client = _client()
    contract_data = _contract().model_dump(mode="python")
    contract_data["references"][0]["content_base64"] = PNG_B64
    res = client.post("/api/v1/jobs", json={"contract": contract_data})
    job_id = res.json()["job_id"]
    client.post(f"/api/v1/jobs/{job_id}/eye", json={"model_id": CALLER_MODEL})

    res = client.post(f"/api/v1/jobs/{job_id}/stylist", json={"model_id": CALLER_MODEL})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "BRAIN_NOT_RUN"


def test_get_stylist_not_run() -> None:
    client = _client()
    job_id = _seed_job(client)
    res = client.get(f"/api/v1/jobs/{job_id}/stylist")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "STYLIST_NOT_RUN"


def test_stylist_empty_model_id_rejected() -> None:
    client = _client()
    job_id = _seed_job(client)
    res = client.post(f"/api/v1/jobs/{job_id}/stylist", json={"model_id": ""})
    assert res.status_code == 422
    assert res.json()["error"]["code"] == "INVALID_REQUEST"

