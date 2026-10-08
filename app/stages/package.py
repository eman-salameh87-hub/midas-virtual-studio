"""Delivery manifest for the current candidate.

The manifest is derived from the job record and its generation receipt.
It does not invent approval, release, cost, or metadata that was not recorded.
Multi-member approval is not implemented.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.review import ReviewStatus
from app.runtime.state import JobRecord, StoredCritique, StoredGeneration

CostStatus = Literal["not_recorded"]


class GenerationLineageEntry(BaseModel):
    """One generation in delivery order. Machine ids stay on the receipt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    sequence_index: int = Field(ge=1)
    generation_kind: Literal["initial", "repair"]
    output_id: str | None = None
    parent_generation: int | None = None
    operation_key: str
    provider_receipt_id: str | None = None
    provider: str | None = None
    model_id: str
    source_hashes: list[dict[str, str]]
    requested_width: int | None = None
    requested_height: int | None = None
    actual_width: int | None = None
    actual_height: int | None = None
    actual_mime: str | None = None
    actual_format: str | None = None
    sha256: str | None = None
    observed_checksum: str | None = None
    checksum_status: str
    status: str
    timestamp: str | None = None
    artifact_path: str | None = None
    output_valid: bool
    requested_resolution: str | None = None
    requested_aspect_ratio: str | None = None
    submitted_api: str | None = None
    submitted_resolution: str | None = None
    submitted_aspect_ratio: str | None = None
    submitted_reference_count: int | None = None
    measured_aspect_ratio: str | None = None


