"""Repository helpers for risk treatment follow-up tasks."""

from __future__ import annotations

from typing import Iterable, List, Optional

from models.messages_kernel import RiskTreatmentTask, RiskTreatmentWorkflow, RiskTreatmentStatus

from .cosmos_repository import CosmosRepository

CONTAINER_NAME = "risk_treatments"
PARTITION_KEY = "/workflow"


class RiskTreatmentRepository(CosmosRepository[RiskTreatmentTask]):
    """CRUD helpers for risk treatment follow-up tasks."""

    def __init__(self) -> None:
        super().__init__(CONTAINER_NAME, RiskTreatmentTask, PARTITION_KEY)

    async def upsert_task(self, task: RiskTreatmentTask) -> RiskTreatmentTask:
        return await self.upsert(task)

    async def get_by_task_id(self, task_id: str, workflow: RiskTreatmentWorkflow | str) -> Optional[RiskTreatmentTask]:
        workflow_key = workflow.value if isinstance(workflow, RiskTreatmentWorkflow) else str(workflow)
        return await self.read(task_id, workflow_key)

    async def list_pending(
        self,
        *,
        workflow: Optional[RiskTreatmentWorkflow | str] = None,
        limit: int = 100,
    ) -> List[RiskTreatmentTask]:
        return await self.list_by_status(RiskTreatmentStatus.PENDING, workflow=workflow, limit=limit)

    async def list_by_status(
        self,
        status: RiskTreatmentStatus | str,
        *,
        workflow: Optional[RiskTreatmentWorkflow | str] = None,
        limit: int = 100,
    ) -> List[RiskTreatmentTask]:
        status_value = status.value if isinstance(status, RiskTreatmentStatus) else str(status)

        if workflow is None:
            results = await self.list_all(limit=limit)
            return [task for task in results if (task.status == status_value or task.status == status)]

        workflow_key = workflow.value if isinstance(workflow, RiskTreatmentWorkflow) else str(workflow)
        records = await self.list_partition(workflow_key, limit=limit)
        return [task for task in records if (task.status == status_value or task.status == status)]


__all__ = ["RiskTreatmentRepository"]
