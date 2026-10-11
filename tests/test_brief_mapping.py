"""UIMidas wire enums → Phase-0 mapping. Persist stays separate from execution."""

from __future__ import annotations

from typing import Any, get_args

from app.contracts.brief_mapping import (
    MISSING_REFERENCE_BYTES,
    UNREPRESENTABLE_FIELD,
    UNSUPPORTED_REFERENCE,
    UNSUPPORTED_RESOLUTION,
    UNRESOLVED_CATEGORY,
    UNRESOLVED_OUTPUT,
    UNRESOLVED_REFERENCE,
    ReferenceBytes,
    map_saved_brief_to_phase0_intake,
)
from app.contracts.client_brief import (
    FloorPreference,
    ImageProportion,
    ImageResolution,
    LightingPreference,
    MoodVibe,
    OutputConcept,
    OutputView,
    ProposedJobContract,
    ReferenceType,
    WallPreference,
)
from tests.png_bytes import PNG_B64
from tests.test_brief_to_job import _PHASE0_NOT_IN_BRIEF, _slice_payload
from tests.test_client_brief import _PLACEHOLDERS, _populated_uimidas_payload

_FILES = [{"reference_id": "ref-product", "content_base64": PNG_B64, "media_type": "PNG"}]
_DEFAULT_EXTRAS = object()


def _contract(payload: dict[str, Any] | None = None) -> ProposedJobContract:
    return ProposedJobContract.model_validate(payload or _slice_payload())


def _map(
    payload: dict[str, Any] | None = None,
    files: list[dict[str, str]] | None = None,
    extras: object = _DEFAULT_EXTRAS,
):
    from app.contracts.brief_mapping import Phase0FieldsNotInBrief, ReferenceBytes

    if extras is _DEFAULT_EXTRAS:
        phase0 = Phase0FieldsNotInBrief.model_validate(_PHASE0_NOT_IN_BRIEF)
    elif extras is None:
        phase0 = None
    else:
        phase0 = Phase0FieldsNotInBrief.model_validate(extras)
    return map_saved_brief_to_phase0_intake(
        _contract(payload),
        owner_id="owner-slice",
        contract_id="contract-slice-1",
        revision=1,
        reference_files=[ReferenceBytes.model_validate(row) for row in (files or _FILES)],
        phase0_fields_not_in_brief=phase0,
    )


def test_every_frontend_output_view_is_classified() -> None:
    payload = _slice_payload()
    classified = {
        "category_template": UNRESOLVED_OUTPUT,
        "wide_view": None,
        "close_up": None,
        "wide_view_close_up": None,
        "front": None,
        "three_quarter": None,
        "side": None,
        "back": None,
        "top": None,
        "detail": None,
        "in_situ": None,
    }
    assert set(classified) == set(get_args(OutputView))
    for view, code in classified.items():
        payload["brief"]["items"][0]["requestedPackage"][0]["views"] = [view]
        payload["package"][0]["outputs"][0]["views"] = [view]
        result = _map(payload)
        if code is None:
            assert result.intake is not None, view
            assert result.issues == []
        else:
            assert result.intake is None, view
            assert code in {issue.code for issue in result.issues}, view


