"""Public API error envelope."""

from typing import Any

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1, examples=["JOB_NOT_FOUND"])
    message: str = Field(min_length=1, examples=["Job not found"])
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorBody


class ApiError(Exception):
    """Raised by the API layer. Converted to ErrorResponse."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(message)

    def to_response(self) -> JSONResponse:
        payload = ErrorResponse(
            error=ErrorBody(code=self.code, message=self.message, details=self.details)
        )
        return JSONResponse(
            status_code=self.status_code,
            content=payload.model_dump(mode="json"),
        )


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return exc.to_response()


async def request_validation_handler(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    return ApiError(
        status_code=422,
        code="INVALID_REQUEST",
        message="Invalid request",
        details={"issues": jsonable_encoder(exc.errors())},
    ).to_response()
