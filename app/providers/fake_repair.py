"""Deterministic repair planner. Does not call a network or invent defects."""

from app.contracts.repair import RepairAction, RepairPlan
from app.providers.repair import RepairPlannerRequest
from app.stages.repair import build_repair_plan


class FakeRepairPlanner:
    """In-memory planner. `requests` records planning attempts only."""

    def __init__(self, *, action: RepairAction | None = None) -> None:
        self.action = action
        self.requests: list[RepairPlannerRequest] = []

    def plan(self, request: RepairPlannerRequest) -> RepairPlan:
        self.requests.append(request)
        if request.original_bytes is None or not request.original_bytes:
            raise ValueError("repair planning requires the original identity reference")
        if request.generated_bytes is None or not request.generated_bytes:
            raise ValueError("repair planning requires the current generated candidate")
        return build_repair_plan(request, action=self.action)
