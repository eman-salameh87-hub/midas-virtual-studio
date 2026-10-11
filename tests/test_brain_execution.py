import json

from app.contracts.brain import BrainPlan
from app.contracts.job import Phase0JobContract
from app.providers.brain_grounding import apply_brain_grounding_evidence
from app.providers.brain_instruction import brain_instruction
from app.providers.fake_brain import FakeBrainProvider, plan_for
from app.providers.fake_eye import FakeEyeProvider
from app.providers.openrouter import OpenRouterBrainProvider, OpenRouterSettings
from app.runtime.jobs import create_job, execute_job_brain, execute_job_eye
from app.runtime.state import InMemoryJobStore
from app.stages.brain import (
    BrainPlanInvalidError,
    build_brain_input,
    execute_brain,
    validate_brain_plan,
)
from tests.png_bytes import PNG_1X1, PNG_HASH
import pytest
from pydantic import ValidationError

CALLER_MODEL = "caller-supplied-model"
HASH = PNG_HASH


_OUTCOME_MEMBERS = (
    ("Lifestyle", "lifestyle"),
    ("White BK", "catalogue"),
    ("Website", "catalogue"),
    ("New Composition", "lifestyle"),
    ("Variations", "alternative view"),
    ("Create with this item", "lifestyle"),
)


