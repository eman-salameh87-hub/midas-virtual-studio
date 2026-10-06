"""Job API for the Phase-0 Eye path."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.providers.openrouter import OpenRouterClient
from app.runtime.job import (
    EyeStageError,
    JobInputError,
    JobStatus,
    execute_job,
    inspect_readiness,
)
from app.contracts.job import Phase0Job
from app.stages.eye import EyeCompletion

router = APIRouter()


class OriginalProductImagePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    media_type: str = Field(min_length=1)
    data_base64: str = Field(min_length=1)
    source_role: str = Field(min_length=1)


class CreateJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    model_id: str = Field(min_length=1)
    original_product_image: OriginalProductImagePayload
    job: Phase0Job


def get_eye_provider() -> EyeCompletion:
    return OpenRouterClient()


@router.post("/jobs", response_model=JobStatus)
def create_job(
    body: CreateJobRequest,
    provider: EyeCompletion = Depends(get_eye_provider),
) -> JobStatus:
    try:
        record = execute_job(
            job=body.job.model_dump(),
            media_type=body.original_product_image.media_type,
            data_base64=body.original_product_image.data_base64,
            source_role=body.original_product_image.source_role,
            model_id=body.model_id,
            provider=provider,
        )
    except (ValidationError, EyeStageError, JobInputError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return inspect_readiness(record.job_id)


@router.get("/jobs/{job_id}", response_model=JobStatus)
def get_job(job_id: str) -> Any:
    try:
        return inspect_readiness(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found.") from exc
