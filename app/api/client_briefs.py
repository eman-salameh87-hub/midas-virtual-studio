"""Client brief persistence API. Does not create jobs or schedule planning.

brief_id is the immutable store key for one persisted revision.
contract_id and revision are Architecture A identity. UIMidas does not emit
them. When omitted on POST, the server applies explicit development-only
identity from MIDAS_DEV_OWNER_ID / MIDAS_DEV_CONTRACT_ID. That is not
production identity. Uniqueness of (contract_id, revision) is unresolved.

This accepts the local UIMidas studio-jobs-v2-draft envelope. Equivalence
with the published Client Studio page is unverified.
"""

from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.api.errors import ApiError, ErrorResponse
from app.api.jobs import (
    get_brain_provider,
    get_engine_compiler,
    get_eye_provider,
    get_job_store,
    get_stylist_provider,
)
from app.api.schemas import JobStatusView, job_status_view
from app.contracts.brief_mapping import (
    BRIEF_MAPPING_UNRESOLVED,
    Phase0FieldsNotInBrief,
    ReferenceBytes,
)
from app.contracts.client_brief import (
    PROJECTS_NOT_SUPPORTED,
    UNSUPPORTED_BRIEF_SCHEMA,
    ClientBriefRecord,
    ProposedJobContract,
    classify_unsupported_brief_payload,
    dump_omitting_optional_nones,
)
from app.providers.brain import BrainProvider
from app.providers.engine import EngineCompiler
from app.providers.eye import EyeProvider
from app.providers.stylist import StylistProvider
from app.runtime.brief_jobs import BriefJobPrepareError, prepare_job_from_saved_brief
from app.runtime.client_briefs import (
    CLIENT_BRIEF_STORE,
    ClientBriefAlreadyPersistedError,
    ClientBriefNotFoundError,
    ClientBriefOwnerMismatchError,
    ClientBriefRevisionMismatchError,
    InMemoryClientBriefStore,
    create_client_brief,
    get_client_brief,
)
from app.runtime.dev_identity import (
    IDENTITY_HELP,
    IDENTITY_NOT_CONFIGURED,
    INCOMPLETE_PERSIST_IDENTITY,
    load_dev_persist_identity,
)
from app.runtime.orchestrator import schedule_planning
from app.runtime.state import InMemoryJobStore

router = APIRouter(prefix="/api/v1", tags=["client-briefs"])

OwnerIdParam = Annotated[
    str | None,
    Query(description="Optional owner check. When set, must match the brief owner_id."),
]
RevisionParam = Annotated[
    int | None,
    Query(
        description="Optional revision check. When set, must match the frozen brief revision."
    ),
]

_ERRORS = {
    403: {"model": ErrorResponse, "description": "Brief owner does not match"},
    404: {"model": ErrorResponse, "description": "Client brief not found"},
    409: {"model": ErrorResponse, "description": "Requested revision does not match"},
    422: {"model": ErrorResponse, "description": "Invalid request"},
}


def get_client_brief_store() -> InMemoryClientBriefStore:
    return CLIENT_BRIEF_STORE


class CreateClientBriefRequest(BaseModel):
    """Persist a local UIMidas ProposedJobContract. Do not send brief_hash.

    owner_id, contract_id, and revision are persist-caller identity. UIMidas
    does not emit them. When all three are omitted, development-only identity
    configuration is used. Placeholder nulls on the envelope are not identity.
    """

    model_config = ConfigDict(extra="forbid")

    owner_id: str | None = Field(default=None, min_length=1)
    contract_id: str | None = Field(default=None, min_length=1)
    revision: int | None = Field(default=None, ge=1)
    client_brief: dict[str, Any]

    @model_validator(mode="before")
    @classmethod
    def drop_client_brief_hash(cls, value: object) -> object:
        if not isinstance(value, dict) or "brief_hash" not in value:
            return value
        data = dict(value)
        data.pop("brief_hash", None)
        return data


