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
_OUTPUT_NAMES = ("generated.png", "generated.jpg", "generated.webp")
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
        }
        self._write_json(record.job_id, "job.json", payload)

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
        self._write_json(
            record.job_id,
            "generation.json",
            {
                "operation": stored.operation.model_dump(mode="json"),
                "receipt": stored.receipt.model_dump(mode="json") if stored.receipt else None,
                "status": stored.status,
            },
        )

    def save_critique(self, record: JobRecord) -> None:
        stored = record.critique
        if stored is None or stored.result is None:
            return
        payload = {
            "model_id": stored.model_id,
            "execution_status": stored.status,
            "assessment": stored.result.model_dump(mode="json"),
        }
        self._write_json(record.job_id, "critique.json", payload)
        output_id = stored.result.generation_output_id
        self._write_json(record.job_id, f"critiques/{output_id}.json", payload)

    def save_repair(self, record: JobRecord) -> None:
        stored = record.repair
        if stored is None:
            return
        payload = {
            "status": stored.status,
            "plan": stored.plan.model_dump(mode="json"),
        }
        self._write_json(record.job_id, "repair.json", payload)
        count = stored.plan.repair_count
        name = f"repairs/{count}.json" if count else "repairs/hold.json"
        self._write_json(record.job_id, name, payload)
        for index, previous in enumerate(record.generation_history, start=1):
            self._write_json(
                record.job_id,
                f"generations/{index}.json",
                {
                    "operation": previous.operation.model_dump(mode="json"),
                    "receipt": previous.receipt.model_dump(mode="json")
                    if previous.receipt
                    else None,
                    "status": previous.status,
                },
            )
            if previous.receipt is not None and previous.receipt.output is not None:
                data = record.reference_bytes.get(previous.receipt.output.output_id)
                if data:
                    self.save_output(
                        record.job_id,
                        f"{previous.receipt.output.output_id}.{_MEDIA_EXT[previous.receipt.output.media_type]}",
                        data,
                    )

    def save_input(self, job_id: str, filename: str, data: bytes) -> None:
        path = self._resolve(job_id, "input", _safe_filename(filename))
        self._write_bytes(path, data)

    def save_output(self, job_id: str, filename: str, data: bytes) -> None:
        path = self._resolve(job_id, "output", _safe_filename(filename))
        self._write_bytes(path, data)

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


def output_filename(media_type: GeneratedMediaType) -> str:
    return f"generated.{_MEDIA_EXT[media_type]}"


def content_type_for(media_type: GeneratedMediaType) -> str:
    return _MEDIA_CONTENT_TYPE[media_type]


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
