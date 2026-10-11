"""Local .env loading for persist identity. Does not mint canonical identity."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.runtime.client_briefs import CLIENT_BRIEF_STORE
from app.runtime.dev_identity import (
    DEFAULT_DEV_REVISION,
    IDENTITY_NOT_CONFIGURED,
    load_dev_persist_identity,
    load_operator_dotenv,
)
from app.runtime.state import JOB_STORE
from tests.test_client_brief import _minimal_uimidas_payload

_EXAMPLE_OWNER = "dev-owner"
_EXAMPLE_CONTRACT = "dev-contract"


def _client() -> TestClient:
    return TestClient(app)


def _write_env(path: Path, text: str) -> Path:
    env_path = path / ".env"
    env_path.write_text(text, encoding="utf-8")
    return env_path


def _clear_identity_env(monkeypatch) -> None:
    monkeypatch.delenv("MIDAS_DEV_OWNER_ID", raising=False)
    monkeypatch.delenv("MIDAS_DEV_CONTRACT_ID", raising=False)
    monkeypatch.delenv("MIDAS_DEV_CONTRACT_REVISION", raising=False)


def test_operator_dotenv_loads_identity_from_env_file(monkeypatch, tmp_path: Path) -> None:
    _clear_identity_env(monkeypatch)
    env_path = _write_env(
        tmp_path,
        "MIDAS_DEV_OWNER_ID=local-owner-from-file\n"
        "MIDAS_DEV_CONTRACT_ID=local-contract-from-file\n",
    )
    identity = load_dev_persist_identity(dotenv_path=env_path)
    assert identity is not None
    assert identity.owner_id == "local-owner-from-file"
    assert identity.contract_id == "local-contract-from-file"
    assert identity.revision == DEFAULT_DEV_REVISION


def test_operator_dotenv_does_not_override_process_environment(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MIDAS_DEV_OWNER_ID", "process-owner")
    monkeypatch.setenv("MIDAS_DEV_CONTRACT_ID", "process-contract")
    monkeypatch.setenv("MIDAS_DEV_CONTRACT_REVISION", "4")
    env_path = _write_env(
        tmp_path,
        "MIDAS_DEV_OWNER_ID=file-owner\n"
        "MIDAS_DEV_CONTRACT_ID=file-contract\n"
        "MIDAS_DEV_CONTRACT_REVISION=9\n",
    )
    identity = load_dev_persist_identity(dotenv_path=env_path)
    assert identity is not None
    assert identity.owner_id == "process-owner"
    assert identity.contract_id == "process-contract"
    assert identity.revision == 4


def test_missing_dotenv_values_are_fail_closed(monkeypatch, tmp_path: Path) -> None:
    _clear_identity_env(monkeypatch)
    env_path = _write_env(tmp_path, "OPENROUTER_API_KEY=\n")
    assert load_dev_persist_identity(dotenv_path=env_path) is None


def test_blank_dotenv_values_are_fail_closed(monkeypatch, tmp_path: Path) -> None:
    _clear_identity_env(monkeypatch)
    env_path = _write_env(
        tmp_path,
        "MIDAS_DEV_OWNER_ID=   \nMIDAS_DEV_CONTRACT_ID=\n",
    )
    assert load_dev_persist_identity(dotenv_path=env_path) is None


def test_python_module_does_not_hardcode_example_identity_values() -> None:
    source = Path("app/runtime/dev_identity.py").read_text(encoding="utf-8")
    assert _EXAMPLE_OWNER not in source
    assert _EXAMPLE_CONTRACT not in source
    assert "load_dotenv" in source
    assert ".env.example" in source


def test_operator_dotenv_does_not_load_env_example(tmp_path: Path) -> None:
    example = tmp_path / ".env.example"
    example.write_text(
        f"MIDAS_DEV_OWNER_ID={_EXAMPLE_OWNER}\nMIDAS_DEV_CONTRACT_ID={_EXAMPLE_CONTRACT}\n",
        encoding="utf-8",
    )
    loaded = load_operator_dotenv(dotenv_path=tmp_path / ".env")
    assert loaded is False


def test_persist_from_dotenv_file_without_process_env(
    monkeypatch, tmp_path: Path
) -> None:
    _clear_identity_env(monkeypatch)
    env_path = _write_env(
        tmp_path,
        "MIDAS_DEV_OWNER_ID=file-persist-owner\n"
        "MIDAS_DEV_CONTRACT_ID=file-persist-contract\n",
    )
    monkeypatch.setattr(
        "app.runtime.dev_identity.load_operator_dotenv",
        lambda **_kwargs: load_operator_dotenv(dotenv_path=env_path),
    )
    response = _client().post(
        "/api/v1/client-briefs",
        json={"client_brief": _minimal_uimidas_payload()},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["owner_id"] == "file-persist-owner"
    assert body["contract_id"] == "file-persist-contract"
    assert body["revision"] == DEFAULT_DEV_REVISION
    assert list(JOB_STORE._jobs) == []  # noqa: SLF001


def test_production_without_identity_config_does_not_persist(
    monkeypatch, tmp_path: Path
) -> None:
    _clear_identity_env(monkeypatch)
    empty_env = _write_env(tmp_path, "")
    monkeypatch.setattr(
        "app.runtime.dev_identity.load_operator_dotenv",
        lambda **_kwargs: load_operator_dotenv(dotenv_path=empty_env),
    )
    response = _client().post(
        "/api/v1/client-briefs",
        json={"client_brief": _minimal_uimidas_payload()},
    )
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == IDENTITY_NOT_CONFIGURED
    assert ".env" in error["message"]
    assert list(JOB_STORE._jobs) == []  # noqa: SLF001
    assert CLIENT_BRIEF_STORE._briefs == {}  # noqa: SLF001
    assert list(tmp_path.rglob("client_brief.json")) == []
