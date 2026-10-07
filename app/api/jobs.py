"""Versioned jobs API: create a job, run Eye/Brain/Stylist/Compile/Generate, retrieve state."""

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import ValidationError

from app.api.errors import ApiError, ErrorResponse
from app.api.schemas import (
    CreateJobRequest,
    CreateJobResponse,
    ExecuteBrainRequest,
    ExecuteBrainResponse,
    ExecuteCompileRequest,
    ExecuteCompileResponse,
    ExecuteCritiqueRequest,
    ExecuteCritiqueResponse,
    ExecuteEyeRequest,
    ExecuteEyeResponse,
    ExecuteGenerateRequest,
    ExecuteGenerateResponse,
    ExecuteRepairRequest,
    ExecuteRepairResponse,
    ExecuteStylistRequest,
    ExecuteStylistResponse,
    GetBrainResponse,
    GetCompileResponse,
    GetCritiqueResponse,
    GetEyeResponse,
    GetGenerateResponse,
    GetRepairResponse,
    GetStylistResponse,
    JobStatusView,
    JobView,
    create_job_response,
    execute_brain_response,
    execute_compile_response,
    execute_critique_response,
    execute_eye_response,
    execute_generate_response,
    execute_repair_response,
    execute_stylist_response,
    get_brain_response,
    get_compile_response,
    get_critique_response,
    get_eye_response,
    get_generate_response,
    get_repair_response,
    get_stylist_response,
    job_status_view,
    job_view,
)
from app.providers.brain import BrainProvider
from app.providers.engine import EngineCompiler
from app.providers.eye import EyeProvider
from app.providers.fake_engine import FakeEngineCompiler
from app.providers.critique import CritiqueProvider
from app.providers.generation import GenerationProvider
from app.providers.openrouter import (
    OpenRouterBrainProvider,
    OpenRouterCritiqueProvider,
    OpenRouterEyeProvider,
    OpenRouterGenerationProvider,
    OpenRouterStylistProvider,
    load_settings,
)
from app.providers.fake_repair import FakeRepairPlanner
from app.providers.repair import RepairPlanner
from app.providers.stylist import StylistProvider
from app.runtime.jobs import (
    BrainNotReadyError,
    BrainNotRunError,
    BrainProviderFailedError,
    CritiqueNotRunError,
    CritiqueProviderFailedError,
    EngineNotReadyError,
    EngineNotRunError,
    EngineProviderFailedError,
    EyeNotRunError,
    EyeProviderFailedError,
    GenerationNotReadyError,
    GenerationNotRunError,
    GenerationProviderFailedError,
    JobNotFoundError,
    JobOwnerMismatchError,
    ModelMismatchError,
    RevisionMismatchError,
    StylistNotReadyError,
    StylistNotRunError,
    StylistProviderFailedError,
    create_job_from_intake,
    execute_job_brain,
    execute_job_compile,
    execute_job_critique,
    execute_job_eye,
    execute_job_generate,
    execute_job_repair,
    execute_job_stylist,
    RepairNotReadyError,
    RepairNotRequiredError,
    RepairNotRunError,
    RepairProviderFailedError,
    get_job,
    get_job_brain,
    get_job_compile,
    get_job_critique,
    get_job_eye,
    get_job_generation,
    get_job_repair,
    get_job_stylist,
)
from app.runtime.artifacts import content_type_for, get_artifact_store, output_filename
from app.runtime.model_policy import (
    allowed_models_for_stage,
    brain_model,
    critique_model,
    eye_model,
    image_model,
    stylist_model,
    validate_stage_model,
)
from app.runtime.state import JOB_STORE, InMemoryJobStore, JobRecord

router = APIRouter(prefix="/api/v1", tags=["jobs"])

OwnerIdParam = Annotated[
    str | None,
    Query(description="Optional owner check. When set, must match the job owner_id."),
]
RevisionParam = Annotated[
    int | None,
    Query(
        description="Optional revision check. When set, must match the frozen contract revision."
    ),
]

_ERRORS = {
    403: {"model": ErrorResponse, "description": "Job owner does not match"},
    404: {"model": ErrorResponse, "description": "Job not found"},
    409: {"model": ErrorResponse, "description": "Job is not in a valid state for this operation"},
    422: {"model": ErrorResponse, "description": "Invalid request"},
    502: {"model": ErrorResponse, "description": "Provider failed"},
}


def get_job_store() -> InMemoryJobStore:
    return JOB_STORE


def get_eye_provider() -> EyeProvider:
    """OpenRouter Eye provider. Tests override this with FakeEyeProvider."""

    return OpenRouterEyeProvider(load_settings(), {})


def get_brain_provider() -> BrainProvider:
    """OpenRouter Brain provider. Tests override this with FakeBrainProvider."""

    return OpenRouterBrainProvider(load_settings())


