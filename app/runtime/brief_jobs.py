"""Create Phase-0 jobs from a saved UIMidas brief without rewriting the brief."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.brief_mapping import (
    BriefMappingResult,
    Phase0FieldsNotInBrief,
    ReferenceBytes,
    map_saved_brief_to_phase0_intake,
)
from app.contracts.client_brief import ClientBriefRecord, dump_omitting_optional_nones
from app.runtime.jobs import create_job_from_intake
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
) -> PreparedBriefJob:
    """Map the frozen brief to one Phase-0 job per executable view/output.

    Does not mutate the saved brief. Does not generate images.
    """

    assert brief.brief_hash is not None
    original = dump_omitting_optional_nones(brief.client_brief)
    mapping = map_saved_brief_to_phase0_intake(
        brief.client_brief,
        owner_id=brief.owner_id,
        contract_id=brief.contract_id,
        revision=brief.revision,
        reference_files=reference_files,
        phase0_fields_not_in_brief=phase0_fields_not_in_brief,
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
