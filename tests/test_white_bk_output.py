"""White BK output type, source-mark handling, and critique checks. No live providers."""

import pytest

from app.contracts.critique import CritiqueAssessment
from app.contracts.job import Phase0JobContract
from app.contracts.stylist import GenericContextProp
from app.providers.fake_brain import FakeBrainProvider
from app.providers.fake_critique import FakeCritiqueProvider, assessment_for
from app.providers.fake_engine import FakeEngineCompiler, compile_for
from app.providers.fake_eye import FakeEyeProvider
from app.providers.fake_generation import FakeGenerationProvider
from app.providers.fake_stylist import FakeStylistProvider, plan_for
from app.providers.openrouter import generation_user_content
from app.runtime.jobs import (
    approve_job,
    approve_pre_generation,
    create_job,
    execute_job_brain,
    execute_job_compile,
    execute_job_critique,
    execute_job_eye,
    execute_job_generate,
    execute_job_stylist,
    release_job,
)
from app.runtime.state import InMemoryJobStore
from app.stages.compile import (
    EngineCompileInvalidError,
    build_engine_input,
    execute_engine,
)
from app.stages.critique import (
    CritiqueAssessmentInvalidError,
    build_critique_input,
    validate_critique_assessment,
)
from app.stages.stylist import (
    StylistPlanInvalidError,
    build_stylist_input,
    validate_stylist_plan,
)
from tests.png_bytes import PNG_1X1, PNG_HASH
from tests.test_generation_execution import _compiled as _lifestyle_compiled
from tests.test_generation_execution import _contract as _lifestyle_contract

CALLER_MODEL = "caller-supplied-model"
HASH = PNG_HASH


def _white_bk_contract() -> Phase0JobContract:
    return Phase0JobContract.model_validate(
        {
            "contract_id": "contract-white-bk-1",
            "revision": 2,
            "owner_id": "owner-1",
            "intent": {
                "mode": "Manual",
                "job_type": "New Project",
                "job_option": "One by one (same department)",
                "requested_outcomes": ["White BK"],
                "other_outcome": None,
                "requested_pieces": ["towels"],
                "excluded_pieces": [],
                "selected_count": {"status": "declared", "value": 1},
            },
            "item": {
                "department": "Accessories",
                "category": "Bathroom",
                "subcategory": "Towels",
                "product_role": "hero",
            },
            "source_condition": {"input_condition": "clean pack shot"},
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
                "views": ["Front"],
                "image_proportions": "Square · 1:1",
                "resolution": "2K",
                "package_members": ["catalogue"],
            },
            "changes": {
                "policy_mode": "fidelity-locked",
                "allowed_changes": [],
                "protected_identity": ["product appearance"],
                "room_locks": [],
                "creative_variables": [],
            },
            "preferences": {
                "lighting": "Soft daylight",
                "wall": "White",
                "floor": "Light oak",
                "plants": False,
                "human": False,
                "mood": "Automatic",
            },
            "statements": [],
            "unknowns": [],
            "conflicts": [],
        }
    )


def _styled_white_bk(store: InMemoryJobStore, *, eye_kind: str = "ready"):
    record = create_job(
        store,
        _white_bk_contract(),
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
        provider=FakeBrainProvider(),
    )
    return execute_job_stylist(
        store,
        job_id=record.job_id,
        model_id=CALLER_MODEL,
        provider=FakeStylistProvider(),
    )


def _compiled_white_bk(store: InMemoryJobStore, *, eye_kind: str = "ready"):
    after = _styled_white_bk(store, eye_kind=eye_kind)
    compiled = execute_job_compile(
        store,
        job_id=after.job_id,
        model_id=CALLER_MODEL,
        compiler=FakeEngineCompiler(),
    )
    return approve_pre_generation(store, job_id=compiled.job_id)


def _generated_white_bk(store: InMemoryJobStore):
    compiled = _compiled_white_bk(store)
    return execute_job_generate(
        store, job_id=compiled.job_id, provider=FakeGenerationProvider()
    )


def test_white_bk_compile_does_not_become_a_lifestyle_scene() -> None:
    store = InMemoryJobStore()
    after = _styled_white_bk(store)
    assert after.stylist is not None and after.stylist.result is not None
    assert after.stylist.result.supporting_props == []
    setting = after.stylist.result.scene.setting.casefold()
    assert "pure white" in setting
    assert "#ffffff" in setting
    assert "no lifestyle scene" in after.stylist.result.scene.setting.casefold()

    result = execute_engine(
        engine_input=build_engine_input(after),
        model_id=CALLER_MODEL,
        compiler=FakeEngineCompiler(),
    )
    prompt = result.compile.exact_prompt
    folded = prompt.casefold()
    assert "Requested output type: White BK" in prompt
    assert "#FFFFFF" in prompt
    assert "product alone" in folded
    assert "no room" in folded
    assert "no lifestyle scene" in folded
    assert "no decorative props" in folded
    assert "styled interior" not in folded
    assert "Place it in the approved styled interior" not in prompt

    with pytest.raises(EngineCompileInvalidError, match="White BK"):
        execute_engine(
            engine_input=build_engine_input(after),
            model_id=CALLER_MODEL,
            compiler=FakeEngineCompiler(violation="lifestyle_scene"),
        )


