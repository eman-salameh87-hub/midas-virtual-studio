"""Server-side Midas catalogue image ingestion. No live HTTP or paid generation."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.contracts.brief_mapping import BRIEF_MAPPING_UNRESOLVED
from app.contracts.client_brief import NormalizedReference
from app.main import app
from app.runtime.catalogue_images import (
    CATALOGUE_IMAGE_FORBIDDEN,
    CATALOGUE_IMAGE_TOO_LARGE,
    CATALOGUE_IMAGE_UNAVAILABLE,
    CATALOGUE_IMAGE_UNSUPPORTED,
    CATALOGUE_PRODUCT_UNKNOWN,
    MAX_IMAGE_BYTES,
    CatalogueImageError,
    assert_safe_catalogue_image_url,
    ingest_catalogue_reference,
    reset_catalogue_image_cache,
    sniff_image_media,
)
from app.runtime.midas_catalogue import CatalogueProduct, parse_catalogue_records
from app.runtime.state import JOB_STORE
from tests.png_bytes import PNG_1X1, PNG_HASH
from tests.test_brief_to_job import _PHASE0_NOT_IN_BRIEF, _prepare, _slice_payload

ABALI = CatalogueProduct(
    id="165931",
    name="ABALI DINING TABLE- WHITE",
    sku="165931",
    image_url="https://midasfurniture.com/media/catalog/product/4/3/43-165931_h.webp?optimize=high&fit=bounds&height=&width=",
    product_url="https://midasfurniture.com/qtr_en/abali-dining-table-dining-rooms-midas.html",
    source_url="https://midasfurniture.com/qtr_en/abali-dining-table-dining-rooms-midas.html",
)


@dataclass
class FakeResponse:
    status_code: int
    content: bytes
    headers: dict[str, str]


@pytest.fixture(autouse=True)
def _clear_catalogue_cache() -> None:
    reset_catalogue_image_cache()
    yield
    reset_catalogue_image_cache()


def _ref() -> NormalizedReference:
    return NormalizedReference.model_validate(
        {
            "id": "ref-midas",
            "type": "midas",
            "source": "midas_library",
            "role": "midas_reference",
            "relationship": "same_product",
            "productGroupId": "group-1",
            "evidence": {
                "fileName": ABALI.name,
                "mediaKind": "image",
                "sizeBytes": None,
                "libraryKey": ABALI.id,
            },
        }
    )


def _catalogue() -> dict[str, CatalogueProduct]:
    return {ABALI.id: ABALI}


def test_sniff_rejects_html_and_accepts_png() -> None:
    assert sniff_image_media(PNG_1X1) == "PNG"
    assert sniff_image_media(b"<html>not an image</html>") is None


def test_ssrf_rejects_private_hosts_and_non_midas_urls() -> None:
    with pytest.raises(CatalogueImageError) as blocked:
        assert_safe_catalogue_image_url("https://127.0.0.1/media/catalog/product/x.webp")
    assert blocked.value.code == CATALOGUE_IMAGE_FORBIDDEN

    with pytest.raises(CatalogueImageError) as html_page:
        assert_safe_catalogue_image_url("https://midasfurniture.com/qtr_en/abali-dining-table-dining-rooms-midas.html")
    assert html_page.value.code == CATALOGUE_IMAGE_FORBIDDEN

    with pytest.raises(CatalogueImageError) as other_host:
        assert_safe_catalogue_image_url("https://example.com/media/catalog/product/x.webp")
    assert other_host.value.code == CATALOGUE_IMAGE_FORBIDDEN

    with pytest.raises(CatalogueImageError) as private_dns:
        assert_safe_catalogue_image_url(
            ABALI.image_url or "",
            resolver=lambda _host: ["10.0.0.8"],
        )
    assert private_dns.value.code == CATALOGUE_IMAGE_FORBIDDEN


def test_unknown_product_and_missing_image_are_actionable() -> None:
    missing_key = NormalizedReference.model_validate(
        {
            "id": "ref-midas",
            "type": "midas",
            "source": "midas_library",
            "role": "midas_reference",
            "relationship": "same_product",
            "productGroupId": "group-1",
            "evidence": {
                "fileName": "unknown",
                "mediaKind": "image",
                "sizeBytes": None,
                "libraryKey": "not-a-sku",
            },
        }
    )
    with pytest.raises(CatalogueImageError) as unknown:
        ingest_catalogue_reference(missing_key, index=0, catalogue=_catalogue(), http_get=lambda _url: FakeResponse(200, PNG_1X1, {}))
    assert unknown.value.code == CATALOGUE_PRODUCT_UNKNOWN

    no_image = ABALI.model_copy(update={"image_url": None})
    with pytest.raises(CatalogueImageError) as unavailable:
        ingest_catalogue_reference(
            _ref(),
            index=0,
            catalogue={ABALI.id: no_image},
            http_get=lambda _url: FakeResponse(200, PNG_1X1, {}),
        )
    assert unavailable.value.code == CATALOGUE_IMAGE_UNAVAILABLE


def test_inaccessible_invalid_mime_and_oversized_images() -> None:
    with pytest.raises(CatalogueImageError) as missing:
        ingest_catalogue_reference(
            _ref(),
            index=0,
            catalogue=_catalogue(),
            http_get=lambda _url: FakeResponse(404, b"missing", {}),
            resolver=lambda _host: ["1.1.1.1"],
        )
    assert missing.value.code == CATALOGUE_IMAGE_UNAVAILABLE

    with pytest.raises(CatalogueImageError) as mime:
        ingest_catalogue_reference(
            _ref(),
            index=0,
            catalogue=_catalogue(),
            http_get=lambda _url: FakeResponse(200, b"<html>catalogue</html>", {}),
            resolver=lambda _host: ["1.1.1.1"],
        )
    assert mime.value.code == CATALOGUE_IMAGE_UNSUPPORTED

    oversized = b"\xff\xd8\xff" + b"\x00" * (MAX_IMAGE_BYTES + 1)

    def too_big(_url: str) -> FakeResponse:
        return FakeResponse(200, oversized, {"content-length": str(len(oversized))})

    with pytest.raises(CatalogueImageError) as large:
        ingest_catalogue_reference(
            _ref(),
            index=0,
            catalogue=_catalogue(),
            http_get=too_big,
            resolver=lambda _host: ["1.1.1.1"],
        )
    assert large.value.code == CATALOGUE_IMAGE_TOO_LARGE


def test_successful_ingest_uses_trusted_url_and_caches() -> None:
    calls: list[str] = []

    def http_get(url: str) -> FakeResponse:
        calls.append(url)
        return FakeResponse(200, PNG_1X1, {})

    first = ingest_catalogue_reference(
        _ref(),
        index=0,
        catalogue=_catalogue(),
        http_get=http_get,
        resolver=lambda _host: ["1.1.1.1"],
    )
    second = ingest_catalogue_reference(
        _ref(),
        index=0,
        catalogue=_catalogue(),
        http_get=http_get,
        resolver=lambda _host: ["1.1.1.1"],
    )
    assert first.content == PNG_1X1
    assert first.media_type == "PNG"
    assert first.product.sku == "165931"
    assert calls == [ABALI.image_url]
    assert second.content == PNG_1X1


def test_client_bytes_are_ignored_and_catalogue_image_reaches_the_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    JOB_STORE.clear()
    calls: list[str] = []

    def http_get(url: str) -> FakeResponse:
        calls.append(url)
        return FakeResponse(200, PNG_1X1, {})

    monkeypatch.setattr("app.runtime.catalogue_images.default_http_get", http_get)
    monkeypatch.setattr("app.runtime.brief_jobs.resolve_host_addresses", lambda _host: ["1.1.1.1"])
    monkeypatch.setattr(
        "app.runtime.catalogue_images.lookup_catalogue_product",
        lambda product_id, catalogue=None: _catalogue().get(product_id),
    )

    payload = _slice_payload()
    payload["brief"]["items"][0]["references"] = [
        {
            "id": "ref-midas",
            "type": "midas",
            "source": "midas_library",
            "role": "midas_reference",
            "relationship": "same_product",
            "productGroupId": "group-1",
            "evidence": {
                "fileName": ABALI.name,
                "mediaKind": "image",
                "sizeBytes": None,
                "libraryKey": ABALI.id,
            },
        }
    ]
    client = TestClient(app)
    created = client.post(
        "/api/v1/client-briefs",
        json={
            "owner_id": "owner-slice",
            "contract_id": "contract-catalogue-1",
            "revision": 1,
            "client_brief": payload,
        },
    )
    assert created.status_code == 200, created.text
    response = _prepare(
        created.json()["brief_id"],
        {
            "phase0_fields_not_in_brief": _PHASE0_NOT_IN_BRIEF,
            "reference_files": [
                {
                    "reference_id": "ref-midas",
                    "content_base64": "not-the-catalogue-image",
                    "media_type": "PNG",
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    record = JOB_STORE.get(job_id)
    assert record is not None
    assert record.reference_bytes["ref-midas"] == PNG_1X1
    assert record.contract.references[0].content_hash == PNG_HASH
    assert record.contract.references[0].filename == "165931.png"
    assert record.contract.references[0].role == "Product / vendor reference"
    subjects = {row.subject: row.value for row in record.contract.statements}
    assert subjects["catalogue sku"] == "165931"
    assert subjects["catalogue selected role"] == "hero"
    assert ABALI.image_url == subjects["catalogue image url"]
    assert calls == [ABALI.image_url]


def test_prepare_reports_inaccessible_catalogue_image(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.runtime.catalogue_images.default_http_get",
        lambda _url: FakeResponse(503, b"down", {}),
    )
    monkeypatch.setattr("app.runtime.brief_jobs.resolve_host_addresses", lambda _host: ["1.1.1.1"])
    monkeypatch.setattr(
        "app.runtime.catalogue_images.lookup_catalogue_product",
        lambda product_id, catalogue=None: _catalogue().get(product_id),
    )
    payload = _slice_payload()
    payload["brief"]["items"][0]["references"] = [
        {
            "id": "ref-midas",
            "type": "midas",
            "source": "midas_library",
            "role": "midas_reference",
            "relationship": "same_product",
            "productGroupId": "group-1",
            "evidence": {
                "fileName": ABALI.name,
                "mediaKind": "image",
                "sizeBytes": None,
                "libraryKey": ABALI.id,
            },
        }
    ]
    client = TestClient(app)
    created = client.post(
        "/api/v1/client-briefs",
        json={
            "owner_id": "owner-slice",
            "contract_id": "contract-catalogue-fail",
            "revision": 1,
            "client_brief": payload,
        },
    )
    assert created.status_code == 200, created.text
    response = _prepare(created.json()["brief_id"], {"reference_files": [], "phase0_fields_not_in_brief": _PHASE0_NOT_IN_BRIEF})
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"]["code"] == BRIEF_MAPPING_UNRESOLVED
    issues = body["error"]["details"]["issues"]
    assert any(issue["code"] == CATALOGUE_IMAGE_UNAVAILABLE for issue in issues)
    assert "HTTP 503" in issues[0]["message"]


def test_parse_catalogue_keeps_image_urls_on_midas_media_host() -> None:
    records = parse_catalogue_records(
        [
            {
                "id": "165931",
                "name": "ABALI DINING TABLE- WHITE",
                "sku": "165931",
                "imageUrl": ABALI.image_url,
                "productUrl": ABALI.product_url,
                "sourceUrl": ABALI.source_url,
            }
        ]
    )
    assert records["165931"].image_url == ABALI.image_url
