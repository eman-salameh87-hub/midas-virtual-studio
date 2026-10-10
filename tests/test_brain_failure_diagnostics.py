"""Sanitized Brain failure details stay on the job record. No live providers."""

from __future__ import annotations

import logging

from pydantic import BaseModel, ValidationError

from app.providers.failure import provider_failure_details, sanitize_provider_text
from app.runtime.jobs import BrainProviderFailedError, execute_job_brain
from app.runtime.model_policy import brain_model
from app.runtime.state import JOB_STORE
from tests.test_api_v1_brain import _create_job, _run_eye, _client
from app.api.jobs import get_brain_provider
from app.main import app
from app.providers.fake_brain import FakeBrainProvider


class _Schema(BaseModel):
    mode: str


class _ValidationBoom:
    def reason(self, request):  # noqa: ANN001
        _Schema.model_validate({"mode": {"nested": True}})


class _SecretBoom:
    last_call = type(
        "Call",
        (),
        {
            "http_status": 401,
            "request_id": "req-1",
            "response_id": None,
            "error_message": "Bearer sk-abcdefghijklmnopqrstuvwxyz 401",
            "raw_keys": ["choices"],
            "mapping_mismatches": [],
        },
    )()

    def reason(self, request):  # noqa: ANN001
        raise RuntimeError(
            "OpenRouter HTTP 401: Bearer sk-abcdefghijklmnopqrstuvwxyz secret leaked"
        )


def test_sanitize_provider_text_redacts_bearer_and_sk_tokens() -> None:
    text = sanitize_provider_text(
        "OpenRouter HTTP 401: Bearer sk-abcdefghijklmnopqrstuvwxyz secret leaked"
    )
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in text
    assert "Bearer [redacted]" in text
    assert "secret" not in text.lower()


def test_sanitize_provider_text_redacts_env_api_key(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setenv("OPENROUTER_API_KEY", "local-dev-key-value-xyz")
    text = sanitize_provider_text("failed with local-dev-key-value-xyz in body")
    assert "local-dev-key-value-xyz" not in text
    assert "[redacted]" in text


def test_stored_brain_failure_keeps_validation_errors() -> None:
    app.dependency_overrides[get_brain_provider] = lambda: _ValidationBoom()
    try:
        client = _client()
        job_id = _create_job(client)
        _run_eye(client, job_id)
        response = client.post(f"/api/v1/jobs/{job_id}/brain", json={})
    finally:
        app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()

    assert response.status_code == 502
    api_details = response.json()["error"]["details"]
    assert api_details["exception_class"] == "ValidationError"
    assert api_details["phase"] == "structured_output_parsing"
    assert api_details["validation_errors"]
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.error is not None
    assert stored.error.details == api_details
    status = client.get(f"/api/v1/jobs/{job_id}/status")
    assert status.json()["error"]["details"]["validation_errors"] == api_details["validation_errors"]
    dumped = status.text.lower()
    assert "authorization" not in dumped
    assert "content_base64" not in dumped


def test_stored_brain_failure_redacts_secrets_and_logs_phase(caplog) -> None:  # noqa: ANN001
    app.dependency_overrides[get_brain_provider] = lambda: _SecretBoom()
    caplog.set_level(logging.WARNING, logger="app.runtime.jobs")
    try:
        client = _client()
        job_id = _create_job(client)
        _run_eye(client, job_id)
        response = client.post(f"/api/v1/jobs/{job_id}/brain", json={})
    finally:
        app.dependency_overrides[get_brain_provider] = lambda: FakeBrainProvider()

    assert response.status_code == 502
    details = response.json()["error"]["details"]
    blob = str(details).lower()
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in blob
    assert "secret" not in blob
    assert details["phase"] == "http_request"
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.error is not None
    assert stored.error.details["phase"] == "http_request"
    assert stored.error.details["http_status"] == 401
    assert any(
        "brain provider failed" in record.message
        and job_id in record.message
        and "http_request" in record.message
        for record in caplog.records
    )


def test_provider_failure_details_redact_validation_messages() -> None:
    try:
        _Schema.model_validate({"mode": 1})
    except ValidationError as exc:
        details = provider_failure_details(exc)
    else:
        raise AssertionError("expected ValidationError")
    assert details["exception_class"] == "ValidationError"
    assert details["validation_errors"]
    blob = str(details)
    assert "Bearer" not in blob
    assert "OPENROUTER_API_KEY" not in blob


def test_execute_job_brain_keeps_details_when_raised() -> None:
    client = _client()
    job_id = _create_job(client)
    _run_eye(client, job_id)

    class Boom:
        def reason(self, request):  # noqa: ANN001
            raise RuntimeError("forced diagnostic failure")

    try:
        execute_job_brain(
            JOB_STORE,
            job_id=job_id,
            model_id=brain_model(),
            provider=Boom(),
        )
    except BrainProviderFailedError as exc:
        assert exc.details["exception_class"] == "RuntimeError"
        assert "forced diagnostic failure" in exc.details["message"]
    else:
        raise AssertionError("expected BrainProviderFailedError")
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.error is not None
    assert stored.error.code == "PROVIDER_FAILURE"
    assert stored.error.details["exception_class"] == "RuntimeError"
    assert stored.error.details["phase"] == "provider_wrapper"
