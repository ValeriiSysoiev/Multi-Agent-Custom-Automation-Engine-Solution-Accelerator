"""Repository helpers for ticket linkage records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional

from models.messages_kernel import TicketRecord

from .cosmos_repository import CosmosRepository

TICKET_CONTAINER = "tickets"
PARTITION_KEY = "/remediation_unit_id"


class TicketRepository(CosmosRepository[TicketRecord]):
    def __init__(self) -> None:
        super().__init__(TICKET_CONTAINER, TicketRecord, PARTITION_KEY)

    async def upsert_ticket(self, record: TicketRecord) -> TicketRecord:
        return await self.upsert(record)

    async def list_for_unit(self, remediation_unit_id: str, limit: int = 20) -> List[TicketRecord]:
        return await self.list_partition(remediation_unit_id, limit=limit)

    async def get_ticket(self, ticket_id: str, remediation_unit_id: str) -> Optional[TicketRecord]:
        return await self.read(ticket_id, remediation_unit_id)

    async def list_pending_verification(self, limit: int = 50) -> List[TicketRecord]:
        query = "SELECT * FROM c WHERE c.status=@resolved"
        results = await self.query(query, parameters=[{"name": "@resolved", "value": "resolved"}])
        return results[:limit]

    async def list_by_status(
        self,
        statuses: Iterable[str],
        limit: int = 50,
    ) -> List[TicketRecord]:
        query = "SELECT * FROM c WHERE ARRAY_CONTAINS(@statuses, c.status) ORDER BY c.due_at"
        parameters = [{"name": "@statuses", "value": list(statuses)}]
        results = await self.query(query, parameters=parameters)
        return results[:limit]

    async def count_ack_overdue(self, *, now: datetime, statuses: Iterable[str]) -> int:
        query = (
            "SELECT VALUE COUNT(1) FROM c WHERE ARRAY_CONTAINS(@statuses, c.status) "
            "AND IS_DEFINED(c.ack_due) AND c.ack_due != null AND c.ack_due <= @now"
        )
        return await self._count(query, statuses, extra_params={"@now": now})

    async def count_ack_between(
        self,
        *,
        start: datetime,
        end: datetime,
        statuses: Iterable[str],
    ) -> int:
        query = (
            "SELECT VALUE COUNT(1) FROM c WHERE ARRAY_CONTAINS(@statuses, c.status) "
            "AND IS_DEFINED(c.ack_due) AND c.ack_due != null "
            "AND c.ack_due > @start AND c.ack_due <= @end"
        )
        return await self._count(
            query,
            statuses,
            extra_params={"@start": start, "@end": end},
        )

    async def count_ack_missing(self, *, statuses: Iterable[str]) -> int:
        query = (
            "SELECT VALUE COUNT(1) FROM c WHERE ARRAY_CONTAINS(@statuses, c.status) "
            "AND (NOT IS_DEFINED(c.ack_due) OR c.ack_due = null)"
        )
        return await self._count(query, statuses)

    async def count_verify_overdue(self, *, now: datetime, statuses: Iterable[str]) -> int:
        query = (
            "SELECT VALUE COUNT(1) FROM c WHERE ARRAY_CONTAINS(@statuses, c.status) "
            "AND IS_DEFINED(c.verify_due) AND c.verify_due != null AND c.verify_due <= @now"
        )
        return await self._count(query, statuses, extra_params={"@now": now})

    async def count_verify_between(
        self,
        *,
        start: datetime,
        end: datetime,
        statuses: Iterable[str],
    ) -> int:
        query = (
            "SELECT VALUE COUNT(1) FROM c WHERE ARRAY_CONTAINS(@statuses, c.status) "
            "AND IS_DEFINED(c.verify_due) AND c.verify_due != null "
            "AND c.verify_due > @start AND c.verify_due <= @end"
        )
        return await self._count(
            query,
            statuses,
            extra_params={"@start": start, "@end": end},
        )

    async def count_verify_missing(self, *, statuses: Iterable[str]) -> int:
        query = (
            "SELECT VALUE COUNT(1) FROM c WHERE ARRAY_CONTAINS(@statuses, c.status) "
            "AND (NOT IS_DEFINED(c.verify_due) OR c.verify_due = null)"
        )
        return await self._count(query, statuses)

    async def _count(
        self,
        query: str,
        statuses: Iterable[str],
        *,
        extra_params: Optional[dict[str, datetime]] = None,
    ) -> int:
        parameters = [{"name": "@statuses", "value": list(statuses)}]
        if extra_params:
            for name, value in extra_params.items():
                dt = value
                if isinstance(dt, datetime) and dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if isinstance(dt, datetime):
                    parameters.append({"name": name, "value": dt.isoformat()})
                else:
                    parameters.append({"name": name, "value": dt})

        iterator = self._container.query_items(
            query=query,
            parameters=parameters,
            enable_cross_partition_query=True,
        )
        async for item in iterator:
            return int(item)
        return 0
