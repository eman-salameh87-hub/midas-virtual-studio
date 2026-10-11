"""Planning orchestrator: Eye → Brain → Stylist → Compile.

Does not generate images, critique, repair, approve, or release.

schedule_planning starts a process-local daemon thread. It is not a durable
queue. Startup recovery does not resume planning; an in-flight crash can
leave a job mid-stage without a second automatic provider call from this
module.
"""

from __future__ import annotations

import logging
import threading

from app.providers.brain import BrainProvider
from app.providers.engine import EngineCompiler
from app.providers.eye import EyeProvider
from app.providers.stylist import StylistProvider
from app.runtime.job_lock import locked_job
from app.runtime.jobs import (
    BrainNotReadyError,
    BrainProviderFailedError,
    EngineNotReadyError,
    EngineProviderFailedError,
    EyeProviderFailedError,
    StylistNotReadyError,
    StylistProviderFailedError,
    execute_job_brain,
    execute_job_compile,
    execute_job_eye,
    execute_job_stylist,
    get_job,
    planning_brain_is_complete,
    planning_compile_is_complete,
    planning_eye_is_complete,
    planning_stylist_is_complete,
)
from app.runtime.model_policy import (
    brain_model,
    eye_model,
    image_model,
    stylist_model,
    validate_stage_model,
)
from app.runtime.state import JobRecord, JobStore
from app.stages.brain import brain_may_proceed
from app.stages.compile import engine_may_proceed
from app.stages.stylist import stylist_may_proceed

logger = logging.getLogger("app.runtime.orchestrator")

_scheduled_guard = threading.Lock()
_scheduled_threads: dict[str, threading.Thread] = {}


def advance_planning(
    store: JobStore,
    *,
    job_id: str,
    eye_provider: EyeProvider,
    brain_provider: BrainProvider,
    stylist_provider: StylistProvider,
    compiler: EngineCompiler,
    owner_id: str | None = None,
    revision: int | None = None,
    eye_model_id: str | None = None,
    brain_model_id: str | None = None,
    stylist_model_id: str | None = None,
    compile_model_id: str | None = None,
) -> JobRecord:
    """Run planning stages until compile, HOLD, failure, or a missing prerequisite.

    Never calls Generate, Critique, Repair, approval, or Release.
    """

    eye_id = validate_stage_model("eye", eye_model_id or eye_model())
    brain_id = validate_stage_model("brain", brain_model_id or brain_model())
    stylist_id = validate_stage_model("stylist", stylist_model_id or stylist_model())
    compile_id = validate_stage_model("compile", compile_model_id or image_model())

    with locked_job(job_id):
        record = get_job(store, job_id, owner_id=owner_id, revision=revision)

        record = _run_eye(
            store,
            record,
            job_id=job_id,
            model_id=eye_id,
            provider=eye_provider,
            owner_id=owner_id,
            revision=revision,
        )
        if _planning_blocked(record):
            return record
        if record.readiness is None or not brain_may_proceed(record.readiness):
            return record

        record = _run_brain(
            store,
            record,
            job_id=job_id,
            model_id=brain_id,
            provider=brain_provider,
            owner_id=owner_id,
            revision=revision,
        )
        if _planning_blocked(record):
            return record
        if record.brain is None or record.brain.result is None:
            return record
        if not stylist_may_proceed(record.brain.result):
            return record

        record = _run_stylist(
            store,
            record,
            job_id=job_id,
            model_id=stylist_id,
            provider=stylist_provider,
            owner_id=owner_id,
            revision=revision,
        )
        if _planning_blocked(record):
            return record
        if (
            record.brain is None
            or record.brain.result is None
            or record.stylist is None
            or record.stylist.result is None
        ):
            return record
        if not engine_may_proceed(record.brain.result, record.stylist.result):
            return record

        return _run_compile(
            store,
            record,
            job_id=job_id,
            model_id=compile_id,
            compiler=compiler,
            owner_id=owner_id,
            revision=revision,
        )


