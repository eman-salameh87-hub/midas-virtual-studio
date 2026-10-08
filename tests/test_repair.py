"""Bounded Critique → Repair tests. No live provider calls."""

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
from app.runtime.artifacts import get_artifact_store
from app.runtime.jobs import execute_job_repair
from app.runtime.recovery import recover_jobs_from_artifacts
from app.runtime.state import JOB_STORE
from app.stages.repair import (
    LOCAL_EDIT_UNSUPPORTED_REASON,
    new_regressions,
    previous_defects_unresolved,
)
from tests.png_bytes import PNG_B64, PNG_HASH

CALLER_MODEL = "caller-supplied-model"
REPO_ROOT = Path(__file__).resolve().parents[1]


def _contract() -> dict:
    return {
        "contract_id": "contract-towel-repair-1",
        "revision": 1,
        "owner_id": "owner-repair",
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
    *,
    critique: FakeCritiqueProvider | None = None,
    generation: FakeGenerationProvider | None = None,
    planner: FakeRepairPlanner | None = None,
) -> TestClient:
    JOB_STORE.clear()
    app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider("ready")
    app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()
    app.dependency_overrides[get_stylist_provider] = lambda: FakeStylistProvider()
    app.dependency_overrides[get_engine_compiler] = lambda: FakeEngineCompiler()
    app.dependency_overrides[get_generation_provider] = lambda: generation or FakeGenerationProvider()
    app.dependency_overrides[get_critique_provider] = lambda: critique or FakeCritiqueProvider(
        "repair_required"
    )
    app.dependency_overrides[get_repair_planner] = lambda: planner or FakeRepairPlanner()
    return TestClient(app)


def _seed_critiqued(
    client: TestClient,
    *,
    through: str = "critique",
) -> str:
    job_id = client.post("/api/v1/jobs", json={"contract": _contract()}).json()["job_id"]
    steps = [
        ("eye", f"/api/v1/jobs/{job_id}/eye", {}),
        ("brain", f"/api/v1/jobs/{job_id}/brain", {}),
        ("stylist", f"/api/v1/jobs/{job_id}/stylist", {}),
        ("compile", f"/api/v1/jobs/{job_id}/compile", {}),
        ("generate", f"/api/v1/jobs/{job_id}/generate", {}),
        ("critique", f"/api/v1/jobs/{job_id}/critique", {}),
    ]
    for name, path, body in steps:
        if name == "generate":
            assert client.post(f"/api/v1/jobs/{job_id}/generate/approve", json={}).status_code == 200
        assert client.post(path, json=body).status_code == 200
        if name == through:
            break
    return job_id


def test_a_critique_to_repair_plan() -> None:
    client = _client()
    job_id = _seed_critiqued(client)
    record = JOB_STORE.get(job_id)
    assert record is not None
    assert record.repair_count == 0
    res = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert res.status_code == 200, res.text
    plan = res.json()["repair"]["plan"]
    assert plan["action"] == "fresh_render"
    assert "geometry" in plan["target_regions"]
    assert plan["repair_instructions"]
    assert "inventory" in plan["preserve_list"]
    assert "identity" in plan["preserve_list"]


def test_e_repair_count_starts_at_zero() -> None:
    client = _client()
    job_id = _seed_critiqued(client)
    assert JOB_STORE.get(job_id).repair_count == 0


def test_b_c_d_named_defects_preserve_original() -> None:
    generation = FakeGenerationProvider()
    client = _client(generation=generation)
    job_id = _seed_critiqued(client)
    res = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert res.status_code == 200, res.text
    body = res.json()["repair"]["plan"]
    assert body["original_reference_id"] == "ref-towel"
    assert "geometry" in body["target_regions"]
    assert "lighting" not in body["target_regions"]
    assert "composition" in body["preserve_list"]
    repair_request = generation.requests[-1]
    assert "ref-towel" in repair_request.operation.reference_ids
    assert repair_request.operation.reference_ids[0] == "ref-towel"
    assert "ref-towel" in repair_request.reference_bytes
    assert "MIDAS bounded repair" in repair_request.operation.exact_prompt
    assert body["lineage"]["original_reference_id"] == "ref-towel"


def test_f_g_h_repair_budget_two_then_hold() -> None:
    critique = FakeCritiqueProvider(violations=["repair_required", "repair_required", "repair_required"])
    generation = FakeGenerationProvider()
    client = _client(critique=critique, generation=generation)
    job_id = _seed_critiqued(client)
    seed_dispatches = len(generation.requests)
    first = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert first.status_code == 200, first.text
    assert first.json()["repair"]["repair_count"] == 1
    assert client.post(
        f"/api/v1/jobs/{job_id}/critique", json={}
    ).status_code == 200
    second = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert second.status_code == 200
    assert second.json()["repair"]["repair_count"] == 2
    assert client.post(
        f"/api/v1/jobs/{job_id}/critique", json={}
    ).status_code == 200
    third = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert third.status_code == 200, third.text
    body = third.json()
    assert body["state"] == "hold"
    assert body["repair"]["plan"]["action"] == "hold"
    assert body["repair"]["repair_count"] == 2
    assert "budget" in " ".join(body["repair"]["plan"]["hold_reasons"])
    assert len(generation.requests) == seed_dispatches + 2