class PrepareJobFromBriefRequest(BaseModel):
    """Create a Phase-0 job from a saved brief. Does not rewrite the brief.

    reference_files must include content_base64 for the product image.
    Engine fields that UIMidas does not collect are derived by the adapter.
    phase0_fields_not_in_brief is an optional override for those internals.
    """

    model_config = ConfigDict(extra="forbid")

    reference_files: list[ReferenceBytes] = Field(min_length=1)
    phase0_fields_not_in_brief: Phase0FieldsNotInBrief | None = None


class PreparedExecution(BaseModel):
    """One EngineCompile / generate path created from a UIMidas view or output."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    requested_view: str
    image_proportions: str
    resolution: str
    requested_outcomes: list[str]


class PrepareJobFromBriefResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief_id: str
    brief_hash: str
    job_id: str
    job_ids: list[str]
    executions: list[PreparedExecution]
    owner_id: str
    contract_id: str
    revision: int
    stage: str
    state: str
    status: JobStatusView
    generation_started: bool = False
    pre_generation_approved: bool = False


class ClientBriefView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    brief_id: str
    owner_id: str
    contract_id: str
    revision: int
    brief_hash: str
    client_brief: ProposedJobContract


def public_validation_issues(exc: ValidationError) -> list[dict[str, object]]:
    """Keep loc/type/msg. Drop input values and validator context."""

    issues: list[dict[str, object]] = []
    for error in exc.errors():
        issues.append(
            {
                "loc": list(error.get("loc", ())),
                "type": str(error.get("type", "")),
                "msg": str(error.get("msg", "")),
            }
        )
    return issues


def _brief_view(record: ClientBriefRecord) -> ClientBriefView:
    assert record.brief_hash is not None
    return ClientBriefView(
        brief_id=record.brief_id,
        owner_id=record.owner_id,
        contract_id=record.contract_id,
        revision=record.revision,
        brief_hash=record.brief_hash,
        client_brief=record.client_brief,
    )


def _not_found(brief_id: str) -> NoReturn:
    raise ApiError(
        status_code=404,
        code="CLIENT_BRIEF_NOT_FOUND",
        message="Client brief not found",
        details={"brief_id": brief_id},
    )


def _owner_mismatch(brief_id: str, owner_id: str) -> NoReturn:
    raise ApiError(
        status_code=403,
        code="JOB_OWNER_MISMATCH",
        message="Client brief does not belong to this owner",
        details={"brief_id": brief_id, "owner_id": owner_id},
    )


def resolve_persist_identity(
    owner_id: str | None,
    contract_id: str | None,
    revision: int | None,
) -> tuple[str, str, int]:
    """Use explicit request identity, else development-only configuration.

    Does not read UIMidas ownerIdentity placeholders.
    """

    supplied = (owner_id, contract_id, revision)
    if all(value is not None for value in supplied):
        assert owner_id is not None and contract_id is not None and revision is not None
        return owner_id, contract_id, revision
    if any(value is not None for value in supplied):
        raise ApiError(
            status_code=422,
            code=INCOMPLETE_PERSIST_IDENTITY,
            message=(
                "owner_id, contract_id, and revision must be supplied together, "
                "or omitted so development identity configuration can be applied"
            ),
            details={
                "owner_id_present": owner_id is not None,
                "contract_id_present": contract_id is not None,
                "revision_present": revision is not None,
            },
        )
    identity = load_dev_persist_identity()
    if identity is None:
        raise ApiError(
            status_code=503,
            code=IDENTITY_NOT_CONFIGURED,
            message=IDENTITY_HELP,
            details={
                "required": ["MIDAS_DEV_OWNER_ID", "MIDAS_DEV_CONTRACT_ID"],
                "optional": ["MIDAS_DEV_CONTRACT_REVISION"],
            },
        )
    return identity.owner_id, identity.contract_id, identity.revision


def _revision_mismatch(brief_id: str, expected: int, actual: int) -> NoReturn:
    raise ApiError(
        status_code=409,
        code="REVISION_MISMATCH",
        message="Requested revision does not match the frozen client brief",
        details={"brief_id": brief_id, "expected": expected, "actual": actual},
    )


@router.post(
    "/client-briefs",
    response_model=ClientBriefView,
    summary="Persist a client brief",
    description=(
        "Accept a local UIMidas ProposedJobContract (contractVersion "
        "studio-jobs-v2-draft) and freeze it under a new brief_id. This is not "
        "a captured original Client Studio snapshot. This does not create a "
        "Phase-0 execution contract, does not schedule planning, and does not "
        "call providers. Do not send brief_hash; the server derives it from "
        "owner_id, contract_id, and the submit envelope. "
        "Projects submit returns PROJECTS_NOT_SUPPORTED. Obsolete display-string "
        "snapshots and other contractVersion values return UNSUPPORTED_BRIEF_SCHEMA. "
        "The on-disk record is immutable; a later revision must use a new brief_id. "
        "UIMidas may omit owner_id, contract_id, and revision; the server then "
        "applies MIDAS_DEV_* development identity. Missing configuration returns "
        "IDENTITY_NOT_CONFIGURED and does not persist."
    ),
    responses={
        422: _ERRORS[422],
        503: {
            "model": ErrorResponse,
            "description": "Development persist identity is not configured",
        },
    },
)
def post_client_brief(
    body: CreateClientBriefRequest,
    store: InMemoryClientBriefStore = Depends(get_client_brief_store),
) -> ClientBriefView:
    owner_id, contract_id, revision = resolve_persist_identity(
        body.owner_id,
        body.contract_id,
        body.revision,
    )
    unsupported = classify_unsupported_brief_payload(body.client_brief)
    if unsupported == PROJECTS_NOT_SUPPORTED:
        raise ApiError(
            status_code=422,
            code=PROJECTS_NOT_SUPPORTED,
            message="Projects submit is not accepted on this endpoint",
            details={"reason": "Use the Manual UIMidas ProposedJobContract envelope"},
        )
    if unsupported == UNSUPPORTED_BRIEF_SCHEMA:
        raise ApiError(
            status_code=422,
            code=UNSUPPORTED_BRIEF_SCHEMA,
            message="Brief schema is not studio-jobs-v2-draft",
            details={"reason": "Unsupported or obsolete client brief schema"},
        )
    try:
        contract = ProposedJobContract.model_validate(body.client_brief)
        record = create_client_brief(
            store,
            owner_id=owner_id,
            contract_id=contract_id,
            revision=revision,
            client_brief=contract,
        )
    except ClientBriefAlreadyPersistedError as exc:
        raise ApiError(
            status_code=409,
            code="BRIEF_ALREADY_PERSISTED",
            message="A brief with this brief_id is already persisted",
            details={"brief_id": exc.brief_id},
        ) from exc
    except (ValueError, ValidationError) as exc:
        details: dict[str, object] = {"reason": "Invalid UIMidas ProposedJobContract"}
        if isinstance(exc, ValidationError):
            details["issues"] = public_validation_issues(exc)
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message="Invalid request",
            details=details,
        ) from exc
    return _brief_view(record)


@router.get(
    "/client-briefs/{brief_id}",
    response_model=ClientBriefView,
    summary="Get a client brief",
    description="Return the frozen local UIMidas ProposedJobContract.",
    responses={
        403: _ERRORS[403],
        404: _ERRORS[404],
        409: _ERRORS[409],
    },
)
def get_client_brief_endpoint(
    brief_id: str,
    store: InMemoryClientBriefStore = Depends(get_client_brief_store),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> ClientBriefView:
    try:
        record = get_client_brief(
            store,
            brief_id,
            owner_id=owner_id,
            revision=revision,
        )
    except ClientBriefNotFoundError:
        _not_found(brief_id)
    except ClientBriefOwnerMismatchError as exc:
        _owner_mismatch(brief_id, exc.owner_id)
    except ClientBriefRevisionMismatchError as exc:
        _revision_mismatch(brief_id, exc.expected, exc.actual)
    return _brief_view(record)


@router.post(
    "/client-briefs/{brief_id}/jobs",
    response_model=PrepareJobFromBriefResponse,
    summary="Create a Phase-0 job from a saved brief",
    description=(
        "Map the frozen UIMidas Manual one-by-one brief to Phase0JobContract, "
        "create a job, and schedule Eye → Brain → Stylist → Compile. Does not "
        "rewrite the saved brief, does not approve generation, and does not "
        "generate images. Unmapped required Phase-0 fields return "
        "BRIEF_MAPPING_UNRESOLVED."
    ),
    responses={
        403: _ERRORS[403],
        404: _ERRORS[404],
        409: _ERRORS[409],
        422: _ERRORS[422],
    },
)
def post_job_from_client_brief(
    brief_id: str,
    body: PrepareJobFromBriefRequest,
    brief_store: InMemoryClientBriefStore = Depends(get_client_brief_store),
    job_store: InMemoryJobStore = Depends(get_job_store),
    eye_provider: EyeProvider = Depends(get_eye_provider),
    brain_provider: BrainProvider = Depends(get_brain_provider),
    stylist_provider: StylistProvider = Depends(get_stylist_provider),
    compiler: EngineCompiler = Depends(get_engine_compiler),
    owner_id: OwnerIdParam = None,
    revision: RevisionParam = None,
) -> PrepareJobFromBriefResponse:
    try:
        brief = get_client_brief(
            brief_store,
            brief_id,
            owner_id=owner_id,
            revision=revision,
        )
    except ClientBriefNotFoundError:
        _not_found(brief_id)
    except ClientBriefOwnerMismatchError as exc:
        _owner_mismatch(brief_id, exc.owner_id)
    except ClientBriefRevisionMismatchError as exc:
        _revision_mismatch(brief_id, exc.expected, exc.actual)
    before = dump_omitting_optional_nones(brief.client_brief)
    try:
        prepared = prepare_job_from_saved_brief(
            job_store,
            brief,
            reference_files=body.reference_files,
            phase0_fields_not_in_brief=body.phase0_fields_not_in_brief,
        )
    except BriefJobPrepareError as exc:
        after = dump_omitting_optional_nones(brief.client_brief)
        if after != before:
            raise RuntimeError("saved brief changed after a failed prepare") from exc
        raise ApiError(
            status_code=422,
            code=BRIEF_MAPPING_UNRESOLVED,
            message=(
                "The saved brief cannot be mapped to Phase-0 without unresolved "
                "decisions. The brief was not changed and no job was created."
            ),
            details={
                "brief_id": brief_id,
                "issues": [issue.model_dump(mode="json") for issue in exc.result.issues],
            },
        ) from exc
    except (ValueError, ValidationError) as exc:
        raise ApiError(
            status_code=422,
            code="INVALID_REQUEST",
            message="Invalid request",
            details={"reason": str(exc)},
        ) from exc
    record = prepared.job
    for job in prepared.jobs:
        schedule_planning(
            job_store,
            job_id=job.job_id,
            eye_provider=eye_provider,
            brain_provider=brain_provider,
            stylist_provider=stylist_provider,
            compiler=compiler,
            owner_id=job.owner_id,
            revision=job.revision,
        )
    after = dump_omitting_optional_nones(brief.client_brief)
    if after != before:
        raise RuntimeError("saved brief changed after job prepare")
    return PrepareJobFromBriefResponse(
        brief_id=prepared.brief_id,
        brief_hash=prepared.brief_hash,
        job_id=record.job_id,
        job_ids=[job.job_id for job in prepared.jobs],
        executions=[
            PreparedExecution(
                job_id=job.job_id,
                requested_view=job.contract.outputs.views[0],
                image_proportions=job.contract.outputs.image_proportions,
                resolution=job.contract.outputs.resolution,
                requested_outcomes=list(job.contract.intent.requested_outcomes),
            )
            for job in prepared.jobs
        ],
        owner_id=record.owner_id,
        contract_id=record.contract.contract_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        status=job_status_view(record),
        generation_started=False,
        pre_generation_approved=record.pre_generation_approval is not None,
    )
