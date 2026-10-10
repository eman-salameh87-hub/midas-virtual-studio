"""UIMidas Manual persist-only integration. Does not create jobs or generate."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.runtime.client_briefs import CLIENT_BRIEF_STORE
from app.runtime.dev_identity import IDENTITY_NOT_CONFIGURED, INCOMPLETE_PERSIST_IDENTITY
from app.runtime.state import JOB_STORE
from tests.test_client_brief import _minimal_uimidas_payload, _populated_uimidas_payload

_DEV_OWNER = "dev-owner-local"
_DEV_CONTRACT = "dev-contract-local"


def _client() -> TestClient:
    return TestClient(app)


def _clear_dev_identity(monkeypatch) -> None:
    monkeypatch.delenv("MIDAS_DEV_OWNER_ID", raising=False)
    monkeypatch.delenv("MIDAS_DEV_CONTRACT_ID", raising=False)
    monkeypatch.delenv("MIDAS_DEV_CONTRACT_REVISION", raising=False)
    monkeypatch.setattr(
        "app.runtime.dev_identity.load_operator_dotenv",
        lambda **_kwargs: False,
    )


def _set_dev_identity(monkeypatch) -> None:
    monkeypatch.setenv("MIDAS_DEV_OWNER_ID", _DEV_OWNER)
    monkeypatch.setenv("MIDAS_DEV_CONTRACT_ID", _DEV_CONTRACT)
    monkeypatch.setenv("MIDAS_DEV_CONTRACT_REVISION", "1")


def test_uimidas_envelope_persists_with_dev_identity_and_is_retrievable(
    monkeypatch,
) -> None:
    _set_dev_identity(monkeypatch)
    planning_calls: list[object] = []

    def _no_planning(*_args: object, **_kwargs: object) -> None:
        planning_calls.append(True)

    monkeypatch.setattr("app.api.jobs.schedule_planning", _no_planning)
    monkeypatch.setattr("app.runtime.orchestrator.advance_planning", _no_planning)

    payload = _populated_uimidas_payload()
    assert payload["ownerIdentity"]["value"] is None
    created = _client().post("/api/v1/client-briefs", json={"client_brief": payload})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["owner_id"] == _DEV_OWNER
    assert body["contract_id"] == _DEV_CONTRACT
    assert body["revision"] == 1
    assert body["client_brief"] == payload
    assert body["client_brief"]["ownerIdentity"]["value"] is None
    brief_id = body["brief_id"]

    fetched = _client().get(f"/api/v1/client-briefs/{brief_id}")
    assert fetched.status_code == 200
    assert fetched.json()["brief_id"] == brief_id
    assert fetched.json()["client_brief"] == payload
    assert fetched.json()["brief_hash"] == body["brief_hash"]

    owned = _client().get(
        f"/api/v1/client-briefs/{brief_id}",
        params={"owner_id": _DEV_OWNER},
    )
    assert owned.status_code == 200

    assert planning_calls == []
    assert list(JOB_STORE._jobs) == []  # noqa: SLF001


def test_missing_dev_identity_does_not_persist(monkeypatch, tmp_path: Path) -> None:
    _clear_dev_identity(monkeypatch)
    planning_calls: list[object] = []
    monkeypatch.setattr(
        "app.api.jobs.schedule_planning",
        lambda *_args, **_kwargs: planning_calls.append(True),
    )
    payload = _minimal_uimidas_payload()
    response = _client().post("/api/v1/client-briefs", json={"client_brief": payload})
    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == IDENTITY_NOT_CONFIGURED
    assert "MIDAS_DEV_OWNER_ID" in error["message"]
    assert "MIDAS_DEV_CONTRACT_ID" in error["message"]
    assert list(JOB_STORE._jobs) == []  # noqa: SLF001
    assert planning_calls == []
    assert list(tmp_path.rglob("client_brief.json")) == []
    assert CLIENT_BRIEF_STORE._briefs == {}  # noqa: SLF001


def test_partial_request_identity_is_rejected_without_persisting(monkeypatch) -> None:
    _clear_dev_identity(monkeypatch)
    response = _client().post(
        "/api/v1/client-briefs",
        json={
            "owner_id": "only-owner",
            "client_brief": _minimal_uimidas_payload(),
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == INCOMPLETE_PERSIST_IDENTITY
    assert CLIENT_BRIEF_STORE._briefs == {}  # noqa: SLF001


def test_explicit_request_identity_still_works_without_dev_env(monkeypatch) -> None:
    _clear_dev_identity(monkeypatch)
    response = _client().post(
        "/api/v1/client-briefs",
        json={
            "owner_id": "caller-owner",
            "contract_id": "caller-contract",
            "revision": 3,
            "client_brief": _minimal_uimidas_payload(),
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["owner_id"] == "caller-owner"
    assert body["contract_id"] == "caller-contract"
    assert body["revision"] == 3
    fetched = _client().get(f"/api/v1/client-briefs/{body['brief_id']}")
    assert fetched.status_code == 200
    assert list(JOB_STORE._jobs) == []  # noqa: SLF001
