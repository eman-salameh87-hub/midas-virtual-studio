"""Explicit job execution mode. Never inferred from filenames or prompt text.

``user`` is the default. Only an explicit environment value of ``evaluation``
selects isolated evaluation storage. Tests may also call ``set_execution_mode``.
"""

from __future__ import annotations

import os
import tempfile
import threading
from pathlib import Path

USER = "user"
EVALUATION = "evaluation"
_ENV = "MIDAS_EXECUTION_MODE"
_EVAL_DIR_ENV = "MIDAS_EVALUATION_OUTPUTS_DIR"

_lock = threading.Lock()
_override: str | None = None
_eval_temp: Path | None = None


def execution_mode() -> str:
    with _lock:
        if _override in {USER, EVALUATION}:
            return _override
    raw = os.getenv(_ENV, USER)
    value = (raw or USER).strip().casefold()
    return EVALUATION if value == EVALUATION else USER


def set_execution_mode(mode: str | None) -> None:
    """Tests set an explicit mode. None restores environment lookup."""

    global _override
    with _lock:
        if mode is None:
            _override = None
            return
        cleaned = mode.strip().casefold()
        if cleaned not in {USER, EVALUATION}:
            raise ValueError("execution mode must be user or evaluation")
        _override = cleaned


def is_evaluation_mode() -> bool:
    return execution_mode() == EVALUATION


def evaluation_outputs_root() -> Path:
    """Isolated directory for evaluation artifacts. Never the user outputs/ tree."""

    env = os.getenv(_EVAL_DIR_ENV)
    if env and env.strip():
        return Path(env.strip())
    global _eval_temp
    with _lock:
        if _eval_temp is None:
            _eval_temp = Path(tempfile.mkdtemp(prefix="midas-evaluation-outputs-"))
        return _eval_temp


def reset_execution_mode() -> None:
    global _override, _eval_temp
    with _lock:
        _override = None
        _eval_temp = None
