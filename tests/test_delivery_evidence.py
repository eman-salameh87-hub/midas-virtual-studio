"""Evidence and delivery: measurements, lineage, manifest, checksums, recovery."""

import json

from fastapi.testclient import TestClient

from app.api.schemas import generation_output_available
from app.contracts.eye import EyeObservation
from app.contracts.job import Phase0JobContract
from app.main import app
from app.providers.fake_critique import FakeCritiqueProvider
from app.providers.fake_eye import FakeEyeProvider
from app.providers.fake_generation import FakeGenerationProvider
from app.providers.fake_repair import FakeRepairPlanner
from app.runtime.artifacts import get_artifact_store
from app.runtime.checksum import sha256_hex
from app.runtime.jobs import (
    approve_job,
    create_job,
    execute_job_critique,
    execute_job_eye,
    execute_job_generate,
    execute_job_repair,
    release_job,
)
from app.runtime.recovery import recover_jobs_from_artifacts
from app.runtime.reference_metadata import measure_references
from app.runtime.state import JOB_STORE, InMemoryJobStore
from app.stages.package import build_delivery_manifest
from tests.png_bytes import PNG_1X1, PNG_HASH
from tests.test_generation_execution import CALLER_MODEL, _compiled, _contract

TAMPERED = b"not-the-original-image"


def _recover(job_id: str):
    JOB_STORE.clear()
    recover_jobs_from_artifacts(JOB_STORE)
    return JOB_STORE.get(job_id)


def test_reference_metadata_measures_bytes_and_leaves_unknowns_unknown() -> None:
    store = InMemoryJobStore()
    created = create_job(
        store, _contract(), {"ref-product": PNG_1X1, "ref-room": PNG_1X1}
    )
    by_id = {item.reference_id: item for item in created.reference_measurements}
    product = by_id["ref-product"]
    assert product.filename == "pixel.png"
    assert product.declared_media_type == "PNG"
    assert product.actual_mime == "image/png"
    assert product.actual_format == "PNG"
    assert (product.width, product.height) == (1, 1)
    assert product.content_hash == PNG_HASH
    assert product.checksum_status == "matched"
    assert product.source_view is None
    assert product.product_components is None
    artifacts = get_artifact_store()
    assert artifacts.get_artifact(created.job_id, "input/ref-product-pixel.png") == PNG_1X1

    data = _contract().model_dump(mode="python")
    data.pop("request_identity", None)
    data["statements"] = [
        {
            "subject": "view",
            "value": "three-quarter",
            "basis": "observed",
            "evidence_reference_id": "ref-product",
        }
    ]
    with_view = Phase0JobContract.model_validate(data)
    measured = measure_references(
        with_view, {"ref-product": PNG_1X1, "ref-room": PNG_1X1}
    )
    viewed = next(item for item in measured if item.reference_id == "ref-product")
    room = next(item for item in measured if item.reference_id == "ref-room")
    assert viewed.source_view == "three-quarter"
    assert room.source_view is None
    assert viewed.product_components is None

    garbage = b"%PDF-1.4 not an image"
    mismatched = measure_references(with_view, {"ref-product": garbage, "ref-room": PNG_1X1})
    broken = next(item for item in mismatched if item.reference_id == "ref-product")
    assert broken.content_hash == PNG_HASH
    assert broken.observed_checksum == sha256_hex(garbage)
    assert broken.checksum_status == "mismatch"
    assert broken.actual_mime is None
    assert broken.actual_format is None
    assert broken.width is None
    assert broken.height is None
    assert broken.filename == "pixel.png"


def test_eye_components_are_copied_only_when_an_item_cites_the_reference() -> None:
    store = InMemoryJobStore()
    created = create_job(
        store, _contract(), {"ref-product": PNG_1X1, "ref-room": PNG_1X1}
    )
    updated = execute_job_eye(
        store,
        job_id=created.job_id,
        model_id=CALLER_MODEL,
        provider=FakeEyeProvider("ready"),
    )
    by_id = {item.reference_id: item for item in updated.reference_measurements}
    assert by_id["ref-product"].product_components == ["visible item"]
    assert by_id["ref-room"].product_components is None
    assert by_id["ref-product"].source_view is None
    assert isinstance(updated.observation, EyeObservation)


