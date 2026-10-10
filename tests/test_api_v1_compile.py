from fastapi.testclient import TestClient

from app.api.jobs import (
    get_brain_provider,
    get_engine_compiler,
    get_eye_provider,
    get_stylist_provider,
)
from app.contracts.job import Phase0JobContract
from app.main import app
from app.providers.fake_brain import FakeBrainProvider
from app.providers.fake_engine import FakeEngineCompiler
from app.providers.fake_eye import FakeEyeProvider
from app.providers.fake_stylist import FakeStylistProvider
from app.runtime.jobs import create_job_from_intake
from app.runtime.model_policy import image_model
from app.runtime.state import JOB_STORE
from tests.png_bytes import PNG_B64, PNG_HASH

HASH = PNG_HASH
CALLER_MODEL = "caller-supplied-model"


def _contract() -> Phase0JobContract:
    return Phase0JobContract.model_validate(
        {
            "contract_id": "contract-towel-api-compile-1",
            "revision": 1,
            "owner_id": "owner-api-compile",
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


def _client(compiler: FakeEngineCompiler | None = None) -> TestClient:
    JOB_STORE.clear()
    app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider("ready")
    app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()
    app.dependency_overrides[get_stylist_provider] = lambda: FakeStylistProvider()
    app.dependency_overrides[get_engine_compiler] = lambda: compiler or FakeEngineCompiler()
    return TestClient(app)


def _seed_styled(client: TestClient) -> str:
    contract_data = _contract().model_dump(mode="python")
    contract_data["references"][0]["content_base64"] = PNG_B64
    job_id = create_job_from_intake(JOB_STORE, contract_data).job_id
    assert client.post(f"/api/v1/jobs/{job_id}/eye", json={}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/brain", json={}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/stylist", json={}).status_code == 200
    return job_id


def test_post_and_get_job_compile() -> None:
    compiler = FakeEngineCompiler()
    client = _client(compiler)
    job_id = _seed_styled(client)

    res = client.post(f"/api/v1/jobs/{job_id}/compile", json={})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["job_id"] == job_id
    assert data["stage"] == "compile"
    assert data["state"] == "ready"
    assert data["engine"]["model_id"] == image_model()
    assert data["engine"]["execution_status"] == "completed"
    assert data["engine"]["compile"]["status"] == "ready"
    assert data["engine"]["compile"]["exact_prompt"]
    assert len(compiler.requests) == 1

    get_res = client.get(f"/api/v1/jobs/{job_id}/compile")
    assert get_res.status_code == 200, get_res.text
    assert get_res.json()["engine"]["compile"] == data["engine"]["compile"]
    assert len(compiler.requests) == 1

    status_res = client.get(f"/api/v1/jobs/{job_id}/status")
    assert status_res.status_code == 200
    assert status_res.json()["compile_available"] is True

    job_res = client.get(f"/api/v1/jobs/{job_id}")
    assert job_res.status_code == 200
    assert job_res.json()["compile_available"] is True
    assert job_res.json()["engine"]["compile"]["contract_id"] == "contract-towel-api-compile-1"


def test_compile_owner_and_revision_mismatch() -> None:
    client = _client()
    job_id = _seed_styled(client)
    res = client.post(
        f"/api/v1/jobs/{job_id}/compile",
        json={},
        params={"owner_id": "wrong-owner"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "JOB_OWNER_MISMATCH"

    res = client.post(
        f"/api/v1/jobs/{job_id}/compile",
        json={},
        params={"revision": 99},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "REVISION_MISMATCH"


def test_compile_requires_prior_stages() -> None:
    client = _client()
    contract_data = _contract().model_dump(mode="python")
    contract_data["references"][0]["content_base64"] = PNG_B64
    job_id = create_job_from_intake(JOB_STORE, contract_data).job_id

    res = client.post(f"/api/v1/jobs/{job_id}/compile", json={})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "EYE_NOT_RUN"

    client.post(f"/api/v1/jobs/{job_id}/eye", json={})
    res = client.post(f"/api/v1/jobs/{job_id}/compile", json={})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "BRAIN_NOT_RUN"

    client.post(f"/api/v1/jobs/{job_id}/brain", json={})
    res = client.post(f"/api/v1/jobs/{job_id}/compile", json={})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "STYLIST_NOT_RUN"


def test_get_compile_not_run() -> None:
    client = _client()
    contract_data = _contract().model_dump(mode="python")
    contract_data["references"][0]["content_base64"] = PNG_B64
    job_id = create_job_from_intake(JOB_STORE, contract_data).job_id
    assert client.post(f"/api/v1/jobs/{job_id}/eye", json={}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/brain", json={}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/stylist", json={}).status_code == 200
    res = client.get(f"/api/v1/jobs/{job_id}/compile")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "ENGINE_NOT_RUN"


def test_stylist_hold_blocks_compile_api() -> None:
    JOB_STORE.clear()
    app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider("ready")
    app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()
    app.dependency_overrides[get_stylist_provider] = lambda: FakeStylistProvider(violation="hold")
    app.dependency_overrides[get_engine_compiler] = lambda: FakeEngineCompiler()
    client = TestClient(app)

    contract_data = _contract().model_dump(mode="python")
    contract_data["references"][0]["content_base64"] = PNG_B64
    job_id = create_job_from_intake(JOB_STORE, contract_data).job_id
    client.post(f"/api/v1/jobs/{job_id}/eye", json={})
    client.post(f"/api/v1/jobs/{job_id}/brain", json={})
    stylist = client.post(f"/api/v1/jobs/{job_id}/stylist", json={})
    assert stylist.status_code == 200
    assert stylist.json()["state"] == "hold"

    res = client.post(f"/api/v1/jobs/{job_id}/compile", json={})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "ENGINE_NOT_READY"
