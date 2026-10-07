"""Generation operation and Operator receipt.

Canonical Operator · execute (framework.json / two-architectures.txt role 15)
saves: operation key, claim, receipt, status, timestamps, and retry
classification. Those sources do not publish a field-level JSON schema.

This is the typed claim/receipt for one EngineCompile dispatch. It does not
critique, repair, or release. Costs/billing are not part of this vertical
slice. Magnific and OpenRouter request blobs are not accepted.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.contracts.engine import EngineOutputFormat
from app.contracts.job import OutputView

GenerationStatus = Literal["claimed", "completed", "failed", "hold", "uncertain"]
RetryClassification = Literal[
    "do_not_retry",
    "retry_if_never_started",
    "reconcile_only",
]
ProviderCapability = Literal[
    "image_generation",
    "multi_reference",
    "exact_prompt",
    "output_format",
]
GeneratedMediaType = Literal["JPG", "PNG", "WebP"]


def _sha256(value: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(
            "content_hash must be an explicit lowercase sha256 hex digest; "
            "the contract does not compute one"
        )
    return value


def _reject_blank(values: list[str], field_name: str) -> None:
    if any(not value.strip() for value in values):
        raise ValueError(f"{field_name} cannot contain a blank entry")


class GenerationOutputRef(BaseModel):
    """Identity of one generated candidate. Bytes are stored on the job, not here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    output_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    media_type: GeneratedMediaType
    hash_algorithm: Literal["sha256"]
    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def hash_is_sha256(cls, value: str) -> str:
        return _sha256(value)


class GenerationOperation(BaseModel):
    """Claimed render operation bound to one EngineCompile revision.

    operation_key is the idempotency key. The same compile must not dispatch
    a second paid call while a claim, receipt, or uncertain result exists.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    contract_revision: int = Field(ge=1)
    compile_contract_id: str = Field(min_length=1)
    compile_revision: int = Field(ge=1)
    operation_key: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    exact_prompt: str = Field(min_length=1)
    reference_ids: list[str] = Field(min_length=1)
    requested_view: OutputView
    output_format: EngineOutputFormat
    required_capabilities: list[ProviderCapability] = Field(min_length=1)
    claimed_at: str = Field(min_length=1)

    @model_validator(mode="after")
    def operation_binds_compile(self) -> "GenerationOperation":
        if self.compile_contract_id != self.contract_id:
            raise ValueError("Generation operation must bind the same contract as EngineCompile")
        if self.compile_revision != self.contract_revision:
            raise ValueError("Generation operation must bind the same revision as EngineCompile")
        if len(self.reference_ids) != len(set(self.reference_ids)):
            raise ValueError("reference_ids must be unique and ordered")
        _reject_blank(list(self.reference_ids), "reference_ids")
        if "image_generation" not in self.required_capabilities:
            raise ValueError("Generation operation requires image_generation capability")
        if not self.exact_prompt.strip():
            raise ValueError("Generation operation must carry the Engine exact_prompt")
        if not self.model_id.strip():
            raise ValueError("Generation operation must record the Engine model_id")
        return self


class GenerationReceipt(BaseModel):
    """Provider receipt for one claimed operation. Never a quality approval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    operation_key: str = Field(min_length=1)
    status: GenerationStatus
    provider_name: str = Field(min_length=1)
    provider_receipt_id: str | None
    claimed_at: str = Field(min_length=1)
    submitted_at: str | None
    completed_at: str | None
    retry_classification: RetryClassification
    output: GenerationOutputRef | None
    capability_checks: list[ProviderCapability]
    hold_reasons: list[str]

    @model_validator(mode="after")
    def receipt_matches_status(self) -> "GenerationReceipt":
        _reject_blank(self.hold_reasons, "hold_reasons")
        if self.status == "completed":
            if self.output is None:
                raise ValueError("a completed generation receipt must include an output reference")
            if self.hold_reasons:
                raise ValueError("a completed generation receipt must not have hold reasons")
            if not self.submitted_at or not self.completed_at:
                raise ValueError("a completed generation receipt needs submitted_at and completed_at")
            if not self.provider_receipt_id:
                raise ValueError("a completed generation receipt needs a provider receipt id")
        elif self.status == "hold":
            if not self.hold_reasons:
                raise ValueError("a held generation receipt must specify at least one hold reason")
            if self.output is not None:
                raise ValueError("a held generation receipt must not claim an output")
        elif self.status == "uncertain":
            if self.output is not None:
                raise ValueError("an uncertain receipt must not claim a generated output")
            if self.retry_classification != "reconcile_only":
                raise ValueError("an uncertain receipt must be classified reconcile_only")
        elif self.status == "claimed":
            if self.output is not None:
                raise ValueError("a claimed operation must not include a generated output")
        elif self.status == "failed":
            if self.output is not None:
                raise ValueError("a failed receipt must not claim a generated output")
        return self
