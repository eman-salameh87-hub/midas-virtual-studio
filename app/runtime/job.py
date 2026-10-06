"""Job runtime for the Phase-0 Eye path.

Connects a validated Phase-0 job and its original product image to the Eye
stage, then keeps the Eye observation on that job for readiness.
"""

from __future__ import annotations

import base64
import binascii
import uuid
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict

from app.contracts.eye import EyeObservation, OriginalProductImage
from app.contracts.job import Phase0Job, validate_phase0
from app.stages.eye import EyeCompletion, EyeStageError, run_eye

STATUS_EYE_COMPLETE = "eye_complete"


class JobInputError(ValueError):
    """The original product image could not be accepted."""


class JobStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    status: str
    model_id: str
    eye_ready: bool
    eye_observation: EyeObservation | None


@dataclass
class JobRecord:
    job_id: str
    contract: Phase0Job
    model_id: str
    eye_observation: EyeObservation
    status: str


_JOBS: dict[str, JobRecord] = {}


def reset_jobs() -> None:
    """Clear in-memory jobs. Used by tests and a fresh process."""

    _JOBS.clear()


def execute_job(
    *,
    job: dict[str, object],
    media_type: str,
    data_base64: str,
    source_role: str,
    model_id: str,
    provider: EyeCompletion,
) -> JobRecord:
    """Validate, load the original product image, run Eye, and store the result."""

    contract = validate_phase0(job)
    image = load_original_product_image(
        media_type=media_type,
        data_base64=data_base64,
        source_role=source_role,
    )
    observation = run_eye(image=image, model_id=model_id, provider=provider)
    record = JobRecord(
        job_id=str(uuid.uuid4()),
        contract=contract,
        model_id=model_id.strip(),
        eye_observation=observation,
        status=STATUS_EYE_COMPLETE,
    )
    _JOBS[record.job_id] = record
    return record


def inspect_readiness(job_id: str) -> JobStatus:
    """Read one job's Eye result. Missing jobs raise KeyError."""

    record = _JOBS[job_id]
    return JobStatus(
        job_id=record.job_id,
        status=record.status,
        model_id=record.model_id,
        eye_ready=record.eye_observation is not None,
        eye_observation=record.eye_observation,
    )


def load_original_product_image(
    *,
    media_type: str,
    data_base64: str,
    source_role: str,
) -> OriginalProductImage:
    if not isinstance(media_type, str) or not media_type.startswith("image/"):
        raise JobInputError("Original product image media_type must be an image type.")
    if not isinstance(source_role, str) or not source_role.strip():
        raise JobInputError("Original product image source_role is required.")
    try:
        content = base64.b64decode(data_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise JobInputError("Original product image is not valid base64.") from exc
    if not content:
        raise JobInputError("Original product image is empty.")
    return OriginalProductImage(media_type=media_type, content=content, source_role=source_role)


__all__ = [
    "EyeStageError",
    "JobInputError",
    "JobStatus",
    "execute_job",
    "inspect_readiness",
    "reset_jobs",
]
