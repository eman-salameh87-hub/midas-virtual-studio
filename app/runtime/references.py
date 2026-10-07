"""Intake of reference bytes for job create.

The frozen Phase-0 ReferenceAsset does not store bytes and does not compute
hashes. The HTTP create DTO may omit content_hash when content_base64 is
present. This module decodes those bytes, computes SHA-256 of the decoded
file (never of the base64 string), fills or verifies content_hash, then
validates the identity-only ReferenceAsset.
"""

from __future__ import annotations

import base64
import binascii
import hashlib

from app.contracts.job import Phase0JobContract
from app.contracts.reference import ReferenceAsset

IMAGE_MEDIA_TYPES = frozenset({"JPG", "PNG", "WebP"})


def decode_content_base64(value: str) -> bytes:
    compact = "".join(value.split())
    if not compact:
        raise ValueError("content_base64 must not be empty")
    try:
        raw = base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("content_base64 is not valid base64") from exc
    if not raw:
        raise ValueError("content_base64 must not be empty")
    return raw


def freeze_intake_payload(payload: dict[str, object]) -> tuple[Phase0JobContract, dict[str, bytes]]:
    """Validate a job-create contract dict, store bytes, freeze ReferenceAsset identity."""

    data = dict(payload)
    raw_refs = data.get("references")
    if not isinstance(raw_refs, list) or not raw_refs:
        return Phase0JobContract.model_validate(data), {}

    stored: dict[str, bytes] = {}
    frozen_refs: list[dict[str, object]] = []
    for index, raw in enumerate(raw_refs):
        if not isinstance(raw, dict):
            raise ValueError(f"references[{index}] must be an object")
        item = dict(raw)
        content_b64 = item.pop("content_base64", None)
        declared_hash = _optional_declared_hash(item.get("content_hash"))
        reference_id = item.get("reference_id")
        if content_b64 is not None:
            if not isinstance(content_b64, str):
                raise ValueError(
                    f"content_base64 for {reference_id!r} must be a string"
                )
            content = decode_content_base64(content_b64)
            digest = hashlib.sha256(content).hexdigest()
            if declared_hash is None:
                item["content_hash"] = digest
            elif declared_hash != digest:
                raise ValueError(
                    f"content_hash does not match content_base64 for {reference_id!r}"
                )
            identity = ReferenceAsset.model_validate(item)
            stored[identity.reference_id] = content
        else:
            if item.get("media_type") in IMAGE_MEDIA_TYPES:
                raise ValueError(
                    f"image reference {reference_id!r} requires content_base64"
                )
            identity = ReferenceAsset.model_validate(item)
        frozen_refs.append(identity.model_dump(mode="python"))

    data["references"] = frozen_refs
    return Phase0JobContract.model_validate(data), stored


def _optional_declared_hash(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("content_hash must be a string")
    stripped = value.strip()
    if not stripped:
        return None
    return stripped


def image_bytes_for_eye(
    references: list[ReferenceAsset],
    stored: dict[str, bytes],
) -> dict[str, bytes]:
    """Bytes OpenRouter Eye can send. Non-image media is not treated as Eye evidence."""

    images: dict[str, bytes] = {}
    for reference in references:
        if reference.media_type not in IMAGE_MEDIA_TYPES:
            continue
        content = stored.get(reference.reference_id)
        if content:
            images[reference.reference_id] = content
    return images
