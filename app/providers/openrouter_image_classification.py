"""Classify a furniture/interior image via the Eye OpenRouter chat path.

Reuses ``eye_model()``, ``load_settings()``, and ``complete_chat_object``.
Does not construct EyeInput, call OpenRouterEyeProvider.observe, or run
Brain/Stylist/any job stage.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Callable

from app.providers.fail_closed_reference_intake import _decode_image, _is_supported_image
from app.providers.image_classification import map_classification_payload
from app.providers.openrouter import OpenRouterCallRecord, OpenRouterSettings, complete_chat_object, load_settings
from app.providers.reference_intake import (
    NOT_FURNITURE_MESSAGE,
    ReferenceIntakeRequest,
    ReferenceIntakeResult,
    constrain_intake_result,
)
from app.runtime.item_taxonomy import IMAGE_REFERENCE_TYPES, taxonomy_option_catalog
from app.runtime.model_policy import eye_model

ChatComplete = Callable[[OpenRouterSettings, dict[str, Any], OpenRouterCallRecord], dict[str, Any]]

_MEDIA = {
    "image/jpeg": "image/jpeg",
    "image/jpg": "image/jpeg",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "image/png": "image/png",
    "png": "image/png",
    "image/webp": "image/webp",
    "webp": "image/webp",
}

_SYSTEM = """You classify one product or interior photograph for a furniture studio.

Decide whether the image is relevant furniture, a furniture product, a room, or interior-design reference material.
Reject unrelated people, vehicles, landscapes, food, documents, and other out-of-scope subjects.

Use only the supplied department/category/sub-category ids. Never invent ids or labels.
Use only these reference types:
- product_image: Product / vendor reference
- room_image: Room / target space
- inspiration: Inspiration / look
- previous_result: Previous result
- other_view: Other views / pieces

Do not classify from a filename. Judge only the attached image.
Return a JSON object with keys:
relevant (boolean), status (accepted|rejected|uncertain), needs_confirmation (boolean),
department (id or null), category (id or null), subcategory (id or null),
suggested_reference_type (one of the types above or null), message (short string).
If you are not sure the image is in-scope, set relevant=false or status=uncertain.
"""


class OpenRouterImageClassificationProvider:
    def __init__(
        self,
        settings: OpenRouterSettings | None = None,
        *,
        model_id: str | None = None,
        complete: ChatComplete | None = None,
    ) -> None:
        self.settings = settings or load_settings()
        self.model_id = (model_id or eye_model()).strip()
        self._complete = complete or complete_chat_object
        self.last_call = OpenRouterCallRecord()

    def analyze(self, request: ReferenceIntakeRequest) -> ReferenceIntakeResult:
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
        media = _media_type(request.media_type, data)
        encoded = base64.b64encode(data).decode("ascii")
        body = {
            "model": self.model_id,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM + "\nAllowed taxonomy:\n" + json.dumps(taxonomy_option_catalog())},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Classify this image. Allowed reference types: "
                                + ", ".join(sorted(IMAGE_REFERENCE_TYPES))
                                + "."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{media};base64,{encoded}"},
                        },
                    ],
                },
            ],
        }
        payload = self._complete(self.settings, body, self.last_call)
        return map_classification_payload(payload)


def _media_type(declared: str | None, data: bytes) -> str:
    if declared:
        key = declared.strip().casefold()
        if key in _MEDIA:
            return _MEDIA[key]
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if len(data) >= 12 and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"
