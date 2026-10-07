"""Safe diagnostic details for provider failures.

These details are for development and tests. They must not include API keys,
Authorization headers, image bytes, or full provider payloads.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx
from pydantic import ValidationError

from app.stages.brain import BrainPlanInvalidError
from app.stages.critique import CritiqueAssessmentInvalidError

_BEARER = re.compile(r"Bearer\s+\S+", re.IGNORECASE)
_LONG_TOKEN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
_SECRET_WORDS = re.compile(r"(api[_-]?key|authorization|secret leaked)", re.IGNORECASE)
_MESSAGE_LIMIT = 240

_HTTP_MARKERS = (
    "OpenRouter HTTP",
    "OPENROUTER_API_KEY is empty",
    "OpenRouter response was not JSON",
    "OpenRouter response JSON was not an object",
    "OpenRouter response had no choices",
    "OpenRouter choice",
    "OpenRouter message content was empty",
)
_JSON_MARKERS = (
    "was not JSON",
    "not a JSON object",
    "model JSON was not an object",
    "model content was not a JSON object",
)


def sanitize_provider_text(value: str) -> str:
    text = _BEARER.sub("Bearer [redacted]", value)
    text = _LONG_TOKEN.sub("[redacted]", text)
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if api_key.strip():
        text = text.replace(api_key, "[redacted]")
    text = _SECRET_WORDS.sub("[redacted]", text)
    text = " ".join(text.split())
    if len(text) > _MESSAGE_LIMIT:
        text = text[: _MESSAGE_LIMIT].rstrip() + "…"
    return text


def provider_failure_details(
    exc: BaseException,
    provider: object | None = None,
) -> dict[str, Any]:
    """Build a public-safe PROVIDER_FAILURE details object."""

    phase = _phase(exc)
    details: dict[str, Any] = {
        "exception_class": type(exc).__name__,
        "phase": phase,
        "message": sanitize_provider_text(str(exc) or type(exc).__name__),
    }
    if isinstance(exc, ValidationError):
        details["validation_errors"] = [
            {
                "type": item.get("type"),
                "loc": [str(part) for part in item.get("loc", ())],
                "msg": sanitize_provider_text(str(item.get("msg", ""))),
            }
            for item in exc.errors()[:12]
        ]
    record = getattr(provider, "last_call", None)
    if record is not None:
        http_status = getattr(record, "http_status", None)
        if http_status is not None:
            details["http_status"] = http_status
        request_id = getattr(record, "request_id", None)
        if request_id:
            details["request_id"] = request_id
        response_id = getattr(record, "response_id", None)
        if response_id:
            details["response_id"] = response_id
        error_message = getattr(record, "error_message", None)
        if error_message:
            details["provider_error"] = sanitize_provider_text(error_message)
        raw_keys = getattr(record, "raw_keys", None)
        if raw_keys:
            details["parsed_keys"] = list(raw_keys)[:40]
        mismatches = getattr(record, "mapping_mismatches", None)
        if mismatches:
            details["mapping_mismatches"] = [
                sanitize_provider_text(str(item)) for item in list(mismatches)[:8]
            ]
    return details


def _phase(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout"
    if isinstance(exc, BrainPlanInvalidError):
        return "brain_plan_validation"
    if isinstance(exc, CritiqueAssessmentInvalidError):
        return "critique_assessment_validation"
    if isinstance(exc, ValidationError):
        return "structured_output_parsing"
    if isinstance(exc, httpx.RequestError):
        return "http_request"
    text = str(exc)
    if "OPENROUTER_API_KEY is empty" in text or text.startswith("OpenRouter HTTP"):
        return "http_request"
    if any(marker in text for marker in _JSON_MARKERS):
        return "json_parsing"
    if any(marker in text for marker in _HTTP_MARKERS):
        return "http_request"
    return "provider_wrapper"