def get_stylist_provider() -> StylistProvider:
    """OpenRouter Stylist provider. Tests override this with FakeStylistProvider."""

    return OpenRouterStylistProvider(load_settings())


def get_engine_compiler() -> EngineCompiler:
    """Deterministic FakeEngineCompiler. Compile does not call OpenRouter."""

    return FakeEngineCompiler()


def get_generation_provider() -> GenerationProvider:
    """OpenRouter image generation. Tests override this with FakeGenerationProvider."""

    return OpenRouterGenerationProvider(load_settings())


def get_critique_provider() -> CritiqueProvider:
    """OpenRouter Critique · assess. Tests override this with FakeCritiqueProvider."""

    return OpenRouterCritiqueProvider(load_settings())


def get_repair_planner() -> RepairPlanner:
    """Deterministic bounded repair planner. Does not invent defects."""

    return FakeRepairPlanner()


def _not_found(job_id: str) -> NoReturn:
    raise ApiError(
        status_code=404,
        code="JOB_NOT_FOUND",
        message="Job not found",
        details={"job_id": job_id},
    )


def _owner_mismatch(job_id: str, owner_id: str) -> NoReturn:
    raise ApiError(
        status_code=403,
        code="JOB_OWNER_MISMATCH",
        message="Job does not belong to this owner",
        details={"job_id": job_id, "owner_id": owner_id},
    )


def _revision_mismatch(job_id: str, expected: int, actual: int) -> NoReturn:
    raise ApiError(
        status_code=409,
        code="REVISION_MISMATCH",
        message="Requested revision does not match the frozen job contract",
        details={"job_id": job_id, "expected": expected, "actual": actual},
    )


@router.post(
    "/jobs",
    response_model=CreateJobResponse,
    summary="Create a job",
    description=(
        "Accept a Phase-0 job contract and freeze it on a new job. "
        "Image references (JPG, PNG, WebP) must include content_base64. "
        "If content_hash is omitted or empty, the server hashes the decoded bytes. "
        "A supplied content_hash must match those bytes. "
        "Bytes are stored on the job; they are not part of the frozen identity contract. "
        "Eye is not executed. Unresolved placeholder values are rejected."
    ),
    responses={422: _ERRORS[422]},
)
def post_job(
    body: CreateJobRequest,
    store: InMemoryJobStore = Depends(get_job_store),
) -> CreateJobResponse:
    try:
        record = create_job_from_intake(store, body.contract.model_dump(mode="python"))
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message="Invalid request",
            details={"reason": str(exc)},
        ) from exc
    return create_job_response(record)


@router.get(
    "/jobs/{job_id}",
    response_model=JobView,
    summary="Get a job",
    description="Return the current public job view, including completed stage results when they exist.",
    responses={403: _ERRORS[403], 404: _ERRORS[404], 409: _ERRORS[409]},
)
def get_job_endpoint(
    job_id: str,
    store: InMemoryJobStore = Depends(get_job_store),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> JobView:
    try:
        record = get_job(store, job_id, owner_id=owner_id, revision=revision)
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    return job_view(record)


@router.post(
    "/jobs/{job_id}/eye",
    response_model=ExecuteEyeResponse,
    summary="Execute Eye",
    description=(
        "Run Eye for an existing job. Pass model_id or edit to an allowed model. "
        "References and stored image bytes are taken from the job. "
        "The observation is persisted on the job."
    ),
    responses={403: _ERRORS[403], 404: _ERRORS[404], 409: _ERRORS[409], 422: _ERRORS[422], 502: _ERRORS[502]},
)
def post_job_eye(
    job_id: str,
    body: ExecuteEyeRequest,
    store: InMemoryJobStore = Depends(get_job_store),
    provider: EyeProvider = Depends(get_eye_provider),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> ExecuteEyeResponse:
    try:
        model_id = validate_stage_model("eye", body.model_id)
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message=str(exc),
            details={"stage": "eye", "requested_model": getattr(body, "model_id", None)},
        ) from exc
    try:
        record = execute_job_eye(
            store,
            job_id=job_id,
            model_id=model_id,
            provider=provider,
            owner_id=owner_id,
            revision=revision,
        )
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message="Invalid request",
            details={"reason": str(exc)},
        ) from exc
    except EyeProviderFailedError as exc:
        raise ApiError(
            status_code=502,
            code="PROVIDER_FAILURE",
            message="Eye provider failed",
            details={},
        ) from exc
    return execute_eye_response(record)


