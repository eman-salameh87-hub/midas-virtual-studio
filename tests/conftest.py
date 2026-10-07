import pytest

from app.api.jobs import (
    get_brain_provider,
    get_critique_provider,
    get_engine_compiler,
    get_eye_provider,
    get_generation_provider,
    get_repair_planner,
)
from app.main import app
from app.providers.fake_brain import FakeBrainProvider
from app.providers.fake_engine import FakeEngineCompiler
from app.providers.fake_eye import FakeEyeProvider
from app.providers.fake_critique import FakeCritiqueProvider
from app.providers.fake_generation import FakeGenerationProvider
from app.providers.fake_repair import FakeRepairPlanner
from app.runtime.artifacts import reset_artifact_store
from app.runtime.state import JOB_STORE


@pytest.fixture(autouse=True)
def clear_job_store() -> None:
    JOB_STORE.clear()
    yield
    JOB_STORE.clear()


@pytest.fixture(autouse=True)
def isolated_artifact_store(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIDAS_OUTPUTS_DIR", str(tmp_path / "outputs"))
    reset_artifact_store()
    yield
    reset_artifact_store()


@pytest.fixture(autouse=True)
def use_fake_eye_unless_live(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("live_provider"):
        yield
        return
    app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider()
    yield
    app.dependency_overrides.pop(get_eye_provider, None)


@pytest.fixture(autouse=True)
def use_fake_brain_unless_live(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("live_provider"):
        yield
        return
    app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()
    yield
    app.dependency_overrides.pop(get_brain_provider, None)


@pytest.fixture(autouse=True)
def use_fake_engine_unless_live(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("live_provider"):
        yield
        return
    app.dependency_overrides[get_engine_compiler] = lambda: FakeEngineCompiler()
    yield
    app.dependency_overrides.pop(get_engine_compiler, None)


@pytest.fixture(autouse=True)
def use_fake_generation_unless_live(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("live_provider"):
        yield
        return
    app.dependency_overrides[get_generation_provider] = lambda: FakeGenerationProvider()
    yield
    app.dependency_overrides.pop(get_generation_provider, None)


@pytest.fixture(autouse=True)
def use_fake_critique_unless_live(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("live_provider"):
        yield
        return
    app.dependency_overrides[get_critique_provider] = lambda: FakeCritiqueProvider()
    yield
    app.dependency_overrides.pop(get_critique_provider, None)


@pytest.fixture(autouse=True)
def use_fake_repair_unless_live(request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("live_provider"):
        yield
        return
    app.dependency_overrides[get_repair_planner] = lambda: FakeRepairPlanner()
    yield
    app.dependency_overrides.pop(get_repair_planner, None)
