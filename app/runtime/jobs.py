"""Job create, Eye/Brain/Stylist/Engine execution, and retrieval against the job store."""

from __future__ import annotations

from uuid import uuid4

from pydantic import ValidationError

from app.contracts.generation import GenerationReceipt
from app.contracts.job import Phase0JobContract
from app.providers.brain import BrainInput, BrainProvider
from app.providers.engine import EngineCompiler, EngineInput
from app.providers.eye import EyeProvider
from app.providers.failure import provider_failure_details
from app.providers.critique import CritiqueProvider
from app.providers.generation import GenerationProvider
from app.providers.repair import RepairPlanner, RepairPlannerRequest
from app.providers.living_room_eye_observation import LivingRoomEyeMappingError
from app.providers.openrouter import OpenRouterEyeProvider
from app.providers.stylist import StylistInput, StylistProvider
from app.runtime.artifacts import output_filename, persist_job_record
from app.runtime.checksum import annotate_checksum
from app.runtime.events import job_event
from app.runtime.reference_metadata import measure_references
from app.runtime.job import execute_eye_job
from app.runtime.references import freeze_intake_payload, image_bytes_for_eye
from app.runtime.state import (
    BrainInputMetadata,
    EngineInputMetadata,
    JobError,
    JobRecord,
    JobStore,
    StoredBrain,
    StoredCritique,
    StoredEngine,
    StoredGeneration,
    StoredRepair,
    StoredStylist,
    StylistInputMetadata,
)
from app.stages.brain import brain_may_proceed, build_brain_input, execute_brain
from app.stages.compile import (
    build_engine_input,
    engine_may_proceed,
    execute_engine,
)
from app.stages.critique import (
    build_critique_input,
    critique_may_proceed,
    execute_critique,
    generated_image_bytes,
    original_reference_bytes,
)
from app.stages.operator import (
    build_generation_operation,
    execute_generation,
    existing_operation_blocks_dispatch,
    generation_may_proceed,
)
from app.contracts.review import OwnerApproval, PackageRelease
from app.stages.package import package_is_complete
from app.stages.repair import (
    FRESH_RENDER_UNSUPPORTED_REASON,
    LOCAL_EDIT_UNSUPPORTED_REASON,
    build_repair_generation_operation,
    build_repair_plan,
    local_edit_supported,
    repair_action_supported,
    repair_reference_bytes,
)
from app.stages.stylist import build_stylist_input, execute_stylist, stylist_may_proceed
from app.contracts.repair import REPAIR_LIMIT, RepairPlan


class JobNotFoundError(Exception):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(job_id)


class EyeNotRunError(Exception):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(job_id)


class EyeProviderFailedError(Exception):
    """Eye provider failed. The public message is stable; the cause is not exposed."""


class BrainNotRunError(Exception):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(job_id)


class BrainNotReadyError(Exception):
    def __init__(self, job_id: str, reasons: list[str]) -> None:
        self.job_id = job_id
        self.reasons = reasons
        super().__init__(job_id)


class BrainProviderFailedError(Exception):
    """Brain provider failed. Public message is stable; details are redacted."""

    def __init__(self, details: dict[str, object] | None = None) -> None:
        self.details = details or {}
        super().__init__("Brain provider failed")


class StylistNotRunError(Exception):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(job_id)


class StylistNotReadyError(Exception):
    def __init__(self, job_id: str, reasons: list[str]) -> None:
        self.job_id = job_id
        self.reasons = reasons
        super().__init__(job_id)


class StylistProviderFailedError(Exception):
    """Stylist provider failed. Public message is stable; details are redacted."""

    def __init__(self, details: dict[str, object] | None = None) -> None:
        self.details = details or {}
        super().__init__("Stylist provider failed")


class EngineNotRunError(Exception):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(job_id)


class EngineNotReadyError(Exception):
    def __init__(self, job_id: str, reasons: list[str]) -> None:
        self.job_id = job_id
        self.reasons = reasons
        super().__init__(job_id)


class EngineProviderFailedError(Exception):
    """Engine compiler failed. Public message is stable; details are redacted."""

    def __init__(self, details: dict[str, object] | None = None) -> None:
        self.details = details or {}
        super().__init__("Engine compiler failed")


class GenerationNotRunError(Exception):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(job_id)


class GenerationNotReadyError(Exception):
    def __init__(self, job_id: str, reasons: list[str]) -> None:
        self.job_id = job_id
        self.reasons = reasons
        super().__init__(job_id)


class GenerationProviderFailedError(Exception):
    """Generation adapter failed. Public message is stable; details are redacted."""

    def __init__(self, details: dict[str, object] | None = None) -> None:
        self.details = details or {}
        super().__init__("Generation provider failed")


class CritiqueNotRunError(Exception):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(job_id)


class CritiqueProviderFailedError(Exception):
    """Critique adapter failed. Public message is stable; details are redacted."""

    def __init__(self, details: dict[str, object] | None = None) -> None:
        self.details = details or {}
        super().__init__("Critique provider failed")


class RepairNotRunError(Exception):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__(job_id)


class RepairNotRequiredError(Exception):
    def __init__(self, job_id: str, overall_result: str) -> None:
        self.job_id = job_id
        self.overall_result = overall_result
        super().__init__(job_id)


class RepairNotReadyError(Exception):
    def __init__(self, job_id: str, reasons: list[str]) -> None:
        self.job_id = job_id
        self.reasons = reasons
        super().__init__(job_id)


class ReviewNotReadyError(Exception):
    def __init__(self, job_id: str, reasons: list[str]) -> None:
        self.job_id = job_id
        self.reasons = reasons
        super().__init__(job_id)


class ReleaseNotReadyError(Exception):
    def __init__(self, job_id: str, reasons: list[str]) -> None:
        self.job_id = job_id
        self.reasons = reasons
        super().__init__(job_id)


class ModelMismatchError(Exception):
    """Requested model does not match the compiled image model."""

    def __init__(
        self,
        job_id: str,
        stage: str,
        requested_model: str,
        compiled_model: str,
    ) -> None:
        self.job_id = job_id
        self.stage = stage
        self.requested_model = requested_model
        self.compiled_model = compiled_model
        super().__init__(
            f"Requested {stage} model '{requested_model}' must match compiled image model '{compiled_model}'"
        )


class RepairProviderFailedError(Exception):
    """Repair generation adapter failed. Public message is stable; details are redacted."""

    def __init__(self, details: dict[str, object] | None = None) -> None:
        self.details = details or {}
        super().__init__("Repair provider failed")


class JobOwnerMismatchError(Exception):
    def __init__(self, job_id: str, owner_id: str) -> None:
        self.job_id = job_id
        self.owner_id = owner_id
        super().__init__(job_id)


class RevisionMismatchError(Exception):
    def __init__(self, job_id: str, expected: int, actual: int) -> None:
        self.job_id = job_id
        self.expected = expected
        self.actual = actual
        super().__init__(job_id)



