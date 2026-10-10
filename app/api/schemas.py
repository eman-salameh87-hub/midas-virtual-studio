"""Public JSON DTOs for the versioned jobs API."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from app.contracts.brain import BrainPlan
from app.contracts.critique import CritiqueAssessment
from app.contracts.engine import EngineCompile
from app.contracts.eye import EyeObservation
from app.contracts.generation import GenerationOperation, GenerationReceipt
from app.contracts.job import Phase0JobContract, RequestIdentity
from app.contracts.reference import ReferenceAsset
from app.contracts.repair import REPAIR_LIMIT, RepairPlan
from app.contracts.stylist import StylistPlan
from app.runtime.model_policy import (
    brain_model,
    critique_model,
    eye_model,
    image_model,
    stylist_model,
)
from app.contracts.review import ReviewStatus
from app.runtime.state import JobError, JobRecord, JobStage, JobState
from app.stages.eye import Readiness
from app.stages.repair import critique_matches_generation, repair_is_eligible

PublicCostStatus = Literal["known", "unknown", "not_recorded"]


def _stage_schema_extra(stage: str, model_func: object) -> object:
    def _extra(schema: dict) -> None:
        model = model_func()  # type: ignore[operator]
        schema.setdefault("properties", {}).setdefault("model_id", {})["default"] = model
        schema["properties"]["model_id"]["example"] = model
        schema["example"] = {"model_id": model}

    return _extra


class IntakeReferenceAsset(ReferenceAsset):
    """Create-page reference identity plus optional file bytes for intake.

    Frozen Job State stores ReferenceAsset identity only. content_base64 is
    required for JPG, PNG, and WebP and is not returned on GET.

    content_hash may be omitted or empty on create. The intake adapter
    computes SHA-256 of the decoded file bytes before the frozen contract
    is validated. A supplied hash must already be a lowercase sha256 digest
    and must match those bytes.
    """

    content_hash: str | None = Field(
        default=None,
        description=(
            "Optional on create. If omitted or empty, the server hashes the "
            "decoded content_base64 bytes. If supplied, it must match."
        ),
    )
    content_base64: str | None = Field(
        default=None,
        description=(
            "Raw base64 of the file bytes. Required for JPG, PNG, and WebP. "
            "Not included in job GET responses."
        ),
    )

    @field_validator("content_hash", mode="before")
    @classmethod
    def blank_intake_hash_is_omitted(cls, value: object) -> object:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("content_hash")
    @classmethod
    def sha256_hex(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError(
                "content_hash must be an explicit lowercase sha256 hex digest; "
                "the contract does not compute one"
            )
        return value


class IntakePhase0JobContract(Phase0JobContract):
    """Phase-0 contract as submitted on POST /jobs.

    request_identity is not caller input. The server hashes the reference
    bytes and computes request_hash after this body is accepted.
    """

    references: list[IntakeReferenceAsset] = Field(min_length=1)
    request_identity: SkipJsonSchema[RequestIdentity | None] = Field(
        default=None,
        description="Server-derived. Omit this object on create.",
    )

    @model_validator(mode="before")
    @classmethod
    def drop_client_request_identity(cls, value: object) -> object:
        """Ignore a caller-supplied identity. The frozen contract recomputes it."""

        if not isinstance(value, dict) or "request_identity" not in value:
            return value
        data = dict(value)
        data.pop("request_identity", None)
        return data


_CREATE_JOB_EXAMPLE: dict[str, object] = {
    "contract": {
        "contract_id": "contract-towel-1",
        "revision": 1,
        "owner_id": "owner-1",
        "intent": {
            "mode": "Manual",
            "job_type": "New Project",
            "job_option": "One by one (same department)",
            "requested_outcomes": ["Lifestyle"],
            "requested_pieces": ["towel"],
            "excluded_pieces": [],
            "selected_count": {"status": "declared", "value": 1},
        },
        "item": {
            "department": "Accessories",
            "category": "Bathroom",
            "subcategory": "Towels",
            "product_role": "hero",
        },
        "source_condition": {"input_condition": "annotated multi-view sheet"},
        "references": [
            {
                "reference_id": "ref-towel",
                "filename": "pixel.png",
                "media_type": "PNG",
                "hash_algorithm": "sha256",
                "role": "Product / vendor reference",
                "content_base64": (
                    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4"
                    "2mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
                ),
            }
        ],
        "outputs": {
            "views": ["Wide view"],
            "image_proportions": "Square · 1:1",
            "resolution": "2K",
            "package_members": ["lifestyle"],
        },
        "changes": {
            "policy_mode": "fidelity-locked",
            "allowed_changes": ["styled setting"],
            "protected_identity": ["towel count"],
            "room_locks": [],
            "creative_variables": [],
        },
        "preferences": {
            "lighting": "Soft daylight",
            "wall": "Sage",
            "floor": "Limestone",
            "plants": False,
            "human": False,
            "mood": "Calm & natural",
        },
        "statements": [],
        "unknowns": [],
        "conflicts": [],
    }
}


class CreateJobRequest(BaseModel):
    """Create a job from a Phase-0 contract. Eye is not executed.

    Do not send request_identity, request_hash, or source_hashes. The server
    derives them from the contract fields and the reference bytes.
    """

    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": _CREATE_JOB_EXAMPLE})

    contract: IntakePhase0JobContract


class CreateJobResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    owner_id: str
    contract_id: str
    revision: int
    state: JobState
    stage: JobStage
    status: JobState


class ExecuteEyeRequest(BaseModel):
    """Run Eye for an existing job.

    Model selection defaults to the configured Eye model (openai/gpt-4.1).
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=_stage_schema_extra("eye", eye_model),
    )

    model_id: str = Field(
        default_factory=eye_model,
        description="Model ID to execute Eye stage. Default: openai/gpt-4.1.",
    )


class ExecuteEyeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    revision: int
    stage: JobStage
    state: JobState
    observation: EyeObservation
    readiness: Readiness


class GetEyeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    revision: int
    stage: JobStage
    state: JobState
    observation: EyeObservation
    readiness: Readiness


class ExecuteBrainRequest(BaseModel):
    """Run Brain for an existing job.

    Model selection defaults to the configured Brain model (openai/gpt-4.1).
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=_stage_schema_extra("brain", brain_model),
    )

    model_id: str = Field(
        default_factory=brain_model,
        description="Model ID to execute Brain stage. Default: openai/gpt-4.1.",
    )


class BrainView(BaseModel):
    """Public persisted Brain plan."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    execution_status: str
    plan: BrainPlan


class ExecuteBrainResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    revision: int
    stage: JobStage
    state: JobState
    brain: BrainView


class GetBrainResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    revision: int
    stage: JobStage
    state: JobState
    brain: BrainView


class ExecuteStylistRequest(BaseModel):
    """Run Stylist for an existing job.

    Model selection defaults to the configured Stylist model (openai/gpt-4.1).
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=_stage_schema_extra("stylist", stylist_model),
    )

    model_id: str = Field(
        default_factory=stylist_model,
        description="Model ID to execute Stylist stage. Default: openai/gpt-4.1.",
    )


class StylistView(BaseModel):
    """Public persisted Stylist plan."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    execution_status: str
    plan: StylistPlan


class ExecuteStylistResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    revision: int
    stage: JobStage
    state: JobState
    stylist: StylistView


class GetStylistResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    revision: int
    stage: JobStage
    state: JobState
    stylist: StylistView


class ExecuteCompileRequest(BaseModel):
    """Run Engine compile for an existing job.

    Selects and persists the image model for downstream Generation and Repair.
    Default: google/gemini-3.1-flash-image.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=_stage_schema_extra("compile", image_model),
    )

    model_id: str = Field(
        default_factory=image_model,
        description="Image model ID to compile. Default: google/gemini-3.1-flash-image.",
    )


class EngineView(BaseModel):
    """Public persisted Engine compile artifact."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    execution_status: str
    compile: EngineCompile


class ExecuteCompileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    revision: int
    stage: JobStage
    state: JobState
    engine: EngineView


class GetCompileResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    revision: int
    stage: JobStage
    state: JobState
    engine: EngineView


