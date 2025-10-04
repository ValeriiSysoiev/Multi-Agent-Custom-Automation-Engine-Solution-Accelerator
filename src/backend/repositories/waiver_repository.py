"""Repository helpers for waiver records."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

from models.messages_kernel import WaiverRecord, WaiverStatus

from .cosmos_repository import CosmosRepository

WAIVER_CONTAINER = "waivers"
PARTITION_KEY = "/remediation_unit_id"


class WaiverRepository(CosmosRepository[WaiverRecord]):
    def __init__(self) -> None:
        super().__init__(WAIVER_CONTAINER, WaiverRecord, PARTITION_KEY)

    async def upsert_waiver(self, record: WaiverRecord) -> WaiverRecord:
        return await self.upsert(record)

    async def list_for_unit(self, remediation_unit_id: str, limit: int = 20) -> List[WaiverRecord]:
        return await self.list_partition(remediation_unit_id, limit=limit)

    async def get_latest(self, remediation_unit_id: str) -> Optional[WaiverRecord]:
        query = (
            "SELECT TOP 1 * FROM c WHERE c.remediation_unit_id=@ru ORDER BY c.timestamp DESC"
        )
        results = await self.query(query, parameters=[{"name": "@ru", "value": remediation_unit_id}])
        return results[0] if results else None

    async def get_by_id(self, waiver_id: str) -> Optional[WaiverRecord]:
        query = "SELECT * FROM c WHERE c.waiver_id=@wid"
        results = await self.query(query, parameters=[{"name": "@wid", "value": waiver_id}])
        return results[0] if results else None

    async def list_active(self, limit: int = 100) -> List[WaiverRecord]:
        query = "SELECT * FROM c WHERE c.status!=@expired"
        results = await self.query(
            query,
            parameters=[{"name": "@expired", "value": WaiverStatus.EXPIRED.value}],
        )
        return results[:limit]

    async def list_due_within(
        self,
        *,
        days: int,
        statuses: Optional[Iterable[WaiverStatus]] = None,
        limit: int = 50,
    ) -> List[WaiverRecord]:
        status_values = [
            status.value if isinstance(status, WaiverStatus) else status
            for status in (
                statuses
                or [
                    WaiverStatus.APPROVED,
                    WaiverStatus.REQUESTED,
                ]
            )
        ]

        horizon = datetime.now(timezone.utc) + timedelta(days=days)

        query = (
            "SELECT * FROM c WHERE ARRAY_CONTAINS(@statuses, c.status) "
            "AND IS_DEFINED(c.expires_at) AND c.expires_at != null "
            "AND c.expires_at <= @horizon"
        )
        parameters = [
            {"name": "@statuses", "value": status_values},
            {"name": "@horizon", "value": horizon.isoformat()},
        ]
        results = await self.query(query, parameters=parameters)
        return results[:limit]