@router.get(
    "/jobs/{job_id}/eye",
    response_model=GetEyeResponse,
    summary="Get stored Eye result",
    description="Return the persisted Eye observation. Does not execute Eye.",
    responses={403: _ERRORS[403], 404: _ERRORS[404], 409: _ERRORS[409]},
)
def get_job_eye_endpoint(
    job_id: str,
    store: InMemoryJobStore = Depends(get_job_store),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> GetEyeResponse:
    try:
        record = get_job_eye(store, job_id, owner_id=owner_id, revision=revision)
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    except EyeNotRunError:
        raise ApiError(
            status_code=409,
            code="EYE_NOT_RUN",
            message="Eye has not been executed for this job",
            details={"job_id": job_id},
        )
    return get_eye_response(record)


@router.post(
    "/jobs/{job_id}/brain",
    response_model=ExecuteBrainResponse,
    summary="Execute Brain",
    description=(
        "Run Brain for an existing job. Pass model_id or edit to an allowed model. "
        "The frozen job contract, stored EyeObservation, readiness, and reference "
        "evidence identity are taken from the job. The frontend does not resend the contract."
    ),
    responses={
        403: _ERRORS[403],
        404: _ERRORS[404],
        409: _ERRORS[409],
        422: _ERRORS[422],
        502: _ERRORS[502],
    },
)
def post_job_brain(
    job_id: str,
    body: ExecuteBrainRequest,
    store: InMemoryJobStore = Depends(get_job_store),
    provider: BrainProvider = Depends(get_brain_provider),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> ExecuteBrainResponse:
    try:
        model_id = validate_stage_model("brain", body.model_id)
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message=str(exc),
            details={"stage": "brain", "requested_model": getattr(body, "model_id", None)},
        ) from exc
    try:
        record = execute_job_brain(
            store,
            job_id=job_id,
            model_id=model_id,
            provider=provider,
            owner_id=owner_id,
            revision=revision,
        )
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    except EyeNotRunError:
        raise ApiError(
            status_code=409,
            code="EYE_NOT_RUN",
            message="Eye has not been executed for this job",
            details={"job_id": job_id},
        )
    except BrainNotReadyError as exc:
        raise ApiError(
            status_code=409,
            code="BRAIN_NOT_READY",
            message="Eye readiness holds this job; Brain was not executed",
            details={"job_id": job_id, "reasons": exc.reasons},
        )
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message="Invalid request",
            details={"reason": str(exc)},
        ) from exc
    except BrainProviderFailedError as exc:
        raise ApiError(
            status_code=502,
            code="PROVIDER_FAILURE",
            message="Brain provider failed",
            details=dict(exc.details),
        ) from exc
    return execute_brain_response(record)


@router.get(
    "/jobs/{job_id}/brain",
    response_model=GetBrainResponse,
    summary="Get stored Brain result",
    description="Return the persisted Brain result. Does not execute Brain.",
    responses={403: _ERRORS[403], 404: _ERRORS[404], 409: _ERRORS[409]},
)
def get_job_brain_endpoint(
    job_id: str,
    store: InMemoryJobStore = Depends(get_job_store),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> GetBrainResponse:
    try:
        record = get_job_brain(store, job_id, owner_id=owner_id, revision=revision)
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    except EyeNotRunError:
        raise ApiError(
            status_code=409,
            code="EYE_NOT_RUN",
            message="Eye has not been executed for this job",
            details={"job_id": job_id},
        )
    except BrainNotRunError:
        raise ApiError(
            status_code=409,
            code="BRAIN_NOT_RUN",
            message="Brain has not been executed for this job",
            details={"job_id": job_id},
        )
    return get_brain_response(record)


@router.post(
    "/jobs/{job_id}/stylist",
    response_model=ExecuteStylistResponse,
    summary="Execute Stylist",
    description=(
        "Run Stylist for an existing job. Pass model_id or edit to an allowed model. "
        "The frozen job contract, stored EyeObservation, BrainPlan, and evidence identity "
        "are taken from the job."
    ),
    responses={
        403: _ERRORS[403],
        404: _ERRORS[404],
        409: _ERRORS[409],
        422: _ERRORS[422],
        502: _ERRORS[502],
    },
)
def post_job_stylist(
    job_id: str,
    body: ExecuteStylistRequest,
    store: InMemoryJobStore = Depends(get_job_store),
    provider: StylistProvider = Depends(get_stylist_provider),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> ExecuteStylistResponse:
    try:
        model_id = validate_stage_model("stylist", body.model_id)
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message=str(exc),
            details={"stage": "stylist", "requested_model": getattr(body, "model_id", None)},
        ) from exc
    try:
        record = execute_job_stylist(
            store,
            job_id=job_id,
            model_id=model_id,
            provider=provider,
            owner_id=owner_id,
            revision=revision,
        )
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    except EyeNotRunError:
        raise ApiError(
            status_code=409,
            code="EYE_NOT_RUN",
            message="Eye has not been executed for this job",
            details={"job_id": job_id},
        )
    except BrainNotRunError:
        raise ApiError(
            status_code=409,
            code="BRAIN_NOT_RUN",
            message="Brain has not been executed for this job",
            details={"job_id": job_id},
        )
    except StylistNotReadyError as exc:
        raise ApiError(
            status_code=409,
            code="STYLIST_NOT_READY",
            message="Brain plan holds this job; Stylist was not executed",
            details={"job_id": job_id, "reasons": exc.reasons},
        )
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message="Invalid request",
            details={"reason": str(exc)},
        ) from exc
    except StylistProviderFailedError as exc:
        raise ApiError(
            status_code=502,
            code="PROVIDER_FAILURE",
            message="Stylist provider failed",
            details=dict(exc.details),
        ) from exc
    return execute_stylist_response(record)


