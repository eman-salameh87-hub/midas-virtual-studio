"""Centralized model policy, OpenAPI defaults, validation, and stage execution."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.jobs import (
    get_brain_provider,
    get_critique_provider,
    get_engine_compiler,
    get_eye_provider,
    get_generation_provider,
    get_repair_planner,
    get_stylist_provider,
)
from app.main import app
from app.providers.fake_brain import FakeBrainProvider
from app.providers.fake_critique import FakeCritiqueProvider
from app.providers.fake_engine import FakeEngineCompiler
from app.providers.fake_eye import FakeEyeProvider
from app.providers.fake_generation import FakeGenerationProvider
from app.providers.fake_repair import FakeRepairPlanner
from app.providers.fake_stylist import FakeStylistProvider
from app.runtime.model_policy import (
    DEFAULT_IMAGE_MODEL,
    DEFAULT_PLANNING_MODEL,
    allowed_models_for_stage,
    brain_model,
    critique_model,
    eye_model,
    image_model,
    stylist_model,
    validate_stage_model,
)
from app.runtime.jobs import create_job_from_intake
from app.runtime.state import JOB_STORE
from tests.png_bytes import PNG_B64, PNG_HASH

STAGE_PATHS = (
    "eye",
    "brain",
    "stylist",
    "compile",
    "generate",
    "critique",
    "repair",
)


def _contract() -> dict:
    return {
        "contract_id": "contract-model-policy-1",
        "revision": 1,
        "owner_id": "owner-model-policy",
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
        "source_condition": {"input_condition": "clean pack shot"},
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
            "protected_identity": ["towel identity"],
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


def _client(
    *,
    eye: FakeEyeProvider | None = None,
    brain: FakeBrainProvider | None = None,
    stylist: FakeStylistProvider | None = None,
    compiler: FakeEngineCompiler | None = None,
    generation: FakeGenerationProvider | None = None,
    critique: FakeCritiqueProvider | None = None,
) -> TestClient:
    JOB_STORE.clear()
    app.dependency_overrides[get_eye_provider] = lambda: eye or FakeEyeProvider("ready")
    app.dependency_overrides[get_brain_provider] = lambda: brain or FakeBrainProvider()
    app.dependency_overrides[get_stylist_provider] = lambda: stylist or FakeStylistProvider()
    app.dependency_overrides[get_engine_compiler] = lambda: compiler or FakeEngineCompiler()
    app.dependency_overrides[get_generation_provider] = (
        lambda: generation or FakeGenerationProvider()
    )
    app.dependency_overrides[get_critique_provider] = lambda: critique or FakeCritiqueProvider(
        "repair_required"
    )
    app.dependency_overrides[get_repair_planner] = lambda: FakeRepairPlanner()
    return TestClient(app)


def _create_job(client: TestClient) -> str:
    return create_job_from_intake(JOB_STORE, _contract()).job_id


def _seed(client: TestClient, *, through: str) -> str:
    job_id = _create_job(client)
    steps = (
        ("eye", f"/api/v1/jobs/{job_id}/eye"),
        ("brain", f"/api/v1/jobs/{job_id}/brain"),
        ("stylist", f"/api/v1/jobs/{job_id}/stylist"),
        ("compile", f"/api/v1/jobs/{job_id}/compile"),
        ("generate", f"/api/v1/jobs/{job_id}/generate"),
        ("critique", f"/api/v1/jobs/{job_id}/critique"),
    )
    for name, path in steps:
        if name == "generate":
            assert client.post(f"/api/v1/jobs/{job_id}/generate/approve", json={}).status_code == 200
        assert client.post(path, json={}).status_code == 200
        if name == through:
            break
    return job_id


def _request_schema(schema: dict, path: str) -> dict:
    post = schema["paths"][f"/api/v1/jobs/{{job_id}}/{path}"]["post"]
    body = post["requestBody"]["content"]["application/json"]["schema"]
    if "$ref" in body:
        ref = body["$ref"].rsplit("/", 1)[-1]
        body = schema["components"]["schemas"][ref]
    return body


def test_defaults_match_proven_models() -> None:
    assert eye_model() == DEFAULT_PLANNING_MODEL == "openai/gpt-4.1"
    assert brain_model() == DEFAULT_PLANNING_MODEL
    assert stylist_model() == DEFAULT_PLANNING_MODEL
    assert critique_model() == DEFAULT_PLANNING_MODEL
    assert image_model() == DEFAULT_IMAGE_MODEL == "google/gemini-3.1-flash-image"


def test_env_overrides_are_backend_owned(monkeypatch) -> None:
    monkeypatch.setenv("MIDAS_EYE_MODEL", "override/eye")
    monkeypatch.setenv("MIDAS_IMAGE_MODEL", "override/image")
    assert eye_model() == "override/eye"
    assert image_model() == "override/image"
    assert "override/eye" in allowed_models_for_stage("eye")
    assert "override/image" in allowed_models_for_stage("compile")


def test_openapi_stage_requests_expose_model_id_and_defaults() -> None:
    app.openapi_schema = None
    client = _client()
    schema = client.get("/openapi.json").json()

    expected_defaults = {
        "eye": "openai/gpt-4.1",
        "brain": "openai/gpt-4.1",
        "stylist": "openai/gpt-4.1",
        "compile": "google/gemini-3.1-flash-image",
        "generate": "google/gemini-3.1-flash-image",
        "critique": "openai/gpt-4.1",
        "repair": "google/gemini-3.1-flash-image",
    }

    for path in STAGE_PATHS:
        body = _request_schema(schema, path)
        properties = body.get("properties") or {}
        assert "model_id" in properties, f"model_id missing in {path}"
        prop = properties["model_id"]
        expected = expected_defaults[path]
        assert prop.get("default") == expected, f"default mismatch in {path}: {prop.get('default')} != {expected}"
        assert body.get("example") == {"model_id": expected}, f"example mismatch in {path}"


def test_openapi_shows_effective_configured_defaults(monkeypatch) -> None:
    monkeypatch.setenv("MIDAS_EYE_MODEL", "custom/planning-eye")
    monkeypatch.setenv("MIDAS_IMAGE_MODEL", "custom/image-gen")
    app.openapi_schema = None
    client = _client()
    schema = client.get("/openapi.json").json()

    eye_body = _request_schema(schema, "eye")
    assert eye_body["properties"]["model_id"]["default"] == "custom/planning-eye"
    assert eye_body["example"] == {"model_id": "custom/planning-eye"}

    compile_body = _request_schema(schema, "compile")
    assert compile_body["properties"]["model_id"]["default"] == "custom/image-gen"
    assert compile_body["example"] == {"model_id": "custom/image-gen"}
    app.openapi_schema = None


def test_explicit_model_submission_for_all_stages() -> None:
    eye_provider = FakeEyeProvider("ready")
    brain_provider = FakeBrainProvider()
    stylist_provider = FakeStylistProvider()
    compiler = FakeEngineCompiler()
    gen_provider = FakeGenerationProvider()
    critique_provider = FakeCritiqueProvider("repair_required")

    client = _client(
        eye=eye_provider,
        brain=brain_provider,
        stylist=stylist_provider,
        compiler=compiler,
        generation=gen_provider,
        critique=critique_provider,
    )

    job_id = _create_job(client)

    # 1. Eye explicit
    res = client.post(f"/api/v1/jobs/{job_id}/eye", json={"model_id": "openai/gpt-4.1"})
    assert res.status_code == 200, res.text
    assert eye_provider.requests[0].model_id == "openai/gpt-4.1"
    assert JOB_STORE.get(job_id).eye_model_id == "openai/gpt-4.1"

    # 2. Brain explicit
    res = client.post(f"/api/v1/jobs/{job_id}/brain", json={"model_id": "openai/gpt-4.1"})
    assert res.status_code == 200, res.text
    assert brain_provider.requests[0].model_id == "openai/gpt-4.1"
    assert res.json()["brain"]["model_id"] == "openai/gpt-4.1"

    # 3. Stylist explicit
    res = client.post(f"/api/v1/jobs/{job_id}/stylist", json={"model_id": "openai/gpt-4.1"})
    assert res.status_code == 200, res.text
    assert stylist_provider.requests[0].model_id == "openai/gpt-4.1"
    assert res.json()["stylist"]["model_id"] == "openai/gpt-4.1"

    # 4. Compile explicit
    res = client.post(f"/api/v1/jobs/{job_id}/compile", json={"model_id": "google/gemini-3.1-flash-image"})
    assert res.status_code == 200, res.text
    assert compiler.requests[0].model_id == "google/gemini-3.1-flash-image"
    assert res.json()["engine"]["model_id"] == "google/gemini-3.1-flash-image"
    assert res.json()["engine"]["compile"]["model_id"] == "google/gemini-3.1-flash-image"

    # 5. Generate explicit
    assert client.post(f"/api/v1/jobs/{job_id}/generate/approve", json={}).status_code == 200
    res = client.post(f"/api/v1/jobs/{job_id}/generate", json={"model_id": "google/gemini-3.1-flash-image"})
    assert res.status_code == 200, res.text
    assert res.json()["generation"]["operation"]["model_id"] == "google/gemini-3.1-flash-image"
    assert gen_provider.requests[0].operation.model_id == "google/gemini-3.1-flash-image"

    # 6. Critique explicit
    res = client.post(f"/api/v1/jobs/{job_id}/critique", json={"model_id": "openai/gpt-4.1"})
    assert res.status_code == 200, res.text
    assert critique_provider.requests[0].model_id == "openai/gpt-4.1"
    assert res.json()["critique"]["model_id"] == "openai/gpt-4.1"

    # 7. Repair explicit
    seed_dispatches = len(gen_provider.requests)
    res = client.post(f"/api/v1/jobs/{job_id}/repair", json={"model_id": "google/gemini-3.1-flash-image"})
    assert res.status_code == 200, res.text
    assert res.json()["repair"]["plan"]["operation"]["model_id"] == "google/gemini-3.1-flash-image"
    assert gen_provider.requests[seed_dispatches].operation.model_id == "google/gemini-3.1-flash-image"


def test_unsupported_model_rejected_422() -> None:
    client = _client()
    job_id = _create_job(client)

    # Eye rejects random model
    res = client.post(f"/api/v1/jobs/{job_id}/eye", json={"model_id": "some-random-model"})
    assert res.status_code == 422
    assert "not configured or allowed" in res.json()["error"]["message"]

    # Eye rejects image model
    res = client.post(f"/api/v1/jobs/{job_id}/eye", json={"model_id": "google/gemini-3.1-flash-image"})
    assert res.status_code == 422

    # Execute eye to proceed
    assert client.post(f"/api/v1/jobs/{job_id}/eye", json={}).status_code == 200

    # Brain rejects random model
    res = client.post(f"/api/v1/jobs/{job_id}/brain", json={"model_id": "some-random-model"})
    assert res.status_code == 422

    # Execute brain
    assert client.post(f"/api/v1/jobs/{job_id}/brain", json={}).status_code == 200

    # Stylist rejects random model
    res = client.post(f"/api/v1/jobs/{job_id}/stylist", json={"model_id": "some-random-model"})
    assert res.status_code == 422

    # Execute stylist
    assert client.post(f"/api/v1/jobs/{job_id}/stylist", json={}).status_code == 200

    # Compile rejects planning model
    res = client.post(f"/api/v1/jobs/{job_id}/compile", json={"model_id": "openai/gpt-4.1"})
    assert res.status_code == 422

    # Compile rejects random model
    res = client.post(f"/api/v1/jobs/{job_id}/compile", json={"model_id": "some-random-model"})
    assert res.status_code == 422


def test_generate_requires_matching_compiled_image_model(monkeypatch) -> None:
    monkeypatch.setenv("MIDAS_ALLOWED_MODELS", "google/gemini-3.1-flash-image,custom/image-v2")
    client = _client()
    job_id = _seed(client, through="stylist")

    # Compile with default image model
    res = client.post(f"/api/v1/jobs/{job_id}/compile", json={"model_id": "google/gemini-3.1-flash-image"})
    assert res.status_code == 200

    # Generate with a different (otherwise allowed) image model -> rejected 422
    res = client.post(f"/api/v1/jobs/{job_id}/generate", json={"model_id": "custom/image-v2"})
    assert res.status_code == 422
    assert "must match compiled image model" in res.json()["error"]["message"]
    assert res.json()["error"]["code"] == "INVALID_REQUEST"

    # Generate with matching compiled model -> succeeds
    assert client.post(f"/api/v1/jobs/{job_id}/generate/approve", json={}).status_code == 200
    res = client.post(f"/api/v1/jobs/{job_id}/generate", json={"model_id": "google/gemini-3.1-flash-image"})
    assert res.status_code == 200


def test_repair_requires_matching_compiled_image_model(monkeypatch) -> None:
    monkeypatch.setenv("MIDAS_ALLOWED_MODELS", "google/gemini-3.1-flash-image,custom/image-v2")
    client = _client()
    job_id = _seed(client, through="critique")

    # Repair with a different image model -> rejected 422
    res = client.post(f"/api/v1/jobs/{job_id}/repair", json={"model_id": "custom/image-v2"})
    assert res.status_code == 422
    assert "must match compiled image model" in res.json()["error"]["message"]
    assert res.json()["error"]["code"] == "INVALID_REQUEST"

    # Repair with matching compiled model -> succeeds
    res = client.post(f"/api/v1/jobs/{job_id}/repair", json={"model_id": "google/gemini-3.1-flash-image"})
    assert res.status_code == 200


