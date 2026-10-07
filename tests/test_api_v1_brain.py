import inspect
import json

from fastapi.testclient import TestClient

from app.api.jobs import get_brain_provider, get_eye_provider
from app.contracts.job import Phase0JobContract
from app.main import app
from app.providers.fake_brain import FakeBrainProvider, plan_for
from app.providers.fake_eye import FakeEyeProvider
from app.runtime.model_policy import brain_model
from app.runtime.state import JOB_STORE
from app.stages.brain import build_brain_input
from tests.png_bytes import PNG_B64, PNG_HASH

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


def _run_eye(client: TestClient, job_id: str) -> None:
    response = client.post(
        f"/api/v1/jobs/{job_id}/eye",
        json={},
    )
    assert response.status_code == 200, response.text


def test_post_brain_unknown_job_returns_404() -> None:
    response = _client().post(
        "/api/v1/jobs/missing-job/brain",
        json={},
    )
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "JOB_NOT_FOUND",
            "message": "Job not found",
            "details": {"job_id": "missing-job"},
        }
    }


def test_post_brain_before_eye_returns_conflict() -> None:
    client = _client()
    job_id = _create_job(client)

    response = client.post(
        f"/api/v1/jobs/{job_id}/brain",
        json={},
    )

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "EYE_NOT_RUN"
    assert body["error"]["details"]["job_id"] == job_id


def test_post_brain_uses_stored_contract_and_eye_without_resend() -> None:
    provider = FakeBrainProvider()
    app.dependency_overrides[get_brain_provider] = lambda: provider
    try:
        client = _client()
        job_id = _create_job(client)
        _run_eye(client, job_id)
        response = client.post(
            f"/api/v1/jobs/{job_id}/brain",
            json={},
        )
    finally:
        app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["job_id"] == job_id
    assert body["revision"] == 1
    assert body["stage"] == "brain"
    assert body["state"] == "ready"
    assert body["brain"]["model_id"] == brain_model()
    assert body["brain"]["execution_status"] == "completed"
    assert body["brain"]["plan"]["contract_id"] == "contract-towel-1"
    assert body["brain"]["plan"]["observation_contract_id"] == "contract-towel-1"
    assert body["brain"]["plan"]["mode"] == "fidelity-locked"
    assert json.loads(response.request.content.decode()) == {}
    assert "contract" not in json.loads(response.request.content.decode())

    assert len(provider.requests) == 1
    received = provider.requests[0]
    assert received.model_id == brain_model()
    assert received.brain_input.job_id == job_id
    assert received.brain_input.contract == _contract()
    assert received.brain_input.observation.contract_id == "contract-towel-1"
    assert received.brain_input.readiness.status == "ready"
    assert received.brain_input.evidence[0].reference_id == "ref-towel"
    assert received.brain_input.evidence[0].content_hash == HASH
    assert received.brain_input.evidence[0].bytes_available is True


def test_brain_result_is_persisted_on_the_same_job() -> None:
    client = _client()
    job_id = _create_job(client)
    _run_eye(client, job_id)
    posted = client.post(
        f"/api/v1/jobs/{job_id}/brain",
        json={},
    )
    assert posted.status_code == 200

    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.observation is not None
    assert stored.brain is not None
    assert stored.brain.model_id == brain_model()
    assert stored.brain.status == "completed"
    assert stored.brain.result is not None
    expected = plan_for(build_brain_input(stored))
    assert stored.brain.result == expected
    assert stored.contract == _contract()


def test_get_brain_returns_stored_result_without_rerun() -> None:
    provider = FakeBrainProvider()
    app.dependency_overrides[get_brain_provider] = lambda: provider
    try:
        client = _client()
        job_id = _create_job(client)
        _run_eye(client, job_id)
        posted = client.post(
            f"/api/v1/jobs/{job_id}/brain",
            json={},
        )
        assert posted.status_code == 200
        stored_brain = posted.json()["brain"]
        assert len(provider.requests) == 1

        response = client.get(f"/api/v1/jobs/{job_id}/brain")
        assert response.status_code == 200
        assert response.json()["brain"] == stored_brain
        assert len(provider.requests) == 1
    finally:
        app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()


