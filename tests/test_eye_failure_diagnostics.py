"""Sanitized Eye failure details stay on the job record. No live providers."""

from __future__ import annotations

import logging

import httpx

from app.api.jobs import get_eye_provider
from app.main import app
from app.providers.fake_eye import FakeEyeProvider
from app.providers.living_room_eye_observation import LivingRoomEyeMappingError
from app.runtime.jobs import EyeProviderFailedError, execute_job_eye
from app.runtime.model_policy import eye_model
from app.runtime.state import JOB_STORE
from tests.test_api_v1_jobs import _client, _freeze_job


class _SecretBoom:
    last_call = type(
        "Call",
        (),
        {
            "http_status": 401,
            "request_id": "req-eye-1",
            "response_id": None,
            "error_message": "Bearer sk-abcdefghijklmnopqrstuvwxyz 401",
            "raw_keys": ["choices"],
            "mapping_mismatches": [],
        },
    )()

    def observe(self, request):  # noqa: ANN001
        raise RuntimeError(
            "OpenRouter HTTP 401: Bearer sk-abcdefghijklmnopqrstuvwxyz secret leaked"
        )


class _TimeoutBoom:
    last_call = type(
        "Call",
        (),
        {
            "http_status": None,
            "request_id": None,
            "response_id": None,
            "error_message": None,
            "raw_keys": [],
            "mapping_mismatches": [],
        },
    )()

    def observe(self, request):  # noqa: ANN001
        raise httpx.TimeoutException("OpenRouter timed out")


class _MappingBoom:
    last_call = type(
        "Call",
        (),
        {
            "http_status": 200,
            "request_id": "req-eye-map",
            "response_id": "resp-eye-map",
            "error_message": None,
            "raw_keys": ["product_category"],
            "mapping_mismatches": ["missing category_candidates"],
        },
    )()

    def observe(self, request):  # noqa: ANN001
        raise LivingRoomEyeMappingError(["missing category_candidates"])


def test_api_eye_failure_returns_sanitized_http_details(caplog) -> None:  # noqa: ANN001
    app.dependency_overrides[get_eye_provider] = lambda: _SecretBoom()
    caplog.set_level(logging.WARNING, logger="app.runtime.jobs")
    try:
        client = _client()
        job_id = _freeze_job()
        response = client.post(f"/api/v1/jobs/{job_id}/eye", json={})
    finally:
        app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider()

    assert response.status_code == 502
    body = response.json()["error"]
    assert body["code"] == "PROVIDER_FAILURE"
    assert body["message"] == "Eye provider failed"
    details = body["details"]
    blob = str(details).lower()
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in blob
    assert "secret" not in blob
    assert details["exception_class"] == "RuntimeError"
    assert details["phase"] == "http_request"
    assert details["http_status"] == 401
    assert details["request_id"] == "req-eye-1"
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.error is not None
    assert stored.error.details == details
    status = client.get(f"/api/v1/jobs/{job_id}/status")
    assert status.status_code == 200
    assert status.json()["error"]["details"] == details
    dumped = (status.text + str(details)).lower()
    assert "authorization" not in dumped
    assert "content_base64" not in dumped
    assert any(
        "eye provider failed" in record.message
        and job_id in record.message
        and "http_request" in record.message
        and "RuntimeError" in record.message
        for record in caplog.records
    )


def test_api_eye_timeout_returns_timeout_phase() -> None:
    app.dependency_overrides[get_eye_provider] = lambda: _TimeoutBoom()
    try:
        client = _client()
        job_id = _freeze_job()
        response = client.post(f"/api/v1/jobs/{job_id}/eye", json={})
    finally:
        app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider()

    assert response.status_code == 502
    details = response.json()["error"]["details"]
    assert details["exception_class"] == "TimeoutException"
    assert details["phase"] == "timeout"
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.error is not None
    assert stored.error.details["phase"] == "timeout"


def test_api_eye_mapping_failure_persists_mismatches() -> None:
    app.dependency_overrides[get_eye_provider] = lambda: _MappingBoom()
    try:
        client = _client()
        job_id = _freeze_job()
        response = client.post(f"/api/v1/jobs/{job_id}/eye", json={})
    finally:
        app.dependency_overrides[get_eye_provider] = lambda: FakeEyeProvider()

    assert response.status_code == 502
    details = response.json()["error"]["details"]
    assert details["exception_class"] == "LivingRoomEyeMappingError"
    assert details["mapping_mismatches"] == ["missing category_candidates"]
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.error is not None
    assert stored.error.details == details


def test_execute_job_eye_keeps_details_when_raised() -> None:
    job_id = _freeze_job()

    class Boom:
        def observe(self, request):  # noqa: ANN001
            raise RuntimeError("forced diagnostic failure")

    try:
        execute_job_eye(
            JOB_STORE,
            job_id=job_id,
            model_id=eye_model(),
            provider=Boom(),
        )
    except EyeProviderFailedError as exc:
        assert exc.details["exception_class"] == "RuntimeError"
        assert "forced diagnostic failure" in exc.details["message"]
    else:
        raise AssertionError("expected EyeProviderFailedError")
    stored = JOB_STORE.get(job_id)
    assert stored is not None
    assert stored.error is not None
    assert stored.error.code == "PROVIDER_FAILURE"
    assert stored.error.details["exception_class"] == "RuntimeError"
    assert stored.error.details["phase"] == "provider_wrapper"
