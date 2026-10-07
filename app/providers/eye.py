"""Eye provider boundary.

The caller supplies model_id and instruction text. This module does not
choose a model, store a registry, or call OpenRouter.
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.eye import EyeInput, EyeObservation


class EyeProviderRequest(BaseModel):
    """What a provider receives. model_id is passed through, not selected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1)
    eye_input: EyeInput
    messages: list[str]


class EyeProvider(Protocol):
    """Returns a structured observation. It does not perform an HTTP call here."""

    def observe(self, request: EyeProviderRequest) -> EyeObservation:
        """Produce an EyeObservation for this request."""
