"""One real Image API call. Skipped unless MIDAS_RUN_LIVE_PROVIDER_TEST=1."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from app.contracts.engine import EngineCompile
from app.contracts.generation import GenerationOperation
from app.providers.generation import GenerationProviderRequest
from app.providers.openrouter import OpenRouterGenerationProvider, load_settings
from app.providers.openrouter_images import clear_image_catalog_cache
from app.runtime.pixels import inspect_image, size_matches_tier
from app.stages.operator import apply_pixel_validation

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "bed-product-reference.png"
LIVE_FLAG = "MIDAS_RUN_LIVE_PROVIDER_TEST"
MODEL = "google/gemini-3.1-flash-image"


@pytest.mark.live_provider
def test_live_image_api_sends_2k_16x9_and_measures_the_bytes() -> None:
    if os.getenv(LIVE_FLAG) != "1":
        pytest.skip(f"set {LIVE_FLAG}=1 to run the live Image API proof")
    if not FIXTURE.is_file():
        pytest.fail(f"missing fixture {FIXTURE}")
    settings = load_settings()
    if not settings.api_key.strip():
        pytest.fail("OPENROUTER_API_KEY is empty")
    image = FIXTURE.read_bytes()
    content_hash = hashlib.sha256(image).hexdigest()
    clear_image_catalog_cache()
    compile_artifact = EngineCompile.model_validate(
        {
            "job_id": "job-live-image",
            "contract_id": "contract-live-image",
            "contract_revision": 1,
            "brain_contract_id": "contract-live-image",
            "brain_revision": 1,
            "stylist_contract_id": "contract-live-image",
            "stylist_revision": 1,
            "product_role": "hero",
            "references": [
                {
                    "reference_id": "ref-bed-product",
                    "filename": "bed-product-reference.png",
                    "media_type": "PNG",
                    "hash_algorithm": "sha256",
                    "content_hash": content_hash,
                    "role": "Product / vendor reference",
                }
            ],
            "locks": [
                {"name": "count", "value": "1", "source": "contract", "evidence_reference_id": None},
                {
                    "name": "identity",
                    "value": "bed",
                    "source": "contract",
                    "evidence_reference_id": "ref-bed-product",
                },
                {
                    "name": "source-supported construction",
                    "value": "visible",
                    "source": "eye",
                    "evidence_reference_id": "ref-bed-product",
                },
            ],
            "variables": [],
            "scene": {
                "frame": "Landscape · 16:9",
                "setting": "a quiet bedroom",
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
            "hero_prominence": "the bed is readable",
            "requested_view": "Wide view",
            "view_requirements": {
                "close_up_requirements": None,
                "wide_view_requirements": "full product",
                "detail_focus": None,
            },
            "output_format": {"image_proportions": "Landscape · 16:9", "resolution": "2K"},
            "exact_prompt": "Place the referenced bed in a quiet bedroom. Keep the product identity.",
            "model_id": MODEL,
            "unknowns": [],
            "status": "ready",
            "hold_reasons": [],
        }
    )
    operation = GenerationOperation.model_validate(
        {
            "job_id": compile_artifact.job_id,
            "contract_id": compile_artifact.contract_id,
            "contract_revision": 1,
            "compile_contract_id": compile_artifact.contract_id,
            "compile_revision": 1,
            "operation_key": "cd" * 32,
            "model_id": MODEL,
            "exact_prompt": compile_artifact.exact_prompt,
            "reference_ids": ["ref-bed-product"],
            "requested_view": "Wide view",
            "output_format": {"image_proportions": "Landscape · 16:9", "resolution": "2K"},
            "required_capabilities": [
                "image_generation",
                "multi_reference",
                "exact_prompt",
                "output_format",
            ],
            "claimed_at": "2026-10-08T11:00:00+00:00",
        }
    )
    provider = OpenRouterGenerationProvider(settings)
    result = provider.generate(
        GenerationProviderRequest(
            operation=operation,
            compile=compile_artifact,
            reference_bytes={"ref-bed-product": image},
        )
    )
    audit = provider.request_audit or {}
    print("IMAGE_API_AUDIT", audit)
    print(
        "IMAGE_API_CALL",
        {
            "http_status": provider.last_call.http_status,
            "error_message": provider.last_call.error_message,
            "mapping_mismatches": provider.last_call.mapping_mismatches,
            "response_id": provider.last_call.response_id,
            "request_id": provider.last_call.request_id,
            "model": provider.last_call.model,
        },
    )
    assert audit.get("api") == "/api/v1/images"
    assert audit.get("model") == MODEL
    assert audit.get("resolution") == "2K"
    assert audit.get("aspect_ratio") == "16:9"
    assert audit.get("input_reference_count") == 1
    assert audit.get("output_format_parameter") is None
    assert "api_key" not in audit
    checked = apply_pixel_validation(operation, result)
    receipt = checked.receipt
    assert receipt.provider_request is not None
    assert receipt.provider_request.resolution == "2K"
    assert receipt.provider_request.aspect_ratio == "16:9"
    assert checked.output_bytes
    measured = inspect_image(checked.output_bytes)
    print(
        "IMAGE_API_MEASURED",
        measured.width,
        measured.height,
        measured.mime_type,
        receipt.format_check,
        receipt.status,
    )
    assert measured.width and measured.height
    assert (receipt.measured_width, receipt.measured_height) == (measured.width, measured.height)
    native = size_matches_tier("2K", "16:9", measured.width, measured.height)
    if native:
        assert receipt.format_check == "passed"
        assert receipt.status == "completed"
    else:
        assert receipt.format_check == "failed"
        assert receipt.status == "hold"
