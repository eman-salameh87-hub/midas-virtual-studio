"""MIDAS backend application.

GET /health reports process status. Jobs live under /api/v1. Eye, Brain,
Stylist, Compile, Generate, Critique · assess, and Critique · repair are
explicit follow-up calls. Release is not implemented.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.openapi.utils import get_openapi

from app.api.errors import ApiError, ErrorResponse, api_error_handler, request_validation_handler
from app.api.jobs import router as jobs_router
from app.runtime.recovery import recover_jobs_from_artifacts
from app.runtime.state import JOB_STORE

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    recovered = recover_jobs_from_artifacts(JOB_STORE)
    if recovered:
        logger.info("recovered %s job(s) from local artifacts", len(recovered))
    yield


app = FastAPI(
    title="MIDAS Virtual Studio",
    description=(
        "Jobs API: create a frozen Phase-0 contract, then explicitly run Eye, "
        "Brain, Stylist, Compile, Generate, Critique · assess, and bounded "
        "Repair. Retrieve persisted JSON results and the generated image. "
        "Release is not available. "
        "Optional query parameters owner_id and revision enforce ownership and "
        "the frozen contract revision. There is no authentication layer yet; "
        "owner_id is an application-level check only."
    ),
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, request_validation_handler)
app.include_router(jobs_router)


def _openapi() -> dict:
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    error_ref = {"$ref": "#/components/schemas/ErrorResponse"}
    for path in schema.get("paths", {}).values():
        for operation in path.values():
            if not isinstance(operation, dict):
                continue
            responses = operation.get("responses")
            if not isinstance(responses, dict) or "422" not in responses:
                continue
            responses["422"] = {
                "description": "Invalid request",
                "content": {"application/json": {"schema": error_ref}},
            }
    components = schema.setdefault("components", {}).setdefault("schemas", {})
    components.pop("HTTPValidationError", None)
    components.pop("ValidationError", None)
    if "ErrorResponse" not in components:
        components["ErrorResponse"] = ErrorResponse.model_json_schema()
    app.openapi_schema = schema
    return schema


app.openapi = _openapi


@app.get("/health", tags=["health"], summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok"}
