"""Pre-generation approval is separate from final owner approval."""

from fastapi.testclient import TestClient

from app.contracts.generation import ProviderCostEvidence, ProviderUsageEvidence
from app.providers.fake_critique import FakeCritiqueProvider
from app.providers.fake_generation import FakeGenerationProvider
from app.runtime.jobs import ReleaseNotReadyError, release_job
from app.runtime.recovery import recover_jobs_from_artifacts
from app.runtime.state import JOB_STORE
from app.stages.package import build_delivery_manifest
from tests.png_bytes import PNG_B64
from tests.test_api_v1_generate import _client, _contract
from tests.test_repair import _client as repair_client
from tests.test_repair import _seed_critiqued


def _compiled(client: TestClient) -> str:
    contract_data = _contract().model_dump(mode="python")
    contract_data["references"][0]["content_base64"] = PNG_B64
    job_id = client.post("/api/v1/jobs", json={"contract": contract_data}).json()["job_id"]
    for stage in ("eye", "brain", "stylist", "compile"):
        response = client.post(f"/api/v1/jobs/{job_id}/{stage}", json={})
        assert response.status_code == 200, response.text
    return job_id


def _record(job_id: str):
    record = JOB_STORE.get(job_id)
    assert record is not None
    return record


def test_generate_without_pre_approval_does_not_call_the_provider() -> None:
    provider = FakeGenerationProvider()
    client = _client(provider)
    job_id = _compiled(client)
    response = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRE_GENERATION_APPROVAL_REQUIRED"
    assert provider.requests == []
    assert _record(job_id).generation is None


def test_valid_pre_approval_allows_one_generation_and_dedupes() -> None:
    provider = FakeGenerationProvider()
    client = _client(provider)
    job_id = _compiled(client)
    first = client.post(f"/api/v1/jobs/{job_id}/generate/approve", json={})
    assert first.status_code == 200, first.text
    approved_at = _record(job_id).pre_generation_approval
    assert approved_at is not None
    again = client.post(f"/api/v1/jobs/{job_id}/generate/approve", json={})
    assert again.status_code == 200
    assert _record(job_id).pre_generation_approval == approved_at
    generated = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert generated.status_code == 200, generated.text
    repeat = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert repeat.status_code == 200
    assert len(provider.requests) == 1
    assert _record(job_id).pre_generation_approval == approved_at
    assert _record(job_id).approval is None


def test_wrong_owner_request_hash_revision_and_expiry_block_generation() -> None:
    provider = FakeGenerationProvider()
    client = _client(provider)
    job_id = _compiled(client)
    assert client.post(f"/api/v1/jobs/{job_id}/generate/approve", json={}).status_code == 200
    record = _record(job_id)
    approval = record.pre_generation_approval
    assert approval is not None

    JOB_STORE.save(
        record.model_copy(
            update={"pre_generation_approval": approval.model_copy(update={"owner_id": "other-owner"})}
        )
    )
    response = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert response.status_code == 409
    assert "another owner" in response.json()["error"]["details"]["reasons"][0]
    assert provider.requests == []

    fresh = client.post(f"/api/v1/jobs/{job_id}/generate/approve", json={})
    assert fresh.status_code == 200
    record = _record(job_id)
    approval = record.pre_generation_approval
    assert approval is not None
    JOB_STORE.save(
        record.model_copy(
            update={
                "pre_generation_approval": approval.model_copy(
                    update={"request_hash": "ab" * 32}
                )
            }
        )
    )
    response = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert response.status_code == 409
    assert "request_hash" in response.json()["error"]["details"]["reasons"][0]
    assert provider.requests == []

    assert client.post(f"/api/v1/jobs/{job_id}/generate/approve", json={}).status_code == 200
    record = _record(job_id)
    approval = record.pre_generation_approval
    assert approval is not None
    JOB_STORE.save(
        record.model_copy(
            update={"pre_generation_approval": approval.model_copy(update={"revision": record.revision + 1})}
        )
    )
    response = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert response.status_code == 409
    assert "revision" in response.json()["error"]["details"]["reasons"][0]

    expired = client.post(
        f"/api/v1/jobs/{job_id}/generate/approve",
        json={"expires_at": "2020-01-01T00:00:00+00:00"},
    )
    assert expired.status_code == 200
    response = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert response.status_code == 409
    assert "expired" in response.json()["error"]["details"]["reasons"][0]
    assert provider.requests == []
    assert _record(job_id).generation is None