def _contract(
    *,
    requested_outcomes: list[str] | None = None,
    package_members: list[str] | None = None,
    department: str = "Accessories",
    category: str = "Bathroom",
    subcategory: str = "Towels",
    policy_mode: str | None = None,
) -> Phase0JobContract:
    outcomes = requested_outcomes or ["Lifestyle"]
    members = package_members or ["lifestyle"]
    if policy_mode is None:
        policy_mode = "fidelity-locked"
        allowed_changes = ["styled setting"]
    else:
        allowed_changes = (
            [] if policy_mode == "fidelity-locked" else ["styled setting"]
        )
    return Phase0JobContract.model_validate(
        {
            "contract_id": "contract-towel-1",
            "revision": 2,
            "owner_id": "owner-1",
            "intent": {
                "mode": "Manual",
                "job_type": "New Project",
                "job_option": "One by one (same department)",
                "requested_outcomes": outcomes,
                "other_outcome": None,
                "requested_pieces": ["towel"],
                "excluded_pieces": [],
                "selected_count": {"status": "declared", "value": 1},
            },
            "item": {
                "department": department,
                "category": category,
                "subcategory": subcategory,
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
                "package_members": members,
            },
            "changes": {
                "policy_mode": policy_mode,
                "allowed_changes": allowed_changes,
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


def _eyed(
    store: InMemoryJobStore,
    kind: str = "ready",
    contract: Phase0JobContract | None = None,
):
    record = create_job(store, contract or _contract(), {"ref-towel": PNG_1X1})
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
    assert "contract.item.category" in text
    assert "home-furniture/living-rooms" in text
    assert "copy_exactly" in text
    assert "allowed_evidence_ids" in text
    assert "omit that grounding item" in text


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


@pytest.mark.parametrize("outcome,member", _OUTCOME_MEMBERS)
def test_route_category_equals_item_category_for_supported_outcomes(
    outcome: str, member: str
) -> None:
    store = InMemoryJobStore()
    record = _eyed(
        store,
        contract=_contract(
            requested_outcomes=[outcome],
            package_members=[member],
            department="home-furniture",
            category="home-furniture/living-rooms",
            subcategory="home-furniture/living-rooms/sofa",
            policy_mode=(
                "fidelity-locked"
                if outcome in {"White BK", "Website"}
                else "creative-room"
            ),
        ),
    )
    result = execute_brain(
        brain_input=build_brain_input(record),
        model_id=CALLER_MODEL,
        provider=FakeBrainProvider(),
    )
    assert result.plan.route.category == "home-furniture/living-rooms"
    assert result.plan.route.category != outcome
    assert result.plan.route.category != member


def test_mismatched_route_category_is_rejected() -> None:
    store = InMemoryJobStore()
    record = _eyed(
        store,
        contract=_contract(
            department="home-furniture",
            category="home-furniture/living-rooms",
            subcategory="home-furniture/living-rooms/sofa",
        ),
    )
    with pytest.raises(
        BrainPlanInvalidError,
        match=r"expected 'home-furniture/living-rooms', got 'Living Rooms'",
    ):
        execute_brain(
            brain_input=build_brain_input(record),
            model_id=CALLER_MODEL,
            provider=FakeBrainProvider(violation="wrong_category"),
        )


def test_openrouter_brain_payload_copy_exactly_item_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryJobStore()
    record = _eyed(
        store,
        contract=_contract(
            department="home-furniture",
            category="home-furniture/living-rooms",
            subcategory="home-furniture/living-rooms/sofa",
        ),
    )
    brain_input = build_brain_input(record)
    captured: dict[str, object] = {}

    def fake_complete(settings, body, last_call):  # noqa: ANN001
        captured["user"] = json.loads(body["messages"][1]["content"])
        return plan_for(brain_input).model_dump(mode="json")

    monkeypatch.setattr(
        "app.providers.openrouter.complete_chat_object", fake_complete
    )
    provider = OpenRouterBrainProvider(
        OpenRouterSettings(
            api_key="test",
            base_url="http://example.invalid",
            timeout_seconds=1.0,
        )
    )
    result = execute_brain(
        brain_input=brain_input,
        model_id=CALLER_MODEL,
        provider=provider,
    )
    copy_exactly = captured["user"]["copy_exactly"]
    assert copy_exactly["route.category"] == "home-furniture/living-rooms"
    assert copy_exactly["route.category"] == result.plan.route.category
    assert "copy_exactly" not in result.plan.model_dump()
    assert captured["user"]["allowed_evidence_ids"] == ["ref-towel"]
    assert "allowed_evidence_ids" not in result.plan.model_dump()


def test_observed_grounding_with_valid_evidence_id_is_kept() -> None:
    store = InMemoryJobStore()
    record = _eyed(store)
    payload = plan_for(build_brain_input(record)).model_dump(mode="json")
    payload["grounding"] = [
        {
            "subject": "bed",
            "relation": "category",
            "value": "visible bed",
            "basis": "observed",
            "evidence_reference_id": "ref-towel",
        }
    ]
    mapped = apply_brain_grounding_evidence(payload, {"ref-towel"})
    parsed = BrainPlan.model_validate(mapped)
    assert parsed.grounding[0].evidence_reference_id == "ref-towel"
    validate_brain_plan(build_brain_input(record), parsed)


def test_observed_grounding_without_evidence_id_is_omitted_not_filled() -> None:
    store = InMemoryJobStore()
    record = _eyed(store)
    payload = plan_for(build_brain_input(record)).model_dump(mode="json")
    payload["grounding"] = [
        {
            "subject": "bed",
            "relation": "category",
            "value": "visible bed",
            "basis": "observed",
            "evidence_reference_id": None,
        },
        {
            "subject": "plan",
            "relation": "category",
            "value": "decision from contract",
            "basis": "decision",
            "evidence_reference_id": None,
        },
    ]
    mapped = apply_brain_grounding_evidence(payload, {"ref-towel"})
    assert [item["basis"] for item in mapped["grounding"]] == ["decision"]
    assert all(item.get("evidence_reference_id") != "ref-towel" for item in mapped["grounding"])
    parsed = BrainPlan.model_validate(mapped)
    assert len(parsed.grounding) == 1
    assert parsed.grounding[0].basis == "decision"


def test_grounding_id_not_in_supplied_evidence_is_rejected_not_replaced() -> None:
    store = InMemoryJobStore()
    record = _eyed(store)
    with pytest.raises(BrainPlanInvalidError, match="unknown evidence"):
        execute_brain(
            brain_input=build_brain_input(record),
            model_id=CALLER_MODEL,
            provider=FakeBrainProvider(violation="unknown_grounding"),
        )
    payload = plan_for(build_brain_input(record)).model_dump(mode="json")
    payload["grounding"] = [
        {
            "subject": "bed",
            "relation": "category",
            "value": "visible bed",
            "basis": "observed",
            "evidence_reference_id": "bed",
        }
    ]
    mapped = apply_brain_grounding_evidence(payload, {"ref-towel"})
    assert mapped["grounding"][0]["evidence_reference_id"] == "bed"
    parsed = BrainPlan.model_validate(mapped)
    with pytest.raises(BrainPlanInvalidError, match="unknown evidence"):
        validate_brain_plan(build_brain_input(record), parsed)


def test_openrouter_omits_observed_grounding_without_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = InMemoryJobStore()
    record = _eyed(store)
    brain_input = build_brain_input(record)
    raw = plan_for(brain_input).model_dump(mode="json")
    raw["grounding"] = [
        {
            "subject": "bed",
            "relation": "category",
            "value": "visible bed",
            "basis": "observed",
            "evidence_reference_id": None,
        },
        {
            "subject": "plan",
            "relation": "provenance",
            "value": "contract",
            "basis": "decision",
            "evidence_reference_id": None,
        },
    ]

    monkeypatch.setattr(
        "app.providers.openrouter.complete_chat_object",
        lambda settings, body, last_call: raw,
    )
    provider = OpenRouterBrainProvider(
        OpenRouterSettings(
            api_key="test",
            base_url="http://example.invalid",
            timeout_seconds=1.0,
        )
    )
    result = execute_brain(
        brain_input=brain_input,
        model_id=CALLER_MODEL,
        provider=provider,
    )
    assert [item.basis for item in result.plan.grounding] == ["decision"]
    assert all(item.evidence_reference_id is None for item in result.plan.grounding)
