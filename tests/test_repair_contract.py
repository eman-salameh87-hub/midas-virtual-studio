import pytest
from pydantic import ValidationError

from app.contracts.repair import REPAIR_LIMIT, RepairLineage, RepairPlan


def _lineage(**overrides):
    payload = {
        "source_generation_output_id": "gen-1",
        "source_generation_operation_key": "op-1",
        "source_critique_generation_output_id": "gen-1",
        "original_reference_id": "ref-towel",
        "version_from": 1,
        "version_to": None,
        "result_generation_output_id": None,
        "result_generation_operation_key": None,
    }
    payload.update(overrides)
    return payload


def _plan(**overrides):
    payload = {
        "job_id": "job-1",
        "contract_id": "contract-1",
        "contract_revision": 1,
        "critique_generation_output_id": "gen-1",
        "critique_generation_operation_key": "op-1",
        "source_generation_output_id": "gen-1",
        "source_generation_operation_key": "op-1",
        "original_reference_id": "ref-towel",
        "repair_count": 1,
        "repair_limit": 2,
        "target_regions": ["geometry"],
        "repair_instructions": ["restore headboard proportions"],
        "preserve_list": ["inventory", "identity"],
        "previous_defects": ["geometry: headboard too wide"],
        "required_resolution_checks": ["geometry: match source construction"],
        "action": "fresh_render",
        "model_id": "caller-supplied-model",
        "status": "planned",
        "hold_reasons": [],
        "lineage": _lineage(),
        "operation": None,
        "receipt": None,
    }
    payload.update(overrides)
    return payload


def test_repair_limit_is_two() -> None:
    assert REPAIR_LIMIT == 2
    plan = RepairPlan.model_validate(_plan())
    assert plan.repair_limit == 2
    assert plan.repair_count == 1


def test_repair_count_three_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RepairPlan.model_validate(_plan(repair_count=3))


def test_hold_requires_reason() -> None:
    with pytest.raises(ValidationError):
        RepairPlan.model_validate(_plan(action="hold", repair_count=2, hold_reasons=[]))


def test_lineage_cannot_reuse_source_output() -> None:
    with pytest.raises(ValidationError):
        RepairLineage.model_validate(
            _lineage(version_to=2, result_generation_output_id="gen-1")
        )


def test_dispatched_repair_needs_targets() -> None:
    with pytest.raises(ValidationError):
        RepairPlan.model_validate(_plan(target_regions=[], repair_instructions=[]))
