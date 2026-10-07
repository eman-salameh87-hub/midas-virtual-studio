"""Deterministic Eye provider for local tests.

It does not call a network and does not choose a model. The observation is
built from the EyeInput's contract id, revision, and reference identity.
"""

from typing import Literal

from app.contracts.eye import EyeInput, EyeObservation, EyeSource
from app.providers.eye import EyeProviderRequest

ObservationKind = Literal[
    "ready",
    "ready_with_unknown",
    "critical_identity_ambiguity",
    "unresolved_identity",
    "conflicting_critical_evidence",
]

_PREVIOUS_RESULT_ROLES = {"Previous result", "previous_result"}


class FakeEyeProvider:
    """In-memory provider. `requests` records exactly what the caller passed."""

    def __init__(self, kind: ObservationKind = "ready") -> None:
        self.kind: ObservationKind = kind
        self.requests: list[EyeProviderRequest] = []

    def observe(self, request: EyeProviderRequest) -> EyeObservation:
        self.requests.append(request)
        return observation_for(request.eye_input, self.kind)


def observation_for(eye_input: EyeInput, kind: ObservationKind) -> EyeObservation:
    """Build one valid observation bound to this EyeInput."""

    reference = _evidence_reference(eye_input)
    count_status = "unresolved" if kind == "unresolved_identity" else "observed"
    count_value = None if count_status == "unresolved" else 1
    ambiguities: list[dict[str, object]] = []
    conflicts: list[dict[str, object]] = []
    unknowns: list[dict[str, object]] = []
    if kind == "critical_identity_ambiguity":
        ambiguities.append(
            {
                "subject": "product identity",
                "hypotheses": ["first reading", "second reading"],
                "status": "unresolved",
                "resolution": None,
            }
        )
    if kind == "conflicting_critical_evidence":
        conflicts.append(
            {
                "subject": "product identity",
                "claims": ["the reference shows one item", "the reference shows two items"],
                "evidence_reference_ids": [reference.reference_id],
            }
        )
    if kind in {"ready", "ready_with_unknown"}:
        conflicts.append(
            {
                "subject": "colour",
                "claims": ["the photo reads darker", "a swatch reads lighter"],
                "evidence_reference_ids": [reference.reference_id],
            }
        )
    if kind == "ready_with_unknown":
        unknowns.append(
            {
                "subject": "fibre composition",
                "detail": "visible texture does not prove fibre composition",
                "evidence_reference_id": reference.reference_id,
            }
        )
    return EyeObservation.model_validate(
        {
            "contract_id": eye_input.contract_id,
            "revision": eye_input.revision,
            "category_candidates": [
                {
                    "label": "visible product",
                    "confidence_basis": "deterministic fake observation, not a model reading",
                    "evidence_reference_id": reference.reference_id,
                    "content_hash": reference.content_hash,
                }
            ],
            "items": [
                {
                    "name": "visible item",
                    "item_kind": "item",
                    "count": {"status": count_status, "value": count_value},
                    "visible_features": ["outline"],
                    "identified_from": "visible content",
                    "evidence_reference_id": reference.reference_id,
                    "content_hash": reference.content_hash,
                }
            ],
            "facts": [
                {
                    "subject": "outline",
                    "value": "the outline is visible",
                    "basis": "observed",
                    "evidence_reference_id": reference.reference_id,
                    "content_hash": reference.content_hash,
                }
            ],
            "unknowns": unknowns,
            "ambiguities": ambiguities,
            "conflicts": conflicts,
            "parsing_limitations": [],
            "relations": [],
            "regions": [],
            "signals": [],
            "shown_views": [],
            "change_log": [],
        }
    )


def _evidence_reference(eye_input: EyeInput) -> EyeSource:
    for reference in eye_input.references:
        if reference.role not in _PREVIOUS_RESULT_ROLES:
            return reference
    raise ValueError(
        "the fake Eye provider needs a selected reference that is not a previous result"
    )
