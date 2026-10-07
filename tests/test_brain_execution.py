from app.contracts.brain import BrainPlan
from app.contracts.job import Phase0JobContract
from app.providers.brain_instruction import brain_instruction
from app.providers.fake_brain import FakeBrainProvider, plan_for
from app.providers.fake_eye import FakeEyeProvider
from app.runtime.jobs import create_job, execute_job_brain, execute_job_eye
from app.runtime.state import InMemoryJobStore
from app.stages.brain import BrainPlanInvalidError, build_brain_input, execute_brain
from tests.png_bytes import PNG_1X1, PNG_HASH
import pytest
from pydantic import ValidationError

CALLER_MODEL = "caller-supplied-model"
HASH = PNG_HASH


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
                    "filename": "pixel.png",
                    "media_type": "PNG",
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


def _eyed(store: InMemoryJobStore, kind: str = "ready"):
    record = create_job(store, _contract(), {"ref-towel": PNG_1X1})
    return execute_job_eye(
        store,
        job_id=record.job_id,
        model_id=CALLER_MODEL,
        provider=FakeEyeProvider(kind),  # type: ignore[arg-type]
    )


def test_execute_brain_binds_job_contract_and_eye() -> None:
    store = InMemoryJobStore()
    record = _eyed(store)
    provider = FakeBrainProvider()
    result = execute_brain(
        brain_input=build_brain_input(record),
        model_id=CALLER_MODEL,
        provider=provider,
    )
    assert result.contract_id == "contract-towel-1"
    assert result.revision == 2
    assert result.observation_revision == 2
    assert result.model_id == CALLER_MODEL
    assert result.plan.mode == "fidelity-locked"
    assert any(item.name == "count" and item.value == "1" for item in result.plan.invariants)
    assert provider.requests[0].brain_input.contract.changes.policy_mode == "fidelity-locked"


def test_execute_job_brain_does_not_mutate_contract_or_eye() -> None:
    store = InMemoryJobStore()
    after_eye = _eyed(store)
    observation = after_eye.observation
    after_brain = execute_job_brain(
        store,
        job_id=after_eye.job_id,
        model_id=CALLER_MODEL,
        provider=FakeBrainProvider(),
    )
    assert after_brain.contract == after_eye.contract
    assert after_brain.observation == observation
    assert after_brain.brain is not None
    assert after_brain.brain.result is not None
    assert after_brain.stage == "brain"
    assert after_brain.events[-1].kind == "brain_completed"


def test_protected_identity_cannot_become_a_variable() -> None:
    store = InMemoryJobStore()
    record = _eyed(store)
    with pytest.raises(BrainPlanInvalidError, match="protected identity"):
        execute_brain(
            brain_input=build_brain_input(record),
            model_id=CALLER_MODEL,
            provider=FakeBrainProvider(violation="protected_as_variable"),
        )


def test_eye_unknowns_remain_in_brain_plan() -> None:
    store = InMemoryJobStore()
    record = _eyed(store, "ready_with_unknown")
    result = execute_brain(
        brain_input=build_brain_input(record),
        model_id=CALLER_MODEL,
        provider=FakeBrainProvider(),
    )
    assert "fibre composition" in {item.subject for item in result.plan.unknowns}

    with pytest.raises(BrainPlanInvalidError, match="unknowns"):
        execute_brain(
            brain_input=build_brain_input(record),
            model_id=CALLER_MODEL,
            provider=FakeBrainProvider(violation="drop_unknowns"),
        )


def test_instruction_requires_exact_brainplan_json() -> None:
    text = brain_instruction()
    assert '"scene": {' in text
    assert '"mode": "preserve_supplied_scene|create_new_scene"' in text
    assert "scene as a string" in text
    assert '"value": "1"' in text
    assert "unknowns.evidence_reference_id" in text
    assert "source-supported construction" in text
    assert "authorised edits" in text
    assert "extra=\"forbid\"" in text or "extra=forbid" in text


def test_mock_openrouter_json_validates_as_brainplan() -> None:
    store = InMemoryJobStore()
    record = _eyed(store)
    expected = plan_for(build_brain_input(record))
    payload = expected.model_dump(mode="json")
    parsed = BrainPlan.model_validate(payload)
    assert parsed == expected
    assert isinstance(payload["scene"], dict)
    assert payload["scene"]["mode"] in {
        "preserve_supplied_scene",
        "create_new_scene",
    }
    assert isinstance(payload["invariants"][0]["value"], str)


def test_live_mismatch_shapes_are_still_rejected() -> None:
    store = InMemoryJobStore()
    record = _eyed(store)
    payload = plan_for(build_brain_input(record)).model_dump(mode="json")
    payload["scene"] = "preserve_supplied_scene"
    payload["invariants"][0]["value"] = 1
    payload["unknowns"] = [{"subject": "x", "detail": "y", "evidence_reference_id": "ref-towel"}]
    with pytest.raises(ValidationError):
        BrainPlan.model_validate(payload)
