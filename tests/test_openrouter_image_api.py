"""Image API settings are provider parameters, then checked against the bytes."""

import base64
import hashlib

import httpx
import pytest

from app.contracts.engine import EngineCompile
from app.contracts.generation import GenerationOperation, GenerationReceipt
from app.providers.generation import GenerationProviderRequest, GenerationProviderResult
from app.providers.openrouter import OpenRouterGenerationProvider, OpenRouterSettings
from app.providers.openrouter_images import (
    ImageModelCapabilities,
    clear_image_catalog_cache,
    prepare_image_request,
    provider_cost_evidence,
    remember_image_catalog,
)
from app.runtime.pixels import aspect_token, size_matches_tier, solid_png
from app.stages.operator import (
    GenerationInvalidError,
    apply_pixel_validation,
    existing_operation_blocks_dispatch,
    validate_generation_receipt,
)
from app.stages.repair import build_repair_generation_operation
from tests.png_bytes import PNG_1X1, PNG_HASH

MODEL = "google/gemini-3.1-flash-image"
_RATIOS = (
    "1:1",
    "16:9",
    "9:16",
    "4:5",
    "5:4",
    "3:2",
    "2:3",
    "4:3",
    "3:4",
    "21:9",
)


def setup_function() -> None:
    clear_image_catalog_cache()


def _capabilities(**overrides: object) -> ImageModelCapabilities:
    values = dict(
        model_id=MODEL,
        resolutions=("512", "1K", "2K", "4K"),
        aspect_ratios=_RATIOS,
        max_input_references=14,
        max_outputs=1,
        output_formats=None,
        supports_resolution=True,
        supports_aspect_ratio=True,
        supports_input_references=True,
    )
    values.update(overrides)
    return ImageModelCapabilities(**values)  # type: ignore[arg-type]


def _compile(
    *,
    proportions: str = "Landscape · 16:9",
    resolution: str = "2K",
    references: list[dict[str, str]] | None = None,
) -> EngineCompile:
    if references is None:
        references = [
            {
                "reference_id": "ref-product",
                "filename": "product.png",
                "media_type": "PNG",
                "hash_algorithm": "sha256",
                "content_hash": PNG_HASH,
                "role": "Product / vendor reference",
            }
        ]
    return EngineCompile.model_validate(
        {
            "job_id": "job-1",
            "contract_id": "c-1",
            "contract_revision": 1,
            "brain_contract_id": "c-1",
            "brain_revision": 1,
            "stylist_contract_id": "c-1",
            "stylist_revision": 1,
            "product_role": "hero",
            "references": references,
            "locks": [
                {"name": "count", "value": "1", "source": "contract", "evidence_reference_id": None},
                {
                    "name": "identity",
                    "value": "product",
                    "source": "contract",
                    "evidence_reference_id": "ref-product",
                },
                {
                    "name": "source-supported construction",
                    "value": "visible",
                    "source": "eye",
                    "evidence_reference_id": "ref-product",
                },
            ],
            "variables": [],
            "scene": {
                "frame": proportions,
                "setting": "a room",
                "light": "daylight",
                "camera": "eye-level",
                "presentation": "hero readable",
            },
            "selected_layout": {
                "board_id": "board-1",
                "focal_hierarchy": "hero",
                "palette": "neutral",
                "spacing": "open",
                "surfaces": "oak",
                "lighting": "daylight",
                "circulation": "clear",
                "arrangement_detail": "centered",
                "functional_use": "usable",
            },
            "hero_prominence": "hero is readable",
            "requested_view": "Wide view",
            "view_requirements": {
                "close_up_requirements": None,
                "wide_view_requirements": "full product",
                "detail_focus": None,
            },
            "output_format": {
                "image_proportions": proportions,
                "resolution": resolution,
            },
            "exact_prompt": "Preserve identity and count of 1.",
            "model_id": MODEL,
            "unknowns": [],
            "status": "ready",
            "hold_reasons": [],
        }
    )


