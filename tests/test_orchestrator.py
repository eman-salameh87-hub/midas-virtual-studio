"""Phase 0–1 planning orchestrator. Fake providers only. No live calls."""

from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

from app.api.jobs import (
    get_brain_provider,
    get_engine_compiler,
    get_eye_provider,
    get_generation_provider,
    get_stylist_provider,
)
from app.main import app
from app.providers.engine import EngineProviderRequest
from app.providers.eye import EyeProviderRequest
from app.providers.fake_brain import FakeBrainProvider
from app.providers.fake_engine import FakeEngineCompiler
from app.providers.fake_eye import FakeEyeProvider
from app.providers.fake_generation import FakeGenerationProvider
from app.providers.fake_stylist import FakeStylistProvider
from app.runtime.jobs import JobNotFoundError, create_job_from_intake
from app.runtime.orchestrator import (
    advance_planning,
    join_scheduled_planning,
)
from app.runtime.state import JOB_STORE
from tests.png_bytes import PNG_B64, PNG_HASH


def _intake() -> dict:
    return {
        "contract_id": "contract-orchestrator-1",
        "revision": 1,
        "owner_id": "owner-orchestrator",
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


def _create_job() -> str:
    record = create_job_from_intake(JOB_STORE, _intake())
    return record.job_id


def _advance(
    job_id: str,
    *,
    eye: FakeEyeProvider | None = None,
    brain: FakeBrainProvider | None = None,
    stylist: FakeStylistProvider | None = None,
    compiler: FakeEngineCompiler | None = None,
):
    return advance_planning(
        JOB_STORE,
        job_id=job_id,
        eye_provider=eye or FakeEyeProvider(),
        brain_provider=brain or FakeBrainProvider(),
        stylist_provider=stylist or FakeStylistProvider(),
        compiler=compiler or FakeEngineCompiler(),
    )


class SlowFakeEyeProvider(FakeEyeProvider):
    def __init__(self, delay: float = 0.2) -> None:
        super().__init__("ready")
        self.delay = delay

    def observe(self, request: EyeProviderRequest):
        time.sleep(self.delay)
        return super().observe(request)


class FailingEyeProvider:
    def __init__(self) -> None:
        self.requests: list[EyeProviderRequest] = []

    def observe(self, request: EyeProviderRequest):
        self.requests.append(request)
        raise RuntimeError("forced eye failure")


class FailingBrainProvider(FakeBrainProvider):
    def reason(self, request):
        self.requests.append(request)
        raise RuntimeError("forced brain failure")


class FailingEngineCompiler(FakeEngineCompiler):
    def compile(self, request: EngineProviderRequest):
        self.requests.append(request)
        raise RuntimeError("forced compile failure")


def test_advance_planning_runs_eye_brain_stylist_compile_and_not_generate() -> None:
    generation = FakeGenerationProvider()
    eye = FakeEyeProvider()
    brain = FakeBrainProvider()
    stylist = FakeStylistProvider()
    compiler = FakeEngineCompiler()
    job_id = _create_job()

    record = _advance(
        job_id, eye=eye, brain=brain, stylist=stylist, compiler=compiler
    )

    assert record.stage == "compile"
    assert record.state == "ready"
    assert record.observation is not None
    assert record.brain is not None and record.brain.result is not None
    assert record.stylist is not None and record.stylist.result is not None
    assert record.engine is not None and record.engine.result is not None
    assert record.engine.result.status == "ready"
    assert record.generation is None
    assert record.critique is None
    assert record.repair is None
    assert record.approval is None
    assert record.pre_generation_approval is None
    assert record.release is None
    assert len(eye.requests) == 1
    assert len(brain.requests) == 1
    assert len(stylist.requests) == 1
    assert len(compiler.requests) == 1
    assert generation.requests == []


class GatedFakeEyeProvider(FakeEyeProvider):
    def __init__(self) -> None:
        super().__init__("ready")
        self.started = threading.Event()
        self.release = threading.Event()

    def observe(self, request: EyeProviderRequest):
        self.started.set()
        assert self.release.wait(timeout=5)
        return super().observe(request)


def test_scheduled_planning_runs_eye_brain_stylist_compile_in_order() -> None:
    order: list[str] = []

    class OrderedEye(FakeEyeProvider):
        def observe(self, request: EyeProviderRequest):
            order.append("eye")
            return super().observe(request)

    class OrderedBrain(FakeBrainProvider):
        def reason(self, request):
            order.append("brain")
            return super().reason(request)

    class OrderedStylist(FakeStylistProvider):
        def compose(self, request):
            order.append("stylist")
            return super().compose(request)

    class OrderedCompiler(FakeEngineCompiler):
        def compile(self, request: EngineProviderRequest):
            order.append("compile")
            return super().compile(request)

    generation = FakeGenerationProvider()
    app.dependency_overrides[get_eye_provider] = lambda: OrderedEye()
    app.dependency_overrides[get_brain_provider] = lambda: OrderedBrain()
    app.dependency_overrides[get_stylist_provider] = lambda: OrderedStylist()
    app.dependency_overrides[get_engine_compiler] = lambda: OrderedCompiler()
    app.dependency_overrides[get_generation_provider] = lambda: generation
    client = TestClient(app)
    job_id = client.post("/api/v1/jobs", json={"contract": _intake()}).json()["job_id"]
    assert join_scheduled_planning(job_id)
    assert order == ["eye", "brain", "stylist", "compile"]
    assert generation.requests == []
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.generation is None
    assert stored.critique is None
    assert stored.repair is None
    assert stored.approval is None
    assert stored.release is None


def test_post_jobs_returns_intake_before_planning_finishes() -> None:
    eye = GatedFakeEyeProvider()
    brain = FakeBrainProvider()
    stylist = FakeStylistProvider()
    compiler = FakeEngineCompiler()
    generation = FakeGenerationProvider()
    app.dependency_overrides[get_eye_provider] = lambda: eye
    app.dependency_overrides[get_brain_provider] = lambda: brain
    app.dependency_overrides[get_stylist_provider] = lambda: stylist
    app.dependency_overrides[get_engine_compiler] = lambda: compiler
    app.dependency_overrides[get_generation_provider] = lambda: generation
    try:
        client = TestClient(app)
        response = client.post("/api/v1/jobs", json={"contract": _intake()})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["stage"] == "intake"
        assert body["state"] == "accepted"
        assert body["status"] == "accepted"
        assert "observation" not in body
        job_id = body["job_id"]
        assert eye.started.wait(timeout=5)
        stored = JOB_STORE.get(job_id)
        assert stored is not None
        assert stored.observation is None
        assert stored.generation is None
        assert generation.requests == []

        first_status = client.get(f"/api/v1/jobs/{job_id}/status")
        second_status = client.get(f"/api/v1/jobs/{job_id}/status")
        assert first_status.status_code == 200
        assert second_status.status_code == 200
        assert first_status.json()["stage"] == "intake"
        assert len(eye.requests) == 0

        eye.release.set()
        assert join_scheduled_planning(job_id)
        stored = JOB_STORE.get(job_id)
        assert stored is not None
        assert stored.stage == "compile"
        assert stored.state == "ready"
        assert stored.generation is None
        assert len(eye.requests) == 1
        assert len(brain.requests) == 1
        assert len(stylist.requests) == 1
        assert len(compiler.requests) == 1
        assert generation.requests == []
    finally:
        eye.release.set()
        join_scheduled_planning()


def test_post_jobs_hold_stops_scheduled_planning() -> None:
    eye = FakeEyeProvider("critical_identity_ambiguity")
    brain = FakeBrainProvider()
    generation = FakeGenerationProvider()
    app.dependency_overrides[get_eye_provider] = lambda: eye
    app.dependency_overrides[get_brain_provider] = lambda: brain
    app.dependency_overrides[get_generation_provider] = lambda: generation
    client = TestClient(app)
    response = client.post("/api/v1/jobs", json={"contract": _intake()})
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    assert join_scheduled_planning(job_id)
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.state == "hold"
    assert stored.stage == "eye"
    assert stored.brain is None
    assert brain.requests == []
    assert generation.requests == []
    assert stored.generation is None


def test_scheduled_planning_exceptions_do_not_crash_the_api(monkeypatch) -> None:
    def boom(*_args, **_kwargs):
        raise RuntimeError("forced scheduler failure")

    monkeypatch.setattr("app.runtime.orchestrator.advance_planning", boom)
    client = TestClient(app)
    response = client.post("/api/v1/jobs", json={"contract": _intake()})
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    assert join_scheduled_planning(job_id)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.generation is None


def test_status_polling_does_not_schedule_planning() -> None:
    eye = FakeEyeProvider()
    app.dependency_overrides[get_eye_provider] = lambda: eye
    client = TestClient(app)
    response = client.post("/api/v1/jobs", json={"contract": _intake()})
    job_id = response.json()["job_id"]
    assert join_scheduled_planning(job_id)
    assert len(eye.requests) == 1
    client.get(f"/api/v1/jobs/{job_id}/status")
    client.get(f"/api/v1/jobs/{job_id}")
    client.get(f"/api/v1/jobs/{job_id}/status")
    assert len(eye.requests) == 1


def test_http_skip_still_applies_after_scheduled_planning() -> None:
    eye = FakeEyeProvider()
    brain = FakeBrainProvider()
    stylist = FakeStylistProvider()
    compiler = FakeEngineCompiler()
    app.dependency_overrides[get_eye_provider] = lambda: eye
    app.dependency_overrides[get_brain_provider] = lambda: brain
    app.dependency_overrides[get_stylist_provider] = lambda: stylist
    app.dependency_overrides[get_engine_compiler] = lambda: compiler
    client = TestClient(app)
    job_id = client.post("/api/v1/jobs", json={"contract": _intake()}).json()["job_id"]
    assert join_scheduled_planning(job_id)
    assert client.post(f"/api/v1/jobs/{job_id}/eye", json={}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/brain", json={}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/stylist", json={}).status_code == 200
    assert client.post(f"/api/v1/jobs/{job_id}/compile", json={}).status_code == 200
    assert len(eye.requests) == 1
    assert len(brain.requests) == 1
    assert len(stylist.requests) == 1
    assert len(compiler.requests) == 1


def test_eye_hold_stops_before_brain() -> None:
    eye = FakeEyeProvider("critical_identity_ambiguity")
    brain = FakeBrainProvider()
    stylist = FakeStylistProvider()
    compiler = FakeEngineCompiler()
    job_id = _create_job()

    record = _advance(
        job_id, eye=eye, brain=brain, stylist=stylist, compiler=compiler
    )

    assert record.stage == "eye"
    assert record.state == "hold"
    assert record.readiness is not None
    assert record.readiness.status == "hold"
    assert record.brain is None
    assert len(eye.requests) == 1
    assert brain.requests == []
    assert stylist.requests == []
    assert compiler.requests == []


def test_brain_hold_stops_before_stylist() -> None:
    brain = FakeBrainProvider(violation="hold")
    stylist = FakeStylistProvider()
    compiler = FakeEngineCompiler()
    job_id = _create_job()

    record = _advance(job_id, brain=brain, stylist=stylist, compiler=compiler)

    assert record.stage == "brain"
    assert record.state == "hold"
    assert record.brain is not None
    assert record.brain.result is not None
    assert record.brain.result.status == "hold"
    assert record.stylist is None
    assert record.engine is None
    assert stylist.requests == []
    assert compiler.requests == []


def test_stylist_hold_stops_before_compile() -> None:
    stylist = FakeStylistProvider(violation="hold")
    compiler = FakeEngineCompiler()
    job_id = _create_job()

    record = _advance(job_id, stylist=stylist, compiler=compiler)

    assert record.stage == "stylist"
    assert record.state == "hold"
    assert record.engine is None
    assert compiler.requests == []


def test_eye_provider_failure_stops_planning() -> None:
    eye = FailingEyeProvider()
    brain = FakeBrainProvider()
    job_id = _create_job()

    record = _advance(job_id, eye=eye, brain=brain)

    assert record.state == "failed"
    assert record.stage == "eye"
    assert record.observation is None
    assert record.brain is None
    assert record.error is not None
    assert record.error.code == "PROVIDER_FAILURE"
    assert record.error.message == "Eye provider failed"
    assert record.error.details["exception_class"] == "RuntimeError"
    assert record.error.details["phase"] == "provider_wrapper"
    assert "forced eye failure" in str(record.error.details["message"])
    assert len(eye.requests) == 1
    assert brain.requests == []


def test_brain_provider_failure_stops_planning() -> None:
    brain = FailingBrainProvider()
    stylist = FakeStylistProvider()
    job_id = _create_job()

    record = _advance(job_id, brain=brain, stylist=stylist)

    assert record.state == "failed"
    assert record.stage == "brain"
    assert record.brain is not None
    assert record.brain.status == "failed"
    assert record.error is not None
    assert record.error.code == "PROVIDER_FAILURE"
    assert record.error.message == "Brain provider failed"
    assert record.error.details["exception_class"] == "RuntimeError"
    assert record.error.details["phase"] == "provider_wrapper"
    assert "forced brain failure" in str(record.error.details["message"])
    assert record.stylist is None
    assert stylist.requests == []


def test_compile_provider_failure_stops_after_stylist() -> None:
    compiler = FailingEngineCompiler()
    job_id = _create_job()

    record = _advance(job_id, compiler=compiler)

    assert record.state == "failed"
    assert record.stage == "compile"
    assert record.stylist is not None
    assert record.stylist.result is not None
    assert record.engine is not None
    assert record.engine.status == "failed"
    assert len(compiler.requests) == 1


def test_repeat_advance_planning_does_not_rerun_completed_stages() -> None:
    eye = FakeEyeProvider()
    brain = FakeBrainProvider()
    stylist = FakeStylistProvider()
    compiler = FakeEngineCompiler()
    job_id = _create_job()

    first = _advance(job_id, eye=eye, brain=brain, stylist=stylist, compiler=compiler)
    second = _advance(job_id, eye=eye, brain=brain, stylist=stylist, compiler=compiler)

    assert first.engine is not None
    assert second.engine is not None
    assert second.engine.result == first.engine.result
    assert len(eye.requests) == 1
    assert len(brain.requests) == 1
    assert len(stylist.requests) == 1
    assert len(compiler.requests) == 1


def test_http_planning_posts_skip_completed_orchestrator_stages() -> None:
    eye = FakeEyeProvider()
    brain = FakeBrainProvider()
    stylist = FakeStylistProvider()
    compiler = FakeEngineCompiler()
    app.dependency_overrides[get_eye_provider] = lambda: eye
    app.dependency_overrides[get_brain_provider] = lambda: brain
    app.dependency_overrides[get_stylist_provider] = lambda: stylist
    app.dependency_overrides[get_engine_compiler] = lambda: compiler
    try:
        client = TestClient(app)
        created = client.post("/api/v1/jobs", json={"contract": _intake()})
        assert created.status_code == 200, created.text
        job_id = created.json()["job_id"]

        _advance(job_id, eye=eye, brain=brain, stylist=stylist, compiler=compiler)
        assert client.post(f"/api/v1/jobs/{job_id}/eye", json={}).status_code == 200
        assert client.post(f"/api/v1/jobs/{job_id}/brain", json={}).status_code == 200
        assert client.post(f"/api/v1/jobs/{job_id}/stylist", json={}).status_code == 200
        assert client.post(f"/api/v1/jobs/{job_id}/compile", json={}).status_code == 200

        assert len(eye.requests) == 1
        assert len(brain.requests) == 1
        assert len(stylist.requests) == 1
        assert len(compiler.requests) == 1
    finally:
        app.dependency_overrides.pop(get_stylist_provider, None)


def test_concurrent_advance_planning_runs_each_stage_once() -> None:
    eye = SlowFakeEyeProvider(delay=0.15)
    brain = FakeBrainProvider()
    stylist = FakeStylistProvider()
    compiler = FakeEngineCompiler()
    job_id = _create_job()
    results: list[str] = []
    errors: list[BaseException] = []

    def run() -> None:
        try:
            record = _advance(
                job_id, eye=eye, brain=brain, stylist=stylist, compiler=compiler
            )
            results.append(record.stage)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert results == ["compile", "compile"]
    assert len(eye.requests) == 1
    assert len(brain.requests) == 1
    assert len(stylist.requests) == 1
    assert len(compiler.requests) == 1
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.generation is None


def test_concurrent_http_eye_and_advance_planning_share_the_job_lock() -> None:
    eye = SlowFakeEyeProvider(delay=0.2)
    brain = FakeBrainProvider()
    stylist = FakeStylistProvider()
    compiler = FakeEngineCompiler()
    app.dependency_overrides[get_eye_provider] = lambda: eye
    app.dependency_overrides[get_brain_provider] = lambda: brain
    app.dependency_overrides[get_stylist_provider] = lambda: stylist
    app.dependency_overrides[get_engine_compiler] = lambda: compiler
    try:
        client = TestClient(app)
        created = client.post("/api/v1/jobs", json={"contract": _intake()})
        assert created.status_code == 200, created.text
        job_id = created.json()["job_id"]
        errors: list[BaseException] = []

        def run_orchestrator() -> None:
            try:
                _advance(job_id, eye=eye, brain=brain, stylist=stylist, compiler=compiler)
            except BaseException as exc:
                errors.append(exc)

        def run_http() -> None:
            try:
                response = client.post(f"/api/v1/jobs/{job_id}/eye", json={})
                assert response.status_code == 200, response.text
            except BaseException as exc:
                errors.append(exc)

        orchestrator = threading.Thread(target=run_orchestrator)
        http = threading.Thread(target=run_http)
        orchestrator.start()
        time.sleep(0.05)
        http.start()
        orchestrator.join()
        http.join()

        assert errors == []
        assert len(eye.requests) == 1
    finally:
        app.dependency_overrides.pop(get_stylist_provider, None)


def test_unknown_job_raises() -> None:
    try:
        advance_planning(
            JOB_STORE,
            job_id="missing-job",
            eye_provider=FakeEyeProvider(),
            brain_provider=FakeBrainProvider(),
            stylist_provider=FakeStylistProvider(),
            compiler=FakeEngineCompiler(),
        )
    except JobNotFoundError as exc:
        assert exc.job_id == "missing-job"
    else:
        raise AssertionError("expected JobNotFoundError")