def test_i_repair_requires_critique() -> None:
    client = _client()
    job_id = _seed_critiqued(client, through="generate")
    res = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CRITIQUE_NOT_RUN"


def test_j_critique_ready_prevents_repair() -> None:
    client = _client(critique=FakeCritiqueProvider())
    job_id = _seed_critiqued(client)
    res = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "REPAIR_NOT_REQUIRED"


def test_k_l_new_version_does_not_overwrite_previous() -> None:
    client = _client()
    job_id = _seed_critiqued(client)
    before = JOB_STORE.get(job_id)
    assert before is not None
    old_output = before.generation.receipt.output.output_id
    old_key = before.generation.operation.operation_key
    old_bytes = before.reference_bytes[old_output]
    res = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert res.status_code == 200
    after = JOB_STORE.get(job_id)
    assert after is not None
    new_output = after.generation.receipt.output.output_id
    assert new_output != old_output
    assert after.generation.operation.operation_key != old_key
    assert after.reference_bytes[old_output] == old_bytes
    assert after.generation_history
    assert after.generation_history[0].operation.operation_key == old_key
    stored_old = get_artifact_store().get_artifact(job_id, "generations/01_initial.json")
    assert stored_old is not None


def test_m_n_o_rereview_unresolved_and_regression() -> None:
    critique = FakeCritiqueProvider(
        violations=["repair_required", "repair_required", "regression"]
    )
    client = _client(critique=critique)
    job_id = _seed_critiqued(client)
    first_assessment = JOB_STORE.get(job_id).critique.result
    assert client.post(
        f"/api/v1/jobs/{job_id}/repair", json={}
    ).status_code == 200
    second = client.post(
        f"/api/v1/jobs/{job_id}/critique", json={}
    )
    assert second.status_code == 200
    assert len(critique.requests) == 2
    assert (
        critique.requests[1].critique_input.generated_output_id
        != critique.requests[0].critique_input.generated_output_id
    )
    second_assessment = JOB_STORE.get(job_id).critique.result
    assert previous_defects_unresolved(first_assessment, second_assessment) == ["geometry"]
    assert client.post(
        f"/api/v1/jobs/{job_id}/repair", json={}
    ).status_code == 200
    third = client.post(
        f"/api/v1/jobs/{job_id}/critique", json={}
    )
    assert third.status_code == 200
    third_assessment = JOB_STORE.get(job_id).critique.result
    assert "inventory" in new_regressions(second_assessment, third_assessment)
    assert third_assessment.overall_result == "repair_required"


def test_p_completed_repair_is_idempotent() -> None:
    generation = FakeGenerationProvider()
    client = _client(generation=generation)
    job_id = _seed_critiqued(client)
    seed_dispatches = len(generation.requests)
    first = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    second = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert first.status_code == 200
    assert second.status_code == 200
    assert len(generation.requests) == seed_dispatches + 1
    assert first.json()["repair"]["plan"]["operation"]["operation_key"] == second.json()[
        "repair"
    ]["plan"]["operation"]["operation_key"]


def test_q_r_restart_recovery_does_not_redispatch() -> None:
    generation = FakeGenerationProvider()
    client = _client(generation=generation)
    job_id = _seed_critiqued(client)
    seed_dispatches = len(generation.requests)
    assert client.post(
        f"/api/v1/jobs/{job_id}/repair", json={}
    ).status_code == 200
    assert len(generation.requests) == seed_dispatches + 1
    JOB_STORE.clear()
    recovered = recover_jobs_from_artifacts(JOB_STORE)
    assert job_id in recovered
    record = JOB_STORE.get(job_id)
    assert record is not None
    assert record.repair_count == 1
    assert record.repair is not None
    assert record.repair.plan.operation is not None
    assert record.generation_history
    again = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert again.status_code == 200
    assert len(generation.requests) == seed_dispatches + 1


def test_s_unsupported_local_edit_holds() -> None:
    generation = FakeGenerationProvider()
    client = _client(generation=generation, planner=FakeRepairPlanner(action="local_edit"))
    job_id = _seed_critiqued(client)
    seed_dispatches = len(generation.requests)
    res = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["state"] == "hold"
    assert body["repair"]["plan"]["action"] == "hold"
    assert LOCAL_EDIT_UNSUPPORTED_REASON in body["repair"]["plan"]["hold_reasons"]
    assert body["repair"]["repair_count"] == 0
    assert len(generation.requests) == seed_dispatches


def test_t_original_reference_remains_authoritative() -> None:
    generation = FakeGenerationProvider()
    client = _client(generation=generation)
    job_id = _seed_critiqued(client)
    client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    request = generation.requests[-1]
    assert request.operation.reference_ids[0] == "ref-towel"
    compile_ids = [item.reference_id for item in request.compile.references]
    assert "ref-towel" in compile_ids
    assert request.reference_bytes["ref-towel"]