@router.get(
    "/jobs/{job_id}/stylist",
    response_model=GetStylistResponse,
    summary="Get stored Stylist result",
    description="Return the persisted Stylist result. Does not execute Stylist.",
    responses={403: _ERRORS[403], 404: _ERRORS[404], 409: _ERRORS[409]},
)
def get_job_stylist_endpoint(
    job_id: str,
    store: InMemoryJobStore = Depends(get_job_store),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> GetStylistResponse:
    try:
        record = get_job_stylist(store, job_id, owner_id=owner_id, revision=revision)
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    except EyeNotRunError:
        raise ApiError(
            status_code=409,
            code="EYE_NOT_RUN",
            message="Eye has not been executed for this job",
            details={"job_id": job_id},
        )
    except BrainNotRunError:
        raise ApiError(
            status_code=409,
            code="BRAIN_NOT_RUN",
            message="Brain has not been executed for this job",
            details={"job_id": job_id},
        )
    except StylistNotRunError:
        raise ApiError(
            status_code=409,
            code="STYLIST_NOT_RUN",
            message="Stylist has not been executed for this job",
            details={"job_id": job_id},
        )
    return get_stylist_response(record)


@router.post(
    "/jobs/{job_id}/compile",
    response_model=ExecuteCompileResponse,
    summary="Execute Engine compile",
    description=(
        "Compile Brain locks and Stylist scene decisions into an EngineCompile "
        "artifact. Pass model_id or edit to an allowed model. "
        "Does not generate an image."
    ),
    responses={
        403: _ERRORS[403],
        404: _ERRORS[404],
        409: _ERRORS[409],
        422: _ERRORS[422],
        502: _ERRORS[502],
    },
)
def post_job_compile(
    job_id: str,
    body: ExecuteCompileRequest,
    store: InMemoryJobStore = Depends(get_job_store),
    compiler: EngineCompiler = Depends(get_engine_compiler),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> ExecuteCompileResponse:
    try:
        model_id = validate_stage_model("compile", body.model_id)
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message=str(exc),
            details={"stage": "compile", "requested_model": getattr(body, "model_id", None)},
        ) from exc
    try:
        record = execute_job_compile(
            store,
            job_id=job_id,
            model_id=model_id,
            compiler=compiler,
            owner_id=owner_id,
            revision=revision,
        )
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    except EyeNotRunError:
        raise ApiError(
            status_code=409,
            code="EYE_NOT_RUN",
            message="Eye has not been executed for this job",
            details={"job_id": job_id},
        )
    except BrainNotRunError:
        raise ApiError(
            status_code=409,
            code="BRAIN_NOT_RUN",
            message="Brain has not been executed for this job",
            details={"job_id": job_id},
        )
    except StylistNotRunError:
        raise ApiError(
            status_code=409,
            code="STYLIST_NOT_RUN",
            message="Stylist has not been executed for this job",
            details={"job_id": job_id},
        )
    except EngineNotReadyError as exc:
        raise ApiError(
            status_code=409,
            code="ENGINE_NOT_READY",
            message="Brain or Stylist holds this job; Engine compile was not executed as ready",
            details={"job_id": job_id, "reasons": exc.reasons},
        )
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message="Invalid request",
            details={"reason": str(exc)},
        ) from exc
    except EngineProviderFailedError as exc:
        raise ApiError(
            status_code=502,
            code="PROVIDER_FAILURE",
            message="Engine compiler failed",
            details=dict(exc.details),
        ) from exc
    return execute_compile_response(record)


