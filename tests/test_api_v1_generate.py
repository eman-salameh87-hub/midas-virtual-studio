from fastapi.testclient import TestClient

from app.api.jobs import (
    get_brain_provider,
    get_engine_compiler,
    get_eye_provider,
    get_generation_provider,
    get_stylist_provider,
)
from app.contracts.job import Phase0JobContract
from app.main import app
from app.providers.fake_brain import FakeBrainProvider
from app.providers.fake_engine import FakeEngineCompiler
from app.providers.fake_eye import FakeEyeProvider
from app.providers.fake_generation import FAKE_OUTPUT_BYTES, FakeGenerationProvider
from app.providers.fake_stylist import FakeStylistProvider
from app.runtime.artifacts import get_artifact_store
from app.runtime.state import JOB_STORE
from tests.png_bytes import PNG_B64, PNG_HASH

HASH = PNG_HASH
CALLER_MODEL = "caller-supplied-model"


def _contract() -> Phase0JobContract:
    return Phase0JobContract.model_validate(
        {
            "contract_id": "contract-towel-api-generate-1",
            "revision": 1,
            "owner_id": "owner-api-generate",
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


def _client(provider: FakeGenerationProvider | None = None) -> TestClient:
    JOB_STORE.clear()
    app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider("ready")
    app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()
    app.dependency_overrides[get_stylist_provider] = lambda: FakeStylistProvider()
    app.dependency_overrides[get_engine_compiler] = lambda: FakeEngineCompiler()
    app.dependency_overrides[get_generation_provider] = lambda: provider or FakeGenerationProvider()
    return TestClient(app)


def _seed_compiled(client: TestClient) -> str:
    contract_data = _contract().model_dump(mode="python")
    contract_data["references"][0]["content_base64"] = PNG_B64
    job_id = client.post("/api/v1/jobs", json={"contract": contract_data}).json()["job_id"]
    assert client.post(f"/api/v1/jobs/{job_id}/eye", json={}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/brain", json={}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/stylist", json={}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/compile", json={}).status_code == 200
    return job_id


def test_end_to_end_job_to_generation() -> None:
    provider = FakeGenerationProvider()
    client = _client(provider)
    job_id = _seed_compiled(client)

    res = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["stage"] == "generate"
    assert data["state"] == "ready"
    receipt = data["generation"]["receipt"]
    assert receipt["status"] == "completed"
    assert receipt["output"]["media_type"] == "PNG"
    operation = data["generation"]["operation"]
    compile_res = client.get(f"/api/v1/jobs/{job_id}/compile").json()
    compile_artifact = compile_res["engine"]["compile"]
    assert operation["exact_prompt"] == compile_artifact["exact_prompt"]
    assert operation["model_id"] == compile_artifact["model_id"]
    assert operation["reference_ids"] == [
        item["reference_id"] for item in compile_artifact["references"]
    ]
    assert operation["output_format"] == compile_artifact["output_format"]
    assert len(provider.requests) == 1
    assert data["generation"]["output_available"] is True
    assert data["generation"]["image_url"] == f"/api/v1/jobs/{job_id}/generate/image"

    get_res = client.get(f"/api/v1/jobs/{job_id}/generate")
    assert get_res.status_code == 200
    assert get_res.json()["generation"]["receipt"] == receipt
    assert get_res.json()["generation"]["output_available"] is True
    repeat = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert repeat.status_code == 200
    assert len(provider.requests) == 1
    assert client.get(f"/api/v1/jobs/{job_id}/status").json()["generation_available"] is True

    artifacts = get_artifact_store()
    job_dir = artifacts.job_dir(job_id)
    for name in (
        "job.json",
        "eye.json",
        "brain.json",
        "stylist.json",
        "compile.json",
        "generation.json",
    ):
        assert (job_dir / name).is_file(), name
    generated = artifacts.get_output(job_id, "generated.png")
    assert generated == FAKE_OUTPUT_BYTES
    image = client.get(f"/api/v1/jobs/{job_id}/generate/image")
    assert image.status_code == 200
    assert image.headers["content-type"].startswith("image/png")
    assert image.content == FAKE_OUTPUT_BYTES
    assert client.get(f"/api/v1/jobs/{job_id}/generate").status_code == 200
    assert len(provider.requests) == 1


def test_generate_requires_compile() -> None:
    client = _client()
    contract_data = _contract().model_dump(mode="python")
    contract_data["references"][0]["content_base64"] = PNG_B64
    job_id = client.post("/api/v1/jobs", json={"contract": contract_data}).json()["job_id"]
    res = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "EYE_NOT_RUN"


def test_generate_owner_and_revision_mismatch() -> None:
    client = _client()
    job_id = _seed_compiled(client)
    res = client.post(
        f"/api/v1/jobs/{job_id}/generate",
        json={},
        params={"owner_id": "wrong-owner"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "JOB_OWNER_MISMATCH"
    res = client.post(
        f"/api/v1/jobs/{job_id}/generate",
        json={},
        params={"revision": 99},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "REVISION_MISMATCH"


def test_get_generate_not_run() -> None:
    client = _client()
    job_id = _seed_compiled(client)
    res = client.get(f"/api/v1/jobs/{job_id}/generate")
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "GENERATION_NOT_RUN"
    missing = client.get(f"/api/v1/jobs/{job_id}/generate/image")
    assert missing.status_code == 409
    assert missing.json()["error"]["code"] == "GENERATION_NOT_RUN"


def test_generate_image_enforces_owner_and_revision() -> None:
    client = _client()
    job_id = _seed_compiled(client)
    assert client.post(f"/api/v1/jobs/{job_id}/generate", json={}).status_code == 200
    denied = client.get(
        f"/api/v1/jobs/{job_id}/generate/image",
        params={"owner_id": "wrong-owner"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "JOB_OWNER_MISMATCH"
    mismatch = client.get(
        f"/api/v1/jobs/{job_id}/generate/image",
        params={"revision": 99},
    )
    assert mismatch.status_code == 409
    assert mismatch.json()["error"]["code"] == "REVISION_MISMATCH"


def test_uncertain_generate_is_not_retried_via_api() -> None:
    provider = FakeGenerationProvider(mode="uncertain")
    client = _client(provider)
    job_id = _seed_compiled(client)
    first = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert first.status_code == 200
    assert first.json()["generation"]["receipt"]["status"] == "uncertain"
    assert first.json()["generation"]["output_available"] is False
    assert first.json()["generation"]["image_url"] is None
    second = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert second.status_code == 200
    assert len(provider.requests) == 1
    image = client.get(f"/api/v1/jobs/{job_id}/generate/image")
    assert image.status_code == 409
    assert image.json()["error"]["code"] == "GENERATION_IMAGE_UNAVAILABLE"
