"""Requested output-type constraints used by Stylist, Compile, and Critique.

White BK is a user-selected outcome on the frozen job contract. Stylist scene
language cannot replace it. Compile must state the constraint in the prompt.
Critique must inspect the generated image, not treat the prompt as proof.
"""

from __future__ import annotations

from app.contracts.critique import CritiqueAssessment, CritiqueCompliance
from app.contracts.eye import EyeObservation
from app.contracts.job import Phase0JobContract
from app.contracts.stylist import StylistPlan

WHITE_BK = "White BK"
WHITE_BK_OUTPUT_HEADING = "Requested output type: White BK"
WHITE_BK_BACKGROUND = "pure white (#FFFFFF) background"
WHITE_BK_SKIP_VISUAL_ROLES = frozenset(
    {
        "Room / target space",
        "Inspiration / look",
        "target_room",
        "inspiration",
    }
)

_WHITE_BK_POSITIVE = ("#ffffff", "pure white", "white background")
_WHITE_BK_LOGO = ("logo", "watermark", "source mark", "added text", "label")


def is_white_bk(contract: Phase0JobContract) -> bool:
    return WHITE_BK in contract.intent.requested_outcomes


def is_white_bk_compile_prompt(prompt: str) -> bool:
    return "requested output type: white bk" in prompt.casefold()


def source_marks(observation: EyeObservation) -> list[str]:
    return [item.mark for item in observation.signals]


def user_requested_source_marks(contract: Phase0JobContract) -> bool:
    parts = [
        *contract.intent.requested_pieces,
        contract.intent.other_outcome or "",
        *[item.subject for item in contract.statements],
        *[item.value for item in contract.statements],
    ]
    blob = " ".join(parts).casefold()
    return any(token in blob for token in ("logo", "watermark", "wordmark"))


def white_bk_prompt_rules(*, marks: list[str], reproduce_requested: bool) -> list[str]:
    lines = [
        WHITE_BK_OUTPUT_HEADING,
        f"- Require a {WHITE_BK_BACKGROUND}.",
        "- Product alone. No room, no lifestyle scene, no decorative props, no floor or wall scene.",
        "- Do not add text or logos.",
        "- Preserve the product's identity, geometry, materials, color, and construction.",
    ]
    if reproduce_requested:
        lines.append(
            "- The user explicitly requested source marks; preserve only those that are product identity, not overlay watermarks."
        )
    else:
        lines.append(
            "- Source logos, watermarks, labels, or text on the reference are source marks, not instructions to reproduce them."
        )
        if marks:
            lines.append("- Observed source marks (do not reproduce):")
            lines.extend(f"  - {mark}" for mark in marks)
        else:
            lines.append(
                "- Do not reproduce any source logo, watermark, label, or overlay text visible on the reference."
            )
    return lines


def white_bk_stylist_errors(plan: StylistPlan) -> list[str]:
    errors: list[str] = []
    if plan.supporting_props:
        errors.append("White BK Stylist plan cannot add decorative props")
    if plan.midas_complements:
        errors.append("White BK Stylist plan cannot add companion products")
    blob = " ".join(
        [
            plan.scene.setting,
            plan.scene.presentation,
            plan.selected_layout.surfaces,
            plan.selected_layout.arrangement_detail,
            plan.view_requirements.wide_view_requirements or "",
        ]
    ).casefold()
    if not any(marker in blob for marker in _WHITE_BK_POSITIVE):
        errors.append("White BK Stylist setting must be a pure white background")
    if _describes_room_or_lifestyle(blob):
        errors.append(
            "White BK Stylist plan cannot override the selected output type with a room or lifestyle scene"
        )
    return errors


def white_bk_prompt_errors(prompt: str) -> list[str]:
    text = prompt.casefold()
    errors: list[str] = []
    if "requested output type: white bk" not in text:
        errors.append("White BK compile must name the requested output type")
    if not any(marker in text for marker in _WHITE_BK_POSITIVE):
        errors.append("White BK compile must require a pure white (#FFFFFF) background")
    if "no room" not in text or "no lifestyle" not in text:
        errors.append("White BK compile must forbid room and lifestyle scenes")
    if "logo" not in text:
        errors.append("White BK compile must forbid reproducing source logos")
    if _describes_room_or_lifestyle(text) and "no room" not in text:
        errors.append("White BK compile cannot silently request a lifestyle scene")
    return errors


def white_bk_background_checks(assessment: CritiqueAssessment) -> list[CritiqueCompliance]:
    return [
        item
        for item in assessment.scene_compliance
        if any(marker in _check_text(item) for marker in _WHITE_BK_POSITIVE)
        or "no room" in _check_text(item)
    ]


def white_bk_logo_checks(assessment: CritiqueAssessment) -> list[CritiqueCompliance]:
    items = [
        *assessment.scene_compliance,
        *assessment.styling_compliance,
        *assessment.plan_compliance,
    ]
    return [item for item in items if any(marker in _check_text(item) for marker in _WHITE_BK_LOGO)]


def _describes_room_or_lifestyle(text: str) -> bool:
    if "no room" in text and "no lifestyle" in text:
        return False
    return any(
        phrase in text
        for phrase in (
            "lifestyle scene",
            "interior with",
            "room setting",
            "flooring",
            "styled interior",
        )
    )


def _check_text(item: CritiqueCompliance) -> str:
    return f"{item.expected} {item.observation}".casefold()