def _operation(compile_artifact: EngineCompile, *, prompt: str | None = None) -> GenerationOperation:
    return GenerationOperation.model_validate(
        {
            "job_id": compile_artifact.job_id,
            "contract_id": compile_artifact.contract_id,
            "contract_revision": compile_artifact.contract_revision,
            "compile_contract_id": compile_artifact.contract_id,
            "compile_revision": compile_artifact.contract_revision,
            "operation_key": "ab" * 32,
            "model_id": compile_artifact.model_id,
            "exact_prompt": prompt or compile_artifact.exact_prompt,
            "reference_ids": [item.reference_id for item in compile_artifact.references],
            "requested_view": compile_artifact.requested_view,
            "output_format": compile_artifact.output_format.model_dump(mode="json"),
            "required_capabilities": [
                "image_generation",
                "multi_reference",
                "exact_prompt",
                "output_format",
            ],
            "claimed_at": "2026-10-08T10:00:00+00:00",
        }
    )


def _bytes_for(compile_artifact: EngineCompile) -> dict[str, bytes]:
    return {item.reference_id: PNG_1X1 for item in compile_artifact.references}


@pytest.mark.parametrize(
    ("proportions", "token"),
    [
        ("Square · 1:1", "1:1"),
        ("Landscape · 16:9", "16:9"),
        ("Portrait · 4:5", "4:5"),
        ("9:16", "9:16"),
        ("3:2", "3:2"),
        ("4:3", "4:3"),
    ],
)
def test_aspect_tokens_are_not_substituted(proportions: str, token: str) -> None:
    assert aspect_token(proportions) == token
    assert aspect_token("ultrawide") is None


@pytest.mark.parametrize(
    ("resolution", "width", "height", "accepted"),
    [
        ("512", 512, 512, True),
        ("1K", 1376, 768, True),
        ("2K", 2048, 1152, True),
        ("2K", 2752, 1536, True),
        ("2K", 1376, 768, False),
        ("4K", 5504, 3072, True),
        ("4K", 2048, 1152, False),
    ],
)
def test_resolution_tier_accepts_native_sizes_and_rejects_the_lower_tier(
    resolution: str, width: int, height: int, accepted: bool
) -> None:
    assert size_matches_tier(resolution, "16:9" if width != height else "1:1", width, height) is accepted


def test_image_request_sends_resolution_aspect_and_references() -> None:
    compile_artifact = _compile()
    room = {
        "reference_id": "ref-room",
        "filename": "room.png",
        "media_type": "PNG",
        "hash_algorithm": "sha256",
        "content_hash": PNG_HASH,
        "role": "Room / target space",
    }
    compile_artifact = _compile(
        references=[
            compile_artifact.references[0].model_dump(mode="json"),
            room,
        ]
    )
    prepared = prepare_image_request(
        _operation(compile_artifact),
        compile_artifact,
        _bytes_for(compile_artifact),
        _capabilities(),
    )
    assert prepared.body["model"] == MODEL
    assert prepared.body["resolution"] == "2K"
    assert prepared.body["aspect_ratio"] == "16:9"
    assert "output_format" not in prepared.body
    assert "quality" not in prepared.body
    assert "modalities" not in prepared.body
    refs = prepared.body["input_references"]
    assert len(refs) == 2
    assert prepared.audit.reference_roles == [
        "Product / vendor reference",
        "Room / target space",
    ]
    assert prepared.audit.api == "/api/v1/images"
    assert prepared.audit.input_reference_count == 2
    first = refs[0]["image_url"]["url"]
    assert first.startswith("data:image/png;base64,")
    assert base64.b64decode(first.split(",", 1)[1]) == PNG_1X1
    assert "Product / vendor reference" in prepared.body["prompt"]
    assert "OPENROUTER" not in prepared.body["prompt"]


@pytest.mark.parametrize(
    ("proportions", "resolution", "aspect"),
    [
        ("Square · 1:1", "2K", "1:1"),
        ("Square · 1:1", "4K", "1:1"),
        ("Portrait · 4:5", "2K", "4:5"),
        ("Landscape · 16:9", "4K", "16:9"),
    ],
)
def test_compiled_output_settings_become_provider_parameters(
    proportions: str, resolution: str, aspect: str
) -> None:
    compile_artifact = _compile(proportions=proportions, resolution=resolution)
    prepared = prepare_image_request(
        _operation(compile_artifact),
        compile_artifact,
        _bytes_for(compile_artifact),
        _capabilities(),
    )
    assert prepared.body["resolution"] == resolution
    assert prepared.body["aspect_ratio"] == aspect


