"""Local Eye execution boundary.

Builds an EyeInput from a Phase-0 job contract and passes it to a
caller-supplied provider. This module does not write a prompt, choose a
model, or call OpenRouter.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.contracts.eye import EyeContract, EyeInput, EyeObservation, EyeSource
from app.contracts.job import Phase0JobContract
from app.providers.eye import EyeProvider, EyeProviderRequest

ReadinessStatus = Literal["ready", "hold"]
ReadinessReason = Literal[
    "critical identity ambiguity",
    "unresolved identity",
    "conflicting critical evidence",
]

_REASON_ORDER: tuple[ReadinessReason, ...] = (
    "critical identity ambiguity",
    "unresolved identity",
    "conflicting critical evidence",
)


class Readiness(BaseModel):
    """Local hold-or-ready result. No other statuses are defined here."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ReadinessStatus
    reasons: list[ReadinessReason]

    @model_validator(mode="after")
    def status_matches_reasons(self) -> "Readiness":
        if self.status == "ready" and self.reasons:
            raise ValueError("ready must not include hold reasons")
        if self.status == "hold" and not self.reasons:
            raise ValueError("hold must name a reason")
        return self


def build_eye_input(
    contract: Phase0JobContract,
    reference_ids: list[str],
) -> EyeInput:
    """Copy selected Phase-0 references into an EyeInput.

    Phase-0 roles are the create-page vocabulary, so role_vocabulary is
    create-page. Atlas-handoff roles are not stored on the job contract and
    are not invented here.
    """

    if not reference_ids:
        raise ValueError("at least one reference must be selected")
    if len(reference_ids) != len(set(reference_ids)):
        raise ValueError("a reference may be selected only once")
    by_id = {reference.reference_id: reference for reference in contract.references}
    selected: list[EyeSource] = []
    for reference_id in reference_ids:
        reference = by_id.get(reference_id)
        if reference is None:
            raise ValueError(
                f"selected reference {reference_id!r} is not on the job contract"
            )
        selected.append(
            EyeSource(
                reference_id=reference.reference_id,
                filename=reference.filename,
                media_type=reference.media_type,
                hash_algorithm=reference.hash_algorithm,
                content_hash=reference.content_hash,
                role_vocabulary="create-page",
                role=reference.role,
            )
        )
    return EyeInput(
        contract_id=contract.contract_id,
        revision=contract.revision,
        references=selected,
    )


def evaluate_readiness(observation: EyeObservation) -> Readiness:
    """Hold only for critical identity ambiguity, unresolved identity, or conflicting critical evidence.

    Identity is the word "identity" in an ambiguity or conflict subject.
    Unresolved identity is an item whose observed count is unresolved.
    A colour conflict or a non-identity ambiguity does not hold the job.
    """

    found: set[ReadinessReason] = set()
    for ambiguity in observation.ambiguities:
        if ambiguity.status == "unresolved" and _subject_is_identity(ambiguity.subject):
            found.add("critical identity ambiguity")
    for item in observation.items:
        if item.count.status == "unresolved":
            found.add("unresolved identity")
    for conflict in observation.conflicts:
        if _subject_is_identity(conflict.subject):
            found.add("conflicting critical evidence")
    reasons = [reason for reason in _REASON_ORDER if reason in found]
    if reasons:
        return Readiness(status="hold", reasons=reasons)
    return Readiness(status="ready", reasons=[])


def execute_eye(
    *,
    eye_input: EyeInput,
    model_id: str,
    messages: list[str],
    provider: EyeProvider,
) -> tuple[EyeObservation, Readiness]:
    """Pass the caller-supplied model id and messages to the provider.

    The returned observation is checked against this EyeInput. The model id
    is not changed and is not written onto the Eye contract.
    """

    if not model_id.strip():
        raise ValueError("model_id must be supplied by the caller")
    request = EyeProviderRequest(
        model_id=model_id,
        eye_input=eye_input,
        messages=list(messages),
    )
    observation = provider.observe(request)
    EyeContract(eye_input=eye_input, observation=observation)
    return observation, evaluate_readiness(observation)


def _subject_is_identity(subject: str) -> bool:
    return "identity" in subject.casefold().split()
