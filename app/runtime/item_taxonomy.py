"""Load the canonical UIMidas item taxonomy. Do not invent department ids."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

_TAXONOMY_TS = (
    Path(__file__).resolve().parents[1].parent / "UIMidas" / "src" / "config" / "midasTaxonomy.ts"
)

ALLOWED_REFERENCE_TYPES = frozenset(
    {
        "product_image",
        "other_view",
        "room_image",
        "inspiration",
        "previous_result",
        "specification_file",
    }
)
IMAGE_REFERENCE_TYPES = frozenset(ALLOWED_REFERENCE_TYPES - {"specification_file"})

_REFERENCE_TYPE_ALIASES = {
    "product_image": (
        "product / vendor reference",
        "product image",
        "product",
        "vendor reference",
    ),
    "room_image": ("room / target space", "room image", "room", "target space"),
    "inspiration": ("inspiration / look", "inspiration", "look"),
    "previous_result": ("previous result",),
    "other_view": ("other views / pieces", "other view", "other views", "other pieces"),
    "specification_file": ("specifications / excel", "specification file", "specifications", "excel"),
}


def coerce_reference_type(value: str | None) -> str | None:
    if value is None:
        return None
    raw = value.strip()
    if not raw:
        return None
    if raw in ALLOWED_REFERENCE_TYPES:
        return raw
    folded = raw.casefold()
    for type_id, aliases in _REFERENCE_TYPE_ALIASES.items():
        if folded == type_id or folded == type_id.replace("_", " ") or folded in aliases:
            return type_id
    return None


@lru_cache(maxsize=1)
def load_item_taxonomy() -> list[dict[str, Any]]:
    text = _TAXONOMY_TS.read_text(encoding="utf-8")
    departments = _parse_ts_array(text, "departmentTaxonomy")
    sections = _parse_ts_array(text, "websiteSectionTaxonomy")
    return [*departments, *sections]


def taxonomy_ids() -> tuple[set[str], set[str], set[str]]:
    departments: set[str] = set()
    categories: set[str] = set()
    subcategories: set[str] = set()
    for dept in load_item_taxonomy():
        dept_id = str(dept.get("id") or "")
        if dept_id:
            departments.add(dept_id)
        for category in dept.get("categories") or []:
            cat_id = str(category.get("id") or "")
            if cat_id:
                categories.add(cat_id)
            for sub in category.get("subcategories") or []:
                sub_id = str(sub.get("id") or "")
                if sub_id:
                    subcategories.add(sub_id)
    return departments, categories, subcategories


def taxonomy_option_catalog() -> list[dict[str, Any]]:
    """Canonical dropdown ids/labels for classification prompts. Do not invent nodes."""

    catalog: list[dict[str, Any]] = []
    for dept in load_item_taxonomy():
        categories: list[dict[str, Any]] = []
        for category in dept.get("categories") or []:
            subcategories = [
                {"id": str(sub.get("id") or ""), "label": str(sub.get("label") or "")}
                for sub in category.get("subcategories") or []
                if sub.get("id")
            ]
            cat_id = str(category.get("id") or "")
            if not cat_id:
                continue
            categories.append(
                {
                    "id": cat_id,
                    "label": str(category.get("label") or ""),
                    "subcategories": subcategories,
                }
            )
        dept_id = str(dept.get("id") or "")
        if not dept_id:
            continue
        catalog.append(
            {
                "id": dept_id,
                "label": str(dept.get("label") or ""),
                "type": dept.get("type"),
                "categories": categories,
            }
        )
    return catalog


def constrain_taxonomy(
    department: str | None,
    category: str | None,
    subcategory: str | None,
) -> tuple[str | None, str | None, str | None]:
    departments, categories, subcategories = taxonomy_ids()
    dept = department if department in departments else None
    cat = category if dept and category in categories and category.startswith(dept + "/") else None
    sub = (
        subcategory
        if cat and subcategory in subcategories and subcategory.startswith(cat)
        else None
    )
    if cat is None:
        sub = None
    if dept is None:
        cat = None
        sub = None
    return dept, cat, sub


def resolve_taxonomy(
    department: str | None,
    category: str | None,
    subcategory: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Map model ids or human labels onto existing taxonomy ids only."""

    by_id = constrain_taxonomy(department, category, subcategory)
    if by_id[0]:
        return by_id
    dept = _match_department(department)
    cat = _match_category(dept, category)
    sub = _match_subcategory(cat, subcategory)
    resolved = constrain_taxonomy(dept, cat, sub)
    if resolved[0]:
        return resolved
    hay = " ".join(part for part in (department, category, subcategory) if part)
    if not hay.strip():
        return None, None, None
    return match_taxonomy(hay)