def test_generation_metadata_keeps_requested_size_separate_from_measured_bytes() -> None:
    store = InMemoryJobStore()
    provider = FakeGenerationProvider()
    generated = execute_job_generate(
        store,
        job_id=_compiled(store).job_id,
        provider=provider,
    )
    stored = generated.generation
    assert stored is not None and stored.receipt is not None and stored.receipt.output is not None
    receipt = stored.receipt
    assert (receipt.requested_width, receipt.requested_height) == (2048, 2048)
    assert (receipt.measured_width, receipt.measured_height) == (2048, 2048)
    assert receipt.measured_mime == "image/png"
    assert receipt.measured_format == "PNG"
    assert receipt.output.content_hash == sha256_hex(
        generated.reference_bytes[receipt.output.output_id]
    )
    assert stored.checksum_status == "matched"
    assert receipt.provider_name == "fake"
    assert receipt.provider_receipt_id
    assert stored.operation.model_id

    held_store = InMemoryJobStore()
    held = execute_job_generate(
        held_store,
        job_id=_compiled(held_store).job_id,
        provider=FakeGenerationProvider(mode="wrong_size"),
    )
    held_receipt = held.generation.receipt
    assert held_receipt is not None
    assert (held_receipt.requested_width, held_receipt.requested_height) == (2048, 2048)
    assert (held_receipt.measured_width, held_receipt.measured_height) == (1024, 1024)
    assert held_receipt.format_check == "failed"
    assert held.state == "hold"


def test_generation_lineage_links_repairs_to_the_previous_version() -> None:
    store = InMemoryJobStore()
    provider = FakeGenerationProvider()
    generated = execute_job_generate(
        store, job_id=_compiled(store).job_id, provider=provider
    )
    critiqued = execute_job_critique(
        store,
        job_id=generated.job_id,
        model_id=CALLER_MODEL,
        provider=FakeCritiqueProvider("repair_required"),
    )
    repaired = execute_job_repair(
        store,
        job_id=critiqued.job_id,
        planner=FakeRepairPlanner(),
        provider=provider,
    )
    manifest = build_delivery_manifest(repaired)
    assert manifest.generation_sequence == [1, 2]
    assert manifest.current_generation is not None
    assert manifest.current_generation.sequence_index == 2
    assert manifest.current_generation.generation_kind == "repair"
    assert manifest.current_generation.parent_generation == 1
    assert manifest.generation_history[0].sequence_index == 1
    assert manifest.generation_history[0].generation_kind == "initial"
    assert manifest.generation_history[0].parent_generation is None
    assert manifest.current_generation.output_id != manifest.generation_history[0].output_id
    assert manifest.current_image_path == "output/current.png"
    artifacts = get_artifact_store()
    current = artifacts.get_artifact(repaired.job_id, "output/current.png")
    second = artifacts.get_artifact(repaired.job_id, "generations/02_repair.png")
    first = artifacts.get_artifact(repaired.job_id, "generations/01_initial.png")
    assert current == second
    assert sha256_hex(current) == manifest.current_generation.sha256
    assert sha256_hex(first) == manifest.generation_history[0].sha256
    payload = json.loads(
        artifacts.get_artifact(repaired.job_id, "generations/02_repair.json").decode("utf-8")
    )
    assert payload["parent_generation"] == 1
    assert payload["generation_kind"] == "repair"
    assert payload["operation_key"] == repaired.generation.operation.operation_key
    assert payload["output_id"] == repaired.generation.receipt.output.output_id
    assert len(provider.requests) == 2


def test_manifest_is_persisted_truth_and_complete_only_after_approval() -> None:
    store = InMemoryJobStore()
    generated = execute_job_generate(
        store, job_id=_compiled(store).job_id, provider=FakeGenerationProvider()
    )
    pending = execute_job_critique(
        store,
        job_id=generated.job_id,
        model_id=CALLER_MODEL,
        provider=FakeCritiqueProvider(),
    )
    manifest = build_delivery_manifest(pending)
    assert manifest.job_id == pending.job_id
    assert manifest.owner_id == pending.owner_id
    assert manifest.contract_id == pending.contract.contract_id
    assert manifest.revision == pending.revision
    assert manifest.request_hash == pending.contract.request_identity.request_hash
    assert manifest.package_status == "review_pending"
    assert manifest.review_status == "review_pending"
    assert manifest.complete is False
    assert manifest.approval is None
    assert manifest.release is None
    assert manifest.cost is None
    assert manifest.cost_status == "not_recorded"
    assert manifest.checksum == pending.generation.receipt.output.content_hash
    assert manifest.critique_result == "pass"
    assert manifest.output_valid is True
    disk = json.loads(
        get_artifact_store().get_artifact(pending.job_id, "manifest.json").decode("utf-8")
    )
    assert disk["complete"] is False
    assert disk["approval"] is None
    assert disk["cost"] is None
    assert disk["cost_status"] == "not_recorded"

    approved = approve_job(store, job_id=pending.job_id)
    approved_manifest = build_delivery_manifest(approved)
    assert approved_manifest.complete is True
    assert approved_manifest.approval["owner_id"] == approved.owner_id
    assert approved_manifest.approval["generation_output_id"] == (
        approved.generation.receipt.output.output_id
    )
    assert approved_manifest.approval["request_hash"] == approved.contract.request_identity.request_hash
    assert "approval_id" not in approved_manifest.approval

    released = release_job(store, job_id=pending.job_id)
    released_manifest = build_delivery_manifest(released)
    assert released_manifest.review_status == "released"
    assert released_manifest.release["generation_output_id"] == (
        released.generation.receipt.output.output_id
    )


