"""Reference image intake analysis. Fake provider only. No OpenRouter."""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from app.api.reference_intake import get_reference_intake_provider
from app.main import app
from app.providers.fake_reference_intake import FakeReferenceIntakeProvider
from app.providers.fail_closed_reference_intake import FailClosedReferenceIntakeProvider
from app.providers.reference_intake import (
    NOT_FURNITURE_MESSAGE,
    ReferenceIntakeRequest,
    constrain_intake_result,
)
from app.runtime.item_taxonomy import match_taxonomy
from tests.png_bytes import PNG_1X1


def _client() -> TestClient:
    return TestClient(app)


def test_fake_accepts_furniture_and_constrains_taxonomy() -> None:
    provider = FakeReferenceIntakeProvider(
        department="home-furniture",
        category="home-furniture/living-rooms",
        subcategory="not-a-real-sub",
    )
    result = provider.analyze(ReferenceIntakeRequest(content_base64=base64.b64encode(PNG_1X1).decode()))
    assert result.status == "accepted"
    assert result.relevant is True
    assert result.department == "home-furniture"
    assert result.category == "home-furniture/living-rooms"
    assert result.subcategory is None
    assert result.suggested_reference_type == "product_image"


def test_fake_rejects_non_furniture() -> None:
    provider = FakeReferenceIntakeProvider(outcome="rejected")
    result = provider.analyze(ReferenceIntakeRequest(content_base64="aaaa"))
    assert result.status == "rejected"
    assert result.relevant is False
    assert result.suggested_reference_type is None
    assert "not recognized" in result.message


def test_fake_uncertain_does_not_accept() -> None:
    provider = FakeReferenceIntakeProvider(outcome="uncertain")
    result = provider.analyze(ReferenceIntakeRequest(content_base64="aaaa"))
    assert result.status == "uncertain"
    assert result.relevant is False
    assert result.needs_confirmation is True


def test_accepted_without_relevance_is_rejected() -> None:
    from app.providers.reference_intake import ReferenceIntakeResult

    constrained = constrain_intake_result(
        ReferenceIntakeResult(
            status="accepted",
            relevant=False,
            needs_confirmation=False,
            suggested_reference_type="product_image",
            department="home-furniture",
            category="home-furniture/living-rooms",
            subcategory=None,
            message="ok",
        )
    )
    assert constrained.status == "rejected"
    assert constrained.relevant is False
    assert constrained.department is None


def test_api_uses_injected_fake_and_redacts_provider_errors() -> None:
    app.dependency_overrides[get_reference_intake_provider] = lambda: FakeReferenceIntakeProvider(
        fail_with=RuntimeError("secret leaked OpenRouter HTTP 401")
    )
    try:
        response = _client().post(
            "/api/v1/reference-intake/analyze",
            json={"content_base64": base64.b64encode(PNG_1X1).decode()},
        )
    finally:
        app.dependency_overrides.pop(get_reference_intake_provider, None)
    assert response.status_code == 502
    body = response.json()["error"]
    assert body["code"] == "PROVIDER_FAILURE"
    assert "secret" not in body["message"].lower()
    assert "secret" not in str(body["details"]).lower()


def test_api_accepted_furniture() -> None:
    app.dependency_overrides[get_reference_intake_provider] = lambda: FakeReferenceIntakeProvider()
    try:
        response = _client().post(
            "/api/v1/reference-intake/analyze",
            json={"content_base64": base64.b64encode(PNG_1X1).decode()},
        )
    finally:
        app.dependency_overrides.pop(get_reference_intake_provider, None)
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["status"] == "accepted"
    assert result["department"] == "home-furniture"


def test_fail_closed_catalogue_is_product_reference() -> None:
    provider = FailClosedReferenceIntakeProvider()
    result = provider.analyze(ReferenceIntakeRequest(library_key="165931"))
    assert result.status == "accepted"
    assert result.relevant is True
    assert result.suggested_reference_type == "product_image"
    assert result.department == "home-furniture"
    assert result.category == "home-furniture/dining-rooms"


def test_fail_closed_local_image_is_uncertain_not_accepted() -> None:
    provider = FailClosedReferenceIntakeProvider()
    result = provider.analyze(
        ReferenceIntakeRequest(content_base64=base64.b64encode(PNG_1X1).decode())
    )
    assert result.status == "uncertain"
    assert result.relevant is False
    assert result.needs_confirmation is True


def test_fail_closed_garbage_bytes_rejected() -> None:
    provider = FailClosedReferenceIntakeProvider()
    result = provider.analyze(ReferenceIntakeRequest(content_base64="not-an-image"))
    assert result.status == "rejected"
    assert result.message == NOT_FURNITURE_MESSAGE


def test_taxonomy_match_uses_existing_dining_rooms() -> None:
    department, category, subcategory = match_taxonomy(
        "ABALI DINING TABLE- WHITE",
        "https://midasfurniture.com/qtr_en/abali-dining-table-dining-rooms-midas.html",
    )
    assert department == "home-furniture"
    assert category == "home-furniture/dining-rooms"