def test_every_frontend_proportion_and_resolution_is_classified() -> None:
    payload = _slice_payload()
    proportions = {
        "standard_for_category": UNRESOLVED_OUTPUT,
        "1:1": None,
        "4:5": None,
        "16:9": None,
        "3:4": None,
        "4:3": None,
        "9:16": None,
        "2:3": None,
    }
    resolutions = {
        "standard_for_category": UNRESOLVED_OUTPUT,
        "2k": None,
        "4k": None,
        "web": UNSUPPORTED_RESOLUTION,
        "standard": UNSUPPORTED_RESOLUTION,
        "high": UNSUPPORTED_RESOLUTION,
        "print": UNSUPPORTED_RESOLUTION,
    }
    assert set(proportions) == set(get_args(ImageProportion))
    assert set(resolutions) == set(get_args(ImageResolution))
    for proportion, code in proportions.items():
        payload["brief"]["items"][0]["requestedPackage"][0]["proportion"] = proportion
        payload["package"][0]["outputs"][0]["proportion"] = proportion
        payload["brief"]["items"][0]["requestedPackage"][0]["resolution"] = "2k"
        payload["package"][0]["outputs"][0]["resolution"] = "2k"
        result = _map(payload)
        if code is None:
            assert result.intake is not None, proportion
        else:
            assert code in {issue.code for issue in result.issues}, proportion
    payload["brief"]["items"][0]["requestedPackage"][0]["proportion"] = "1:1"
    payload["package"][0]["outputs"][0]["proportion"] = "1:1"
    for resolution, code in resolutions.items():
        payload["brief"]["items"][0]["requestedPackage"][0]["resolution"] = resolution
        payload["package"][0]["outputs"][0]["resolution"] = resolution
        result = _map(payload)
        if code is None:
            assert result.intake is not None, resolution
        else:
            assert code in {issue.code for issue in result.issues}, resolution


def test_every_frontend_concept_maps_when_delivery_is_executable() -> None:
    payload = _slice_payload()
    assert set(_slice_payload()["brief"]["items"][0]["requestedPackage"][0])  # sanity
    for concept in get_args(OutputConcept):
        output = {
            "concept": concept,
            "views": ["wide_view"],
            "proportion": "1:1",
            "resolution": "2k",
        }
        if concept == "others":
            output["otherLabel"] = "Styled corner"
        payload["brief"]["items"][0]["requestedPackage"] = [output]
        payload["package"][0]["outputs"] = [output]
        result = _map(payload)
        assert result.intake is not None, concept
        assert result.issues == []


def test_single_item_role_becomes_job_option_not_product_role() -> None:
    payload = _slice_payload()
    payload["role"] = "secondary"
    payload["brief"]["job"] = {"kind": "single_item", "singleItemRole": "secondary"}
    result = _map(payload)
    assert result.intake is not None
    assert result.intake["intent"]["job_type"] == "Single item"
    assert result.intake["intent"]["job_option"] == "Secondary"
    assert result.intake["item"]["product_role"] == "hero"


def test_edit_and_batch_one_item_map_job_options() -> None:
    payload = _slice_payload()
    payload["brief"]["job"] = {"kind": "edit", "editMode": "new_item"}
    result = _map(payload)
    assert result.intake is not None
    assert result.intake["intent"]["job_type"] == "Edit"
    assert result.intake["intent"]["job_option"] == "New item"

    payload["brief"]["job"] = {"kind": "new_project", "newProjectMode": "batch"}
    result = _map(payload)
    assert result.intake is not None
    assert result.intake["intent"]["job_option"] == "Batch"


def test_batch_two_items_creates_one_intake_per_item() -> None:
    payload = _slice_payload()
    payload["brief"]["job"] = {"kind": "new_project", "newProjectMode": "batch"}
    second = {
        **payload["brief"]["items"][0],
        "id": "item-2",
        "productGroupId": "group-2",
        "references": [
            {
                **payload["brief"]["items"][0]["references"][0],
                "id": "ref-product-2",
                "productGroupId": "group-2",
            }
        ],
    }
    payload["brief"]["items"].append(second)
    payload["package"].append(
        {
            "itemId": "item-2",
            "productGroupId": "group-2",
            "outputs": payload["package"][0]["outputs"],
        }
    )
    files = [
        *_FILES,
        {"reference_id": "ref-product-2", "content_base64": PNG_B64, "media_type": "PNG"},
    ]
    result = _map(payload, files=files)
    assert result.issues == []
    assert len(result.intakes) == 2
    assert result.intakes[0]["intent"]["job_option"] == "Batch"


