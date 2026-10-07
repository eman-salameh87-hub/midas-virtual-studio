"""Local/dev artifact store isolation. Not a Vault/database."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.contracts.job import Phase0JobContract
from app.runtime.artifacts import FilesystemArtifactStore, get_artifact_store
from app.runtime.jobs import create_job
from app.runtime.state import JOB_STORE
from tests.png_bytes import PNG_1X1, PNG_HASH


def test_artifact_store_rejects_path_escape(tmp_path: Path) -> None:
    store = FilesystemArtifactStore(tmp_path / "outputs")
    with pytest.raises(ValueError):
        store.save_input("../outside", "pixel.png", PNG_1X1)
    store.save_input("job-1", "../pixel.png", PNG_1X1)
    written = store.get_artifact("job-1", "input/pixel.png")
    assert written == PNG_1X1
    assert not (tmp_path / "pixel.png").exists()
    root = (tmp_path / "outputs").resolve()
    job_dir = store.job_dir("job-1")
    assert root in job_dir.parents


def _contract() -> Phase0JobContract:
    return Phase0JobContract.model_validate(
        {
            "contract_id": "contract-artifact-1",
            "revision": 1,
            "owner_id": "owner-artifacts",
            "intent": {
                "mode": "Manual",
                "job_type": "New Project",
                "job_option": "One by one (same department)",
                "requested_outcomes": ["Lifestyle"],
                "other_outcome": None,
                "requested_pieces": ["towel"],
                "excluded_pieces": [],
                "selected_count": {"status": "declared", "value": 1},
            },
            "item": {
                "department": "Accessories",
                "category": "Bathroom",
                "subcategory": "Towels",
                "product_role": "hero",
            },
            "source_condition": {"input_condition": "clean pack shot"},
            "references": [
                {
                    "reference_id": "ref-product",
                    "filename": "pixel.png",
                    "media_type": "PNG",
                    "hash_algorithm": "sha256",
                    "content_hash": PNG_HASH,
                    "role": "Product / vendor reference",
                }
            ],
            "outputs": {
                "views": ["Wide view"],
                "image_proportions": "Square · 1:1",
                "resolution": "2K",
                "package_members": ["lifestyle"],
            },
            "changes": {
                "policy_mode": "fidelity-locked",
                "allowed_changes": ["styled setting"],
                "protected_identity": ["towel identity"],
                "room_locks": [],
                "creative_variables": [],
            },
            "preferences": {
                "lighting": "Soft daylight",
                "wall": "White",
                "floor": "Light oak",
                "plants": False,
                "human": False,
                "mood": "Calm & natural",
            },
            "statements": [],
            "unknowns": [],
            "conflicts": [],
        }
    )


def test_job_artifacts_are_isolated_by_job_id() -> None:
    contract = _contract()
    first = create_job(JOB_STORE, contract, {"ref-product": PNG_1X1})
    second = create_job(JOB_STORE, contract, {"ref-product": PNG_1X1})
    artifacts = get_artifact_store()
    first_dir = artifacts.job_dir(first.job_id)
    second_dir = artifacts.job_dir(second.job_id)
    assert first_dir != second_dir
    assert first_dir.is_dir()
    assert second_dir.is_dir()
    first_job = json.loads((first_dir / "job.json").read_text(encoding="utf-8"))
    second_job = json.loads((second_dir / "job.json").read_text(encoding="utf-8"))
    assert first_job["job_id"] == first.job_id
    assert second_job["job_id"] == second.job_id
    assert first_job["job_id"] != second_job["job_id"]
    first_input = artifacts.get_artifact(first.job_id, "input/ref-product-pixel.png")
    assert first_input == PNG_1X1
    assert artifacts.get_artifact(second.job_id, "job.json")
    assert artifacts.get_output(first.job_id) is None
