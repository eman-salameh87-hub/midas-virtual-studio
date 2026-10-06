"""OpenRouter HTTP boundary.

This is the only module that talks to OpenRouter. It does not choose a model.
The caller passes model_id through on every request.
"""

from __future__ import annotations

import json
import os
from typing import Any

import httpx

OPENROUTER_API_KEY_ENV = "OPENROUTER_API_KEY"
OPENROUTER_BASE_URL_ENV = "OPENROUTER_BASE_URL"
OPENROUTER_TIMEOUT_ENV = "OPENROUTER_TIMEOUT_SECONDS"
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_TIMEOUT_SECONDS = 60.0


class OpenRouterError(RuntimeError):
    """The provider call could not be completed."""


class OpenRouterClient:
    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float | None = None,
    ) -> None:
        if api_key is None:
            api_key = os.getenv(OPENROUTER_API_KEY_ENV)
        self._api_key = api_key.strip() if isinstance(api_key, str) and api_key.strip() else None
        if base_url is None:
            base_url = os.getenv(OPENROUTER_BASE_URL_ENV) or DEFAULT_BASE_URL
        self._base_url = base_url.rstrip("/")
        if timeout is None:
            raw_timeout = os.getenv(OPENROUTER_TIMEOUT_ENV)
            timeout = float(raw_timeout) if raw_timeout and raw_timeout.strip() else DEFAULT_TIMEOUT_SECONDS
        self._timeout = timeout

    def complete(
        self,
        *,
        model_id: str,
        messages: list[dict[str, Any]],
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Post one chat completion. model_id is required and is not replaced."""

        if not isinstance(model_id, str) or not model_id.strip():
            raise OpenRouterError("model_id is required.")
        if not self._api_key:
            raise OpenRouterError(f"{OPENROUTER_API_KEY_ENV} is not set.")
        payload = {
            "model": model_id.strip(),
            "messages": messages,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "structured_response",
                    "strict": True,
                    "schema": response_schema,
                },
            },
        }
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OpenRouterError("OpenRouter request failed.") from exc
        return _parsed_object(response.json())


def _parsed_object(body: object) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise OpenRouterError("OpenRouter returned a non-object response.")
    try:
        content = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise OpenRouterError("OpenRouter response did not include message content.") from exc
    if isinstance(content, dict):
        return content
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OpenRouterError("OpenRouter message content was not JSON.") from exc
        if isinstance(parsed, dict):
            return parsed
    raise OpenRouterError("OpenRouter message content was not a JSON object.")
