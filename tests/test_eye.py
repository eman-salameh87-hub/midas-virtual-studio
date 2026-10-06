import base64
import inspect
import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.providers.openrouter as openrouter
import app.runtime.job as job_runtime
import app.stages.eye as eye_stage
from app.api.jobs import get_eye_provider
from app.contracts.eye import EyeObservation, OriginalProductImage
from app.contracts.job import validate_phase0
from app.main import app
from app.runtime.job import execute_job, inspect_readiness, reset_jobs
from app.stages.eye import EyeStageError, run_eye

TEMPORARY_LIVE_MODEL_ID = "openai/gpt-4.1"


def setup_function() -> None:
    reset_jobs()
    app.dependency_overrides.clear()


def teardown_function() -> None:
    reset_jobs()
    app.dependency_overrides.clear()


def sample_contract() -> dict[str, object]:
    return {
        "taxonomy_node_id": "node-1",
        "profile_id": "profile-1",
        "product_role": "hero",
        "references": [
            {
                "id": "ref-1",
                "role": "product",
                "filename": "product.png",
                "media_type": "image/png",
            }
        ],
        "lighting": "soft",
        "wall_paint": "white",
        "floor": "oak",
        "mood": "calm",
        "plants": False,
        "human": False,
        "input_condition": "as-supplied",
    }


def image_b64() -> str:
    return base64.b64encode(b"original-product-image").decode("ascii")


def observation_payload(source_role: str) -> dict[str, object]:
    return {
        "source_role": source_role,
        "category_candidates": [
            {"name": "candidate", "confidence_basis": "visible shape"},
        ],
        "visible_features": ["a single object"],
        "observed_facts": [f"observed for {source_role}"],
        "unknowns": ["material is not stated"],
        "ambiguities": [],
        "conflicts": [],
        "parsing_limits": [],
    }


class RecordingProvider:
    def __init__(self, payload: dict[str, object] | None = None) -> None:
        self.payload = payload
        self.model_ids: list[str] = []
        self.messages: list[list[dict[str, object]]] = []

    def complete(
        self,
        *,
        model_id: str,
        messages: list[dict[str, object]],
        response_schema: dict[str, object],
    ) -> dict[str, object]:
        self.model_ids.append(model_id)
        self.messages.append(messages)
        if self.payload is not None:
            return self.payload
        role = json.loads(messages[0]["content"][0]["text"])["source_role"]
        return observation_payload(role)


def test_valid_phase0_job() -> None:
    job = validate_phase0(sample_contract())

    assert job.taxonomy_node_id == "node-1"
    assert job.profile_id == "profile-1"
    assert job.product_role == "hero"
    assert job.references[0].id == "ref-1"
    assert job.lighting == "soft"
    assert job.wall_paint == "white"
    assert job.floor == "oak"
    assert job.mood == "calm"
    assert job.plants is False
    assert job.human is False
    assert job.input_condition == "as-supplied"

    with pytest.raises(ValidationError):
        validate_phase0({**sample_contract(), "category": "not-a-phase0-field"})


def test_eye_stage_receives_explicit_model_id() -> None:
    parameter = inspect.signature(run_eye).parameters["model_id"]
    assert parameter.default is inspect.Parameter.empty

    provider = RecordingProvider(observation_payload("product-photo"))
    image = OriginalProductImage(
        media_type="image/png",
        content=b"original-product-image",
        source_role="product-photo",
    )

    run_eye(image=image, model_id=TEMPORARY_LIVE_MODEL_ID, provider=provider)

    assert provider.model_ids == [TEMPORARY_LIVE_MODEL_ID]
    assert provider.messages[0][0]["role"] == "user"
    assert "image/png" in provider.messages[0][0]["content"][1]["image_url"]["url"]
    assert all(message["role"] != "system" for message in provider.messages[0])

    rejected = RecordingProvider(observation_payload("product-photo"))
    with pytest.raises(EyeStageError):
        run_eye(image=image, model_id="  ", provider=rejected)
    assert rejected.model_ids == []


