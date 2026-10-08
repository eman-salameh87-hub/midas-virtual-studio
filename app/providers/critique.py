"""Critique provider boundary.

The caller supplies model_id. This module does not choose a model, repair an
image, or call OpenRouter directly.
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.brain import BrainPlan
from app.contracts.critique import CritiqueAssessment
from app.contracts.engine import EngineCompile
from app.contracts.eye import EyeObservation
from app.contracts.generation import GenerationOperation, GenerationReceipt
from app.contracts.job import Phase0JobContract
from app.contracts.stylist import StylistPlan
from app.runtime.state import JobStage, JobState


class PriorGenerationRef(BaseModel):
    """Earlier generation identity available to Critique. Bytes stay on the job."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_key: str = Field(min_length=1)
    output_id: str | None = None
    status: str = Field(min_length=1)


class PriorRepairRef(BaseModel):
    """Earlier repair identity. This does not rewrite the repair plan."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    repair_count: int = Field(ge=0, le=2)
    action: str = Field(min_length=1)
    status: str = Field(min_length=1)
    scene_base_reference: str | None = None
    product_authority_reference: str | None = None
    source_generation_output_id: str = Field(min_length=1)
    result_generation_output_id: str | None = None


class CritiqueInput(BaseModel):
    """Persisted Job State snapshot for a stateless Critique · assess call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    contract: Phase0JobContract
    observation: EyeObservation
    brain_plan: BrainPlan
    stylist_plan: StylistPlan
    compile: EngineCompile
    operation: GenerationOperation
    receipt: GenerationReceipt
    original_reference_id: str = Field(min_length=1)
    generated_output_id: str = Field(min_length=1)
    prior_generations: list[PriorGenerationRef] = Field(default_factory=list)
    prior_repairs: list[PriorRepairRef] = Field(default_factory=list)
    stage: JobStage
    state: JobState


class CritiqueResult(BaseModel):
    """Validated critique execution result bound to one job revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    model_id: str = Field(min_length=1)
    execution_status: str = Field(min_length=1)
    assessment: CritiqueAssessment


class CritiqueProviderRequest(BaseModel):
    """What a provider receives. model_id is passed through from the caller."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1)
    critique_input: CritiqueInput
    original_bytes: bytes
    original_media_type: str = Field(min_length=1)
    generated_bytes: bytes
    generated_media_type: str = Field(min_length=1)


class CritiqueProvider(Protocol):
    """Returns a structured CritiqueAssessment. It does not repair."""

    def assess(self, request: CritiqueProviderRequest) -> CritiqueAssessment:
        """Inspect original and generated images against the locked contract."""
