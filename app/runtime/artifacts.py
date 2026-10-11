"""Local/dev job artifact store.

This is a process-local filesystem layout under outputs/<job_id>/. It is not
the durable Vault layer and is not a database. JobRecord remains authoritative
in-process state. This store can be replaced by object storage later without
changing Eye/Brain/Stylist/Engine/Operator stages.
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Protocol

from app.contracts.generation import GeneratedMediaType
from app.runtime.state import JobRecord

_JOB_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")
_OUTPUT_NAMES = (
    "current.png",
    "current.jpg",
    "current.webp",
    "generated.png",
    "generated.jpg",
    "generated.webp",
)
_MEDIA_EXT: dict[GeneratedMediaType, str] = {"PNG": "png", "JPG": "jpg", "WebP": "webp"}
_MEDIA_CONTENT_TYPE: dict[GeneratedMediaType, str] = {
    "PNG": "image/png",
    "JPG": "image/jpeg",
    "WebP": "image/webp",
}


class ArtifactStore(Protocol):
    """Replacement seam for later durable/object storage."""

    def save_job(self, record: JobRecord) -> None: ...

    def save_eye(self, record: JobRecord) -> None: ...

    def save_brain(self, record: JobRecord) -> None: ...

    def save_stylist(self, record: JobRecord) -> None: ...

    def save_compile(self, record: JobRecord) -> None: ...

    def save_generation(self, record: JobRecord) -> None: ...

    def save_critique(self, record: JobRecord) -> None: ...

    def save_repair(self, record: JobRecord) -> None: ...

    def save_input(self, job_id: str, filename: str, data: bytes) -> None: ...

    def save_output(self, job_id: str, filename: str, data: bytes) -> None: ...

    def get_output(self, job_id: str, filename: str | None = None) -> bytes | None: ...

    def get_artifact(self, job_id: str, name: str) -> bytes | None: ...

    def list_artifact_names(self, job_id: str, directory: str) -> list[str]: ...

    def list_job_ids(self) -> list[str]: ...


class FilesystemArtifactStore:
    """Isolated per-job folders. Never writes outside the configured root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self._lock = threading.Lock()

    def save_job(self, record: JobRecord) -> None:
        payload = {
            "job_id": record.job_id,
            "owner_id": record.owner_id,
            "revision": record.revision,
            "stage": record.stage,
            "state": record.state,
            "status": record.status,
            "contract": record.contract.model_dump(mode="json"),
            "hold": record.hold.model_dump(mode="json") if record.hold else None,
            "error": record.error.model_dump(mode="json") if record.error else None,
            "repair_count": record.repair_count,
            "repair_limit": record.repair_limit,
            "review_status": record.review_status,
            "complete": record.complete,
            "releasable": record.releasable,
            "approval": record.approval.model_dump(mode="json") if record.approval else None,
            "pre_generation_approval": (
                record.pre_generation_approval.model_dump(mode="json")
                if record.pre_generation_approval
                else None
            ),
            "release": record.release.model_dump(mode="json") if record.release else None,
            "reference_measurements": [
                item.model_dump(mode="json") for item in record.reference_measurements
            ],
        }
        self._write_json(record.job_id, "job.json", payload)
        from app.stages.package import build_delivery_manifest

        manifest = build_delivery_manifest(record)
        self._write_json(record.job_id, "manifest.json", manifest.model_dump(mode="json"))

    def save_eye(self, record: JobRecord) -> None:
        if record.observation is None or record.readiness is None:
            return
        self._write_json(
            record.job_id,
            "eye.json",
            {
                "model_id": record.eye_model_id,
                "observation": record.observation.model_dump(mode="json"),
                "readiness": record.readiness.model_dump(mode="json"),
            },
        )

    def save_brain(self, record: JobRecord) -> None:
        stored = record.brain
        if stored is None or stored.result is None:
            return
        self._write_json(
            record.job_id,
            "brain.json",
            {
                "model_id": stored.model_id,
                "execution_status": stored.status,
                "plan": stored.result.model_dump(mode="json"),
            },
        )

    def save_stylist(self, record: JobRecord) -> None:
        stored = record.stylist
        if stored is None or stored.result is None:
            return
        self._write_json(
            record.job_id,
            "stylist.json",
            {
                "model_id": stored.model_id,
                "execution_status": stored.status,
                "plan": stored.result.model_dump(mode="json"),
            },
        )

    def save_compile(self, record: JobRecord) -> None:
        stored = record.engine
        if stored is None or stored.result is None:
            return
        self._write_json(
            record.job_id,
            "compile.json",
            {
                "model_id": stored.model_id,
                "execution_status": stored.status,
                "compile": stored.result.model_dump(mode="json"),
            },
        )

    def save_generation(self, record: JobRecord) -> None:
        stored = record.generation
        if stored is None:
            return
        versions = _generation_versions(record)
        current_index = versions[-1][0] if versions else 1
        self._write_json(
            record.job_id,
            "generation.json",
            _generation_payload(stored, current_index, record),
        )
        for index, version in versions:
            self._write_generation_version(record, version, index)

    def save_critique(self, record: JobRecord) -> None:
        stored = record.critique
        if stored is None or stored.result is None:
            return
        generation_index = _generation_index_for_output(
            record, stored.result.generation_output_id
        )
        critique_index = generation_index
        payload = {
            "model_id": stored.model_id,
            "execution_status": stored.status,
            "critique_index": critique_index,
            "assessed_generation_index": generation_index,
            "generation_output_id": stored.result.generation_output_id,
            "assessment": stored.result.model_dump(mode="json"),
        }
        self._write_json(record.job_id, "critique.json", payload)
        self._write_json(
            record.job_id,
            critique_artifact_name(critique_index, generation_index),
            payload,
        )

    def save_repair(self, record: JobRecord) -> None:
        stored = record.repair
        if stored is None:
            return
        count = stored.plan.repair_count
        source_index = count if count else 0
        result_index = count + 1 if count else 0
        payload = {
            "status": stored.status,
            "repair_index": count,
            "source_generation_index": source_index,
            "result_generation_index": result_index,
            "plan": stored.plan.model_dump(mode="json"),
        }
        self._write_json(record.job_id, "repair.json", payload)
        if count:
            self._write_json(
                record.job_id,
                repair_artifact_name(count, source_index, result_index),
                payload,
            )
        else:
            self._write_json(record.job_id, "repairs/hold.json", payload)
        for index, version in _generation_versions(record):
            self._write_generation_version(record, version, index)

    def save_input(self, job_id: str, filename: str, data: bytes) -> None:
        path = self._resolve(job_id, "input", _safe_filename(filename))
        self._write_bytes(path, data)

    def save_output(self, job_id: str, filename: str, data: bytes) -> None:
        safe = _safe_filename(filename)
        self._write_bytes(self._resolve(job_id, "output", safe), data)
        stem, _, ext = safe.partition(".")
        if ext and stem == "generated":
            self._write_bytes(self._resolve(job_id, "output", f"current.{ext}"), data)
        elif ext and stem == "current":
            self._write_bytes(self._resolve(job_id, "output", f"generated.{ext}"), data)

    def get_output(self, job_id: str, filename: str | None = None) -> bytes | None:
        names = (_safe_filename(filename),) if filename else _OUTPUT_NAMES
        for name in names:
            path = self._resolve(job_id, "output", name)
            if path.is_file():
                return path.read_bytes()
        return None

    def get_artifact(self, job_id: str, name: str) -> bytes | None:
        parts = _safe_relative_parts(name)
        path = self._resolve(job_id, *parts)
        if path.is_file():
            return path.read_bytes()
        return None

    def list_artifact_names(self, job_id: str, directory: str) -> list[str]:
        parts = _safe_relative_parts(directory)
        path = self._resolve(job_id, *parts)
        if not path.is_dir():
            return []
        return sorted(child.name for child in path.iterdir() if child.is_file())

    def job_dir(self, job_id: str) -> Path:
        return self._job_dir(job_id)

    def list_job_ids(self) -> list[str]:
        root = self.root
        if not root.exists() or not root.is_dir():
            return []
        found: list[str] = []
        for path in sorted(root.iterdir()):
            if not path.is_dir():
                continue
            name = path.name
            if not _JOB_ID_RE.fullmatch(name) or ".." in name:
                continue
            # Client-brief dirs share this root and only have client_brief.json.
            if not (path / "job.json").is_file():
                continue
            found.append(name)
        return found

    def _write_json(self, job_id: str, name: str, payload: dict[str, object]) -> None:
        encoded = json.dumps(payload, indent=2, ensure_ascii=True).encode("utf-8")
        self._write_bytes(self._resolve(job_id, name), encoded)

    def _write_bytes(self, path: Path, data: bytes) -> None:
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)

    def _job_dir(self, job_id: str) -> Path:
        if not _JOB_ID_RE.fullmatch(job_id) or ".." in job_id:
            raise ValueError("job_id is not a safe artifact directory name")
        root = self.root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        candidate = (root / job_id).resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("artifact path escaped the outputs root")
        if candidate == root:
            raise ValueError("artifact path escaped the outputs root")
        return candidate

    def _resolve(self, job_id: str, *parts: str) -> Path:
        job_dir = self._job_dir(job_id)
        candidate = job_dir.joinpath(*parts).resolve()
        if job_dir not in candidate.parents and candidate != job_dir:
            raise ValueError("artifact path escaped the job directory")
        return candidate

    def _write_generation_version(self, record: JobRecord, stored: object, index: int) -> None:
        from app.runtime.state import StoredGeneration

        if not isinstance(stored, StoredGeneration):
            return
        payload = _generation_payload(stored, index, record)
        stem = generation_artifact_stem(index)
        self._write_json(record.job_id, f"generations/{stem}.json", payload)
        if stored.receipt is None or stored.receipt.output is None:
            return
        output = stored.receipt.output
        data = record.reference_bytes.get(output.output_id)
        if not data:
            return
        ext = _MEDIA_EXT[output.media_type]
        self._write_bytes(
            self._resolve(record.job_id, "generations", f"{stem}.{ext}"),
            data,
        )


