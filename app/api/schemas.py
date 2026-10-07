"""Public JSON DTOs for the versioned jobs API."""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.contracts.brain import BrainPlan
from app.contracts.critique import CritiqueAssessment
from app.contracts.engine import EngineCompile
from app.contracts.eye import EyeObservation
from app.contracts.generation import GenerationOperation, GenerationReceipt
from app.contracts.job import Phase0JobContract
from app.contracts.reference import ReferenceAsset
from app.contracts.repair import RepairPlan
from app.contracts.stylist import StylistPlan
from app.runtime.state import JobError, JobRecord, JobStage, JobState
from app.stages.eye import Readiness


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
    """Phase-0 contract as submitted on POST /jobs. Same canonical fields."""

    references: list[IntakeReferenceAsset] = Field(min_length=1)


class CreateJobRequest(BaseModel):
    """Create a job from a Phase-0 contract. Eye is not executed."""

    model_config = ConfigDict(extra="forbid")

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
    """Run Eye for an existing job. model_id is supplied by the caller."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, examples=["openai/gpt-4.1"])


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
    """Run Brain for an existing job. model_id is supplied by the caller."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, examples=["openai/gpt-4.1"])


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
    """Run Stylist for an existing job. model_id is supplied by the caller."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, examples=["openai/gpt-4.1"])


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
    """Run Engine compile for an existing job. model_id is supplied by the caller."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, examples=["caller-supplied-model"])


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


class ExecuteGenerateRequest(BaseModel):
    """Dispatch generation for a persisted EngineCompile. No model selection.

    Send an empty JSON object. The compiled model_id is already on the job.
    """

    model_config = ConfigDict(extra="forbid")


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
    """Run Critique · assess for a completed generation. model_id is supplied by the caller."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, examples=["openai/gpt-4.1"])


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
    """Run bounded Critique · repair. model_id is supplied by the caller."""

    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1, examples=["openai/gpt-4.1"])


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
    eye: JobEyeView | None
    brain: BrainView | None
    stylist: StylistView | None
    engine: EngineView | None
    generation: GenerationView | None
    critique: CritiqueView | None
    repair: RepairView | None


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
    hold: Readiness | None
    error: JobError | None


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
        eye=eye,
        brain=brain,
        stylist=stylist,
        engine=engine,
        generation=generation,
        critique=critique,
        repair=repair,
    )


def job_status_view(record: JobRecord) -> JobStatusView:
    ready = record.readiness is not None and record.readiness.status == "ready"
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
        hold=record.hold,
        error=record.error,
    )

