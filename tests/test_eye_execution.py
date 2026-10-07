import inspect

import httpx
import pytest
from fastapi.testclient import TestClient

from app.contracts.job import Phase0JobContract
from app.main import app
from app.providers.fake_eye import FakeEyeProvider
from app.runtime.job import execute_eye_job
from app.stages.eye import build_eye_input
from tests.png_bytes import PNG_B64, PNG_HASH

HASH = "ab" * 32
CALLER_MODEL = "caller-supplied-model"


def _contract() -> Phase0JobContract:
    return Phase0JobContract.model_validate(
        {
            "contract_id": "contract-towel-1",
            "revision": 2,
            "owner_id": "owner-1",
            "intent": {
                "mode": "Manual",
                "job_type": "New Project",
                "job_option": "One by one (same department)",
                "requested_outcomes": ["Lifestyle"],
                "other_outcome": None,
                "requested_pieces": ["towel"],
                "excluded_pieces": [],
                "selected_count": {"status": "declared", "value": 1},
            },
            "item": {
                "department": "Accessories",
                "category": "Bathroom",
                "subcategory": "Towels",
                "product_role": "hero",
            },
            "source_condition": {"input_condition": "annotated multi-view sheet"},
            "references": [
                {
                    "reference_id": "ref-towel",
                    "filename": "towel-sheet.jpg",
                    "media_type": "JPG",
                    "hash_algorithm": "sha256",
                    "content_hash": HASH,
                    "role": "Product / vendor reference",
                }
            ],
            "outputs": {
                "views": ["Wide view"],
                "image_proportions": "Square · 1:1",
                "resolution": "2K",
                "package_members": ["lifestyle"],
            },
            "changes": {
                "policy_mode": "fidelity-locked",
                "allowed_changes": ["styled setting"],
                "protected_identity": ["towel count"],
                "room_locks": [],
                "creative_variables": [],
            },
            "preferences": {
                "lighting": "Soft daylight",
                "wall": "Sage",
                "floor": "Limestone",
                "plants": False,
                "human": False,
                "mood": "Calm & natural",
            },
            "statements": [],
            "unknowns": [],
            "conflicts": [],
        }
    )


def _run(kind: str = "ready", messages: list[str] | None = None):
    provider = FakeEyeProvider(kind)  # type: ignore[arg-type]
    result = execute_eye_job(
        contract=_contract(),
        reference_ids=["ref-towel"],
        model_id=CALLER_MODEL,
        messages=[] if messages is None else messages,
        provider=provider,
    )
    return provider, result


def test_job_contract_builds_eye_input_with_identity_and_hash() -> None:
    contract = _contract()
    eye_input = build_eye_input(contract, ["ref-towel"])

    assert eye_input.contract_id == contract.contract_id
    assert eye_input.revision == contract.revision
    source = eye_input.references[0]
    original = contract.references[0]
    assert source.reference_id == original.reference_id
    assert source.filename == original.filename
    assert source.media_type == original.media_type
    assert source.content_hash == original.content_hash == HASH
    assert source.role == original.role
    assert source.role_vocabulary == "create-page"
    assert contract.revision == 2


def test_fake_provider_observation_stays_bound_to_the_job() -> None:
    provider, result = _run()

    assert result.observation.contract_id == "contract-towel-1"
    assert result.observation.revision == 2
    assert result.observation.items[0].evidence_reference_id == "ref-towel"
    assert result.observation.items[0].content_hash == HASH
    assert provider.requests[0].eye_input.revision == 2
    assert result.readiness.status == "ready"
    assert result.readiness.reasons == []


def test_critical_identity_ambiguity_and_conflict_hold() -> None:
    _, ambiguity = _run("critical_identity_ambiguity")
    assert ambiguity.readiness.status == "hold"
    assert ambiguity.readiness.reasons == ["critical identity ambiguity"]

    _, unresolved = _run("unresolved_identity")
    assert unresolved.readiness.status == "hold"
    assert unresolved.readiness.reasons == ["unresolved identity"]

    _, conflict = _run("conflicting_critical_evidence")
    assert conflict.readiness.status == "hold"
    assert conflict.readiness.reasons == ["conflicting critical evidence"]


def test_colour_conflict_stays_ready() -> None:
    _, result = _run("ready")
    assert result.observation.conflicts[0].subject == "colour"
    assert result.readiness.status == "ready"


def test_caller_model_and_messages_are_not_replaced(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_request(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("an HTTP client was used")

    monkeypatch.setattr(httpx.Client, "request", fail_request)
    monkeypatch.setattr(httpx, "request", fail_request)

    messages = ["caller instruction only"]
    provider, _result = _run(messages=messages)

    assert provider.requests[0].model_id == CALLER_MODEL
    assert provider.requests[0].messages == messages
    assert inspect.signature(execute_eye_job).parameters["model_id"].default is inspect.Parameter.empty

    for module_name in (
        "app.stages.eye",
        "app.runtime.job",
        "app.providers.fake_eye",
        "app.providers.eye",
        "app.api.jobs",
    ):
        source = inspect.getsource(__import__(module_name, fromlist=["*"]))
        assert "gpt-4.1" not in source
        assert "openrouter.ai" not in source


def test_post_jobs_creates_without_running_eye() -> None:
    payload = _contract().model_dump(mode="json")
    payload["references"][0]["media_type"] = "PNG"
    payload["references"][0]["filename"] = "pixel.png"
    payload["references"][0]["content_hash"] = PNG_HASH
    payload["references"][0]["content_base64"] = PNG_B64
    response = TestClient(app).post("/api/v1/jobs", json={"contract": payload})

    assert response.status_code == 200
    body = response.json()
    assert body["contract_id"] == "contract-towel-1"
    assert body["revision"] == 2
    assert body["stage"] == "intake"
    assert body["state"] == "accepted"
    assert "observation" not in body
    assert "model_id" not in body