def test_stylist_cannot_override_white_bk_with_props() -> None:
    store = InMemoryJobStore()
    after = _styled_white_bk(store)
    stylist_input = build_stylist_input(after)
    plan = plan_for(stylist_input)
    bad = plan.model_copy(
        update={
            "supporting_props": [
                GenericContextProp(
                    name="Potted indoor plant",
                    purpose="lifestyle greenery",
                    placement="corner",
                    is_midas_product=False,
                )
            ]
        }
    )
    with pytest.raises(StylistPlanInvalidError, match="decorative props"):
        validate_stylist_plan(stylist_input, bad)


def test_detected_source_logo_is_not_a_reproduction_request() -> None:
    store = InMemoryJobStore()
    after = _styled_white_bk(store, eye_kind="ready_with_logo")
    assert after.observation is not None
    assert any(item.mark == "vendor watermark ACME" for item in after.observation.signals)
    compiled = compile_for(
        build_engine_input(after),
        model_id=CALLER_MODEL,
    )
    prompt = compiled.exact_prompt
    assert "vendor watermark ACME" in prompt
    assert "do not reproduce" in prompt.casefold()
    assert "Observed source marks (do not reproduce)" in prompt


def test_white_bk_generation_does_not_attach_room_pixels() -> None:
    store = InMemoryJobStore()
    generated = _generated_white_bk(store)
    assert generated.engine is not None and generated.engine.result is not None
    assert generated.generation is not None
    parts = generation_user_content(
        generated.generation.operation,
        generated.engine.result,
        {"ref-product": PNG_1X1, "ref-room": PNG_1X1},
    )
    texts = [part["text"] for part in parts if part.get("type") == "text"]
    types = [part["type"] for part in parts]
    assert any("role=Room / target space" in text for text in texts)
    assert any("Do not use this reference as the output scene" in text for text in texts)
    assert types.count("image_url") == 1


def test_critique_fails_white_bk_room_or_logo() -> None:
    store = InMemoryJobStore()
    generated = _generated_white_bk(store)
    room = execute_job_critique(
        store,
        job_id=generated.job_id,
        model_id=CALLER_MODEL,
        provider=FakeCritiqueProvider("white_bk_room"),
    )
    assert room.critique is not None and room.critique.result is not None
    assert room.critique.result.overall_result == "repair_required"
    assert room.critique.result.overall_result not in {"pass", "approved", "released"}
    assert any(item.result == "fail" for item in room.critique.result.scene_compliance)
    assert all(item.result == "pass" for item in room.critique.result.findings if item.dimension == "identity")
    assert room.state != "approved"
    assert room.approval is None
    assert room.releasable is False

    store2 = InMemoryJobStore()
    generated2 = _generated_white_bk(store2)
    logo = execute_job_critique(
        store2,
        job_id=generated2.job_id,
        model_id=CALLER_MODEL,
        provider=FakeCritiqueProvider("white_bk_logo"),
    )
    assert logo.critique is not None and logo.critique.result is not None
    assert logo.critique.result.overall_result == "repair_required"
    assert any(
        item.result == "fail" and "logo" in item.expected.casefold()
        for item in logo.critique.result.scene_compliance
    )


def test_white_bk_critique_pass_requires_output_type_checks() -> None:
    store = InMemoryJobStore()
    generated = _generated_white_bk(store)
    updated = execute_job_critique(
        store,
        job_id=generated.job_id,
        model_id=CALLER_MODEL,
        provider=FakeCritiqueProvider(),
    )
    assessment = updated.critique.result
    assert assessment is not None
    assert assessment.overall_result == "pass"
    assert any("#FFFFFF" in item.expected for item in assessment.scene_compliance)
    assert any("logo" in item.expected.casefold() for item in assessment.scene_compliance)

    critique_input = build_critique_input(updated)
    invented = assessment_for(critique_input).model_dump()
    invented["scene_compliance"] = [
        {
            "section": "scene",
            "result": "pass",
            "observation": "compile prompt asked for white so the image is accepted",
            "expected": "styled interior with flooring",
            "evidence": ["exact_prompt mentioned White BK"],
        }
    ]
    shaped = CritiqueAssessment.model_validate(invented)
    with pytest.raises(CritiqueAssessmentInvalidError, match="background purity"):
        validate_critique_assessment(critique_input, shaped)


def test_lifestyle_generation_and_approval_safeguards_still_work() -> None:
    store = InMemoryJobStore()
    compiled = _lifestyle_compiled(store)
    assert compiled.engine is not None and compiled.engine.result is not None
    prompt = compiled.engine.result.exact_prompt
    assert "Requested output type: Lifestyle" in prompt
    assert "interior with" in prompt
    assert _lifestyle_contract().intent.requested_outcomes == ["Lifestyle"]

    generated = execute_job_generate(
        store, job_id=compiled.job_id, provider=FakeGenerationProvider()
    )
    updated = execute_job_critique(
        store,
        job_id=generated.job_id,
        model_id=CALLER_MODEL,
        provider=FakeCritiqueProvider(),
    )
    assert updated.critique is not None and updated.critique.result is not None
    assert updated.critique.result.overall_result == "pass"
    assert updated.state == "review_pending"
    assert updated.complete is False
    assert updated.approval is None
    assert updated.releasable is False

    approved = approve_job(store, job_id=updated.job_id)
    assert approved.review_status == "owner_approved"
    assert approved.complete is True
    released = release_job(store, job_id=approved.job_id)
    assert released.review_status == "released"