@router.get(
    "/jobs/{job_id}/compile",
    response_model=GetCompileResponse,
    summary="Get stored Engine compile result",
    description="Return the persisted EngineCompile. Does not rerun compilation.",
    responses={403: _ERRORS[403], 404: _ERRORS[404], 409: _ERRORS[409]},
)
def get_job_compile_endpoint(
    job_id: str,
    store: InMemoryJobStore = Depends(get_job_store),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> GetCompileResponse:
    try:
        record = get_job_compile(store, job_id, owner_id=owner_id, revision=revision)
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    except EyeNotRunError:
        raise ApiError(
            status_code=409,
            code="EYE_NOT_RUN",
            message="Eye has not been executed for this job",
            details={"job_id": job_id},
        )
    except BrainNotRunError:
        raise ApiError(
            status_code=409,
            code="BRAIN_NOT_RUN",
            message="Brain has not been executed for this job",
            details={"job_id": job_id},
        )
    except StylistNotRunError:
        raise ApiError(
            status_code=409,
            code="STYLIST_NOT_RUN",
            message="Stylist has not been executed for this job",
            details={"job_id": job_id},
        )
    except EngineNotRunError:
        raise ApiError(
            status_code=409,
            code="ENGINE_NOT_RUN",
            message="Engine compile has not been executed for this job",
            details={"job_id": job_id},
        )
    return get_compile_response(record)


@router.post(
    "/jobs/{job_id}/generate",
    response_model=ExecuteGenerateResponse,
    summary="Execute generation",
    description=(
        "Claim an operation for the persisted EngineCompile and dispatch it "
        "through the generation adapter. The submitted model_id must match the "
        "compiled image model. Uncertain receipts are not retried. "
        "Does not critique, repair, or release."
    ),
    responses={
        403: _ERRORS[403],
        404: _ERRORS[404],
        409: _ERRORS[409],
        422: _ERRORS[422],
        502: _ERRORS[502],
    },
)
def post_job_generate(
    job_id: str,
    body: ExecuteGenerateRequest,
    store: InMemoryJobStore = Depends(get_job_store),
    provider: GenerationProvider = Depends(get_generation_provider),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> ExecuteGenerateResponse:
    try:
        model_id = validate_stage_model("generate", body.model_id)
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message=str(exc),
            details={"stage": "generate", "requested_model": getattr(body, "model_id", None)},
        ) from exc
    try:
        record = execute_job_generate(
            store,
            job_id=job_id,
            model_id=model_id,
            provider=provider,
            owner_id=owner_id,
            revision=revision,
        )
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    except ModelMismatchError as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message=str(exc),
            details={
                "job_id": job_id,
                "stage": exc.stage,
                "requested_model": exc.requested_model,
                "compiled_model": exc.compiled_model,
            },
        ) from exc
    except EyeNotRunError:
        raise ApiError(
            status_code=409,
            code="EYE_NOT_RUN",
            message="Eye has not been executed for this job",
            details={"job_id": job_id},
        )
    except BrainNotRunError:
        raise ApiError(
            status_code=409,
            code="BRAIN_NOT_RUN",
            message="Brain has not been executed for this job",
            details={"job_id": job_id},
        )
    except StylistNotRunError:
        raise ApiError(
            status_code=409,
            code="STYLIST_NOT_RUN",
            message="Stylist has not been executed for this job",
            details={"job_id": job_id},
        )
    except EngineNotRunError:
        raise ApiError(
            status_code=409,
            code="ENGINE_NOT_RUN",
            message="Engine compile has not been executed for this job",
            details={"job_id": job_id},
        )
    except GenerationNotReadyError as exc:
        raise ApiError(
            status_code=409,
            code="GENERATION_NOT_READY",
            message="Engine compile holds this job; generation was not dispatched",
            details={"job_id": job_id, "reasons": exc.reasons},
        )
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message="Invalid request",
            details={"reason": str(exc)},
        ) from exc
    except GenerationProviderFailedError as exc:
        raise ApiError(
            status_code=502,
            code="PROVIDER_FAILURE",
            message="Generation provider failed",
            details=dict(exc.details),
        ) from exc
    return execute_generate_response(record)


