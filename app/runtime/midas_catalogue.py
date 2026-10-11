"""Trusted Midas catalogue records used for server-side image ingestion.

The source of truth is the scraped UIMidas catalogue JSON. Image URLs are
Magento small_image files on midasfurniture.com, not product-page HTML.
Callers must look up products by id; they must not fetch client-supplied URLs.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Mapping
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

CATALOGUE_JSON = (
    Path(__file__).resolve().parents[1].parent / "UIMidas" / "src" / "data" / "midasProducts.json"
)
ALLOWED_IMAGE_HOSTS = frozenset({"midasfurniture.com", "www.midasfurniture.com"})
ALLOWED_IMAGE_PATH_PREFIX = "/media/catalog/product/"


class CatalogueProduct(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    sku: str = Field(min_length=1)
    image_url: str | None = None
    product_url: str = Field(min_length=1)
    source_url: str = Field(min_length=1)


def catalogue_image_url_is_allowed(url: str | None) -> bool:
    if not url or not url.strip():
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    if parsed.username or parsed.password:
        return False
    if parsed.port not in (None, 443):
        return False
    host = (parsed.hostname or "").casefold()
    if host not in ALLOWED_IMAGE_HOSTS:
        return False
    path = parsed.path or ""
    return path.startswith(ALLOWED_IMAGE_PATH_PREFIX)


def _safe_https_midas_page(url: str | None) -> str | None:
    if not url or not url.strip():
        return None
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme != "https":
        return None
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        return None
    host = (parsed.hostname or "").casefold()
    if host not in ALLOWED_IMAGE_HOSTS:
        return None
    if not (parsed.path or "").startswith("/"):
        return None
    return parsed.geturl()


def parse_catalogue_records(value: object) -> dict[str, CatalogueProduct]:
    if not isinstance(value, list):
        return {}
    products: dict[str, CatalogueProduct] = {}
    for entry in value:
        product = _parse_product(entry)
        if product is None or product.id in products:
            continue
        products[product.id] = product
    return products


def _parse_product(value: object) -> CatalogueProduct | None:
    if not isinstance(value, dict):
        return None
    product_id = _text(value.get("id"))
    name = _text(value.get("name"))
    sku = _text(value.get("sku"))
    product_url = _safe_https_midas_page(_text(value.get("productUrl")) or None)
    source_url = _safe_https_midas_page(_text(value.get("sourceUrl")) or None)
    if not product_id or not name or not sku or product_id != sku or not product_url or not source_url:
        return None
    image_raw = value.get("imageUrl")
    image_url = image_raw if isinstance(image_raw, str) else None
    if image_url and not catalogue_image_url_is_allowed(image_url):
        image_url = None
    return CatalogueProduct(
        id=product_id,
        name=name,
        sku=sku,
        image_url=image_url,
        product_url=product_url,
        source_url=source_url,
    )


def _text(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


@lru_cache(maxsize=1)
def load_trusted_catalogue() -> Mapping[str, CatalogueProduct]:
    if not CATALOGUE_JSON.is_file():
        return {}
    payload = json.loads(CATALOGUE_JSON.read_text(encoding="utf-8"))
    return parse_catalogue_records(payload)


def lookup_catalogue_product(
    product_id: str,
    catalogue: Mapping[str, CatalogueProduct] | None = None,
) -> CatalogueProduct | None:
    records = load_trusted_catalogue() if catalogue is None else catalogue
    return records.get(product_id.strip())