def test_get_brain_before_eye_returns_eye_not_run() -> None:
    client = _client()
    job_id = _create_job(client)
    response = client.get(f"/api/v1/jobs/{job_id}/brain")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EYE_NOT_RUN"


def test_get_brain_after_eye_before_brain_returns_brain_not_run() -> None:
    client = _client()
    job_id = _create_job(client)
    _run_eye(client, job_id)
    response = client.get(f"/api/v1/jobs/{job_id}/brain")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "BRAIN_NOT_RUN"


def test_brain_hold_uses_existing_readiness_reasons() -> None:
    app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider(
        "critical_identity_ambiguity"
    )
    try:
        client = _client()
        job_id = _create_job(client)
        eye = client.post(
            f"/api/v1/jobs/{job_id}/eye",
            json={},
        )
        assert eye.status_code == 200
        assert eye.json()["readiness"]["status"] == "hold"

        response = client.post(
            f"/api/v1/jobs/{job_id}/brain",
            json={},
        )
    finally:
        app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider()

    assert response.status_code == 409
    body = response.json()
    assert body["error"]["code"] == "BRAIN_NOT_READY"
    assert body["error"]["details"]["reasons"] == ["critical identity ambiguity"]
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.brain is None
    assert stored.observation is not None


def test_caller_model_is_required_and_not_selected() -> None:
    from app.runtime.jobs import execute_job_brain

    rejected = _client().post(
        "/api/v1/jobs/any/brain",
        json={"model_id": "fake-model"},
    )
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "INVALID_REQUEST"

    missing = _client().post("/api/v1/jobs/any/brain", json={})
    assert missing.status_code == 404

    assert inspect.signature(execute_job_brain).parameters["model_id"].default is inspect.Parameter.empty
    for module_name in (
        "app.stages.brain",
        "app.runtime.jobs",
        "app.providers.fake_brain",
        "app.providers.brain",
        "app.api.jobs",
    ):
        source = inspect.getsource(__import__(module_name, fromlist=["*"]))
        assert "ModelRegistry" not in source
        assert "select_model" not in source


def test_brain_provider_failure_hides_internals() -> None:
    class BoomProvider:
        def reason(self, request):  # noqa: ANN001
            raise RuntimeError("OpenRouter HTTP 401: secret leaked")

    app.dependency_overrides[get_brain_provider] = lambda: BoomProvider()
    try:
        client = _client()
        job_id = _create_job(client)
        _run_eye(client, job_id)
        response = client.post(
            f"/api/v1/jobs/{job_id}/brain",
            json={},
        )
    finally:
        app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()

    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "PROVIDER_FAILURE"
    assert body["error"]["message"] == "Brain provider failed"
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
    assert stored.observation is not None


def test_end_to_end_job_eye_brain_persistence() -> None:
    client = _client()
    created = client.post("/api/v1/jobs", json={"contract": _intake()})
    assert created.status_code == 200
    job_id = created.json()["job_id"]

    eye = client.post(
        f"/api/v1/jobs/{job_id}/eye",
        json={},
    )
    assert eye.status_code == 200
    observation = eye.json()["observation"]

    brain = client.post(
        f"/api/v1/jobs/{job_id}/brain",
        json={},
    )
    assert brain.status_code == 200
    stored_brain = brain.json()["brain"]

    job = client.get(f"/api/v1/jobs/{job_id}")
    assert job.status_code == 200
    body = job.json()
    assert body["eye"] is not None
    assert body["eye"]["observation"] == observation
    assert body["brain"] == stored_brain
    dumped = job.text
    assert PNG_B64 not in dumped
    assert "content_base64" not in dumped

    fetched = client.get(f"/api/v1/jobs/{job_id}/brain")
    assert fetched.status_code == 200
    assert fetched.json()["brain"] == stored_brain


