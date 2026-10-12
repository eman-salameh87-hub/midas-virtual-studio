"""Evaluation execution mode must not write into the user outputs/ directory."""

from __future__ import annotations

import os
from pathlib import Path

from app.runtime.artifacts import (
    canonical_user_outputs_root,
    default_outputs_root,
    get_artifact_store,
    reset_artifact_store,
    user_outputs_root,
)
from app.runtime.execution_mode import EVALUATION, USER, set_execution_mode
from app.runtime.jobs import create_job
from app.runtime.state import InMemoryJobStore, JOB_STORE
from tests.png_bytes import PNG_1X1, PNG_HASH
from tests.test_artifacts import _contract


def test_evaluation_jobs_do_not_write_user_outputs(
    tmp_path: Path, monkeypatch
) -> None:  # noqa: ANN001
    monkeypatch.delenv("MIDAS_OUTPUTS_DIR", raising=False)
    eval_root = tmp_path / "evaluation_outputs"
    monkeypatch.setenv("MIDAS_EVALUATION_OUTPUTS_DIR", str(eval_root))
    user_root = tmp_path / "user-outputs-sentinel"
    monkeypatch.setattr("app.runtime.artifacts.user_outputs_root", lambda: user_root)
    set_execution_mode(EVALUATION)
    reset_artifact_store()
    user_root.mkdir()
    before = {path.name for path in user_root.iterdir()}

    record = create_job(JOB_STORE, _contract(), {"ref-product": PNG_1X1})
    store = get_artifact_store()
    assert user_root.resolve() not in store.root.resolve().parents
    assert store.root.resolve() != user_root.resolve()
    assert store.get_artifact(record.job_id, "job.json") is not None
    assert (eval_root / record.job_id / "job.json").is_file()
    assert {path.name for path in user_root.iterdir()} == before
    assert not (user_root / record.job_id).exists()

    from app.runtime.recovery import recover_jobs_from_artifacts

    recovered_store = InMemoryJobStore()
    recovered_ids = recover_jobs_from_artifacts(recovered_store)
    assert record.job_id not in recovered_ids


def test_evaluation_mode_ignores_user_outputs_dir_override(
    tmp_path: Path, monkeypatch
) -> None:  # noqa: ANN001
    user_root = tmp_path / "outputs"
    eval_root = tmp_path / "evaluation_outputs"
    monkeypatch.setenv("MIDAS_OUTPUTS_DIR", str(user_root))
    monkeypatch.setenv("MIDAS_EVALUATION_OUTPUTS_DIR", str(eval_root))
    set_execution_mode(EVALUATION)
    reset_artifact_store()
    user_root.mkdir()
    record = create_job(JOB_STORE, _contract(), {"ref-product": PNG_1X1})
    assert (eval_root / record.job_id / "job.json").is_file()
    assert not (user_root / record.job_id).exists()
    assert user_outputs_root().resolve() == user_root.resolve()
    assert default_outputs_root().resolve() == eval_root.resolve()


def test_pytest_cannot_create_entries_in_canonical_user_outputs(
    monkeypatch,
) -> None:  # noqa: ANN001
    repo_outputs = canonical_user_outputs_root()
    monkeypatch.delenv("MIDAS_OUTPUTS_DIR", raising=False)
    set_execution_mode(USER)
    reset_artifact_store()
    before = set()
    if repo_outputs.exists():
        before = {path.name for path in repo_outputs.iterdir()}

    record = create_job(JOB_STORE, _contract(), {"ref-product": PNG_1X1})
    store = get_artifact_store()
    after = set()
    if repo_outputs.exists():
        after = {path.name for path in repo_outputs.iterdir()}
    assert after == before
    assert not (repo_outputs / record.job_id).exists()
    assert store.root.resolve() != repo_outputs.resolve()
    assert repo_outputs.resolve() not in store.root.resolve().parents
    assert store.get_artifact(record.job_id, "job.json") is not None
    assert os.getenv("PYTEST_CURRENT_TEST")


def test_user_jobs_still_persist_under_outputs_root(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    user_root = tmp_path / "outputs"
    monkeypatch.setenv("MIDAS_OUTPUTS_DIR", str(user_root))
    set_execution_mode(USER)
    reset_artifact_store()
    record = create_job(JOB_STORE, _contract(), {"ref-product": PNG_1X1})
    assert (user_root / record.job_id / "job.json").is_file()
    assert (user_root / record.job_id / "manifest.json").is_file()
    assert default_outputs_root().resolve() == user_root.resolve()
    assert user_outputs_root().resolve() == user_root.resolve()
    from app.runtime.recovery import recover_jobs_from_artifacts

    recovered_store = InMemoryJobStore()
    recovered_ids = recover_jobs_from_artifacts(recovered_store)
    assert record.job_id in recovered_ids
    restored = recovered_store.get(record.job_id)
    assert restored is not None
    assert restored.contract.references[0].content_hash == PNG_HASH
