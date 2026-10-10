"""Deterministic Stylist provider for local tests.

It does not call a network and does not invent catalogue evidence.
"""

from typing import Literal

from app.contracts.job import ImageProportions, ProductRole
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
from app.providers.stylist import StylistInput, StylistProviderRequest


class FakeStylistProvider:
    """In-memory provider. `requests` records exactly what the caller passed."""

    def __init__(
        self,
        violation: str | None = None,
        complements: list[MidasCompanion] | None = None,
    ) -> None:
        self.violation = violation
        self.complements = complements
        self.requests: list[StylistProviderRequest] = []

    def compose(self, request: StylistProviderRequest) -> StylistPlan:
        self.requests.append(request)
        return plan_for(
            request.stylist_input,
            violation=self.violation,
            complements=self.complements,
        )


def plan_for(
    stylist_input: StylistInput,
    *,
    violation: str | None = None,
    complements: list[MidasCompanion] | None = None,
) -> StylistPlan:
    """Build one StylistPlan bound to this StylistInput."""

    contract = stylist_input.contract
    brain_plan = stylist_input.brain_plan
    observation = stylist_input.observation
    verified_complements = (
        complements
        if complements is not None
        else list(stylist_input.verified_complements)
    )

    product_role: ProductRole = contract.item.product_role
    department = contract.item.department.casefold()
    category = contract.item.category.casefold()
    subcategory = contract.item.subcategory.casefold()

    frame: ImageProportions = contract.outputs.image_proportions

    # Determine hero prominence and presentation based on category and role
    if product_role == "hero":
        if "towel" in subcategory or "towel" in category or "textile" in department:
            hero_prominence = f"The {contract.item.subcategory} is the primary hero focal point, draped neatly in the foreground"
            presentation = f"The {contract.item.subcategory} is hung cleanly on a matching rail with visible texture and clean hems"
            functional_use = "Accessible reaching placement beside bathing/wash basin area"
            view_reqs = StylistViewRequirements(
                close_up_requirements=f"Close-up highlighting weave texture and stitching of {contract.item.subcategory}",
                wide_view_requirements="Contextual wide view of room setting",
                detail_focus="Fabric weave and border hem",
            )
            supporting_props = [
                GenericContextProp(
                    name="ceramic soap dish",
                    purpose="Functional vanity accessory",
                    placement="Adjacent vanity countertop",
                    is_midas_product=False,
                )
            ]
        elif "bookend" in subcategory or "accessories" in department:
            hero_prominence = f"The {contract.item.subcategory} pair is positioned front and center on the main eye-level shelf"
            presentation = f"The {contract.item.subcategory} securely supports a sequence of hardcover volumes"
            functional_use = "Credible structural support for books on open shelf"
            view_reqs = StylistViewRequirements(
                close_up_requirements=f"Detail view showing surface texture and craftsmanship of {contract.item.subcategory}",
                wide_view_requirements="Full shelf arrangement showing surrounding books",
                detail_focus="Groove joinery and ceramic glaze finish",
            )
            supporting_props = [
                GenericContextProp(
                    name="Hardcover art monographs",
                    purpose="Books functionally supported by the hero bookends",
                    placement="Between the bookends on shelf",
                    is_midas_product=False,
                )
            ]
        else:
            # Furniture / Seating / Tables / General hero
            hero_prominence = f"The {contract.item.subcategory} is the central anchor of the scene, commanding clear visual hierarchy"
            presentation = f"The {contract.item.subcategory} is positioned with generous surrounding clearance and all pieces fully countable"
            functional_use = f"Arranged for comfortable circulation and functional conversation/living use"
            view_reqs = StylistViewRequirements(
                close_up_requirements=f"Close-up view of material upholstery and joint details on {contract.item.subcategory}",
                wide_view_requirements="Full room perspective with all furniture pieces countable",
                detail_focus="Joinery and fabric seam detail",
            )
            supporting_props = [
                GenericContextProp(
                    name="Potted indoor plant",
                    purpose="Natural contextual greenery placed away from hero sightline",
                    placement="Corner background beside window",
                    is_midas_product=False,
                )
            ]
    else:
        # Supporting product role
        hero_prominence = f"The {contract.item.subcategory} serves as a supporting accent harmonizing with the main space"
        presentation = f"The {contract.item.subcategory} is integrated naturally alongside the primary furniture pieces"
        functional_use = "Provides complementary support within the functional space"
        view_reqs = StylistViewRequirements(
            close_up_requirements=None,
            wide_view_requirements="Full scene showing supporting relationship to room",
            detail_focus=None,
        )
        supporting_props = []

    white_bk = "White BK" in contract.intent.requested_outcomes
    if white_bk:
        hero_prominence = (
            f"The {contract.item.subcategory} is the sole subject on a pure white (#FFFFFF) background"
        )
        presentation = (
            f"The {contract.item.subcategory} alone on a pure white (#FFFFFF) background; "
            "no room, no lifestyle scene, no decorative props, no floor or wall scene, no added text or logos"
        )
        functional_use = "Catalogue white-background product shot"
        view_reqs = StylistViewRequirements(
            close_up_requirements=(
                f"Close-up of {contract.item.subcategory} on a pure white (#FFFFFF) background"
            ),
            wide_view_requirements=(
                "Product alone on a pure white (#FFFFFF) background; no room, no lifestyle scene"
            ),
            detail_focus="Product construction and materials only; do not add logos or text",
        )
        supporting_props = []
        verified_complements = []

    # Lighting and setting derived from preferences and contract
    wall_color = contract.preferences.wall
    floor_finish = contract.preferences.floor
    light_pref = contract.preferences.lighting
    mood_pref = contract.preferences.mood

    if white_bk:
        setting = (
            "Pure white (#FFFFFF) studio background. Product alone. "
            "No room, no lifestyle scene, no decorative props, no floor or wall scene."
        )
        light = (
            f"{light_pref} on the product against a pure white (#FFFFFF) background. "
            "No interior window or room lighting scene."
        )
        camera = (
            "Eye-level product shot keeping all product pieces completely visible, "
            "unobstructed, and clearly countable."
        )
        surfaces = "Pure white (#FFFFFF) background only; no floor or wall scene"
        palette = "Pure white (#FFFFFF) background; preserve product color unchanged"
        spacing = "Product centered in an empty white field"
        circulation = "No room circulation; product-only frame"
        arrangement_detail = (
            "Hero alone on pure white (#FFFFFF); no props, no room, no lifestyle scene"
        )
    else:
        setting = (
            f"A {mood_pref.lower()} interior with {wall_color.lower()} walls and "
            f"{floor_finish.lower()} flooring, tailored to complement the product."
        )
        light = f"{light_pref} illuminating the space gently from natural window openings."
        camera = (
            "Eye-level shot keeping all product pieces completely visible, "
            "unobstructed, and clearly countable."
        )
        surfaces = f"{floor_finish} flooring with smooth {wall_color} wall surfaces"
        palette = f"{wall_color}, {floor_finish}, and complementary neutral accents"
        spacing = "Generous functional spacing and clear circulation paths"
        circulation = "Clear 80cm walkways around main pieces"
        arrangement_detail = "Hero centered with realistic placement and clear sightlines"

    scene = StylistScene(
        frame=frame,
        setting=setting,
        light=light,
        camera=camera,
        presentation=presentation,
    )

    # Genuine companion SKUs only
    if violation == "unverified_companion":
        verified_complements = [
            MidasCompanion(
                sku="UNVERIFIED-SKU-999",
                name="Unverified Accent Lamp",
                category="Lighting",
                product_url="https://midas.example/lamp",
                image_hash="aa" * 32,
                dimensions="30x30 cm",
                availability="in_stock",
                function="Accent lighting",
                source_reference="ref-fake",
            )
        ]
    companion_skus = [c.sku for c in verified_complements]


    board_1 = CandidateBoard(
        board_id="board-primary-cohesive",
        name=f"Cohesive {contract.preferences.mood}",
        focal_hierarchy=hero_prominence,
        palette=palette,
        spacing=spacing,
        surfaces=surfaces,
        lighting=light,
        circulation=circulation,
        companion_skus=companion_skus,
    )

    board_2 = CandidateBoard(
        board_id="board-secondary-contrast",
        name="High Contrast Alternative",
        focal_hierarchy="Accentuated focal point with stark foreground/background contrast",
        palette="High-contrast dark and light tones",
        spacing="Tighter compact arrangement",
        surfaces="Glossy reflective surfaces",
        lighting="Direct dramatic overhead lighting",
        circulation="Narrow 50cm circulation walkway",
        companion_skus=companion_skus,
    )

    selected_layout = SelectedLayout(
        board_id="board-primary-cohesive" if violation != "invalid_board" else "board-nonexistent",
        focal_hierarchy=hero_prominence,
        palette=palette,
        spacing=spacing,
        surfaces=surfaces,
        lighting=light,
        circulation=circulation,
        arrangement_detail=arrangement_detail,
        functional_use=functional_use,
    )

    rejected_alternatives = [
        RejectedAlternative(
            board_id="board-secondary-contrast",
            reason="High-contrast lighting creates harsh glare and tight spacing restricts circulation",
        )
    ]

    # Unknowns from Eye & Brain
    if violation == "drop_unknowns":
        unknowns = []
    else:
        unknowns = [
            StylistUnknown(subject=item.subject, detail=item.detail)
            for item in brain_plan.unknowns
        ]
        if not unknowns:
            unknowns = [
                StylistUnknown(
                    subject=item.subject,
                    detail=item.detail,
                )
                for item in observation.unknowns
            ]

    risks = [
        "Potential shadow obstruction on fine details",
        "Color temperature shift on material texture",
    ]

    status: Literal["ready", "hold"] = "hold" if violation == "hold" else "ready"
    hold_reasons = ["Stylist hold requested for testing"] if status == "hold" else []

    brain_contract_id = (
        contract.contract_id
        if violation != "mismatched_brain_contract"
        else "mismatched-contract-id"
    )
    brain_revision = (
        contract.revision
        if violation != "mismatched_brain_revision"
        else contract.revision + 99
    )

    return StylistPlan(
        job_id=stylist_input.job_id,
        contract_id=contract.contract_id,
        contract_revision=contract.revision,
        brain_contract_id=brain_contract_id,
        brain_revision=brain_revision,
        product_role=product_role,
        hero_prominence=hero_prominence,
        scene=scene,
        candidate_boards=[board_1, board_2],
        selected_layout=selected_layout,
        rejected_alternatives=rejected_alternatives,
        functional_rationale=f"Selected layout provides optimal lighting, realistic functional spacing, and preserves product visibility",
        midas_complements=verified_complements,
        supporting_props=supporting_props,
        view_requirements=view_reqs,
        risks=risks,
        unknowns=unknowns,
        status=status,
        hold_reasons=hold_reasons,
    )
