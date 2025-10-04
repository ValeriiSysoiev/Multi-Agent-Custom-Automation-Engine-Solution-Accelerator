"""Deduplication service for canonical findings."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Tuple

from models.messages_kernel import (
    AssetIdentifier,
    CanonicalFinding,
    FindingLifecycleStatus,
    RiskTier,
    SourceReference,
)
from repositories.canonical_finding_repository import CanonicalFindingRepository
from services.canonical_utils import generate_canonical_id

RISK_TIER_PRIORITY = {
    RiskTier.VERY_LOW: 0,
    RiskTier.LOW: 1,
    RiskTier.MEDIUM: 2,
    RiskTier.HIGH: 3,
    RiskTier.CRITICAL: 4,
}

STATUS_PRIORITY = {
    FindingLifecycleStatus.OPEN: 3,
    FindingLifecycleStatus.REOPENED: 2,
    FindingLifecycleStatus.IN_REMEDIATION: 2,
    FindingLifecycleStatus.MITIGATED: 1,
    FindingLifecycleStatus.RESOLVED: 0,
    FindingLifecycleStatus.VERIFIED: 0,
    FindingLifecycleStatus.WAIVED: 0,
}


class DeduplicationService:
    """Merge canonical findings so each asset/vulnerability pair appears once."""

    def __init__(self, repository: CanonicalFindingRepository | None = None) -> None:
        self._repository = repository or CanonicalFindingRepository()

    async def merge(self, candidate: CanonicalFinding) -> CanonicalFinding:
        canonical_id = candidate.canonical_id or generate_canonical_id(
            candidate.asset_id,
            candidate.vuln_key,
            None,
        )
        candidate.canonical_id = canonical_id
        existing = await self._repository.get_by_id(canonical_id, candidate.asset_id)
        if existing is None:
            return await self._repository.upsert_finding(candidate)

        merged = await self._merge_records(existing, candidate)
        return await self._repository.upsert_finding(merged)

    async def _merge_records(self, existing: CanonicalFinding, candidate: CanonicalFinding) -> CanonicalFinding:
        existing.asset_identifiers = self._merge_identifiers(existing.asset_identifiers, candidate.asset_identifiers)
        existing.sources = self._merge_sources(existing.sources, candidate.sources)

        existing.severity = self._choose_severity(existing.severity, candidate.severity)
        existing.risk_tier = self._choose_risk_tier(existing.risk_tier, candidate.risk_tier)

        existing.description = existing.description or candidate.description
        existing.recommendations = existing.recommendations or candidate.recommendations

        existing.first_observed = self._choose_min_datetime(existing.first_observed, candidate.first_observed)
        existing.last_observed = self._choose_max_datetime(existing.last_observed, candidate.last_observed)

        existing.status = self._choose_status(existing, candidate)
        return existing

    def _merge_identifiers(
        self, existing: list[AssetIdentifier], incoming: list[AssetIdentifier]
    ) -> list[AssetIdentifier]:
        merged: Dict[Tuple[str, str], AssetIdentifier] = {
            (identifier.id_type.value, identifier.value): identifier for identifier in existing
        }
        for identifier in incoming:
            merged.setdefault((identifier.id_type.value, identifier.value), identifier)
        return list(merged.values())

    def _merge_sources(
        self, existing: list[SourceReference], incoming: list[SourceReference]
    ) -> list[SourceReference]:
        merged: Dict[Tuple[str, str], SourceReference] = {
            (src.scanner_id, src.external_id): src for src in existing
        }
        for reference in incoming:
            key = (reference.scanner_id, reference.external_id)
            current = merged.get(key)
            if current:
                current.last_seen = max(current.last_seen, reference.last_seen)
                current.first_seen = min(current.first_seen, reference.first_seen)
                current.severity = reference.severity or current.severity
                current.raw_finding_id = reference.raw_finding_id or current.raw_finding_id
                current.status = reference.status or current.status
            else:
                merged[key] = reference
        return list(merged.values())

    def _choose_severity(self, existing: str | None, incoming: str | None) -> str | None:
        if incoming is None:
            return existing
        if existing is None:
            return incoming
        # If severities are numeric strings, choose the higher numeric value
        try:
            existing_value = float(existing)
            incoming_value = float(incoming)
            return str(max(existing_value, incoming_value))
        except ValueError:
            # Fallback: prefer incoming when severities are non-numeric strings
            return incoming

    def _choose_risk_tier(self, existing: RiskTier, incoming: RiskTier) -> RiskTier:
        return existing if RISK_TIER_PRIORITY[existing] >= RISK_TIER_PRIORITY[incoming] else incoming

    def _choose_status(self, existing: CanonicalFinding, incoming: CanonicalFinding) -> FindingLifecycleStatus:
        existing_priority = STATUS_PRIORITY.get(existing.status, 1)
        incoming_priority = STATUS_PRIORITY.get(incoming.status, 1)

        # If any source in merged record indicates OPEN/REOPENED, prefer OPEN
        has_open_source = any(
            self._is_open_status(src.status) for src in existing.sources
        )
        if has_open_source:
            return FindingLifecycleStatus.OPEN

        if incoming_priority > existing_priority:
            return incoming.status
        return existing.status

    def _choose_min_datetime(self, existing: datetime | None, incoming: datetime | None) -> datetime | None:
        if not existing:
            return incoming
        if not incoming:
            return existing
        return min(existing, incoming)

    def _choose_max_datetime(self, existing: datetime | None, incoming: datetime | None) -> datetime | None:
        if not existing:
            return incoming
        if not incoming:
            return existing
        return max(existing, incoming)

    def _is_open_status(self, status: str | None) -> bool:
        if not status:
            return False
        return status.lower() in {"open", "re-opened", "reopened", "unhealthy"}