def output_filename(media_type: GeneratedMediaType) -> str:
    return f"generated.{_MEDIA_EXT[media_type]}"


def content_type_for(media_type: GeneratedMediaType) -> str:
    return _MEDIA_CONTENT_TYPE[media_type]


def generation_artifact_stem(index: int) -> str:
    kind = "initial" if index == 1 else "repair"
    return f"{index:02d}_{kind}"


def generation_artifact_name(index: int, media_type: GeneratedMediaType) -> str:
    return f"generations/{generation_artifact_stem(index)}.{_MEDIA_EXT[media_type]}"


def critique_artifact_name(critique_index: int, generation_index: int) -> str:
    return (
        f"critiques/{critique_index:02d}_critique_generation_{generation_index:02d}.json"
    )


def repair_artifact_name(repair_index: int, source_index: int, result_index: int) -> str:
    return (
        f"repairs/{repair_index:02d}_repair_generation_"
        f"{source_index:02d}_to_{result_index:02d}.json"
    )


def _generation_versions(record: JobRecord) -> list[tuple[int, object]]:
    from app.runtime.state import StoredGeneration

    items: list[StoredGeneration] = list(record.generation_history)
    current = record.generation
    if current is not None:
        key = current.operation.operation_key
        if not any(item.operation.operation_key == key for item in items):
            items.append(current)
    return [(index, item) for index, item in enumerate(items, start=1)]