def test_unsupported_resolution_or_ratio_does_not_call_the_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    def _post(*_args: object, **_kwargs: object) -> dict[str, object]:
        calls.append(True)
        raise AssertionError("provider was called")

    monkeypatch.setattr("app.providers.openrouter_images.post_image", _post)
    remember_image_catalog({MODEL: _capabilities(resolutions=("1K",), aspect_ratios=("1:1",))})
    provider = OpenRouterGenerationProvider(
        OpenRouterSettings(api_key="test-key", base_url="https://openrouter.ai/api/v1", timeout_seconds=5)
    )
    compile_artifact = _compile()
    result = provider.generate(
        GenerationProviderRequest(
            operation=_operation(compile_artifact),
            compile=compile_artifact,
            reference_bytes=_bytes_for(compile_artifact),
        )
    )
    assert calls == []
    assert result.receipt.status == "hold"
    assert result.output_bytes is None
    assert any("resolution" in reason for reason in result.receipt.hold_reasons)
    assert any("16:9" in reason for reason in result.receipt.hold_reasons)
    assert MODEL in result.receipt.hold_reasons[0] or any(MODEL in reason for reason in result.receipt.hold_reasons)


def test_too_many_references_does_not_call_the_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.providers.openrouter_images.post_image",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("provider was called")),
    )
    remember_image_catalog({MODEL: _capabilities(max_input_references=1)})
    compile_artifact = _compile(
        references=[
            {
                "reference_id": "ref-product",
                "filename": "product.png",
                "media_type": "PNG",
                "hash_algorithm": "sha256",
                "content_hash": PNG_HASH,
                "role": "Product / vendor reference",
            },
            {
                "reference_id": "ref-room",
                "filename": "room.png",
                "media_type": "PNG",
                "hash_algorithm": "sha256",
                "content_hash": PNG_HASH,
                "role": "Room / target space",
            },
        ]
    )
    provider = OpenRouterGenerationProvider(
        OpenRouterSettings(api_key="test-key", base_url="https://openrouter.ai/api/v1", timeout_seconds=5)
    )
    result = provider.generate(
        GenerationProviderRequest(
            operation=_operation(compile_artifact),
            compile=compile_artifact,
            reference_bytes=_bytes_for(compile_artifact),
        )
    )
    assert result.receipt.status == "hold"
    assert "max input_references" in result.receipt.hold_reasons[0]


def test_1376_by_768_holds_and_native_2k_passes() -> None:
    compile_artifact = _compile()
    operation = _operation(compile_artifact)
    prepared = prepare_image_request(
        operation, compile_artifact, _bytes_for(compile_artifact), _capabilities()
    )
    low = solid_png(1376, 768)
    low_result = apply_pixel_validation(
        operation,
        _completed(operation, low, prepared.audit),
    )
    assert low_result.receipt.status == "hold"
    assert low_result.receipt.format_check == "failed"
    assert (low_result.receipt.measured_width, low_result.receipt.measured_height) == (1376, 768)
    assert low_result.receipt.measured_aspect_ratio == "16:9"
    assert low_result.output_bytes == low

    native = solid_png(2752, 1536)
    native_result = apply_pixel_validation(
        operation,
        _completed(operation, native, prepared.audit),
    )
    assert native_result.receipt.status == "completed"
    assert native_result.receipt.format_check == "passed"
    assert (native_result.receipt.measured_width, native_result.receipt.measured_height) == (2752, 1536)
    assert native_result.receipt.provider_request is not None
    assert native_result.receipt.provider_request.resolution == "2K"
    assert native_result.receipt.provider_request.aspect_ratio == "16:9"


def test_repair_keeps_the_compiled_resolution_and_aspect() -> None:
    compile_artifact = _compile(proportions="Landscape · 16:9", resolution="2K")
    initial = prepare_image_request(
        _operation(compile_artifact),
        compile_artifact,
        _bytes_for(compile_artifact),
        _capabilities(),
    )
    repair_prompt = (
        compile_artifact.exact_prompt
        + "\n\nMIDAS bounded repair. Restore the named defect only."
    )
    repaired = prepare_image_request(
        _operation(compile_artifact, prompt=repair_prompt),
        compile_artifact,
        _bytes_for(compile_artifact),
        _capabilities(),
    )
    assert repaired.body["resolution"] == initial.body["resolution"] == "2K"
    assert repaired.body["aspect_ratio"] == initial.body["aspect_ratio"] == "16:9"
    assert repaired.body["prompt"] != initial.body["prompt"]
    assert build_repair_generation_operation is not None


