"""MIDAS backend application.

GET /health reports process status. Jobs live under /api/v1. POST /jobs
schedules in-process planning (Eye → Brain → Stylist → Compile). Generate,
Critique, repair, approval, and release remain explicit follow-up calls.
"""

import json
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi
from fastapi.responses import HTMLResponse

from app.api.errors import ApiError, ErrorResponse, api_error_handler, request_validation_handler
from app.api.client_briefs import router as client_briefs_router
from app.api.jobs import router as jobs_router
from app.api.reference_intake import router as reference_intake_router
from app.runtime.client_briefs import CLIENT_BRIEF_STORE, recover_client_briefs_from_artifacts
from app.runtime.recovery import recover_jobs_from_artifacts
from app.runtime.state import JOB_STORE

logger = logging.getLogger("app.main")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    recovered = recover_jobs_from_artifacts(JOB_STORE)
    if recovered:
        logger.info("recovered %s job(s) from local artifacts", len(recovered))
    brief_recovery = recover_client_briefs_from_artifacts(CLIENT_BRIEF_STORE)
    if brief_recovery.recovered:
        logger.info(
            "recovered %s client brief(s) from local artifacts",
            len(brief_recovery.recovered),
        )
    for error in brief_recovery.errors:
        logger.error(
            "client brief recovery failed brief_id=%s code=%s reason=%s",
            error.brief_id,
            error.code,
            error.reason,
        )
    # Do not auto-resume planning. Recovery restores artifacts only. Restarting
    # Eye/Brain/Stylist after an ambiguous crash could repeat a provider call.
    yield


# Swagger UI groups operations by path. This order is display-only.
POST_DOC_PATHS = (
    "/api/v1/jobs",
    "/api/v1/client-briefs",
    "/api/v1/client-briefs/{brief_id}/jobs",
    "/api/v1/reference-intake/analyze",
    "/api/v1/jobs/{job_id}/eye",
    "/api/v1/jobs/{job_id}/brain",
    "/api/v1/jobs/{job_id}/stylist",
    "/api/v1/jobs/{job_id}/compile",
    "/api/v1/jobs/{job_id}/generate/approve",
    "/api/v1/jobs/{job_id}/generate",
    "/api/v1/jobs/{job_id}/critique",
    "/api/v1/jobs/{job_id}/repair",
    "/api/v1/jobs/{job_id}/review/approve",
    "/api/v1/jobs/{job_id}/review/release",
)
GET_DOC_PATHS = (
    "/api/v1/jobs/{job_id}",
    "/api/v1/client-briefs/{brief_id}",
    "/api/v1/jobs/{job_id}/eye",
    "/api/v1/jobs/{job_id}/brain",
    "/api/v1/jobs/{job_id}/stylist",
    "/api/v1/jobs/{job_id}/compile",
    "/api/v1/jobs/{job_id}/generate",
    "/api/v1/jobs/{job_id}/critique",
    "/api/v1/jobs/{job_id}/repair",
    "/api/v1/jobs/{job_id}/generate/image",
    "/api/v1/jobs/{job_id}/status",
    "/health",
)


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
    docs_url=None,
    lifespan=lifespan,
)
app.add_exception_handler(ApiError, api_error_handler)
app.add_exception_handler(RequestValidationError, request_validation_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://newaeonjo-001-site7.atempurl.com",
        "https://newaeonjo-001-site7.atempurl.com",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.include_router(jobs_router)
app.include_router(client_briefs_router)
app.include_router(reference_intake_router)


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


def _ordered_docs() -> HTMLResponse:
    """Serve Swagger UI with every POST listed before every GET."""

    response = get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=f"{app.title} - Swagger UI",
    )
    html = response.body.decode()
    sorter = f"""
    operationsSorter: (a, b) => {{
      const rank = {{ post: 0, get: 1 }};
      const posts = {json.dumps(list(POST_DOC_PATHS))};
      const gets = {json.dumps(list(GET_DOC_PATHS))};
      const methodDelta = (rank[a.get("method")] ?? 9) - (rank[b.get("method")] ?? 9);
      if (methodDelta !== 0) return methodDelta;
      const order = a.get("method") === "post" ? posts : gets;
      const left = order.indexOf(a.get("path"));
      const right = order.indexOf(b.get("path"));
      return (left < 0 ? order.length : left) - (right < 0 ? order.length : right);
    }},
    """
    html = html.replace("presets:", sorter + "presets:", 1)
    return HTMLResponse(html)


@app.get("/docs", include_in_schema=False)
def swagger_docs() -> HTMLResponse:
    return _ordered_docs()


@app.get("/health", tags=["health"], summary="Health check")
def health() -> dict[str, str]:
    return {"status": "ok"}