def create_job(
    store: JobStore,
    contract: Phase0JobContract,
    reference_bytes: dict[str, bytes] | None = None,
) -> JobRecord:
    """Freeze the accepted Phase-0 contract. Eye is not run here."""

    stored_bytes = dict(reference_bytes or {})
    record = JobRecord(
        job_id=str(uuid4()),
        owner_id=contract.owner_id,
        contract=contract,
        revision=contract.revision,
        stage="intake",
        state="accepted",
        status="accepted",
        hold=None,
        error=None,
        eye_model_id=None,
        eye_input=None,
        observation=None,
        readiness=None,
        brain=None,
        events=[
            job_event(
                kind="job_created",
                stage="intake",
                state="accepted",
                contract_id=contract.contract_id,
                revision=contract.revision,
            )
        ],
        reference_bytes=stored_bytes,
        reference_measurements=measure_references(contract, stored_bytes, observation=None),
    )
    _commit(store, record, write_inputs=True)
    return record


def _commit(
    store: JobStore,
    record: JobRecord,
    *,
    stage: str | None = None,
    write_inputs: bool = False,
    output: tuple[str, bytes] | None = None,
) -> None:
    store.save(record)
    persist_job_record(
        record,
        stage=stage,
        write_inputs=write_inputs,
        output=output,
    )


def create_job_from_intake(
    store: JobStore, payload: dict[str, object]
) -> JobRecord:
    contract, reference_bytes = freeze_intake_payload(payload)
    return create_job(store, contract, reference_bytes)


def get_job(
    store: JobStore,
    job_id: str,
    *,
    owner_id: str | None = None,
    revision: int | None = None,
) -> JobRecord:
    record = store.get(job_id)
    if record is None:
        raise JobNotFoundError(job_id)
    if owner_id is not None and owner_id != record.owner_id:
        raise JobOwnerMismatchError(job_id, owner_id)
    if revision is not None and revision != record.revision:
        raise RevisionMismatchError(job_id, revision, record.revision)
    return record


def get_job_eye(
    store: JobStore,
    job_id: str,
    *,
    owner_id: str | None = None,
    revision: int | None = None,
) -> JobRecord:
    record = get_job(store, job_id, owner_id=owner_id, revision=revision)
    if record.observation is None or record.readiness is None:
        raise EyeNotRunError(job_id)
    return record


def get_job_brain(
    store: JobStore,
    job_id: str,
    *,
    owner_id: str | None = None,
    revision: int | None = None,
) -> JobRecord:
    record = get_job(store, job_id, owner_id=owner_id, revision=revision)
    if record.observation is None or record.readiness is None:
        raise EyeNotRunError(job_id)
    if record.brain is None or record.brain.result is None:
        raise BrainNotRunError(job_id)
    return record


def load_brain_input(
    store: JobStore,
    job_id: str,
    *,
    owner_id: str | None = None,
    revision: int | None = None,
) -> BrainInput:
    """Load persisted Job Contract + EyeObservation for a later Brain call.

    This does not execute Brain and does not call a provider.
    """

    record = get_job_eye(store, job_id, owner_id=owner_id, revision=revision)
    observation = record.observation
    assert observation is not None
    if (
        observation.contract_id != record.contract.contract_id
        or observation.revision != record.revision
    ):
        raise RevisionMismatchError(job_id, record.revision, observation.revision)
    return build_brain_input(record)


def get_job_stylist(
    store: JobStore,
    job_id: str,
    *,
    owner_id: str | None = None,
    revision: int | None = None,
) -> JobRecord:
    record = get_job(store, job_id, owner_id=owner_id, revision=revision)
    if record.observation is None or record.readiness is None:
        raise EyeNotRunError(job_id)
    if record.brain is None or record.brain.result is None:
        raise BrainNotRunError(job_id)
    if record.stylist is None or record.stylist.result is None:
        raise StylistNotRunError(job_id)
    return record


def load_stylist_input(
    store: JobStore,
    job_id: str,
    *,
    owner_id: str | None = None,
    revision: int | None = None,
) -> StylistInput:
    """Load persisted Job Contract + EyeObservation + BrainPlan for a later Stylist call.

    This does not execute Stylist and does not call a provider.
    """

    record = get_job_brain(store, job_id, owner_id=owner_id, revision=revision)
    brain = record.brain
    assert brain is not None and brain.result is not None
    if (
        brain.result.contract_id != record.contract.contract_id
        or brain.result.contract_revision != record.revision
    ):
        raise RevisionMismatchError(
            job_id, record.revision, brain.result.contract_revision
        )
    return build_stylist_input(record)


def get_job_compile(
    store: JobStore,
    job_id: str,
    *,
    owner_id: str | None = None,
    revision: int | None = None,
) -> JobRecord:
    record = get_job(store, job_id, owner_id=owner_id, revision=revision)
    if record.observation is None or record.readiness is None:
        raise EyeNotRunError(job_id)
    if record.brain is None or record.brain.result is None:
        raise BrainNotRunError(job_id)
    if record.stylist is None or record.stylist.result is None:
        raise StylistNotRunError(job_id)
    if record.engine is None or record.engine.result is None:
        raise EngineNotRunError(job_id)
    return record


def get_job_generation(
    store: JobStore,
    job_id: str,
    *,
    owner_id: str | None = None,
    revision: int | None = None,
) -> JobRecord:
    record = get_job_compile(store, job_id, owner_id=owner_id, revision=revision)
    if record.generation is None or record.generation.receipt is None:
        raise GenerationNotRunError(job_id)
    return record


def get_job_critique(
    store: JobStore,
    job_id: str,
    *,
    owner_id: str | None = None,
    revision: int | None = None,
) -> JobRecord:
    record = get_job_generation(store, job_id, owner_id=owner_id, revision=revision)
    if record.critique is None or record.critique.result is None:
        raise CritiqueNotRunError(job_id)
    return record


def get_job_repair(
    store: JobStore,
    job_id: str,
    *,
    owner_id: str | None = None,
    revision: int | None = None,
) -> JobRecord:
    record = get_job_critique(store, job_id, owner_id=owner_id, revision=revision)
    if record.repair is None:
        raise RepairNotRunError(job_id)
    return record


def load_engine_input(
    store: JobStore,
    job_id: str,
    *,
    owner_id: str | None = None,
    revision: int | None = None,
) -> EngineInput:
    """Load persisted Job Contract + Eye + Brain + Stylist for a later compile call.

    This does not execute Engine and does not call a provider.
    """

    record = get_job_stylist(store, job_id, owner_id=owner_id, revision=revision)
    stylist = record.stylist
    assert stylist is not None and stylist.result is not None
    if (
        stylist.result.contract_id != record.contract.contract_id
        or stylist.result.contract_revision != record.revision
    ):
        raise RevisionMismatchError(
            job_id, record.revision, stylist.result.contract_revision
        )
    return build_engine_input(record)


