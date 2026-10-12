"""Production reference intake without a paid vision provider.

Catalogue products are trusted Midas furniture/interior SKUs. Local images are
validated as decodable JPG/PNG/WebP and otherwise fail closed as uncertain —
never silently accepted as furniture. Excel/specification kinds skip vision.
"""

from __future__ import annotations

import base64
import binascii

from app.providers.reference_intake import (
    NOT_FURNITURE_MESSAGE,
    UNCERTAIN_MESSAGE,
    ReferenceIntakeRequest,
    ReferenceIntakeResult,
    constrain_intake_result,
)
from app.runtime.item_taxonomy import match_taxonomy
from app.runtime.midas_catalogue import lookup_catalogue_product

_JPEG = b"\xff\xd8\xff"
_PNG = b"\x89PNG\r\n\x1a\n"
_WEBP = b"WEBP"


def _decode_image(raw_b64: str | None) -> bytes | None:
    if not raw_b64 or not raw_b64.strip():
        return None
    try:
        return base64.b64decode(raw_b64, validate=False)
    except (binascii.Error, ValueError):
        return None


def _is_supported_image(data: bytes) -> bool:
    if data.startswith(_JPEG) or data.startswith(_PNG):
        return True
    return len(data) >= 12 and data[8:12] == _WEBP


class FailClosedReferenceIntakeProvider:
    def analyze(self, request: ReferenceIntakeRequest) -> ReferenceIntakeResult:
        kind = (request.intended_kind or "").strip()
        if kind == "specification_file":
            return constrain_intake_result(
                ReferenceIntakeResult(
                    status="skipped",
                    relevant=True,
                    needs_confirmation=False,
                    suggested_reference_type="specification_file",
                    department=None,
                    category=None,
                    subcategory=None,
                    message="Specification files are not image-analyzed.",
                )
            )
        key = (request.library_key or "").strip()
        if key:
            product = lookup_catalogue_product(key)
            if product is None:
                return constrain_intake_result(
                    ReferenceIntakeResult(
                        status="rejected",
                        relevant=False,
                        needs_confirmation=False,
                        suggested_reference_type=None,
                        department=None,
                        category=None,
                        subcategory=None,
                        message=NOT_FURNITURE_MESSAGE,
                    )
                )
            department, category, subcategory = match_taxonomy(
                product.name, product.product_url
            )
            return constrain_intake_result(
                ReferenceIntakeResult(
                    status="accepted",
                    relevant=True,
                    needs_confirmation=False,
                    suggested_reference_type="product_image",
                    department=department,
                    category=category,
                    subcategory=subcategory,
                    message="Midas catalogue product selected as a product / vendor reference.",
                )
            )
        data = _decode_image(request.content_base64)
        if data is None or not _is_supported_image(data):
            return constrain_intake_result(
                ReferenceIntakeResult(
                    status="rejected",
                    relevant=False,
                    needs_confirmation=False,
                    suggested_reference_type=None,
                    department=None,
                    category=None,
                    subcategory=None,
                    message=NOT_FURNITURE_MESSAGE,
                )
            )
        return constrain_intake_result(
            ReferenceIntakeResult(
                status="uncertain",
                relevant=False,
                needs_confirmation=True,
                suggested_reference_type=None,
                department=None,
                category=None,
                subcategory=None,
                message=UNCERTAIN_MESSAGE,
            )
        )
