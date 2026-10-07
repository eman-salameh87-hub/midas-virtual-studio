"""Brain provider boundary.

The caller supplies model_id. This module does not choose a model, store a
registry, or call OpenRouter.
"""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.brain import BrainPlan
from app.contracts.eye import EyeObservation
from app.contracts.job import Phase0JobContract
from app.stages.eye import Readiness

JobStage = Literal["intake", "eye", "brain"]
JobState = Literal["accepted", "ready", "hold", "failed"]


class BrainEvidenceRef(BaseModel):
    """Reference identity available to Brain. Raw bytes are not included."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reference_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    hash_algorithm: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    role: str = Field(min_length=1)
    bytes_available: bool


class BrainInput(BaseModel):
    """Persisted Job State snapshot for a stateless Brain call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    contract: Phase0JobContract
    observation: EyeObservation
    readiness: Readiness
    evidence: list[BrainEvidenceRef]
    stage: JobStage
    state: JobState


class BrainResult(BaseModel):
    """Validated Brain execution result bound to one job revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    observation_contract_id: str = Field(min_length=1)
    observation_revision: int = Field(ge=1)
    model_id: str = Field(min_length=1)
    execution_status: str = Field(min_length=1)
    plan: BrainPlan


class BrainProviderRequest(BaseModel):
    """What a provider receives. model_id is passed through, not selected."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1)
    brain_input: BrainInput


class BrainProvider(Protocol):
    """Returns a structured Brain plan. It does not perform an HTTP call here."""

    def reason(self, request: BrainProviderRequest) -> BrainPlan:
        """Produce a BrainPlan for this request."""
