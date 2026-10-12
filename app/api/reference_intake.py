"""Analyze a reference image. Does not create a job or call image generation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from fastapi import APIRouter, Depends

from app.api.errors import ApiError, ErrorResponse
from app.providers.composite_reference_intake import CompositeReferenceIntakeProvider
from app.providers.failure import provider_failure_details
from app.providers.reference_intake import (
    PROVIDER_FAILED_MESSAGE,
    ReferenceIntakeProvider,
    ReferenceIntakeRequest,
    ReferenceIntakeResult,
    constrain_intake_result,
)

router = APIRouter(prefix="/api/v1", tags=["reference-intake"])

_ERRORS = {
    422: {"model": ErrorResponse, "description": "Invalid request"},
    502: {"model": ErrorResponse, "description": "Provider failed"},
}


def get_reference_intake_provider() -> ReferenceIntakeProvider:
    return CompositeReferenceIntakeProvider()


class AnalyzeReferenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result: ReferenceIntakeResult


@router.post(
    "/reference-intake/analyze",
    response_model=AnalyzeReferenceResponse,
    summary="Analyze a reference image",
    description=(
        "Decide whether an uploaded image or Midas catalogue product is relevant "
        "furniture/interior reference material and suggest existing taxonomy and "
        "reference-type values. Does not generate images."
    ),
    responses={422: _ERRORS[422], 502: _ERRORS[502]},
)
def post_analyze_reference(
    body: ReferenceIntakeRequest,
    provider: ReferenceIntakeProvider = Depends(get_reference_intake_provider),
) -> AnalyzeReferenceResponse:
    if not (body.library_key or "").strip() and not (body.content_base64 or "").strip():
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message="Invalid request",
            details={"reason": "Provide library_key or image bytes"},
        )
    try:
        result = constrain_intake_result(provider.analyze(body))
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message="Invalid request",
            details={"reason": str(exc)},
        ) from exc
    except Exception as exc:
        details = provider_failure_details(exc, provider)
        raise ApiError(
            status_code=502,
            code="PROVIDER_FAILURE",
            message=PROVIDER_FAILED_MESSAGE,
            details=dict(details),
        ) from exc
    if result.status == "accepted" and not result.relevant:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message=PROVIDER_FAILED_MESSAGE,
            details={"reason": "analyzer marked the image accepted without relevance"},
        )
    return AnalyzeReferenceResponse(result=result)
