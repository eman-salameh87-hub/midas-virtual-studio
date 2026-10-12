"""Deterministic reference-intake fake. Tests inject outcomes. No network."""

from __future__ import annotations

from app.providers.reference_intake import (
    NOT_FURNITURE_MESSAGE,
    PROVIDER_FAILED_MESSAGE,
    UNCERTAIN_MESSAGE,
    ReferenceIntakeRequest,
    ReferenceIntakeResult,
    constrain_intake_result,
)


class FakeReferenceIntakeProvider:
    def __init__(
        self,
        outcome: str = "accepted",
        *,
        department: str | None = "home-furniture",
        category: str | None = "home-furniture/living-rooms",
        subcategory: str | None = "home-furniture/living-rooms/sofa",
        suggested_reference_type: str | None = "product_image",
        fail_with: BaseException | None = None,
        outcomes: list[str] | None = None,
    ) -> None:
        self.outcome = outcome
        self.department = department
        self.category = category
        self.subcategory = subcategory
        self.suggested_reference_type = suggested_reference_type
        self.fail_with = fail_with
        self._outcomes = list(outcomes or [])
        self.requests: list[ReferenceIntakeRequest] = []

    def analyze(self, request: ReferenceIntakeRequest) -> ReferenceIntakeResult:
        self.requests.append(request)
        if self.fail_with is not None:
            raise self.fail_with
        outcome = self._outcomes.pop(0) if self._outcomes else self.outcome
        if outcome == "error":
            raise RuntimeError(PROVIDER_FAILED_MESSAGE)
        if outcome == "rejected":
            return constrain_intake_result(
                ReferenceIntakeResult(
                    status="rejected",
                    relevant=False,
                    needs_confirmation=False,
                    suggested_reference_type=None,
                    department=None,
                    category=None,
                    subcategory=None,
                    message=NOT_FURNITURE_MESSAGE,
                )
            )
        if outcome == "uncertain":
            return constrain_intake_result(
                ReferenceIntakeResult(
                    status="uncertain",
                    relevant=False,
                    needs_confirmation=True,
                    suggested_reference_type=None,
                    department=None,
                    category=None,
                    subcategory=None,
                    message=UNCERTAIN_MESSAGE,
                )
            )
        if outcome == "skipped":
            return constrain_intake_result(
                ReferenceIntakeResult(
                    status="skipped",
                    relevant=True,
                    needs_confirmation=False,
                    suggested_reference_type="specification_file",
                    department=None,
                    category=None,
                    subcategory=None,
                    message="Specification files are not image-analyzed.",
                )
            )
        return constrain_intake_result(
            ReferenceIntakeResult(
                status="accepted",
                relevant=True,
                needs_confirmation=False,
                suggested_reference_type=self.suggested_reference_type,
                department=self.department,
                category=self.category,
                subcategory=self.subcategory,
                message="Recognized as furniture or interior product reference material.",
            )
        )
