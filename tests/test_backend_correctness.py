"""Backend correctness: pixels, request identity, review, critique, repair."""

from fastapi.testclient import TestClient

from app.api.jobs import get_critique_provider, get_generation_provider, get_repair_planner
from app.api.schemas import ExecuteGenerateRequest
from app.contracts.job import Phase0JobContract
from app.contracts.repair import REPAIR_LIMIT, RepairPlan
from app.main import app
from app.providers.fake_critique import FakeCritiqueProvider
from app.providers.fake_generation import FakeGenerationProvider
from app.providers.fake_repair import FakeRepairPlanner
from app.runtime.artifacts import generation_artifact_name, output_filename
from app.runtime.jobs import (
    approve_job,
    execute_job_critique,
    execute_job_generate,
    execute_job_repair,
    release_job,
)
from app.runtime.pixels import inspect_image
from app.runtime.orchestrator import join_scheduled_planning
from app.runtime.recovery import recover_jobs_from_artifacts
from app.runtime.state import JOB_STORE, InMemoryJobStore
from app.stages.critique import record_view_drift
from tests.test_generation_execution import _compiled, _contract
from tests.test_repair import _client, _contract as repair_contract, _seed_critiqued

CALLER_MODEL = "caller-supplied-model"


def test_wrong_returned_pixel_size_holds_and_keeps_measured_bytes() -> None:
    store = InMemoryJobStore()
    compiled = _compiled(store)
    updated = execute_job_generate(
        store,
        job_id=compiled.job_id,
        provider=FakeGenerationProvider(mode="wrong_size"),
    )
    receipt = updated.generation.receipt
    assert receipt is not None and receipt.output is not None
    assert receipt.format_check == "failed"
    assert receipt.status == "hold"
    assert (receipt.requested_width, receipt.requested_height) == (2048, 2048)
    assert (receipt.measured_width, receipt.measured_height) == (1024, 1024)
    assert receipt.measured_mime == "image/png"
    raw = updated.reference_bytes[receipt.output.output_id]
    assert inspect_image(raw).width == 1024
    assert inspect_image(raw).height == 1024
    assert updated.state == "hold"
    assert updated.review_status == "hold"
    assert updated.complete is False
    assert updated.approval is None
    assert updated.releasable is False


def test_correct_returned_pixel_size_passes_format_validation() -> None:
    store = InMemoryJobStore()
    compiled = _compiled(store)
    updated = execute_job_generate(
        store,
        job_id=compiled.job_id,
        provider=FakeGenerationProvider(),
    )
    receipt = updated.generation.receipt
    assert receipt is not None and receipt.output is not None
    assert receipt.format_check == "passed"
    assert receipt.status == "completed"
    assert (receipt.requested_width, receipt.requested_height) == (2048, 2048)
    assert (receipt.measured_width, receipt.measured_height) == (2048, 2048)
    assert receipt.measured_format == "PNG"
    assert receipt.measured_mime == "image/png"
    raw = updated.reference_bytes[receipt.output.output_id]
    assert inspect_image(raw).width == 2048
    assert updated.review_status == "generation_completed"
    assert updated.complete is False


def test_request_hash_is_stable_and_revision_changes_with_the_request() -> None:
    original = _contract()
    repeated = Phase0JobContract.model_validate(original.model_dump(mode="json"))
    assert original.request_identity is not None
    assert repeated.request_identity is not None
    assert original.request_identity.request_hash == repeated.request_identity.request_hash
    assert original.request_identity.owner_id == original.owner_id
    assert original.request_identity.revision == original.revision
    assert [item.content_hash for item in original.request_identity.source_hashes] == [
        item.content_hash for item in original.references
    ]

    revised = original.revise(
        preferences=original.preferences.model_copy(update={"plants": True})
    )
    assert revised.revision == original.revision + 1
    assert revised.request_identity is not None
    assert revised.request_identity.request_hash != original.request_identity.request_hash
    assert revised.request_identity.revision == revised.revision
    assert original.preferences.plants is False
    assert original.request_identity.request_hash == repeated.request_identity.request_hash