def execute_job_eye(
    store: JobStore,
    *,
    job_id: str,
    model_id: str,
    provider: EyeProvider,
    owner_id: str | None = None,
    revision: int | None = None,
) -> JobRecord:
    """Run Eye for an existing job using the caller-supplied model_id."""

    record = get_job(store, job_id, owner_id=owner_id, revision=revision)
    reference_ids = [item.reference_id for item in record.contract.references]
    bound = _bind_provider(provider, record)
    try:
        result = execute_eye_job(
            contract=record.contract,
            reference_ids=reference_ids,
            model_id=model_id,
            messages=[],
            provider=bound,
        )
    except LivingRoomEyeMappingError as exc:
        _commit(store, _eye_failed(record, model_id))
        raise EyeProviderFailedError from exc
    except (ValueError, ValidationError):
        raise
    except Exception as exc:
        _commit(store, _eye_failed(record, model_id))
        raise EyeProviderFailedError from exc

    if (
        result.observation.contract_id != record.contract.contract_id
        or result.observation.revision != record.revision
    ):
        raise ValueError("EyeObservation must bind the frozen job contract revision")

    hold = result.readiness if result.readiness.status == "hold" else None
    state = "hold" if hold is not None else "ready"
    updated = record.model_copy(
        update={
            "stage": "eye",
            "state": state,
            "status": state,
            "hold": hold,
            "error": None,
            "eye_model_id": model_id,
            "eye_input": result.eye_input,
            "observation": result.observation,
            "readiness": result.readiness,
            "events": list(record.events)
            + [
                job_event(
                    kind="eye_persisted",
                    stage="eye",
                    state=state,
                    contract_id=record.contract.contract_id,
                    revision=record.revision,
                )
            ],
        }
    )
    updated = updated.model_copy(
        update={
            "reference_measurements": measure_references(
                updated.contract,
                updated.reference_bytes,
                observation=updated.observation,
            )
        }
    )
    _commit(store, updated, stage="eye")
    return updated


def execute_job_brain(
    store: JobStore,
    *,
    job_id: str,
    model_id: str,
    provider: BrainProvider,
    owner_id: str | None = None,
    revision: int | None = None,
) -> JobRecord:
    """Run Brain for an existing job using persisted Job State."""

    record = get_job(store, job_id, owner_id=owner_id, revision=revision)
    if record.observation is None or record.readiness is None:
        raise EyeNotRunError(job_id)
    if not brain_may_proceed(record.readiness):
        raise BrainNotReadyError(job_id, list(record.readiness.reasons))

    brain_input = load_brain_input(
        store, job_id, owner_id=owner_id, revision=revision
    )
    try:
        result = execute_brain(
            brain_input=brain_input,
            model_id=model_id,
            provider=provider,
        )
    except (ValueError, ValidationError) as exc:
        if isinstance(exc, ValueError) and str(exc) == "model_id must be supplied by the caller":
            raise
        _commit(store, _brain_failed(record, model_id))
        raise BrainProviderFailedError(
            provider_failure_details(exc, provider)
        ) from exc
    except Exception as exc:
        _commit(store, _brain_failed(record, model_id))
        raise BrainProviderFailedError(
            provider_failure_details(exc, provider)
        ) from exc

    current = get_job(store, job_id)
    if current.revision != result.plan.contract_revision:
        raise RevisionMismatchError(
            job_id, result.plan.contract_revision, current.revision
        )

    state = "hold" if result.plan.status == "hold" else "ready"
    hold = current.hold if state == "hold" else None
    updated = current.model_copy(
        update={
            "stage": "brain",
            "state": state,
            "status": state,
            "hold": hold,
            "error": None,
            "brain": StoredBrain(
                model_id=result.model_id,
                input=BrainInputMetadata(
                    job_id=brain_input.job_id,
                    contract_id=brain_input.contract.contract_id,
                    revision=brain_input.contract.revision,
                    observation_contract_id=brain_input.observation.contract_id,
                    observation_revision=brain_input.observation.revision,
                    evidence=list(brain_input.evidence),
                ),
                result=result.plan,
                status="completed",
            ),
            "events": list(current.events)
            + [
                job_event(
                    kind="brain_completed",
                    stage="brain",
                    state=state,
                    contract_id=current.contract.contract_id,
                    revision=current.revision,
                )
            ],
        }
    )
    _commit(store, updated, stage="brain")
    return updated


def _brain_failed(record: JobRecord, model_id: str) -> JobRecord:
    return record.model_copy(
        update={
            "stage": "brain",
            "state": "failed",
            "status": "failed",
            "error": JobError(
                code="PROVIDER_FAILURE",
                message="Brain provider failed",
            ),
            "brain": StoredBrain(
                model_id=model_id,
                input=None,
                result=None,
                status="failed",
            ),
            "events": list(record.events)
            + [
                job_event(
                    kind="brain_failed",
                    stage="brain",
                    state="failed",
                    contract_id=record.contract.contract_id,
                    revision=record.revision,
                )
            ],
        }
    )


def execute_job_stylist(
    store: JobStore,
    *,
    job_id: str,
    model_id: str,
    provider: StylistProvider,
    owner_id: str | None = None,
    revision: int | None = None,
) -> JobRecord:
    """Run Stylist for an existing job using persisted Job State."""

    record = get_job(store, job_id, owner_id=owner_id, revision=revision)
    if record.observation is None or record.readiness is None:
        raise EyeNotRunError(job_id)
    if record.brain is None or record.brain.result is None:
        raise BrainNotRunError(job_id)
    if not stylist_may_proceed(record.brain.result):
        raise StylistNotReadyError(job_id, list(record.brain.result.decision_reasons))

    stylist_input = load_stylist_input(
        store, job_id, owner_id=owner_id, revision=revision
    )
    try:
        result = execute_stylist(
            stylist_input=stylist_input,
            model_id=model_id,
            provider=provider,
        )
    except (ValueError, ValidationError) as exc:
        if isinstance(exc, ValueError) and str(exc) == "model_id must be supplied by the caller":
            raise
        _commit(store, _stylist_failed(record, model_id))
        raise StylistProviderFailedError(
            provider_failure_details(exc, provider)
        ) from exc
    except Exception as exc:
        _commit(store, _stylist_failed(record, model_id))
        raise StylistProviderFailedError(
            provider_failure_details(exc, provider)
        ) from exc

    current = get_job(store, job_id)
    if current.revision != result.plan.contract_revision:
        raise RevisionMismatchError(
            job_id, result.plan.contract_revision, current.revision
        )

    state = "hold" if result.plan.status == "hold" else "ready"
    hold = current.hold if state == "hold" else None
    updated = current.model_copy(
        update={
            "stage": "stylist",
            "state": state,
            "status": state,
            "hold": hold,
            "error": None,
            "stylist": StoredStylist(
                model_id=result.model_id,
                input=StylistInputMetadata(
                    job_id=stylist_input.job_id,
                    contract_id=stylist_input.contract.contract_id,
                    revision=stylist_input.contract.revision,
                    brain_contract_id=stylist_input.brain_plan.contract_id,
                    brain_revision=stylist_input.brain_plan.contract_revision,
                    evidence=list(stylist_input.evidence),
                ),
                result=result.plan,
                status="completed",
            ),
            "events": list(current.events)
            + [
                job_event(
                    kind="stylist_completed",
                    stage="stylist",
                    state=state,
                    contract_id=current.contract.contract_id,
                    revision=current.revision,
                )
            ],
        }
    )
    _commit(store, updated, stage="stylist")
    return updated


