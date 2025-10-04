"""Repository helpers for run/telemetry events."""

from __future__ import annotations

from typing import List

from models.messages_kernel import RunEventRecord

from .cosmos_repository import CosmosRepository

RUN_EVENTS_CONTAINER = "runs_events"
PARTITION_KEY = "/agent_name"


class RunEventRepository(CosmosRepository[RunEventRecord]):
    def __init__(self) -> None:
        super().__init__(RUN_EVENTS_CONTAINER, RunEventRecord, PARTITION_KEY)

    async def upsert_event(self, record: RunEventRecord) -> RunEventRecord:
        return await self.upsert(record)

    async def list_agent_events(self, agent_name: str, limit: int = 100) -> List[RunEventRecord]:
        return await self.list_partition(agent_name, limit=limit)

    async def list_recent_events(
        self,
        agent_name: str,
        *,
        limit: int = 20,
    ) -> List[RunEventRecord]:
        """Return the most recent events for an agent ordered by timestamp desc."""

        query = (
            "SELECT * FROM c WHERE c." + self._partition_key_field + "=@pk "
            "ORDER BY c.timestamp DESC"
        )
        params = [{"name": "@pk", "value": agent_name}]
        results = await self.query(query, params)
        return results[:limit]
