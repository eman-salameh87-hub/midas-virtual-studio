"""Local/dev JobRecord recovery from the filesystem artifact store.

This is not Vault persistence and is not a database. It reconstructs
in-memory JobState from outputs/<job_id>/ after a process restart.
It does not rerun providers and does not rewrite artifacts.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.contracts.brain import BrainPlan
from app.contracts.critique import CritiqueAssessment
from app.contracts.engine import EngineCompile
from app.contracts.eye import EyeObservation
from app.contracts.generation import GenerationOperation, GenerationReceipt
from app.contracts.job import Phase0JobContract
from app.contracts.reference import ReferenceMeasurement
from app.contracts.repair import RepairPlan
from app.contracts.review import OwnerApproval, PackageRelease, PreGenerationApproval
from app.contracts.stylist import StylistPlan
from app.providers.brain import BrainEvidenceRef
from app.runtime.checksum import annotate_checksum
from app.runtime.reference_metadata import retain_stored_measurements
from app.runtime.artifacts import (
    ArtifactStore,
    FilesystemArtifactStore,
    generation_artifact_name,
    output_filename,
    user_outputs_root,
)
from app.runtime.state import (
    BrainInputMetadata,
    EngineInputMetadata,
    JobError,
    JobRecord,
    JobStage,
    JobState,
    JobStore,
    StoredBrain,
    StoredCritique,
    StoredEngine,
    StoredGeneration,
    StoredRepair,
    StoredStylist,
    StylistInputMetadata,
)
from app.stages.eye import Readiness, build_eye_input

logger = logging.getLogger("app.runtime.recovery")

_STAGE_ORDER: tuple[JobStage, ...] = (
    "intake",
    "eye",
    "brain",
    "stylist",
    "compile",
    "generate",
    "critique",
    "repair",
)


def recover_jobs_from_artifacts(
    job_store: JobStore,
    artifacts: ArtifactStore | None = None,
) -> list[str]:
    """Load completed jobs from disk into JobStore. Skip jobs already in memory."""

    store = artifacts or FilesystemArtifactStore(user_outputs_root())
    recovered: list[str] = []
    for job_id in store.list_job_ids():
        if job_store.get(job_id) is not None:
            continue
        try:
            record = reconstruct_job_record(job_id, store)
        except Exception:
            logger.warning("skipping malformed job %s during recovery", job_id, exc_info=True)
            continue
        if record is None:
            continue
        job_store.save(record)
        recovered.append(job_id)
    return recovered


def reconstruct_job_record(
    job_id: str, artifacts: ArtifactStore
) -> JobRecord | None:
    """Rebuild one JobRecord from artifacts. None if job.json is missing."""

    raw_job = _read_json(artifacts, job_id, "job.json")
    if raw_job is None:
        logger.warning("skipping job %s: job.json is missing or invalid", job_id)
        return None
    try:
        contract = Phase0JobContract.model_validate(raw_job.get("contract"))
        owner_id = str(raw_job.get("owner_id") or contract.owner_id)
        revision = int(raw_job.get("revision") or contract.revision)
        hold = (
            Readiness.model_validate(raw_job["hold"])
            if raw_job.get("hold") is not None
            else None
        )
        error = (
            JobError.model_validate(raw_job["error"])
            if raw_job.get("error") is not None
            else None
        )
        approval = (
            OwnerApproval.model_validate(raw_job["approval"])
            if isinstance(raw_job.get("approval"), dict)
            else None
        )
        release = (
            PackageRelease.model_validate(raw_job["release"])
            if isinstance(raw_job.get("release"), dict)
            else None
        )
        pre_generation_approval = (
            PreGenerationApproval.model_validate(raw_job["pre_generation_approval"])
            if isinstance(raw_job.get("pre_generation_approval"), dict)
            else None
        )
    except (ValidationError, TypeError, ValueError):
        logger.warning("skipping job %s: job.json failed contract validation", job_id, exc_info=True)
        return None

    persisted_job_id = str(raw_job.get("job_id") or job_id)
    if persisted_job_id != job_id:
        logger.warning(
            "skipping job %s: job.json job_id %s does not match directory",
            job_id,
            persisted_job_id,
        )
        return None

    reference_bytes = _load_input_bytes(artifacts, job_id, contract)
    eye_model_id, eye_input, observation, readiness = _load_eye(
        artifacts, job_id, contract
    )
    brain = _load_brain(artifacts, job_id, contract, observation, reference_bytes)
    stylist = _load_stylist(artifacts, job_id, contract, brain, reference_bytes)
    engine = _load_compile(artifacts, job_id, contract, brain, stylist, reference_bytes)
    generation = _load_generation(artifacts, job_id, reference_bytes)
    critique, critique_history = _load_critiques(artifacts, job_id)
    repairs, latest_repair = _load_repairs(artifacts, job_id, reference_bytes)
    generation_history = _load_generation_history(
        artifacts, job_id, reference_bytes, generation
    )
    repair_count = 0
    raw_count = raw_job.get("repair_count")
    if isinstance(raw_count, int) and 0 <= raw_count <= 2:
        repair_count = raw_count
    elif latest_repair is not None:
        repair_count = min(latest_repair.plan.repair_count, 2)

    stage = _effective_stage(
        _as_stage(raw_job.get("stage")),
        observation is not None,
        brain is not None,
        stylist is not None,
        engine is not None,
        generation is not None,
        critique is not None,
        latest_repair is not None,
    )
    state = _effective_state(
        _as_state(raw_job.get("state")),
        generation,
        critique,
        latest_repair,
        approval=approval,
    )
    status = _as_state(raw_job.get("status")) or state
    review_status, complete, releasable, approval, release = _recovered_review(
        raw_review_status=raw_job.get("review_status"),
        raw_complete=raw_job.get("complete"),
        generation=generation,
        critique=critique,
        approval=approval,
        release=release,
        state=state,
    )
    if review_status == "review_pending" and state not in {"hold", "failed"}:
        state = "review_pending"
        status = state
    elif review_status == "owner_approved" and approval is not None:
        state = "approved"
        status = state
    elif review_status == "released" and approval is not None and release is not None:
        state = "released"
        status = state
    elif review_status == "hold":
        state = "hold"
        status = state
    measurements = _load_reference_measurements(
        raw_job.get("reference_measurements"),
        contract,
        reference_bytes,
        observation,
    )
    checksum_failed = (
        generation is not None and generation.checksum_status == "mismatch"
    ) or any(item.checksum_status == "mismatch" for item in measurements)
    if checksum_failed:
        state = "hold"
        status = "hold"
        review_status = "hold"
        complete = False
        releasable = False
        error = JobError(
            code="CHECKSUM_MISMATCH",
            message="Stored checksum does not match the artifact bytes",
        )
    try:
        return JobRecord(
            job_id=job_id,
            owner_id=owner_id,
            contract=contract,
            revision=revision,
            stage=stage,
            state=state,
            status=status,
            hold=hold,
            error=error,
            eye_model_id=eye_model_id,
            eye_input=eye_input,
            observation=observation,
            readiness=readiness,
            brain=brain,
            stylist=stylist,
            engine=engine,
            generation=generation,
            critique=critique,
            critique_history=critique_history,
            repair=latest_repair,
            repairs=repairs,
            generation_history=generation_history,
            repair_count=repair_count,
            review_status=review_status,
            complete=complete,
            releasable=releasable,
            approval=approval,
            pre_generation_approval=pre_generation_approval,
            release=release,
            events=[],
            reference_bytes=reference_bytes,
            reference_measurements=measurements,
        )
    except (ValidationError, TypeError, ValueError):
        logger.warning("skipping job %s: reconstructed JobRecord is invalid", job_id, exc_info=True)
        return None


def _load_eye(
    artifacts: ArtifactStore,
    job_id: str,
    contract: Phase0JobContract,
) -> tuple[str | None, Any, EyeObservation | None, Readiness | None]:
    payload = _read_json(artifacts, job_id, "eye.json")
    if payload is None:
        return None, None, None, None
    try:
        observation = EyeObservation.model_validate(payload.get("observation"))
        readiness = Readiness.model_validate(payload.get("readiness"))
        eye_input = build_eye_input(
            contract, [item.reference_id for item in contract.references]
        )
        model_id = payload.get("model_id")
        return (
            str(model_id) if isinstance(model_id, str) and model_id.strip() else None,
            eye_input,
            observation,
            readiness,
        )
    except (ValidationError, TypeError, ValueError):
        logger.warning("skipping eye artifact for job %s", job_id, exc_info=True)
        return None, None, None, None


def _load_brain(
    artifacts: ArtifactStore,
    job_id: str,
    contract: Phase0JobContract,
    observation: EyeObservation | None,
    reference_bytes: dict[str, bytes],
) -> StoredBrain | None:
    payload = _read_json(artifacts, job_id, "brain.json")
    if payload is None:
        return None
    try:
        plan = BrainPlan.model_validate(payload.get("plan"))
        model_id = _required_model_id(payload.get("model_id"))
        status = payload.get("execution_status") or "completed"
        metadata = None
        if observation is not None:
            metadata = BrainInputMetadata(
                job_id=job_id,
                contract_id=contract.contract_id,
                revision=contract.revision,
                observation_contract_id=plan.observation_contract_id,
                observation_revision=plan.observation_revision,
                evidence=_evidence(contract, reference_bytes),
            )
        return StoredBrain(
            model_id=model_id,
            input=metadata,
            result=plan,
            status=status if status in {"completed", "failed"} else "completed",
        )
    except (ValidationError, TypeError, ValueError):
        logger.warning("skipping brain artifact for job %s", job_id, exc_info=True)
        return None


def _load_stylist(
    artifacts: ArtifactStore,
    job_id: str,
    contract: Phase0JobContract,
    brain: StoredBrain | None,
    reference_bytes: dict[str, bytes],
) -> StoredStylist | None:
    payload = _read_json(artifacts, job_id, "stylist.json")
    if payload is None:
        return None
    try:
        plan = StylistPlan.model_validate(payload.get("plan"))
        model_id = _required_model_id(payload.get("model_id"))
        status = payload.get("execution_status") or "completed"
        metadata = None
        if brain is not None and brain.result is not None:
            metadata = StylistInputMetadata(
                job_id=job_id,
                contract_id=contract.contract_id,
                revision=contract.revision,
                brain_contract_id=brain.result.contract_id,
                brain_revision=brain.result.contract_revision,
                evidence=_evidence(contract, reference_bytes),
            )
        return StoredStylist(
            model_id=model_id,
            input=metadata,
            result=plan,
            status=status if status in {"completed", "failed"} else "completed",
        )
    except (ValidationError, TypeError, ValueError):
        logger.warning("skipping stylist artifact for job %s", job_id, exc_info=True)
        return None


def _load_compile(
    artifacts: ArtifactStore,
    job_id: str,
    contract: Phase0JobContract,
    brain: StoredBrain | None,
    stylist: StoredStylist | None,
    reference_bytes: dict[str, bytes],
) -> StoredEngine | None:
    payload = _read_json(artifacts, job_id, "compile.json")
    if payload is None:
        return None
    try:
        compile_artifact = EngineCompile.model_validate(payload.get("compile"))
        model_id = _required_model_id(payload.get("model_id") or compile_artifact.model_id)
        status = payload.get("execution_status") or "completed"
        metadata = None
        if (
            brain is not None
            and brain.result is not None
            and stylist is not None
            and stylist.result is not None
        ):
            metadata = EngineInputMetadata(
                job_id=job_id,
                contract_id=contract.contract_id,
                revision=contract.revision,
                brain_contract_id=brain.result.contract_id,
                brain_revision=brain.result.contract_revision,
                stylist_contract_id=stylist.result.contract_id,
                stylist_revision=stylist.result.contract_revision,
                evidence=_evidence(contract, reference_bytes),
            )
        return StoredEngine(
            model_id=model_id,
            input=metadata,
            result=compile_artifact,
            status=status if status in {"completed", "failed"} else "completed",
        )
    except (ValidationError, TypeError, ValueError):
        logger.warning("skipping compile artifact for job %s", job_id, exc_info=True)
        return None


def _load_generation(
    artifacts: ArtifactStore,
    job_id: str,
    reference_bytes: dict[str, bytes],
) -> StoredGeneration | None:
    payload = _read_json(artifacts, job_id, "generation.json")
    if payload is None:
        return None
    try:
        operation = GenerationOperation.model_validate(payload.get("operation"))
        receipt = None
        if payload.get("receipt") is not None:
            receipt = GenerationReceipt.model_validate(payload.get("receipt"))
        status = payload.get("status") or (receipt.status if receipt else "claimed")
        if receipt is not None and receipt.output is not None:
            _load_generation_bytes(
                artifacts,
                job_id,
                receipt,
                reference_bytes,
                artifact_filename=payload.get("artifact_filename"),
                sequence_index=payload.get("sequence_index"),
            )
        stored = StoredGeneration(
            operation=operation,
            receipt=receipt,
            status=status,
        )
        if receipt is not None and receipt.output is not None:
            stored = annotate_checksum(
                stored, reference_bytes.get(receipt.output.output_id)
            )
        return stored
    except (ValidationError, TypeError, ValueError):
        logger.warning("skipping generation artifact for job %s", job_id, exc_info=True)
        return None


def _load_generation_bytes(
    artifacts: ArtifactStore,
    job_id: str,
    receipt: GenerationReceipt,
    reference_bytes: dict[str, bytes],
    *,
    artifact_filename: object = None,
    sequence_index: object = None,
) -> None:
    if receipt.output is None:
        return
    output = receipt.output
    ext = output.media_type.lower()
    names: list[str] = []
    if isinstance(artifact_filename, str) and artifact_filename.strip():
        names.append(f"generations/{Path(artifact_filename).name}")
    if isinstance(sequence_index, int) and 1 <= sequence_index <= 3:
        names.append(generation_artifact_name(sequence_index, output.media_type))
    names.extend(
        (
            f"output/{output.output_id}.{ext}",
            f"generations/{output.output_id}.{ext}",
            f"output/current.{ext}",
            f"output/{output_filename(output.media_type)}",
        )
    )
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        data = artifacts.get_artifact(job_id, name)
        if data:
            reference_bytes[output.output_id] = data
            return
    data = artifacts.get_output(job_id, output_filename(output.media_type))
    if data and output.output_id not in reference_bytes:
        reference_bytes[output.output_id] = data


def _load_generation_history(
    artifacts: ArtifactStore,
    job_id: str,
    reference_bytes: dict[str, bytes],
    current: StoredGeneration | None,
) -> list[StoredGeneration]:
    history: list[StoredGeneration] = []
    current_key = current.operation.operation_key if current is not None else None
    seen_keys: set[str] = set()
    for _index, payload in _iter_generation_payloads(artifacts, job_id):
        try:
            stored = _stored_generation_from_payload(payload, artifacts, job_id, reference_bytes)
        except (ValidationError, TypeError, ValueError):
            logger.warning("skipping generation history for job %s", job_id, exc_info=True)
            continue
        key = stored.operation.operation_key
        if current_key and key == current_key:
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        history.append(stored)
    return history


def _stored_generation_from_payload(
    payload: dict[str, Any],
    artifacts: ArtifactStore,
    job_id: str,
    reference_bytes: dict[str, bytes],
) -> StoredGeneration:
    operation = GenerationOperation.model_validate(payload.get("operation"))
    receipt = None
    if payload.get("receipt") is not None:
        receipt = GenerationReceipt.model_validate(payload.get("receipt"))
    status = payload.get("status") or (receipt.status if receipt else "claimed")
    if receipt is not None:
        _load_generation_bytes(
            artifacts,
            job_id,
            receipt,
            reference_bytes,
            artifact_filename=payload.get("artifact_filename"),
            sequence_index=payload.get("sequence_index"),
        )
    stored = StoredGeneration(operation=operation, receipt=receipt, status=status)
    if receipt is not None and receipt.output is not None:
        stored = annotate_checksum(stored, reference_bytes.get(receipt.output.output_id))
    return stored


def _load_repairs(
    artifacts: ArtifactStore,
    job_id: str,
    reference_bytes: dict[str, bytes],
) -> tuple[list[StoredRepair], StoredRepair | None]:
    found: list[StoredRepair] = []
    for name in _repair_artifact_candidates(artifacts, job_id):
        payload = _read_json(artifacts, job_id, name)
        if payload is None:
            continue
        try:
            plan = RepairPlan.model_validate(payload.get("plan"))
            status = str(payload.get("status") or plan.status)
            stored = StoredRepair(plan=plan, status=status)
        except (ValidationError, TypeError, ValueError):
            logger.warning("skipping repair artifact %s for job %s", name, job_id, exc_info=True)
            continue
        if plan.receipt is not None:
            _load_generation_bytes(
                artifacts,
                job_id,
                plan.receipt,
                reference_bytes,
                sequence_index=payload.get("result_generation_index"),
            )
        if not any(
            item.plan.repair_count == stored.plan.repair_count
            and item.plan.critique_generation_output_id
            == stored.plan.critique_generation_output_id
            for item in found
        ):
            found.append(stored)
    found.sort(key=lambda item: item.plan.repair_count)
    latest = None
    latest_payload = _read_json(artifacts, job_id, "repair.json")
    if latest_payload is not None:
        try:
            plan = RepairPlan.model_validate(latest_payload.get("plan"))
            latest = StoredRepair(
                plan=plan,
                status=str(latest_payload.get("status") or plan.status),
            )
        except (ValidationError, TypeError, ValueError):
            logger.warning("skipping latest repair artifact for job %s", job_id, exc_info=True)
    if latest is None and found:
        latest = found[-1]
    return found, latest


def _load_reference_measurements(
    raw: object,
    contract: Phase0JobContract,
    reference_bytes: dict[str, bytes],
    observation: EyeObservation | None,
) -> list[ReferenceMeasurement]:
    """Reload stored measurements. Jobs that never recorded them stay unknown."""

    del contract, observation
    if not isinstance(raw, list) or not raw:
        return []
    try:
        stored = [ReferenceMeasurement.model_validate(item) for item in raw]
    except (ValidationError, TypeError, ValueError):
        return []
    return retain_stored_measurements(stored, reference_bytes)


def _load_critiques(
    artifacts: ArtifactStore, job_id: str
) -> tuple[StoredCritique | None, list[StoredCritique]]:
    current = _load_critique(artifacts, job_id)
    history: list[StoredCritique] = []
    current_output = None
    if current is not None and current.result is not None:
        current_output = current.result.generation_output_id
    names = [f"critiques/{name}" for name in _list_dir(artifacts, job_id, "critiques")]
    names.extend(
        (
            "critiques/01_critique_generation_01.json",
            "critiques/02_critique_generation_02.json",
            "critiques/03_critique_generation_03.json",
        )
    )
    seen: set[str] = set()
    for name in names:
        if name in seen:
            continue
        seen.add(name)
        payload = _read_json(artifacts, job_id, name)
        if payload is None:
            continue
        try:
            assessment = CritiqueAssessment.model_validate(payload.get("assessment"))
            model_id = _required_model_id(payload.get("model_id"))
            status = payload.get("execution_status") or "completed"
            stored = StoredCritique(
                model_id=model_id,
                result=assessment,
                status=status if status in {"completed", "failed"} else "completed",
            )
        except (ValidationError, TypeError, ValueError):
            continue
        if assessment.generation_output_id == current_output:
            continue
        if any(
            item.result is not None
            and item.result.generation_output_id == assessment.generation_output_id
            for item in history
        ):
            continue
        history.append(stored)
    return current, history


def _load_critique(artifacts: ArtifactStore, job_id: str) -> StoredCritique | None:
    payload = _read_json(artifacts, job_id, "critique.json")
    if payload is None:
        return None
    try:
        assessment = CritiqueAssessment.model_validate(payload.get("assessment"))
        model_id = _required_model_id(payload.get("model_id"))
        status = payload.get("execution_status") or "completed"
        return StoredCritique(
            model_id=model_id,
            result=assessment,
            status=status if status in {"completed", "failed"} else "completed",
        )
    except (ValidationError, TypeError, ValueError):
        logger.warning("skipping critique artifact for job %s", job_id, exc_info=True)
        return None


def _load_input_bytes(
    artifacts: ArtifactStore,
    job_id: str,
    contract: Phase0JobContract,
) -> dict[str, bytes]:
    stored: dict[str, bytes] = {}
    for item in contract.references:
        candidates = (
            f"input/{item.reference_id}-{item.filename}",
            f"input/{item.filename}",
        )
        for name in candidates:
            data = artifacts.get_artifact(job_id, name)
            if data:
                stored[item.reference_id] = data
                break
    return stored


def _evidence(
    contract: Phase0JobContract, reference_bytes: dict[str, bytes]
) -> list[BrainEvidenceRef]:
    return [
        BrainEvidenceRef(
            reference_id=item.reference_id,
            filename=item.filename,
            media_type=item.media_type,
            hash_algorithm=item.hash_algorithm,
            content_hash=item.content_hash,
            role=item.role,
            bytes_available=item.reference_id in reference_bytes,
        )
        for item in contract.references
    ]


def _list_dir(artifacts: ArtifactStore, job_id: str, directory: str) -> list[str]:
    lister = getattr(artifacts, "list_artifact_names", None)
    if not callable(lister):
        return []
    try:
        return list(lister(job_id, directory))
    except (TypeError, ValueError):
        return []


def _iter_generation_payloads(
    artifacts: ArtifactStore, job_id: str
) -> list[tuple[int, dict[str, Any]]]:
    indexed: list[tuple[int, dict[str, Any]]] = []
    seen_files: set[str] = set()
    names = _list_dir(artifacts, job_id, "generations")
    fallback = [f"{index}.json" for index in range(1, 4)] + [
        "01_initial.json",
        "02_repair.json",
        "03_repair.json",
    ]
    for name in names + fallback:
        if not name.endswith(".json") or name in seen_files:
            continue
        seen_files.add(name)
        payload = _read_json(artifacts, job_id, f"generations/{name}")
        if payload is None:
            continue
        sequence = payload.get("sequence_index")
        if not isinstance(sequence, int):
            stem = name.rsplit(".", 1)[0]
            if stem[:2].isdigit():
                sequence = int(stem[:2])
            elif stem.isdigit():
                sequence = int(stem)
            else:
                sequence = 0
        if "sequence_index" not in payload:
            payload["sequence_index"] = sequence
        indexed.append((sequence, payload))
    indexed.sort(key=lambda item: item[0])
    return indexed


def _repair_artifact_candidates(artifacts: ArtifactStore, job_id: str) -> list[str]:
    names = [f"repairs/{name}" for name in _list_dir(artifacts, job_id, "repairs")]
    names.extend(
        (
            "repairs/01_repair_generation_01_to_02.json",
            "repairs/02_repair_generation_02_to_03.json",
            "repairs/1.json",
            "repairs/2.json",
            "repairs/hold.json",
        )
    )
    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        if not name.endswith(".json") or name in seen:
            continue
        seen.add(name)
        ordered.append(name)
    return ordered


def _read_json(artifacts: ArtifactStore, job_id: str, name: str) -> dict[str, Any] | None:
    raw = artifacts.get_artifact(job_id, name)
    if not raw:
        return None
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.warning("skipping %s for job %s: not valid JSON", name, job_id)
        return None
    if not isinstance(value, dict):
        logger.warning("skipping %s for job %s: JSON was not an object", name, job_id)
        return None
    return value


def _required_model_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("model_id is required")
    return value.strip()


def _as_stage(value: object) -> JobStage:
    if value in _STAGE_ORDER:
        return value  # type: ignore[return-value]
    return "intake"


def _as_state(value: object) -> JobState | None:
    if value in {
        "accepted",
        "ready",
        "hold",
        "failed",
        "review_pending",
        "approved",
        "released",
    }:
        return value  # type: ignore[return-value]
    return None


def _recovered_review(
    *,
    raw_review_status: object,
    raw_complete: object,
    generation: StoredGeneration | None,
    critique: StoredCritique | None,
    approval: OwnerApproval | None,
    release: PackageRelease | None,
    state: JobState,
) -> tuple[object, bool, bool, OwnerApproval | None, PackageRelease | None]:
    """Restore review facts. Missing approval is never filled in."""

    critique_pass = (
        critique is not None
        and critique.result is not None
        and critique.result.overall_result == "pass"
        and critique.result.status != "hold"
    )
    format_failed = (
        generation is not None
        and generation.receipt is not None
        and generation.receipt.format_check == "failed"
    )
    if format_failed or state == "hold":
        return "hold", False, False, approval, None
    if approval is None or release is not None and approval is None:
        release = None
    if approval is None:
        if critique_pass:
            return "review_pending", False, False, None, None
        if (
            generation is not None
            and generation.receipt is not None
            and generation.receipt.status == "completed"
        ):
            return "generation_completed", False, False, None, None
        return None, False, False, None, None
    if raw_review_status == "released" and release is not None:
        return "released", True, True, approval, release
    if raw_complete is False:
        return "review_pending" if critique_pass else "generation_completed", False, False, approval, None
    return "owner_approved", True, True, approval, None


def _effective_stage(
    job_stage: JobStage,
    has_eye: bool,
    has_brain: bool,
    has_stylist: bool,
    has_compile: bool,
    has_generation: bool,
    has_critique: bool,
    has_repair: bool,
) -> JobStage:
    derived: JobStage = "intake"
    if has_eye:
        derived = "eye"
    if has_brain:
        derived = "brain"
    if has_stylist:
        derived = "stylist"
    if has_compile:
        derived = "compile"
    if has_generation:
        derived = "generate"
    if has_critique:
        derived = "critique"
    if has_repair:
        derived = "repair"
    if _STAGE_ORDER.index(derived) > _STAGE_ORDER.index(job_stage):
        return derived
    return job_stage


def _effective_state(
    job_state: JobState | None,
    generation: StoredGeneration | None,
    critique: StoredCritique | None,
    repair: StoredRepair | None = None,
    *,
    approval: OwnerApproval | None = None,
) -> JobState:
    if repair is not None and repair.plan.status == "hold":
        return "hold"
    if repair is not None and repair.plan.status == "failed":
        return "failed"
    if (
        generation is not None
        and generation.receipt is not None
        and generation.receipt.format_check == "failed"
    ):
        return "hold"
    if critique is not None and critique.result is not None:
        if critique.result.status == "hold":
            return "hold"
        if critique.result.overall_result == "pass" and approval is None:
            return "review_pending"
        if critique.result.overall_result == "pass" and approval is not None:
            return job_state or "approved"
        return "ready"
    if generation is not None and generation.receipt is not None:
        if generation.receipt.status == "failed":
            return "failed"
        if generation.receipt.status in {"hold", "uncertain"}:
            return "hold"
        if generation.receipt.status == "completed":
            return job_state or "ready"
    return job_state or "accepted"
