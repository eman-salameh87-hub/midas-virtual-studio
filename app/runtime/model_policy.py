"""Backend-owned model policy and caller model validation.

Public API endpoints expose caller-controlled model_id inputs with Swagger
defaults from this centralized policy. Callers may override model_id within
the configured/allowed models for each stage.

Override defaults or allowed lists with environment variables when needed.
Empty values fall back to proven defaults.
"""

from __future__ import annotations

import os
from typing import Set

DEFAULT_PLANNING_MODEL = "openai/gpt-4.1"
DEFAULT_IMAGE_MODEL = "google/gemini-3.1-flash-image"

DEFAULT_PLANNING_MODELS: tuple[str, ...] = (DEFAULT_PLANNING_MODEL,)
DEFAULT_IMAGE_MODELS: tuple[str, ...] = (DEFAULT_IMAGE_MODEL,)

_ENV_EYE = "MIDAS_EYE_MODEL"
_ENV_BRAIN = "MIDAS_BRAIN_MODEL"
_ENV_STYLIST = "MIDAS_STYLIST_MODEL"
_ENV_CRITIQUE = "MIDAS_CRITIQUE_MODEL"
_ENV_IMAGE = "MIDAS_IMAGE_MODEL"
_ENV_ALLOWED_MODELS = "MIDAS_ALLOWED_MODELS"
_ENV_ALLOWED_PLANNING = "MIDAS_ALLOWED_PLANNING_MODELS"
_ENV_ALLOWED_IMAGE = "MIDAS_ALLOWED_IMAGE_MODELS"


def _from_env(name: str, default: str) -> str:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip()
    return value or default


def _list_from_env(name: str) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def eye_model() -> str:
    return _from_env(_ENV_EYE, DEFAULT_PLANNING_MODEL)


def brain_model() -> str:
    return _from_env(_ENV_BRAIN, DEFAULT_PLANNING_MODEL)


def stylist_model() -> str:
    return _from_env(_ENV_STYLIST, DEFAULT_PLANNING_MODEL)


def critique_model() -> str:
    return _from_env(_ENV_CRITIQUE, DEFAULT_PLANNING_MODEL)


def image_model() -> str:
    return _from_env(_ENV_IMAGE, DEFAULT_IMAGE_MODEL)


def default_model_for_stage(stage: str) -> str:
    normalized = stage.lower().strip()
    if normalized == "eye":
        return eye_model()
    if normalized == "brain":
        return brain_model()
    if normalized == "stylist":
        return stylist_model()
    if normalized == "critique":
        return critique_model()
    if normalized in {"compile", "generate", "repair"}:
        return image_model()
    raise ValueError(f"Unknown stage: '{stage}'")


def allowed_models_for_stage(stage: str) -> set[str]:
    normalized = stage.lower().strip()
    if normalized in {"eye", "brain", "stylist", "critique"}:
        allowed: set[str] = set(DEFAULT_PLANNING_MODELS)
        allowed.add(eye_model())
        allowed.add(brain_model())
        allowed.add(stylist_model())
        allowed.add(critique_model())
        allowed.update(_list_from_env(_ENV_ALLOWED_PLANNING))
        allowed.update(_list_from_env(_ENV_ALLOWED_MODELS))
        return allowed
    if normalized in {"compile", "generate", "repair"}:
        allowed = set(DEFAULT_IMAGE_MODELS)
        allowed.add(image_model())
        allowed.update(_list_from_env(_ENV_ALLOWED_IMAGE))
        allowed.update(_list_from_env(_ENV_ALLOWED_MODELS))
        return allowed
    raise ValueError(f"Unknown stage: '{stage}'")


def validate_stage_model(stage: str, model_id: str | None) -> str:
    if not model_id or not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("model_id must be a non-empty string")
    cleaned = model_id.strip()
    allowed = allowed_models_for_stage(stage)
    if cleaned not in allowed:
        allowed_desc = ", ".join(sorted(allowed))
        raise ValueError(
            f"Model '{cleaned}' is not configured or allowed for stage '{stage}'. "
            f"Allowed model(s) for '{stage}': {allowed_desc}"
        )
    return cleaned

