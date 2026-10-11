"""Measured pixel facts for a generated image.

The requested output specification is compared with the bytes the provider
returned. This module does not resize, upscale, or transcode those bytes.
"""

from __future__ import annotations

import struct
import zlib

from pydantic import BaseModel, ConfigDict

from app.contracts.engine import EngineOutputFormat
from app.contracts.generation import GeneratedMediaType

_LONG_EDGE = {"2K": 2048, "4K": 4096}
_ASPECT_TOKEN = {
    "Square · 1:1": "1:1",
    "Portrait · 4:5": "4:5",
    "Landscape · 16:9": "16:9",
    "3:4": "3:4",
    "4:3": "4:3",
    "9:16": "9:16",
    "2:3": "2:3",
}
# Long-edge bands for a resolution tier. 1K 16:9 is 1376 and must not pass as 2K.
_TIER_LONG_EDGE = {
    "512": (512, 1024),
    "1K": (1024, 2048),
    "2K": (2048, 4096),
    "4K": (4096, 8192),
}
_PNG_CACHE: dict[tuple[int, int], bytes] = {}


class MeasuredImage(BaseModel):
    """Facts read from image bytes. Missing fields mean the bytes were unreadable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    width: int | None
    height: int | None
    image_format: str | None
    mime_type: str | None


def aspect_token(image_proportions: str) -> str | None:
    """Provider aspect token for a MIDAS proportion. Unknown values are not substituted."""

    if image_proportions in _ASPECT_TOKEN:
        return _ASPECT_TOKEN[image_proportions]
    if image_proportions in {
        "1:1",
        "16:9",
        "9:16",
        "4:5",
        "5:4",
        "3:2",
        "2:3",
        "4:3",
        "3:4",
        "21:9",
    }:
        return image_proportions
    return None


def expected_pixels(output_format: EngineOutputFormat) -> tuple[int, int]:
    """Canonical MIDAS pixel target for the requested tier and ratio.

    Square 2K is 2048×2048. Landscape 16:9 at 2K is 2048×1152. A provider may
    return a different native size inside the same tier; size_matches_tier
    accepts that size. This function does not resize anything.
    """

    long_edge = _LONG_EDGE[output_format.resolution]
    token = aspect_token(output_format.image_proportions)
    if token is None:
        raise ValueError(
            f"no pixel policy for image_proportions {output_format.image_proportions!r}"
        )
    ratio = _ratio_value(token)
    if ratio is None:
        raise ValueError(f"invalid aspect token {token!r}")
    if ratio >= 1:
        return long_edge, max(1, round(long_edge / ratio))
    return max(1, round(long_edge * ratio)), long_edge


def aspect_matches(aspect_ratio: str, width: int, height: int) -> bool:
    """True when width/height is within 2 percent of the requested ratio."""

    target = _ratio_value(aspect_ratio)
    if target is None or width < 1 or height < 1:
        return False
    actual = width / height
    return abs(actual - target) / target <= 0.02


def size_matches_tier(resolution: str, aspect_ratio: str, width: int, height: int) -> bool:
    """True when measured pixels are the requested ratio and resolution tier.

    1376×768 is 16:9 at the 1K tier, so it does not satisfy 2K. 2048×1152 and
    a provider-native 2K 16:9 such as 2752×1536 both satisfy 2K.
    """

    band = _TIER_LONG_EDGE.get(resolution)
    if band is None or not aspect_matches(aspect_ratio, width, height):
        return False
    long_edge = max(width, height)
    floor, ceiling = band
    return floor <= long_edge < ceiling


def _ratio_value(aspect_ratio: str) -> float | None:
    if ":" not in aspect_ratio:
        return None
    left, right = aspect_ratio.split(":", 1)
    if not left.isdigit() or not right.isdigit() or int(right) == 0:
        return None
    return int(left) / int(right)


def inspect_image(data: bytes) -> MeasuredImage:
    """Read width, height, format, and mime type from the returned bytes."""

    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        size = _png_size(data)
        return MeasuredImage(
            width=None if size is None else size[0],
            height=None if size is None else size[1],
            image_format="PNG",
            mime_type="image/png",
        )
    if data.startswith(b"\xff\xd8"):
        size = _jpeg_size(data)
        return MeasuredImage(
            width=None if size is None else size[0],
            height=None if size is None else size[1],
            image_format="JPG",
            mime_type="image/jpeg",
        )
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        size = _webp_size(data)
        return MeasuredImage(
            width=None if size is None else size[0],
            height=None if size is None else size[1],
            image_format="WebP",
            mime_type="image/webp",
        )
    return MeasuredImage(
        width=None,
        height=None,
        image_format=None,
        mime_type=None,
    )


def media_types_agree(declared: GeneratedMediaType, measured: MeasuredImage) -> bool:
    if measured.image_format is None:
        return False
    return measured.image_format == declared


def solid_png(width: int, height: int, rgb: tuple[int, int, int] = (255, 255, 255)) -> bytes:
    """Build a solid-color PNG. Used by the fake adapter, not to resize a result."""

    key = (width, height, rgb)
    cached = _PNG_CACHE.get(key)
    if cached is not None:
        return cached
    if width < 1 or height < 1:
        raise ValueError("png dimensions must be positive")

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    row = b"\x00" + bytes(rgb) * width
    raw = row * height
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    encoded = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw, 1))
        + chunk(b"IEND", b"")
    )
    _PNG_CACHE[key] = encoded
    return encoded


def _png_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 24 or data[12:16] != b"IHDR":
        return None
    width, height = struct.unpack(">II", data[16:24])
    if width < 1 or height < 1:
        return None
    return width, height


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    sof = {
        0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
        0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
    }
    index = 2
    length = len(data)
    while index + 8 < length:
        if data[index] != 0xFF:
            index += 1
            continue
        while index < length and data[index] == 0xFF:
            index += 1
        if index >= length:
            return None
        marker = data[index]
        index += 1
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > length:
            return None
        segment = int.from_bytes(data[index : index + 2], "big")
        if segment < 2:
            return None
        if marker in sof and index + 7 <= length:
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            if width > 0 and height > 0:
                return width, height
            return None
        index += segment
    return None


def _webp_size(data: bytes) -> tuple[int, int] | None:
    if len(data) < 30:
        return None
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        if width > 0 and height > 0:
            return width, height
    if chunk == b"VP8 " and len(data) >= 30:
        start = 23
        if data[start : start + 3] == b"\x9d\x01\x2a":
            width = int.from_bytes(data[start + 3 : start + 5], "little") & 0x3FFF
            height = int.from_bytes(data[start + 5 : start + 7], "little") & 0x3FFF
            if width > 0 and height > 0:
                return width, height
    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        if width > 0 and height > 0:
            return width, height
    return None
