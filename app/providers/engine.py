"""Engine · compile provider boundary.

The caller supplies model_id. This module does not choose a model, call a
generation API, or invent creative decisions. Compilation is provider-neutral.
"""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.brain import BrainPlan
from app.contracts.engine import EngineCompile
from app.contracts.eye import EyeObservation
from app.contracts.job import Phase0JobContract
from app.contracts.stylist import StylistPlan
from app.providers.brain import BrainEvidenceRef
from app.runtime.state import JobStage, JobState

EngineExecutionStatus = Literal["completed", "failed"]


class EngineInput(BaseModel):
    """Persisted Job State snapshot for a stateless Engine compile call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    contract: Phase0JobContract
    observation: EyeObservation
    brain_plan: BrainPlan
    stylist_plan: StylistPlan
    evidence: list[BrainEvidenceRef]
    stage: JobStage
    state: JobState


class EngineResult(BaseModel):
    """Validated Engine compile result bound to one job revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    brain_contract_id: str = Field(min_length=1)
    brain_revision: int = Field(ge=1)
    stylist_contract_id: str = Field(min_length=1)
    stylist_revision: int = Field(ge=1)
    model_id: str = Field(min_length=1)
    execution_status: EngineExecutionStatus
    compile: EngineCompile


class EngineProviderRequest(BaseModel):
    """What a compiler receives. model_id is passed through from the caller."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1)
    engine_input: EngineInput


class EngineCompiler(Protocol):
    """Returns a structured EngineCompile. It does not generate an image."""

    def compile(self, request: EngineProviderRequest) -> EngineCompile:
        """Produce an EngineCompile for this request."""
