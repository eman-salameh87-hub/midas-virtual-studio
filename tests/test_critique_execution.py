import pytest

from app.providers.fake_brain import FakeBrainProvider
from app.providers.fake_critique import FakeCritiqueProvider
from app.providers.fake_engine import FakeEngineCompiler
from app.providers.fake_eye import FakeEyeProvider
from app.providers.fake_generation import FakeGenerationProvider
from app.providers.fake_stylist import FakeStylistProvider
from app.runtime.artifacts import get_artifact_store
from app.runtime.jobs import (
    CritiqueProviderFailedError,
    GenerationNotReadyError,
    GenerationNotRunError,
    JobOwnerMismatchError,
    RevisionMismatchError,
    create_job,
    execute_job_brain,
    execute_job_compile,
    execute_job_critique,
    execute_job_eye,
    execute_job_generate,
    execute_job_stylist,
)
from app.runtime.state import InMemoryJobStore
from tests.test_generation_execution import _compiled, _contract
from tests.png_bytes import PNG_1X1

CALLER_MODEL = "caller-supplied-model"


def _generated(store: InMemoryJobStore):
    compiled = _compiled(store)
    return execute_job_generate(
        store, job_id=compiled.job_id, provider=FakeGenerationProvider()
    )


def test_fake_critique_records_request_and_passes() -> None:
    store = InMemoryJobStore()
    generated = _generated(store)
    provider = FakeCritiqueProvider()
    updated = execute_job_critique(
        store,
        job_id=generated.job_id,
        model_id=CALLER_MODEL,
        provider=provider,
    )
    assert len(provider.requests) == 1
    assert provider.requests[0].original_bytes == PNG_1X1
    assert provider.requests[0].generated_bytes
    assert updated.critique is not None
    assert updated.critique.result is not None
    assert updated.critique.result.overall_result == "pass"
    assert updated.events[-1].kind == "critique_completed"


def test_critique_cannot_run_without_generation() -> None:
    store = InMemoryJobStore()
    compiled = _compiled(store)
    with pytest.raises(GenerationNotRunError):
        execute_job_critique(
            store,
            job_id=compiled.job_id,
            model_id=CALLER_MODEL,
            provider=FakeCritiqueProvider(),
        )


def test_critique_rejects_incomplete_generation() -> None:
    store = InMemoryJobStore()
    compiled = _compiled(store)
    execute_job_generate(
        store, job_id=compiled.job_id, provider=FakeGenerationProvider(mode="uncertain")
    )
    with pytest.raises(GenerationNotReadyError):
        execute_job_critique(
            store,
            job_id=compiled.job_id,
            model_id=CALLER_MODEL,
            provider=FakeCritiqueProvider(),
        )


def test_critique_rejects_missing_generated_output() -> None:
    store = InMemoryJobStore()
    generated = _generated(store)
    receipt = generated.generation.receipt
    assert receipt is not None and receipt.output is not None
    stripped = dict(generated.reference_bytes)
    stripped.pop(receipt.output.output_id, None)
    store.save(generated.model_copy(update={"reference_bytes": stripped}))
    artifacts = get_artifact_store()
    output_path = artifacts.job_dir(generated.job_id) / "output" / "generated.png"
    if output_path.exists():
        output_path.unlink()
    with pytest.raises(GenerationNotReadyError):
        execute_job_critique(
            store,
            job_id=generated.job_id,
            model_id=CALLER_MODEL,
            provider=FakeCritiqueProvider(),
        )


def test_successful_critique_persists_artifact() -> None:
    store = InMemoryJobStore()
    generated = _generated(store)
    updated = execute_job_critique(
        store,
        job_id=generated.job_id,
        model_id=CALLER_MODEL,
        provider=FakeCritiqueProvider(),
    )
    artifacts = get_artifact_store()
    saved = artifacts.get_artifact(updated.job_id, "critique.json")
    assert saved is not None
    assert b"overall_result" in saved
    assert updated.stage == "critique"


def test_critique_hold_is_persisted() -> None:
    store = InMemoryJobStore()
    generated = _generated(store)
    updated = execute_job_critique(
        store,
        job_id=generated.job_id,
        model_id=CALLER_MODEL,
        provider=FakeCritiqueProvider("hold"),
    )
    assert updated.state == "hold"
    assert updated.critique is not None
    assert updated.critique.result is not None
    assert updated.critique.result.overall_result == "hold"


def test_critique_owner_and_revision_mismatch() -> None:
    store = InMemoryJobStore()
    generated = _generated(store)
    with pytest.raises(JobOwnerMismatchError):
        execute_job_critique(
            store,
            job_id=generated.job_id,
            model_id=CALLER_MODEL,
            provider=FakeCritiqueProvider(),
            owner_id="wrong-owner",
        )
    with pytest.raises(RevisionMismatchError):
        execute_job_critique(
            store,
            job_id=generated.job_id,
            model_id=CALLER_MODEL,
            provider=FakeCritiqueProvider(),
            revision=99,
        )


def test_critique_provider_failure() -> None:
    store = InMemoryJobStore()
    generated = _generated(store)
    with pytest.raises(CritiqueProviderFailedError):
        execute_job_critique(
            store,
            job_id=generated.job_id,
            model_id=CALLER_MODEL,
            provider=FakeCritiqueProvider("wrong_job"),
        )
    stored = store.get(generated.job_id)
    assert stored is not None
    assert stored.state == "failed"
    assert stored.events[-1].kind == "critique_failed"


def test_generation_stage_helpers_still_import() -> None:
    assert _contract().intent.requested_outcomes == ["Lifestyle"]
    assert callable(execute_job_eye)
    assert callable(execute_job_brain)
    assert callable(execute_job_stylist)
    assert callable(execute_job_compile)
    assert callable(FakeEyeProvider)
    assert callable(FakeBrainProvider)
    assert callable(FakeEngineCompiler)
