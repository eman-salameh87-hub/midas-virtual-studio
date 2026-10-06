"""Provider-neutral Eye stage.

The caller supplies model_id. This module does not select a model and does
not contain a system prompt. The canonical Eye prompt is not in this repository.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Protocol

from pydantic import ValidationError

from app.contracts.eye import EYE_RESPONSE_SCHEMA, EyeObservation, OriginalProductImage


class EyeStageError(ValueError):
    """Eye could not accept the call or the provider payload."""


class EyeCompletion(Protocol):
    def complete(
        self,
        *,
        model_id: str,
        messages: list[dict[str, Any]],
        response_schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Return the provider's parsed JSON object."""


def run_eye(
    *,
    image: OriginalProductImage,
    model_id: str,
    provider: EyeCompletion,
) -> EyeObservation:
    """Send the original product image to the injected provider."""

    explicit_model_id = _required_model_id(model_id)
    payload = provider.complete(
        model_id=explicit_model_id,
        messages=_messages(image),
        response_schema=EYE_RESPONSE_SCHEMA,
    )
    return _observation(payload, expected_role=image.source_role)


def _required_model_id(model_id: str) -> str:
    if not isinstance(model_id, str) or not model_id.strip():
        raise EyeStageError("Eye requires an explicit model_id.")
    return model_id.strip()


def _messages(image: OriginalProductImage) -> list[dict[str, Any]]:
    context = json.dumps({"source_role": image.source_role}, sort_keys=True)
    encoded = base64.b64encode(image.content).decode("ascii")
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": context},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image.media_type};base64,{encoded}"},
                },
            ],
        }
    ]


def _observation(payload: object, *, expected_role: str) -> EyeObservation:
    if not isinstance(payload, dict):
        raise EyeStageError("Eye provider did not return a JSON object.")
    try:
        observation = EyeObservation.model_validate(payload)
    except ValidationError as exc:
        raise EyeStageError(
            "Structured Eye response did not match the evidence schema."
        ) from exc
    if observation.source_role != expected_role:
        raise EyeStageError("Eye response changed the supplied source role.")
    return observation
