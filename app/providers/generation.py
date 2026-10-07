"""Generation provider adapter boundary.

The adapter receives a claimed GenerationOperation plus EngineCompile.
It does not choose a model, invent a prompt, or approve quality.
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.engine import EngineCompile
from app.contracts.generation import (
    GenerationOperation,
    GenerationReceipt,
    ProviderCapability,
)


class GenerationProviderRequest(BaseModel):
    """What a generation adapter receives after capability checks and claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: GenerationOperation
    compile: EngineCompile
    reference_bytes: dict[str, bytes] = Field(default_factory=dict)


class GenerationProviderResult(BaseModel):
    """Adapter result. Bytes are optional except on completed receipts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt: GenerationReceipt
    output_bytes: bytes | None = None


class GenerationProvider(Protocol):
    """Provider-agnostic image generation adapter."""

    def capabilities(self) -> frozenset[ProviderCapability]:
        """Capabilities this adapter actually supports. Not a ranking."""

    def generate(self, request: GenerationProviderRequest) -> GenerationProviderResult:
        """Dispatch one claimed operation. Must not fabricate a completed receipt."""
