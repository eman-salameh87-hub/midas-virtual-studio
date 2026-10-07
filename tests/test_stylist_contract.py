import pytest
from pydantic import ValidationError

from app.contracts.stylist import (
    CandidateBoard,
    GenericContextProp,
    MidasCompanion,
    RejectedAlternative,
    SelectedLayout,
    StylistPlan,
    StylistScene,
    StylistUnknown,
    StylistViewRequirements,
)

HASH_A = "a1" * 32
HASH_B = "b2" * 32


def _midas_companion(
    sku: str = "MIDAS-TBL-001",
    name: str = "Walnut Accent Coffee Table",
    category: str = "Tables",
    product_url: str = "https://midas.example/products/table-001",
    image_hash: str = HASH_A,
    function: str = "Low central surface for placement of functional items",
    source_reference: str = "ref-catalogue-table-001",
    dimensions: str = "120x60x45 cm",
    availability: str = "in_stock_2026_10",
) -> dict:
    return {
        "sku": sku,
        "name": name,
        "category": category,
        "product_url": product_url,
        "image_hash": image_hash,
        "dimensions": dimensions,
        "availability": availability,
        "function": function,
        "material": "Solid Walnut",
        "color": "Dark Walnut",
        "source_reference": source_reference,
    }


def _generic_prop(
    name: str = "Stack of art books",
    purpose: str = "Provides realistic contextual reading material on low table",
    placement: str = "Lower shelf of accent table",
) -> dict:
    return {
        "name": name,
        "purpose": purpose,
        "placement": placement,
        "is_midas_product": False,
    }


def _board_1() -> dict:
    return {
        "board_id": "board-warm-natural",
        "name": "Warm Natural Contemporary",
        "focal_hierarchy": "Hero piece centered with balanced companion table to the right",
        "palette": "Oatmeal beige, warm walnut wood, and muted sage accents",
        "spacing": "Generous 80cm circulation around seating and table",
        "surfaces": "Limestone tile flooring with off-white plaster walls",
        "lighting": "Soft indirect daylight from left side aperture",
        "circulation": "Clear walkway along foreground and right perimeter",
        "companion_skus": ["MIDAS-TBL-001"],
    }


def _board_2() -> dict:
    return {
        "board_id": "board-bold-contrast",
        "name": "Bold Contrast Modern",
        "focal_hierarchy": "Hero piece flanked by high-contrast dark accents",
        "palette": "Charcoal, terracotta, and dark bronze",
        "spacing": "Compact 50cm arrangement",
        "surfaces": "Dark hardwood flooring with charcoal accent wall",
        "lighting": "Dramatic directional evening light",
        "circulation": "Constrained front access",
        "companion_skus": ["MIDAS-TBL-001"],
    }


def _selected_layout() -> dict:
    return {
        "board_id": "board-warm-natural",
        "focal_hierarchy": "Hero piece centered with balanced companion table to the right",
        "palette": "Oatmeal beige, warm walnut wood, and muted sage accents",
        "spacing": "Generous 80cm circulation around seating and table",
        "surfaces": "Limestone tile flooring with off-white plaster walls",
        "lighting": "Soft indirect daylight from left side aperture",
        "circulation": "Clear walkway along foreground and right perimeter",
        "arrangement_detail": "Hero positioned 1.5m from backdrop; companion table angled 30 degrees",
        "functional_use": "Every seating piece and tabletop is accessible and oriented for natural conversation",
    }


def _rejected_alternative() -> dict:
    return {
        "board_id": "board-bold-contrast",
        "reason": "High contrast palette overpowers product texture and tight spacing limits circulation",
    }


def _scene() -> dict:
    return {
        "frame": "Landscape · 16:9",
        "setting": "A spacious sunlit room with limestone floors and soft off-white walls",
        "light": "Soft natural daylight streaming from lateral floor-to-ceiling windows",
        "camera": "Eye-level 50mm shot positioned 3.5m away ensuring all product pieces are fully in view",
        "presentation": "Main piece arranged prominently with companion table alongside and clear functional clearance",
    }