class DeliveryManifest(BaseModel):
    """Auditable package projection. cost is null when no charge was recorded."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: str
    owner_id: str
    contract_id: str
    revision: int
    request_hash: str | None
    package_status: ReviewStatus | None
    complete: bool
    current_generation: GenerationLineageEntry | None
    generation_history: list[GenerationLineageEntry]
    generation_sequence: list[int]
    current_image_path: str | None
    actual_width: int | None = None
    actual_height: int | None = None
    actual_mime: str | None = None
    actual_format: str | None = None
    checksum: str | None = None
    checksum_status: str = "unverified"
    parent_generation: int | None = None
    model_id: str | None = None
    provider: str | None = None
    provider_receipt_id: str | None = None
    exact_prompt: str | None = None
    requested_view: str | None = None
    requested_width: int | None = None
    requested_height: int | None = None
    requested_resolution: str | None = None
    requested_aspect_ratio: str | None = None
    submitted_api: str | None = None
    submitted_resolution: str | None = None
    submitted_aspect_ratio: str | None = None
    submitted_reference_count: int | None = None
    measured_aspect_ratio: str | None = None
    references: list[dict[str, object]]
    critique_result: str | None = None
    critique_generation_output_id: str | None = None
    repair_history: list[dict[str, object]]
    review_status: ReviewStatus | None
    approval: dict[str, object] | None = None
    release: dict[str, object] | None = None
    unknowns: list[dict[str, str]]
    cost: None = None
    cost_status: CostStatus = "not_recorded"
    output_valid: bool = False
    consistency_notes: list[str] = Field(default_factory=list)


def package_status(record: JobRecord) -> ReviewStatus | None:
    """Lifecycle of the current candidate. Critique pass is review_pending."""

    return record.review_status


def package_is_complete(record: JobRecord) -> bool:
    """True only after an explicit owner approval record exists."""

    return bool(record.complete and record.approval is not None)


def generation_lineage(record: JobRecord) -> list[GenerationLineageEntry]:
    """History then current generation. The first entry has no parent."""

    from app.runtime.artifacts import generation_artifact_name

    versions = _versions(record)
    hashes = {
        item.reference_id: item.content_hash for item in record.contract.references
    }
    entries: list[GenerationLineageEntry] = []
    for index, stored in versions:
        receipt = stored.receipt
        output = receipt.output if receipt is not None else None
        media = output.media_type if output is not None else None
        path = generation_artifact_name(index, media) if media is not None else None
        valid = (
            stored.checksum_status == "matched"
            and output is not None
            and receipt is not None
            and receipt.status == "completed"
        )
        entries.append(
            GenerationLineageEntry(
                sequence_index=index,
                generation_kind="initial" if index == 1 else "repair",
                output_id=output.output_id if output is not None else None,
                parent_generation=None if index == 1 else index - 1,
                operation_key=stored.operation.operation_key,
                provider_receipt_id=receipt.provider_receipt_id if receipt else None,
                provider=receipt.provider_name if receipt else None,
                model_id=stored.operation.model_id,
                source_hashes=[
                    {"reference_id": reference_id, "content_hash": hashes[reference_id]}
                    for reference_id in stored.operation.reference_ids
                    if reference_id in hashes
                ],
                requested_width=receipt.requested_width if receipt else None,
                requested_height=receipt.requested_height if receipt else None,
                actual_width=receipt.measured_width if receipt else None,
                actual_height=receipt.measured_height if receipt else None,
                actual_mime=receipt.measured_mime if receipt else None,
                actual_format=receipt.measured_format if receipt else None,
                sha256=output.content_hash if output is not None else None,
                observed_checksum=stored.observed_checksum,
                checksum_status=stored.checksum_status,
                status=stored.status,
                timestamp=(
                    receipt.completed_at or receipt.claimed_at if receipt is not None else None
                ),
                artifact_path=path,
                output_valid=valid,
                requested_resolution=(
                    stored.operation.output_format.resolution
                ),
                requested_aspect_ratio=stored.operation.output_format.image_proportions,
                submitted_api=None if receipt is None or receipt.provider_request is None else receipt.provider_request.api,
                submitted_resolution=(
                    None if receipt is None or receipt.provider_request is None else receipt.provider_request.resolution
                ),
                submitted_aspect_ratio=(
                    None if receipt is None or receipt.provider_request is None else receipt.provider_request.aspect_ratio
                ),
                submitted_reference_count=(
                    None
                    if receipt is None or receipt.provider_request is None
                    else receipt.provider_request.input_reference_count
                ),
                measured_aspect_ratio=None if receipt is None else receipt.measured_aspect_ratio,
            )
        )
    return entries


def build_delivery_manifest(record: JobRecord) -> DeliveryManifest:
    """Project the current job. Missing approval, release, and cost stay empty."""

    from app.runtime.artifacts import output_filename

    lineage = generation_lineage(record)
    current = lineage[-1] if lineage else None
    history = lineage[:-1] if lineage else []
    notes = _consistency_notes(record, lineage)
    output_valid = bool(current and current.output_valid and not notes)
    image_path = None
    if current is not None and record.generation is not None:
        receipt = record.generation.receipt
        if receipt is not None and receipt.output is not None:
            image_path = f"output/{output_filename(receipt.output.media_type).replace('generated', 'current')}"
    critique = record.critique.result if record.critique is not None else None
    approval = None
    if record.approval is not None:
        approval = {
            "owner_id": record.approval.owner_id,
            "approved_at": record.approval.approved_at,
            "revision": record.approval.revision,
            "generation_output_id": record.approval.generation_output_id,
            "request_hash": record.approval.request_hash,
        }
    release = None
    if record.release is not None:
        release = {
            "owner_id": record.release.owner_id,
            "generation_output_id": record.release.generation_output_id,
            "released_at": record.release.released_at,
        }
    identity = record.contract.request_identity
    complete = package_is_complete(record) and output_valid
    return DeliveryManifest(
        job_id=record.job_id,
        owner_id=record.owner_id,
        contract_id=record.contract.contract_id,
        revision=record.revision,
        request_hash=None if identity is None else identity.request_hash,
        package_status=package_status(record),
        complete=complete,
        current_generation=current,
        generation_history=history,
        generation_sequence=[item.sequence_index for item in lineage],
        current_image_path=image_path,
        actual_width=None if current is None else current.actual_width,
        actual_height=None if current is None else current.actual_height,
        actual_mime=None if current is None else current.actual_mime,
        actual_format=None if current is None else current.actual_format,
        checksum=None if current is None else current.sha256,
        checksum_status="unverified" if current is None else current.checksum_status,
        parent_generation=None if current is None else current.parent_generation,
        model_id=None if current is None else current.model_id,
        provider=None if current is None else current.provider,
        provider_receipt_id=None if current is None else current.provider_receipt_id,
        exact_prompt=(
            record.generation.operation.exact_prompt if record.generation is not None else None
        ),
        requested_view=(
            record.generation.operation.requested_view if record.generation is not None else None
        ),
        requested_width=None if current is None else current.requested_width,
        requested_height=None if current is None else current.requested_height,
        requested_resolution=None if current is None else current.requested_resolution,
        requested_aspect_ratio=None if current is None else current.requested_aspect_ratio,
        submitted_api=None if current is None else current.submitted_api,
        submitted_resolution=None if current is None else current.submitted_resolution,
        submitted_aspect_ratio=None if current is None else current.submitted_aspect_ratio,
        submitted_reference_count=None if current is None else current.submitted_reference_count,
        measured_aspect_ratio=None if current is None else current.measured_aspect_ratio,
        references=[item.model_dump(mode="json") for item in record.reference_measurements],
        critique_result=None if critique is None else critique.overall_result,
        critique_generation_output_id=(
            None if critique is None else critique.generation_output_id
        ),
        repair_history=[
            {
                "repair_count": item.plan.repair_count,
                "action": item.plan.action,
                "status": item.status,
                "source_generation_output_id": item.plan.source_generation_output_id,
                "result_generation_output_id": item.plan.lineage.result_generation_output_id,
                "scene_base_reference": item.plan.scene_base_reference,
                "product_authority_reference": item.plan.product_authority_reference,
            }
            for item in record.repairs
        ],
        review_status=record.review_status,
        approval=approval,
        release=release,
        unknowns=[
            {"subject": item.subject, "detail": item.detail} for item in record.contract.unknowns
        ],
        cost=None,
        cost_status="not_recorded",
        output_valid=output_valid,
        consistency_notes=notes,
    )


def _versions(record: JobRecord) -> list[tuple[int, StoredGeneration]]:
    items = list(record.generation_history)
    current = record.generation
    if current is not None:
        key = current.operation.operation_key
        if not any(item.operation.operation_key == key for item in items):
            items.append(current)
    return [(index, item) for index, item in enumerate(items, start=1)]


def _consistency_notes(
    record: JobRecord, lineage: list[GenerationLineageEntry]
) -> list[str]:
    notes: list[str] = []
    if not lineage:
        return notes
    current = lineage[-1]
    for index, entry in enumerate(lineage, start=1):
        if entry.sequence_index != index:
            notes.append("generation sequence is not contiguous")
        expected_parent = None if index == 1 else index - 1
        if entry.parent_generation != expected_parent:
            notes.append(f"generation {index} parent does not match the previous version")
        if index == 1 and entry.generation_kind != "initial":
            notes.append("first generation is not initial")
        if index > 1 and entry.generation_kind != "repair":
            notes.append(f"generation {index} is not a repair")
    critique = record.critique.result if record.critique is not None else None
    if critique is not None and current.output_id is not None:
        if critique.generation_output_id != current.output_id and not _critique_matches_lineage(
            critique.generation_output_id, lineage
        ):
            notes.append("critique does not reference a recorded generation")
    if current.checksum_status == "mismatch":
        notes.append("current image checksum does not match the stored receipt")
    return notes


def _critique_matches_lineage(output_id: str, lineage: list[GenerationLineageEntry]) -> bool:
    return any(item.output_id == output_id for item in lineage)


def critique_assessed_output(stored: StoredCritique) -> str | None:
    if stored.result is None:
        return None
    return stored.result.generation_output_id