def _generation_index_for_output(record: JobRecord, output_id: str) -> int:
    for index, stored in _generation_versions(record):
        receipt = getattr(stored, "receipt", None)
        if receipt is not None and receipt.output is not None:
            if receipt.output.output_id == output_id:
                return index
    return max(len(_generation_versions(record)), 1)


def _generation_payload(stored: object, index: int, record: JobRecord | None = None) -> dict[str, object]:
    from app.runtime.state import StoredGeneration

    assert isinstance(stored, StoredGeneration)
    kind = "initial" if index == 1 else "repair"
    receipt = stored.receipt
    output = receipt.output if receipt is not None else None
    artifact_filename = None
    if output is not None:
        artifact_filename = (
            f"{generation_artifact_stem(index)}.{_MEDIA_EXT[output.media_type]}"
        )
    source_hashes: list[dict[str, str]] = []
    if record is not None:
        by_id = {
            item.reference_id: item.content_hash for item in record.contract.references
        }
        for reference_id in stored.operation.reference_ids:
            content_hash = by_id.get(reference_id)
            if content_hash:
                source_hashes.append(
                    {"reference_id": reference_id, "content_hash": content_hash}
                )
    return {
        "sequence_index": index,
        "generation_kind": kind,
        "parent_generation": None if index == 1 else index - 1,
        "artifact_filename": artifact_filename,
        "output_id": output.output_id if output is not None else None,
        "operation_key": stored.operation.operation_key,
        "provider_receipt_id": receipt.provider_receipt_id if receipt is not None else None,
        "provider": receipt.provider_name if receipt is not None else None,
        "model_id": stored.operation.model_id,
        "source_hashes": source_hashes,
        "requested_width": receipt.requested_width if receipt is not None else None,
        "requested_height": receipt.requested_height if receipt is not None else None,
        "requested_resolution": stored.operation.output_format.resolution,
        "requested_aspect_ratio": stored.operation.output_format.image_proportions,
        "submitted_api": (
            None if receipt is None or receipt.provider_request is None else receipt.provider_request.api
        ),
        "submitted_resolution": (
            None if receipt is None or receipt.provider_request is None else receipt.provider_request.resolution
        ),
        "submitted_aspect_ratio": (
            None if receipt is None or receipt.provider_request is None else receipt.provider_request.aspect_ratio
        ),
        "submitted_reference_count": (
            None
            if receipt is None or receipt.provider_request is None
            else receipt.provider_request.input_reference_count
        ),
        "measured_aspect_ratio": None if receipt is None else receipt.measured_aspect_ratio,
        "actual_width": receipt.measured_width if receipt is not None else None,
        "actual_height": receipt.measured_height if receipt is not None else None,
        "actual_mime": receipt.measured_mime if receipt is not None else None,
        "actual_format": receipt.measured_format if receipt is not None else None,
        "sha256": output.content_hash if output is not None else None,
        "observed_checksum": stored.observed_checksum,
        "checksum_status": stored.checksum_status,
        "timestamp": (
            receipt.completed_at or receipt.claimed_at if receipt is not None else None
        ),
        "operation": stored.operation.model_dump(mode="json"),
        "receipt": receipt.model_dump(mode="json") if receipt is not None else None,
        "status": stored.status,
    }