def test_category_ids_and_compatible_package_are_preserved() -> None:
    payload = _slice_payload()
    second = {
        "concept": "website",
        "views": ["close_up"],
        "proportion": "1:1",
        "resolution": "2k",
    }
    payload["brief"]["items"][0]["requestedPackage"].append(second)
    payload["package"][0]["outputs"].append(second)
    result = _map(payload)
    assert result.intake is not None
    assert len(result.intakes) == 2
    assert result.intake["item"]["department"] == "home-furniture"
    assert result.intake["item"]["category"] == "home-furniture/living-rooms"
    assert [row["intent"]["requested_outcomes"] for row in result.intakes] == [["Lifestyle"], ["Website"]]
    assert [row["outputs"]["views"] for row in result.intakes] == [["Wide view"], ["Close-up"]]


def test_two_views_become_two_intakes() -> None:
    payload = _slice_payload()
    payload["brief"]["items"][0]["requestedPackage"][0]["views"] = ["wide_view", "close_up"]
    payload["package"][0]["outputs"][0]["views"] = ["wide_view", "close_up"]
    result = _map(payload)
    assert result.issues == []
    assert [row["outputs"]["views"] for row in result.intakes] == [["Wide view"], ["Close-up"]]


def test_item_count_and_piece_text_are_preserved() -> None:
    payload = _slice_payload()
    payload["brief"]["items"][0]["metadata"] = {
        "itemCount": 2,
        "otherPieces": "side table",
        "specificItemsCombo": "sofa + table",
    }
    result = _map(payload)
    assert result.intake is not None
    assert result.intake["intent"]["selected_count"] == {"status": "declared", "value": 2}
    assert result.intake["intent"]["requested_pieces"] == ["sofa + table", "side table"]


def test_sku_is_kept_as_protected_identity_and_notes_still_block() -> None:
    payload = _slice_payload()
    payload["brief"]["items"][0]["metadata"]["sku"] = "SKU-1"
    sku_only = _map(payload, extras=None)
    assert sku_only.issues == []
    assert sku_only.intake is not None
    assert sku_only.intake["changes"]["protected_identity"] == ["uploaded product appearance", "SKU-1"]

    payload["brief"]["notes"] = {"fidelity": "keep the grain"}
    result = _map(payload)
    assert result.intake is None
    codes = {issue.code for issue in result.issues}
    assert UNREPRESENTABLE_FIELD in codes
    assert any("fidelity" in issue.field for issue in result.issues)


def test_midas_catalogue_reference_maps_when_bytes_are_ingested() -> None:
    from app.runtime.midas_catalogue import CatalogueProduct

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
                "fileName": "ABALI DINING TABLE- WHITE",
                "mediaKind": "image",
                "sizeBytes": None,
                "libraryKey": "165931",
            },
        }
    ]
    product = CatalogueProduct(
        id="165931",
        name="ABALI DINING TABLE- WHITE",
        sku="165931",
        image_url="https://midasfurniture.com/media/catalog/product/4/3/43-165931_h.webp",
        product_url="https://midasfurniture.com/qtr_en/abali-dining-table-dining-rooms-midas.html",
        source_url="https://midasfurniture.com/qtr_en/abali-dining-table-dining-rooms-midas.html",
    )
    result = map_saved_brief_to_phase0_intake(
        _contract(payload),
        owner_id="owner-slice",
        contract_id="contract-slice-1",
        revision=1,
        reference_files=[
            ReferenceBytes.model_validate(
                {"reference_id": "ref-midas", "content_base64": PNG_B64, "media_type": "PNG"}
            )
        ],
        phase0_fields_not_in_brief=None,
        catalogue_products={"ref-midas": product},
    )
    assert result.issues == []
    assert result.intake is not None
    assert result.intake["references"][0]["role"] == "Product / vendor reference"
    assert result.intake["references"][0]["filename"] == "165931.png"
    assert result.intake["references"][0]["content_base64"] == PNG_B64
    subjects = {row["subject"]: row["value"] for row in result.intake["statements"]}
    assert subjects["catalogue sku"] == "165931"
    assert subjects["catalogue product name"] == "ABALI DINING TABLE- WHITE"
    assert subjects["catalogue selected role"] == "hero"
    assert "midasfurniture.com/media/catalog/product/" in subjects["catalogue image url"]


