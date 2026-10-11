"""Owner review boundary for one critiqued candidate.

Critique pass, owner approval, and release are different records.
A passing critique does not create approval. Historical jobs without an
approval record stay unapproved.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ReviewStatus = Literal[
    "generation_completed",
    "critique_passed",
    "review_pending",
    "owner_approved",
    "released",
    "hold",
]


class PreGenerationApproval(BaseModel):
    """Owner authorization to spend one render. This is not a release approval.

    The job contract has no expiry field. expires_at stays null unless the
    approval itself was given an explicit timestamp.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    request_hash: str = Field(min_length=64, max_length=64)
    render_count: int = Field(ge=1)
    approved_at: str = Field(min_length=1)
    expires_at: str | None = None


class OwnerApproval(BaseModel):
    """Explicit owner approval. This object is not inferred from critique."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner_id: str = Field(min_length=1)
    contract_id: str = Field(min_length=1)
    revision: int = Field(ge=1)
    request_hash: str = Field(min_length=64, max_length=64)
    generation_output_id: str = Field(min_length=1)
    approved_at: str = Field(min_length=1)


class PackageRelease(BaseModel):
    """Explicit release of an already approved candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    owner_id: str = Field(min_length=1)
    generation_output_id: str = Field(min_length=1)
    released_at: str = Field(min_length=1)
