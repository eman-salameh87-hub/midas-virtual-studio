import pytest
from pydantic import ValidationError

from app.contracts.generation import GenerationOperation, GenerationReceipt


def _operation() -> dict:
    return {
        "job_id": "job-1",
        "contract_id": "contract-1",
        "contract_revision": 1,
        "compile_contract_id": "contract-1",
        "compile_revision": 1,
        "operation_key": "ab" * 32,
        "model_id": "caller-supplied-model",
        "exact_prompt": "Preserve identity and count.",
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


def _completed_receipt() -> dict:
    return {
        "operation_key": "ab" * 32,
        "status": "completed",
        "provider_name": "fake",
        "provider_receipt_id": "fake-1",
        "claimed_at": "2026-10-07T08:00:00+00:00",
        "submitted_at": "2026-10-07T08:00:01+00:00",
        "completed_at": "2026-10-07T08:00:02+00:00",
        "retry_classification": "do_not_retry",
        "output": {
            "output_id": "gen-1",
            "filename": "gen-1.png",
            "media_type": "PNG",
            "hash_algorithm": "sha256",
            "content_hash": "cd" * 32,
        },
        "capability_checks": ["image_generation"],
        "hold_reasons": [],
    }


def test_valid_generation_operation_and_receipt() -> None:
    operation = GenerationOperation.model_validate(_operation())
    receipt = GenerationReceipt.model_validate(_completed_receipt())
    assert operation.reference_ids == ["ref-product", "ref-room"]
    assert receipt.output is not None
    assert receipt.status == "completed"


def test_operation_requires_image_generation_capability() -> None:
    payload = _operation()
    payload["required_capabilities"] = ["multi_reference"]
    with pytest.raises(ValidationError, match="image_generation"):
        GenerationOperation.model_validate(payload)


def test_completed_receipt_cannot_omit_output() -> None:
    payload = _completed_receipt()
    payload["output"] = None
    with pytest.raises(ValidationError, match="output reference"):
        GenerationReceipt.model_validate(payload)


def test_uncertain_receipt_cannot_claim_output() -> None:
    payload = _completed_receipt()
    payload["status"] = "uncertain"
    payload["retry_classification"] = "reconcile_only"
    payload["completed_at"] = None
    payload["provider_receipt_id"] = None
    with pytest.raises(ValidationError, match="uncertain receipt"):
        GenerationReceipt.model_validate(payload)
    payload["output"] = None
    receipt = GenerationReceipt.model_validate(payload)
    assert receipt.status == "uncertain"


def test_hold_requires_reasons() -> None:
    payload = _completed_receipt()
    payload["status"] = "hold"
    payload["output"] = None
    payload["hold_reasons"] = []
    payload["provider_receipt_id"] = None
    payload["submitted_at"] = None
    payload["completed_at"] = None
    with pytest.raises(ValidationError, match="hold reason"):
        GenerationReceipt.model_validate(payload)


def test_provider_specific_fields_rejected() -> None:
    payload = _completed_receipt()
    payload["magnfic_settings"] = {}
    with pytest.raises(ValidationError):
        GenerationReceipt.model_validate(payload)