def test_detail_references_remain_unsupported() -> None:
    payload = _slice_payload()
    payload["brief"]["items"][0]["references"].append(
        {
            "id": "ref-detail",
            "type": "detail",
            "source": "local_file",
            "role": "detail",
            "relationship": "same_product",
            "productGroupId": "group-1",
            "evidence": {
                "fileName": "detail.jpg",
                "mediaKind": "image",
                "sizeBytes": 10,
                "libraryKey": None,
            },
        }
    )
    result = _map(payload)
    assert result.intake is None
    assert UNSUPPORTED_REFERENCE in {issue.code for issue in result.issues}


def test_room_reference_is_mapped_when_bytes_are_sent() -> None:
    payload = _slice_payload()
    payload["brief"]["items"][0]["references"].append(
        {
            "id": "ref-room",
            "type": "room_image",
            "source": "local_file",
            "role": "room",
            "relationship": "supporting_context",
            "productGroupId": None,
            "evidence": {
                "fileName": "room.png",
                "mediaKind": "image",
                "sizeBytes": 10,
                "libraryKey": None,
            },
        }
    )
    files = [
        *_FILES,
        {"reference_id": "ref-room", "content_base64": PNG_B64, "media_type": "PNG"},
    ]
    result = _map(payload, files=files)
    assert result.intake is not None
    roles = [row["role"] for row in result.intake["references"]]
    assert roles == ["Product / vendor reference", "Room / target space"]


def test_missing_bytes_do_not_invent_a_hash() -> None:
    result = _map(files=[{"reference_id": "ref-product", "content_base64": "   ", "media_type": "PNG"}])
    assert result.intake is None
    assert MISSING_REFERENCE_BYTES in {issue.code for issue in result.issues}


def test_image_media_types_are_canonicalized_before_validation() -> None:
    payload = _slice_payload()
    cases = (
        ("JPG", "product.jpg", "JPG"),
        ("jpg", "product.jpg", "JPG"),
        ("JPEG", "product.jpeg", "JPG"),
        ("jpeg", "product.jpeg", "JPG"),
        ("PNG", "product.png", "PNG"),
        ("png", "product.png", "PNG"),
        ("WebP", "product.webp", "WebP"),
        ("webp", "product.webp", "WebP"),
        ("WEBP", "product.webp", "WebP"),
        ("wEbP", "11-173716_o.webp", "WebP"),
    )
    for declared, filename, canonical in cases:
        payload["brief"]["items"][0]["references"][0]["evidence"]["fileName"] = filename
        result = _map(
            payload,
            files=[{"reference_id": "ref-product", "content_base64": PNG_B64, "media_type": declared}],
        )
        assert result.intake is not None, declared
        assert result.intake["references"][0]["media_type"] == canonical, declared


def test_webp_filename_is_accepted_when_media_type_is_omitted() -> None:
    payload = _slice_payload()
    payload["brief"]["items"][0]["references"][0]["evidence"]["fileName"] = "11-173716_o.webp"
    result = _map(
        payload,
        files=[{"reference_id": "ref-product", "content_base64": PNG_B64}],
    )
    assert result.intake is not None
    assert result.intake["references"][0]["media_type"] == "WebP"


