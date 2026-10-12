"""Standalone OpenRouter image classification. Mocked chat only. No Eye stage."""

from __future__ import annotations

import base64

import pytest

from fastapi.testclient import TestClient

from app.api.reference_intake import get_reference_intake_provider
from app.main import app
from app.providers.composite_reference_intake import CompositeReferenceIntakeProvider
from app.providers.fail_closed_reference_intake import FailClosedReferenceIntakeProvider
from app.providers.fake_reference_intake import FakeReferenceIntakeProvider
from app.providers.image_classification import map_classification_payload
from app.providers.openrouter import OpenRouterCallRecord, OpenRouterSettings
from app.providers.openrouter_image_classification import OpenRouterImageClassificationProvider
from app.providers.reference_intake import NOT_FURNITURE_MESSAGE, ReferenceIntakeRequest
from app.runtime.artifacts import user_outputs_root
from app.runtime.model_policy import eye_model
from app.runtime.job import execute_eye_job
from tests.png_bytes import PNG_1X1

_B64 = base64.b64encode(PNG_1X1).decode()


class _Chat:
    def __init__(self, payload: object | None = None, error: BaseException | None = None) -> None:
        self.payload = payload
        self.error = error
        self.bodies: list[dict] = []

    def __call__(self, settings: OpenRouterSettings, body: dict, record: OpenRouterCallRecord) -> dict:
        self.bodies.append(body)
        if self.error is not None:
            raise self.error
        assert isinstance(self.payload, dict)
        return self.payload


def _settings() -> OpenRouterSettings:
    return OpenRouterSettings(api_key="test-key", base_url="https://openrouter.ai/api/v1", timeout_seconds=5)


def _furniture_payload(**overrides: object) -> dict:
    payload = {
        "relevant": True,
        "status": "accepted",
        "needs_confirmation": False,
        "department": "home-furniture",
        "category": "home-furniture/living-rooms",
        "subcategory": "home-furniture/living-rooms/sofa",
        "suggested_reference_type": "product_image",
        "message": "Sofa product photograph.",
    }
    payload.update(overrides)
    return payload


def test_valid_furniture_uses_existing_taxonomy_only() -> None:
    chat = _Chat(_furniture_payload(subcategory="invented-sub"))
    provider = OpenRouterImageClassificationProvider(settings=_settings(), complete=chat)
    result = provider.analyze(ReferenceIntakeRequest(content_base64=_B64, media_type="image/png"))
    assert result.status == "accepted"
    assert result.relevant is True
    assert result.department == "home-furniture"
    assert result.category == "home-furniture/living-rooms"
    assert result.subcategory is None
    assert result.suggested_reference_type == "product_image"
    assert chat.bodies[0]["model"] == eye_model()
    content = chat.bodies[0]["messages"][1]["content"]
    assert any(part.get("type") == "image_url" for part in content)


def test_out_of_scope_image_is_rejected() -> None:
    chat = _Chat(
        {
            "relevant": False,
            "status": "accepted",
            "needs_confirmation": False,
            "department": "home-furniture",
            "category": "home-furniture/living-rooms",
            "subcategory": None,
            "suggested_reference_type": "product_image",
            "message": "A highway landscape.",
        }
    )
    provider = OpenRouterImageClassificationProvider(settings=_settings(), complete=chat)
    result = provider.analyze(ReferenceIntakeRequest(content_base64=_B64))
    assert result.status == "rejected"
    assert result.relevant is False
    assert result.department is None
    assert result.suggested_reference_type is None
    assert result.message == NOT_FURNITURE_MESSAGE


def test_uncertain_and_malformed_and_provider_failure_block() -> None:
    uncertain = OpenRouterImageClassificationProvider(
        settings=_settings(),
        complete=_Chat(_furniture_payload(status="uncertain", needs_confirmation=True, relevant=True)),
    ).analyze(ReferenceIntakeRequest(content_base64=_B64))
    assert uncertain.status == "uncertain"
    assert uncertain.relevant is False
    assert uncertain.needs_confirmation is True

    with pytest.raises(ValueError):
        map_classification_payload({"relevant": "yes"})

    with pytest.raises(RuntimeError, match="timed out"):
        OpenRouterImageClassificationProvider(
            settings=_settings(),
            complete=_Chat(error=RuntimeError("OpenRouter timed out")),
        ).analyze(ReferenceIntakeRequest(content_base64=_B64))


