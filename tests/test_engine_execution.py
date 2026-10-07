import pytest

from app.contracts.job import Phase0JobContract
from app.providers.fake_brain import FakeBrainProvider
from app.providers.fake_engine import FakeEngineCompiler, compile_for
from app.providers.fake_eye import FakeEyeProvider
from app.providers.fake_stylist import FakeStylistProvider
from app.runtime.jobs import (
    BrainNotRunError,
    EngineNotReadyError,
    EyeNotRunError,
    StylistNotRunError,
    create_job,
    execute_job_brain,
    execute_job_compile,
    execute_job_eye,
    execute_job_stylist,
    get_job_compile,
)
from app.runtime.state import InMemoryJobStore
from app.stages.compile import (
    EngineCompileInvalidError,
    build_engine_input,
    execute_engine,
)
from tests.png_bytes import PNG_1X1, PNG_HASH

CALLER_MODEL = "caller-supplied-model"
HASH = PNG_HASH


def _contract(
    *,
    contract_id: str = "contract-towel-1",
    category: str = "Bathroom",
    department: str = "Accessories",
    subcategory: str = "Towels",
    product_role: str = "hero",
    selected_count: int = 1,
    views: list[str] | None = None,
) -> Phase0JobContract:
    return Phase0JobContract.model_validate(
        {
            "contract_id": contract_id,
            "revision": 2,
            "owner_id": "owner-1",
            "intent": {
                "mode": "Manual",
                "job_type": "New Project",
                "job_option": "One by one (same department)",
                "requested_outcomes": ["Lifestyle"],
                "other_outcome": None,
                "requested_pieces": [subcategory.casefold()],
                "excluded_pieces": [],
                "selected_count": {"status": "declared", "value": selected_count},
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
                    "reference_id": "ref-product",
                    "filename": "pixel.png",
                    "media_type": "PNG",
                    "hash_algorithm": "sha256",
                    "content_hash": HASH,
                    "role": "Product / vendor reference",
                },
                {
                    "reference_id": "ref-room",
                    "filename": "room.png",
                    "media_type": "PNG",
                    "hash_algorithm": "sha256",
                    "content_hash": HASH,
                    "role": "Room / target space",
                },
            ],
            "outputs": {
                "views": views or ["Wide view"],
                "image_proportions": "Square · 1:1",
                "resolution": "2K",
                "package_members": ["lifestyle"],
            },
            "changes": {
                "policy_mode": "fidelity-locked",
                "allowed_changes": ["styled setting"],
                "protected_identity": [f"{subcategory.casefold()} count"],
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


def _styled(
    store: InMemoryJobStore,
    contract: Phase0JobContract | None = None,
    *,
    eye_kind: str = "ready",
    brain_violation: str | None = None,
    stylist_violation: str | None = None,
):
    c = contract or _contract()
    record = create_job(
        store,
        c,
        {"ref-product": PNG_1X1, "ref-room": PNG_1X1},
    )
    execute_job_eye(
        store,
        job_id=record.job_id,
        model_id=CALLER_MODEL,
        provider=FakeEyeProvider(eye_kind),  # type: ignore[arg-type]
    )
    execute_job_brain(
        store,
        job_id=record.job_id,
        model_id=CALLER_MODEL,
        provider=FakeBrainProvider(violation=brain_violation),
    )
    return execute_job_stylist(
        store,
        job_id=record.job_id,
        model_id=CALLER_MODEL,
        provider=FakeStylistProvider(violation=stylist_violation),
    )


def test_engine_cannot_run_without_eye() -> None:
    store = InMemoryJobStore()
    record = create_job(store, _contract(), {"ref-product": PNG_1X1, "ref-room": PNG_1X1})
    with pytest.raises(EyeNotRunError):
        execute_job_compile(
            store,
            job_id=record.job_id,
            model_id=CALLER_MODEL,
            compiler=FakeEngineCompiler(),
        )


def test_engine_cannot_run_without_brain() -> None:
    store = InMemoryJobStore()
    record = create_job(store, _contract(), {"ref-product": PNG_1X1, "ref-room": PNG_1X1})
    execute_job_eye(
        store,
        job_id=record.job_id,
        model_id=CALLER_MODEL,
        provider=FakeEyeProvider("ready"),
    )
    with pytest.raises(BrainNotRunError):
        execute_job_compile(
            store,
            job_id=record.job_id,
            model_id=CALLER_MODEL,
            compiler=FakeEngineCompiler(),
        )


def test_engine_cannot_run_without_stylist() -> None:
    store = InMemoryJobStore()
    record = create_job(store, _contract(), {"ref-product": PNG_1X1, "ref-room": PNG_1X1})
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
        provider=FakeBrainProvider(),
    )
    with pytest.raises(StylistNotRunError):
        execute_job_compile(
            store,
            job_id=record.job_id,
            model_id=CALLER_MODEL,
            compiler=FakeEngineCompiler(),
        )


def test_brain_hold_blocks_ready_compilation() -> None:
    store = InMemoryJobStore()
    record = create_job(store, _contract(), {"ref-product": PNG_1X1, "ref-room": PNG_1X1})
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
    with pytest.raises(StylistNotRunError):
        execute_job_compile(
            store,
            job_id=record.job_id,
            model_id=CALLER_MODEL,
            compiler=FakeEngineCompiler(),
        )


def test_stylist_hold_blocks_ready_compilation() -> None:
    store = InMemoryJobStore()
    after_stylist = _styled(store, stylist_violation="hold")
    assert after_stylist.stylist is not None
    assert after_stylist.stylist.result is not None
    assert after_stylist.stylist.result.status == "hold"
    with pytest.raises(EngineNotReadyError):
        execute_job_compile(
            store,
            job_id=after_stylist.job_id,
            model_id=CALLER_MODEL,
            compiler=FakeEngineCompiler(),
        )


def test_valid_fake_compilation_persists_and_get_does_not_rerun() -> None:
    store = InMemoryJobStore()
    after_stylist = _styled(store)
    compiler = FakeEngineCompiler()
    compiled = execute_job_compile(
        store,
        job_id=after_stylist.job_id,
        model_id=CALLER_MODEL,
        compiler=compiler,
    )
    assert compiled.stage == "compile"
    assert compiled.state == "ready"
    assert compiled.engine is not None
    assert compiled.engine.result is not None
    assert compiled.engine.result.status == "ready"
    assert compiled.engine.result.model_id == CALLER_MODEL
    assert compiled.events[-1].kind == "compile_completed"
    assert len(compiler.requests) == 1

    first_prompt = compiled.engine.result.exact_prompt
    loaded = get_job_compile(store, compiled.job_id)
    assert loaded.engine is not None
    assert loaded.engine.result is not None
    assert loaded.engine.result.exact_prompt == first_prompt
    assert len(compiler.requests) == 1


def test_bindings_locks_scene_layout_and_references_preserved() -> None:
    store = InMemoryJobStore()
    after_stylist = _styled(store)
    result = execute_engine(
        engine_input=build_engine_input(after_stylist),
        model_id=CALLER_MODEL,
        compiler=FakeEngineCompiler(),
    )
    artifact = result.compile
    brain = after_stylist.brain.result
    stylist = after_stylist.stylist.result
    assert brain is not None and stylist is not None

    assert artifact.brain_contract_id == brain.contract_id
    assert artifact.brain_revision == brain.contract_revision
    assert artifact.stylist_contract_id == stylist.contract_id
    assert artifact.stylist_revision == stylist.contract_revision
    assert artifact.locks == brain.invariants
    assert artifact.scene == stylist.scene
    assert artifact.selected_layout == stylist.selected_layout
    assert artifact.hero_prominence == stylist.hero_prominence
    assert [item.reference_id for item in artifact.references] == [
        "ref-product",
        "ref-room",
    ]
    assert [item.role for item in artifact.references] == [
        "Product / vendor reference",
        "Room / target space",
    ]


def test_no_invented_references() -> None:
    store = InMemoryJobStore()
    after_stylist = _styled(store)
    with pytest.raises(EngineCompileInvalidError, match="reference order"):
        execute_engine(
            engine_input=build_engine_input(after_stylist),
            model_id=CALLER_MODEL,
            compiler=FakeEngineCompiler(violation="invent_reference"),
        )


def test_exact_prompt_is_deterministic() -> None:
    store = InMemoryJobStore()
    after_stylist = _styled(store)
    assert after_stylist.stylist is not None and after_stylist.stylist.result is not None
    engine_input = build_engine_input(after_stylist)
    first = compile_for(engine_input, model_id=CALLER_MODEL)
    second = compile_for(engine_input, model_id=CALLER_MODEL)
    assert first.exact_prompt == second.exact_prompt
    assert "Locks (must not change):" in first.exact_prompt
    assert "count:" in first.exact_prompt
    assert after_stylist.stylist.result.scene.setting in first.exact_prompt
    assert "Do not invent product facts." in first.exact_prompt


def test_multiple_categories_compile_with_same_architecture() -> None:
    store = InMemoryJobStore()
    cases = [
        _contract(
            contract_id="contract-towel",
            department="Accessories",
            category="Bathroom",
            subcategory="Towels",
        ),
        _contract(
            contract_id="contract-bookends",
            department="Accessories",
            category="Decor",
            subcategory="Bookends",
            selected_count=2,
        ),
        _contract(
            contract_id="contract-dining",
            department="Home Furniture",
            category="Dining Rooms",
            subcategory="Dining Chairs",
            selected_count=12,
        ),
        _contract(
            contract_id="contract-table",
            department="Home Furniture",
            category="Living Rooms",
            subcategory="Coffee Tables",
        ),
    ]
    for contract in cases:
        after = _styled(store, contract)
        compiled = execute_job_compile(
            store,
            job_id=after.job_id,
            model_id=CALLER_MODEL,
            compiler=FakeEngineCompiler(),
        )
        assert compiled.engine is not None
        assert compiled.engine.result is not None
        assert compiled.engine.result.status == "ready"
        assert compiled.engine.result.product_role == contract.item.product_role
        assert compiled.engine.result.contract_id == contract.contract_id


def test_missing_critical_information_results_in_hold() -> None:
    store = InMemoryJobStore()
    after_stylist = _styled(store)
    compiled = execute_job_compile(
        store,
        job_id=after_stylist.job_id,
        model_id=CALLER_MODEL,
        compiler=FakeEngineCompiler(violation="missing_critical"),
    )
    assert compiled.state == "hold"
    assert compiled.engine is not None
    assert compiled.engine.result is not None
    assert compiled.engine.result.status == "hold"
    assert compiled.engine.result.exact_prompt == ""
    assert any("critical unknown" in reason for reason in compiled.engine.result.hold_reasons)
    assert compiled.engine.result.locks == after_stylist.brain.result.invariants


def test_owner_and_revision_mismatch() -> None:
    from app.runtime.jobs import JobOwnerMismatchError, RevisionMismatchError

    store = InMemoryJobStore()
    after_stylist = _styled(store)
    with pytest.raises(JobOwnerMismatchError):
        execute_job_compile(
            store,
            job_id=after_stylist.job_id,
            model_id=CALLER_MODEL,
            compiler=FakeEngineCompiler(),
            owner_id="wrong-owner",
        )
    with pytest.raises(RevisionMismatchError):
        execute_job_compile(
            store,
            job_id=after_stylist.job_id,
            model_id=CALLER_MODEL,
            compiler=FakeEngineCompiler(),
            revision=99,
        )