class PreGenerationApprovalRequest(BaseModel):
    """Authorize the compiled render. Does not approve release.

    expires_at is optional because the job contract has no expiry field.
    """

    model_config = ConfigDict(extra="forbid")

    expires_at: str | None = None


class ExecuteGenerateRequest(BaseModel):
    """Dispatch generation for a persisted EngineCompile.

    The model_id must match the compiled image model.
    Default: google/gemini-3.1-flash-image.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=_stage_schema_extra("generate", image_model),
    )

    model_id: str = Field(
        default_factory=image_model,
        description="Image model ID for generation; must match compiled model. Default: google/gemini-3.1-flash-image.",
    )


class GenerationView(BaseModel):
    """Public persisted generation claim and receipt."""

    model_config = ConfigDict(extra="forbid")

    operation: GenerationOperation
    receipt: GenerationReceipt | None
    status: str
    output_available: bool
    image_url: str | None = Field(
        default=None,
        description="Frontend URL for the generated image bytes, when available.",
        examples=["/api/v1/jobs/00000000-0000-0000-0000-000000000000/generate/image"],
    )


class ExecuteGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    revision: int
    stage: JobStage
    state: JobState
    generation: GenerationView


class GetGenerateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    revision: int
    stage: JobStage
    state: JobState
    generation: GenerationView


class ExecuteCritiqueRequest(BaseModel):
    """Run Critique · assess for a completed generation.

    Model selection defaults to the configured Critique model (openai/gpt-4.1).
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=_stage_schema_extra("critique", critique_model),
    )

    model_id: str = Field(
        default_factory=critique_model,
        description="Model ID to execute Critique stage. Default: openai/gpt-4.1.",
    )


class CritiqueView(BaseModel):
    """Public persisted Critique · assess artifact."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    execution_status: str
    assessment: CritiqueAssessment


class ExecuteCritiqueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    revision: int
    stage: JobStage
    state: JobState
    critique: CritiqueView


class GetCritiqueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    revision: int
    stage: JobStage
    state: JobState
    critique: CritiqueView


class ExecuteRepairRequest(BaseModel):
    """Dispatch one bounded repair.

    Image generation uses the compiled image model and must match it.
    Default: google/gemini-3.1-flash-image.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra=_stage_schema_extra("repair", image_model),
    )

    model_id: str = Field(
        default_factory=image_model,
        description="Image model ID for repair generation; must match compiled model. Default: google/gemini-3.1-flash-image.",
    )


class RepairView(BaseModel):
    """Public persisted repair artifact, including lineage."""

    model_config = ConfigDict(extra="forbid")

    status: str
    repair_count: int
    repair_limit: int
    plan: RepairPlan
    history: list[RepairPlan]


class ExecuteRepairResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    revision: int
    stage: JobStage
    state: JobState
    repair: RepairView


class GetRepairResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    revision: int
    stage: JobStage
    state: JobState
    repair: RepairView


class JobEyeView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observation: EyeObservation
    readiness: Readiness


class PublicGenerationCost(BaseModel):
    """Provider-recorded cost for one generation. Unknown is never stored as zero."""

    model_config = ConfigDict(extra="forbid")

    output_id: str | None = None
    amount: float | None = None
    currency: str | None = None
    status: PublicCostStatus


class JobView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    owner_id: str
    contract: Phase0JobContract
    revision: int
    stage: JobStage
    state: JobState
    hold: Readiness | None
    error: JobError | None
    eye_available: bool
    brain_available: bool
    stylist_available: bool
    compile_available: bool
    generation_available: bool
    critique_available: bool
    repair_available: bool
    repair_eligible: bool
    critique_overall_result: str | None = None
    critique_matches_generation: bool = False
    generation_output_available: bool = False
    generation_output_id: str | None = None
    generation_cost: PublicGenerationCost | None = None
    initial_generation_cost: PublicGenerationCost | None = None
    repair_generation_cost: PublicGenerationCost | None = None
    generation_cost_total: PublicGenerationCost | None = None
    repair_count: int = 0
    repair_limit: int = 2
    eye: JobEyeView | None
    brain: BrainView | None
    stylist: StylistView | None
    engine: EngineView | None
    generation: GenerationView | None
    critique: CritiqueView | None
    repair: RepairView | None
    review_status: ReviewStatus | None = None
    package_status: ReviewStatus | None = None
    complete: bool = False
    releasable: bool = False
    approved: bool = False