def test_critique_pass_is_review_pending_until_explicit_approval() -> None:
    store = InMemoryJobStore()
    generated = execute_job_generate(
        store,
        job_id=_compiled(store).job_id,
        provider=FakeGenerationProvider(),
    )
    brain_before = generated.brain.result
    updated = execute_job_critique(
        store,
        job_id=generated.job_id,
        model_id=CALLER_MODEL,
        provider=FakeCritiqueProvider(),
    )
    assert updated.critique is not None and updated.critique.result is not None
    assert updated.critique.result.overall_result == "pass"
    assert updated.state == "review_pending"
    assert updated.review_status == "review_pending"
    assert updated.complete is False
    assert updated.approval is None
    assert updated.releasable is False
    assert updated.brain.result == brain_before
    assessment = updated.critique.result
    assert assessment.product_fidelity
    assert assessment.styling_compliance
    assert assessment.plan_compliance
    assert assessment.view_compliance
    assert assessment.scene_compliance

    approved = approve_job(store, job_id=updated.job_id)
    assert approved.approval is not None
    assert approved.approval.owner_id == approved.owner_id
    assert approved.state == "approved"
    assert approved.review_status == "owner_approved"
    assert approved.complete is True
    assert approved.releasable is True

    released = release_job(store, job_id=updated.job_id)
    assert released.review_status == "released"
    assert released.state == "released"
    assert released.release is not None
    assert released.approval is not None


def test_view_drift_is_recorded_without_rewriting_plans() -> None:
    drift = record_view_drift(planned="three-quarter", observed="straight-on")
    assert drift is not None
    assert drift.attribute == "view"
    assert drift.planned == "three-quarter"
    assert drift.observed == "straight-on"
    assert drift.result == "drift"
    assert record_view_drift(planned="three-quarter", observed="three-quarter") is None

    store = InMemoryJobStore()
    generated = execute_job_generate(
        store,
        job_id=_compiled(store).job_id,
        provider=FakeGenerationProvider(),
    )
    stylist_before = generated.stylist.result
    brain_before = generated.brain.result
    updated = execute_job_critique(
        store,
        job_id=generated.job_id,
        model_id=CALLER_MODEL,
        provider=FakeCritiqueProvider("view_drift"),
    )
    assert updated.stylist.result == stylist_before
    assert updated.brain.result == brain_before
    assert updated.critique is not None and updated.critique.result is not None
    recorded = updated.critique.result.drift
    assert recorded
    assert recorded[0].attribute == "view"
    assert recorded[0].observed == "straight-on"
    assert recorded[0].result == "drift"
    assert updated.critique.result.view_compliance[0].result == "fail"
    assert updated.critique.result.styling_compliance
    assert updated.critique.result.plan_compliance
    assert updated.state != "approved"
    assert updated.approval is None


def test_local_edit_records_scene_base_and_unsupported_edit_does_not_claim_success() -> None:
    generation = FakeGenerationProvider(extra_capabilities=frozenset({"local_edit"}))
    client = _client(
        generation=generation,
        planner=FakeRepairPlanner(action="local_edit"),
        critique=FakeCritiqueProvider("repair_required"),
    )
    job_id = _seed_critiqued(client)
    before = JOB_STORE.get(job_id)
    assert before is not None and before.generation is not None
    assert before.generation.receipt is not None and before.generation.receipt.output is not None
    source_output = before.generation.receipt.output.output_id
    res = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert res.status_code == 200, res.text
    plan = res.json()["repair"]["plan"]
    assert plan["action"] == "local_edit"
    assert plan["scene_base_reference"] == source_output
    assert plan["product_authority_reference"] == "ref-towel"
    assert plan["preservation_status"] == "preserved"
    protected = " ".join(plan["protected_scene_attributes"])
    assert "room:" in protected
    assert "lighting:" in protected
    assert "composition:" in protected
    assert "placement:" in protected
    assert "supporting props:" in protected
    assert plan["targeted_attributes"]
    request = generation.requests[-1]
    assert source_output in request.reference_bytes
    assert "ref-towel" in request.reference_bytes

    unsupported = FakeGenerationProvider()
    client = _client(
        generation=unsupported,
        planner=FakeRepairPlanner(action="local_edit"),
        critique=FakeCritiqueProvider("repair_required"),
    )
    job_id = _seed_critiqued(client)
    dispatched = len(unsupported.requests)
    held = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert held.status_code == 200, held.text
    body = held.json()["repair"]["plan"]
    assert body["action"] == "hold"
    assert body["preservation_status"] == "unsupported"
    assert "not claimed" in body["preservation_result"]
    assert body["status"] != "completed"
    assert len(unsupported.requests) == dispatched


