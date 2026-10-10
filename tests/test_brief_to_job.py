"""Saved UIMidas brief → Phase-0 job. Fake providers only. No generation."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.contracts.brief_mapping import (
    BRIEF_MAPPING_UNRESOLVED,
    MISSING_REFERENCE_BYTES,
    UNREPRESENTABLE_FIELD,
    UNSUPPORTED_RESOLUTION,
    UNRESOLVED_OUTPUT,
    UNRESOLVED_PREFERENCES,
    UNRESOLVED_REFERENCE,
)
from app.runtime.pixels import expected_pixels, inspect_image
from app.contracts.engine import EngineOutputFormat
from app.contracts.client_brief import dump_omitting_optional_nones
from app.main import app
from app.runtime.client_briefs import CLIENT_BRIEF_STORE
from app.runtime.orchestrator import join_scheduled_planning
from app.runtime.state import JOB_STORE
from app.providers.fake_generation import FAKE_OUTPUT_BYTES
from tests.png_bytes import PNG_B64
from tests.test_client_brief import _PLACEHOLDERS, _populated_uimidas_payload

_PHASE0_NOT_IN_BRIEF = {
    "source_condition": {"input_condition": "clean pack shot"},
    "changes": {
        "policy_mode": "fidelity-locked",
        "allowed_changes": ["styled setting"],
        "protected_identity": ["product identity"],
        "room_locks": [],
        "creative_variables": [],
    },
    "product_role": "hero",
    "package_members": ["lifestyle"],
}


def _client() -> TestClient:
    return TestClient(app)


def _slice_payload() -> dict[str, Any]:
    return {
        "endpoint": "POST /api/studio/v2/jobs",
        "contractVersion": "studio-jobs-v2-draft",
        "idempotencyKey": "slice-key",
        **_PLACEHOLDERS,
        "category": "home-furniture/living-rooms",
        "role": None,
        "package": [
            {
                "itemId": "item-1",
                "productGroupId": "group-1",
                "outputs": [
                    {
                        "concept": "lifestyle",
                        "views": ["wide_view"],
                        "proportion": "1:1",
                        "resolution": "2k",
                    }
                ],
            }
        ],
        "brief": {
            "job": {"kind": "new_project", "newProjectMode": "one_by_one"},
            "items": [
                {
                    "id": "item-1",
                    "productGroupId": "group-1",
                    "categoryState": "specified",
                    "department": "home-furniture",
                    "category": "home-furniture/living-rooms",
                    "subcategory": "home-furniture/living-rooms/sofa",
                    "references": [
                        {
                            "id": "ref-product",
                            "type": "product_image",
                            "source": "local_file",
                            "role": "product",
                            "relationship": "same_product",
                            "productGroupId": "group-1",
                            "evidence": {
                                "fileName": "sofa.png",
                                "mediaKind": "image",
                                "sizeBytes": 2048,
                                "libraryKey": None,
                            },
                        }
                    ],
                    "requestedPackage": [
                        {
                            "concept": "lifestyle",
                            "views": ["wide_view"],
                            "proportion": "1:1",
                            "resolution": "2k",
                        }
                    ],
                    "metadata": {"itemCount": 1},
                }
            ],
            "preferences": {
                "lighting": "soft_daylight",
                "wall": "ivory",
                "floor": "light_oak",
            },
            "suggestions": {
                "plants": "leave_out",
                "human": "leave_out",
                "mood": "calm_natural",
            },
        },
    }


def _persist_slice() -> dict[str, Any]:
    response = _client().post(
        "/api/v1/client-briefs",
        json={
            "owner_id": "owner-slice",
            "contract_id": "contract-slice-1",
            "revision": 1,
            "client_brief": _slice_payload(),
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _prepare(brief_id: str, body: dict[str, Any], owner_id: str = "owner-slice"):
    return _client().post(
        f"/api/v1/client-briefs/{brief_id}/jobs",
        params={"owner_id": owner_id, "revision": 1},
        json=body,
    )


def test_browser_like_brief_reports_unresolved_phase0_blockers_and_creates_no_job() -> None:
    payload = _slice_payload()
    payload["brief"]["preferences"] = {"useWorkflowDefaults": True}
    payload["brief"]["suggestions"] = {"mood": "automatic"}
    created = _client().post(
        "/api/v1/client-briefs",
        json={
            "owner_id": "owner-slice",
            "contract_id": "contract-browser-blockers",
            "revision": 1,
            "client_brief": payload,
        },
    )
    assert created.status_code == 200, created.text
    before = created.json()["client_brief"]
    response = _prepare(
        created.json()["brief_id"],
        {
            "reference_files": [
                {
                    "reference_id": "ref-product",
                    "content_base64": PNG_B64,
                    "media_type": "GIF",
                }
            ]
        },
    )
    assert response.status_code == 422, response.text
    codes = {issue["code"] for issue in response.json()["error"]["details"]["issues"]}
    assert UNRESOLVED_PREFERENCES in codes
    assert UNRESOLVED_REFERENCE in codes or MISSING_REFERENCE_BYTES in codes
    assert "UNRESOLVED_SOURCE_CONDITION" not in codes
    assert "UNRESOLVED_PRODUCT_ROLE" not in codes
    assert list(JOB_STORE._jobs) == []  # noqa: SLF001
    fetched = _client().get(f"/api/v1/client-briefs/{created.json()['brief_id']}")
    assert fetched.json()["client_brief"] == before


def test_complete_uimidas_brief_creates_a_job_without_phase0_form_fields() -> None:
    created = _persist_slice()
    brief_id = created["brief_id"]
    before = created["client_brief"]
    response = _prepare(
        brief_id,
        {
            "reference_files": [
                {
                    "reference_id": "ref-product",
                    "content_base64": PNG_B64,
                    "media_type": "PNG",
                }
            ]
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["generation_started"] is False
    assert body["pre_generation_approved"] is False
    job_id = body["job_id"]
    assert join_scheduled_planning(job_id) is True
    job = _client().get(f"/api/v1/jobs/{job_id}").json()
    assert job["contract"]["item"]["product_role"] == "hero"
    assert job["contract"]["source_condition"]["input_condition"] == "clean pack shot"
    assert job["contract"]["outputs"]["package_members"] == ["lifestyle"]
    assert job["contract"]["changes"]["protected_identity"] == ["uploaded product appearance"]
    denied = _client().post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "PRE_GENERATION_APPROVAL_REQUIRED"
    image = _generate_fake(job_id)
    assert image == FAKE_OUTPUT_BYTES
    fetched = _client().get(f"/api/v1/client-briefs/{brief_id}")
    assert fetched.json()["client_brief"] == before
    assert fetched.json()["brief_hash"] == created["brief_hash"]


def test_category_template_output_is_unresolved_even_with_caller_phase0_fields() -> None:
    payload = _populated_uimidas_payload()
    created = _client().post(
        "/api/v1/client-briefs",
        json={
            "owner_id": "owner-slice",
            "contract_id": "contract-slice-populated",
            "revision": 1,
            "client_brief": payload,
        },
    ).json()
    response = _prepare(
        created["brief_id"],
        {
            "reference_files": [
                {
                    "reference_id": "ref-product",
                    "content_base64": PNG_B64,
                    "media_type": "PNG",
                }
            ],
            "phase0_fields_not_in_brief": _PHASE0_NOT_IN_BRIEF,
        },
    )
    assert response.status_code == 422
    codes = {issue["code"] for issue in response.json()["error"]["details"]["issues"]}
    assert UNRESOLVED_OUTPUT in codes or "UNSUPPORTED_SLICE" in codes or UNREPRESENTABLE_FIELD in codes
    assert list(JOB_STORE._jobs) == []  # noqa: SLF001


def test_filename_without_bytes_does_not_create_a_job() -> None:
    created = _persist_slice()
    response = _prepare(
        created["brief_id"],
        {
            "reference_files": [
                {
                    "reference_id": "ref-product",
                    "content_base64": "   ",
                    "media_type": "PNG",
                }
            ],
            "phase0_fields_not_in_brief": _PHASE0_NOT_IN_BRIEF,
        },
    )
    assert response.status_code == 422
    codes = {issue["code"] for issue in response.json()["error"]["details"]["issues"]}
    assert MISSING_REFERENCE_BYTES in codes
    assert list(JOB_STORE._jobs) == []  # noqa: SLF001


def test_supported_slice_creates_job_runs_planning_and_stops_before_generate() -> None:
    created = _persist_slice()
    brief_id = created["brief_id"]
    before = created["client_brief"]
    response = _prepare(
        brief_id,
        {
            "reference_files": [
                {
                    "reference_id": "ref-product",
                    "content_base64": PNG_B64,
                    "media_type": "PNG",
                }
            ],
            "phase0_fields_not_in_brief": _PHASE0_NOT_IN_BRIEF,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["generation_started"] is False
    assert body["pre_generation_approved"] is False
    job_id = body["job_id"]
    assert join_scheduled_planning(job_id) is True

    status = _client().get(f"/api/v1/jobs/{job_id}/status").json()
    assert status["compile_available"] is True
    assert status["generation_available"] is False
    compile_res = _client().get(f"/api/v1/jobs/{job_id}/compile")
    assert compile_res.status_code == 200, compile_res.text
    generate_res = _client().post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert generate_res.status_code == 409
    assert generate_res.json()["error"]["code"] == "PRE_GENERATION_APPROVAL_REQUIRED"

    job = _client().get(f"/api/v1/jobs/{job_id}").json()
    assert "content_base64" not in str(job["contract"]["references"])
    assert job["contract"]["owner_id"] == "owner-slice"
    assert job["contract"]["intent"]["job_option"] == "One by one (same department)"
    assert "pre_generation_approval" not in job

    fetched = _client().get(f"/api/v1/client-briefs/{brief_id}").json()
    assert fetched["client_brief"] == before
    assert fetched["brief_hash"] == created["brief_hash"]
    stored = CLIENT_BRIEF_STORE.get(brief_id)
    assert stored is not None
    assert dump_omitting_optional_nones(stored.client_brief) == before


def test_supported_slice_requires_approval_then_generates_with_fake_provider() -> None:
    created = _persist_slice()
    response = _prepare(
        created["brief_id"],
        {
            "reference_files": [
                {
                    "reference_id": "ref-product",
                    "content_base64": PNG_B64,
                    "media_type": "PNG",
                }
            ],
            "phase0_fields_not_in_brief": _PHASE0_NOT_IN_BRIEF,
        },
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    assert join_scheduled_planning(job_id) is True

    denied = _client().post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "PRE_GENERATION_APPROVAL_REQUIRED"

    approved = _client().post(f"/api/v1/jobs/{job_id}/generate/approve", json={})
    assert approved.status_code == 200, approved.text
    assert _client().get(f"/api/v1/jobs/{job_id}/status").json()["generation_available"] is False

    generated = _client().post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert generated.status_code == 200, generated.text
    image = _client().get(f"/api/v1/jobs/{job_id}/generate/image")
    assert image.status_code == 200
    assert image.content == FAKE_OUTPUT_BYTES

    critique = _client().post(f"/api/v1/jobs/{job_id}/critique", json={})
    assert critique.status_code == 200, critique.text
    review = _client().post(f"/api/v1/jobs/{job_id}/review/approve", json={})
    assert review.status_code == 200, review.text
    release = _client().post(f"/api/v1/jobs/{job_id}/review/release", json={})
    assert release.status_code == 200, release.text


def test_persist_accepts_unexecutable_resolution_and_prepare_preserves_the_brief() -> None:
    payload = _slice_payload()
    payload["brief"]["items"][0]["requestedPackage"][0]["resolution"] = "web"
    payload["package"][0]["outputs"][0]["resolution"] = "web"
    created = _client().post(
        "/api/v1/client-briefs",
        json={
            "owner_id": "owner-slice",
            "contract_id": "contract-front-1",
            "revision": 1,
            "client_brief": payload,
        },
    )
    assert created.status_code == 200, created.text
    before = created.json()["client_brief"]
    response = _prepare(
        created.json()["brief_id"],
        {
            "reference_files": [
                {
                    "reference_id": "ref-product",
                    "content_base64": PNG_B64,
                    "media_type": "PNG",
                }
            ],
            "phase0_fields_not_in_brief": _PHASE0_NOT_IN_BRIEF,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == BRIEF_MAPPING_UNRESOLVED
    assert UNSUPPORTED_RESOLUTION in {issue["code"] for issue in response.json()["error"]["details"]["issues"]}
    assert list(JOB_STORE._jobs) == []  # noqa: SLF001
    fetched = _client().get(f"/api/v1/client-briefs/{created.json()['brief_id']}")
    assert fetched.json()["client_brief"] == before


def test_single_item_prepare_uses_brief_role_and_keeps_approval_gate() -> None:
    payload = _slice_payload()
    payload["role"] = "secondary"
    payload["brief"]["job"] = {"kind": "single_item", "singleItemRole": "secondary"}
    created = _client().post(
        "/api/v1/client-briefs",
        json={
            "owner_id": "owner-slice",
            "contract_id": "contract-single-1",
            "revision": 1,
            "client_brief": payload,
        },
    )
    assert created.status_code == 200, created.text
    response = _prepare(
        created.json()["brief_id"],
        {
            "reference_files": [
                {
                    "reference_id": "ref-product",
                    "content_base64": PNG_B64,
                    "media_type": "PNG",
                }
            ],
            "phase0_fields_not_in_brief": _PHASE0_NOT_IN_BRIEF,
        },
    )
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    assert join_scheduled_planning(job_id) is True
    job = _client().get(f"/api/v1/jobs/{job_id}").json()
    assert job["contract"]["intent"]["job_type"] == "Single item"
    assert job["contract"]["intent"]["job_option"] == "Secondary"
    assert job["contract"]["item"]["product_role"] == "hero"
    denied = _client().post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert denied.status_code == 409
    assert denied.json()["error"]["code"] == "PRE_GENERATION_APPROVAL_REQUIRED"


def _prepare_body() -> dict[str, Any]:
    return {
        "reference_files": [
            {
                "reference_id": "ref-product",
                "content_base64": PNG_B64,
                "media_type": "PNG",
            }
        ]
    }


def _persist_payload(payload: dict[str, Any], contract_id: str) -> dict[str, Any]:
    response = _client().post(
        "/api/v1/client-briefs",
        json={
            "owner_id": "owner-slice",
            "contract_id": contract_id,
            "revision": 1,
            "client_brief": payload,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _compile_of(job_id: str) -> dict[str, Any]:
    assert join_scheduled_planning(job_id) is True
    compile_res = _client().get(f"/api/v1/jobs/{job_id}/compile")
    assert compile_res.status_code == 200, compile_res.text
    return compile_res.json()["engine"]["compile"]


def _generate_fake(job_id: str) -> bytes:
    approved = _client().post(f"/api/v1/jobs/{job_id}/generate/approve", json={})
    assert approved.status_code == 200, approved.text
    generated = _client().post(f"/api/v1/jobs/{job_id}/generate", json={})
    assert generated.status_code == 200, generated.text
    image = _client().get(f"/api/v1/jobs/{job_id}/generate/image")
    assert image.status_code == 200
    return image.content


def test_close_up_portrait_4k_reaches_compile_and_fake_generation() -> None:
    payload = _slice_payload()
    payload["brief"]["items"][0]["requestedPackage"][0].update(
        {"views": ["close_up"], "proportion": "4:5", "resolution": "4k"}
    )
    payload["package"][0]["outputs"][0].update(
        {"views": ["close_up"], "proportion": "4:5", "resolution": "4k"}
    )
    created = _persist_payload(payload, "contract-close-4k")
    prepared = _prepare(created["brief_id"], _prepare_body())
    assert prepared.status_code == 200, prepared.text
    body = prepared.json()
    job_id = body["job_id"]
    assert body["executions"][0]["requested_view"] == "Close-up"
    assert body["executions"][0]["image_proportions"] == "Portrait · 4:5"
    assert body["executions"][0]["resolution"] == "4K"
    compiled = _compile_of(job_id)
    assert compiled["requested_view"] == "Close-up"
    assert compiled["output_format"] == {
        "image_proportions": "Portrait · 4:5",
        "resolution": "4K",
    }
    pixels = expected_pixels(
        EngineOutputFormat(image_proportions="Portrait · 4:5", resolution="4K")
    )
    measured = inspect_image(_generate_fake(job_id))
    assert (measured.width, measured.height) == pixels


def test_two_requested_views_create_two_jobs_not_the_first_only() -> None:
    payload = _slice_payload()
    payload["brief"]["items"][0]["requestedPackage"][0]["views"] = ["wide_view", "close_up"]
    payload["package"][0]["outputs"][0]["views"] = ["wide_view", "close_up"]
    created = _persist_payload(payload, "contract-two-views")
    prepared = _prepare(created["brief_id"], _prepare_body())
    assert prepared.status_code == 200, prepared.text
    body = prepared.json()
    assert body["job_ids"] == [row["job_id"] for row in body["executions"]]
    assert [row["requested_view"] for row in body["executions"]] == ["Wide view", "Close-up"]
    views = [_compile_of(job_id)["requested_view"] for job_id in body["job_ids"]]
    assert views == ["Wide view", "Close-up"]
    for job_id in body["job_ids"]:
        denied = _client().post(f"/api/v1/jobs/{job_id}/generate", json={})
        assert denied.json()["error"]["code"] == "PRE_GENERATION_APPROVAL_REQUIRED"
        _generate_fake(job_id)


def test_two_outputs_keep_separate_delivery() -> None:
    payload = _slice_payload()
    website = {
        "concept": "website",
        "views": ["close_up"],
        "proportion": "16:9",
        "resolution": "2k",
    }
    payload["brief"]["items"][0]["requestedPackage"].append(website)
    payload["package"][0]["outputs"].append(website)
    created = _persist_payload(payload, "contract-two-outputs")
    prepared = _prepare(created["brief_id"], _prepare_body())
    assert prepared.status_code == 200, prepared.text
    executions = prepared.json()["executions"]
    assert [
        (row["requested_outcomes"], row["requested_view"], row["image_proportions"], row["resolution"])
        for row in executions
    ] == [
        (["Lifestyle"], "Wide view", "Square · 1:1", "2K"),
        (["Website"], "Close-up", "Landscape · 16:9", "2K"),
    ]
    for job_id, expected_view, expected_format in (
        (executions[0]["job_id"], "Wide view", {"image_proportions": "Square · 1:1", "resolution": "2K"}),
        (executions[1]["job_id"], "Close-up", {"image_proportions": "Landscape · 16:9", "resolution": "2K"}),
    ):
        compiled = _compile_of(job_id)
        assert compiled["requested_view"] == expected_view
        assert compiled["output_format"] == expected_format
        _generate_fake(job_id)


def test_edit_and_batch_and_hero_reach_compile_and_fake_generate() -> None:
    cases = [
        ("contract-edit-new", {"kind": "edit", "editMode": "new_item"}, None, "Edit", "New item"),
        (
            "contract-edit-saved",
            {"kind": "edit", "editMode": "choose_from_saving", "savedItemId": "saving-lounge-chair"},
            None,
            "Edit",
            "Choose from saving",
        ),
        ("contract-batch-one", {"kind": "new_project", "newProjectMode": "batch"}, None, "New Project", "Batch"),
        ("contract-hero", {"kind": "single_item", "singleItemRole": "hero"}, "hero", "Single item", "Hero"),
    ]
    for contract_id, job, role, job_type, job_option in cases:
        payload = _slice_payload()
        payload["brief"]["job"] = job
        payload["role"] = role
        created = _persist_payload(payload, contract_id)
        prepared = _prepare(created["brief_id"], _prepare_body())
        assert prepared.status_code == 200, prepared.text
        job_id = prepared.json()["job_id"]
        compiled = _compile_of(job_id)
        assert compiled["requested_view"] == "Wide view"
        stored = _client().get(f"/api/v1/jobs/{job_id}").json()
        assert stored["contract"]["intent"]["job_type"] == job_type
        assert stored["contract"]["intent"]["job_option"] == job_option
        denied = _client().post(f"/api/v1/jobs/{job_id}/generate", json={})
        assert denied.json()["error"]["code"] == "PRE_GENERATION_APPROVAL_REQUIRED"
        _generate_fake(job_id)
