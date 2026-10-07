import pytest
from fastapi.testclient import TestClient

from app.contracts.job import Phase0JobContract
from app.main import app
from app.runtime.jobs import BrainNotRunError, EyeNotRunError, load_brain_input, load_stylist_input
from app.runtime.state import JOB_STORE
from tests.png_bytes import PNG_B64, PNG_HASH


CALLER_MODEL = "caller-supplied-model"


def _contract(owner_id: str = "owner-1", revision: int = 1) -> Phase0JobContract:
    return Phase0JobContract.model_validate(
        {
            "contract_id": "contract-towel-1",
            "revision": revision,
            "owner_id": owner_id,
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


def _intake(owner_id: str = "owner-1") -> dict:
    payload = _contract(owner_id=owner_id).model_dump(mode="json")
    payload["references"][0]["content_base64"] = PNG_B64
    return payload


def _client() -> TestClient:
    return TestClient(app)


def test_job_creation_creates_job_state() -> None:
    response = _client().post("/api/v1/jobs", json={"contract": _intake()})
    assert response.status_code == 200
    job_id = response.json()["job_id"]
    assert response.json()["owner_id"] == "owner-1"
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.owner_id == "owner-1"
    assert stored.contract.contract_id == "contract-towel-1"
    assert stored.revision == 1
    assert stored.observation is None
    assert stored.events[0].kind == "job_created"


def test_eye_execution_persists_observation_on_job_state() -> None:
    client = _client()
    created = client.post("/api/v1/jobs", json={"contract": _intake()})
    job_id = created.json()["job_id"]
    posted = client.post(
        f"/api/v1/jobs/{job_id}/eye",
        json={"model_id": CALLER_MODEL},
    )
    assert posted.status_code == 200
    posted_observation = posted.json()["observation"]

    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.observation is not None
    assert stored.observation.model_dump(mode="json") == posted_observation
    assert stored.observation.contract_id == stored.contract.contract_id
    assert stored.observation.revision == stored.revision
    assert stored.events[-1].kind == "eye_persisted"


def test_get_eye_returns_persisted_observation() -> None:
    client = _client()
    job_id = client.post("/api/v1/jobs", json={"contract": _intake()}).json()["job_id"]
    client.post(f"/api/v1/jobs/{job_id}/eye", json={"model_id": CALLER_MODEL})
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    persisted = stored.observation
    assert persisted is not None

    response = client.get(f"/api/v1/jobs/{job_id}/eye")
    assert response.status_code == 200
    assert response.json()["observation"] == persisted.model_dump(mode="json")


def test_job_state_read_recovers_observation_without_eye_return_value() -> None:
    client = _client()
    job_id = client.post("/api/v1/jobs", json={"contract": _intake()}).json()["job_id"]
    client.post(f"/api/v1/jobs/{job_id}/eye", json={"model_id": CALLER_MODEL})

    recovered = JOB_STORE.get(job_id)
    assert recovered is not None
    assert recovered.observation is not None
    assert recovered.observation.revision == 1

    job = client.get(f"/api/v1/jobs/{job_id}")
    assert job.json()["eye_available"] is True
    assert job.json()["brain_available"] is False
    assert job.json()["eye"]["observation"] == recovered.observation.model_dump(mode="json")


def test_load_brain_input_returns_contract_and_observation() -> None:
    client = _client()
    job_id = client.post("/api/v1/jobs", json={"contract": _intake()}).json()["job_id"]
    client.post(f"/api/v1/jobs/{job_id}/eye", json={"model_id": CALLER_MODEL})

    loaded = load_brain_input(JOB_STORE, job_id)
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert loaded.job_id == job_id
    assert loaded.contract == stored.contract
    assert loaded.observation == stored.observation
    assert loaded.contract.revision == stored.revision
    assert loaded.evidence[0].reference_id == "ref-towel"


def test_load_brain_input_fails_when_eye_is_absent() -> None:
    client = _client()
    job_id = client.post("/api/v1/jobs", json={"contract": _intake()}).json()["job_id"]
    with pytest.raises(EyeNotRunError):
        load_brain_input(JOB_STORE, job_id)


def test_wrong_owner_cannot_read_eye_observation() -> None:
    client = _client()
    first = client.post("/api/v1/jobs", json={"contract": _intake("owner-1")})
    job_id = first.json()["job_id"]
    client.post(f"/api/v1/jobs/{job_id}/eye", json={"model_id": CALLER_MODEL})

    denied = client.get(f"/api/v1/jobs/{job_id}/eye", params={"owner_id": "owner-2"})
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "JOB_OWNER_MISMATCH"

    allowed = client.get(f"/api/v1/jobs/{job_id}/eye", params={"owner_id": "owner-1"})
    assert allowed.status_code == 200


def test_wrong_job_cannot_read_another_observation() -> None:
    client = _client()
    first = client.post("/api/v1/jobs", json={"contract": _intake("owner-1")})
    second = client.post("/api/v1/jobs", json={"contract": _intake("owner-2")})
    job_a = first.json()["job_id"]
    job_b = second.json()["job_id"]
    client.post(f"/api/v1/jobs/{job_a}/eye", json={"model_id": CALLER_MODEL})

    missing = client.get(f"/api/v1/jobs/{job_b}/eye")
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "EYE_NOT_RUN"

    unknown = client.get("/api/v1/jobs/not-this-job/eye")
    assert unknown.status_code == 404


def test_revision_binding_is_preserved() -> None:
    client = _client()
    job_id = client.post("/api/v1/jobs", json={"contract": _intake()}).json()["job_id"]
    client.post(f"/api/v1/jobs/{job_id}/eye", json={"model_id": CALLER_MODEL})

    mismatch = client.get(f"/api/v1/jobs/{job_id}/eye", params={"revision": 9})
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "REVISION_MISMATCH"

    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.observation is not None
    assert stored.observation.revision == stored.contract.revision == 1
    assert stored.observation.contract_id == stored.contract.contract_id


def test_load_stylist_input_returns_contract_observation_and_brain() -> None:
    client = _client()
    job_id = client.post("/api/v1/jobs", json={"contract": _intake()}).json()["job_id"]
    client.post(f"/api/v1/jobs/{job_id}/eye", json={"model_id": CALLER_MODEL})
    client.post(f"/api/v1/jobs/{job_id}/brain", json={"model_id": CALLER_MODEL})

    loaded = load_stylist_input(JOB_STORE, job_id)
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.brain is not None
    assert loaded.job_id == job_id
    assert loaded.contract == stored.contract
    assert loaded.observation == stored.observation
    assert loaded.brain_plan == stored.brain.result
    assert loaded.contract.revision == stored.revision


def test_load_stylist_input_fails_when_brain_is_absent() -> None:
    client = _client()
    job_id = client.post("/api/v1/jobs", json={"contract": _intake()}).json()["job_id"]
    client.post(f"/api/v1/jobs/{job_id}/eye", json={"model_id": CALLER_MODEL})
    with pytest.raises(BrainNotRunError):
        load_stylist_input(JOB_STORE, job_id)