def test_checksum_mismatch_is_detected_and_does_not_rewrite_the_receipt() -> None:
    store = InMemoryJobStore()
    provider = FakeGenerationProvider()
    generated = execute_job_generate(
        store, job_id=_compiled(store).job_id, provider=provider
    )
    job_id = generated.job_id
    stored_hash = generated.generation.receipt.output.content_hash
    artifacts = get_artifact_store()
    before = artifacts.get_artifact(job_id, "generation.json")
    for name in (
        "generations/01_initial.png",
        "output/current.png",
        "output/generated.png",
    ):
        path_bytes = artifacts.get_artifact(job_id, name)
        if path_bytes:
            job_dir = artifacts.job_dir(job_id)
            artifacts._write_bytes(job_dir / name, TAMPERED)
    calls = len(provider.requests)
    recovered = _recover(job_id)
    assert recovered is not None
    assert recovered.generation.receipt.output.content_hash == stored_hash
    assert recovered.generation.observed_checksum == sha256_hex(TAMPERED)
    assert recovered.generation.checksum_status == "mismatch"
    assert recovered.state == "hold"
    assert recovered.review_status == "hold"
    assert recovered.complete is False
    assert recovered.error is not None
    assert recovered.error.code == "CHECKSUM_MISMATCH"
    assert artifacts.get_artifact(job_id, "generation.json") == before
    assert generation_output_available(recovered) is False
    manifest = build_delivery_manifest(recovered)
    assert manifest.output_valid is False
    assert manifest.complete is False
    assert manifest.checksum == stored_hash
    client = TestClient(app)
    response = client.get(f"/api/v1/jobs/{job_id}/generate/image")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GENERATION_IMAGE_UNAVAILABLE"
    assert len(provider.requests) == calls


def test_valid_checksum_survives_recovery_without_a_provider_call() -> None:
    store = InMemoryJobStore()
    provider = FakeGenerationProvider()
    generated = execute_job_generate(
        store, job_id=_compiled(store).job_id, provider=provider
    )
    pending = execute_job_critique(
        store,
        job_id=generated.job_id,
        model_id=CALLER_MODEL,
        provider=FakeCritiqueProvider(),
    )
    calls = len(provider.requests)
    recovered = _recover(pending.job_id)
    assert recovered.review_status == "review_pending"
    assert recovered.complete is False
    assert recovered.approval is None
    assert recovered.generation.checksum_status == "matched"
    assert recovered.generation.receipt.measured_width == 2048
    assert recovered.reference_measurements
    assert recovered.reference_measurements[0].width == 1
    assert len(provider.requests) == calls
    manifest = build_delivery_manifest(recovered)
    assert manifest.complete is False
    assert manifest.approval is None
    assert manifest.checksum_status == "matched"


def test_approval_and_release_survive_only_when_the_records_exist() -> None:
    store = InMemoryJobStore()
    generated = execute_job_generate(
        store, job_id=_compiled(store).job_id, provider=FakeGenerationProvider()
    )
    pending = execute_job_critique(
        store,
        job_id=generated.job_id,
        model_id=CALLER_MODEL,
        provider=FakeCritiqueProvider(),
    )
    approved = approve_job(store, job_id=pending.job_id)
    recovered = _recover(approved.job_id)
    assert recovered.review_status == "owner_approved"
    assert recovered.approval is not None
    assert recovered.approval.owner_id == approved.owner_id
    assert recovered.complete is True
    assert recovered.release is None

    released = release_job(store, job_id=approved.job_id)
    again = _recover(released.job_id)
    assert again.review_status == "released"
    assert again.release is not None
    assert again.approval is not None

    artifacts = get_artifact_store()
    raw = json.loads(artifacts.get_artifact(released.job_id, "job.json").decode("utf-8"))
    raw["approval"] = None
    raw["release"] = None
    raw["review_status"] = "review_pending"
    raw["complete"] = False
    artifacts._write_bytes(
        artifacts.job_dir(released.job_id) / "job.json",
        json.dumps(raw).encode("utf-8"),
    )
    stale = json.loads(artifacts.get_artifact(released.job_id, "manifest.json").decode("utf-8"))
    stale["approval"] = {"owner_id": "invented"}
    stale["complete"] = True
    artifacts._write_bytes(
        artifacts.job_dir(released.job_id) / "manifest.json",
        json.dumps(stale).encode("utf-8"),
    )
    stripped = _recover(released.job_id)
    assert stripped.approval is None
    assert stripped.release is None
    assert stripped.review_status == "review_pending"
    assert stripped.complete is False
    assert build_delivery_manifest(stripped).approval is None
    assert build_delivery_manifest(stripped).complete is False


