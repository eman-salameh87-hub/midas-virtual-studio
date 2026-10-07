"""In-memory Eye run for one validated job contract.

Nothing is written to a database, queue, or file.
"""

from pydantic import BaseModel, ConfigDict

from app.contracts.eye import EyeInput, EyeObservation
from app.contracts.job import Phase0JobContract
from app.providers.eye import EyeProvider
from app.stages.eye import Readiness, build_eye_input, execute_eye


class InMemoryEyeJob(BaseModel):
    """The Eye result for this call. It is not stored."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_id: str
    revision: int
    eye_input: EyeInput
    observation: EyeObservation
    readiness: Readiness


def execute_eye_job(
    *,
    contract: Phase0JobContract,
    reference_ids: list[str],
    model_id: str,
    messages: list[str],
    provider: EyeProvider,
) -> InMemoryEyeJob:
    """Job contract → selected references → EyeInput → provider → readiness."""

    eye_input = build_eye_input(contract, reference_ids)
    observation, readiness = execute_eye(
        eye_input=eye_input,
        model_id=model_id,
        messages=messages,
        provider=provider,
    )
    return InMemoryEyeJob(
        contract_id=contract.contract_id,
        revision=contract.revision,
        eye_input=eye_input,
        observation=observation,
        readiness=readiness,
    )
