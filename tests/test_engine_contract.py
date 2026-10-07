import pytest
from pydantic import ValidationError

from app.contracts.engine import EngineCompile, EngineOutputFormat

HASH_A = "a1" * 32
HASH_B = "b2" * 32
HASH_C = "c3" * 32


def _reference(
    reference_id: str = "ref-product",
    filename: str = "product.png",
    media_type: str = "PNG",
    content_hash: str = HASH_A,
    role: str = "Product / vendor reference",
) -> dict:
    return {
        "reference_id": reference_id,
        "filename": filename,
        "media_type": media_type,
        "hash_algorithm": "sha256",
        "content_hash": content_hash,
        "role": role,
    }


def _locks() -> list[dict]:
    return [
        {
            "name": "count",
            "value": "1",
            "source": "contract.intent.selected_count",
            "evidence_reference_id": None,
        },
        {
            "name": "identity",
            "value": "visible product identity from vendor reference",
            "source": "contract.changes.protected_identity",
            "evidence_reference_id": "ref-product",
        },
        {
            "name": "source-supported construction",
            "value": "visible construction from Eye",
            "source": "eye.items",
            "evidence_reference_id": "ref-product",
        },
    ]


def _variables() -> list[dict]:
    return [
        {"name": "room", "value": "styled interior setting", "authorized": True},
        {"name": "styling", "value": "Calm & natural", "authorized": True},
        {"name": "light", "value": "Soft daylight", "authorized": True},
        {"name": "framing", "value": "Wide view", "authorized": True},
        {"name": "authorised edits", "value": "styled setting", "authorized": True},
    ]


def _scene() -> dict:
    return {
        "frame": "Landscape · 16:9",
        "setting": "A calm interior with limestone floors and off-white walls",
        "light": "Soft natural daylight from a lateral aperture",
        "camera": "Eye-level 50mm view that keeps the full product in frame",
        "presentation": "Hero product readable with authorised companions",
    }


def _selected_layout() -> dict:
    return {
        "board_id": "board-selected",
        "focal_hierarchy": "Hero product centred; authorised companions secondary",
        "palette": "Warm neutrals with one darker wood accent",
        "spacing": "Clear circulation around the hero",
        "surfaces": "Limestone floor and plaster wall",
        "lighting": "Soft daylight",
        "circulation": "Open foreground path",
        "arrangement_detail": "Hero 1.5m from backdrop; companions to the right",
        "functional_use": "Hero remains usable in the scene",
    }


def _valid_compile_dict() -> dict:
    return {
        "job_id": "job-textile-001",
        "contract_id": "contract-textile-1",
        "contract_revision": 2,
        "brain_contract_id": "contract-textile-1",
        "brain_revision": 2,
        "stylist_contract_id": "contract-textile-1",
        "stylist_revision": 2,
        "product_role": "hero",
        "references": [
            _reference(),
            _reference(
                reference_id="ref-room",
                filename="room.jpg",
                media_type="JPG",
                content_hash=HASH_B,
                role="Room / target space",
            ),
            _reference(
                reference_id="ref-look",
                filename="look.webp",
                media_type="WebP",
                content_hash=HASH_C,
                role="Inspiration / look",
            ),
        ],
        "locks": _locks(),
        "variables": _variables(),
        "scene": _scene(),
        "selected_layout": _selected_layout(),
        "hero_prominence": "The textile is the readable focal object in the composition",
        "requested_view": "Wide view",
        "view_requirements": {
            "close_up_requirements": "Border weave and hem must remain readable",
            "wide_view_requirements": "Full product silhouette in the styled setting",
            "detail_focus": "Waffle texture",
        },
        "output_format": {
            "image_proportions": "Landscape · 16:9",
            "resolution": "2K",
        },
        "exact_prompt": (
            "Preserve the source textile identity and count of 1. "
            "Place it in the approved styled interior under soft daylight. "
            "Do not invent fibre composition."
        ),
        "model_id": "caller-supplied-model",
        "unknowns": [
            {
                "subject": "fibre composition",
                "detail": "the photograph does not establish fibre or GSM",
            }
        ],
        "status": "ready",
        "hold_reasons": [],
    }


def test_valid_generalized_engine_compile() -> None:
    artifact = EngineCompile.model_validate(_valid_compile_dict())
    assert artifact.job_id == "job-textile-001"
    assert artifact.status == "ready"
    assert artifact.product_role == "hero"
    assert artifact.exact_prompt.startswith("Preserve the source textile")
    assert artifact.output_format.resolution == "2K"