def test_model_mismatch_is_still_rejected() -> None:
    compile_artifact = _compile()
    operation = _operation(compile_artifact).model_copy(update={"model_id": "other/model"})
    prepared = prepare_image_request(
        _operation(compile_artifact),
        compile_artifact,
        _bytes_for(compile_artifact),
        _capabilities(),
    )
    native = solid_png(2048, 1152)
    result = apply_pixel_validation(operation, _completed(operation, native, prepared.audit))
    with pytest.raises(GenerationInvalidError, match="model_id"):
        validate_generation_receipt(operation, compile_artifact, result)


def test_receipt_settings_round_trip_and_old_receipts_still_load() -> None:
    compile_artifact = _compile()
    operation = _operation(compile_artifact)
    prepared = prepare_image_request(
        operation, compile_artifact, _bytes_for(compile_artifact), _capabilities()
    )
    checked = apply_pixel_validation(
        operation,
        _completed(operation, solid_png(2048, 1152), prepared.audit),
    )
    restored = GenerationReceipt.model_validate(checked.receipt.model_dump(mode="json"))
    assert restored.provider_request is not None
    assert restored.provider_request.resolution == "2K"
    assert restored.requested_width == 2048
    assert restored.measured_width == 2048
    legacy = GenerationReceipt.model_validate(
        {
            "operation_key": "ab" * 32,
            "status": "completed",
            "provider_name": "openrouter",
            "provider_receipt_id": "gen-old",
            "claimed_at": "2026-10-07T08:00:00+00:00",
            "submitted_at": "2026-10-07T08:00:01+00:00",
            "completed_at": "2026-10-07T08:00:02+00:00",
            "retry_classification": "do_not_retry",
            "output": {
                "output_id": "gen-old",
                "filename": "gen-old.png",
                "media_type": "PNG",
                "hash_algorithm": "sha256",
                "content_hash": PNG_HASH,
            },
            "capability_checks": ["image_generation"],
            "hold_reasons": [],
            "format_check": "unmeasured",
        }
    )
    assert legacy.provider_request is None
    assert legacy.measured_width is None


def _provider() -> OpenRouterGenerationProvider:
    remember_image_catalog({MODEL: _capabilities()})
    return OpenRouterGenerationProvider(
        OpenRouterSettings(
            api_key="test-key",
            base_url="https://openrouter.ai/api/v1",
            timeout_seconds=5,
        )
    )


def _generate(provider: OpenRouterGenerationProvider) -> GenerationProviderResult:
    compile_artifact = _compile()
    return provider.generate(
        GenerationProviderRequest(
            operation=_operation(compile_artifact),
            compile=compile_artifact,
            reference_bytes=_bytes_for(compile_artifact),
        )
    )


def test_openrouter_cost_is_stored_only_when_the_response_reports_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded = base64.b64encode(PNG_1X1).decode("ascii")

    def _with_cost(_settings: object, _body: object, record: object, **_kwargs: object) -> dict[str, object]:
        record.http_status = 200  # type: ignore[attr-defined]
        return {
            "data": [{"b64_json": encoded, "media_type": "image/png"}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3, "cost": 0.04, "currency": "USD"},
        }

    monkeypatch.setattr("app.providers.openrouter_images.post_image", _with_cost)
    known = _generate(_provider())
    assert known.receipt.status == "completed"
    assert known.receipt.provider_cost is not None
    assert known.receipt.provider_cost.status == "known"
    assert known.receipt.provider_cost.amount == 0.04
    assert known.receipt.provider_cost.currency == "USD"
    assert known.receipt.provider_usage is not None
    assert known.receipt.provider_usage.total_tokens == 3

    def _without_cost(_settings: object, _body: object, record: object, **_kwargs: object) -> dict[str, object]:
        record.http_status = 200  # type: ignore[attr-defined]
        return {"data": [{"b64_json": encoded, "media_type": "image/png"}], "usage": {"total_tokens": 3}}

    monkeypatch.setattr("app.providers.openrouter_images.post_image", _without_cost)
    unknown = _generate(_provider())
    assert unknown.receipt.provider_cost is not None
    assert unknown.receipt.provider_cost.status == "unknown"
    assert unknown.receipt.provider_cost.amount is None
    assert unknown.receipt.provider_cost.currency is None
    absent = provider_cost_evidence({"data": []})
    assert absent[0].status == "unknown"
    assert absent[0].amount is None


