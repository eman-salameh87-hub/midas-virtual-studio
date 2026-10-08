"""Measured source metadata. Unknown view and components stay null."""

from __future__ import annotations

from app.contracts.eye import EyeObservation
from app.contracts.job import Phase0JobContract
from app.contracts.reference import ReferenceMeasurement
from app.runtime.checksum import sha256_hex
from app.runtime.pixels import inspect_image

_VIEW_SUBJECTS = {"view", "source view", "shown view"}


def measure_references(
    contract: Phase0JobContract,
    reference_bytes: dict[str, bytes],
    observation: EyeObservation | None = None,
) -> list[ReferenceMeasurement]:
    """Measure bytes that exist. Do not rename files or fill unknown facts."""

    measurements: list[ReferenceMeasurement] = []
    for reference in contract.references:
        data = reference_bytes.get(reference.reference_id)
        observed = sha256_hex(data) if data else None
        if observed is None:
            checksum_status = "unverified"
        elif observed == reference.content_hash:
            checksum_status = "matched"
        else:
            checksum_status = "mismatch"
        inspected = inspect_image(data) if data else None
        measurements.append(
            ReferenceMeasurement(
                reference_id=reference.reference_id,
                filename=reference.filename,
                declared_media_type=reference.media_type,
                actual_mime=None if inspected is None else inspected.mime_type,
                actual_format=None if inspected is None else inspected.image_format,
                width=None if inspected is None else inspected.width,
                height=None if inspected is None else inspected.height,
                content_hash=reference.content_hash,
                observed_checksum=observed,
                checksum_status=checksum_status,
                source_view=_source_view(contract, reference.reference_id),
                product_components=_product_components(observation, reference.reference_id),
                evidence_reference_id=reference.reference_id,
            )
        )
    return measurements


def retain_stored_measurements(
    stored: list[ReferenceMeasurement],
    reference_bytes: dict[str, bytes],
) -> list[ReferenceMeasurement]:
    """Note a checksum mismatch without replacing stored dimensions or hashes."""

    updated: list[ReferenceMeasurement] = []
    for item in stored:
        data = reference_bytes.get(item.reference_id)
        if not data:
            updated.append(item)
            continue
        observed = sha256_hex(data)
        status = "matched" if observed == item.content_hash else "mismatch"
        updated.append(
            item.model_copy(
                update={"observed_checksum": observed, "checksum_status": status}
            )
        )
    return updated


def _source_view(contract: Phase0JobContract, reference_id: str) -> str | None:
    values = [
        statement.value
        for statement in contract.statements
        if statement.evidence_reference_id == reference_id
        and statement.subject.casefold().strip() in _VIEW_SUBJECTS
    ]
    if not values:
        return None
    return values[0]


def _product_components(
    observation: EyeObservation | None, reference_id: str
) -> list[str] | None:
    if observation is None:
        return None
    names = [
        item.name
        for item in observation.items
        if item.evidence_reference_id == reference_id and item.name.strip()
    ]
    if not names:
        return None
    return names