def test_required_identity_and_binding_fields() -> None:
    artifact = EngineCompile.model_validate(_valid_compile_dict())
    assert artifact.contract_id == "contract-textile-1"
    assert artifact.contract_revision == 2
    assert artifact.brain_contract_id == artifact.contract_id
    assert artifact.brain_revision == artifact.contract_revision
    assert artifact.stylist_contract_id == artifact.contract_id
    assert artifact.stylist_revision == artifact.contract_revision

    mismatched_brain = _valid_compile_dict()
    mismatched_brain["brain_contract_id"] = "other-contract"
    with pytest.raises(ValidationError, match="same contract as BrainPlan"):
        EngineCompile.model_validate(mismatched_brain)

    mismatched_stylist = _valid_compile_dict()
    mismatched_stylist["stylist_revision"] = 9
    with pytest.raises(ValidationError, match="same revision as StylistPlan"):
        EngineCompile.model_validate(mismatched_stylist)

    missing = _valid_compile_dict()
    del missing["job_id"]
    with pytest.raises(ValidationError):
        EngineCompile.model_validate(missing)


def test_reference_roles_preserved() -> None:
    artifact = EngineCompile.model_validate(_valid_compile_dict())
    assert [item.role for item in artifact.references] == [
        "Product / vendor reference",
        "Room / target space",
        "Inspiration / look",
    ]
    assert artifact.references[0].content_hash == HASH_A
    assert artifact.references[0].media_type == "PNG"
    assert artifact.references[0].hash_algorithm == "sha256"


def test_reference_ordering_preserved() -> None:
    artifact = EngineCompile.model_validate(_valid_compile_dict())
    assert [item.reference_id for item in artifact.references] == [
        "ref-product",
        "ref-room",
        "ref-look",
    ]
    dumped = artifact.model_dump()
    assert [item["reference_id"] for item in dumped["references"]] == [
        "ref-product",
        "ref-room",
        "ref-look",
    ]

    duplicate = _valid_compile_dict()
    duplicate["references"][1]["reference_id"] = "ref-product"
    with pytest.raises(ValidationError, match="reference_id values must be unique"):
        EngineCompile.model_validate(duplicate)


def test_locks_preserved() -> None:
    artifact = EngineCompile.model_validate(_valid_compile_dict())
    names = [item.name for item in artifact.locks]
    assert names == ["count", "identity", "source-supported construction"]
    assert artifact.locks[0].value == "1"
    assert artifact.locks[1].value == "visible product identity from vendor reference"

    missing_count = _valid_compile_dict()
    missing_count["locks"] = [lock for lock in _locks() if lock["name"] != "count"]
    with pytest.raises(ValidationError, match="preserve count"):
        EngineCompile.model_validate(missing_count)

    missing_construction = _valid_compile_dict()
    missing_construction["locks"] = [
        lock for lock in _locks() if lock["name"] != "source-supported construction"
    ]
    with pytest.raises(ValidationError, match="source-supported construction"):
        EngineCompile.model_validate(missing_construction)


def test_scene_and_stylist_direction_preserved() -> None:
    artifact = EngineCompile.model_validate(_valid_compile_dict())
    assert artifact.scene.setting.startswith("A calm interior")
    assert artifact.scene.light.startswith("Soft natural daylight")
    assert artifact.scene.camera.startswith("Eye-level")
    assert artifact.scene.presentation.startswith("Hero product")
    assert artifact.hero_prominence.startswith("The textile")
    assert artifact.selected_layout.board_id == "board-selected"
    assert artifact.variables[0].name == "room"
    assert artifact.requested_view == "Wide view"
    assert artifact.view_requirements.detail_focus == "Waffle texture"


def test_exact_compiled_instruction_required() -> None:
    artifact = EngineCompile.model_validate(_valid_compile_dict())
    assert artifact.exact_prompt.strip()

    blank = _valid_compile_dict()
    blank["exact_prompt"] = "   "
    with pytest.raises(ValidationError, match="exact prompt"):
        EngineCompile.model_validate(blank)

    missing = _valid_compile_dict()
    del missing["exact_prompt"]
    with pytest.raises(ValidationError):
        EngineCompile.model_validate(missing)


def test_output_format_validation() -> None:
    artifact = EngineCompile.model_validate(_valid_compile_dict())
    assert artifact.output_format.image_proportions == "Landscape · 16:9"
    assert artifact.output_format.resolution == "2K"

    invalid_ratio = _valid_compile_dict()
    invalid_ratio["output_format"]["image_proportions"] = "2.39:1"
    with pytest.raises(ValidationError):
        EngineCompile.model_validate(invalid_ratio)

    extra_format = _valid_compile_dict()
    extra_format["output_format"]["mime_type"] = "image/png"
    with pytest.raises(ValidationError):
        EngineCompile.model_validate(extra_format)

    EngineOutputFormat.model_validate(
        {"image_proportions": "Square · 1:1", "resolution": "4K"}
    )


def test_model_version_follows_existing_boundary() -> None:
    artifact = EngineCompile.model_validate(_valid_compile_dict())
    assert artifact.model_id == "caller-supplied-model"

    blank = _valid_compile_dict()
    blank["model_id"] = ""
    with pytest.raises(ValidationError, match="caller-recorded model identifier"):
        EngineCompile.model_validate(blank)

    ranking = _valid_compile_dict()
    ranking["capability_checks"] = ["vision"]
    with pytest.raises(ValidationError):
        EngineCompile.model_validate(ranking)

    fallback = _valid_compile_dict()
    fallback["fallback_reason"] = "cheaper model"
    with pytest.raises(ValidationError):
        EngineCompile.model_validate(fallback)


