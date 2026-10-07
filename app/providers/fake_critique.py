"""Deterministic Critique provider for local tests.

It does not call a network and does not invent a generated image.
"""

from app.contracts.critique import (
    REQUIRED_DIMENSIONS,
    CritiqueAssessment,
    CritiqueFinding,
    CritiqueUnknown,
)
from app.providers.critique import CritiqueInput, CritiqueProviderRequest


class FakeCritiqueProvider:
    """In-memory provider. `requests` records exactly what the caller passed."""

    def __init__(
        self,
        violation: str | None = None,
        *,
        violations: list[str | None] | None = None,
    ) -> None:
        self.violation = violation
        self.violations = list(violations) if violations is not None else None
        self._index = 0
        self.requests: list[CritiqueProviderRequest] = []

    def assess(self, request: CritiqueProviderRequest) -> CritiqueAssessment:
        self.requests.append(request)
        violation = self.violation
        if self.violations is not None:
            if self._index < len(self.violations):
                violation = self.violations[self._index]
                self._index += 1
            else:
                violation = self.violations[-1] if self.violations else None
        return assessment_for(request.critique_input, violation=violation)


def assessment_for(
    critique_input: CritiqueInput,
    *,
    violation: str | None = None,
) -> CritiqueAssessment:
    """Build one CritiqueAssessment bound to this CritiqueInput."""

    receipt = critique_input.receipt
    assert receipt.output is not None
    findings = [
        CritiqueFinding(
            dimension=dimension,
            severity="info",
            result="pass",
            observation=f"{dimension} matches the locked contract on the generated candidate",
            expected=f"preserve {dimension} from the original reference and Brain locks",
            evidence=[
                f"original={critique_input.original_reference_id}",
                f"generated={critique_input.generated_output_id}",
            ],
            repair_instruction=None,
        )
        for dimension in REQUIRED_DIMENSIONS
    ]
    unknowns: list[CritiqueUnknown] = [
        CritiqueUnknown(subject=item.subject, detail=item.detail)
        for item in critique_input.compile.unknowns
    ]
    status = "ready"
    overall = "pass"
    summary = "Generated candidate preserves inventory, identity, and construction."

    if violation == "hold":
        status = "hold"
        overall = "hold"
        findings[0] = findings[0].model_copy(
            update={
                "result": "uncertain",
                "severity": "medium",
                "observation": "count cannot be confirmed from the generated candidate",
            }
        )
        unknowns.append(
            CritiqueUnknown(
                subject="inventory",
                detail="generated framing does not make count independently countable",
            )
        )
        summary = "Critique holds because inventory is uncertain."
    elif violation == "repair_required":
        overall = "repair_required"
        findings[2] = findings[2].model_copy(
            update={
                "result": "fail",
                "severity": "high",
                "observation": "visible construction does not match the source-supported lock",
                "repair_instruction": "restore source-supported construction from the original",
            }
        )
        summary = "Geometry/construction failed; repair is required."
    elif violation == "regression":
        overall = "repair_required"
        findings[0] = findings[0].model_copy(
            update={
                "result": "fail",
                "severity": "critical",
                "observation": "inventory/count regressed after repair",
                "repair_instruction": "restore the locked product count from the original",
            }
        )
        summary = "A new inventory regression appeared after repair."
    elif violation == "pass_with_lock_fail":
        findings[1] = findings[1].model_copy(
            update={
                "result": "fail",
                "severity": "critical",
                "observation": "identity changed",
            }
        )
    elif violation == "missing_dimension":
        findings = findings[1:]
    elif violation == "wrong_job":
        return CritiqueAssessment(
            job_id="other-job",
            contract_id=critique_input.contract_id,
            contract_revision=critique_input.revision,
            engine_contract_id=critique_input.compile.contract_id,
            engine_revision=critique_input.compile.contract_revision,
            generation_operation_key=critique_input.operation.operation_key,
            generation_output_id=receipt.output.output_id,
            status="ready",
            overall_result="pass",
            findings=findings,
            unknowns=unknowns,
            summary=summary,
        )

    return CritiqueAssessment(
        job_id=critique_input.job_id,
        contract_id=critique_input.contract_id,
        contract_revision=critique_input.revision,
        engine_contract_id=critique_input.compile.contract_id,
        engine_revision=critique_input.compile.contract_revision,
        generation_operation_key=critique_input.operation.operation_key,
        generation_output_id=receipt.output.output_id,
        status=status,
        overall_result=overall,
        findings=findings,
        unknowns=unknowns,
        summary=summary,
    )
