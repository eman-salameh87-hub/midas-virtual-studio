"""Persist local UIMidas ProposedJobContract payloads without creating a job.

Identity (not supplied by UIMidas):
- brief_id: server store key for one immutable persisted revision
- contract_id: Architecture A identity from the persist caller
- revision: Architecture A revision from the persist caller

Each persist writes outputs/<brief_id>/client_brief.json once. A later revision
must use a new brief_id. Uniqueness of (contract_id, revision) is unresolved
and is not enforced.

This store does not schedule planning and does not write a Phase-0 job
contract. Projects submit is a different shape and is not stored here.
"""

from __future__ import annotations

import json
import logging
import threading
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.contracts.client_brief import (
    ClientBriefRecord,
    ProposedJobContract,
    dump_omitting_optional_nones,
)
from app.runtime.artifacts import FilesystemArtifactStore, get_artifact_store, user_outputs_root

logger = logging.getLogger("app.runtime.client_briefs")

BRIEF_HASH_MISMATCH = "BRIEF_HASH_MISMATCH"
MALFORMED_BRIEF = "MALFORMED_BRIEF"
BRIEF_ID_MISMATCH = "BRIEF_ID_MISMATCH"


class ClientBriefNotFoundError(Exception):
    def __init__(self, brief_id: str) -> None:
        self.brief_id = brief_id
        super().__init__(brief_id)


class ClientBriefOwnerMismatchError(Exception):
    def __init__(self, brief_id: str, owner_id: str) -> None:
        self.brief_id = brief_id
        self.owner_id = owner_id
        super().__init__(brief_id)


class ClientBriefRevisionMismatchError(Exception):
    def __init__(self, brief_id: str, expected: int, actual: int) -> None:
        self.brief_id = brief_id
        self.expected = expected
        self.actual = actual
        super().__init__(brief_id)


class ClientBriefAlreadyPersistedError(Exception):
    def __init__(self, brief_id: str) -> None:
        self.brief_id = brief_id
        super().__init__(brief_id)


class ClientBriefRecoveryError(BaseModel):
    """Public recovery failure. Does not include file contents or hashes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    brief_id: str = Field(min_length=1)
    code: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class ClientBriefRecoveryResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recovered: list[str]
    errors: list[ClientBriefRecoveryError]


class InMemoryClientBriefStore:
    """Process-local ClientBriefRecord map. Not shared across processes."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._briefs: dict[str, ClientBriefRecord] = {}
        self.last_recovery: ClientBriefRecoveryResult | None = None

    def save(self, record: ClientBriefRecord) -> None:
        with self._lock:
            self._briefs[record.brief_id] = record

    def get(self, brief_id: str) -> ClientBriefRecord | None:
        with self._lock:
            return self._briefs.get(brief_id)

    def clear(self) -> None:
        with self._lock:
            self._briefs.clear()
            self.last_recovery = None


CLIENT_BRIEF_STORE = InMemoryClientBriefStore()


def persist_client_brief(record: ClientBriefRecord) -> None:
    artifacts = get_artifact_store()
    path = artifacts._resolve(record.brief_id, "client_brief.json")
    if path.is_file():
        raise ClientBriefAlreadyPersistedError(record.brief_id)
    payload = {
        "brief_id": record.brief_id,
        "owner_id": record.owner_id,
        "contract_id": record.contract_id,
        "revision": record.revision,
        "brief_hash": record.brief_hash,
        "client_brief": dump_omitting_optional_nones(record.client_brief),
    }
    artifacts._write_json(record.brief_id, "client_brief.json", payload)


def create_client_brief(
    store: InMemoryClientBriefStore,
    *,
    owner_id: str,
    contract_id: str,
    revision: int,
    client_brief: ProposedJobContract,
) -> ClientBriefRecord:
    record = ClientBriefRecord.model_validate(
        {
            "brief_id": str(uuid4()),
            "owner_id": owner_id,
            "contract_id": contract_id,
            "revision": revision,
            "client_brief": dump_omitting_optional_nones(client_brief),
        }
    )
    store.save(record)
    persist_client_brief(record)
    return record


def get_client_brief(
    store: InMemoryClientBriefStore,
    brief_id: str,
    *,
    owner_id: str | None = None,
    revision: int | None = None,
) -> ClientBriefRecord:
    record = store.get(brief_id)
    if record is None:
        raise ClientBriefNotFoundError(brief_id)
    if owner_id is not None and owner_id != record.owner_id:
        raise ClientBriefOwnerMismatchError(brief_id, owner_id)
    if revision is not None and revision != record.revision:
        raise ClientBriefRevisionMismatchError(brief_id, revision, record.revision)
    return record


def recover_client_briefs_from_artifacts(
    store: InMemoryClientBriefStore,
) -> ClientBriefRecoveryResult:
    """Load valid client_brief.json artifacts. Report corrupt records explicitly."""

    artifacts = FilesystemArtifactStore(user_outputs_root())
    recovered: list[str] = []
    errors: list[ClientBriefRecoveryError] = []
    root = artifacts.root
    if not root.exists() or not root.is_dir():
        result = ClientBriefRecoveryResult(recovered=recovered, errors=errors)
        store.last_recovery = result
        return result
    for path in sorted(root.iterdir()):
        if not path.is_dir():
            continue
        brief_path = path / "client_brief.json"
        if not brief_path.is_file():
            continue
        brief_id = path.name
        if store.get(brief_id) is not None:
            continue
        error = _load_persisted_brief(store, brief_id, brief_path)
        if error is None:
            recovered.append(brief_id)
            continue
        errors.append(error)
        logger.error(
            "client brief recovery failed brief_id=%s code=%s reason=%s",
            error.brief_id,
            error.code,
            error.reason,
        )
    result = ClientBriefRecoveryResult(recovered=recovered, errors=errors)
    store.last_recovery = result
    return result


def _load_persisted_brief(
    store: InMemoryClientBriefStore,
    brief_id: str,
    brief_path: object,
) -> ClientBriefRecoveryError | None:
    try:
        raw = json.loads(brief_path.read_text(encoding="utf-8"))  # type: ignore[union-attr]
    except (OSError, ValueError, TypeError):
        return ClientBriefRecoveryError(
            brief_id=brief_id,
            code=MALFORMED_BRIEF,
            reason="client_brief.json is not valid JSON",
        )
    if not isinstance(raw, dict):
        return ClientBriefRecoveryError(
            brief_id=brief_id,
            code=MALFORMED_BRIEF,
            reason="client_brief.json is not an object",
        )
    try:
        record = ClientBriefRecord.model_validate(raw)
    except ValidationError as exc:
        if _validation_is_hash_mismatch(exc):
            return ClientBriefRecoveryError(
                brief_id=brief_id,
                code=BRIEF_HASH_MISMATCH,
                reason="persisted brief_hash does not match the stored envelope",
            )
        return ClientBriefRecoveryError(
            brief_id=brief_id,
            code=MALFORMED_BRIEF,
            reason="persisted record failed schema validation",
        )
    except (ValueError, TypeError):
        return ClientBriefRecoveryError(
            brief_id=brief_id,
            code=MALFORMED_BRIEF,
            reason="persisted record failed schema validation",
        )
    if record.brief_id != brief_id:
        return ClientBriefRecoveryError(
            brief_id=brief_id,
            code=BRIEF_ID_MISMATCH,
            reason="brief_id in the file does not match the directory name",
        )
    store.save(record)
    return None


def _validation_is_hash_mismatch(exc: ValidationError) -> bool:
    return any(
        "brief_hash does not match the submitted client_brief" in error.get("msg", "")
        for error in exc.errors()
    )