class JobStatusView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    owner_id: str
    revision: int
    stage: JobStage
    state: JobState
    ready: bool
    eye_available: bool
    brain_available: bool
    stylist_available: bool
    compile_available: bool
    generation_available: bool
    critique_available: bool
    repair_available: bool
    repair_eligible: bool
    critique_overall_result: str | None = None
    critique_matches_generation: bool = False
    generation_output_available: bool = False
    generation_output_id: str | None = None
    generation_cost: PublicGenerationCost | None = None
    initial_generation_cost: PublicGenerationCost | None = None
    repair_generation_cost: PublicGenerationCost | None = None
    generation_cost_total: PublicGenerationCost | None = None
    repair_count: int = 0
    repair_limit: int = 2
    hold: Readiness | None
    error: JobError | None
    review_status: ReviewStatus | None = None
    package_status: ReviewStatus | None = None
    complete: bool = False
    releasable: bool = False
    approved: bool = False


def create_job_response(record: JobRecord) -> CreateJobResponse:
    return CreateJobResponse(
        job_id=record.job_id,
        owner_id=record.owner_id,
        contract_id=record.contract.contract_id,
        revision=record.revision,
        state=record.state,
        stage=record.stage,
        status=record.status,
    )


def execute_eye_response(record: JobRecord) -> ExecuteEyeResponse:
    assert record.observation is not None
    assert record.readiness is not None
    return ExecuteEyeResponse(
        job_id=record.job_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        observation=record.observation,
        readiness=record.readiness,
    )


def get_eye_response(record: JobRecord) -> GetEyeResponse:
    assert record.observation is not None
    assert record.readiness is not None
    return GetEyeResponse(
        job_id=record.job_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        observation=record.observation,
        readiness=record.readiness,
    )


def _brain_view(record: JobRecord) -> BrainView | None:
    stored = record.brain
    if stored is None or stored.result is None or stored.input is None:
        return None
    return BrainView(
        model_id=stored.model_id,
        execution_status=stored.status,
        plan=stored.result,
    )


def execute_brain_response(record: JobRecord) -> ExecuteBrainResponse:
    brain = _brain_view(record)
    assert brain is not None
    return ExecuteBrainResponse(
        job_id=record.job_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        brain=brain,
    )


def get_brain_response(record: JobRecord) -> GetBrainResponse:
    brain = _brain_view(record)
    assert brain is not None
    return GetBrainResponse(
        job_id=record.job_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        brain=brain,
    )


def _stylist_view(record: JobRecord) -> StylistView | None:
    stored = record.stylist
    if stored is None or stored.result is None or stored.input is None:
        return None
    return StylistView(
        model_id=stored.model_id,
        execution_status=stored.status,
        plan=stored.result,
    )


def execute_stylist_response(record: JobRecord) -> ExecuteStylistResponse:
    stylist = _stylist_view(record)
    assert stylist is not None
    return ExecuteStylistResponse(
        job_id=record.job_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        stylist=stylist,
    )


def get_stylist_response(record: JobRecord) -> GetStylistResponse:
    stylist = _stylist_view(record)
    assert stylist is not None
    return GetStylistResponse(
        job_id=record.job_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        stylist=stylist,
    )


def _engine_view(record: JobRecord) -> EngineView | None:
    stored = record.engine
    if stored is None or stored.result is None or stored.input is None:
        return None
    return EngineView(
        model_id=stored.model_id,
        execution_status=stored.status,
        compile=stored.result,
    )


def execute_compile_response(record: JobRecord) -> ExecuteCompileResponse:
    engine = _engine_view(record)
    assert engine is not None
    return ExecuteCompileResponse(
        job_id=record.job_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        engine=engine,
    )


