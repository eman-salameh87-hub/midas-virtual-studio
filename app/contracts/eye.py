"""Eye observation contract.

The fields are the evidenced Eye observation structure.
A filename, SKU, or hidden attribute is not part of this contract.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CategoryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    name: str = Field(min_length=1)
    confidence_basis: str = Field(min_length=1)


class OriginalProductImage(BaseModel):
    """Image bytes handed to Eye after Phase-0 validation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    media_type: str = Field(min_length=1)
    content: bytes = Field(min_length=1)
    source_role: str = Field(min_length=1)


class EyeObservation(BaseModel):
    """Model-reported evidence. Extra fields are rejected."""

    model_config = ConfigDict(extra="forbid", strict=True)

    source_role: str = Field(min_length=1)
    category_candidates: list[CategoryCandidate]
    visible_features: list[str]
    observed_facts: list[str]
    unknowns: list[str]
    ambiguities: list[str]
    conflicts: list[str]
    parsing_limits: list[str]


EYE_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "source_role",
        "category_candidates",
        "visible_features",
        "observed_facts",
        "unknowns",
        "ambiguities",
        "conflicts",
        "parsing_limits",
    ],
    "properties": {
        "source_role": {"type": "string"},
        "category_candidates": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["name", "confidence_basis"],
                "properties": {
                    "name": {"type": "string"},
                    "confidence_basis": {"type": "string"},
                },
            },
        },
        "visible_features": {"type": "array", "items": {"type": "string"}},
        "observed_facts": {"type": "array", "items": {"type": "string"}},
        "unknowns": {"type": "array", "items": {"type": "string"}},
        "ambiguities": {"type": "array", "items": {"type": "string"}},
        "conflicts": {"type": "array", "items": {"type": "string"}},
        "parsing_limits": {"type": "array", "items": {"type": "string"}},
    },
}
