"""Load the historical Living Room Eye standing prompt from a tracked asset.

The extract is taken from the evidence file
``Midas Look Pipeline Prompts - Living room.html``. That corpus stays
authoritative and is not read at runtime. This module is provider-proof
only. It is not a generalized production Eye prompt.
"""

from __future__ import annotations

import html as html_lib
import re
from pathlib import Path

_ASSET = (
    Path(__file__).resolve().parent / "assets" / "living_room_eye_standing_prompt.txt"
)
_START = "You are the Eye of a furniture and home textile product studio."
_END = "Do not write an image prompt."


def extract_living_room_eye_standing_prompt(html: str) -> str:
    """Extract the standing Eye prompt from Living Room evidence HTML.

    For source verification only. Production loading must not call this.
    """

    start = html.find(_START)
    end = html.find(_END)
    if start < 0 or end < 0 or end < start:
        raise ValueError("the Living Room Eye standing prompt was not found in the HTML")
    raw = html[start : end + len(_END)]
    raw = re.sub(r"<[^>]+>", "", raw)
    raw = html_lib.unescape(raw)
    prompt = re.sub(r"\s+", " ", raw).strip()
    return _require_markers(prompt)


def living_room_eye_standing_prompt() -> str:
    """Return the standing Eye instructions from the tracked application asset."""

    text = _ASSET.read_text(encoding="utf-8")
    if text.endswith("\n"):
        text = text[:-1]
    return _require_markers(text)


def _require_markers(prompt: str) -> str:
    if not prompt.startswith(_START) or not prompt.endswith(_END):
        raise ValueError("the Living Room Eye standing prompt was altered while loading")
    return prompt