@router.get(
    "/jobs/{job_id}/generate",
    response_model=GetGenerateResponse,
    summary="Get stored generation receipt",
    description="Return the persisted generation operation and receipt. Does not dispatch.",
    responses={403: _ERRORS[403], 404: _ERRORS[404], 409: _ERRORS[409]},
)
def get_job_generate_endpoint(
    job_id: str,
    store: InMemoryJobStore = Depends(get_job_store),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> GetGenerateResponse:
    try:
        record = get_job_generation(store, job_id, owner_id=owner_id, revision=revision)
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    except EyeNotRunError:
        raise ApiError(
            status_code=409,
            code="EYE_NOT_RUN",
            message="Eye has not been executed for this job",
            details={"job_id": job_id},
        )
    except BrainNotRunError:
        raise ApiError(
            status_code=409,
            code="BRAIN_NOT_RUN",
            message="Brain has not been executed for this job",
            details={"job_id": job_id},
        )
    except StylistNotRunError:
        raise ApiError(
            status_code=409,
            code="STYLIST_NOT_RUN",
            message="Stylist has not been executed for this job",
            details={"job_id": job_id},
        )
    except EngineNotRunError:
        raise ApiError(
            status_code=409,
            code="ENGINE_NOT_RUN",
            message="Engine compile has not been executed for this job",
            details={"job_id": job_id},
        )
    except GenerationNotRunError:
        raise ApiError(
            status_code=409,
            code="GENERATION_NOT_RUN",
            message="Generation has not been executed for this job",
            details={"job_id": job_id},
        )
    return get_generate_response(record)


@router.post(
    "/jobs/{job_id}/critique",
    response_model=ExecuteCritiqueResponse,
    summary="Execute Critique · assess",
    description=(
        "Inspect the original reference and generated image against the locked "
        "contract. Pass model_id or edit to an allowed model. "
        "Does not repair or release. GET does not rerun this call."
    ),
    responses={
        403: _ERRORS[403],
        404: _ERRORS[404],
        409: _ERRORS[409],
        422: _ERRORS[422],
        502: _ERRORS[502],
    },
)
def post_job_critique(
    job_id: str,
    body: ExecuteCritiqueRequest,
    store: InMemoryJobStore = Depends(get_job_store),
    provider: CritiqueProvider = Depends(get_critique_provider),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> ExecuteCritiqueResponse:
    try:
        model_id = validate_stage_model("critique", body.model_id)
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message=str(exc),
            details={"stage": "critique", "requested_model": getattr(body, "model_id", None)},
        ) from exc
    try:
        record = execute_job_critique(
            store,
            job_id=job_id,
            model_id=model_id,
            provider=provider,
            owner_id=owner_id,
            revision=revision,
        )
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    except EyeNotRunError:
        raise ApiError(
            status_code=409,
            code="EYE_NOT_RUN",
            message="Eye has not been executed for this job",
            details={"job_id": job_id},
        )
    except BrainNotRunError:
        raise ApiError(
            status_code=409,
            code="BRAIN_NOT_RUN",
            message="Brain has not been executed for this job",
            details={"job_id": job_id},
        )
    except BrainNotReadyError as exc:
        raise ApiError(
            status_code=409,
            code="BRAIN_NOT_READY",
            message="Eye readiness holds this job; Critique was not executed",
            details={"job_id": job_id, "reasons": exc.reasons},
        )
    except StylistNotRunError:
        raise ApiError(
            status_code=409,
            code="STYLIST_NOT_RUN",
            message="Stylist has not been executed for this job",
            details={"job_id": job_id},
        )
    except StylistNotReadyError as exc:
        raise ApiError(
            status_code=409,
            code="STYLIST_NOT_READY",
            message="Brain plan holds this job; Critique was not executed",
            details={"job_id": job_id, "reasons": exc.reasons},
        )
    except EngineNotRunError:
        raise ApiError(
            status_code=409,
            code="ENGINE_NOT_RUN",
            message="Engine compile has not been executed for this job",
            details={"job_id": job_id},
        )
    except EngineNotReadyError as exc:
        raise ApiError(
            status_code=409,
            code="ENGINE_NOT_READY",
            message="Engine compile holds this job; Critique was not executed",
            details={"job_id": job_id, "reasons": exc.reasons},
        )
    except GenerationNotRunError:
        raise ApiError(
            status_code=409,
            code="GENERATION_NOT_RUN",
            message="Generation has not been executed for this job",
            details={"job_id": job_id},
        )
    except GenerationNotReadyError as exc:
        raise ApiError(
            status_code=409,
            code="GENERATION_NOT_READY",
            message="Generation is not completed or the generated image is missing",
            details={"job_id": job_id, "reasons": exc.reasons},
        )
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message="Invalid request",
            details={"reason": str(exc)},
        ) from exc
    except CritiqueProviderFailedError as exc:
        raise ApiError(
            status_code=502,
            code="PROVIDER_FAILURE",
            message="Critique provider failed",
            details=dict(exc.details),
        ) from exc
    return execute_critique_response(record)


