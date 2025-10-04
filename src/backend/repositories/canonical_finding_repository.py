"""Repository for canonical vulnerability findings."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, List, Optional

from models.messages_kernel import (CanonicalFinding, FindingLifecycleStatus,
                                    RiskTier)

from .cosmos_repository import CosmosRepository

CANONICAL_CONTAINER = "findings_canonical"
PARTITION_KEY = "/asset_id"


class CanonicalFindingRepository(CosmosRepository[CanonicalFinding]):
    def __init__(self) -> None:
        super().__init__(CANONICAL_CONTAINER, CanonicalFinding, PARTITION_KEY)

    async def get_by_id(self, canonical_id: str, asset_id: str) -> Optional[CanonicalFinding]:
        return await self.read(canonical_id, asset_id)

    async def upsert_finding(self, finding: CanonicalFinding) -> CanonicalFinding:
        return await self.upsert(finding)

    async def list_for_asset(self, asset_id: str, limit: int = 100) -> List[CanonicalFinding]:
        return await self.list_partition(asset_id, limit=limit)

    async def list_pending_triage(self, limit: int = 100) -> List[CanonicalFinding]:
        query = "SELECT * FROM c WHERE c.status=@open OR c.status=@reopened"
        parameters = [
            {"name": "@open", "value": "open"},
            {"name": "@reopened", "value": "reopened"},
        ]
        results = await self.query(query, parameters)
        return results[:limit]

    async def list_ready_for_remediation(self, limit: int = 100) -> List[CanonicalFinding]:
        query = (
            "SELECT * FROM c WHERE c.status=@triaged "
            "AND (NOT IS_DEFINED(c.remediation_unit_id) OR c.remediation_unit_id = null) "
            "AND (NOT IS_DEFINED(c.treatment_follow_up_id) OR c.treatment_follow_up_id = null)"
        )
        parameters = [{"name": "@triaged", "value": "triaged"}]
        results = await self.query(query, parameters)
        return results[:limit]

    async def get_by_canonical_id(self, canonical_id: str) -> Optional[CanonicalFinding]:
        query = "SELECT * FROM c WHERE c.id=@cid"
        results = await self.query(query, parameters=[{"name": "@cid", "value": canonical_id}])
        return results[0] if results else None

    async def query_open_findings(
        self,
        *,
        risk_tiers: Optional[Iterable[RiskTier]] = None,
        statuses: Optional[Iterable[FindingLifecycleStatus]] = None,
        limit: int = 50,
        modified_since: Optional[datetime] = None,
    ) -> List[CanonicalFinding]:
        """Return open/active findings filtered by risk tier/status."""

        query = "SELECT * FROM c WHERE 1=1"
        parameters = []

        status_values = [
            status.value if isinstance(status, FindingLifecycleStatus) else status
            for status in (statuses or [
                FindingLifecycleStatus.OPEN,
                FindingLifecycleStatus.TRIAGED,
                FindingLifecycleStatus.IN_REMEDIATION,
                FindingLifecycleStatus.REOPENED,
            ])
        ]
        query += " AND ARRAY_CONTAINS(@statuses, c.status)"
        parameters.append({"name": "@statuses", "value": status_values})

        if risk_tiers:
            tier_values = [
                tier.value if isinstance(tier, RiskTier) else tier for tier in risk_tiers
            ]
            query += " AND ARRAY_CONTAINS(@risk_tiers, c.risk_tier)"
            parameters.append({"name": "@risk_tiers", "value": tier_values})

        if modified_since:
            if modified_since.tzinfo is None:
                modified_since = modified_since.replace(tzinfo=timezone.utc)
            query += " AND c.last_observed >= @modified_since"
            parameters.append(
                {
                    "name": "@modified_since",
                    "value": modified_since.isoformat(),
                }
            )

        query += " ORDER BY c.last_observed DESC"

        results = await self.query(query, parameters)
        return results[:limit]