def get_compile_response(record: JobRecord) -> GetCompileResponse:
    engine = _engine_view(record)
    assert engine is not None
    return GetCompileResponse(
        job_id=record.job_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        engine=engine,
    )


def generation_image_url(job_id: str) -> str:
    return f"/api/v1/jobs/{job_id}/generate/image"


def generation_output_available(record: JobRecord) -> bool:
    stored = record.generation
    if stored is None or stored.receipt is None or stored.receipt.output is None:
        return False
    if stored.receipt.status != "completed":
        return False
    if stored.checksum_status == "mismatch":
        return False
    output_id = stored.receipt.output.output_id
    if output_id in record.reference_bytes and record.reference_bytes[output_id]:
        return True
    return False


def _generation_view(record: JobRecord) -> GenerationView | None:
    stored = record.generation
    if stored is None:
        return None
    available = generation_output_available(record)
    return GenerationView(
        operation=stored.operation,
        receipt=stored.receipt,
        status=stored.status,
        output_available=available,
        image_url=generation_image_url(record.job_id) if available else None,
    )


def execute_generate_response(record: JobRecord) -> ExecuteGenerateResponse:
    generation = _generation_view(record)
    assert generation is not None
    return ExecuteGenerateResponse(
        job_id=record.job_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        generation=generation,
    )


def get_generate_response(record: JobRecord) -> GetGenerateResponse:
    generation = _generation_view(record)
    assert generation is not None and generation.receipt is not None
    return GetGenerateResponse(
        job_id=record.job_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        generation=generation,
    )


def _critique_view(record: JobRecord) -> CritiqueView | None:
    stored = record.critique
    if stored is None or stored.result is None:
        return None
    return CritiqueView(
        model_id=stored.model_id,
        execution_status=stored.status,
        assessment=stored.result,
    )


def execute_critique_response(record: JobRecord) -> ExecuteCritiqueResponse:
    critique = _critique_view(record)
    assert critique is not None
    return ExecuteCritiqueResponse(
        job_id=record.job_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        critique=critique,
    )


def get_critique_response(record: JobRecord) -> GetCritiqueResponse:
    critique = _critique_view(record)
    assert critique is not None
    return GetCritiqueResponse(
        job_id=record.job_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        critique=critique,
    )


def _repair_view(record: JobRecord) -> RepairView | None:
    stored = record.repair
    if stored is None:
        return None
    return RepairView(
        status=stored.status,
        repair_count=record.repair_count,
        repair_limit=record.repair_limit,
        plan=stored.plan,
        history=[item.plan for item in record.repairs],
    )


def execute_repair_response(record: JobRecord) -> ExecuteRepairResponse:
    repair = _repair_view(record)
    assert repair is not None
    return ExecuteRepairResponse(
        job_id=record.job_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        repair=repair,
    )


def get_repair_response(record: JobRecord) -> GetRepairResponse:
    repair = _repair_view(record)
    assert repair is not None
    return GetRepairResponse(
        job_id=record.job_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        repair=repair,
    )


def job_view(record: JobRecord) -> JobView:
    eye = None
    if record.observation is not None and record.readiness is not None:
        eye = JobEyeView(observation=record.observation, readiness=record.readiness)
    brain = _brain_view(record)
    stylist = _stylist_view(record)
    engine = _engine_view(record)
    generation = _generation_view(record)
    critique = _critique_view(record)
    repair = _repair_view(record)
    flags = _repair_status_flags(record)
    return JobView(
        job_id=record.job_id,
        owner_id=record.owner_id,
        contract=record.contract,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        hold=record.hold,
        error=record.error,
        eye_available=eye is not None,
        brain_available=brain is not None,
        stylist_available=stylist is not None,
        compile_available=engine is not None,
        generation_available=generation is not None and generation.receipt is not None,
        critique_available=critique is not None,
        repair_available=repair is not None,
        **flags,
        eye=eye,
        brain=brain,
        stylist=stylist,
        engine=engine,
        generation=generation,
        critique=critique,
        repair=repair,
        review_status=record.review_status,
        package_status=record.review_status,
        complete=record.complete,
        releasable=record.releasable,
        approved=record.approval is not None and record.review_status in {
            "owner_approved",
            "released",
        },
    )