def _stylist_failed(record: JobRecord, model_id: str) -> JobRecord:
    return record.model_copy(
        update={
            "stage": "stylist",
            "state": "failed",
            "status": "failed",
            "error": JobError(
                code="PROVIDER_FAILURE",
                message="Stylist provider failed",
            ),
            "stylist": StoredStylist(
                model_id=model_id,
                input=None,
                result=None,
                status="failed",
            ),
            "events": list(record.events)
            + [
                job_event(
                    kind="stylist_failed",
                    stage="stylist",
                    state="failed",
                    contract_id=record.contract.contract_id,
                    revision=record.revision,
                )
            ],
        }
    )


def execute_job_compile(
    store: JobStore,
    *,
    job_id: str,
    model_id: str,
    compiler: EngineCompiler,
    owner_id: str | None = None,
    revision: int | None = None,
) -> JobRecord:
    """Run Engine compile for an existing job using persisted Job State."""

    record = get_job(store, job_id, owner_id=owner_id, revision=revision)
    if record.observation is None or record.readiness is None:
        raise EyeNotRunError(job_id)
    if record.brain is None or record.brain.result is None:
        raise BrainNotRunError(job_id)
    if record.stylist is None or record.stylist.result is None:
        raise StylistNotRunError(job_id)

    brain_plan = record.brain.result
    stylist_plan = record.stylist.result
    if not engine_may_proceed(brain_plan, stylist_plan):
        reasons: list[str] = []
        if brain_plan.status == "hold":
            reasons.extend(brain_plan.decision_reasons or ["Brain plan is held"])
        if stylist_plan.status == "hold":
            reasons.extend(stylist_plan.hold_reasons or ["Stylist plan is held"])
        raise EngineNotReadyError(job_id, reasons)

    engine_input = load_engine_input(
        store, job_id, owner_id=owner_id, revision=revision
    )
    try:
        result = execute_engine(
            engine_input=engine_input,
            model_id=model_id,
            compiler=compiler,
        )
    except (ValueError, ValidationError) as exc:
        if isinstance(exc, ValueError) and str(exc) == "model_id must be supplied by the caller":
            raise
        _commit(store, _engine_failed(record, model_id))
        raise EngineProviderFailedError(
            provider_failure_details(exc, compiler)
        ) from exc
    except Exception as exc:
        _commit(store, _engine_failed(record, model_id))
        raise EngineProviderFailedError(
            provider_failure_details(exc, compiler)
        ) from exc

    current = get_job(store, job_id)
    if current.revision != result.compile.contract_revision:
        raise RevisionMismatchError(
            job_id, result.compile.contract_revision, current.revision
        )

    state = "hold" if result.compile.status == "hold" else "ready"
    hold = current.hold if state == "hold" else None
    updated = current.model_copy(
        update={
            "stage": "compile",
            "state": state,
            "status": state,
            "hold": hold,
            "error": None,
            "engine": StoredEngine(
                model_id=result.model_id,
                input=EngineInputMetadata(
                    job_id=engine_input.job_id,
                    contract_id=engine_input.contract.contract_id,
                    revision=engine_input.contract.revision,
                    brain_contract_id=engine_input.brain_plan.contract_id,
                    brain_revision=engine_input.brain_plan.contract_revision,
                    stylist_contract_id=engine_input.stylist_plan.contract_id,
                    stylist_revision=engine_input.stylist_plan.contract_revision,
                    evidence=list(engine_input.evidence),
                ),
                result=result.compile,
                status="completed",
            ),
            "events": list(current.events)
            + [
                job_event(
                    kind="compile_completed",
                    stage="compile",
                    state=state,
                    contract_id=current.contract.contract_id,
                    revision=current.revision,
                )
            ],
        }
    )
    _commit(store, updated, stage="compile")
    return updated


def execute_job_generate(
    store: JobStore,
    *,
    job_id: str,
    provider: GenerationProvider,
    model_id: str | None = None,
    owner_id: str | None = None,
    revision: int | None = None,
) -> JobRecord:
    """Claim and dispatch generation for a persisted EngineCompile."""

    record = get_job(store, job_id, owner_id=owner_id, revision=revision)
    if record.observation is None or record.readiness is None:
        raise EyeNotRunError(job_id)
    if record.brain is None or record.brain.result is None:
        raise BrainNotRunError(job_id)
    if record.stylist is None or record.stylist.result is None:
        raise StylistNotRunError(job_id)
    if record.engine is None or record.engine.result is None:
        raise EngineNotRunError(job_id)

    compile_artifact = record.engine.result
    if model_id is not None and model_id != compile_artifact.model_id:
        raise ModelMismatchError(
            job_id=job_id,
            stage="generate",
            requested_model=model_id,
            compiled_model=compile_artifact.model_id,
        )
    if not generation_may_proceed(compile_artifact):
        raise GenerationNotReadyError(
            job_id,
            list(compile_artifact.hold_reasons) or ["Engine compile is held"],
        )

    operation = build_generation_operation(record)
    stored = record.generation
    if stored is not None and stored.operation.operation_key == operation.operation_key:
        if stored.receipt is None or existing_operation_blocks_dispatch(stored.receipt):
            return record

    claimed = record.model_copy(
        update={
            "stage": "generate",
            "state": record.state,
            "status": record.status,
            "error": None,
            "generation": StoredGeneration(
                operation=operation,
                receipt=None,
                status="claimed",
            ),
            "events": list(record.events)
            + [
                job_event(
                    kind="generate_claimed",
                    stage="generate",
                    state=record.state,
                    contract_id=record.contract.contract_id,
                    revision=record.revision,
                )
            ],
        }
    )
    _commit(store, claimed, stage="generate")

    try:
        result = execute_generation(
            operation=operation,
            compile_artifact=compile_artifact,
            reference_bytes=claimed.reference_bytes,
            provider=provider,
        )
    except (ValueError, ValidationError) as exc:
        _commit(store, _generation_failed(claimed, operation), stage="generate")
        raise GenerationProviderFailedError(
            provider_failure_details(exc, provider)
        ) from exc
    except Exception as exc:
        _commit(store, _generation_failed(claimed, operation), stage="generate")
        raise GenerationProviderFailedError(
            provider_failure_details(exc, provider)
        ) from exc

    current = get_job(store, job_id)
    if current.revision != operation.contract_revision:
        raise RevisionMismatchError(
            job_id, operation.contract_revision, current.revision
        )

    receipt = result.receipt
    state = "hold" if receipt.status == "hold" else (
        "failed" if receipt.status == "failed" else (
            "ready" if receipt.status == "completed" else "hold"
        )
    )
    if receipt.status == "uncertain" or receipt.format_check == "failed":
        state = "hold"
    if receipt.status == "completed" and receipt.format_check != "passed":
        state = "hold"
    review_status = "hold" if state == "hold" else (
        "generation_completed" if receipt.status == "completed" else None
    )
    hold = current.hold if state == "hold" else None
    output_bytes = dict(current.reference_bytes)
    if receipt.output is not None and result.output_bytes is not None:
        output_bytes[receipt.output.output_id] = result.output_bytes

    event_kind = "generate_completed"
    if receipt.status == "failed":
        event_kind = "generate_failed"
    updated = current.model_copy(
        update={
            "stage": "generate",
            "state": state,
            "status": state,
            "hold": hold,
            "error": None,
            "review_status": review_status,
            "complete": False,
            "releasable": False,
            "approval": None,
            "release": None,
            "generation": annotate_checksum(
                StoredGeneration(
                    operation=operation,
                    receipt=receipt,
                    status=receipt.status,
                ),
                result.output_bytes,
            ),
            "reference_bytes": output_bytes,
            "events": list(current.events)
            + [
                job_event(
                    kind=event_kind,
                    stage="generate",
                    state=state,
                    contract_id=current.contract.contract_id,
                    revision=current.revision,
                )
            ],
        }
    )
    generated_file: tuple[str, bytes] | None = None
    if receipt.output is not None and result.output_bytes is not None:
        generated_file = (
            output_filename(receipt.output.media_type),
            result.output_bytes,
        )
    _commit(store, updated, stage="generate", output=generated_file)
    return updated


