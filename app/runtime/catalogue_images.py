"""Fetch Midas catalogue images for job intake. Never uses client-supplied URLs."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Mapping, Protocol
from urllib.parse import urljoin, urlparse

import httpx

from app.contracts.client_brief import NormalizedReference, ProposedJobContract
from app.runtime.midas_catalogue import (
    CatalogueProduct,
    catalogue_image_url_is_allowed,
    lookup_catalogue_product,
)

CATALOGUE_PRODUCT_UNKNOWN = "CATALOGUE_PRODUCT_UNKNOWN"
CATALOGUE_IMAGE_UNAVAILABLE = "CATALOGUE_IMAGE_UNAVAILABLE"
CATALOGUE_IMAGE_UNSUPPORTED = "CATALOGUE_IMAGE_UNSUPPORTED"
CATALOGUE_IMAGE_FORBIDDEN = "CATALOGUE_IMAGE_FORBIDDEN"
CATALOGUE_IMAGE_TOO_LARGE = "CATALOGUE_IMAGE_TOO_LARGE"

MAX_IMAGE_BYTES = 12 * 1024 * 1024
MAX_REDIRECTS = 3
FETCH_TIMEOUT_SECONDS = 10.0
_JPEG = b"\xff\xd8\xff"
_PNG = b"\x89PNG\r\n\x1a\n"

Resolver = Callable[[str], list[str]]
HttpGet = Callable[[str], "CatalogueHttpResponse"]


class CatalogueHttpResponse(Protocol):
    status_code: int
    content: bytes
    headers: Mapping[str, str]


@dataclass(frozen=True)
class _HttpResponse:
    status_code: int
    content: bytes
    headers: Mapping[str, str]


class CatalogueImageError(Exception):
    def __init__(self, code: str, field: str, message: str) -> None:
        self.code = code
        self.field = field
        self.message = message
        super().__init__(message)


@dataclass
class _CacheEntry:
    product_id: str
    image_url: str
    media_type: str
    content: bytes


_CACHE: dict[tuple[str, str], _CacheEntry] = {}
_CACHE_LOCK = Lock()


def reset_catalogue_image_cache() -> None:
    with _CACHE_LOCK:
        _CACHE.clear()


def sniff_image_media(content: bytes) -> str | None:
    if content.startswith(_JPEG):
        return "JPG"
    if content.startswith(_PNG):
        return "PNG"
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "WebP"
    return None


def resolve_host_addresses(host: str) -> list[str]:
    try:
        results = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise CatalogueImageError(
            CATALOGUE_IMAGE_UNAVAILABLE,
            "catalogue.imageUrl",
            f"The catalogue image host {host!r} could not be resolved. Try again later or upload a local JPG, PNG, or WebP.",
        ) from exc
    addresses: list[str] = []
    for item in results:
        sockaddr = item[4]
        if sockaddr:
            addresses.append(str(sockaddr[0]))
    return addresses


def assert_safe_catalogue_image_url(
    url: str,
    *,
    field: str = "catalogue.imageUrl",
    resolver: Resolver = resolve_host_addresses,
) -> str:
    if not catalogue_image_url_is_allowed(url):
        raise CatalogueImageError(
            CATALOGUE_IMAGE_FORBIDDEN,
            field,
            "The catalogue image URL is not an allowed Midas product-image address. "
            "Select the product again from Choose from Midas, or upload a local JPG, PNG, or WebP.",
        )
    parsed = urlparse(url)
    host = parsed.hostname or ""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise CatalogueImageError(
            CATALOGUE_IMAGE_FORBIDDEN,
            field,
            "Catalogue image URLs must use a Midas hostname, not a raw IP address.",
        )
    for address in resolver(host):
        ip = ipaddress.ip_address(address)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise CatalogueImageError(
                CATALOGUE_IMAGE_FORBIDDEN,
                field,
                "The catalogue image host resolved to a private or non-public address and was not fetched.",
            )
    return url


def default_http_get(url: str) -> _HttpResponse:
    with httpx.Client(
        timeout=FETCH_TIMEOUT_SECONDS,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        with client.stream(
            "GET",
            url,
            headers={"User-Agent": "midas-virtual-studio-catalogue-ingest", "Accept": "image/*"},
        ) as response:
            declared = response.headers.get("content-length")
            if declared is not None:
                try:
                    if int(declared) > MAX_IMAGE_BYTES:
                        raise CatalogueImageError(
                            CATALOGUE_IMAGE_TOO_LARGE,
                            "catalogue.imageUrl",
                            f"The catalogue image is larger than {MAX_IMAGE_BYTES} bytes. Upload a smaller local JPG, PNG, or WebP.",
                        )
                except ValueError:
                    pass
            chunks = bytearray()
            for chunk in response.iter_bytes():
                chunks.extend(chunk)
                if len(chunks) > MAX_IMAGE_BYTES:
                    raise CatalogueImageError(
                        CATALOGUE_IMAGE_TOO_LARGE,
                        "catalogue.imageUrl",
                        f"The catalogue image is larger than {MAX_IMAGE_BYTES} bytes. Upload a smaller local JPG, PNG, or WebP.",
                    )
            headers = {key.lower(): value for key, value in response.headers.items()}
            return _HttpResponse(status_code=response.status_code, content=bytes(chunks), headers=headers)


def fetch_catalogue_image_bytes(
    url: str,
    *,
    field: str = "catalogue.imageUrl",
    http_get: HttpGet = default_http_get,
    resolver: Resolver = resolve_host_addresses,
) -> tuple[bytes, str]:
    current = assert_safe_catalogue_image_url(url, field=field, resolver=resolver)
    for _ in range(MAX_REDIRECTS + 1):
        try:
            response = http_get(current)
        except CatalogueImageError:
            raise
        except httpx.TimeoutException as exc:
            raise CatalogueImageError(
                CATALOGUE_IMAGE_UNAVAILABLE,
                field,
                "Retrieving the catalogue image timed out. Try again later or upload a local JPG, PNG, or WebP.",
            ) from exc
        except httpx.HTTPError as exc:
            raise CatalogueImageError(
                CATALOGUE_IMAGE_UNAVAILABLE,
                field,
                "The catalogue image could not be retrieved. Try again later or upload a local JPG, PNG, or WebP.",
            ) from exc
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("location") or response.headers.get("Location")
            if not location:
                raise CatalogueImageError(
                    CATALOGUE_IMAGE_UNAVAILABLE,
                    field,
                    "The catalogue image redirected without a Location header. Upload a local JPG, PNG, or WebP.",
                )
            nxt = urljoin(current, location)
            current = assert_safe_catalogue_image_url(nxt, field=field, resolver=resolver)
            continue
        if response.status_code != 200:
            raise CatalogueImageError(
                CATALOGUE_IMAGE_UNAVAILABLE,
                field,
                f"The catalogue image could not be retrieved (HTTP {response.status_code}). "
                "Confirm the product is still listed, or upload a local JPG, PNG, or WebP.",
            )
        if len(response.content) > MAX_IMAGE_BYTES:
            raise CatalogueImageError(
                CATALOGUE_IMAGE_TOO_LARGE,
                field,
                f"The catalogue image is larger than {MAX_IMAGE_BYTES} bytes. Upload a smaller local JPG, PNG, or WebP.",
            )
        media = sniff_image_media(response.content)
        if media is None:
            raise CatalogueImageError(
                CATALOGUE_IMAGE_UNSUPPORTED,
                field,
                "The catalogue file is not a JPG, PNG, or WebP image. Upload a local JPG, PNG, or WebP instead.",
            )
        if not response.content:
            raise CatalogueImageError(
                CATALOGUE_IMAGE_UNAVAILABLE,
                field,
                "The catalogue image response was empty. Upload a local JPG, PNG, or WebP.",
            )
        return response.content, media
    raise CatalogueImageError(
        CATALOGUE_IMAGE_FORBIDDEN,
        field,
        "The catalogue image redirected too many times and was not fetched.",
    )


@dataclass(frozen=True)
class IngestedCatalogueImage:
    reference_id: str
    content: bytes
    media_type: str
    product: CatalogueProduct


def ingest_catalogue_reference(
    ref: NormalizedReference,
    *,
    index: int,
    catalogue: Mapping[str, CatalogueProduct] | None = None,
    http_get: HttpGet | None = None,
    resolver: Resolver | None = None,
) -> IngestedCatalogueImage:
    field = f"references[{index}]"
    key = ref.evidence.library_key if ref.evidence is not None else None
    if not key or not key.strip():
        raise CatalogueImageError(
            CATALOGUE_PRODUCT_UNKNOWN,
            f"{field}.evidence.libraryKey",
            "A Midas catalogue reference is missing its product id. Select the product again from Choose from Midas.",
        )
    product = lookup_catalogue_product(key, catalogue)
    if product is None:
        raise CatalogueImageError(
            CATALOGUE_PRODUCT_UNKNOWN,
            f"{field}.evidence.libraryKey",
            f"Catalogue product {key!r} is not in the trusted Midas catalogue. "
            "Select it again from Choose from Midas, or upload a local JPG, PNG, or WebP.",
        )
    if not product.image_url:
        raise CatalogueImageError(
            CATALOGUE_IMAGE_UNAVAILABLE,
            f"{field}.evidence.libraryKey",
            f"Catalogue product {product.sku} has no downloadable image URL. "
            "Choose another product or upload a local JPG, PNG, or WebP.",
        )
    cache_key = (product.id, product.image_url)
    with _CACHE_LOCK:
        cached = _CACHE.get(cache_key)
    if cached is not None:
        return IngestedCatalogueImage(
            reference_id=ref.id,
            content=cached.content,
            media_type=cached.media_type,
            product=product,
        )
    content, media = fetch_catalogue_image_bytes(
        product.image_url,
        field=f"{field}.imageUrl",
        http_get=http_get or default_http_get,
        resolver=resolver or resolve_host_addresses,
    )
    with _CACHE_LOCK:
        _CACHE[cache_key] = _CacheEntry(
            product_id=product.id,
            image_url=product.image_url,
            media_type=media,
            content=content,
        )
    return IngestedCatalogueImage(
        reference_id=ref.id,
        content=content,
        media_type=media,
        product=product,
    )


def ingest_brief_catalogue_images(
    contract: ProposedJobContract,
    *,
    catalogue: Mapping[str, CatalogueProduct] | None = None,
    http_get: HttpGet | None = None,
    resolver: Resolver | None = None,
) -> tuple[list[IngestedCatalogueImage], list[CatalogueImageError]]:
    files: list[IngestedCatalogueImage] = []
    issues: list[CatalogueImageError] = []
    for item in contract.brief.items:
        for index, ref in enumerate(item.references):
            if ref.source != "midas_library" and ref.type != "midas":
                continue
            try:
                files.append(
                    ingest_catalogue_reference(
                        ref,
                        index=index,
                        catalogue=catalogue,
                        http_get=http_get,
                        resolver=resolver,
                    )
                )
            except CatalogueImageError as exc:
                issues.append(exc)
    return files, issues


def catalogue_role_label(ref: NormalizedReference) -> str:
    return "hero" if ref.relationship == "same_product" else "secondary"


def catalogue_filename(product: CatalogueProduct, media_type: str) -> str:
    extension = {"JPG": "jpg", "PNG": "png", "WebP": "webp"}[media_type]
    return f"{product.sku}.{extension}"


def catalogue_provenance_statements(ref: NormalizedReference, product: CatalogueProduct) -> list[dict[str, str]]:
    role = catalogue_role_label(ref)
    rows = [
        ("catalogue sku", product.sku),
        ("catalogue product name", product.name),
        ("catalogue source url", product.source_url),
        ("catalogue product url", product.product_url),
        ("catalogue selected role", role),
    ]
    if product.image_url:
        rows.append(("catalogue image url", product.image_url))
    return [
        {
            "subject": subject,
            "value": value,
            "basis": "published",
            "evidence_reference_id": ref.id,
        }
        for subject, value in rows
    ]


def midas_library_reference_ids(contract: ProposedJobContract) -> set[str]:
    ids: set[str] = set()
    for item in contract.brief.items:
        for ref in item.references:
            if ref.source == "midas_library" or ref.type == "midas":
                ids.add(ref.id)
    return ids
