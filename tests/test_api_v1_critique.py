from fastapi.testclient import TestClient

from app.api.jobs import (
    get_brain_provider,
    get_critique_provider,
    get_engine_compiler,
    get_eye_provider,
    get_generation_provider,
    get_stylist_provider,
)
from app.main import app
from app.providers.fake_brain import FakeBrainProvider
from app.providers.fake_critique import FakeCritiqueProvider
from app.providers.fake_engine import FakeEngineCompiler
from app.providers.fake_eye import FakeEyeProvider
from app.providers.fake_generation import FakeGenerationProvider
from app.providers.fake_stylist import FakeStylistProvider
from app.runtime.artifacts import get_artifact_store
from app.runtime.state import JOB_STORE
from tests.png_bytes import PNG_B64, PNG_HASH

HASH = PNG_HASH
CALLER_MODEL = "caller-supplied-model"


def _contract() -> dict:
    return {
        "contract_id": "contract-towel-api-critique-1",
        "revision": 1,
        "owner_id": "owner-api-critique",
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


def _client(critique: FakeCritiqueProvider | None = None) -> TestClient:
    JOB_STORE.clear()
    app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider("ready")
    app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()
    app.dependency_overrides[get_stylist_provider] = lambda: FakeStylistProvider()
    app.dependency_overrides[get_engine_compiler] = lambda: FakeEngineCompiler()
    app.dependency_overrides[get_generation_provider] = lambda: FakeGenerationProvider()
    app.dependency_overrides[get_critique_provider] = lambda: critique or FakeCritiqueProvider()
    return TestClient(app)


def _seed_generated(client: TestClient) -> str:
    job_id = client.post("/api/v1/jobs", json={"contract": _contract()}).json()["job_id"]
    assert client.post(f"/api/v1/jobs/{job_id}/eye", json={"model_id": CALLER_MODEL}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/brain", json={"model_id": CALLER_MODEL}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/stylist", json={"model_id": CALLER_MODEL}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/compile", json={"model_id": CALLER_MODEL}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/generate", json={}).status_code == 200
    return job_id


def test_end_to_end_critique_and_get_does_not_rerun() -> None:
    provider = FakeCritiqueProvider()
    client = _client(provider)
    job_id = _seed_generated(client)

    res = client.post(
        f"/api/v1/jobs/{job_id}/critique", json={"model_id": CALLER_MODEL}
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["stage"] == "critique"
    assessment = body["critique"]["assessment"]
    assert assessment["overall_result"] == "pass"
    assert len(assessment["findings"]) >= 8
    assert len(provider.requests) == 1

    stored = get_artifact_store().get_artifact(job_id, "critique.json")
    assert stored is not None

    get_res = client.get(f"/api/v1/jobs/{job_id}/critique")
    assert get_res.status_code == 200
    assert get_res.json()["critique"]["assessment"] == assessment
    assert len(provider.requests) == 1


def test_get_critique_not_run() -> None:
    client = _client()
    job_id = _seed_generated(client)
    res = client.get(f"/api/v1/jobs/{job_id}/critique")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CRITIQUE_NOT_RUN"


def test_critique_requires_generation() -> None:
    client = _client()
    job_id = client.post("/api/v1/jobs", json={"contract": _contract()}).json()["job_id"]
    res = client.post(
        f"/api/v1/jobs/{job_id}/critique", json={"model_id": CALLER_MODEL}
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "EYE_NOT_RUN"


def test_critique_owner_and_revision_mismatch() -> None:
    client = _client()
    job_id = _seed_generated(client)
    res = client.post(
        f"/api/v1/jobs/{job_id}/critique",
        json={"model_id": CALLER_MODEL},
        params={"owner_id": "wrong-owner"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "JOB_OWNER_MISMATCH"
    res = client.post(
        f"/api/v1/jobs/{job_id}/critique",
        json={"model_id": CALLER_MODEL},
        params={"revision": 99},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "REVISION_MISMATCH"


def test_critique_provider_failure_is_502() -> None:
    client = _client(FakeCritiqueProvider("wrong_job"))
    job_id = _seed_generated(client)
    res = client.post(
        f"/api/v1/jobs/{job_id}/critique", json={"model_id": CALLER_MODEL}
    )
    assert res.status_code == 502
    assert res.json()["error"]["code"] == "PROVIDER_FAILURE"


def test_uncertain_generation_blocks_critique() -> None:
    JOB_STORE.clear()
    app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider("ready")
    app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()
    app.dependency_overrides[get_stylist_provider] = lambda: FakeStylistProvider()
    app.dependency_overrides[get_engine_compiler] = lambda: FakeEngineCompiler()
    app.dependency_overrides[get_generation_provider] = lambda: FakeGenerationProvider(
        mode="uncertain"
    )
    app.dependency_overrides[get_critique_provider] = lambda: FakeCritiqueProvider()
    client = TestClient(app)
    job_id = client.post("/api/v1/jobs", json={"contract": _contract()}).json()["job_id"]
    assert client.post(f"/api/v1/jobs/{job_id}/eye", json={"model_id": CALLER_MODEL}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/brain", json={"model_id": CALLER_MODEL}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/stylist", json={"model_id": CALLER_MODEL}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/compile", json={"model_id": CALLER_MODEL}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/generate", json={}).status_code == 200
    res = client.post(
        f"/api/v1/jobs/{job_id}/critique", json={"model_id": CALLER_MODEL}
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "GENERATION_NOT_READY"


def test_openapi_documents_critique() -> None:
    spec = _client().get("/openapi.json").json()
    assert "/api/v1/jobs/{job_id}/critique" in spec["paths"]
    schemas = spec["components"]["schemas"]
    assert "CritiqueAssessment" in schemas
    assert "ExecuteCritiqueRequest" in schemas
    assert "GetCritiqueResponse" in schemas