def _valid_stylist_plan_dict() -> dict:
    return {
        "job_id": "job-sofa-001",
        "contract_id": "contract-sofa-1",
        "contract_revision": 2,
        "brain_contract_id": "contract-sofa-1",
        "brain_revision": 2,
        "product_role": "hero",
        "hero_prominence": "The sofa is the primary focal anchor placed centrally in the composition",
        "scene": _scene(),
        "candidate_boards": [_board_1(), _board_2()],
        "selected_layout": _selected_layout(),
        "rejected_alternatives": [_rejected_alternative()],
        "functional_rationale": "Board 1 establishes optimal daylighting, generous circulation, and natural companion proportion",
        "midas_complements": [_midas_companion()],
        "supporting_props": [_generic_prop()],
        "view_requirements": {
            "close_up_requirements": "Detail shot of fabric weave and wood jointing",
            "wide_view_requirements": "Full view showing sofa silhouette and full room context",
            "detail_focus": "Carved base joinery",
        },
        "risks": [
            "Excessive shadow under low table",
            "Color temperature shifting fabric weave away from beige",
        ],
        "unknowns": [
            {
                "subject": "exact cushion fill firmness",
                "detail": "Vendor sheet does not state foam density; assumed standard loft",
            }
        ],
        "status": "ready",
        "hold_reasons": [],
    }


def test_valid_generalized_stylist_plan() -> None:
    plan_dict = _valid_stylist_plan_dict()
    plan = StylistPlan.model_validate(plan_dict)
    assert plan.job_id == "job-sofa-001"
    assert plan.contract_id == "contract-sofa-1"
    assert plan.contract_revision == 2
    assert plan.status == "ready"
    assert len(plan.candidate_boards) == 2
    assert plan.selected_layout.board_id == "board-warm-natural"
    assert len(plan.rejected_alternatives) == 1
    assert plan.midas_complements[0].sku == "MIDAS-TBL-001"
    assert plan.supporting_props[0].is_midas_product is False


def test_invalid_status_rejected() -> None:
    plan_dict = _valid_stylist_plan_dict()
    plan_dict["status"] = "in_progress"
    with pytest.raises(ValidationError):
        StylistPlan.model_validate(plan_dict)


def test_hold_status_requires_hold_reasons() -> None:
    plan_dict = _valid_stylist_plan_dict()
    plan_dict["status"] = "hold"
    plan_dict["hold_reasons"] = []
    with pytest.raises(ValidationError, match="held Stylist plan must specify at least one hold reason"):
        StylistPlan.model_validate(plan_dict)

    plan_dict["hold_reasons"] = ["Catalogue retrieval failed for companion table"]
    held_plan = StylistPlan.model_validate(plan_dict)
    assert held_plan.status == "hold"
    assert len(held_plan.hold_reasons) == 1


def test_ready_status_forbids_hold_reasons() -> None:
    plan_dict = _valid_stylist_plan_dict()
    plan_dict["status"] = "ready"
    plan_dict["hold_reasons"] = ["Some unresolved conflict"]
    with pytest.raises(ValidationError, match="ready Stylist plan must not have hold reasons"):
        StylistPlan.model_validate(plan_dict)


def test_invalid_product_role_rejected() -> None:
    plan_dict = _valid_stylist_plan_dict()
    plan_dict["product_role"] = "primary_actor"
    with pytest.raises(ValidationError):
        StylistPlan.model_validate(plan_dict)


def test_preservation_of_brain_contract_and_revision() -> None:
    plan_dict = _valid_stylist_plan_dict()
    plan_dict["brain_contract_id"] = "mismatched-contract"
    with pytest.raises(ValidationError, match="Stylist plan must bind the same contract as BrainPlan"):
        StylistPlan.model_validate(plan_dict)

    plan_dict = _valid_stylist_plan_dict()
    plan_dict["brain_revision"] = 99
    with pytest.raises(ValidationError, match="Stylist plan must bind the same revision as BrainPlan"):
        StylistPlan.model_validate(plan_dict)


def test_selected_layout_must_match_candidate_board() -> None:
    plan_dict = _valid_stylist_plan_dict()
    plan_dict["selected_layout"]["board_id"] = "unlisted-board-id"
    with pytest.raises(ValidationError, match="must match one of the candidate boards"):
        StylistPlan.model_validate(plan_dict)


def test_all_non_selected_boards_must_be_in_rejected_alternatives() -> None:
    plan_dict = _valid_stylist_plan_dict()
    plan_dict["rejected_alternatives"] = []
    with pytest.raises(ValidationError, match="All non-selected candidate boards must be listed"):
        StylistPlan.model_validate(plan_dict)


def test_selected_board_cannot_be_rejected() -> None:
    plan_dict = _valid_stylist_plan_dict()
    plan_dict["rejected_alternatives"].append({
        "board_id": "board-warm-natural",
        "reason": "Contradictory rejection of selected board",
    })
    with pytest.raises(ValidationError, match="Selected layout cannot also be listed as a rejected alternative"):
        StylistPlan.model_validate(plan_dict)


def test_candidate_board_companion_sku_must_exist_in_midas_complements() -> None:
    plan_dict = _valid_stylist_plan_dict()
    plan_dict["candidate_boards"][0]["companion_skus"] = ["INVENTED-SKU-999"]
    with pytest.raises(ValidationError, match="not found in midas_complements"):
        StylistPlan.model_validate(plan_dict)


