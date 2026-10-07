"""Decision-history records on a job.

These events are process-local JobState history, not a durable log.
They do not replace the frozen contract or EyeObservation.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

JobEventKind = Literal[
    "job_created",
    "eye_persisted",
    "eye_failed",
    "brain_completed",
    "brain_failed",
    "stylist_completed",
    "stylist_failed",
    "compile_completed",
    "compile_failed",
    "generate_claimed",
    "generate_completed",
    "generate_failed",
    "critique_completed",
    "critique_failed",
    "repair_claimed",
    "repair_completed",
    "repair_failed",
    "repair_held",
]



class JobEvent(BaseModel):
    """One recorded JobState transition. No provider internals."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: JobEventKind
    stage: str = Field(min_length=1)
    state: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)


def job_event(
    *,
    kind: JobEventKind,
    stage: str,
    state: str,
    contract_id: str,
    revision: int,
) -> JobEvent:
    return JobEvent(
        kind=kind,
        stage=stage,
        state=state,
        contract_id=contract_id,
        revision=revision,
    )