@router.get(
    "/jobs/{job_id}/critique",
    response_model=GetCritiqueResponse,
    summary="Get stored Critique · assess result",
    description="Return the persisted critique. Does not rerun Critique.",
    responses={403: _ERRORS[403], 404: _ERRORS[404], 409: _ERRORS[409]},
)
def get_job_critique_endpoint(
    job_id: str,
    store: InMemoryJobStore = Depends(get_job_store),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> GetCritiqueResponse:
    try:
        record = get_job_critique(store, job_id, owner_id=owner_id, revision=revision)
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    except EyeNotRunError:
        raise ApiError(
            status_code=409,
            code="EYE_NOT_RUN",
            message="Eye has not been executed for this job",
            details={"job_id": job_id},
        )
    except BrainNotRunError:
        raise ApiError(
            status_code=409,
            code="BRAIN_NOT_RUN",
            message="Brain has not been executed for this job",
            details={"job_id": job_id},
        )
    except StylistNotRunError:
        raise ApiError(
            status_code=409,
            code="STYLIST_NOT_RUN",
            message="Stylist has not been executed for this job",
            details={"job_id": job_id},
        )
    except EngineNotRunError:
        raise ApiError(
            status_code=409,
            code="ENGINE_NOT_RUN",
            message="Engine compile has not been executed for this job",
            details={"job_id": job_id},
        )
    except GenerationNotRunError:
        raise ApiError(
            status_code=409,
            code="GENERATION_NOT_RUN",
            message="Generation has not been executed for this job",
            details={"job_id": job_id},
        )
    except CritiqueNotRunError:
        raise ApiError(
            status_code=409,
            code="CRITIQUE_NOT_RUN",
            message="Critique has not been executed for this job",
            details={"job_id": job_id},
        )
    return get_critique_response(record)


@router.post(
    "/jobs/{job_id}/repair",
    response_model=ExecuteRepairResponse,
    summary="Execute Critique · repair",
    description=(
        "Plan and execute one bounded repair (maximum two). "
        "Requires a Critique assessment with overall_result=repair_required. "
        "The submitted model_id must match the compiled image model. "
        "The planner is deterministic. Does not create Repair #3 or release."
    ),
    responses={
        403: _ERRORS[403],
        404: _ERRORS[404],
        409: _ERRORS[409],
        422: _ERRORS[422],
        502: _ERRORS[502],
    },
)
def post_job_repair(
    job_id: str,
    body: ExecuteRepairRequest,
    store: InMemoryJobStore = Depends(get_job_store),
    planner: RepairPlanner = Depends(get_repair_planner),
    provider: GenerationProvider = Depends(get_generation_provider),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> ExecuteRepairResponse:
    try:
        model_id = validate_stage_model("repair", body.model_id)
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message=str(exc),
            details={"stage": "repair", "requested_model": getattr(body, "model_id", None)},
        ) from exc
    try:
        record = execute_job_repair(
            store,
            job_id=job_id,
            planner=planner,
            provider=provider,
            model_id=model_id,
            owner_id=owner_id,
            revision=revision,
        )
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    except ModelMismatchError as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message=str(exc),
            details={
                "job_id": job_id,
                "stage": exc.stage,
                "requested_model": exc.requested_model,
                "compiled_model": exc.compiled_model,
            },
        ) from exc
    except EyeNotRunError:
        raise ApiError(
            status_code=409,
            code="EYE_NOT_RUN",
            message="Eye has not been executed for this job",
            details={"job_id": job_id},
        )
    except BrainNotRunError:
        raise ApiError(
            status_code=409,
            code="BRAIN_NOT_RUN",
            message="Brain has not been executed for this job",
            details={"job_id": job_id},
        )
    except StylistNotRunError:
        raise ApiError(
            status_code=409,
            code="STYLIST_NOT_RUN",
            message="Stylist has not been executed for this job",
            details={"job_id": job_id},
        )
    except EngineNotRunError:
        raise ApiError(
            status_code=409,
            code="ENGINE_NOT_RUN",
            message="Engine compile has not been executed for this job",
            details={"job_id": job_id},
        )
    except GenerationNotRunError:
        raise ApiError(
            status_code=409,
            code="GENERATION_NOT_RUN",
            message="Generation has not been executed for this job",
            details={"job_id": job_id},
        )
    except GenerationNotReadyError as exc:
        raise ApiError(
            status_code=409,
            code="GENERATION_NOT_READY",
            message="Generation is not completed or the generated image is missing",
            details={"job_id": job_id, "reasons": exc.reasons},
        )
    except CritiqueNotRunError:
        raise ApiError(
            status_code=409,
            code="CRITIQUE_NOT_RUN",
            message="Critique has not been executed for this job",
            details={"job_id": job_id},
        )
    except RepairNotRequiredError as exc:
        raise ApiError(
            status_code=409,
            code="REPAIR_NOT_REQUIRED",
            message="Critique does not require repair",
            details={"job_id": job_id, "overall_result": exc.overall_result},
        )
    except RepairNotReadyError as exc:
        raise ApiError(
            status_code=409,
            code="REPAIR_NOT_READY",
            message="Critique holds this job; repair was not executed",
            details={"job_id": job_id, "reasons": exc.reasons},
        )
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message="Invalid request",
            details={"reason": str(exc)},
        ) from exc
    except RepairProviderFailedError as exc:
        raise ApiError(
            status_code=502,
            code="PROVIDER_FAILURE",
            message="Repair provider failed",
            details=dict(exc.details),
        ) from exc
    return execute_repair_response(record)


