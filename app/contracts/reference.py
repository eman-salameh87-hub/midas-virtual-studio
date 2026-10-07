"""Original and reference asset identity for a Phase-0 job contract.

Reference roles are the six client reference types in the canonical Create
snapshot. The workflow atlas also shows an explanatory Eye handoff list
(product_identity, target_room, specification, catalogue_support, inspiration,
previous_result). That list is not an emitted contract, and it does not match
the client labels, so those ids are not accepted as aliases.

Historical evidence roles such as original_product and owner_original are not
copied into this contract.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ReferenceRole = Literal[
    "Product / vendor reference",
    "Room / target space",
    "Inspiration / look",
    "Previous result",
    "Other views / pieces",
    "Specifications / Excel",
]

MediaType = Literal["JPG", "PNG", "WebP", "PDF", "XLS", "XLSX", "CSV"]

HashAlgorithm = Literal["sha256"]


class ReferenceAsset(BaseModel):
    """Identity of one original or reference. Bytes are not stored."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reference_id: str = Field(min_length=1)
    filename: str = Field(min_length=1)
    media_type: MediaType
    hash_algorithm: HashAlgorithm
    content_hash: str
    role: ReferenceRole

    @field_validator("content_hash")
    @classmethod
    def sha256_hex(cls, value: str) -> str:
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ValueError(
                "content_hash must be an explicit lowercase sha256 hex digest; "
                "the contract does not compute one"
            )
        return value