def _receipt_output_id(receipt: GenerationReceipt | None) -> str | None:
    if receipt is None or receipt.output is None:
        return None
    return receipt.output.output_id


def _public_generation_cost(receipt: GenerationReceipt | None, output_id: str | None) -> PublicGenerationCost:
    if receipt is None or receipt.provider_cost is None:
        return PublicGenerationCost(
            output_id=output_id,
            amount=None,
            currency=None,
            status="not_recorded",
        )
    cost = receipt.provider_cost
    return PublicGenerationCost(
        output_id=output_id,
        amount=cost.amount,
        currency=cost.currency,
        status=cost.status,
    )


def _same_recorded_currency(left: str | None, right: str | None) -> bool:
    if left is None and right is None:
        return True
    if left is None or right is None:
        return False
    return left.casefold() == right.casefold()


def _generation_cost_flags(record: JobRecord) -> dict[str, object]:
    stored = record.generation
    current_receipt = None if stored is None else stored.receipt
    current_id = _receipt_output_id(current_receipt)
    current_cost = None if stored is None else _public_generation_cost(current_receipt, current_id)

    history = [item for item in record.generation_history if item is not None]
    initial = history[0] if history else stored
    initial_receipt = None if initial is None else initial.receipt
    initial_cost = (
        None
        if initial is None
        else _public_generation_cost(initial_receipt, _receipt_output_id(initial_receipt))
    )
    repair_cost = current_cost if record.repair_count > 0 and history and current_cost is not None else None

    lineage = [*history]
    if stored is not None:
        lineage.append(stored)
    total: PublicGenerationCost | None = None
    if len(lineage) > 1:
        currency: str | None = None
        amount = 0.0
        complete = True
        for item in lineage:
            view = _public_generation_cost(
                None if item is None else item.receipt,
                _receipt_output_id(None if item is None else item.receipt),
            )
            if view.status != "known" or view.amount is None:
                complete = False
                break
            if currency is None:
                currency = view.currency
            elif not _same_recorded_currency(currency, view.currency):
                complete = False
                break
            amount += view.amount
        if complete:
            total = PublicGenerationCost(
                output_id=None,
                amount=amount,
                currency=currency,
                status="known",
            )

    return {
        "generation_output_id": current_id,
        "generation_cost": current_cost,
        "initial_generation_cost": initial_cost if history else None,
        "repair_generation_cost": repair_cost,
        "generation_cost_total": total,
    }


def _repair_status_flags(record: JobRecord) -> dict[str, object]:
    assessment = record.critique.result if record.critique is not None else None
    return {
        "repair_eligible": repair_is_eligible(record),
        "critique_overall_result": assessment.overall_result if assessment is not None else None,
        "critique_matches_generation": critique_matches_generation(record),
        "generation_output_available": generation_output_available(record),
        "repair_count": record.repair_count,
        "repair_limit": record.repair_limit if record.repair_limit else REPAIR_LIMIT,
        **_generation_cost_flags(record),
    }


def job_status_view(record: JobRecord) -> JobStatusView:
    ready = record.readiness is not None and record.readiness.status == "ready"
    flags = _repair_status_flags(record)
    return JobStatusView(
        job_id=record.job_id,
        owner_id=record.owner_id,
        revision=record.revision,
        stage=record.stage,
        state=record.state,
        ready=ready,
        eye_available=record.observation is not None,
        brain_available=_brain_view(record) is not None,
        stylist_available=_stylist_view(record) is not None,
        compile_available=_engine_view(record) is not None,
        generation_available=_generation_view(record) is not None
        and record.generation is not None
        and record.generation.receipt is not None,
        critique_available=_critique_view(record) is not None,
        repair_available=_repair_view(record) is not None,
        **flags,
        hold=record.hold,
        error=record.error,
        review_status=record.review_status,
        package_status=record.review_status,
        complete=record.complete,
        releasable=record.releasable,
        approved=record.approval is not None and record.review_status in {
            "owner_approved",
            "released",
        },
    )

