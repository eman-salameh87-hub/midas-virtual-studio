import pytest

from app.contracts.job import Phase0JobContract
from app.providers.fake_brain import FakeBrainProvider
from app.providers.fake_engine import FakeEngineCompiler
from app.providers.fake_eye import FakeEyeProvider
from app.providers.fake_generation import FAKE_OUTPUT_BYTES, FAKE_OUTPUT_HASH, FakeGenerationProvider
from app.providers.fake_stylist import FakeStylistProvider
from app.runtime.jobs import (
    BrainNotRunError,
    EngineNotRunError,
    EyeNotRunError,
    GenerationNotReadyError,
    JobOwnerMismatchError,
    RevisionMismatchError,
    StylistNotRunError,
    create_job,
    execute_job_brain,
    execute_job_compile,
    execute_job_eye,
    execute_job_generate,
    execute_job_stylist,
    get_job_generation,
)
from app.runtime.state import InMemoryJobStore
from app.stages.operator import operation_key_for
from tests.png_bytes import PNG_1X1, PNG_HASH

CALLER_MODEL = "caller-supplied-model"
HASH = PNG_HASH


def _contract() -> Phase0JobContract:
    return Phase0JobContract.model_validate(
        {
            "contract_id": "contract-towel-gen-1",
            "revision": 2,
            "owner_id": "owner-1",
            "intent": {
                "mode": "Manual",
                "job_type": "New Project",
                "job_option": "One by one (same department)",
                "requested_outcomes": ["Lifestyle"],
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
                "views": ["Wide view"],
                "image_proportions": "Square · 1:1",
                "resolution": "2K",
                "package_members": ["lifestyle"],
            },
            "changes": {
                "policy_mode": "fidelity-locked",
                "allowed_changes": ["styled setting"],
                "protected_identity": ["towels count"],
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


def _compiled(store: InMemoryJobStore, *, compile_hold: bool = False):
    record = create_job(
        store, _contract(), {"ref-product": PNG_1X1, "ref-room": PNG_1X1}
    )
    execute_job_eye(
        store, job_id=record.job_id, model_id=CALLER_MODEL, provider=FakeEyeProvider("ready")
    )
    execute_job_brain(
        store, job_id=record.job_id, model_id=CALLER_MODEL, provider=FakeBrainProvider()
    )
    execute_job_stylist(
        store, job_id=record.job_id, model_id=CALLER_MODEL, provider=FakeStylistProvider()
    )
    return execute_job_compile(
        store,
        job_id=record.job_id,
        model_id=CALLER_MODEL,
        compiler=FakeEngineCompiler(violation="missing_critical" if compile_hold else None),
    )


def test_generation_cannot_run_without_eye() -> None:
    store = InMemoryJobStore()
    record = create_job(store, _contract(), {"ref-product": PNG_1X1, "ref-room": PNG_1X1})
    with pytest.raises(EyeNotRunError):
        execute_job_generate(store, job_id=record.job_id, provider=FakeGenerationProvider())


def test_generation_cannot_run_without_brain() -> None:
    store = InMemoryJobStore()
    record = create_job(store, _contract(), {"ref-product": PNG_1X1, "ref-room": PNG_1X1})
    execute_job_eye(
        store, job_id=record.job_id, model_id=CALLER_MODEL, provider=FakeEyeProvider("ready")
    )
    with pytest.raises(BrainNotRunError):
        execute_job_generate(store, job_id=record.job_id, provider=FakeGenerationProvider())


def test_generation_cannot_run_without_stylist() -> None:
    store = InMemoryJobStore()
    record = create_job(store, _contract(), {"ref-product": PNG_1X1, "ref-room": PNG_1X1})
    execute_job_eye(
        store, job_id=record.job_id, model_id=CALLER_MODEL, provider=FakeEyeProvider("ready")
    )
    execute_job_brain(
        store, job_id=record.job_id, model_id=CALLER_MODEL, provider=FakeBrainProvider()
    )
    with pytest.raises(StylistNotRunError):
        execute_job_generate(store, job_id=record.job_id, provider=FakeGenerationProvider())


def test_generation_cannot_run_without_compile() -> None:
    store = InMemoryJobStore()
    record = create_job(store, _contract(), {"ref-product": PNG_1X1, "ref-room": PNG_1X1})
    execute_job_eye(
        store, job_id=record.job_id, model_id=CALLER_MODEL, provider=FakeEyeProvider("ready")
    )
    execute_job_brain(
        store, job_id=record.job_id, model_id=CALLER_MODEL, provider=FakeBrainProvider()
    )
    execute_job_stylist(
        store, job_id=record.job_id, model_id=CALLER_MODEL, provider=FakeStylistProvider()
    )
    with pytest.raises(EngineNotRunError):
        execute_job_generate(store, job_id=record.job_id, provider=FakeGenerationProvider())


def test_compile_hold_blocks_generation() -> None:
    store = InMemoryJobStore()
    compiled = _compiled(store, compile_hold=True)
    with pytest.raises(GenerationNotReadyError):
        execute_job_generate(
            store, job_id=compiled.job_id, provider=FakeGenerationProvider()
        )


def test_valid_fake_generation_persists_receipt() -> None:
    store = InMemoryJobStore()
    compiled = _compiled(store)
    provider = FakeGenerationProvider()
    generated = execute_job_generate(
        store, job_id=compiled.job_id, provider=provider
    )
    assert generated.stage == "generate"
    assert generated.state == "ready"
    assert generated.generation is not None
    receipt = generated.generation.receipt
    assert receipt is not None
    assert receipt.status == "completed"
    assert receipt.output is not None
    assert receipt.output.content_hash == FAKE_OUTPUT_HASH
    assert generated.reference_bytes[receipt.output.output_id] == FAKE_OUTPUT_BYTES
    compile_artifact = compiled.engine.result
    assert compile_artifact is not None
    operation = generated.generation.operation
    assert operation.exact_prompt == compile_artifact.exact_prompt
    assert operation.model_id == compile_artifact.model_id
    assert operation.reference_ids == [
        item.reference_id for item in compile_artifact.references
    ]
    assert operation.output_format == compile_artifact.output_format
    assert operation.operation_key == operation_key_for(compile_artifact)
    assert generated.events[-1].kind == "generate_completed"
    assert len(provider.requests) == 1

    loaded = get_job_generation(store, generated.job_id)
    assert loaded.generation is not None
    assert loaded.generation.receipt == receipt
    execute_job_generate(store, job_id=generated.job_id, provider=provider)
    assert len(provider.requests) == 1


def test_uncertain_receipt_is_not_retried() -> None:
    store = InMemoryJobStore()
    compiled = _compiled(store)
    provider = FakeGenerationProvider(mode="uncertain")
    first = execute_job_generate(store, job_id=compiled.job_id, provider=provider)
    assert first.generation is not None
    assert first.generation.receipt is not None
    assert first.generation.receipt.status == "uncertain"
    assert first.generation.receipt.output is None
    assert first.state == "hold"
    second = execute_job_generate(store, job_id=compiled.job_id, provider=provider)
    assert len(provider.requests) == 1
    assert second.generation is not None
    assert second.generation.receipt == first.generation.receipt


def test_missing_capability_holds_without_fabricating_output() -> None:
    store = InMemoryJobStore()
    compiled = _compiled(store)
    provider = FakeGenerationProvider(mode="missing_capability")
    held = execute_job_generate(store, job_id=compiled.job_id, provider=provider)
    assert held.state == "hold"
    assert held.generation is not None
    assert held.generation.receipt is not None
    assert held.generation.receipt.status == "hold"
    assert held.generation.receipt.output is None
    assert len(provider.requests) == 0


def test_owner_and_revision_mismatch() -> None:
    store = InMemoryJobStore()
    compiled = _compiled(store)
    with pytest.raises(JobOwnerMismatchError):
        execute_job_generate(
            store,
            job_id=compiled.job_id,
            provider=FakeGenerationProvider(),
            owner_id="wrong-owner",
        )
    with pytest.raises(RevisionMismatchError):
        execute_job_generate(
            store,
            job_id=compiled.job_id,
            provider=FakeGenerationProvider(),
            revision=99,
        )
