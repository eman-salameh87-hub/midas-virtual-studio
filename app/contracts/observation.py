"""Declared evidence, unknowns, and conflicts on a Phase-0 contract.

This is not Eye execution. It only records statements the contract is given.

Fact bases observed, published, and inferred come from the canonical atlas
handoff. unknown and conflicted are represented by Unknown and Conflict, not
as product facts. Requested preferences are not facts.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FactBasis = Literal["observed", "published", "inferred"]


class EvidenceStatement(BaseModel):
    """A product or source statement tied to one reference."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1)
    value: str = Field(min_length=1)
    basis: FactBasis
    evidence_reference_id: str = Field(min_length=1)


class Unknown(BaseModel):
    """Something the sources do not establish."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1)
    detail: str = Field(min_length=1)


class Conflict(BaseModel):
    """Two or more claims that remain unresolved."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    subject: str = Field(min_length=1)
    claims: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def claims_are_stated(self) -> "Conflict":
        if any(not claim.strip() for claim in self.claims):
            raise ValueError("conflict claims must be non-empty")
        return self