def execute_job_critique(
    store: JobStore,
    *,
    job_id: str,
    model_id: str,
    provider: CritiqueProvider,
    owner_id: str | None = None,
    revision: int | None = None,
) -> JobRecord:
    """Run Critique · assess for a completed generation."""

    record = get_job(store, job_id, owner_id=owner_id, revision=revision)
    if record.critique is not None and record.critique.result is not None:
        current_output = None
        if (
            record.generation is not None
            and record.generation.receipt is not None
            and record.generation.receipt.output is not None
        ):
            current_output = record.generation.receipt.output.output_id
        if record.critique.result.generation_output_id == current_output:
            return record
    if record.observation is None or record.readiness is None:
        raise EyeNotRunError(job_id)
    if record.brain is None or record.brain.result is None:
        raise BrainNotRunError(job_id)
    if not brain_may_proceed(record.readiness):
        raise BrainNotReadyError(job_id, list(record.readiness.reasons))
    if record.stylist is None or record.stylist.result is None:
        raise StylistNotRunError(job_id)
    if not stylist_may_proceed(record.brain.result):
        raise StylistNotReadyError(job_id, list(record.brain.result.decision_reasons))
    if record.engine is None or record.engine.result is None:
        raise EngineNotRunError(job_id)
    if not critique_may_proceed(record.engine.result):
        raise EngineNotReadyError(
            job_id,
            list(record.engine.result.hold_reasons) or ["Engine compile is held"],
        )
    if record.generation is None or record.generation.receipt is None:
        raise GenerationNotRunError(job_id)
    receipt = record.generation.receipt
    if receipt.status != "completed" or receipt.output is None:
        raise GenerationNotReadyError(
            job_id,
            ["Generation is not completed"] if receipt.status != "completed" else [
                "Generated image is not available"
            ],
        )

    generated = generated_image_bytes(record)
    original = original_reference_bytes(record)
    if generated is None:
        raise GenerationNotReadyError(job_id, ["Generated image is not available"])
    if original is None:
        raise GenerationNotReadyError(job_id, ["Original reference image is not available"])
    _original_id, original_bytes, original_media = original

    critique_input = build_critique_input(record)
    try:
        result = execute_critique(
            critique_input=critique_input,
            model_id=model_id,
            original_bytes=original_bytes,
            original_media_type=original_media,
            generated_bytes=generated,
            generated_media_type=receipt.output.media_type,
            provider=provider,
        )
    except (ValueError, ValidationError) as exc:
        if isinstance(exc, ValueError) and str(exc) == "model_id must be supplied by the caller":
            raise
        _commit(store, _critique_failed(record, model_id), stage="critique")
        raise CritiqueProviderFailedError(
            provider_failure_details(exc, provider)
        ) from exc
    except Exception as exc:
        _commit(store, _critique_failed(record, model_id), stage="critique")
        raise CritiqueProviderFailedError(
            provider_failure_details(exc, provider)
        ) from exc

    current = get_job(store, job_id)
    if current.revision != result.assessment.contract_revision:
        raise RevisionMismatchError(
            job_id, result.assessment.contract_revision, current.revision
        )

    if result.assessment.status == "hold" or result.assessment.overall_result == "hold":
        state = "hold"
        review_status = "hold"
    elif result.assessment.overall_result == "pass":
        state = "review_pending"
        review_status = "review_pending"
    else:
        state = "ready"
        review_status = "generation_completed"
    hold = current.hold if state == "hold" else None
    critique_history = list(current.critique_history)
    if (
        current.critique is not None
        and current.critique.result is not None
        and current.critique.result.generation_output_id
        != result.assessment.generation_output_id
    ):
        critique_history.append(current.critique)
    updated = current.model_copy(
        update={
            "stage": "critique",
            "state": state,
            "status": state,
            "hold": hold,
            "error": None,
            "review_status": review_status,
            "complete": False,
            "releasable": False,
            "approval": None,
            "release": None,
            "critique": StoredCritique(
                model_id=result.model_id,
                result=result.assessment,
                status="completed",
            ),
            "critique_history": critique_history,
            "events": list(current.events)
            + [
                job_event(
                    kind="critique_completed",
                    stage="critique",
                    state=state,
                    contract_id=current.contract.contract_id,
                    revision=current.revision,
                )
            ],
        }
    )
    _commit(store, updated, stage="critique")
    return updated