def persist_job_record(
    record: JobRecord,
    *,
    stage: str | None = None,
    write_inputs: bool = False,
    output: tuple[str, bytes] | None = None,
    artifacts: ArtifactStore | None = None,
) -> None:
    """Mirror JobRecord contracts onto the local artifact store."""

    store = artifacts or get_artifact_store()
    store.save_job(record)
    if write_inputs:
        for item in record.contract.references:
            data = record.reference_bytes.get(item.reference_id)
            if not data:
                continue
            filename = f"{item.reference_id}-{item.filename}"
            store.save_input(record.job_id, filename, data)
    if stage == "eye":
        store.save_eye(record)
    elif stage == "brain":
        store.save_brain(record)
    elif stage == "stylist":
        store.save_stylist(record)
    elif stage == "compile":
        store.save_compile(record)
    elif stage == "generate":
        store.save_generation(record)
    elif stage == "critique":
        store.save_critique(record)
    elif stage == "repair":
        store.save_repair(record)
        store.save_generation(record)
        store.save_critique(record)
    if output is not None:
        store.save_output(record.job_id, output[0], output[1])


_store_lock = threading.Lock()
_store: FilesystemArtifactStore | None = None
_store_root: str | None = None


def default_outputs_root() -> Path:
    env = os.getenv("MIDAS_OUTPUTS_DIR")
    if env and env.strip():
        return Path(env.strip())
    return Path(__file__).resolve().parents[2] / "outputs"


def get_artifact_store() -> FilesystemArtifactStore:
    """Return the process-local filesystem store for the current outputs root."""

    global _store, _store_root
    root = str(default_outputs_root().resolve())
    with _store_lock:
        if _store is None or _store_root != root:
            _store = FilesystemArtifactStore(Path(root))
            _store_root = root
        return _store


def reset_artifact_store() -> None:
    """Drop the cached store so tests can point at a new directory."""

    global _store, _store_root
    with _store_lock:
        _store = None
        _store_root = None


def _safe_filename(name: str) -> str:
    base = Path(name).name
    cleaned = _UNSAFE_FILENAME.sub("_", base).strip("._")
    if not cleaned:
        raise ValueError("filename is not a safe artifact name")
    if cleaned in {".", ".."}:
        raise ValueError("filename is not a safe artifact name")
    return cleaned[:180]


def _safe_relative_parts(name: str) -> tuple[str, ...]:
    raw = name.replace("\\", "/").strip("/")
    if not raw or raw.startswith("/") or ".." in Path(raw).parts:
        raise ValueError("artifact name is not a safe relative path")
    parts = tuple(_safe_filename(part) for part in Path(raw).parts)
    if not parts:
        raise ValueError("artifact name is not a safe relative path")
    return parts
