import json

from fastapi.testclient import TestClient

from app.api.jobs import get_eye_provider
from app.contracts.job import Phase0JobContract
from app.main import GET_DOC_PATHS, POST_DOC_PATHS, app
from app.providers.fake_eye import FakeEyeProvider, observation_for
from app.runtime.jobs import create_job_from_intake
from app.runtime.model_policy import eye_model
from app.runtime.state import JOB_STORE
from app.stages.eye import build_eye_input
from tests.png_bytes import PNG_1X1, PNG_B64, PNG_HASH

HASH = PNG_HASH
CALLER_MODEL = "caller-supplied-model"


def _contract() -> Phase0JobContract:
    return Phase0JobContract.model_validate(
        {
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


def _intake() -> dict:
    payload = _contract().model_dump(mode="json")
    payload["references"][0]["content_base64"] = PNG_B64
    return payload


def _client() -> TestClient:
    return TestClient(app)


def _create_job(client: TestClient) -> str:
    response = client.post("/api/v1/jobs", json={"contract": _intake()})
    assert response.status_code == 200, response.text
    return response.json()["job_id"]


def _freeze_job() -> str:
    return create_job_from_intake(JOB_STORE, _intake()).job_id


def test_post_jobs_creates_a_job() -> None:
    response = _client().post("/api/v1/jobs", json={"contract": _intake()})

    assert response.status_code == 200
    body = response.json()
    assert body["contract_id"] == "contract-towel-1"
    assert body["revision"] == 1
    assert body["stage"] == "intake"
    assert body["state"] == "accepted"
    assert body["status"] == "accepted"
    assert body["job_id"]
    assert "observation" not in body
    stored = JOB_STORE.get(body["job_id"])
    assert stored is not None
    assert stored.reference_bytes["ref-towel"] == PNG_1X1
    assert stored.contract.references[0].content_hash == HASH


def test_get_job_returns_the_job() -> None:
    from app.runtime.orchestrator import join_scheduled_planning

    client = _client()
    job_id = _create_job(client)
    assert join_scheduled_planning(job_id)

    response = client.get(f"/api/v1/jobs/{job_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert body["contract"]["contract_id"] == "contract-towel-1"
    assert body["revision"] == 1
    assert body["stage"] == "compile"
    assert body["state"] == "ready"
    assert body["hold"] is None
    assert body["error"] is None
    assert body["eye"] is not None
    assert body["brain"] is not None
    assert body["eye_available"] is True
    assert body["brain_available"] is True
    assert body["compile_available"] is True
    assert body["generation"] is None
    assert body["owner_id"] == "owner-1"
    dumped = json.dumps(body)
    assert "content_base64" not in dumped
    assert PNG_B64 not in dumped


def test_post_eye_executes_with_fake_provider() -> None:
    client = _client()
    job_id = _freeze_job()

    response = client.post(
        f"/api/v1/jobs/{job_id}/eye",
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert body["revision"] == 1
    assert body["stage"] == "eye"
    assert body["state"] == "ready"
    assert body["observation"]["contract_id"] == "contract-towel-1"
    assert body["observation"]["items"][0]["content_hash"] == HASH
    assert body["readiness"]["status"] == "ready"
    assert "model_id" not in body


def test_eye_observation_is_persisted_in_job_state() -> None:
    client = _client()
    job_id = _freeze_job()
    client.post(f"/api/v1/jobs/{job_id}/eye", json={})

    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.observation is not None
    assert stored.readiness is not None
    assert stored.eye_model_id == eye_model()
    expected = observation_for(build_eye_input(_contract(), ["ref-towel"]), "ready")
    assert stored.observation == expected
    assert stored.readiness.status == "ready"


def test_get_eye_returns_the_stored_observation() -> None:
    client = _client()
    job_id = _freeze_job()
    posted = client.post(
        f"/api/v1/jobs/{job_id}/eye",
        json={},
    ).json()["observation"]

    response = client.get(f"/api/v1/jobs/{job_id}/eye")

    assert response.status_code == 200
    body = response.json()
    assert body["job_id"] == job_id
    assert body["revision"] == 1
    assert body["observation"] == posted
    assert body["readiness"]["status"] == "ready"


def test_get_status_reflects_eye_execution() -> None:
    from app.runtime.orchestrator import join_scheduled_planning

    client = _client()
    job_id = _create_job(client)
    assert join_scheduled_planning(job_id)

    after = client.get(f"/api/v1/jobs/{job_id}/status")

    assert after.status_code == 200
    body = after.json()
    assert body["job_id"] == job_id
    assert body["revision"] == 1
    assert body["stage"] == "compile"
    assert body["state"] == "ready"
    assert body["ready"] is True
    assert body["compile_available"] is True
    assert body["generation_available"] is False
    assert body["hold"] is None
    assert body["error"] is None


def test_unknown_job_returns_404() -> None:
    response = _client().get("/api/v1/jobs/missing-job")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "JOB_NOT_FOUND",
            "message": "Job not found",
            "details": {"job_id": "missing-job"},
        }
    }


def test_get_eye_before_execution_returns_conflict() -> None:
    client = _client()
    job_id = create_job_from_intake(JOB_STORE, _intake()).job_id

    response = client.get(f"/api/v1/jobs/{job_id}/eye")

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "EYE_NOT_RUN"
    assert body["error"]["message"]
    assert body["error"]["details"]["job_id"] == job_id


def test_validation_errors_use_public_error_shape() -> None:
    response = _client().post("/api/v1/jobs", json={"contract": {"revision": 1}})

    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["message"] == "Invalid request"
    assert "issues" in body["error"]["details"]


def test_unresolved_placeholder_is_rejected() -> None:
    payload = _intake()
    payload["item"]["category"] = "Automatic from references"

    response = _client().post("/api/v1/jobs", json={"contract": payload})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_end_to_end_job_eye_persistence() -> None:
    client = _client()
    job_id = _freeze_job()

    executed = client.post(
        f"/api/v1/jobs/{job_id}/eye",
        json={},
    )
    assert executed.status_code == 200
    observation = executed.json()["observation"]
    assert observation["items"]

    job = client.get(f"/api/v1/jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["eye"] is not None
    assert job.json()["eye"]["observation"] == observation

    stored = client.get(f"/api/v1/jobs/{job_id}/eye")
    assert stored.status_code == 200
    assert stored.json()["observation"] == observation


def test_eye_unknown_job_returns_404() -> None:
    response = _client().post(
        "/api/v1/jobs/missing-job/eye",
        json={},
    )
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_openapi_documents_jobs_api() -> None:
    spec = _client().get("/openapi.json").json()
    paths = spec["paths"]
    assert "/api/v1/jobs" in paths
    assert "/api/v1/jobs/{job_id}/eye" in paths
    assert "/api/v1/jobs/{job_id}/brain" in paths
    assert "/api/v1/jobs/{job_id}/stylist" in paths
    assert "/api/v1/jobs/{job_id}/compile" in paths
    assert "/api/v1/jobs/{job_id}/generate" in paths
    assert "/api/v1/jobs/{job_id}/generate/image" in paths
    assert "/api/v1/jobs/{job_id}/critique" in paths
    assert "/api/v1/jobs/{job_id}/status" in paths
    image_get = paths["/api/v1/jobs/{job_id}/generate/image"]["get"]
    assert "200" in image_get["responses"]
    assert "image/png" in image_get["responses"]["200"]["content"]
    schemas = spec["components"]["schemas"]
    for name in (
        "IntakeReferenceAsset",
        "CreateJobRequest",
        "CreateJobResponse",
        "ExecuteEyeRequest",
        "ExecuteEyeResponse",
        "GetEyeResponse",
        "ExecuteGenerateRequest",
        "ExecuteGenerateResponse",
        "GetGenerateResponse",
        "GenerationView",
        "JobView",
        "JobStatusView",
        "ErrorResponse",
        "EyeObservation",
    ):
        assert name in schemas
    generation = schemas["GenerationView"]["properties"]
    assert "output_available" in generation
    assert "image_url" in generation
    assert "HTTPValidationError" not in schemas


def test_post_eye_with_failing_provider_hides_internals() -> None:
    class BoomProvider:
        def observe(self, request):  # noqa: ANN001
            raise RuntimeError("OpenRouter HTTP 401: secret leaked")

    from app.api.jobs import get_eye_provider

    app.dependency_overrides[get_eye_provider] = lambda: BoomProvider()
    try:
        client = _client()
        job_id = _freeze_job()
        response = client.post(
            f"/api/v1/jobs/{job_id}/eye",
            json={},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "PROVIDER_FAILURE"
    assert body["error"]["message"] == "Eye provider failed"
    assert "OpenRouter" not in body["error"]["message"]
    assert "secret" not in body["error"]["message"]
    details = body["error"]["details"]
    assert details["exception_class"] == "RuntimeError"
    assert details["phase"] == "http_request"
    assert "secret" not in str(details).lower()
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.state == "failed"
    assert stored.error is not None
    assert stored.error.code == "PROVIDER_FAILURE"
    assert stored.error.details["exception_class"] == "RuntimeError"
    assert stored.error.details["phase"] == "http_request"
    assert "secret" not in str(stored.error.details).lower()


def test_fake_provider_receives_job_reference_identity() -> None:
    provider = FakeEyeProvider()
    app.dependency_overrides[get_eye_provider] = lambda: provider
    try:
        client = _client()
        job_id = _freeze_job()
        response = client.post(
            f"/api/v1/jobs/{job_id}/eye",
            json={},
        )
    finally:
        app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider()

    assert response.status_code == 200
    assert len(provider.requests) == 1
    source = provider.requests[0].eye_input.references[0]
    assert source.reference_id == "ref-towel"
    assert source.filename == "pixel.png"
    assert source.media_type == "PNG"
    assert source.content_hash == HASH
    assert source.role == "Product / vendor reference"
    assert provider.requests[0].model_id == eye_model()


def test_missing_image_content_base64_is_rejected() -> None:
    payload = _contract().model_dump(mode="json")
    response = _client().post("/api/v1/jobs", json={"contract": payload})

    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert "content_base64" in body["error"]["details"]["reason"]


def test_invalid_content_base64_is_rejected() -> None:
    payload = _intake()
    payload["references"][0]["content_base64"] = "not-valid-base64!!!"
    response = _client().post("/api/v1/jobs", json={"contract": payload})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"


def test_content_hash_must_match_bytes() -> None:
    payload = _intake()
    payload["references"][0]["content_hash"] = "ab" * 32
    response = _client().post("/api/v1/jobs", json={"contract": payload})

    assert response.status_code == 422
    assert "content_hash" in response.json()["error"]["details"]["reason"]


def test_post_jobs_computes_hash_when_content_hash_is_missing() -> None:
    payload = _intake()
    del payload["references"][0]["content_hash"]
    response = _client().post("/api/v1/jobs", json={"contract": payload})

    assert response.status_code == 200, response.text
    stored = JOB_STORE.get(response.json()["job_id"])
    assert stored is not None
    assert stored.reference_bytes["ref-towel"] == PNG_1X1
    assert stored.contract.references[0].content_hash == HASH
    job = _client().get(f"/api/v1/jobs/{response.json()['job_id']}")
    assert job.json()["contract"]["references"][0]["content_hash"] == HASH


def test_post_jobs_computes_hash_when_content_hash_is_empty() -> None:
    payload = _intake()
    payload["references"][0]["content_hash"] = ""
    response = _client().post("/api/v1/jobs", json={"contract": payload})

    assert response.status_code == 200, response.text
    stored = JOB_STORE.get(response.json()["job_id"])
    assert stored is not None
    assert stored.contract.references[0].content_hash == HASH
    assert stored.reference_bytes["ref-towel"] == PNG_1X1


def test_post_jobs_accepts_lifestyle_without_other_outcome() -> None:
    payload = _intake()
    del payload["intent"]["other_outcome"]
    response = _client().post("/api/v1/jobs", json={"contract": payload})

    assert response.status_code == 200, response.text
    stored = JOB_STORE.get(response.json()["job_id"])
    assert stored is not None
    assert stored.contract.intent.other_outcome is None


def test_docs_list_every_post_before_every_get() -> None:
    spec = _client().get("/openapi.json").json()
    posts = [path for path, methods in spec["paths"].items() if "post" in methods]
    gets = [path for path, methods in spec["paths"].items() if "get" in methods]
    assert set(POST_DOC_PATHS) == set(posts)
    assert set(GET_DOC_PATHS) == set(gets)
    docs = _client().get("/docs")
    assert docs.status_code == 200
    html = docs.text
    post_list = json.dumps(list(POST_DOC_PATHS))
    get_list = json.dumps(list(GET_DOC_PATHS))
    assert "operationsSorter" in html
    assert post_list in html
    assert get_list in html
    assert html.index(post_list) < html.index(get_list)
    assert "post: 0, get: 1" in html


def test_mime_media_type_is_rejected() -> None:
    payload = _intake()
    payload["references"][0]["media_type"] = "image/png"
    response = _client().post("/api/v1/jobs", json={"contract": payload})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_REQUEST"