def execute_job_repair(
    store: JobStore,
    *,
    job_id: str,
    planner: RepairPlanner,
    provider: GenerationProvider,
    model_id: str | None = None,
    owner_id: str | None = None,
    revision: int | None = None,
) -> JobRecord:
    """Plan and execute one bounded repair. Never creates Repair #3.

    Image generation uses EngineCompile.model_id. The planner is deterministic.
    """

    record = get_job(store, job_id, owner_id=owner_id, revision=revision)
    if record.observation is None or record.readiness is None:
        raise EyeNotRunError(job_id)
    if record.brain is None or record.brain.result is None:
        raise BrainNotRunError(job_id)
    if record.stylist is None or record.stylist.result is None:
        raise StylistNotRunError(job_id)
    if record.engine is None or record.engine.result is None:
        raise EngineNotRunError(job_id)
    image_model_id = record.engine.result.model_id
    if model_id is not None and model_id != image_model_id:
        raise ModelMismatchError(
            job_id=job_id,
            stage="repair",
            requested_model=model_id,
            compiled_model=image_model_id,
        )
    if record.generation is None or record.generation.receipt is None:
        raise GenerationNotRunError(job_id)
    if record.critique is None or record.critique.result is None:
        raise CritiqueNotRunError(job_id)

    assessment = record.critique.result
    if assessment.overall_result == "pass":
        raise RepairNotRequiredError(job_id, assessment.overall_result)
    if assessment.overall_result == "hold" or assessment.status == "hold":
        raise RepairNotReadyError(job_id, ["Critique is on hold"])
    if assessment.overall_result != "repair_required":
        raise RepairNotRequiredError(job_id, assessment.overall_result)

    receipt = record.generation.receipt
    if receipt.status != "completed" or receipt.output is None:
        raise GenerationNotReadyError(job_id, ["Generation is not completed"])
    current_output = receipt.output.output_id

    latest = record.repair
    if (
        latest is not None
        and latest.plan.critique_generation_output_id == assessment.generation_output_id
    ):
        if latest.plan.receipt is None or existing_operation_blocks_dispatch(
            latest.plan.receipt
        ):
            return record
        if latest.plan.action == "hold":
            return record

    if assessment.generation_output_id != current_output:
        raise CritiqueNotRunError(job_id)

    generated = generated_image_bytes(record)
    original = original_reference_bytes(record)
    if generated is None:
        raise GenerationNotReadyError(job_id, ["Generated image is not available"])
    if original is None:
        raise GenerationNotReadyError(job_id, ["Original reference image is not available"])
    original_id, original_bytes, original_media = original

    if record.repair_count >= REPAIR_LIMIT:
        hold_request = _repair_planner_request(
            record,
            model_id=image_model_id,
            original_id=original_id,
            original_bytes=original_bytes,
            original_media=original_media,
            generated=generated,
            generated_media=receipt.output.media_type,
        )
        hold_plan = build_repair_plan(
            hold_request,
            action="hold",
            hold_reasons=["repair budget exhausted after two attempts"],
            status="hold",
        )
        return _persist_repair(store, record, hold_plan, increment=False, event_kind="repair_held")

    planner_request = _repair_planner_request(
        record,
        model_id=image_model_id,
        original_id=original_id,
        original_bytes=original_bytes,
        original_media=original_media,
        generated=generated,
        generated_media=receipt.output.media_type,
    )
    try:
        plan = planner.plan(planner_request)
    except (ValueError, ValidationError) as exc:
        raise RepairProviderFailedError(provider_failure_details(exc, planner)) from exc

    if plan.original_reference_id != original_id:
        raise RepairProviderFailedError(
            {"reason": "repair plan dropped the original identity reference"}
        )
    if original_id not in record.reference_bytes:
        raise RepairProviderFailedError(
            {"reason": "original identity reference bytes are missing"}
        )

    if plan.action != "hold" and not repair_action_supported(plan.action, provider):
        reason = (
            LOCAL_EDIT_UNSUPPORTED_REASON
            if plan.action == "local_edit"
            else FRESH_RENDER_UNSUPPORTED_REASON
        )
        plan = build_repair_plan(
            planner_request,
            action="hold",
            hold_reasons=[reason],
            status="hold",
        )
        return _persist_repair(store, record, plan, increment=False, event_kind="repair_held")

    if plan.action == "local_edit":
        scene_id = plan.scene_base_reference
        scene_bytes = record.reference_bytes.get(scene_id or "")
        if not scene_id or not scene_bytes or not local_edit_supported(provider):
            plan = build_repair_plan(
                planner_request,
                action="hold",
                hold_reasons=[LOCAL_EDIT_UNSUPPORTED_REASON],
                status="hold",
                preservation_status="unsupported",
                preservation_result=(
                    "local_edit could not use a scene base; scene preservation was not claimed"
                ),
            )
            return _persist_repair(
                store, record, plan, increment=False, event_kind="repair_held"
            )

    if plan.action == "hold":
        return _persist_repair(store, record, plan, increment=False, event_kind="repair_held")

    operation = build_repair_generation_operation(record, plan)
    if (
        latest is not None
        and latest.plan.operation is not None
        and latest.plan.operation.operation_key == operation.operation_key
    ):
        if latest.plan.receipt is None or existing_operation_blocks_dispatch(
            latest.plan.receipt
        ):
            return record

    claimed_plan = plan.model_copy(
        update={"status": "claimed", "operation": operation, "receipt": None}
    )
    claimed = _repair_record(
        record,
        claimed_plan,
        generation=record.generation,
        increment=False,
        event_kind="repair_claimed",
        state=record.state,
    )
    _commit(store, claimed, stage="repair")

    refs = repair_reference_bytes(claimed, claimed_plan)
    if original_id not in refs:
        raise RepairProviderFailedError(
            {"reason": "original identity reference is required on every repair"}
        )
    try:
        result = execute_generation(
            operation=operation,
            compile_artifact=claimed.engine.result,  # type: ignore[union-attr]
            reference_bytes=refs,
            provider=provider,
        )
    except (ValueError, ValidationError) as exc:
        failed = _repair_generation_failed(claimed, claimed_plan, operation)
        _commit(store, failed, stage="repair")
        raise RepairProviderFailedError(provider_failure_details(exc, provider)) from exc
    except Exception as exc:
        failed = _repair_generation_failed(claimed, claimed_plan, operation)
        _commit(store, failed, stage="repair")
        raise RepairProviderFailedError(provider_failure_details(exc, provider)) from exc

    current = get_job(store, job_id)
    repair_receipt = result.receipt
    output_bytes = dict(current.reference_bytes)
    if repair_receipt.output is not None and result.output_bytes is not None:
        output_bytes[repair_receipt.output.output_id] = result.output_bytes

    lineage = claimed_plan.lineage.model_copy(
        update={
            "version_to": claimed_plan.lineage.version_from + 1,
            "result_generation_output_id": repair_receipt.output.output_id
            if repair_receipt.output
            else None,
            "result_generation_operation_key": operation.operation_key
            if repair_receipt.status == "completed"
            else None,
        }
    )
    status = (
        "completed"
        if repair_receipt.status == "completed"
        else ("hold" if repair_receipt.status in {"hold", "uncertain"} else "failed")
    )
    preservation_status, preservation_result = _repair_preservation_result(
        claimed_plan,
        provider,
        status=status,
        format_check=repair_receipt.format_check,
    )
    completed_plan = claimed_plan.model_copy(
        update={
            "status": status,
            "operation": operation,
            "receipt": repair_receipt,
            "lineage": lineage,
            "hold_reasons": list(repair_receipt.hold_reasons)
            if repair_receipt.status == "hold"
            else claimed_plan.hold_reasons,
            "preservation_status": preservation_status,
            "preservation_result": preservation_result,
        }
    )
    history = list(current.generation_history)
    if current.generation is not None:
        history.append(current.generation)
    state = "hold" if status != "completed" else "ready"
    review_status = "hold" if state == "hold" else "generation_completed"
    event_kind = "repair_completed" if status == "completed" else (
        "repair_held" if status == "hold" else "repair_failed"
    )
    updated = current.model_copy(
        update={
            "stage": "repair",
            "state": state,
            "status": state,
            "error": None,
            "review_status": review_status,
            "complete": False,
            "releasable": False,
            "approval": None,
            "release": None,
            "generation": annotate_checksum(
                StoredGeneration(
                    operation=operation,
                    receipt=repair_receipt,
                    status=repair_receipt.status,
                ),
                result.output_bytes,
            ),
            "generation_history": history,
            "repair": StoredRepair(plan=completed_plan, status=status),
            "repairs": list(current.repairs[:-1])
            + [StoredRepair(plan=completed_plan, status=status)]
            if current.repairs
            else [StoredRepair(plan=completed_plan, status=status)],
            "repair_count": min(current.repair_count + 1, REPAIR_LIMIT)
            if status in {"completed", "claimed", "failed", "hold"}
            else current.repair_count,
            "reference_bytes": output_bytes,
            "events": list(current.events)
            + [
                job_event(
                    kind=event_kind,
                    stage="repair",
                    state=state,
                    contract_id=current.contract.contract_id,
                    revision=current.revision,
                )
            ],
        }
    )
    generated_file: tuple[str, bytes] | None = None
    if repair_receipt.output is not None and result.output_bytes is not None:
        generated_file = (
            output_filename(repair_receipt.output.media_type),
            result.output_bytes,
        )
    _commit(store, updated, stage="repair", output=generated_file)
    return updated


