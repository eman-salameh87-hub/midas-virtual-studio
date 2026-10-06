"""Phase-0 job contract.

Only evidenced fields are stored. Extra keys are rejected.
Option catalogs are not loaded, and unresolved fields are not invented.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Reference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    filename: str | None = None
    sha256: str | None = None
    media_type: str | None = None

    @field_validator("id", "role")
    @classmethod
    def _required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Required text is blank.")
        return value


class Phase0Job(BaseModel):
    """Frozen client inputs evidenced for Phase-0."""

    model_config = ConfigDict(extra="forbid", strict=True)

    taxonomy_node_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    product_role: str = Field(min_length=1)
    references: list[Reference] = Field(default_factory=list)
    lighting: str | None = None
    wall_paint: str | None = None
    floor: str | None = None
    mood: str | None = None
    plants: bool
    human: bool
    input_condition: str | None = None

    @field_validator("taxonomy_node_id", "profile_id", "product_role")
    @classmethod
    def _required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Required text is blank.")
        return value

    @field_validator("lighting", "wall_paint", "floor", "mood", "input_condition")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("Blank values are not accepted.")
        return value

    @model_validator(mode="after")
    def _unique_reference_ids(self) -> Phase0Job:
        seen: set[str] = set()
        for reference in self.references:
            if reference.id in seen:
                raise ValueError(f"Duplicate reference id '{reference.id}'.")
            seen.add(reference.id)
        return self


def validate_phase0(data: dict[str, object]) -> Phase0Job:
    """Validate a Phase-0 job. Unresolved keys fail instead of being stored."""

    return Phase0Job.model_validate(data)
