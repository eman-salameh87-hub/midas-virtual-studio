"""Local UIMidas ProposedJobContract persistence. Not an original Studio snapshot."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.contracts.client_brief import (
    ClientBriefRecord,
    ProposedJobContract,
    dump_omitting_optional_nones,
)
from app.main import app
from app.runtime.artifacts import get_artifact_store
from app.runtime.client_briefs import (
    BRIEF_HASH_MISMATCH,
    CLIENT_BRIEF_STORE,
    MALFORMED_BRIEF,
    ClientBriefAlreadyPersistedError,
    persist_client_brief,
    recover_client_briefs_from_artifacts,
)
from app.runtime.state import JOB_STORE

_PLACEHOLDERS = {
    "ownerIdentity": {
        "status": "development-placeholder",
        "value": None,
        "note": "Production owner identity is not available in this client.",
    },
    "fileIds": {
        "status": "development-placeholder",
        "value": None,
        "note": "Local files have no production file ids yet. Names stay on the brief evidence.",
    },
    "limits": {
        "status": "development-placeholder",
        "value": None,
        "note": "File and generation limits are not defined.",
    },
}


def _client() -> TestClient:
    return TestClient(app)


def _minimal_uimidas_payload() -> dict[str, Any]:
    """Minimum valid Manual submit from UIMidas empty-draft defaults + single item hero.

    Derived from createEmptyDraft, ScopeSection delivery defaults, and
    submissionAudit.test.ts 'visible View & delivery defaults'.
    """

    return {
        "endpoint": "POST /api/studio/v2/jobs",
        "contractVersion": "studio-jobs-v2-draft",
        "idempotencyKey": "audit-key",
        **_PLACEHOLDERS,
        "category": None,
        "role": "hero",
        "package": [
            {
                "itemId": "item-1",
                "productGroupId": "group-1",
                "outputs": [
                    {
                        "concept": "lifestyle",
                        "views": ["category_template"],
                        "proportion": "standard_for_category",
                        "resolution": "standard_for_category",
                    }
                ],
            }
        ],
        "brief": {
            "job": {"kind": "single_item", "singleItemRole": "hero"},
            "items": [
                {
                    "id": "item-1",
                    "productGroupId": "group-1",
                    "categoryState": "automatic_unknown",
                    "references": [],
                    "requestedPackage": [
                        {
                            "concept": "lifestyle",
                            "views": ["category_template"],
                            "proportion": "standard_for_category",
                            "resolution": "standard_for_category",
                        }
                    ],
                }
            ],
            "suggestions": {"mood": "automatic"},
        },
    }


def _populated_uimidas_payload() -> dict[str, Any]:
    """Populated envelope matching UIMidas/src/submissionAudit.test.ts readyDraft submit."""

    lifestyle = {
        "concept": "lifestyle",
        "views": ["close_up"],
        "proportion": "4:5",
        "resolution": "4k",
    }
    variations = {
        "concept": "variations",
        "views": ["close_up"],
        "proportion": "4:5",
        "resolution": "4k",
        "variationCount": 3,
    }
    others = {
        "concept": "others",
        "otherLabel": "A styled corner",
        "views": ["close_up"],
        "proportion": "4:5",
        "resolution": "4k",
    }
    white = {
        "concept": "white_bk",
        "views": ["category_template"],
        "proportion": "standard_for_category",
        "resolution": "standard_for_category",
    }
    website = {
        "concept": "website",
        "views": ["category_template"],
        "proportion": "standard_for_category",
        "resolution": "standard_for_category",
    }
    new_composition = {
        "concept": "new_composition",
        "views": ["category_template"],
        "proportion": "standard_for_category",
        "resolution": "standard_for_category",
    }
    create_with = {
        "concept": "create_with_this_item",
        "views": ["category_template"],
        "proportion": "standard_for_category",
        "resolution": "standard_for_category",
    }
    outputs = [white, lifestyle, website, new_composition, variations, create_with, others]
    return {
        "endpoint": "POST /api/studio/v2/jobs",
        "contractVersion": "studio-jobs-v2-draft",
        "idempotencyKey": "audit-key",
        **_PLACEHOLDERS,
        "category": "home-furniture/living-rooms",
        "role": None,
        "package": [
            {
                "itemId": "item-1",
                "productGroupId": "group-1",
                "outputs": outputs,
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
                                "fileName": "sofa.jpg",
                                "mediaKind": "image",
                                "sizeBytes": 2048,
                                "libraryKey": None,
                            },
                        },
                        {
                            "id": "ref-midas",
                            "type": "midas",
                            "source": "midas_library",
                            "role": "midas_reference",
                            "relationship": "supporting_context",
                            "productGroupId": None,
                            "evidence": {
                                "fileName": "Studio white sweep",
                                "mediaKind": "image",
                                "sizeBytes": None,
                                "libraryKey": "midas-white-sweep",
                            },
                        },
                    ],
                    "requestedPackage": outputs,
                    "metadata": {
                        "sku": "SOFA-1",
                        "itemCount": 2,
                        "fabricMaterial": "linen",
                    },
                }
            ],
            "preferences": {
                "lighting": "soft_daylight",
                "wall": "ivory",
                "floor": "light_oak",
            },
            "suggestions": {
                "plants": "suggest",
                "human": "suggest",
                "mood": "warm_inviting",
            },
            "notes": {
                "fidelity": "keep the weave",
                "customPrompting": "warmer",
            },
        },
    }


def _create_body(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "owner_id": "owner-1",
        "contract_id": "contract-brief-1",
        "revision": 1,
        "client_brief": payload if payload is not None else _minimal_uimidas_payload(),
    }


def _post(body: dict[str, Any] | None = None):
    return _client().post("/api/v1/client-briefs", json=body or _create_body())


def test_uimidas_payload_round_trips_through_api_and_disk() -> None:
    payload = _populated_uimidas_payload()
    response = _post(_create_body(payload))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["client_brief"] == payload
    assert "blob:" not in json.dumps(body)
    assert "variationAspects" not in json.dumps(body)
    assert JOB_STORE.get(body["brief_id"]) is None

    fetched = _client().get(f"/api/v1/client-briefs/{body['brief_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["client_brief"] == payload

    raw = json.loads(
        get_artifact_store()
        .get_artifact(body["brief_id"], "client_brief.json")
        .decode("utf-8")
    )
    assert raw["client_brief"] == payload
    assert (get_artifact_store().job_dir(body["brief_id"]) / "job.json").is_file() is False


def test_omitted_optional_fields_stay_omitted() -> None:
    payload = _minimal_uimidas_payload()
    response = _post(_create_body(payload))
    assert response.status_code == 200, response.text
    stored = response.json()["client_brief"]
    assert stored == payload
    item = stored["brief"]["items"][0]
    assert "department" not in item
    assert "category" not in item
    assert "subcategory" not in item
    assert "metadata" not in item
    assert "preferences" not in stored["brief"]
    assert "notes" not in stored["brief"]
    assert "otherLabel" not in item["requestedPackage"][0]
    assert "variationCount" not in item["requestedPackage"][0]
    assert stored["category"] is None
    assert stored["role"] == "hero"
    assert stored["brief"]["suggestions"] == {"mood": "automatic"}


def test_workflow_defaults_omit_concrete_room_choices() -> None:
    payload = _minimal_uimidas_payload()
    payload["brief"]["preferences"] = {"useWorkflowDefaults": True}
    response = _post(_create_body(payload))
    assert response.status_code == 200, response.text
    assert response.json()["client_brief"]["brief"]["preferences"] == {
        "useWorkflowDefaults": True
    }


def test_identical_input_has_stable_hash() -> None:
    first = _post()
    second = _post()
    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["brief_hash"] == second.json()["brief_hash"]
    assert first.json()["brief_id"] != second.json()["brief_id"]


def test_hash_changes_when_a_brief_field_changes() -> None:
    baseline = _post().json()["brief_hash"]
    changed = _minimal_uimidas_payload()
    changed["brief"]["suggestions"] = {"mood": "calm_natural"}
    response = _post(_create_body(changed))
    assert response.status_code == 200, response.text
    assert response.json()["brief_hash"] != baseline


def test_unknown_keys_are_rejected_on_typed_objects() -> None:
    extra = _minimal_uimidas_payload()
    extra["inventedField"] = True
    assert _post(_create_body(extra)).status_code == 422

    extra_brief = _minimal_uimidas_payload()
    extra_brief["brief"]["inventedBrief"] = 1
    assert _post(_create_body(extra_brief)).status_code == 422

    extra_ref = _populated_uimidas_payload()
    extra_ref["brief"]["items"][0]["references"][0]["localPreviewUrl"] = "blob:http://local/x"
    assert _post(_create_body(extra_ref)).status_code == 422

    extra_output = _minimal_uimidas_payload()
    extra_output["brief"]["items"][0]["requestedPackage"][0]["variationAspects"] = [
        "lighting"
    ]
    assert _post(_create_body(extra_output)).status_code == 422


def test_reconstructed_display_string_snapshot_is_rejected() -> None:
    reconstructed = {
        "version": "Client first-page design · 2",
        "execution": "preview",
        "mode": "Manual",
        "job": {"type": "New Project", "option": "One by one (same department)"},
    }
    response = _post(_create_body(reconstructed))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "UNSUPPORTED_BRIEF_SCHEMA"
    assert "client_brief" not in json.dumps(error["details"])
    assert "preview" not in json.dumps(error["details"])


def test_projects_submit_shape_is_rejected() -> None:
    projects = {
        "idempotencyKey": "audit-key",
        "categoryState": "automatic_unknown",
        "productGroupId": "group-1",
        "references": [],
        "outputs": [{"concept": "lifestyle"}],
    }
    response = _post(_create_body(projects))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "PROJECTS_NOT_SUPPORTED"
    assert "group-1" not in json.dumps(error["details"])


def test_use_workflow_defaults_false_is_rejected() -> None:
    payload = _minimal_uimidas_payload()
    payload["brief"]["preferences"] = {"useWorkflowDefaults": False}
    assert _post(_create_body(payload)).status_code == 422


def test_caller_brief_hash_is_ignored() -> None:
    body = _create_body()
    body["brief_hash"] = "0" * 64
    response = _post(body)
    assert response.status_code == 200, response.text
    assert response.json()["brief_hash"] != "0" * 64


def test_revision_is_immutable_and_previous_record_is_not_mutated() -> None:
    contract = ProposedJobContract.model_validate(_minimal_uimidas_payload())
    original = ClientBriefRecord.model_validate(
        {
            "brief_id": "brief-1",
            "owner_id": "owner-1",
            "contract_id": "contract-brief-1",
            "revision": 1,
            "client_brief": dump_omitting_optional_nones(contract),
        }
    )
    updated_payload = dump_omitting_optional_nones(contract)
    updated_payload["brief"]["items"][0]["metadata"] = {"sku": "SOFA-9"}
    revised_contract = ProposedJobContract.model_validate(updated_payload)
    revised = original.revise(client_brief=revised_contract)

    assert original.revision == 1
    assert original.client_brief.brief.items[0].metadata is None
    assert original.brief_hash != revised.brief_hash
    assert revised.revision == 2
    assert revised.contract_id == original.contract_id
    assert revised.brief_id != original.brief_id
    assert revised.client_brief.brief.items[0].metadata is not None
    assert revised.client_brief.brief.items[0].metadata.sku == "SOFA-9"

    with pytest.raises(ValidationError):
        original.revision = 2  # type: ignore[misc]
    with pytest.raises(ValueError, match="new brief_id"):
        original.revise(revision=9)


def test_brief_post_does_not_create_a_job_or_schedule_planning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[object] = []

    def _should_not_run(*_args: object, **_kwargs: object) -> None:
        called.append(True)

    monkeypatch.setattr("app.api.jobs.schedule_planning", _should_not_run)
    assert _post().status_code == 200
    assert called == []
    assert list(JOB_STORE._jobs) == []  # noqa: SLF001


def test_persisted_brief_survives_recovery() -> None:
    created = _post().json()
    CLIENT_BRIEF_STORE.clear()
    assert CLIENT_BRIEF_STORE.get(created["brief_id"]) is None
    recovered = recover_client_briefs_from_artifacts(CLIENT_BRIEF_STORE)
    assert created["brief_id"] in recovered.recovered
    assert recovered.errors == []
    stored = CLIENT_BRIEF_STORE.get(created["brief_id"])
    assert stored is not None
    assert stored.brief_hash == created["brief_hash"]
    assert dump_omitting_optional_nones(stored.client_brief) == created["client_brief"]


def test_brief_only_directory_is_not_recovered_as_a_job() -> None:
    from app.runtime.recovery import recover_jobs_from_artifacts

    created = _post().json()
    JOB_STORE.clear()
    recovered_jobs = recover_jobs_from_artifacts(JOB_STORE)
    assert created["brief_id"] not in recovered_jobs
    assert JOB_STORE.get(created["brief_id"]) is None


def test_owner_and_revision_checks_on_get() -> None:
    created = _post().json()
    brief_id = created["brief_id"]
    client = _client()
    assert (
        client.get(f"/api/v1/client-briefs/{brief_id}", params={"owner_id": "other"}).status_code
        == 403
    )
    assert (
        client.get(f"/api/v1/client-briefs/{brief_id}", params={"revision": 9}).status_code
        == 409
    )
    assert client.get("/api/v1/client-briefs/missing").status_code == 404


def test_copy_independence_for_hash_mutations() -> None:
    first = _minimal_uimidas_payload()
    second = copy.deepcopy(first)
    second["brief"]["notes"] = {"customPrompting": "warmer"}
    assert _post(_create_body(first)).json()["brief_hash"] != _post(
        _create_body(second)
    ).json()["brief_hash"]


def test_lifespan_recovers_brief_from_outputs_dir() -> None:
    created = _post().json()
    brief_id = created["brief_id"]
    CLIENT_BRIEF_STORE.clear()
    JOB_STORE.clear()
    assert CLIENT_BRIEF_STORE.get(brief_id) is None
    with TestClient(app) as restarted:
        res = restarted.get(f"/api/v1/client-briefs/{brief_id}")
        assert res.status_code == 200
        assert res.json()["client_brief"] == created["client_brief"]
        assert res.json()["brief_hash"] == created["brief_hash"]


def test_malformed_persisted_brief_is_reported_and_valid_records_remain() -> None:
    created = _post().json()
    artifacts = get_artifact_store()
    artifacts._write_bytes(
        artifacts._resolve("broken-brief", "client_brief.json"),
        b"{not-json",
    )
    CLIENT_BRIEF_STORE.clear()
    result = recover_client_briefs_from_artifacts(CLIENT_BRIEF_STORE)
    assert created["brief_id"] in result.recovered
    assert CLIENT_BRIEF_STORE.get(created["brief_id"]) is not None
    assert CLIENT_BRIEF_STORE.get("broken-brief") is None
    errors = [error for error in result.errors if error.brief_id == "broken-brief"]
    assert len(errors) == 1
    assert errors[0].code == MALFORMED_BRIEF
    encoded = json.dumps(errors[0].model_dump(mode="json"))
    assert "{not-json" not in encoded
    assert _client().get("/api/v1/client-briefs/broken-brief").status_code == 404


def test_hash_mismatched_persisted_brief_is_reported() -> None:
    created = _post().json()
    artifacts = get_artifact_store()
    raw = json.loads(
        artifacts.get_artifact(created["brief_id"], "client_brief.json").decode("utf-8")
    )
    raw["brief_hash"] = "0" * 64
    artifacts._write_json(created["brief_id"], "client_brief.json", raw)
    CLIENT_BRIEF_STORE.clear()
    result = recover_client_briefs_from_artifacts(CLIENT_BRIEF_STORE)
    assert created["brief_id"] not in result.recovered
    assert CLIENT_BRIEF_STORE.get(created["brief_id"]) is None
    assert len(result.errors) == 1
    assert result.errors[0].brief_id == created["brief_id"]
    assert result.errors[0].code == BRIEF_HASH_MISMATCH
    encoded = json.dumps(result.errors[0].model_dump(mode="json"))
    assert "0" * 64 not in encoded
    assert created["brief_hash"] not in encoded
    assert _client().get(f"/api/v1/client-briefs/{created['brief_id']}").status_code == 404


def test_persisted_brief_file_is_immutable() -> None:
    created = _post().json()
    record = CLIENT_BRIEF_STORE.get(created["brief_id"])
    assert record is not None
    with pytest.raises(ClientBriefAlreadyPersistedError):
        persist_client_brief(record)


def test_lifespan_reports_malformed_brief_without_hiding_valid_ones() -> None:
    created = _post().json()
    artifacts = get_artifact_store()
    artifacts._write_bytes(
        artifacts._resolve("broken-lifespan", "client_brief.json"),
        b"{not-json",
    )
    CLIENT_BRIEF_STORE.clear()
    JOB_STORE.clear()
    with TestClient(app) as restarted:
        ok = restarted.get(f"/api/v1/client-briefs/{created['brief_id']}")
        assert ok.status_code == 200
        missing = restarted.get("/api/v1/client-briefs/broken-lifespan")
        assert missing.status_code == 404
    recovery = CLIENT_BRIEF_STORE.last_recovery
    assert recovery is not None
    assert created["brief_id"] in recovery.recovered
    assert any(
        error.brief_id == "broken-lifespan" and error.code == MALFORMED_BRIEF
        for error in recovery.errors
    )
