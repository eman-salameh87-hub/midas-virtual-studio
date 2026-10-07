"""Repair planner boundary.

The planner consumes the locked contract, original reference, current
candidate, Engine compile, latest CritiqueAssessment, and repair history.
It does not generate images, choose models, or execute Repair #3.
"""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.critique import CritiqueAssessment
from app.contracts.engine import EngineCompile
from app.contracts.eye import EyeObservation
from app.contracts.generation import GenerationOperation, GenerationReceipt
from app.contracts.job import Phase0JobContract
from app.contracts.repair import RepairPlan
from app.contracts.stylist import StylistPlan
from app.runtime.state import JobStage, JobState


class RepairPlannerRequest(BaseModel):
    """What the bounded repair controller receives."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    contract: Phase0JobContract
    observation: EyeObservation
    stylist_plan: StylistPlan
    compile: EngineCompile
    operation: GenerationOperation
    receipt: GenerationReceipt
    assessment: CritiqueAssessment
    original_reference_id: str = Field(min_length=1)
    generated_output_id: str = Field(min_length=1)
    original_bytes: bytes
    original_media_type: str = Field(min_length=1)
    generated_bytes: bytes
    generated_media_type: str = Field(min_length=1)
    previous_repairs: list[RepairPlan]
    repair_count: int = Field(ge=0, le=2)
    repair_limit: int = Field(ge=2, le=2)
    model_id: str = Field(min_length=1)
    stage: JobStage
    state: JobState


class RepairPlanner(Protocol):
    """Returns a bounded RepairPlan. It does not dispatch generation."""

    def plan(self, request: RepairPlannerRequest) -> RepairPlan:
        """Convert named critique defects into a controller action."""