def schedule_planning(
    store: JobStore,
    *,
    job_id: str,
    eye_provider: EyeProvider,
    brain_provider: BrainProvider,
    stylist_provider: StylistProvider,
    compiler: EngineCompiler,
    owner_id: str | None = None,
    revision: int | None = None,
) -> None:
    """Run advance_planning in a daemon thread. Does not block the caller.

    Exceptions are logged and do not propagate to the scheduling thread.
    GET/status polling must not call this function.
    """

    thread = threading.Thread(
        target=_run_scheduled_planning,
        kwargs={
            "store": store,
            "job_id": job_id,
            "eye_provider": eye_provider,
            "brain_provider": brain_provider,
            "stylist_provider": stylist_provider,
            "compiler": compiler,
            "owner_id": owner_id,
            "revision": revision,
        },
        name=f"midas-planning-{job_id}",
        daemon=True,
    )
    with _scheduled_guard:
        _scheduled_threads[job_id] = thread
    thread.start()


def join_scheduled_planning(job_id: str | None = None, timeout: float = 10.0) -> bool:
    """Wait for one scheduled planning thread, or all of them. Tests use this."""

    with _scheduled_guard:
        if job_id is None:
            threads = list(_scheduled_threads.values())
        else:
            thread = _scheduled_threads.get(job_id)
            threads = [thread] if thread is not None else []
    finished = True
    for thread in threads:
        thread.join(timeout)
        if thread.is_alive():
            finished = False
    return finished


def _run_scheduled_planning(
    *,
    store: JobStore,
    job_id: str,
    eye_provider: EyeProvider,
    brain_provider: BrainProvider,
    stylist_provider: StylistProvider,
    compiler: EngineCompiler,
    owner_id: str | None,
    revision: int | None,
) -> None:
    try:
        advance_planning(
            store,
            job_id=job_id,
            eye_provider=eye_provider,
            brain_provider=brain_provider,
            stylist_provider=stylist_provider,
            compiler=compiler,
            owner_id=owner_id,
            revision=revision,
        )
    except Exception:
        logger.exception("scheduled planning failed for job_id=%s", job_id)


def _planning_blocked(record: JobRecord) -> bool:
    return record.state in {"hold", "failed"}


def _run_eye(
    store: JobStore,
    record: JobRecord,
    *,
    job_id: str,
    model_id: str,
    provider: EyeProvider,
    owner_id: str | None,
    revision: int | None,
) -> JobRecord:
    if planning_eye_is_complete(record):
        return record
    try:
        return execute_job_eye(
            store,
            job_id=job_id,
            model_id=model_id,
            provider=provider,
            owner_id=owner_id,
            revision=revision,
        )
    except EyeProviderFailedError:
        return get_job(store, job_id, owner_id=owner_id, revision=revision)


def _run_brain(
    store: JobStore,
    record: JobRecord,
    *,
    job_id: str,
    model_id: str,
    provider: BrainProvider,
    owner_id: str | None,
    revision: int | None,
) -> JobRecord:
    if planning_brain_is_complete(record):
        return record
    try:
        return execute_job_brain(
            store,
            job_id=job_id,
            model_id=model_id,
            provider=provider,
            owner_id=owner_id,
            revision=revision,
        )
    except (BrainProviderFailedError, BrainNotReadyError):
        return get_job(store, job_id, owner_id=owner_id, revision=revision)


def _run_stylist(
    store: JobStore,
    record: JobRecord,
    *,
    job_id: str,
    model_id: str,
    provider: StylistProvider,
    owner_id: str | None,
    revision: int | None,
) -> JobRecord:
    if planning_stylist_is_complete(record):
        return record
    try:
        return execute_job_stylist(
            store,
            job_id=job_id,
            model_id=model_id,
            provider=provider,
            owner_id=owner_id,
            revision=revision,
        )
    except (StylistProviderFailedError, StylistNotReadyError):
        return get_job(store, job_id, owner_id=owner_id, revision=revision)


def _run_compile(
    store: JobStore,
    record: JobRecord,
    *,
    job_id: str,
    model_id: str,
    compiler: EngineCompiler,
    owner_id: str | None,
    revision: int | None,
) -> JobRecord:
    if planning_compile_is_complete(record):
        return record
    try:
        return execute_job_compile(
            store,
            job_id=job_id,
            model_id=model_id,
            compiler=compiler,
            owner_id=owner_id,
            revision=revision,
        )
    except (EngineProviderFailedError, EngineNotReadyError):
        return get_job(store, job_id, owner_id=owner_id, revision=revision)