def test_http_rejection_is_not_an_ambiguous_generation(monkeypatch: pytest.MonkeyPatch) -> None:
    def _post(_settings: object, _body: object, record: object, **_kwargs: object) -> dict[str, object]:
        record.http_status = 402  # type: ignore[attr-defined]
        record.error_message = "Insufficient credits"  # type: ignore[attr-defined]
        raise RuntimeError("Insufficient credits")

    monkeypatch.setattr("app.providers.openrouter_images.post_image", _post)
    result = _generate(_provider())
    assert result.receipt.status == "failed"
    assert result.receipt.retry_classification == "retry_if_never_started"
    assert result.receipt.output is None
    assert result.receipt.provider_receipt_id is None
    assert result.receipt.provider_request is not None
    assert result.receipt.provider_request.resolution == "2K"
    assert "HTTP 402" in result.receipt.hold_reasons[0]
    assert "Insufficient credits" in result.receipt.hold_reasons[0]
    assert existing_operation_blocks_dispatch(result.receipt) is False


def test_timeout_and_connection_loss_stay_reconcile_only(monkeypatch: pytest.MonkeyPatch) -> None:
    def _timeout(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr("app.providers.openrouter_images.post_image", _timeout)
    timed_out = _generate(_provider())
    assert timed_out.receipt.status == "uncertain"
    assert timed_out.receipt.retry_classification == "reconcile_only"
    assert timed_out.receipt.output is None
    assert timed_out.receipt.hold_reasons == ["OpenRouter generation timed out"]
    assert existing_operation_blocks_dispatch(timed_out.receipt) is True

    def _reset(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise httpx.RemoteProtocolError("connection closed")

    monkeypatch.setattr("app.providers.openrouter_images.post_image", _reset)
    dropped = _generate(_provider())
    assert dropped.receipt.status == "uncertain"
    assert dropped.receipt.retry_classification == "reconcile_only"
    assert "RemoteProtocolError" in dropped.receipt.hold_reasons[0]
    assert existing_operation_blocks_dispatch(dropped.receipt) is True


def test_server_error_stays_uncertain_and_records_the_status(monkeypatch: pytest.MonkeyPatch) -> None:
    def _post(_settings: object, _body: object, record: object, **_kwargs: object) -> dict[str, object]:
        record.http_status = 500  # type: ignore[attr-defined]
        record.error_message = "upstream failed"  # type: ignore[attr-defined]
        raise RuntimeError("upstream failed")

    monkeypatch.setattr("app.providers.openrouter_images.post_image", _post)
    result = _generate(_provider())
    assert result.receipt.status == "uncertain"
    assert result.receipt.retry_classification == "reconcile_only"
    assert "HTTP 500" in result.receipt.hold_reasons[0]
    assert existing_operation_blocks_dispatch(result.receipt) is True


def test_complete_response_without_image_bytes_can_be_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    def _post(_settings: object, _body: object, record: object, **_kwargs: object) -> dict[str, object]:
        record.http_status = 200  # type: ignore[attr-defined]
        return {"created": 1, "data": [{}]}

    monkeypatch.setattr("app.providers.openrouter_images.post_image", _post)
    result = _generate(_provider())
    assert result.receipt.status == "failed"
    assert result.receipt.retry_classification == "retry_if_never_started"
    assert result.receipt.output is None
    assert "b64_json" in result.receipt.hold_reasons[0]
    assert existing_operation_blocks_dispatch(result.receipt) is False


def _completed(operation: GenerationOperation, data: bytes, audit: object) -> GenerationProviderResult:
    digest = hashlib.sha256(data).hexdigest()
    return GenerationProviderResult(
        receipt=GenerationReceipt(
            operation_key=operation.operation_key,
            status="completed",
            provider_name="openrouter",
            provider_receipt_id="gen-test",
            claimed_at=operation.claimed_at,
            submitted_at=operation.claimed_at,
            completed_at=operation.claimed_at,
            retry_classification="do_not_retry",
            output={
                "output_id": "gen-test",
                "filename": "gen-test.png",
                "media_type": "PNG",
                "hash_algorithm": "sha256",
                "content_hash": digest,
            },
            capability_checks=["image_generation"],
            hold_reasons=[],
            provider_request=audit,  # type: ignore[arg-type]
        ),
        output_bytes=data,
    )