def test_contract_revision_invalidates_the_previous_pre_approval() -> None:
    provider = FakeGenerationProvider()
    client = _client(provider)
    job_id = _compiled(client)
    assert client.post(f"/api/v1/jobs/{job_id}/generate/approve", json={}).status_code == 200
    record = _record(job_id)
    revised = record.contract.revise(
        preferences=record.contract.preferences.model_copy(update={"mood": "Warm & inviting"})
    )
    JOB_STORE.save(record.model_copy(update={"contract": revised, "revision": revised.revision}))
    response = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PRE_GENERATION_APPROVAL_REQUIRED"
    assert provider.requests == []
    assert _record(job_id).pre_generation_approval is None
    assert revised.request_identity is not None
    assert record.contract.request_identity is not None
    assert revised.request_identity.request_hash != record.contract.request_identity.request_hash


def test_pre_approval_cannot_release_the_package() -> None:
    client = repair_client(critique=FakeCritiqueProvider())
    job_id = _seed_critiqued(client)
    record = _record(job_id)
    assert record.pre_generation_approval is not None
    assert record.approval is None
    assert record.releasable is False
    try:
        release_job(JOB_STORE, job_id=job_id)
    except ReleaseNotReadyError as exc:
        assert "owner approval" in exc.reasons[0]
    else:
        raise AssertionError("pre-generation approval released the package")
    assert _record(job_id).release is None


def test_recovery_keeps_pre_approval_and_cost_evidence() -> None:
    provider = FakeGenerationProvider()
    client = _client(provider)
    job_id = _compiled(client)
    blocked = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert blocked.status_code == 409
    assert client.post(f"/api/v1/jobs/{job_id}/generate/approve", json={}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/generate", json={}).status_code == 200
    record = _record(job_id)
    assert record.generation is not None and record.generation.receipt is not None
    receipt = record.generation.receipt.model_copy(
        update={
            "provider_cost": ProviderCostEvidence(amount=0.04, currency="USD", status="known"),
            "provider_usage": ProviderUsageEvidence(
                prompt_tokens=1, completion_tokens=2, total_tokens=3, cost=0.04
            ),
        }
    )
    stored = record.generation.model_copy(update={"receipt": receipt})
    JOB_STORE.save(record.model_copy(update={"generation": stored}))
    from app.runtime.artifacts import persist_job_record

    persist_job_record(JOB_STORE.get(job_id), stage="generate")  # type: ignore[arg-type]
    JOB_STORE.clear()
    assert job_id in recover_jobs_from_artifacts(JOB_STORE)
    recovered = _record(job_id)
    assert recovered.pre_generation_approval is not None
    assert recovered.pre_generation_approval.request_hash == record.pre_generation_approval.request_hash
    assert recovered.generation is not None and recovered.generation.receipt is not None
    assert recovered.generation.receipt.provider_cost is not None
    assert recovered.generation.receipt.provider_cost.amount == 0.04
    assert recovered.generation.receipt.provider_cost.status == "known"
    manifest = build_delivery_manifest(recovered)
    assert manifest.cost is not None
    assert manifest.cost.amount == 0.04
    assert manifest.cost_status == "known"
    repeat = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert repeat.status_code == 200
    assert len(provider.requests) == 1

    unknown = recovered.generation.receipt.model_copy(
        update={"provider_cost": ProviderCostEvidence(amount=None, currency=None, status="unknown")}
    )
    manifest = build_delivery_manifest(
        recovered.model_copy(
            update={"generation": recovered.generation.model_copy(update={"receipt": unknown})}
        )
    )
    assert manifest.cost is not None
    assert manifest.cost.amount is None
    assert manifest.cost.status == "unknown"
    assert manifest.cost_status == "unknown"
