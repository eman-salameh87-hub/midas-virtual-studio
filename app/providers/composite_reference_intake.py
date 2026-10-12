"""Route catalogue/spec intake to trusted metadata and images to vision.

Vision classification is injected. This router does not run Eye or Brain.
"""

from __future__ import annotations

from app.providers.fail_closed_reference_intake import FailClosedReferenceIntakeProvider
from app.providers.openrouter_image_classification import OpenRouterImageClassificationProvider
from app.providers.reference_intake import ReferenceIntakeProvider, ReferenceIntakeRequest, ReferenceIntakeResult


class CompositeReferenceIntakeProvider:
    def __init__(
        self,
        *,
        trusted: ReferenceIntakeProvider | None = None,
        vision: ReferenceIntakeProvider | None = None,
    ) -> None:
        self.trusted = trusted or FailClosedReferenceIntakeProvider()
        self.vision = vision or OpenRouterImageClassificationProvider()

    def analyze(self, request: ReferenceIntakeRequest) -> ReferenceIntakeResult:
        kind = (request.intended_kind or "").strip()
        if kind == "specification_file" or (request.library_key or "").strip():
            return self.trusted.analyze(request)
        return self.vision.analyze(request)
