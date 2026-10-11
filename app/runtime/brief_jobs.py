"""Create Phase-0 jobs from a saved UIMidas brief without rewriting the brief."""

from __future__ import annotations

import base64
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.brief_mapping import (
    BriefMappingResult,
    MISSING_REFERENCE_BYTES,
    MappingIssue,
    Phase0FieldsNotInBrief,
    ReferenceBytes,
    map_saved_brief_to_phase0_intake,
)
from app.contracts.client_brief import ClientBriefRecord, dump_omitting_optional_nones
from app.runtime.catalogue_images import (
    HttpGet,
    Resolver,
    ingest_brief_catalogue_images,
    midas_library_reference_ids,
    resolve_host_addresses,
)
from app.runtime.jobs import create_job_from_intake
from app.runtime.midas_catalogue import CatalogueProduct
from app.runtime.state import JobRecord, JobStore


class BriefJobPrepareError(Exception):
    def __init__(self, result: BriefMappingResult) -> None:
        self.result = result
        super().__init__("brief mapping unresolved")


class PreparedBriefJob(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    brief_id: str = Field(min_length=1)
    brief_hash: str = Field(min_length=1)
    client_brief: dict[str, object]
    job: JobRecord
    jobs: list[JobRecord]


def prepare_job_from_saved_brief(
    job_store: JobStore,
    brief: ClientBriefRecord,
    *,
    reference_files: list[ReferenceBytes],
    phase0_fields_not_in_brief: Phase0FieldsNotInBrief | None,
    catalogue: Mapping[str, CatalogueProduct] | None = None,
    catalogue_http_get: HttpGet | None = None,
    catalogue_resolver: Resolver | None = None,
) -> PreparedBriefJob:
    """Map the frozen brief to one Phase-0 job per executable view/output.

    Does not mutate the saved brief. Does not generate images.
    Catalogue references are resolved from the trusted catalogue and fetched
    server-side. Client-supplied bytes for those ids are ignored.
    """

    assert brief.brief_hash is not None
    original = dump_omitting_optional_nones(brief.client_brief)
    midas_ids = midas_library_reference_ids(brief.client_brief)
    local_files = [row for row in reference_files if row.reference_id not in midas_ids]
    ingested, ingest_errors = ingest_brief_catalogue_images(
        brief.client_brief,
        catalogue=catalogue,
        http_get=catalogue_http_get,
        resolver=catalogue_resolver or resolve_host_addresses,
    )
    ingest_issues = [
        MappingIssue(code=error.code, field=error.field, message=error.message)
        for error in ingest_errors
    ]
    catalogue_files = [
        ReferenceBytes(
            reference_id=row.reference_id,
            content_base64=base64.b64encode(row.content).decode("ascii"),
            media_type=row.media_type,
        )
        for row in ingested
    ]
    catalogue_products = {row.reference_id: row.product for row in ingested}
    mapping = map_saved_brief_to_phase0_intake(
        brief.client_brief,
        owner_id=brief.owner_id,
        contract_id=brief.contract_id,
        revision=brief.revision,
        reference_files=[*local_files, *catalogue_files],
        phase0_fields_not_in_brief=phase0_fields_not_in_brief,
        catalogue_products=catalogue_products,
    )
    if ingest_issues:
        extra = [issue for issue in mapping.issues if issue.code != MISSING_REFERENCE_BYTES]
        mapping = BriefMappingResult(
            issues=[*ingest_issues, *extra],
            intake=None,
            intakes=[],
        )
    if mapping.issues or not mapping.intakes:
        raise BriefJobPrepareError(mapping)
    records = [create_job_from_intake(job_store, intake) for intake in mapping.intakes]
    if dump_omitting_optional_nones(brief.client_brief) != original:
        raise RuntimeError("saved brief was mutated during job prepare")
    return PreparedBriefJob(
        brief_id=brief.brief_id,
        brief_hash=brief.brief_hash,
        client_brief=original,
        job=records[0],
        jobs=records,
    )
