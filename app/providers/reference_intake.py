"""Analyze a reference image for furniture relevance and taxonomy.

Production must not call OpenRouter from this module. Callers inject a provider.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.runtime.item_taxonomy import IMAGE_REFERENCE_TYPES, coerce_reference_type, resolve_taxonomy

NOT_FURNITURE_MESSAGE = (
    "This image is not recognized as relevant furniture, product, or interior "
    "reference material. Replace it with a product, room, or interior photo, "
    "or choose a Midas catalogue item."
)
UNCERTAIN_MESSAGE = (
    "This image could not be classified with certainty. Confirm that it is "
    "furniture, product, or interior reference material, or replace it."
)
PROVIDER_FAILED_MESSAGE = (
    "Image analysis failed. Retry or replace the image. It was not marked valid."
)


class ReferenceIntakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    library_key: str | None = None
    content_base64: str | None = None
    media_type: str | None = None
    intended_kind: str | None = None


class ReferenceIntakeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: str = Field(min_length=1)
    relevant: bool
    needs_confirmation: bool
    suggested_reference_type: str | None = None
    department: str | None = None
    category: str | None = None
    subcategory: str | None = None
    message: str = Field(min_length=1)

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        allowed = {"accepted", "rejected", "uncertain", "skipped"}
        if value not in allowed:
            raise ValueError("status must be accepted, rejected, uncertain, or skipped")
        return value

    @field_validator("suggested_reference_type")
    @classmethod
    def _type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        coerced = coerce_reference_type(value)
        if coerced is None:
            return None
        if coerced not in IMAGE_REFERENCE_TYPES and coerced != "specification_file":
            return None
        return coerced


class ReferenceIntakeProvider(Protocol):
    def analyze(self, request: ReferenceIntakeRequest) -> ReferenceIntakeResult: ...


def constrain_intake_result(result: ReferenceIntakeResult) -> ReferenceIntakeResult:
    department, category, subcategory = resolve_taxonomy(
        result.department, result.category, result.subcategory
    )
    suggested = coerce_reference_type(result.suggested_reference_type)
    if suggested and suggested not in IMAGE_REFERENCE_TYPES and suggested != "specification_file":
        suggested = None
    relevant = bool(result.relevant)
    status = result.status
    if status == "accepted" and not relevant:
        status = "rejected"
        suggested = None
        department = category = subcategory = None
    if status in {"rejected", "uncertain"}:
        relevant = False
        if status == "rejected":
            suggested = None
            department = category = subcategory = None
    return result.model_copy(
        update={
            "status": status,
            "relevant": relevant,
            "suggested_reference_type": suggested,
            "department": department,
            "category": category,
            "subcategory": subcategory,
        }
    )
