"""Deterministic fake generation adapter.

It does not call a network, Magnific, or OpenRouter. Completed receipts use a
fixed PNG whose hash is known to tests. Uncertain and capability-missing
paths never claim a successful output.
"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timezone

from app.contracts.generation import GenerationOutputRef, GenerationReceipt, ProviderCapability
from app.providers.generation import GenerationProviderRequest, GenerationProviderResult

_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
FAKE_OUTPUT_BYTES = base64.b64decode(_PNG_B64)
FAKE_OUTPUT_HASH = hashlib.sha256(FAKE_OUTPUT_BYTES).hexdigest()

FAKE_CAPABILITIES: frozenset[ProviderCapability] = frozenset(
    {
        "image_generation",
        "multi_reference",
        "exact_prompt",
        "output_format",
    }
)


class FakeGenerationProvider:
    """In-memory adapter. `requests` records dispatch attempts only."""

    def __init__(self, *, mode: str | None = None) -> None:
        self.mode = mode
        self.requests: list[GenerationProviderRequest] = []

    def capabilities(self) -> frozenset[ProviderCapability]:
        if self.mode == "missing_capability":
            return frozenset()
        return FAKE_CAPABILITIES

    def generate(self, request: GenerationProviderRequest) -> GenerationProviderResult:
        self.requests.append(request)
        operation = request.operation
        now = _now()
        if self.mode == "uncertain":
            return GenerationProviderResult(
                receipt=GenerationReceipt(
                    operation_key=operation.operation_key,
                    status="uncertain",
                    provider_name="fake",
                    provider_receipt_id=None,
                    claimed_at=operation.claimed_at,
                    submitted_at=now,
                    completed_at=None,
                    retry_classification="reconcile_only",
                    output=None,
                    capability_checks=list(FAKE_CAPABILITIES),
                    hold_reasons=[],
                ),
                output_bytes=None,
            )
        if self.mode == "fail":
            raise RuntimeError("fake generation provider failed")
        output_id = f"gen-{operation.operation_key[:12]}"
        return GenerationProviderResult(
            receipt=GenerationReceipt(
                operation_key=operation.operation_key,
                status="completed",
                provider_name="fake",
                provider_receipt_id=f"fake-receipt-{operation.operation_key[:16]}",
                claimed_at=operation.claimed_at,
                submitted_at=now,
                completed_at=now,
                retry_classification="do_not_retry",
                output=GenerationOutputRef(
                    output_id=output_id,
                    filename=f"{output_id}.png",
                    media_type="PNG",
                    hash_algorithm="sha256",
                    content_hash=FAKE_OUTPUT_HASH,
                ),
                capability_checks=list(FAKE_CAPABILITIES),
                hold_reasons=[],
            ),
            output_bytes=FAKE_OUTPUT_BYTES,
        )


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
