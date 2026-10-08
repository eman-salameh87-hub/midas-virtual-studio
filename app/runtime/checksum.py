"""Checksum comparison for persisted image bytes.

The stored SHA-256 is never replaced. A mismatch is evidence, not a rewrite
and not a reason to call a provider.
"""

from __future__ import annotations

import hashlib

from app.runtime.state import StoredGeneration


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def annotate_checksum(stored: StoredGeneration, data: bytes | None) -> StoredGeneration:
    """Compare bytes with the receipt hash. The receipt hash stays as stored."""

    receipt = stored.receipt
    if data is None or receipt is None or receipt.output is None:
        return stored
    observed = sha256_hex(data)
    status = "matched" if observed == receipt.output.content_hash else "mismatch"
    return stored.model_copy(
        update={"checksum_status": status, "observed_checksum": observed}
    )