def match_taxonomy(name: str, product_url: str = "") -> tuple[str | None, str | None, str | None]:
    """Pick the most specific existing taxonomy node whose label appears in name/URL."""

    hay = f"{name} {product_url}".casefold()
    best: tuple[int, str, str | None, str | None] | None = None
    for dept in load_item_taxonomy():
        dept_id = str(dept.get("id") or "")
        dept_label = str(dept.get("label") or "")
        kind_bonus = 1000 if dept.get("type") == "department" else 0
        for category in dept.get("categories") or []:
            cat_id = str(category.get("id") or "")
            cat_label = str(category.get("label") or "")
            for sub in category.get("subcategories") or []:
                sub_id = str(sub.get("id") or "")
                sub_label = str(sub.get("label") or "")
                if _label_hits(hay, sub_label, sub_id):
                    score = kind_bonus + 300 + len(sub_label)
                    if best is None or score > best[0]:
                        best = (score, dept_id, cat_id, sub_id)
            if _label_hits(hay, cat_label, cat_id):
                score = kind_bonus + 200 + len(cat_label)
                if best is None or score > best[0]:
                    best = (score, dept_id, cat_id, None)
        if _label_hits(hay, dept_label, dept_id):
            score = kind_bonus + 100 + len(dept_label)
            if best is None or score > best[0]:
                best = (score, dept_id, None, None)
    if best is None:
        return None, None, None
    return constrain_taxonomy(best[1], best[2], best[3])


def _field_equals(value: str | None, node_id: str, node_label: str) -> bool:
    if not value:
        return False
    raw = value.strip()
    if not raw:
        return False
    return raw == node_id or raw.casefold() == node_label.casefold()


def _match_department(value: str | None) -> str | None:
    if not value:
        return None
    ranked: tuple[int, str] | None = None
    for dept in load_item_taxonomy():
        dept_id = str(dept.get("id") or "")
        if not dept_id:
            continue
        if not _field_equals(value, dept_id, str(dept.get("label") or "")):
            continue
        score = 1000 if dept.get("type") == "department" else 0
        if ranked is None or score > ranked[0]:
            ranked = (score, dept_id)
    return ranked[1] if ranked else None


def _match_category(department_id: str | None, value: str | None) -> str | None:
    if not value:
        return None
    for dept in load_item_taxonomy():
        dept_id = str(dept.get("id") or "")
        if department_id and dept_id != department_id:
            continue
        for category in dept.get("categories") or []:
            cat_id = str(category.get("id") or "")
            if _field_equals(value, cat_id, str(category.get("label") or "")):
                return cat_id
    return None


def _match_subcategory(category_id: str | None, value: str | None) -> str | None:
    if not value or not category_id:
        return None
    for dept in load_item_taxonomy():
        for category in dept.get("categories") or []:
            if str(category.get("id") or "") != category_id:
                continue
            for sub in category.get("subcategories") or []:
                sub_id = str(sub.get("id") or "")
                if _field_equals(value, sub_id, str(sub.get("label") or "")):
                    return sub_id
    return None


def _label_hits(hay: str, label: str, node_id: str) -> bool:
    text = label.casefold().strip()
    if len(text) < 4:
        return False
    if text in hay:
        return True
    slug = node_id.rsplit("/", 1)[-1].replace("-", " ")
    return len(slug) >= 4 and slug in hay.replace("-", " ")


def _parse_ts_array(source: str, name: str) -> list[dict[str, Any]]:
    marker = f"export const {name} ="
    start = source.find(marker)
    if start < 0:
        return []
    bracket = source.find("[", start)
    if bracket < 0:
        return []
    depth = 0
    end = bracket
    for index, char in enumerate(source[bracket:], bracket):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    blob = source[bracket:end]
    blob = re.sub(r",\s*([}\]])", r"\1", blob)
    payload = json.loads(blob)
    return payload if isinstance(payload, list) else []
