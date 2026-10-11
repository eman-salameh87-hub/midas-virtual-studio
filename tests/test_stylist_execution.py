import pytest
from pydantic import ValidationError

from app.contracts.job import Phase0JobContract
from app.contracts.stylist import StylistPlan
from app.providers.fake_brain import FakeBrainProvider
from app.providers.fake_eye import FakeEyeProvider
from app.providers.fake_stylist import FakeStylistProvider, plan_for
from app.providers.stylist_instruction import stylist_instruction
from app.runtime.jobs import (
    BrainNotRunError,
    EyeNotRunError,
    StylistNotReadyError,
    create_job,
    execute_job_brain,
    execute_job_eye,
    execute_job_stylist,
)
from app.runtime.state import InMemoryJobStore
from app.stages.stylist import (
    StylistPlanInvalidError,
    build_stylist_input,
    execute_stylist,
)
from tests.png_bytes import PNG_1X1, PNG_HASH

CALLER_MODEL = "caller-supplied-model"
HASH = PNG_HASH


def _contract(
    category: str = "Towels",
    department: str = "Accessories",
    subcategory: str = "Bathroom",
    product_role: str = "hero",
) -> Phase0JobContract:
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
                "department": department,
                "category": category,
                "subcategory": subcategory,
                "product_role": product_role,
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


def _brained(store: InMemoryJobStore, contract: Phase0JobContract | None = None, kind: str = "ready"):
    c = contract or _contract()
    record = create_job(store, c, {"ref-towel": PNG_1X1})
    eyed = execute_job_eye(
        store,
        job_id=record.job_id,
        model_id=CALLER_MODEL,
        provider=FakeEyeProvider(kind),  # type: ignore[arg-type]
    )
    return execute_job_brain(
        store,
        job_id=eyed.job_id,
        model_id=CALLER_MODEL,
        provider=FakeBrainProvider(violation="hold" if kind == "hold" else None),
    )


def test_execute_stylist_binds_job_contract_eye_and_brain() -> None:
    store = InMemoryJobStore()
    record = _brained(store)
    provider = FakeStylistProvider()
    result = execute_stylist(
        stylist_input=build_stylist_input(record),
        model_id=CALLER_MODEL,
        provider=provider,
    )
    assert result.contract_id == "contract-towel-1"
    assert result.revision == 2
    assert result.brain_contract_id == "contract-towel-1"
    assert result.brain_revision == 2
    assert result.model_id == CALLER_MODEL
    assert result.plan.product_role == "hero"
    assert provider.requests[0].stylist_input.contract.changes.policy_mode == "fidelity-locked"


def test_execute_job_stylist_does_not_mutate_prior_stages() -> None:
    store = InMemoryJobStore()
    after_brain = _brained(store)
    contract = after_brain.contract
    observation = after_brain.observation
    brain = after_brain.brain
    after_stylist = execute_job_stylist(
        store,
        job_id=after_brain.job_id,
        model_id=CALLER_MODEL,
        provider=FakeStylistProvider(),
    )
    assert after_stylist.contract == contract
    assert after_stylist.observation == observation
    assert after_stylist.brain == brain
    assert after_stylist.stylist is not None
    assert after_stylist.stylist.result is not None
    assert after_stylist.stage == "stylist"
    assert after_stylist.events[-1].kind == "stylist_completed"


def test_stylist_cannot_run_without_eye() -> None:
    store = InMemoryJobStore()
    record = create_job(store, _contract(), {"ref-towel": PNG_1X1})
    with pytest.raises(EyeNotRunError):
        execute_job_stylist(
            store,
            job_id=record.job_id,
            model_id=CALLER_MODEL,
            provider=FakeStylistProvider(),
        )


def test_stylist_cannot_run_without_brain() -> None:
    store = InMemoryJobStore()
    record = create_job(store, _contract(), {"ref-towel": PNG_1X1})
    execute_job_eye(
        store,
        job_id=record.job_id,
        model_id=CALLER_MODEL,
        provider=FakeEyeProvider("ready"),
    )
    with pytest.raises(BrainNotRunError):
        execute_job_stylist(
            store,
            job_id=record.job_id,
            model_id=CALLER_MODEL,
            provider=FakeStylistProvider(),
        )


def test_stylist_held_when_brain_held() -> None:
    store = InMemoryJobStore()
    record = create_job(store, _contract(), {"ref-towel": PNG_1X1})
    execute_job_eye(
        store,
        job_id=record.job_id,
        model_id=CALLER_MODEL,
        provider=FakeEyeProvider("ready"),
    )
    execute_job_brain(
        store,
        job_id=record.job_id,
        model_id=CALLER_MODEL,
        provider=FakeBrainProvider(violation="hold"),
    )
    with pytest.raises(StylistNotReadyError):
        execute_job_stylist(
            store,
            job_id=record.job_id,
            model_id=CALLER_MODEL,
            provider=FakeStylistProvider(),
        )


def test_unverified_midas_sku_rejected_by_stylist_stage() -> None:
    store = InMemoryJobStore()
    record = _brained(store)
    with pytest.raises(StylistPlanInvalidError, match="not in verified catalogue evidence"):
        execute_stylist(
            stylist_input=build_stylist_input(record),
            model_id=CALLER_MODEL,
            provider=FakeStylistProvider(violation="unverified_companion"),
        )



def test_brain_unknowns_remain_in_stylist_plan() -> None:
    store = InMemoryJobStore()
    record = _brained(store, kind="ready_with_unknown")
    result = execute_stylist(
        stylist_input=build_stylist_input(record),
        model_id=CALLER_MODEL,
        provider=FakeStylistProvider(),
    )
    assert "fibre composition" in {item.subject for item in result.plan.unknowns}

    with pytest.raises(StylistPlanInvalidError, match="unknowns"):
        execute_stylist(
            stylist_input=build_stylist_input(record),
            model_id=CALLER_MODEL,
            provider=FakeStylistProvider(violation="drop_unknowns"),
        )


def test_instruction_requires_exact_stylistplan_json() -> None:
    text = stylist_instruction()
    assert '"scene": {' in text
    assert '"frame": "Square · 1:1|Portrait · 4:5|Landscape · 16:9"' in text
    assert '"candidate_boards": [' in text
    assert '"selected_layout": {' in text
    assert '"rejected_alternatives": [' in text
    assert '"is_midas_product": false' in text
    assert "extra=\"forbid\"" in text or "extra=forbid" in text
    assert "White BK" in text
    assert "pure white (#FFFFFF)" in text


def test_mock_openrouter_json_validates_as_stylistplan() -> None:
    store = InMemoryJobStore()
    record = _brained(store)
    expected = plan_for(build_stylist_input(record))
    payload = expected.model_dump(mode="json")
    parsed = StylistPlan.model_validate(payload)
    assert parsed == expected
    assert isinstance(payload["scene"], dict)
    assert payload["selected_layout"]["board_id"] in [b["board_id"] for b in payload["candidate_boards"]]


def test_accessory_and_textile_hero_planning() -> None:
    store = InMemoryJobStore()
    towel_contract = _contract(category="Towels", department="Accessories", subcategory="Towels", product_role="hero")
    record = _brained(store, towel_contract)
    result = execute_stylist(
        stylist_input=build_stylist_input(record),
        model_id=CALLER_MODEL,
        provider=FakeStylistProvider(),
    )
    assert result.plan.product_role == "hero"
    assert "towel" in result.plan.hero_prominence.lower()
    assert result.plan.view_requirements.close_up_requirements is not None