def test_classification_does_not_invoke_eye_or_brain(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def _eye(*_args: object, **_kwargs: object) -> None:
        calls.append("eye")
        raise AssertionError("Eye must not run during classification")

    def _job(*_args: object, **_kwargs: object) -> None:
        calls.append("execute_eye")
        raise AssertionError("execute_eye_job must not run")

    monkeypatch.setattr("app.providers.openrouter.OpenRouterEyeProvider.observe", _eye)
    monkeypatch.setattr("app.runtime.job.execute_eye_job", _job)
    monkeypatch.setattr("app.providers.fake_brain.FakeBrainProvider.reason", lambda *_a, **_k: calls.append("brain"))
    chat = _Chat(_furniture_payload())
    provider = OpenRouterImageClassificationProvider(settings=_settings(), complete=chat)
    result = provider.analyze(ReferenceIntakeRequest(content_base64=_B64))
    assert result.status == "accepted"
    assert calls == []
    system = chat.bodies[0]["messages"][0]["content"]
    assert "living room standing" not in system.casefold()
    assert execute_eye_job is not None


def test_catalogue_uses_trusted_metadata_without_vision() -> None:
    chat = _Chat(_furniture_payload())
    vision = OpenRouterImageClassificationProvider(settings=_settings(), complete=chat)
    provider = CompositeReferenceIntakeProvider(
        trusted=FailClosedReferenceIntakeProvider(),
        vision=vision,
    )
    result = provider.analyze(ReferenceIntakeRequest(library_key="165931"))
    assert result.status == "accepted"
    assert result.suggested_reference_type == "product_image"
    assert result.department == "home-furniture"
    assert chat.bodies == []


def test_excel_skips_vision() -> None:
    chat = _Chat(_furniture_payload())
    provider = CompositeReferenceIntakeProvider(
        trusted=FailClosedReferenceIntakeProvider(),
        vision=OpenRouterImageClassificationProvider(settings=_settings(), complete=chat),
    )
    result = provider.analyze(ReferenceIntakeRequest(intended_kind="specification_file", content_base64="aaaa"))
    assert result.status == "skipped"
    assert result.suggested_reference_type == "specification_file"
    assert chat.bodies == []


def test_api_rejects_out_of_scope_and_does_not_write_outputs() -> None:
    root = user_outputs_root()
    before = {path.name for path in root.iterdir()} if root.exists() else set()
    app.dependency_overrides[get_reference_intake_provider] = lambda: FakeReferenceIntakeProvider(outcome="rejected")
    try:
        response = TestClient(app).post(
            "/api/v1/reference-intake/analyze",
            json={"content_base64": _B64},
        )
    finally:
        app.dependency_overrides.pop(get_reference_intake_provider, None)
    assert response.status_code == 200
    body = response.json()["result"]
    assert body["status"] == "rejected"
    assert body["relevant"] is False
    after = {path.name for path in root.iterdir()} if root.exists() else set()
    assert after == before


def test_label_payload_maps_to_existing_ids() -> None:
    from app.providers.image_classification import map_classification_payload

    result = map_classification_payload(
        {
            "relevant": True,
            "status": "accepted",
            "needs_confirmation": False,
            "department": "Home Furniture",
            "category": "Living Rooms",
            "subcategory": "Sofas",
            "suggested_reference_type": "Product / vendor reference",
            "message": "Sofa product photograph.",
        }
    )
    assert result.status == "accepted"
    assert result.department == "home-furniture"
    assert result.category == "home-furniture/living-rooms"
    assert result.subcategory == "home-furniture/living-rooms/sofa"
    assert result.suggested_reference_type == "product_image"


def test_classification_reuses_eye_model_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MIDAS_EYE_MODEL", "openai/gpt-4.1")
    chat = _Chat(_furniture_payload())
    provider = OpenRouterImageClassificationProvider(settings=_settings(), complete=chat)
    assert provider.model_id == "openai/gpt-4.1"
    provider.analyze(ReferenceIntakeRequest(content_base64=_B64))
    assert chat.bodies[0]["model"] == "openai/gpt-4.1"
