"""Map a vision-model JSON object onto the reference-intake result.

This module does not call Eye, Brain, Stylist, or OpenRouter.
"""

from __future__ import annotations

from typing import Any

from app.providers.reference_intake import (
    NOT_FURNITURE_MESSAGE,
    UNCERTAIN_MESSAGE,
    ReferenceIntakeResult,
    constrain_intake_result,
)
from app.runtime.item_taxonomy import IMAGE_REFERENCE_TYPES, coerce_reference_type

_STATUSES = {"accepted", "rejected", "uncertain"}


def map_classification_payload(payload: object) -> ReferenceIntakeResult:
    if not isinstance(payload, dict):
        raise ValueError("classification payload was not an object")
    relevant = payload.get("relevant")
    if not isinstance(relevant, bool):
        raise ValueError("classification payload missing relevant boolean")
    status = payload.get("status")
    if status is not None and status not in _STATUSES:
        raise ValueError("classification status is not accepted, rejected, or uncertain")
    needs = payload.get("needs_confirmation")
    if needs is not None and not isinstance(needs, bool):
        raise ValueError("classification needs_confirmation must be a boolean")
    suggested = payload.get("suggested_reference_type")
    if suggested == "":
        suggested = None
    if suggested is not None and not isinstance(suggested, str):
        raise ValueError("suggested_reference_type must be a string or null")
    if isinstance(suggested, str):
        suggested = coerce_reference_type(suggested)
    if suggested == "specification_file":
        suggested = None
    if suggested is not None and suggested not in IMAGE_REFERENCE_TYPES:
        suggested = None
    message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        message = NOT_FURNITURE_MESSAGE if not relevant else UNCERTAIN_MESSAGE
    derived = _derive_status(relevant, status, bool(needs) if isinstance(needs, bool) else False)
    department = _optional_id(payload.get("department"))
    category = _optional_id(payload.get("category"))
    subcategory = _optional_id(payload.get("subcategory"))
    if derived != "accepted":
        if derived == "rejected":
            suggested = None
            department = category = subcategory = None
        relevant = False
    result = ReferenceIntakeResult(
        status=derived,
        relevant=derived == "accepted",
        needs_confirmation=derived == "uncertain",
        suggested_reference_type=suggested if derived == "accepted" else None,
        department=department if derived == "accepted" else None,
        category=category if derived == "accepted" else None,
        subcategory=subcategory if derived == "accepted" else None,
        message=message.strip() if derived != "rejected" else NOT_FURNITURE_MESSAGE,
    )
    constrained = constrain_intake_result(result)
    if constrained.status == "accepted" and not constrained.department:
        return constrain_intake_result(
            ReferenceIntakeResult(
                status="uncertain",
                relevant=False,
                needs_confirmation=True,
                suggested_reference_type=constrained.suggested_reference_type,
                department=None,
                category=None,
                subcategory=None,
                message=UNCERTAIN_MESSAGE,
            )
        )
    return constrained


def _derive_status(relevant: bool, status: object, needs_confirmation: bool) -> str:
    if not relevant:
        return "rejected"
    if needs_confirmation:
        return "uncertain"
    if status is None:
        return "accepted"
    if status == "accepted":
        return "accepted"
    if status == "uncertain":
        return "uncertain"
    return "rejected"


def _optional_id(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()
