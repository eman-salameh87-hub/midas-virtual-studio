"""Load the historical Living Room Eye standing prompt from MIDAS_SOURCES.

This is provider-proof only. It is not a generalized production Eye prompt.
"""

from __future__ import annotations

import html as html_lib
import re
from pathlib import Path

_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "MIDAS_SOURCES"
    / "evidence"
    / "Midas Look Pipeline Prompts - Living room.html"
)
_START = "You are the Eye of a furniture and home textile product studio."
_END = "Do not write an image prompt."


def living_room_eye_standing_prompt() -> str:
    """Return the standing Eye instructions from the Living Room evidence file."""

    text = _SOURCE.read_text(encoding="utf-8")
    start = text.find(_START)
    end = text.find(_END)
    if start < 0 or end < 0 or end < start:
        raise ValueError(
            "the Living Room Eye standing prompt was not found in MIDAS_SOURCES"
        )
    raw = text[start : end + len(_END)]
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html_lib.unescape(raw)
    prompt = re.sub(r"\s+", " ", raw).strip()
    if not prompt.startswith(_START) or not prompt.endswith(_END):
        raise ValueError("the Living Room Eye standing prompt was altered while loading")
    return prompt
