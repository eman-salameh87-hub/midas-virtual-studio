"""Map Brain grounding evidence IDs without inventing them.

observed/published claims need a supplied evidence reference_id. A missing ID
is an unsupported claim and is omitted. An ID that is not in the supplied
evidence is left unchanged so later validation can fail clearly.
"""

from __future__ import annotations

from typing import Any

_OBSERVED = frozenset({"observed", "published"})


def supplied_evidence_ids(evidence: list[Any]) -> frozenset[str]:
    return frozenset(
        item.reference_id
        for item in evidence
        if getattr(item, "reference_id", None)
    )


def apply_brain_grounding_evidence(
    payload: dict[str, Any],
    allowed_ids: frozenset[str] | set[str],
) -> dict[str, Any]:
    """Drop observed/published grounding that has no evidence reference.

    Does not invent, guess, or replace an evidence_reference_id.
    """

    grounding = payload.get("grounding")
    if not isinstance(grounding, list):
        return payload
    kept: list[Any] = []
    for item in grounding:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        basis = item.get("basis")
        ref = item.get("evidence_reference_id")
        if basis in _OBSERVED and not _stated_id(ref):
            continue
        kept.append(item)
    updated = dict(payload)
    updated["grounding"] = kept
    return updated


def _stated_id(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