def test_wrong_owner_cannot_execute_or_read_brain() -> None:
    client = _client()
    job_id = _create_job(client)
    _run_eye(client, job_id)
    denied = client.post(
        f"/api/v1/jobs/{job_id}/brain",
        params={"owner_id": "owner-2"},
        json={},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "JOB_OWNER_MISMATCH"

    allowed = client.post(
        f"/api/v1/jobs/{job_id}/brain",
        params={"owner_id": "owner-1"},
        json={},
    )
    assert allowed.status_code == 200
    blocked_get = client.get(
        f"/api/v1/jobs/{job_id}/brain",
        params={"owner_id": "owner-2"},
    )
    assert blocked_get.status_code == 403


def test_brain_revision_mismatch_is_rejected() -> None:
    client = _client()
    job_id = _create_job(client)
    _run_eye(client, job_id)
    response = client.post(
        f"/api/v1/jobs/{job_id}/brain",
        params={"revision": 9},
        json={},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REVISION_MISMATCH"


def test_invalid_provider_json_is_rejected() -> None:
    class BadJsonProvider:
        def reason(self, request):  # noqa: ANN001
            raise RuntimeError("model content was not a JSON object")

    app.dependency_overrides[get_brain_provider] = lambda: BadJsonProvider()
    try:
        client = _client()
        job_id = _create_job(client)
        _run_eye(client, job_id)
        response = client.post(
            f"/api/v1/jobs/{job_id}/brain",
            json={},
        )
    finally:
        app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()

    assert response.status_code == 502
    body = response.json()
    assert body["error"]["code"] == "PROVIDER_FAILURE"
    details = body["error"]["details"]
    assert details["exception_class"] == "RuntimeError"
    assert details["phase"] == "json_parsing"
    assert "JSON" in details["message"]


def test_invalid_brain_schema_is_rejected() -> None:
    app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider(
        violation="protected_as_variable"
    )
    try:
        client = _client()
        job_id = _create_job(client)
        _run_eye(client, job_id)
        response = client.post(
            f"/api/v1/jobs/{job_id}/brain",
            json={},
        )
    finally:
        app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()

    assert response.status_code == 502
    details = response.json()["error"]["details"]
    assert details["exception_class"] == "BrainPlanInvalidError"
    assert details["phase"] == "brain_plan_validation"
    assert "protected identity" in details["message"]
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.observation is not None
    assert stored.brain is None or stored.brain.result is None


def test_provider_failure_includes_openrouter_call_record() -> None:
    class Record:
        http_status = 429
        request_id = "req-live-1"
        response_id = "resp-live-1"
        error_message = "OpenRouter HTTP 429: rate limited"
        raw_keys = ["mode", "route"]
        mapping_mismatches: list[str] = []

    class BoomProvider:
        last_call = Record()

        def reason(self, request):  # noqa: ANN001
            raise RuntimeError(self.last_call.error_message)

    app.dependency_overrides[get_brain_provider] = lambda: BoomProvider()
    try:
        client = _client()
        job_id = _create_job(client)
        _run_eye(client, job_id)
        response = client.post(
            f"/api/v1/jobs/{job_id}/brain",
            json={},
        )
    finally:
        app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()

    assert response.status_code == 502
    details = response.json()["error"]["details"]
    assert details["phase"] == "http_request"
    assert details["http_status"] == 429
    assert details["request_id"] == "req-live-1"
    assert details["response_id"] == "resp-live-1"
    assert details["parsed_keys"] == ["mode", "route"]
    assert "429" in details["provider_error"]
    dumped = json.dumps(details)
    assert "Bearer" not in dumped
    assert "OPENROUTER_API_KEY" not in dumped


def test_user_selected_count_remains_invariant() -> None:
    client = _client()
    job_id = _create_job(client)
    _run_eye(client, job_id)
    response = client.post(
        f"/api/v1/jobs/{job_id}/brain",
        json={},
    )
    assert response.status_code == 200
    plan = response.json()["brain"]["plan"]
    counts = [item for item in plan["invariants"] if item["name"] == "count"]
    assert counts
    assert counts[0]["value"] == "1"
    protected = "towel count"
    assert all(variable["value"] != protected for variable in plan["variables"])