def test_unknowns_can_be_preserved() -> None:
    payload = _valid_compile_dict()
    payload["unknowns"] = [
        {"subject": "fibre composition", "detail": "not established by the source"},
        {"subject": "hidden geometry", "detail": "unseen reverse face remains unknown"},
    ]
    artifact = EngineCompile.model_validate(payload)
    assert len(artifact.unknowns) == 2
    assert artifact.unknowns[1].subject == "hidden geometry"

    empty = _valid_compile_dict()
    empty["unknowns"] = []
    EngineCompile.model_validate(empty)


def test_invalid_status_rejected() -> None:
    payload = _valid_compile_dict()
    payload["status"] = "compiled"
    with pytest.raises(ValidationError):
        EngineCompile.model_validate(payload)


def test_hold_requires_explicit_reasons() -> None:
    payload = _valid_compile_dict()
    payload["status"] = "hold"
    payload["hold_reasons"] = []
    payload["exact_prompt"] = ""
    with pytest.raises(ValidationError, match="at least one hold reason"):
        EngineCompile.model_validate(payload)

    payload["hold_reasons"] = [
        "critical unknown: fibre composition is not established and cannot be asserted"
    ]
    held = EngineCompile.model_validate(payload)
    assert held.status == "hold"
    assert held.exact_prompt == ""
    assert len(held.hold_reasons) == 1

    ready_with_hold = _valid_compile_dict()
    ready_with_hold["hold_reasons"] = ["should not be ready"]
    with pytest.raises(ValidationError, match="must not have hold reasons"):
        EngineCompile.model_validate(ready_with_hold)


def test_no_provider_specific_fields_accepted() -> None:
    for field, value in (
        ("magnfic_settings", {"strength": 0.4}),
        ("openrouter_request", {"messages": []}),
        ("qdrant_id", "vec-1"),
        ("embedding_id", "emb-1"),
        ("vector_score", 0.91),
        ("prompt_score", 0.8),
        ("style_score", 0.7),
        ("generation_score", 0.6),
        ("visual_similarity_score", 0.5),
        ("token_budget", 4096),
        ("provider_latency", 12.0),
        ("provider_cost", 0.02),
        ("image_generation_parameters", {"cfg": 7}),
    ):
        payload = _valid_compile_dict()
        payload[field] = value
        with pytest.raises(ValidationError):
            EngineCompile.model_validate(payload)


def test_multiple_product_categories_use_the_same_contract() -> None:
    towel = _valid_compile_dict()
    towel["hero_prominence"] = "Waffle-weave bath towel on a brass rail"
    towel["requested_view"] = "Close-up"
    towel["output_format"] = {
        "image_proportions": "Portrait · 4:5",
        "resolution": "2K",
    }
    towel["exact_prompt"] = (
        "Keep the towel identity and count of 1. Close-up of waffle texture. "
        "Do not assert fibre composition."
    )
    validated_towel = EngineCompile.model_validate(towel)
    assert validated_towel.requested_view == "Close-up"
    assert validated_towel.output_format.image_proportions == "Portrait · 4:5"

    tableware = _valid_compile_dict()
    tableware["job_id"] = "job-bookends-001"
    tableware["product_role"] = "hero"
    tableware["hero_prominence"] = "Ceramic bookend pair supporting books on a shelf"
    tableware["locks"][0]["value"] = "2"
    tableware["requested_view"] = "Wide view + close-up"
    tableware["exact_prompt"] = (
        "Show both bookends supporting books. Preserve pair count of 2. "
        "Do not invent exact ceramic composition."
    )
    validated_tableware = EngineCompile.model_validate(tableware)
    assert validated_tableware.locks[0].value == "2"
    assert validated_tableware.requested_view == "Wide view + close-up"

    dining = _valid_compile_dict()
    dining["job_id"] = "job-dining-001"
    dining["hero_prominence"] = "Twelve dining chairs around the table"
    dining["locks"][0]["value"] = "12"
    dining["exact_prompt"] = (
        "Keep all twelve chairs and the table identity. "
        "Do not reduce the set to a styled fragment."
    )
    validated_dining = EngineCompile.model_validate(dining)
    assert validated_dining.locks[0].value == "12"
    assert validated_dining.product_role == "hero"

    accessory = _valid_compile_dict()
    accessory["product_role"] = "supporting"
    accessory["hero_prominence"] = "Napkin rings remain readable at the place setting"
    accessory["exact_prompt"] = (
        "Keep napkin-ring identity while the table setting supports their use."
    )
    validated_accessory = EngineCompile.model_validate(accessory)
    assert validated_accessory.product_role == "supporting"
