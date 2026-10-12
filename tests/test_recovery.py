"""Local/dev JobStore recovery from outputs/<job_id>/. No provider reruns."""

from __future__ import annotations

from pathlib import Path

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
from app.runtime.artifacts import FilesystemArtifactStore, get_artifact_store
from app.runtime.events import job_event
from app.runtime.jobs import create_job_from_intake
from app.runtime.recovery import reconstruct_job_record, recover_jobs_from_artifacts
from app.runtime.state import InMemoryJobStore, JOB_STORE
from tests.png_bytes import PNG_B64, PNG_HASH

CALLER_MODEL = "caller-supplied-model"
REAL_JOB_ID = "7a2dbd76-12d4-4edc-a8af-5368295ffcdc"
REPO_OUTPUTS = Path(__file__).resolve().parents[1] / "outputs"


def _contract(*, owner_id: str = "owner-recovery", contract_id: str = "contract-recovery-1") -> dict:
    return {
        "contract_id": contract_id,
        "revision": 1,
        "owner_id": owner_id,
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


def _client(
    generation: FakeGenerationProvider | None = None,
    critique: FakeCritiqueProvider | None = None,
) -> TestClient:
    JOB_STORE.clear()
    app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider("ready")
    app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()
    app.dependency_overrides[get_stylist_provider] = lambda: FakeStylistProvider()
    app.dependency_overrides[get_engine_compiler] = lambda: FakeEngineCompiler()
    app.dependency_overrides[get_generation_provider] = lambda: generation or FakeGenerationProvider()
    app.dependency_overrides[get_critique_provider] = lambda: critique or FakeCritiqueProvider()
    app.dependency_overrides[get_repair_planner] = lambda: FakeRepairPlanner()
    return TestClient(app)


def _seed_through(client: TestClient, *, through: str) -> str:
    job_id = create_job_from_intake(JOB_STORE, _contract()).job_id
    stages = [
        ("eye", f"/api/v1/jobs/{job_id}/eye", {}),
        ("brain", f"/api/v1/jobs/{job_id}/brain", {}),
        ("stylist", f"/api/v1/jobs/{job_id}/stylist", {}),
        ("compile", f"/api/v1/jobs/{job_id}/compile", {}),
        ("generate", f"/api/v1/jobs/{job_id}/generate", {}),
        ("critique", f"/api/v1/jobs/{job_id}/critique", {}),
    ]
    for name, path, body in stages:
        if name == "generate":
            assert client.post(f"/api/v1/jobs/{job_id}/generate/approve", json={}).status_code == 200
        assert client.post(path, json=body).status_code == 200
        if name == through:
            break
    return job_id


def _fresh_recover(job_id: str):
    JOB_STORE.clear()
    recovered = recover_jobs_from_artifacts(JOB_STORE)
    assert job_id in recovered
    record = JOB_STORE.get(job_id)
    assert record is not None
    return record


def test_full_recovery_through_generation() -> None:
    client = _client()
    job_id = _seed_through(client, through="generate")
    before = JOB_STORE.get(job_id)
    assert before is not None
    assert before.generation is not None
    assert before.generation.receipt is not None
    assert before.critique is None

    record = _fresh_recover(job_id)
    assert record.job_id == job_id
    assert record.owner_id == before.owner_id
    assert record.contract.contract_id == before.contract.contract_id
    assert record.revision == before.revision
    assert record.observation is not None
    assert record.brain is not None and record.brain.result is not None
    assert record.stylist is not None and record.stylist.result is not None
    assert record.engine is not None and record.engine.result is not None
    assert record.generation is not None
    assert record.generation.receipt is not None
    assert record.generation.status == "completed"
    assert record.generation.receipt.status == "completed"
    assert record.generation.operation.operation_key == before.generation.operation.operation_key
    assert record.generation.receipt.provider_receipt_id
    assert record.generation.receipt.output is not None
    assert record.critique is None
    assert record.stage == "generate"


def test_partial_recovery_job_and_eye_only() -> None:
    client = _client()
    job_id = _seed_through(client, through="eye")
    record = _fresh_recover(job_id)
    assert record.observation is not None
    assert record.readiness is not None
    assert record.brain is None
    assert record.stylist is None
    assert record.engine is None
    assert record.generation is None
    assert record.critique is None
    assert record.stage == "eye"


def test_critique_recovery() -> None:
    client = _client()
    job_id = _seed_through(client, through="critique")
    before = JOB_STORE.get(job_id)
    assert before is not None and before.critique is not None
    assessment = before.critique.result
    record = _fresh_recover(job_id)
    assert record.critique is not None
    assert record.critique.result is not None
    assert record.critique.result.model_dump(mode="json") == assessment.model_dump(mode="json")
    get_res = client.get(f"/api/v1/jobs/{job_id}/critique")
    assert get_res.status_code == 200
    assert get_res.json()["critique"]["assessment"]["overall_result"] == assessment.overall_result


def test_restart_continuation_post_critique_without_rerunning_generation() -> None:
    generation = FakeGenerationProvider()
    critique = FakeCritiqueProvider()
    client = _client(generation=generation, critique=critique)
    job_id = _seed_through(client, through="generate")
    assert len(generation.requests) == 1
    _fresh_recover(job_id)

    res = client.post(f"/api/v1/jobs/{job_id}/critique", json={})
    assert res.status_code == 200, res.text
    assert res.json()["stage"] == "critique"
    assert len(generation.requests) == 1
    assert len(critique.requests) == 1


def test_generation_idempotency_after_recovery() -> None:
    generation = FakeGenerationProvider()
    client = _client(generation=generation)
    job_id = _seed_through(client, through="generate")
    assert len(generation.requests) == 1
    _fresh_recover(job_id)

    res = client.post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert res.status_code == 200, res.text
    assert res.json()["generation"]["status"] == "completed"
    assert len(generation.requests) == 1


def test_get_endpoints_after_recovery() -> None:
    client = _client()
    job_id = _seed_through(client, through="generate")
    _fresh_recover(job_id)

    assert client.get(f"/api/v1/jobs/{job_id}").status_code == 200
    assert client.get(f"/api/v1/jobs/{job_id}/eye").status_code == 200
    assert client.get(f"/api/v1/jobs/{job_id}/brain").status_code == 200
    assert client.get(f"/api/v1/jobs/{job_id}/stylist").status_code == 200
    assert client.get(f"/api/v1/jobs/{job_id}/compile").status_code == 200
    gen = client.get(f"/api/v1/jobs/{job_id}/generate")
    assert gen.status_code == 200
    body = gen.json()["generation"]
    assert body["status"] == "completed"
    assert body["receipt"]["provider_receipt_id"]
    image = client.get(f"/api/v1/jobs/{job_id}/generate/image")
    assert image.status_code == 200


def test_malformed_artifact_does_not_crash_recovery() -> None:
    client = _client()
    valid_id = _seed_through(client, through="generate")
    artifacts = get_artifact_store()
    artifacts._write_json("broken-job", "job.json", {"not": "a phase0 contract"})
    artifacts._write_bytes(
        artifacts._resolve(valid_id, "stylist.json"),
        b"{not-json",
    )

    JOB_STORE.clear()
    recovered = recover_jobs_from_artifacts(JOB_STORE)
    assert valid_id in recovered
    assert JOB_STORE.get("broken-job") is None
    record = JOB_STORE.get(valid_id)
    assert record is not None
    assert record.observation is not None
    assert record.brain is not None
    assert record.stylist is None
    assert record.engine is not None
    assert record.generation is not None


def test_duplicate_recovery_does_not_overwrite_memory() -> None:
    client = _client()
    job_id = _seed_through(client, through="generate")
    artifacts = get_artifact_store()
    store = InMemoryJobStore()
    first = recover_jobs_from_artifacts(store, artifacts)
    assert first == [job_id]
    original = store.get(job_id)
    assert original is not None
    marked = original.model_copy(
        update={
            "events": [
                job_event(
                    kind="job_created",
                    stage="intake",
                    state="accepted",
                    contract_id=original.contract.contract_id,
                    revision=original.revision,
                )
            ]
        }
    )
    store.save(marked)
    second = recover_jobs_from_artifacts(store, artifacts)
    assert second == []
    kept = store.get(job_id)
    assert kept is not None
    assert kept.events == marked.events


def test_lifespan_recovers_jobs_from_outputs_dir() -> None:
    client = _client()
    job_id = _seed_through(client, through="generate")
    JOB_STORE.clear()
    assert JOB_STORE.get(job_id) is None
    with TestClient(app) as restarted:
        res = restarted.get(f"/api/v1/jobs/{job_id}")
        assert res.status_code == 200
        assert res.json()["job_id"] == job_id


def test_existing_outputs_job_is_recoverable_without_provider_calls() -> None:
    job_dir = REPO_OUTPUTS / REAL_JOB_ID
    if not (job_dir / "job.json").is_file():
        return
    generation = FakeGenerationProvider()
    artifacts = FilesystemArtifactStore(REPO_OUTPUTS)  # read-only recovery of an existing user job
    store = InMemoryJobStore()
    recovered = recover_jobs_from_artifacts(store, artifacts)
    assert REAL_JOB_ID in recovered
    record = store.get(REAL_JOB_ID)
    assert record is not None
    assert record.job_id == REAL_JOB_ID
    assert record.owner_id == "frontend-user-001"
    assert record.contract.contract_id == "midas-job-001"
    assert record.revision == 1
    assert record.observation is not None
    assert record.brain is not None
    assert record.stylist is not None
    assert record.engine is not None
    assert record.generation is not None
    assert record.generation.status == "completed"
    receipt = record.generation.receipt
    assert receipt is not None
    assert receipt.status == "completed"
    assert receipt.operation_key
    assert receipt.provider_receipt_id
    assert receipt.output is not None
    if record.critique is not None:
        assert record.critique.result is not None
        assert record.critique.result.job_id == REAL_JOB_ID
    assert generation.requests == []
    reconstruct_job_record(REAL_JOB_ID, artifacts)
    assert generation.requests == []
    assert (job_dir / "generation.json").is_file()


def test_recovery_preserves_repair_order_and_latest_generation() -> None:
    generation = FakeGenerationProvider()
    critique = FakeCritiqueProvider("repair_required")
    client = _client(generation=generation, critique=critique)
    job_id = _seed_through(client, through="critique")
    before = JOB_STORE.get(job_id)
    assert before is not None
    initial_key = before.generation.operation.operation_key
    initial_output = before.generation.receipt.output.output_id
    res = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert res.status_code == 200, res.text
    after = JOB_STORE.get(job_id)
    assert after is not None
    repaired_key = after.generation.operation.operation_key
    repaired_output = after.generation.receipt.output.output_id
    repaired_receipt = after.generation.receipt.provider_receipt_id
    assert repaired_key != initial_key
    record = _fresh_recover(job_id)
    assert record.repair_count == 1
    assert record.generation is not None
    assert record.generation.operation.operation_key == repaired_key
    assert record.generation.receipt is not None
    assert record.generation.receipt.output.output_id == repaired_output
    assert record.generation.receipt.provider_receipt_id == repaired_receipt
    assert record.generation_history
    assert record.generation_history[0].operation.operation_key == initial_key
    assert record.generation_history[0].receipt.output.output_id == initial_output
    assert initial_output in record.reference_bytes
    assert repaired_output in record.reference_bytes
    artifacts = get_artifact_store()
    job_dir = artifacts.job_dir(job_id)
    assert (job_dir / "generations" / "01_initial.png").is_file()
    assert (job_dir / "generations" / "02_repair.png").is_file()


def test_recovery_reads_legacy_generation_json_names() -> None:
    client = _client()
    job_id = _seed_through(client, through="generate")
    artifacts = get_artifact_store()
    job_dir = artifacts.job_dir(job_id)
    payload = artifacts.get_artifact(job_id, "generations/01_initial.json")
    assert payload is not None
    artifacts._write_bytes(job_dir / "generations" / "1.json", payload)
    (job_dir / "generations" / "01_initial.json").unlink()
    png = job_dir / "generations" / "01_initial.png"
    if png.is_file():
        png.unlink()
    record = _fresh_recover(job_id)
    assert record.generation is not None
    assert record.generation.receipt is not None
    assert record.generation.receipt.output is not None
