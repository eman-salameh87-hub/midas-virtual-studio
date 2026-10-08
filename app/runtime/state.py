"""In-process JobState for Architecture A's durable-state boundary.

JobRecord is the authoritative job state. The backing store is process-local
today; JobStore is the replacement seam for a later durable implementation.
There is no database.
"""

from __future__ import annotations

import threading
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.brain import BrainPlan
from app.contracts.critique import CritiqueAssessment
from app.contracts.engine import EngineCompile
from app.contracts.eye import EyeInput, EyeObservation
from app.contracts.generation import GenerationOperation, GenerationReceipt, GenerationStatus
from app.contracts.reference import ChecksumStatus, ReferenceMeasurement
from app.contracts.job import Phase0JobContract
from app.contracts.repair import REPAIR_LIMIT, RepairPlan
from app.contracts.review import (
    OwnerApproval,
    PackageRelease,
    PreGenerationApproval,
    ReviewStatus,
)
from app.contracts.stylist import StylistPlan
from app.providers.brain import BrainEvidenceRef
from app.runtime.events import JobEvent
from app.stages.eye import Readiness

JobStage = Literal[
    "intake",
    "eye",
    "brain",
    "stylist",
    "compile",
    "generate",
    "critique",
    "repair",
]
JobState = Literal[
    "accepted",
    "ready",
    "hold",
    "failed",
    "review_pending",
    "approved",
    "released",
]
BrainExecutionStatus = Literal["completed", "failed"]
StylistExecutionStatus = Literal["completed", "failed"]
EngineExecutionStatus = Literal["completed", "failed"]
CritiqueExecutionStatus = Literal["completed", "failed"]


class JobError(BaseModel):
    """Public-safe job error. Provider internals are not stored here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)


class BrainInputMetadata(BaseModel):
    """Stored Brain input identity. Not a canonical MIDAS Brain contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    observation_contract_id: str = Field(min_length=1)
    observation_revision: int = Field(ge=1)
    evidence: list[BrainEvidenceRef]


class StoredBrain(BaseModel):
    """Brain artifact on JobRecord. Implementation-specific persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1)
    input: BrainInputMetadata | None
    result: BrainPlan | None
    status: BrainExecutionStatus


class StylistInputMetadata(BaseModel):
    """Stored Stylist input identity. Not a canonical MIDAS Stylist contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    brain_contract_id: str = Field(min_length=1)
    brain_revision: int = Field(ge=1)
    evidence: list[BrainEvidenceRef]


class StoredStylist(BaseModel):
    """Stylist artifact on JobRecord. Implementation-specific persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1)
    input: StylistInputMetadata | None
    result: StylistPlan | None
    status: StylistExecutionStatus


class EngineInputMetadata(BaseModel):
    """Stored Engine input identity. Not a canonical MIDAS Engine contract."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    brain_contract_id: str = Field(min_length=1)
    brain_revision: int = Field(ge=1)
    stylist_contract_id: str = Field(min_length=1)
    stylist_revision: int = Field(ge=1)
    evidence: list[BrainEvidenceRef]


class StoredEngine(BaseModel):
    """Engine compile artifact on JobRecord. Implementation-specific persistence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1)
    input: EngineInputMetadata | None
    result: EngineCompile | None
    status: EngineExecutionStatus


class StoredGeneration(BaseModel):
    """Claimed generation operation and receipt on JobRecord."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation: GenerationOperation
    receipt: GenerationReceipt | None
    status: GenerationStatus
    checksum_status: ChecksumStatus = "unverified"
    observed_checksum: str | None = None


class StoredCritique(BaseModel):
    """Critique · assess artifact on JobRecord."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1)
    result: CritiqueAssessment | None
    status: CritiqueExecutionStatus


class StoredRepair(BaseModel):
    """Bounded repair artifact on JobRecord."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    plan: RepairPlan
    status: str = Field(min_length=1)


class JobRecord(BaseModel):
    """Authoritative in-process JobState for one job.

    The frozen Phase-0 contract is stored once. EyeObservation is attached
    to that same record when Eye has run. owner_id is copied from the
    contract so job/owner checks do not reconstruct identity from chat.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    owner_id: str = Field(min_length=1)
    contract: Phase0JobContract
    revision: int = Field(ge=1)
    stage: JobStage
    state: JobState
    status: JobState
    hold: Readiness | None
    error: JobError | None
    eye_model_id: str | None
    eye_input: EyeInput | None
    observation: EyeObservation | None
    readiness: Readiness | None
    brain: StoredBrain | None
    stylist: StoredStylist | None = None
    engine: StoredEngine | None = None
    generation: StoredGeneration | None = None
    critique: StoredCritique | None = None
    repair: StoredRepair | None = None
    repairs: list[StoredRepair] = Field(default_factory=list)
    generation_history: list[StoredGeneration] = Field(default_factory=list)
    critique_history: list[StoredCritique] = Field(default_factory=list)
    repair_count: int = Field(default=0, ge=0, le=2)
    repair_limit: int = Field(default=REPAIR_LIMIT, ge=2, le=2)
    review_status: ReviewStatus | None = None
    complete: bool = False
    releasable: bool = False
    approval: OwnerApproval | None = None
    pre_generation_approval: PreGenerationApproval | None = None
    release: PackageRelease | None = None
    events: list[JobEvent] = Field(default_factory=list)
    reference_bytes: dict[str, bytes] = Field(default_factory=dict)
    reference_measurements: list[ReferenceMeasurement] = Field(default_factory=list)



class JobStore(Protocol):
    """Persistence seam. InMemoryJobStore is the current backing store."""

    def save(self, record: JobRecord) -> None:
        """Write or replace one JobRecord."""

    def get(self, job_id: str) -> JobRecord | None:
        """Return the JobRecord, or None if it is not in this process."""


class InMemoryJobStore:
    """Process-local JobRecord map. Not shared across processes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, JobRecord] = {}

    def save(self, record: JobRecord) -> None:
        with self._lock:
            self._jobs[record.job_id] = record

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()


JOB_STORE = InMemoryJobStore()