def test_recovery_keeps_generation_repair_and_critique_history() -> None:
    store = InMemoryJobStore()
    provider = FakeGenerationProvider()
    generated = execute_job_generate(
        store, job_id=_compiled(store).job_id, provider=provider
    )
    first = execute_job_critique(
        store,
        job_id=generated.job_id,
        model_id=CALLER_MODEL,
        provider=FakeCritiqueProvider("repair_required"),
    )
    repaired = execute_job_repair(
        store,
        job_id=first.job_id,
        planner=FakeRepairPlanner(),
        provider=provider,
    )
    second = execute_job_critique(
        store,
        job_id=repaired.job_id,
        model_id=CALLER_MODEL,
        provider=FakeCritiqueProvider(),
    )
    calls = len(provider.requests)
    recovered = _recover(second.job_id)
    assert len(provider.requests) == calls
    assert recovered.review_status == "review_pending"
    assert [item.operation.operation_key for item in recovered.generation_history] == [
        generated.generation.operation.operation_key
    ]
    assert recovered.generation.operation.operation_key == repaired.generation.operation.operation_key
    assert recovered.repair_count == 1
    assert recovered.repairs
    assert recovered.critique.result.generation_output_id == (
        recovered.generation.receipt.output.output_id
    )
    assert recovered.critique_history
    assert recovered.critique_history[0].result.generation_output_id == (
        generated.generation.receipt.output.output_id
    )
    manifest = build_delivery_manifest(recovered)
    assert manifest.generation_sequence == [1, 2]
    assert manifest.parent_generation == 1
    assert manifest.repair_history


def test_legacy_names_and_missing_metadata_still_load() -> None:
    store = InMemoryJobStore()
    generated = execute_job_generate(
        store, job_id=_compiled(store).job_id, provider=FakeGenerationProvider()
    )
    critiqued = execute_job_critique(
        store,
        job_id=generated.job_id,
        model_id=CALLER_MODEL,
        provider=FakeCritiqueProvider("repair_required"),
    )
    repaired = execute_job_repair(
        store,
        job_id=critiqued.job_id,
        planner=FakeRepairPlanner(),
        provider=FakeGenerationProvider(),
    )
    artifacts = get_artifact_store()
    job_dir = artifacts.job_dir(repaired.job_id)
    generation_payload = artifacts.get_artifact(repaired.job_id, "generations/01_initial.json")
    repair_payload = artifacts.get_artifact(
        repaired.job_id, "repairs/01_repair_generation_01_to_02.json"
    )
    generated_png = artifacts.get_artifact(repaired.job_id, "output/generated.png")
    artifacts._write_bytes(job_dir / "generations" / "1.json", generation_payload)
    artifacts._write_bytes(job_dir / "repairs" / "1.json", repair_payload)
    (job_dir / "generations" / "01_initial.json").unlink()
    (job_dir / "repairs" / "01_repair_generation_01_to_02.json").unlink()
    (job_dir / "repair.json").unlink()
    (job_dir / "output" / "current.png").unlink()
    (job_dir / "generations" / "02_repair.png").unlink()
    recovered = _recover(repaired.job_id)
    assert recovered.generation is not None
    assert recovered.generation.receipt.output is not None
    assert recovered.repairs
    assert recovered.reference_bytes[recovered.generation.receipt.output.output_id] == generated_png

    raw = json.loads(artifacts.get_artifact(repaired.job_id, "job.json").decode("utf-8"))
    raw.pop("reference_measurements", None)
    artifacts._write_bytes(job_dir / "job.json", json.dumps(raw).encode("utf-8"))
    generation = json.loads(artifacts.get_artifact(repaired.job_id, "generation.json").decode("utf-8"))
    receipt = generation["receipt"]
    for key in (
        "requested_width",
        "requested_height",
        "measured_width",
        "measured_height",
        "measured_format",
        "measured_mime",
    ):
        receipt.pop(key, None)
    receipt["format_check"] = "unmeasured"
    artifacts._write_bytes(
        job_dir / "generation.json",
        json.dumps(generation).encode("utf-8"),
    )
    legacy = _recover(repaired.job_id)
    assert legacy is not None
    assert legacy.reference_measurements == []
    assert legacy.generation.receipt.measured_width is None
    assert legacy.generation.receipt.format_check == "unmeasured"
    assert build_delivery_manifest(legacy).actual_width is None
    assert build_delivery_manifest(legacy).cost is None
