"""Development-only persist identity for UIMidas Manual briefs.

This is not production identity and is not derived from UIMidas
ownerIdentity / fileIds / limits placeholders (those stay null on the
envelope). Equivalence with the published Client Studio page is unverified.

Required:
- MIDAS_DEV_OWNER_ID
- MIDAS_DEV_CONTRACT_ID

Optional:
- MIDAS_DEV_CONTRACT_REVISION (default 1)

Values are read from the process environment. For local runs, python-dotenv
loads a repo-root `.env` the same way OpenRouter settings do. `.env.example`
is documentation only and is never loaded. Process environment wins over
`.env`. Missing or blank required values stay fail-closed.

Uniqueness of (contract_id, revision) is unresolved and is not enforced.
Each persist still allocates a new brief_id.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

DEV_OWNER_ID_ENV = "MIDAS_DEV_OWNER_ID"
DEV_CONTRACT_ID_ENV = "MIDAS_DEV_CONTRACT_ID"
DEV_REVISION_ENV = "MIDAS_DEV_CONTRACT_REVISION"
DEFAULT_DEV_REVISION = 1

IDENTITY_NOT_CONFIGURED = "IDENTITY_NOT_CONFIGURED"
INCOMPLETE_PERSIST_IDENTITY = "INCOMPLETE_PERSIST_IDENTITY"

IDENTITY_HELP = (
    "Development-only persist identity is not configured. Copy "
    ".env.example to .env in the repo root and set "
    f"{DEV_OWNER_ID_ENV} and {DEV_CONTRACT_ID_ENV}. "
    f"Optional {DEV_REVISION_ENV} defaults to {DEFAULT_DEV_REVISION}. "
    "This is not production identity. Do not use UIMidas ownerIdentity "
    "placeholders as owner_id."
)


class DevPersistIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    owner_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)


def _env_value(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def load_operator_dotenv(*, dotenv_path: str | Path | None = None) -> bool:
    """Load operator `.env` without overriding process environment.

    Same python-dotenv behavior as OpenRouter `load_settings`. Does not load
    `.env.example` and does not invent identity values.
    """

    if dotenv_path is None:
        return load_dotenv(override=False)
    return load_dotenv(dotenv_path, override=False)


def load_dev_persist_identity(
    *, dotenv_path: str | Path | None = None
) -> DevPersistIdentity | None:
    """Return configured development identity, or None if it is not set.

    Empty strings are treated as unset. Invalid revision is treated as unset
    so the API can return IDENTITY_NOT_CONFIGURED instead of guessing.
    """

    load_operator_dotenv(dotenv_path=dotenv_path)
    owner_id = _env_value(DEV_OWNER_ID_ENV)
    contract_id = _env_value(DEV_CONTRACT_ID_ENV)
    if owner_id is None or contract_id is None:
        return None
    revision_raw = _env_value(DEV_REVISION_ENV)
    if revision_raw is None:
        revision = DEFAULT_DEV_REVISION
    else:
        try:
            revision = int(revision_raw)
        except ValueError:
            return None
        if revision < 1:
            return None
    return DevPersistIdentity(
        owner_id=owner_id,
        contract_id=contract_id,
        revision=revision,
    )