def test_webp_blank_bytes_still_report_missing_reference_bytes() -> None:
    payload = _slice_payload()
    payload["brief"]["items"][0]["references"][0]["evidence"]["fileName"] = "11-173716_o.webp"
    result = _map(
        payload,
        files=[{"reference_id": "ref-product", "content_base64": "   ", "media_type": "WebP"}],
    )
    assert result.intake is None
    codes = {issue.code for issue in result.issues}
    assert MISSING_REFERENCE_BYTES in codes
    assert UNRESOLVED_REFERENCE not in codes


def test_unsupported_image_media_types_remain_rejected() -> None:
    payload = _slice_payload()
    for declared, filename in (("GIF", "product.gif"), ("gif", "product.gif"), ("HEIC", "product.heic")):
        payload["brief"]["items"][0]["references"][0]["evidence"]["fileName"] = filename
        result = _map(
            payload,
            files=[{"reference_id": "ref-product", "content_base64": PNG_B64, "media_type": declared}],
        )
        assert result.intake is None, declared
        issues = [issue for issue in result.issues if issue.code == UNRESOLVED_REFERENCE]
        assert issues
        assert issues[0].field == "references[0].media_type"


def test_populated_audit_fixture_persists_shape_but_does_not_execute() -> None:
    payload = _populated_uimidas_payload()
    ProposedJobContract.model_validate(payload)
    result = _map(payload)
    assert result.intake is None
    codes = {issue.code for issue in result.issues}
    assert UNRESOLVED_OUTPUT in codes or UNSUPPORTED_VIEW in codes or UNREPRESENTABLE_FIELD in codes


def test_automatic_unknown_category_is_unresolved() -> None:
    payload = _slice_payload()
    payload["brief"]["items"][0]["categoryState"] = "automatic_unknown"
    del payload["brief"]["items"][0]["department"]
    del payload["brief"]["items"][0]["category"]
    del payload["brief"]["items"][0]["subcategory"]
    payload["category"] = None
    result = _map(payload)
    assert result.intake is None
    assert UNRESOLVED_CATEGORY in {issue.code for issue in result.issues}


def test_omitted_inclusions_and_white_bk_room_use_documented_fills() -> None:
    payload = _slice_payload()
    payload["brief"]["items"][0]["requestedPackage"][0]["concept"] = "white_bk"
    payload["package"][0]["outputs"][0]["concept"] = "white_bk"
    del payload["brief"]["preferences"]
    del payload["brief"]["suggestions"]
    result = _map(payload, extras=None)
    assert result.issues == []
    assert result.intake is not None
    assert result.intake["preferences"] == {
        "lighting": "Soft daylight",
        "wall": "White",
        "floor": "Light oak",
        "plants": False,
        "human": False,
        "mood": "Automatic",
    }
    assert result.intake["outputs"]["package_members"] == ["catalogue"]
    assert result.intake["changes"]["policy_mode"] == "fidelity-locked"


def test_styled_outcome_without_room_picks_stays_unresolved() -> None:
    payload = _slice_payload()
    del payload["brief"]["preferences"]
    result = _map(payload, extras=None)
    assert result.intake is None
    assert any(issue.code == "UNRESOLVED_PREFERENCES" for issue in result.issues)


def test_one_by_one_derives_engine_fields_without_caller_extras() -> None:
    result = _map(extras=None)
    assert result.issues == []
    assert result.intake is not None
    assert result.intake["item"]["product_role"] == "hero"
    assert result.intake["source_condition"]["input_condition"] == "clean pack shot"
    assert result.intake["outputs"]["package_members"] == ["lifestyle"]
    assert result.intake["changes"]["protected_identity"] == ["uploaded product appearance"]
    assert result.intake["changes"]["policy_mode"] == "creative-room"


def test_preference_enum_tables_cover_the_wire() -> None:
    assert set(_slice_payload()["brief"]["preferences"].values()) <= set(get_args(LightingPreference)) | set(
        get_args(WallPreference)
    ) | set(get_args(FloorPreference))
    assert set(get_args(MoodVibe))
    assert set(get_args(ReferenceType))
