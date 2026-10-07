import pytest
from pydantic import ValidationError

from app.contracts.critique import REQUIRED_DIMENSIONS, CritiqueAssessment


def _finding(
    dimension: str = "inventory",
    *,
    result: str = "pass",
    severity: str = "info",
) -> dict:
    return {
        "dimension": dimension,
        "severity": severity,
        "result": result,
        "observation": f"{dimension} observation",
        "expected": f"{dimension} expected",
        "evidence": ["original vs generated"],
        "repair_instruction": None,
    }


def _assessment(**updates: object) -> dict:
    payload = {
        "job_id": "job-1",
        "contract_id": "c-1",
        "contract_revision": 1,
        "engine_contract_id": "c-1",
        "engine_revision": 1,
        "generation_operation_key": "op-1",
        "generation_output_id": "gen-1",
        "status": "ready",
        "overall_result": "pass",
        "findings": [_finding(name) for name in REQUIRED_DIMENSIONS],
        "unknowns": [],
        "summary": "Candidate preserves locked identity and count.",
    }
    payload.update(updates)
    return payload


def test_valid_critique_assessment() -> None:
    assessment = CritiqueAssessment.model_validate(_assessment())
    assert assessment.status == "ready"
    assert assessment.overall_result == "pass"
    assert {item.dimension for item in assessment.findings} == set(REQUIRED_DIMENSIONS)


def test_invalid_critique_pass_cannot_override_identity() -> None:
    findings = [_finding(name) for name in REQUIRED_DIMENSIONS]
    findings[1] = _finding("identity", result="fail", severity="critical")
    with pytest.raises(ValidationError, match="cannot override"):
        CritiqueAssessment.model_validate(_assessment(findings=findings))


def test_invalid_critique_missing_ready_dimension() -> None:
    findings = [_finding(name) for name in REQUIRED_DIMENSIONS if name != "lighting"]
    with pytest.raises(ValidationError, match="lighting"):
        CritiqueAssessment.model_validate(_assessment(findings=findings))


def test_hold_overall_requires_hold_status() -> None:
    with pytest.raises(ValidationError, match="hold"):
        CritiqueAssessment.model_validate(_assessment(overall_result="hold"))


def test_repair_required_is_ready() -> None:
    findings = [_finding(name) for name in REQUIRED_DIMENSIONS]
    findings[2] = _finding(
        "geometry",
        result="fail",
        severity="high",
    )
    assessment = CritiqueAssessment.model_validate(
        _assessment(overall_result="repair_required", findings=findings)
    )
    assert assessment.status == "ready"
    assert assessment.overall_result == "repair_required"