def test_eye_result_becomes_eye_observation() -> None:
    provider = RecordingProvider(observation_payload("product-photo"))
    image = OriginalProductImage(
        media_type="image/png",
        content=b"original-product-image",
        source_role="product-photo",
    )

    observation = run_eye(image=image, model_id="caller/explicit-model", provider=provider)

    assert isinstance(observation, EyeObservation)
    assert observation.source_role == "product-photo"
    assert observation.category_candidates[0].name == "candidate"
    assert observation.visible_features == ["a single object"]
    assert observation.observed_facts == ["observed for product-photo"]
    assert observation.unknowns == ["material is not stated"]
    assert observation.ambiguities == []
    assert observation.conflicts == []
    assert observation.parsing_limits == []


def test_eye_observation_attached_to_correct_job() -> None:
    provider = RecordingProvider()
    app.dependency_overrides[get_eye_provider] = lambda: provider
    client = TestClient(app)

    first = client.post(
        "/jobs",
        json=_request(model_id=TEMPORARY_LIVE_MODEL_ID, source_role="role-a"),
    )
    second = client.post(
        "/jobs",
        json=_request(model_id="caller/other-model", source_role="role-b"),
    )

    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body["job_id"] != second_body["job_id"]

    loaded_first = client.get(f"/jobs/{first_body['job_id']}")
    loaded_second = client.get(f"/jobs/{second_body['job_id']}")

    assert loaded_first.json()["eye_observation"]["source_role"] == "role-a"
    assert loaded_first.json()["eye_observation"]["observed_facts"] == ["observed for role-a"]
    assert loaded_second.json()["eye_observation"]["source_role"] == "role-b"
    assert loaded_second.json()["eye_observation"]["observed_facts"] == ["observed for role-b"]
    assert provider.model_ids == [TEMPORARY_LIVE_MODEL_ID, "caller/other-model"]


def test_readiness_inspects_job_eye_result() -> None:
    provider = RecordingProvider()
    record = execute_job(
        job=sample_contract(),
        media_type="image/png",
        data_base64=image_b64(),
        source_role="role-a",
        model_id=TEMPORARY_LIVE_MODEL_ID,
        provider=provider,
    )

    readiness = inspect_readiness(record.job_id)

    assert readiness.job_id == record.job_id
    assert readiness.status == "eye_complete"
    assert readiness.eye_ready is True
    assert readiness.eye_observation is not None
    assert readiness.eye_observation.observed_facts == ["observed for role-a"]
    assert readiness.eye_observation.category_candidates[0].confidence_basis == "visible shape"


def test_no_model_selection_code_is_called(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_called(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("model selection code was called")

    monkeypatch.setattr(job_runtime, "select_model", fail_if_called, raising=False)
    monkeypatch.setattr(eye_stage, "select_model", fail_if_called, raising=False)
    monkeypatch.setattr(openrouter, "select_model", fail_if_called, raising=False)

    provider = RecordingProvider(observation_payload("product-photo"))
    record = execute_job(
        job=sample_contract(),
        media_type="image/png",
        data_base64=image_b64(),
        source_role="product-photo",
        model_id="caller/explicit-model",
        provider=provider,
    )

    assert provider.model_ids == ["caller/explicit-model"]
    assert record.model_id == "caller/explicit-model"
    assert inspect_readiness(record.job_id).model_id == "caller/explicit-model"
    for module in (job_runtime, eye_stage, openrouter):
        source = inspect.getsource(module)
        assert "select_model" not in source
        assert "choose_model" not in source
        assert "resolve_model" not in source
        assert "OPENROUTER_MODEL" not in source


def _request(*, model_id: str, source_role: str) -> dict[str, object]:
    return {
        "model_id": model_id,
        "original_product_image": {
            "media_type": "image/png",
            "data_base64": image_b64(),
            "source_role": source_role,
        },
        "job": sample_contract(),
    }
