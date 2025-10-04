"""Service responsible for enriching canonical findings with business and threat context."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence

from models.messages_kernel import (
    ApplicationContext,
    AssetIdentifier,
    AssetRecord,
    CanonicalFinding,
    ConfidenceLevel,
    EnrichmentRecord,
    ExposureSurface,
    LinkageReviewInfo,
    OwnershipStatus,
)
from repositories.asset_repository import AssetRepository
from repositories.canonical_finding_repository import CanonicalFindingRepository
from repositories.enrichment_repository import EnrichmentRepository
from services.jira_assets_client import JiraAssetsClient
from services.threat_intel_service import ThreatIntelService

logger = logging.getLogger(__name__)

ENRICHMENT_VERSION = "2025-Phase1b"


class EnrichmentService:
    """Coordinates CMDB and threat-intel enrichment for canonical findings."""

    def __init__(
        self,
        canonical_repo: Optional[CanonicalFindingRepository] = None,
        enrichment_repo: Optional[EnrichmentRepository] = None,
        asset_repo: Optional[AssetRepository] = None,
        jira_client: Optional[JiraAssetsClient] = None,
        threat_service: Optional[ThreatIntelService] = None,
    ) -> None:
        self._canonical_repo = canonical_repo or CanonicalFindingRepository()
        self._enrichment_repo = enrichment_repo or EnrichmentRepository()
        self._asset_repo = asset_repo or AssetRepository()
        self._jira = jira_client or JiraAssetsClient()
        self._threat = threat_service or ThreatIntelService()

    async def close(self) -> None:
        await self._jira.close()
        await self._threat.close()

    async def enrich_findings(self, findings: Sequence[CanonicalFinding]) -> List[EnrichmentRecord]:
        results: List[EnrichmentRecord] = []
        for finding in findings:
            try:
                enriched = await self._enrich_single(finding)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Failed to enrich canonical %s: %s", finding.canonical_id, exc)
                continue
            if enriched:
                results.append(enriched)
        return results

    async def _enrich_single(self, finding: CanonicalFinding) -> Optional[EnrichmentRecord]:
        existing = await self._enrichment_repo.get_enrichment(finding.canonical_id, finding.asset_id)
        if existing and existing.enrichment_version == ENRICHMENT_VERSION:
            logger.debug("Enrichment already up-to-date for %s", finding.canonical_id)
            return existing

        context, exposure, ownership_status, linkage_info = await self._jira.resolve_context(
            finding.asset_id,
            finding.asset_identifiers,
            finding.risk_tier,
        )
        threat_signals = await self._threat.gather_signals(finding.vuln_key)

        enrichment = EnrichmentRecord(
            id=finding.canonical_id,
            canonical_id=finding.canonical_id,
            asset_id=finding.asset_id,
            application_context=context,
            exposure=exposure,
            threat_signals=threat_signals,
            enrichment_version=ENRICHMENT_VERSION,
        )
        enrichment.timestamp = datetime.now(timezone.utc)
        saved = await self._enrichment_repo.upsert_enrichment(enrichment)

        await self._update_asset_record(finding, context, ownership_status, linkage_info)
        await self._update_canonical(finding, ownership_status, linkage_info)
        return saved

    async def _update_asset_record(
        self,
        finding: CanonicalFinding,
        context: ApplicationContext,
        ownership_status: OwnershipStatus,
        linkage_info: Optional[LinkageReviewInfo],
    ) -> None:
        existing = await self._asset_repo.get_asset(finding.asset_id)
        if existing:
            merged_identifiers = self._merge_identifiers(existing.identifiers, finding.asset_identifiers)
            best_context = self._choose_better_context(existing.application_context, context)
            best_status = self._prefer_status(existing.ownership_status, ownership_status)
            if (
                existing.ownership_status == OwnershipStatus.LINKAGE_REVIEW
                and ownership_status in {OwnershipStatus.CONFIRMED, OwnershipStatus.PROVISIONAL}
            ):
                best_status = ownership_status

            if linkage_info is not None:
                linkage = linkage_info
            elif best_status == OwnershipStatus.LINKAGE_REVIEW:
                linkage = existing.linkage_review
            else:
                linkage = None
            record = AssetRecord(
                id=finding.asset_id,
                asset_id=finding.asset_id,
                identifiers=merged_identifiers,
                application_context=best_context,
                ownership_status=best_status,
                linkage_review=linkage,
            )
        else:
            initial_linkage = linkage_info if ownership_status == OwnershipStatus.LINKAGE_REVIEW else None
            record = AssetRecord(
                id=finding.asset_id,
                asset_id=finding.asset_id,
                identifiers=list(finding.asset_identifiers),
                application_context=context,
                ownership_status=ownership_status,
                linkage_review=initial_linkage,
            )
        await self._asset_repo.upsert_asset(record)

    async def _update_canonical(
        self,
        finding: CanonicalFinding,
        ownership_status: OwnershipStatus,
        linkage_info: Optional[LinkageReviewInfo],
    ) -> None:
        finding.ownership_status = ownership_status
        finding.linkage_review = linkage_info
        finding.timestamp = datetime.now(timezone.utc)
        await self._canonical_repo.upsert_finding(finding)

    def _merge_identifiers(
        self,
        existing: Iterable[AssetIdentifier],
        incoming: Iterable[AssetIdentifier],
    ) -> List[AssetIdentifier]:
        merged: dict[tuple[str, str], AssetIdentifier] = {
            (identifier.id_type.value, identifier.value): identifier for identifier in existing
        }
        for identifier in incoming:
            merged.setdefault((identifier.id_type.value, identifier.value), identifier)
        return list(merged.values())

    def _choose_better_context(
        self,
        current: ApplicationContext,
        incoming: ApplicationContext,
    ) -> ApplicationContext:
        current_score = self._context_score(current)
        incoming_score = self._context_score(incoming)
        return incoming if incoming_score >= current_score else current

    def _prefer_status(
        self,
        existing: OwnershipStatus,
        incoming: OwnershipStatus,
    ) -> OwnershipStatus:
        order = {
            OwnershipStatus.CONFIRMED: 3,
            OwnershipStatus.PROVISIONAL: 2,
            OwnershipStatus.LINKAGE_REVIEW: 1,
            OwnershipStatus.UNKNOWN: 0,
        }
        return incoming if order.get(incoming, 0) >= order.get(existing, 0) else existing

    def _context_score(self, context: ApplicationContext) -> int:
        score = 0
        if context.completeness == ConfidenceLevel.HIGH:
            score += 3
        elif context.completeness == ConfidenceLevel.MEDIUM:
            score += 2
        elif context.completeness == ConfidenceLevel.LOW:
            score += 1
        if context.owner:
            score += 1
        if context.application:
            score += 1
        return score
