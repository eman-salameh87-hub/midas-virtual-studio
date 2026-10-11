"""Tracked Eye standing-prompt asset. No live providers. No corpus required except one skippable check."""

from __future__ import annotations

import hashlib
import inspect
from pathlib import Path

import pytest

from app.providers import living_room_eye_prompt as prompt_mod
from app.providers.living_room_eye_prompt import (
    extract_living_room_eye_standing_prompt,
    living_room_eye_standing_prompt,
)

EXPECTED_SHA256 = "84f114ea4bffb25d596e170740d02dd5d17c321ba51cae0e6f1a4e49bdd04408"
EXPECTED_LENGTH = 2558
_START = "You are the Eye of a furniture and home textile product studio."
_END = "Do not write an image prompt."
ASSET = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "providers"
    / "assets"
    / "living_room_eye_standing_prompt.txt"
)
CORPUS = (
    Path(__file__).resolve().parents[1]
    / "MIDAS_SOURCES"
    / "evidence"
    / "Midas Look Pipeline Prompts - Living room.html"
)


def _asset_prompt_bytes() -> bytes:
    raw = ASSET.read_bytes()
    if raw.endswith(b"\n"):
        raw = raw[:-1]
    if raw.endswith(b"\n"):
        raise AssertionError("asset may include at most one trailing newline")
    return raw


def test_asset_matches_expected_hash_length_and_markers() -> None:
    raw = _asset_prompt_bytes()
    prompt = raw.decode("utf-8")
    assert len(prompt) == EXPECTED_LENGTH
    assert hashlib.sha256(raw).hexdigest() == EXPECTED_SHA256
    assert prompt.startswith(_START)
    assert prompt.endswith(_END)
    assert living_room_eye_standing_prompt() == prompt


def test_missing_asset_raises_without_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing = tmp_path / "missing_living_room_eye_standing_prompt.txt"
    monkeypatch.setattr(prompt_mod, "_ASSET", missing)
    with pytest.raises(FileNotFoundError):
        living_room_eye_standing_prompt()


def test_invalid_asset_raises_without_fallback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    invalid = tmp_path / "living_room_eye_standing_prompt.txt"
    invalid.write_text("not the living room eye standing prompt\n", encoding="utf-8")
    monkeypatch.setattr(prompt_mod, "_ASSET", invalid)
    with pytest.raises(ValueError, match="altered while loading"):
        living_room_eye_standing_prompt()


def test_production_loader_does_not_access_midas_sources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reads: list[str] = []
    original = Path.read_text

    def tracking(self: Path, *args: object, **kwargs: object) -> str:
        reads.append(self.as_posix())
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", tracking)
    living_room_eye_standing_prompt()
    assert reads
    assert all("MIDAS_SOURCES" not in path for path in reads)
    source = inspect.getsource(living_room_eye_standing_prompt)
    assert "MIDAS_SOURCES" not in source
    assert "extract_living_room_eye_standing_prompt" not in source


@pytest.mark.skipif(not CORPUS.is_file(), reason="ignored MIDAS_SOURCES corpus is absent")
def test_extract_equals_asset_when_corpus_present() -> None:
    html = CORPUS.read_text(encoding="utf-8")
    assert extract_living_room_eye_standing_prompt(html) == living_room_eye_standing_prompt()