def test_get_repair_never_dispatches() -> None:
    generation = FakeGenerationProvider()
    client = _client(generation=generation)
    job_id = _seed_critiqued(client)
    client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    count = len(generation.requests)
    res = client.get(f"/api/v1/jobs/{job_id}/repair")
    assert res.status_code == 200
    assert len(generation.requests) == count


def test_synthetic_job_can_enter_repair_without_writing_repo_outputs() -> None:
    generation = FakeGenerationProvider()
    client = _client(generation=generation)
    job_id = _seed_critiqued(client)
    record = JOB_STORE.get(job_id)
    assert record is not None
    assert record.critique is not None
    assert record.critique.result is not None
    assert record.critique.result.overall_result == "repair_required"
    assert record.repair_count == 0

    findings = []
    for item in record.critique.result.findings:
        if item.dimension == "details":
            findings.append(
                item.model_copy(
                    update={
                        "result": "fail",
                        "severity": "medium",
                        "observation": "woven texture and seam placement differ from the original",
                        "repair_instruction": "restore woven texture and seam placement",
                    }
                )
            )
        else:
            findings.append(item)
    patched = record.model_copy(
        update={
            "critique": record.critique.model_copy(
                update={
                    "result": record.critique.result.model_copy(
                        update={"findings": findings}
                    )
                }
            )
        }
    )
    JOB_STORE.save(patched)

    seed_dispatches = len(generation.requests)
    updated = execute_job_repair(
        JOB_STORE,
        job_id=job_id,
        planner=FakeRepairPlanner(),
        provider=generation,
    )
    assert updated.repair is not None
    assert updated.repair.plan.action == "fresh_render"
    assert "geometry" in updated.repair.plan.target_regions
    assert "details" in updated.repair.plan.target_regions
    assert "inventory" in updated.repair.plan.preserve_list
    assert updated.repair.plan.original_reference_id == "ref-towel"
    assert updated.repair_count == 1
    assert generation.requests[seed_dispatches:]
    assert not (REPO_ROOT / "outputs" / job_id / "repair.json").exists()


def test_repair_openapi_does_not_default_to_gpt_41() -> None:
    client = _client()
    schema = client.get("/openapi.json").json()
    path = schema["paths"]["/api/v1/jobs/{job_id}/repair"]["post"]
    description = path.get("description") or ""
    assert "openai/gpt-4.1" not in description
    assert "compiled" in description.lower()
    body = path["requestBody"]["content"]["application/json"]["schema"]
    if "$ref" in body:
        ref = body["$ref"].rsplit("/", 1)[-1]
        body = schema["components"]["schemas"][ref]
    properties = body.get("properties") or {}
    assert "model_id" in properties
    assert properties["model_id"]["default"] == "google/gemini-3.1-flash-image"
    job_id = _seed_critiqued(client)
    rejected = client.post(
        f"/api/v1/jobs/{job_id}/repair", json={"model_id": "openai/gpt-4.1"}
    )
    assert rejected.status_code == 422


def test_repair_generation_uses_compile_image_model() -> None:
    generation = FakeGenerationProvider()
    client = _client(generation=generation)
    job_id = _seed_critiqued(client)
    record = JOB_STORE.get(job_id)
    assert record is not None and record.engine is not None
    compile_model = record.engine.result.model_id
    assert compile_model != "openai/gpt-4.1"
    res = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert res.status_code == 200, res.text
    plan = res.json()["repair"]["plan"]
    assert plan["operation"]["model_id"] == compile_model
    assert generation.requests[-1].operation.model_id == compile_model


def test_ordered_human_readable_artifact_names() -> None:
    critique = FakeCritiqueProvider(violations=["repair_required", "repair_required"])
    client = _client(critique=critique)
    job_id = _seed_critiqued(client)
    artifacts = get_artifact_store()
    job_dir = artifacts.job_dir(job_id)
    assert (job_dir / "generations" / "01_initial.png").is_file()
    assert (job_dir / "critiques" / "01_critique_generation_01.json").is_file()
    assert (job_dir / "output" / "current.png").is_file()
    assert artifacts.get_artifact(job_id, "critiques/01_critique_generation_01.json")
    res = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert res.status_code == 200, res.text
    assert (job_dir / "generations" / "02_repair.png").is_file()
    assert (job_dir / "repairs" / "01_repair_generation_01_to_02.json").is_file()
    second = client.post(f"/api/v1/jobs/{job_id}/critique", json={})
    assert second.status_code == 200, second.text
    assert (job_dir / "critiques" / "02_critique_generation_02.json").is_file()
    initial = artifacts.get_artifact(job_id, "generations/01_initial.json")
    repaired = artifacts.get_artifact(job_id, "generations/02_repair.json")
    assert initial is not None and repaired is not None
    assert b'"operation_key"' in initial
    assert b'"sequence_index": 1' in initial
    assert b'"sequence_index": 2' in repaired
