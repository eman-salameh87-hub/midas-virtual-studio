"""Deterministic fake generation adapter.

It does not call a network, Magnific, or OpenRouter. Completed receipts use a
fixed PNG whose hash is known to tests. Uncertain and capability-missing
paths never claim a successful output.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.contracts.generation import GenerationOutputRef, GenerationReceipt, ProviderCapability
from app.providers.generation import GenerationProviderRequest, GenerationProviderResult
from app.runtime.pixels import expected_pixels, solid_png

FAKE_OUTPUT_BYTES = solid_png(2048, 2048)
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

    def __init__(
        self,
        *,
        mode: str | None = None,
        extra_capabilities: frozenset[ProviderCapability] | set[ProviderCapability] | None = None,
    ) -> None:
        self.mode = mode
        self.extra_capabilities = frozenset(extra_capabilities or ())
        self.requests: list[GenerationProviderRequest] = []

    def capabilities(self) -> frozenset[ProviderCapability]:
        if self.mode == "missing_capability":
            return frozenset()
        return frozenset(FAKE_CAPABILITIES | self.extra_capabilities)

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
        if self.mode == "wrong_size":
            output_bytes = solid_png(1024, 1024)
        else:
            width, height = expected_pixels(operation.output_format)
            output_bytes = solid_png(width, height)
        output_hash = hashlib.sha256(output_bytes).hexdigest()
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
                    content_hash=output_hash,
                ),
                capability_checks=list(self.capabilities()),
                hold_reasons=[],
            ),
            output_bytes=output_bytes,
        )


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