def test_repair_limit_remains_two() -> None:
    assert REPAIR_LIMIT == 2
    with_limit = {
        "job_id": "job-1",
        "contract_id": "contract-1",
        "contract_revision": 1,
        "critique_generation_output_id": "gen-1",
        "critique_generation_operation_key": "op-1",
        "source_generation_output_id": "gen-1",
        "source_generation_operation_key": "op-1",
        "original_reference_id": "ref-towel",
        "repair_count": 2,
        "repair_limit": 2,
        "target_regions": ["geometry"],
        "repair_instructions": ["restore construction"],
        "preserve_list": ["inventory"],
        "previous_defects": ["geometry: drifted"],
        "required_resolution_checks": ["geometry: match source"],
        "action": "fresh_render",
        "model_id": "caller-supplied-model",
        "status": "planned",
        "hold_reasons": [],
        "lineage": {
            "source_generation_output_id": "gen-1",
            "source_generation_operation_key": "op-1",
            "source_critique_generation_output_id": "gen-1",
            "original_reference_id": "ref-towel",
            "version_from": 1,
        },
    }
    assert RepairPlan.model_validate(with_limit).repair_limit == 2


def test_recovery_and_artifact_names_and_model_id_stay_intact() -> None:
    assert generation_artifact_name(1, "PNG") == "generations/01_initial.png"
    assert generation_artifact_name(2, "PNG") == "generations/02_repair.png"
    assert output_filename("PNG") == "generated.png"
    assert "model_id" in ExecuteGenerateRequest.model_fields

    client = TestClient(app)
    payload = repair_contract()
    created = client.post("/api/v1/jobs", json={"contract": payload})
    assert created.status_code == 200, created.text
    job_id = created.json()["job_id"]
    for path in ("eye", "brain", "stylist", "compile", "generate"):
        if path == "generate":
            approved = client.post(f"/api/v1/jobs/{job_id}/generate/approve", json={})
            assert approved.status_code == 200, approved.text
        response = client.post(f"/api/v1/jobs/{job_id}/{path}", json={})
        assert response.status_code == 200, response.text
    assert join_scheduled_planning(job_id)
    JOB_STORE.clear()
    recovered = recover_jobs_from_artifacts(JOB_STORE)
    assert job_id in recovered
    record = JOB_STORE.get(job_id)
    assert record is not None
    assert record.approval is None
    assert record.complete is False
    assert record.generation is not None
    assert record.generation.receipt is not None
    assert record.generation.receipt.format_check == "passed"
    assert record.contract.request_identity is not None
    assert record.contract.request_identity.owner_id == record.owner_id


def test_public_generate_route_still_accepts_model_id() -> None:
    client = _client()
    job_id = _seed_critiqued(client, through="compile")
    assert client.post(f"/api/v1/jobs/{job_id}/generate/approve", json={}).status_code == 200
    response = client.post(
        f"/api/v1/jobs/{job_id}/generate",
        json={"model_id": "google/gemini-3.1-flash-image"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["generation"]["operation"]["model_id"] == (
        "google/gemini-3.1-flash-image"
    )


def test_execute_repair_import_remains_available() -> None:
    assert callable(execute_job_repair)
    assert callable(get_generation_provider)
    assert callable(get_critique_provider)
    assert callable(get_repair_planner)