def _repair_preservation_result(
    plan: RepairPlan,
    provider: GenerationProvider,
    *,
    status: str,
    format_check: str,
):
    if status != "completed" or format_check == "failed":
        return (
            "failed",
            "repair did not complete with the requested pixel size; "
            "scene preservation was not claimed",
        )
    if plan.action == "local_edit" and local_edit_supported(provider):
        if plan.scene_base_reference and plan.product_authority_reference:
            protected = ", ".join(plan.protected_scene_attributes)
            return (
                "preserved",
                "local_edit used the previous generation as the scene base "
                f"({plan.scene_base_reference}) and the original reference as "
                f"product authority ({plan.product_authority_reference}); "
                f"protected scene attributes: {protected}",
            )
    if plan.action == "fresh_render":
        return (
            "not_claimed",
            "fresh_render does not preserve the previous scene; "
            f"product authority remains {plan.product_authority_reference}",
        )
    return (
        "unsupported",
        "the adapter did not perform a targeted local edit; scene preservation was not claimed",
    )


def approve_job(
    store: JobStore,
    *,
    job_id: str,
    owner_id: str | None = None,
    revision: int | None = None,
    approved_at: str | None = None,
) -> JobRecord:
    """Record explicit owner approval. Critique pass alone cannot call this."""

    record = get_job(store, job_id, owner_id=owner_id, revision=revision)
    if (
        record.approval is not None
        and record.review_status in {"owner_approved", "released"}
        and record.complete
    ):
        return record
    reasons = _approval_blockers(record)
    if reasons:
        raise ReviewNotReadyError(job_id, reasons)
    assert record.generation is not None
    assert record.generation.receipt is not None
    assert record.generation.receipt.output is not None
    assert record.contract.request_identity is not None
    approval = OwnerApproval(
        owner_id=record.owner_id,
        contract_id=record.contract.contract_id,
        revision=record.revision,
        request_hash=record.contract.request_identity.request_hash,
        generation_output_id=record.generation.receipt.output.output_id,
        approved_at=approved_at or _now_iso(),
    )
    updated = record.model_copy(
        update={
            "state": "approved",
            "status": "approved",
            "review_status": "owner_approved",
            "complete": True,
            "releasable": True,
            "approval": approval,
            "events": list(record.events)
            + [
                job_event(
                    kind="owner_approved",
                    stage="review",
                    state="approved",
                    contract_id=record.contract.contract_id,
                    revision=record.revision,
                )
            ],
        }
    )
    _commit(store, updated, stage="critique")
    return updated


def release_job(
    store: JobStore,
    *,
    job_id: str,
    owner_id: str | None = None,
    revision: int | None = None,
    released_at: str | None = None,
) -> JobRecord:
    """Release an explicitly approved candidate. Does not create approval."""

    record = get_job(store, job_id, owner_id=owner_id, revision=revision)
    if record.review_status == "released" and record.release is not None:
        return record
    if record.approval is None or record.review_status != "owner_approved":
        raise ReleaseNotReadyError(
            job_id, ["release requires an explicit owner approval"]
        )
    if not record.releasable or not package_is_complete(record):
        raise ReleaseNotReadyError(job_id, ["candidate is not releasable"])
    receipt = record.generation.receipt if record.generation else None
    if receipt is None or receipt.format_check != "passed" or receipt.output is None:
        raise ReleaseNotReadyError(job_id, ["format_check has not passed"])
    if receipt.output.output_id != record.approval.generation_output_id:
        raise ReleaseNotReadyError(
            job_id, ["approval does not match the current generation"]
        )
    release = PackageRelease(
        owner_id=record.owner_id,
        generation_output_id=receipt.output.output_id,
        released_at=released_at or _now_iso(),
    )
    updated = record.model_copy(
        update={
            "state": "released",
            "status": "released",
            "review_status": "released",
            "complete": True,
            "releasable": True,
            "release": release,
            "events": list(record.events)
            + [
                job_event(
                    kind="package_released",
                    stage="review",
                    state="released",
                    contract_id=record.contract.contract_id,
                    revision=record.revision,
                )
            ],
        }
    )
    _commit(store, updated, stage="critique")
    return updated


