"""Offline parse tests for OpenRouter image responses. No network."""

import base64

from app.contracts.engine import EngineCompile
from app.contracts.generation import GenerationOperation
from app.providers.openrouter import (
    decode_generated_image,
    extract_message_image_urls,
    generation_user_content,
)
from tests.png_bytes import PNG_1X1, PNG_B64, PNG_HASH


def test_extract_message_image_urls_reads_openrouter_shape() -> None:
    data = {
        "id": "gen-1",
        "choices": [
            {
                "message": {
                    "images": [
                        {
                            "image_url": {
                                "url": f"data:image/png;base64,{PNG_B64}",
                            }
                        }
                    ]
                }
            }
        ],
    }
    urls = extract_message_image_urls(data)
    assert urls == [f"data:image/png;base64,{PNG_B64}"]


def test_extract_message_image_urls_empty_without_images() -> None:
    assert extract_message_image_urls({"choices": [{"message": {}}]}) == []
    assert extract_message_image_urls({}) == []


def test_decode_data_url_does_not_fabricate_bytes() -> None:
    data, media = decode_generated_image(f"data:image/png;base64,{PNG_B64}")
    assert data == PNG_1X1
    assert media == "PNG"
    empty, _ = decode_generated_image("data:image/png;base64,")
    assert empty == b""
    missing, _ = decode_generated_image("not-a-url")
    assert missing == b""


def test_generation_content_preserves_prompt_order_and_roles() -> None:
    compile_artifact = EngineCompile.model_validate(
        {
            "job_id": "job-1",
            "contract_id": "c-1",
            "contract_revision": 1,
            "brain_contract_id": "c-1",
            "brain_revision": 1,
            "stylist_contract_id": "c-1",
            "stylist_revision": 1,
            "product_role": "hero",
            "references": [
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
            ],
            "locks": [
                {
                    "name": "count",
                    "value": "1",
                    "source": "contract",
                    "evidence_reference_id": None,
                },
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
                "frame": "Square · 1:1",
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
                "image_proportions": "Square · 1:1",
                "resolution": "2K",
            },
            "exact_prompt": "Preserve identity and count of 1.",
            "model_id": "google/gemini-3.1-flash-image",
            "unknowns": [],
            "status": "ready",
            "hold_reasons": [],
        }
    )
    operation = GenerationOperation.model_validate(
        {
            "job_id": "job-1",
            "contract_id": "c-1",
            "contract_revision": 1,
            "compile_contract_id": "c-1",
            "compile_revision": 1,
            "operation_key": "ab" * 32,
            "model_id": "google/gemini-3.1-flash-image",
            "exact_prompt": compile_artifact.exact_prompt,
            "reference_ids": ["ref-product", "ref-room"],
            "requested_view": "Wide view",
            "output_format": {
                "image_proportions": "Square · 1:1",
                "resolution": "2K",
            },
            "required_capabilities": [
                "image_generation",
                "multi_reference",
                "exact_prompt",
                "output_format",
            ],
            "claimed_at": "2026-10-07T08:00:00+00:00",
        }
    )
    parts = generation_user_content(
        operation,
        compile_artifact,
        {"ref-product": PNG_1X1, "ref-room": PNG_1X1},
    )
    texts = [part["text"] for part in parts if part["type"] == "text"]
    types = [part["type"] for part in parts]
    assert texts[0] == "Preserve identity and count of 1."
    assert "role=Product / vendor reference" in texts[2]
    assert "role=Room / target space" in texts[3]
    assert types == [
        "text",
        "text",
        "text",
        "image_url",
        "text",
        "image_url",
    ]
    assert parts[3]["image_url"]["url"].startswith("data:image/png;base64,")
    assert base64.b64decode(parts[3]["image_url"]["url"].split(",", 1)[1]) == PNG_1X1
