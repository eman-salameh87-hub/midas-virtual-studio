"""Stylist provider boundary.

The caller supplies model_id. This module does not choose a model, store a
registry, or call OpenRouter directly.
"""

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.brain import BrainPlan
from app.contracts.eye import EyeObservation
from app.contracts.job import Phase0JobContract
from app.contracts.stylist import MidasCompanion, StylistPlan
from app.providers.brain import BrainEvidenceRef
from app.runtime.state import JobStage, JobState


class StylistInput(BaseModel):
    """Persisted Job State snapshot for a stateless Stylist call."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    contract: Phase0JobContract
    observation: EyeObservation
    brain_plan: BrainPlan
    evidence: list[BrainEvidenceRef]
    verified_complements: list[MidasCompanion] = Field(default_factory=list)
    stage: JobStage
    state: JobState


class StylistResult(BaseModel):
    """Validated Stylist execution result bound to one job revision."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    brain_contract_id: str = Field(min_length=1)
    brain_revision: int = Field(ge=1)
    model_id: str = Field(min_length=1)
    execution_status: str = Field(min_length=1)
    plan: StylistPlan


class StylistProviderRequest(BaseModel):
    """What a provider receives. model_id is passed through from caller."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1)
    stylist_input: StylistInput


class StylistProvider(Protocol):
    """Returns a structured Stylist plan. It does not perform an HTTP call here."""

    def compose(self, request: StylistProviderRequest) -> StylistPlan:
        """Produce a StylistPlan for this request."""