@router.get(
    "/jobs/{job_id}/repair",
    response_model=GetRepairResponse,
    summary="Get stored Critique · repair result",
    description="Return the persisted repair plan, lineage, and receipt. Does not dispatch.",
    responses={403: _ERRORS[403], 404: _ERRORS[404], 409: _ERRORS[409]},
)
def get_job_repair_endpoint(
    job_id: str,
    store: InMemoryJobStore = Depends(get_job_store),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> GetRepairResponse:
    try:
        record = get_job_repair(store, job_id, owner_id=owner_id, revision=revision)
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    except EyeNotRunError:
        raise ApiError(
            status_code=409,
            code="EYE_NOT_RUN",
            message="Eye has not been executed for this job",
            details={"job_id": job_id},
        )
    except BrainNotRunError:
        raise ApiError(
            status_code=409,
            code="BRAIN_NOT_RUN",
            message="Brain has not been executed for this job",
            details={"job_id": job_id},
        )
    except StylistNotRunError:
        raise ApiError(
            status_code=409,
            code="STYLIST_NOT_RUN",
            message="Stylist has not been executed for this job",
            details={"job_id": job_id},
        )
    except EngineNotRunError:
        raise ApiError(
            status_code=409,
            code="ENGINE_NOT_RUN",
            message="Engine compile has not been executed for this job",
            details={"job_id": job_id},
        )
    except GenerationNotRunError:
        raise ApiError(
            status_code=409,
            code="GENERATION_NOT_RUN",
            message="Generation has not been executed for this job",
            details={"job_id": job_id},
        )
    except CritiqueNotRunError:
        raise ApiError(
            status_code=409,
            code="CRITIQUE_NOT_RUN",
            message="Critique has not been executed for this job",
            details={"job_id": job_id},
        )
    except RepairNotRunError:
        raise ApiError(
            status_code=409,
            code="REPAIR_NOT_RUN",
            message="Repair has not been executed for this job",
            details={"job_id": job_id},
        )
    return get_repair_response(record)


@router.get(
    "/jobs/{job_id}/generate/image",
    summary="Get generated image",
    description=(
        "Return the generated image bytes for this job. "
        "Does not dispatch generation. Missing images are errors, not empty 200 responses."
    ),
    response_class=Response,
    responses={
        200: {
            "description": "Generated image bytes",
            "content": {
                "image/png": {"schema": {"type": "string", "format": "binary"}},
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
                "image/webp": {"schema": {"type": "string", "format": "binary"}},
            },
        },
        403: _ERRORS[403],
        404: _ERRORS[404],
        409: _ERRORS[409],
    },
)
def get_job_generate_image_endpoint(
    job_id: str,
    store: InMemoryJobStore = Depends(get_job_store),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> Response:
    try:
        record = get_job_generation(store, job_id, owner_id=owner_id, revision=revision)
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    except EyeNotRunError:
        raise ApiError(
            status_code=409,
            code="EYE_NOT_RUN",
            message="Eye has not been executed for this job",
            details={"job_id": job_id},
        )
    except BrainNotRunError:
        raise ApiError(
            status_code=409,
            code="BRAIN_NOT_RUN",
            message="Brain has not been executed for this job",
            details={"job_id": job_id},
        )
    except StylistNotRunError:
        raise ApiError(
            status_code=409,
            code="STYLIST_NOT_RUN",
            message="Stylist has not been executed for this job",
            details={"job_id": job_id},
        )
    except EngineNotRunError:
        raise ApiError(
            status_code=409,
            code="ENGINE_NOT_RUN",
            message="Engine compile has not been executed for this job",
            details={"job_id": job_id},
        )
    except GenerationNotRunError:
        raise ApiError(
            status_code=409,
            code="GENERATION_NOT_RUN",
            message="Generation has not been executed for this job",
            details={"job_id": job_id},
        )
    image = _generated_image_bytes(record)
    if image is None:
        raise ApiError(
            status_code=409,
            code="GENERATION_IMAGE_UNAVAILABLE",
            message="Generated image is not available for this job",
            details={"job_id": job_id},
        )
    data, media_type = image
    return Response(content=data, media_type=media_type)


@router.get(
    "/jobs/{job_id}/status",

    response_model=JobStatusView,
    summary="Get job status",
    description="Return a short status object for the current stage and state.",
    responses={403: _ERRORS[403], 404: _ERRORS[404], 409: _ERRORS[409]},
)
def get_job_status(
    job_id: str,
    store: InMemoryJobStore = Depends(get_job_store),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> JobStatusView:
    try:
        record = get_job(store, job_id, owner_id=owner_id, revision=revision)
    except JobNotFoundError:
        _not_found(job_id)
    except JobOwnerMismatchError as exc:
        _owner_mismatch(job_id, exc.owner_id)
    except RevisionMismatchError as exc:
        _revision_mismatch(job_id, exc.expected, exc.actual)
    return job_status_view(record)


def _generated_image_bytes(record: JobRecord) -> tuple[bytes, str] | None:
    stored = record.generation
    if stored is None or stored.receipt is None or stored.receipt.output is None:
        return None
    if stored.receipt.status != "completed":
        return None
    output = stored.receipt.output
    data = record.reference_bytes.get(output.output_id)
    if not data:
        data = get_artifact_store().get_output(
            record.job_id, output_filename(output.media_type)
        )
    if not data:
        return None
    return data, content_type_for(output.media_type)