def _approval_blockers(record: JobRecord) -> list[str]:
    reasons: list[str] = []
    if record.critique is None or record.critique.result is None:
        reasons.append("critique has not passed")
    elif record.critique.result.overall_result != "pass":
        reasons.append("critique has not passed")
    if record.review_status == "hold" or record.state == "hold":
        reasons.append("job is on hold")
    receipt = record.generation.receipt if record.generation else None
    if receipt is None or receipt.status != "completed" or receipt.format_check != "passed":
        reasons.append("format_check has not passed")
    if receipt is None or receipt.output is None:
        reasons.append("generated image is not available")
    if record.contract.request_identity is None:
        reasons.append("request identity is missing")
    return reasons


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _repair_planner_request(
    record: JobRecord,
    *,
    model_id: str,
    original_id: str,
    original_bytes: bytes,
    original_media: str,
    generated: bytes,
    generated_media: str,
) -> RepairPlannerRequest:
    assert record.observation is not None
    assert record.stylist is not None and record.stylist.result is not None
    assert record.engine is not None and record.engine.result is not None
    assert record.generation is not None and record.generation.receipt is not None
    assert record.critique is not None and record.critique.result is not None
    receipt = record.generation.receipt
    assert receipt.output is not None
    return RepairPlannerRequest(
        job_id=record.job_id,
        contract_id=record.contract.contract_id,
        revision=record.revision,
        contract=record.contract,
        observation=record.observation,
        stylist_plan=record.stylist.result,
        compile=record.engine.result,
        operation=record.generation.operation,
        receipt=receipt,
        assessment=record.critique.result,
        original_reference_id=original_id,
        generated_output_id=receipt.output.output_id,
        original_bytes=original_bytes,
        original_media_type=original_media,
        generated_bytes=generated,
        generated_media_type=generated_media,
        previous_repairs=[item.plan for item in record.repairs],
        repair_count=record.repair_count,
        repair_limit=record.repair_limit,
        model_id=model_id,
        stage=record.stage,
        state=record.state,
    )


def _persist_repair(
    store: JobStore,
    record: JobRecord,
    plan: RepairPlan,
    *,
    increment: bool,
    event_kind: str,
) -> JobRecord:
    updated = _repair_record(
        record,
        plan,
        generation=record.generation,
        increment=increment,
        event_kind=event_kind,
        state="hold" if plan.action == "hold" or plan.status == "hold" else record.state,
    )
    _commit(store, updated, stage="repair")
    return updated


def _repair_record(
    record: JobRecord,
    plan: RepairPlan,
    *,
    generation: StoredGeneration | None,
    increment: bool,
    event_kind: str,
    state: str,
) -> JobRecord:
    stored = StoredRepair(plan=plan, status=plan.status)
    repairs = list(record.repairs)
    if repairs and repairs[-1].plan.critique_generation_output_id == plan.critique_generation_output_id:
        repairs[-1] = stored
    else:
        repairs.append(stored)
    count = record.repair_count
    if increment:
        count = min(record.repair_count + 1, REPAIR_LIMIT)
    return record.model_copy(
        update={
            "stage": "repair",
            "state": state,
            "status": state,
            "error": None,
            "review_status": "hold" if state == "hold" else record.review_status,
            "complete": False,
            "releasable": False,
            "approval": None,
            "release": None,
            "generation": generation,
            "repair": stored,
            "repairs": repairs,
            "repair_count": count,
            "events": list(record.events)
            + [
                job_event(
                    kind=event_kind,  # type: ignore[arg-type]
                    stage="repair",
                    state=state,
                    contract_id=record.contract.contract_id,
                    revision=record.revision,
                )
            ],
        }
    )


def _repair_generation_failed(
    record: JobRecord, plan: RepairPlan, operation
) -> JobRecord:
    receipt = GenerationReceipt(
        operation_key=operation.operation_key,
        status="failed",
        provider_name="unknown",
        provider_receipt_id=None,
        claimed_at=operation.claimed_at,
        submitted_at=None,
        completed_at=None,
        retry_classification="do_not_retry",
        output=None,
        capability_checks=[],
        hold_reasons=[],
    )
    failed_plan = plan.model_copy(
        update={"status": "failed", "operation": operation, "receipt": receipt}
    )
    return _repair_record(
        record,
        failed_plan,
        generation=StoredGeneration(operation=operation, receipt=receipt, status="failed"),
        increment=True,
        event_kind="repair_failed",
        state="failed",
    )


def _critique_failed(record: JobRecord, model_id: str) -> JobRecord:
    return record.model_copy(
        update={
            "stage": "critique",
            "state": "failed",
            "status": "failed",
            "error": JobError(
                code="PROVIDER_FAILURE",
                message="Critique provider failed",
            ),
            "critique": StoredCritique(
                model_id=model_id,
                result=None,
                status="failed",
            ),
            "events": list(record.events)
            + [
                job_event(
                    kind="critique_failed",
                    stage="critique",
                    state="failed",
                    contract_id=record.contract.contract_id,
                    revision=record.revision,
                )
            ],
        }
    )


def _generation_failed(record: JobRecord, operation) -> JobRecord:
    receipt = GenerationReceipt(
        operation_key=operation.operation_key,
        status="failed",
        provider_name="unknown",
        provider_receipt_id=None,
        claimed_at=operation.claimed_at,
        submitted_at=None,
        completed_at=None,
        retry_classification="do_not_retry",
        output=None,
        capability_checks=[],
        hold_reasons=[],
    )
    return record.model_copy(
        update={
            "stage": "generate",
            "state": "failed",
            "status": "failed",
            "error": JobError(
                code="PROVIDER_FAILURE",
                message="Generation provider failed",
            ),
            "generation": StoredGeneration(
                operation=operation,
                receipt=receipt,
                status="failed",
            ),
            "events": list(record.events)
            + [
                job_event(
                    kind="generate_failed",
                    stage="generate",
                    state="failed",
                    contract_id=record.contract.contract_id,
                    revision=record.revision,
                )
            ],
        }
    )


def _engine_failed(record: JobRecord, model_id: str) -> JobRecord:
    return record.model_copy(
        update={
            "stage": "compile",
            "state": "failed",
            "status": "failed",
            "error": JobError(
                code="PROVIDER_FAILURE",
                message="Engine compiler failed",
            ),
            "engine": StoredEngine(
                model_id=model_id,
                input=None,
                result=None,
                status="failed",
            ),
            "events": list(record.events)
            + [
                job_event(
                    kind="compile_failed",
                    stage="compile",
                    state="failed",
                    contract_id=record.contract.contract_id,
                    revision=record.revision,
                )
            ],
        }
    )


def _eye_failed(record: JobRecord, model_id: str) -> JobRecord:
    return record.model_copy(
        update={
            "stage": "eye",
            "state": "failed",
            "status": "failed",
            "hold": None,
            "error": JobError(
                code="PROVIDER_FAILURE",
                message="Eye provider failed",
            ),
            "eye_model_id": model_id,
            "events": list(record.events)
            + [
                job_event(
                    kind="eye_failed",
                    stage="eye",
                    state="failed",
                    contract_id=record.contract.contract_id,
                    revision=record.revision,
                )
            ],
        }
    )


def _bind_provider(provider: EyeProvider, record: JobRecord) -> EyeProvider:
    if not isinstance(provider, OpenRouterEyeProvider):
        return provider
    images = image_bytes_for_eye(record.contract.references, record.reference_bytes)
    if not images:
        raise ValueError(
            "Eye requires stored image bytes for at least one JPG, PNG, or WebP reference"
        )
    return OpenRouterEyeProvider(provider.settings, images)
