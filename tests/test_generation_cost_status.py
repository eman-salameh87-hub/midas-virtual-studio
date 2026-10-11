"""Status exposes provider-recorded generation cost. No live provider calls."""

from fastapi.testclient import TestClient

from app.contracts.generation import ProviderCostEvidence
from app.main import app
from app.providers.fake_brain import FakeBrainProvider
from app.providers.fake_critique import FakeCritiqueProvider
from app.providers.fake_engine import FakeEngineCompiler
from app.providers.fake_eye import FakeEyeProvider
from app.providers.fake_generation import FakeGenerationProvider
from app.providers.fake_repair import FakeRepairPlanner
from app.providers.fake_stylist import FakeStylistProvider
from app.runtime.jobs import create_job_from_intake
from app.runtime.state import JOB_STORE
from app.api.jobs import (
    get_brain_provider,
    get_critique_provider,
    get_engine_compiler,
    get_eye_provider,
    get_generation_provider,
    get_repair_planner,
    get_stylist_provider,
)
from tests.test_repair import _contract


def _client(*, generation: FakeGenerationProvider | None = None, critique: FakeCritiqueProvider | None = None) -> TestClient:
    JOB_STORE.clear()
    app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider("ready")
    app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()
    app.dependency_overrides[get_stylist_provider] = lambda: FakeStylistProvider()
    app.dependency_overrides[get_engine_compiler] = lambda: FakeEngineCompiler()
    app.dependency_overrides[get_generation_provider] = lambda: generation or FakeGenerationProvider()
    app.dependency_overrides[get_critique_provider] = lambda: critique or FakeCritiqueProvider()
    app.dependency_overrides[get_repair_planner] = lambda: FakeRepairPlanner()
    return TestClient(app)


def _seed(client: TestClient, *, through: str = "generate") -> str:
    job_id = create_job_from_intake(JOB_STORE, _contract()).job_id
    steps = [
        ("eye", f"/api/v1/jobs/{job_id}/eye"),
        ("brain", f"/api/v1/jobs/{job_id}/brain"),
        ("stylist", f"/api/v1/jobs/{job_id}/stylist"),
        ("compile", f"/api/v1/jobs/{job_id}/compile"),
        ("generate", f"/api/v1/jobs/{job_id}/generate"),
        ("critique", f"/api/v1/jobs/{job_id}/critique"),
    ]
    for name, path in steps:
        if name == "generate":
            assert client.post(f"/api/v1/jobs/{job_id}/generate/approve", json={}).status_code == 200
        assert client.post(path, json={}).status_code == 200
        if name == through:
            break
    return job_id


def test_status_exposes_recorded_generation_cost() -> None:
    client = _client(
        generation=FakeGenerationProvider(
            provider_cost=ProviderCostEvidence(amount=0.101968, currency="USD", status="known")
        )
    )
    job_id = _seed(client)
    status = client.get(f"/api/v1/jobs/{job_id}/status").json()
    cost = status["generation_cost"]
    assert cost["amount"] == 0.101968
    assert cost["currency"] == "USD"
    assert cost["status"] == "known"
    assert cost["output_id"] == status["generation_output_id"]
    assert status["generation_output_id"]
    assert status["repair_generation_cost"] is None
    assert status["generation_cost_total"] is None
    generate = client.get(f"/api/v1/jobs/{job_id}/generate").json()
    assert generate["generation"]["receipt"]["provider_cost"]["amount"] == 0.101968


def test_missing_cost_is_not_recorded_as_zero() -> None:
    client = _client()
    job_id = _seed(client)
    status = client.get(f"/api/v1/jobs/{job_id}/status").json()
    cost = status["generation_cost"]
    assert cost["status"] == "not_recorded"
    assert cost["amount"] is None
    assert cost["currency"] is None
    unknown = _client(
        generation=FakeGenerationProvider(
            provider_cost=ProviderCostEvidence(amount=None, currency=None, status="unknown")
        )
    )
    unknown_id = _seed(unknown)
    unknown_cost = unknown.get(f"/api/v1/jobs/{unknown_id}/status").json()["generation_cost"]
    assert unknown_cost["status"] == "unknown"
    assert unknown_cost["amount"] is None


def test_repair_records_a_separate_generation_cost() -> None:
    client = _client(
        generation=FakeGenerationProvider(
            provider_costs=[
                ProviderCostEvidence(amount=0.04, currency="USD", status="known"),
                ProviderCostEvidence(amount=0.02, currency="USD", status="known"),
            ]
        ),
        critique=FakeCritiqueProvider("repair_required"),
    )
    job_id = _seed(client, through="critique")
    before = client.get(f"/api/v1/jobs/{job_id}/status").json()
    initial_id = before["generation_output_id"]
    assert before["generation_cost"]["amount"] == 0.04
    assert before["generation_cost"]["output_id"] == initial_id
    repaired = client.post(f"/api/v1/jobs/{job_id}/repair", json={})
    assert repaired.status_code == 200, repaired.text
    after = client.get(f"/api/v1/jobs/{job_id}/status").json()
    assert after["generation_output_id"] != initial_id
    assert after["generation_cost"]["amount"] == 0.02
    assert after["generation_cost"]["output_id"] == after["generation_output_id"]
    assert after["initial_generation_cost"]["amount"] == 0.04
    assert after["initial_generation_cost"]["output_id"] == initial_id
    assert after["repair_generation_cost"]["amount"] == 0.02
    assert after["generation_cost_total"]["amount"] == 0.06
    assert after["generation_cost_total"]["status"] == "known"