def test_midas_companion_requires_valid_sha256_hash() -> None:
    companion = _midas_companion()
    companion["image_hash"] = "not-a-valid-sha256-hash"
    with pytest.raises(ValidationError, match="image_hash must be an explicit lowercase sha256 hex digest"):
        MidasCompanion.model_validate(companion)


def test_midas_companion_requires_source_reference() -> None:
    companion = _midas_companion()
    companion["source_reference"] = ""
    with pytest.raises(ValidationError):
        MidasCompanion.model_validate(companion)


def test_generic_prop_cannot_claim_to_be_midas_product() -> None:
    prop = _generic_prop()
    prop["is_midas_product"] = True
    with pytest.raises(ValidationError):
        GenericContextProp.model_validate(prop)


def test_unknowns_can_be_represented() -> None:
    plan_dict = _valid_stylist_plan_dict()
    plan_dict["unknowns"] = [
        {"subject": "stain resistance", "detail": "Fibre treatment level not documented"},
        {"subject": "exact ceiling height", "detail": "Target room clearance unmeasured"},
    ]
    plan = StylistPlan.model_validate(plan_dict)
    assert len(plan.unknowns) == 2
    assert plan.unknowns[0].subject == "stain resistance"


def test_multiple_product_categories_work_identically() -> None:
    # 1. Textile / Towel Hero
    towel_plan = _valid_stylist_plan_dict()
    towel_plan["product_role"] = "hero"
    towel_plan["hero_prominence"] = "The waffle-weave bath towel is hung neatly on a brushed brass rail in the foreground"
    towel_plan["scene"] = {
        "frame": "Portrait · 4:5",
        "setting": "A minimalist limestone bathroom with warm recessed lighting and microcement walls",
        "light": "Gentle, warm, diffuse overhead bathroom illumination",
        "camera": "Medium close-up at chest height showing the towel's waffle texture and edge stitching clearly",
        "presentation": "Towel draped cleanly over brass bar with slight natural fold",
    }
    towel_plan["selected_layout"]["functional_use"] = "Accessible reach beside washbasin on wall-mounted bar"
    towel_plan["view_requirements"] = {
        "close_up_requirements": "Macro view of waffle texture and hem border",
        "wide_view_requirements": "Context view showing basin and rail setup",
        "detail_focus": "Weave pattern and stitching",
    }
    validated_towel = StylistPlan.model_validate(towel_plan)
    assert validated_towel.scene.frame == "Portrait · 4:5"
    assert validated_towel.product_role == "hero"

    # 2. Tableware / Accessory Reverse Role (Bookends)
    bookend_plan = _valid_stylist_plan_dict()
    bookend_plan["product_role"] = "hero"
    bookend_plan["hero_prominence"] = "The ceramic bookend pair flanks a row of art monographs on the center eye-level shelf"
    bookend_plan["scene"] = {
        "frame": "Square · 1:1",
        "setting": "A calm study with oak shelving and ivory plaster wall background",
        "light": "Directional desk lamp lighting complemented by soft daylight",
        "camera": "Eye-level 50mm close shot focused directly on the bookends holding books upright",
        "presentation": "Pair actively supporting heavy hardback books on solid oak bookshelf",
    }
    bookend_plan["selected_layout"]["functional_use"] = "Bookends provide credible structural support to hardcover volumes"
    bookend_plan["view_requirements"] = {
        "close_up_requirements": "Close-up showing grooved off-white ceramic surface and speckle texture",
        "wide_view_requirements": "Full shelf view showing both bookends in place",
        "detail_focus": "Curved ridge detail and speckled glaze",
    }
    validated_bookend = StylistPlan.model_validate(bookend_plan)
    assert validated_bookend.product_role == "hero"
    assert "ceramic bookend" in validated_bookend.hero_prominence

    # 3. Dining set
    dining_plan = _valid_stylist_plan_dict()
    dining_plan["product_role"] = "hero"
    dining_plan["hero_prominence"] = "The 8-person dining table and matching chairs occupy the main dining hall axis"
    dining_plan["scene"] = {
        "frame": "Landscape · 16:9",
        "setting": "An airy dining room with French oak chevron floors and off-white paneled walls",
        "light": "Warm afternoon light through sheer linen window drapery",
        "camera": "Wide angle from head of table showing all 8 chairs and full tabletop clearly",
        "presentation": "All chairs neatly tucked under table with table runner and ceramic centerpiece",
    }
    validated_dining = StylistPlan.model_validate(dining_plan)
    assert validated_dining.product_role == "hero"
