"""Create Job derives request identity. Callers do not send the hashes."""

import hashlib
import json

from fastapi.testclient import TestClient

from app.contracts.job import Phase0JobContract
from app.main import app
from app.runtime.artifacts import get_artifact_store
from app.runtime.recovery import recover_jobs_from_artifacts
from app.runtime.state import JOB_STORE
from app.stages.package import build_delivery_manifest
from tests.png_bytes import PNG_1X1, PNG_HASH
from tests.test_api_v1_jobs import _intake


def _client() -> TestClient:
    return TestClient(app)


def _without_identity() -> dict:
    payload = _intake()
    payload.pop("request_identity", None)
    payload["references"][0].pop("content_hash", None)
    return payload


def test_openapi_create_job_does_not_require_derived_hashes() -> None:
    app.openapi_schema = None
    spec = _client().get("/openapi.json").json()
    intake = spec["components"]["schemas"]["IntakePhase0JobContract"]
    assert "request_identity" not in intake["properties"]
    assert "request_identity" not in intake.get("required", [])
    assert "RequestIdentity" not in json.dumps(intake)
    persisted = spec["components"]["schemas"]["Phase0JobContract"]
    assert "request_identity" in persisted["properties"]
    reference = spec["components"]["schemas"]["IntakeReferenceAsset"]
    assert "content_hash" not in reference.get("required", [])
    example = spec["components"]["schemas"]["CreateJobRequest"]["example"]
    encoded = json.dumps(example)
    assert "request_hash" not in encoded
    assert "source_hashes" not in encoded
    assert "content_hash" not in encoded
    assert "content_base64" in encoded
    eye = spec["components"]["schemas"]["ExecuteEyeRequest"]
    assert "model_id" in eye["properties"]


def test_swagger_example_creates_a_job_without_manual_hashes() -> None:
    app.openapi_schema = None
    example = _client().get("/openapi.json").json()["components"]["schemas"]["CreateJobRequest"]["example"]
    response = _client().post("/api/v1/jobs", json=example)
    assert response.status_code == 200, response.text
    stored = JOB_STORE.get(response.json()["job_id"])
    assert stored is not None
    identity = stored.contract.request_identity
    assert identity is not None
    assert len(identity.request_hash) == 64
    assert identity.source_hashes[0].content_hash == hashlib.sha256(PNG_1X1).hexdigest()
    assert stored.contract.references[0].content_hash == identity.source_hashes[0].content_hash


def test_create_without_request_identity_persists_server_hash() -> None:
    response = _client().post("/api/v1/jobs", json={"contract": _without_identity()})
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    identity = stored.contract.request_identity
    assert identity is not None
    assert len(identity.request_hash) == 64
    assert all(character in "0123456789abcdef" for character in identity.request_hash)
    assert identity.source_hashes[0].reference_id == "ref-towel"
    assert identity.source_hashes[0].content_hash == PNG_HASH
    assert stored.contract.references[0].content_hash == PNG_HASH
    assert hashlib.sha256(stored.reference_bytes["ref-towel"]).hexdigest() == PNG_HASH
    body = _client().get(f"/api/v1/jobs/{job_id}").json()
    assert body["contract"]["request_identity"]["request_hash"] == identity.request_hash
    assert body["contract"]["request_identity"]["source_hashes"][0]["content_hash"] == PNG_HASH


def test_same_request_has_the_same_hash_and_a_change_does_not() -> None:
    first = _client().post("/api/v1/jobs", json={"contract": _without_identity()})
    second = _client().post("/api/v1/jobs", json={"contract": _without_identity()})
    assert first.status_code == 200 and second.status_code == 200
    first_id = JOB_STORE.get(first.json()["job_id"]).contract.request_identity
    second_id = JOB_STORE.get(second.json()["job_id"]).contract.request_identity
    assert first_id.request_hash == second_id.request_hash
    assert [item.model_dump() for item in first_id.source_hashes] == [
        item.model_dump() for item in second_id.source_hashes
    ]

    changed = _without_identity()
    changed["preferences"]["plants"] = True
    third = _client().post("/api/v1/jobs", json={"contract": changed})
    assert third.status_code == 200, third.text
    third_id = JOB_STORE.get(third.json()["job_id"]).contract.request_identity
    assert third_id.request_hash != first_id.request_hash


def test_revision_keeps_the_previous_hash() -> None:
    response = _client().post("/api/v1/jobs", json={"contract": _without_identity()})
    stored = JOB_STORE.get(response.json()["job_id"])
    original = stored.contract
    revised = original.revise(preferences=original.preferences.model_copy(update={"plants": True}))
    assert revised.revision == original.revision + 1
    assert revised.request_identity.request_hash != original.request_identity.request_hash
    assert original.request_identity.request_hash == stored.contract.request_identity.request_hash
    assert original.revision == 1


def test_derived_identity_survives_recovery_and_manifest() -> None:
    response = _client().post("/api/v1/jobs", json={"contract": _without_identity()})
    job_id = response.json()["job_id"]
    created = JOB_STORE.get(job_id)
    request_hash = created.contract.request_identity.request_hash
    source_hash = created.contract.request_identity.source_hashes[0].content_hash
    JOB_STORE.clear()
    assert job_id in recover_jobs_from_artifacts(JOB_STORE)
    recovered = JOB_STORE.get(job_id)
    assert recovered.contract.request_identity.request_hash == request_hash
    assert recovered.contract.request_identity.source_hashes[0].content_hash == source_hash
    manifest = build_delivery_manifest(recovered)
    assert manifest.request_hash == request_hash
    disk = json.loads(get_artifact_store().get_artifact(job_id, "manifest.json").decode("utf-8"))
    assert disk["request_hash"] == request_hash


def test_existing_persisted_request_identity_still_loads() -> None:
    response = _client().post("/api/v1/jobs", json={"contract": _without_identity()})
    job_id = response.json()["job_id"]
    raw = json.loads(get_artifact_store().get_artifact(job_id, "job.json").decode("utf-8"))
    assert raw["contract"]["request_identity"]["request_hash"]
    contract = Phase0JobContract.model_validate(raw["contract"])
    assert contract.request_identity.request_hash == raw["contract"]["request_identity"]["request_hash"]
    JOB_STORE.clear()
    recovered = recover_jobs_from_artifacts(JOB_STORE)
    assert job_id in recovered
    assert JOB_STORE.get(job_id).contract.request_identity.source_hashes
