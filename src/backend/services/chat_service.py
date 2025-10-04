"""Chat service translating natural language questions into Cosmos queries."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple
from uuid import uuid4

try:
    from azure.cosmos.exceptions import CosmosHttpResponseError
except (ModuleNotFoundError, ImportError):  # pragma: no cover - fallback for tests without SDK
    class CosmosHttpResponseError(Exception):
        """Fallback when Azure Cosmos SDK is unavailable during tests."""


from models.messages_kernel import AgentType, RunEventRecord, RiskTier
from repositories.asset_repository import AssetRepository
from repositories.canonical_finding_repository import CanonicalFindingRepository
from repositories.enrichment_repository import EnrichmentRepository
from repositories.remediation_unit_repository import RemediationUnitRepository
from repositories.run_event_repository import RunEventRepository
from repositories.ticket_repository import TicketRepository
from repositories.triage_repository import TriageRepository
from repositories.waiver_repository import WaiverRepository
from services.chat_access_policy import AccessDeniedError, ChatAccessPolicy, ChatScope
from services.chat_intent_classifier import ChatIntentClassifier, ChatIntentResult

logger = logging.getLogger(__name__)


class ChatService:
    """Execute structured queries on behalf of the chat agent."""

    def __init__(
        self,
        *,
        asset_repo: AssetRepository,
        canonical_repo: CanonicalFindingRepository,
        triage_repo: TriageRepository,
        remediation_repo: RemediationUnitRepository,
        ticket_repo: TicketRepository,
        waiver_repo: WaiverRepository,
        run_event_repo: RunEventRepository,
        enrichment_repo: Optional[EnrichmentRepository] = None,
        intent_classifier: Optional[ChatIntentClassifier] = None,
        access_policy: Optional[ChatAccessPolicy] = None,
    ) -> None:
        self._asset_repo = asset_repo
        self._canonical_repo = canonical_repo
        self._triage_repo = triage_repo
        self._remediation_repo = remediation_repo
        self._ticket_repo = ticket_repo
        self._waiver_repo = waiver_repo
        self._run_event_repo = run_event_repo
        self._enrichment_repo = enrichment_repo
        self._intent_classifier = intent_classifier or ChatIntentClassifier()
        self._access_policy = access_policy or ChatAccessPolicy()

    async def answer_question(
        self,
        *,
        question: str,
        user_context: Optional[Mapping[str, object]] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        intent = self._intent_classifier.classify(question)
        scope = self._access_policy.resolve_scope(user_context)

        records, citations = await self._execute_intent(
            intent=intent,
            scope=scope,
            limit=limit,
        )

        payload = {
            "intent": intent.intent,
            "question": question,
            "filters": intent.filters,
            "scope": self._scope_dict(scope),
            "results": records,
            "citations": citations,
        }

        run_id = await self._record_run_event(
            intent=intent.intent,
            scope=scope,
            question=question,
            result_count=len(records),
        )
        payload["run_id"] = run_id
        return payload

    async def _execute_intent(
        self,
        *,
        intent: ChatIntentResult,
        scope: ChatScope,
        limit: int,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        if intent.intent == "waivers_due":
            return await self._query_waivers(intent.filters, scope, limit)
        if intent.intent == "tickets_by_status":
            return await self._query_tickets(intent.filters, scope, limit)
        if intent.intent == "kev_exposures":
            return await self._query_kev_exposures(intent.filters, scope, limit)
        if intent.intent == "executive_summary":
            return await self._query_executive_summary(intent.filters, scope, limit)
        return await self._query_open_findings(intent.filters, scope, limit)

    async def _query_open_findings(
        self,
        filters: Mapping[str, Any],
        scope: ChatScope,
        limit: int,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        entries, citations = await self._collect_findings(
            filters=filters,
            scope=scope,
            limit=limit,
            require_kev=False,
            include_kev_signals=False,
        )
        return entries, citations

    async def _query_kev_exposures(
        self,
        filters: Mapping[str, Any],
        scope: ChatScope,
        limit: int,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        entries, citations = await self._collect_findings(
            filters=filters,
            scope=scope,
            limit=limit,
            require_kev=True,
            include_kev_signals=True,
        )
        return entries, citations

    async def _collect_findings(
        self,
        *,
        filters: Mapping[str, Any],
        scope: ChatScope,
        limit: int,
        require_kev: bool,
        include_kev_signals: bool,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        requested_tiers = filters.get("risk_tiers", []) or []
        risk_tiers: List[Any] = []
        for value in requested_tiers:
            try:
                risk_tiers.append(RiskTier(value))
            except ValueError:
                risk_tiers.append(value)

        canonical_records = await self._canonical_repo.query_open_findings(
            risk_tiers=risk_tiers,
            limit=limit * 5,
        )

        asset_cache: Dict[str, Any] = {}
        remediation_cache: Dict[str, Any] = {}
        enrichment_cache: Dict[str, Any] = {}
        results: List[Dict[str, Any]] = []
        citations: List[Dict[str, str]] = []

        for canonical in canonical_records:
            context = await self._load_context(
                canonical,
                asset_cache=asset_cache,
                remediation_cache=remediation_cache,
                enrichment_cache=enrichment_cache,
            )
            if context is None:
                continue
            asset, remediation, triage, enrichment = context

            if not self._passes_scope(scope, asset, remediation):
                continue

            kev_match = self._has_kev_signal(enrichment)
            if require_kev and not kev_match:
                continue

            entry = self._build_finding_entry(
                canonical=canonical,
                asset=asset,
                triage=triage,
                remediation=remediation,
            )

            if include_kev_signals and kev_match:
                entry["kev_signals"] = [
                    {
                        "source": signal.source,
                        "type": signal.signal_type,
                        "details": signal.details,
                        "confidence": self._confidence_value(signal.confidence),
                    }
                    for signal in enrichment.threat_signals
                    if self._is_kev_signal(signal)
                ]

            citations.extend(
                [
                    {"type": "canonical_finding", "id": canonical.canonical_id},
                    {"type": "asset", "id": asset.asset_id},
                ]
            )
            if remediation:
                citations.append({"type": "remediation_unit", "id": remediation.remediation_unit_id})

            results.append(entry)
            if len(results) >= limit:
                break

        return results, self._dedupe_citations(citations)

    @staticmethod
    def _confidence_value(value: Optional[object]) -> Optional[str]:
        if value is None:
            return None
        if hasattr(value, "value"):
            return getattr(value, "value")
        return str(value)

    async def _query_waivers(
        self,
        filters: Mapping[str, Any],
        scope: ChatScope,
        limit: int,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        days = int(filters.get("days", 30))
        waivers = await self._waiver_repo.list_due_within(days=days, limit=limit * 3)

        remediation_cache: Dict[str, Any] = {}
        results: List[Dict[str, Any]] = []
        citations: List[Dict[str, str]] = []

        for waiver in waivers:
            remediation = None
            if waiver.remediation_unit_id:
                if waiver.remediation_unit_id not in remediation_cache:
                    remediation_cache[waiver.remediation_unit_id] = await self._remediation_repo.get_unit(
                        waiver.remediation_unit_id
                    )
                remediation = remediation_cache[waiver.remediation_unit_id]

            if not scope.is_admin and scope.owner_groups:
                if remediation and remediation.owner not in scope.owner_groups:
                    continue

            entry = {
                "waiver_id": waiver.waiver_id,
                "risk_tier": waiver.risk_tier,
                "status": waiver.status,
                "expires_at": waiver.expires_at,
                "requested_by": waiver.requested_by,
                "requested_at": waiver.requested_at,
                "remediation_unit_id": waiver.remediation_unit_id,
            }
            if remediation:
                entry["remediation_unit_owner"] = remediation.owner
            citations.append({"type": "waiver", "id": waiver.waiver_id})
            if remediation:
                citations.append({"type": "remediation_unit", "id": remediation.remediation_unit_id})

            results.append(entry)
            if len(results) >= limit:
                break

        return results, self._dedupe_citations(citations)

    async def _query_tickets(
        self,
        filters: Mapping[str, Any],
        scope: ChatScope,
        limit: int,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        statuses = filters.get("statuses") or ["open", "in_progress"]
        tickets = await self._ticket_repo.list_by_status(statuses=statuses, limit=limit * 3)

        remediation_cache: Dict[str, Any] = {}
        results: List[Dict[str, Any]] = []
        citations: List[Dict[str, str]] = []

        for ticket in tickets:
            remediation = None
            if ticket.remediation_unit_id:
                if ticket.remediation_unit_id not in remediation_cache:
                    remediation_cache[ticket.remediation_unit_id] = await self._remediation_repo.get_unit(
                        ticket.remediation_unit_id
                    )
                remediation = remediation_cache[ticket.remediation_unit_id]

            if not scope.is_admin and scope.owner_groups:
                if remediation and remediation.owner not in scope.owner_groups:
                    continue

            entry = {
                "ticket_id": ticket.ticket_id,
                "status": ticket.status,
                "remediation_unit_id": ticket.remediation_unit_id,
                "assigned_to": ticket.assigned_to,
                "due_at": ticket.due_at,
                "url": ticket.url,
            }
            if remediation:
                entry["remediation_unit_owner"] = remediation.owner

            citations.append({"type": "ticket", "id": ticket.ticket_id, "url": ticket.url})
            if remediation:
                citations.append({"type": "remediation_unit", "id": remediation.remediation_unit_id})

            results.append(entry)
            if len(results) >= limit:
                break

        return results, self._dedupe_citations(citations)

    async def _query_executive_summary(
        self,
        filters: Mapping[str, Any],
        scope: ChatScope,
        limit: int,
    ) -> tuple[List[Dict[str, Any]], List[Dict[str, str]]]:
        risk_tiers = filters.get("risk_tiers", []) or []
        canonical_records = await self._canonical_repo.query_open_findings(
            risk_tiers=risk_tiers,
            limit=limit * 10,
        )

        asset_cache: Dict[str, Any] = {}
        remediation_cache: Dict[str, Any] = {}
        enrichment_cache: Dict[str, Any] = {}

        summary = {
            "total_open": 0,
            "by_risk": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            "kev_open": 0,
            "applications": {},
        }
        citations: List[Dict[str, str]] = []
        cited_ids: List[str] = []

        for canonical in canonical_records:
            context = await self._load_context(
                canonical,
                asset_cache=asset_cache,
                remediation_cache=remediation_cache,
                enrichment_cache=enrichment_cache,
            )
            if context is None:
                continue
            asset, remediation, _triage, enrichment = context

            if not self._passes_scope(scope, asset, remediation):
                continue

            summary["total_open"] += 1

            tier_value = str((canonical.risk_tier.value if isinstance(canonical.risk_tier, RiskTier) else canonical.risk_tier)).lower()
            if tier_value in summary["by_risk"]:
                summary["by_risk"][tier_value] += 1

            app_key = asset.application_context.application or "Unmapped"
            summary["applications"].setdefault(app_key, 0)
            summary["applications"][app_key] += 1

            if self._has_kev_signal(enrichment):
                summary["kev_open"] += 1

            if len(cited_ids) < max(1, limit):
                cited_ids.append(canonical.canonical_id)
                citations.append({"type": "canonical_finding", "id": canonical.canonical_id})

        return [summary], citations

    async def _record_run_event(
        self,
        *,
        intent: str,
        scope: ChatScope,
        question: str,
        result_count: int,
    ) -> str:
        record = RunEventRecord(
            correlation_id=str(uuid4()),
            agent_name=AgentType.CHAT.value,
            run_type="chat_qa",
            status="completed",
            metrics={
                "intent": intent,
                "result_count": result_count,
                "scope": self._scope_dict(scope),
            },
            error=None,
        )
        record.timestamp = datetime.now(timezone.utc)
        saved = await self._run_event_repo.upsert_event(record)
        return saved.id

    async def _load_context(
        self,
        canonical,
        *,
        asset_cache: Dict[str, Any],
        remediation_cache: Dict[str, Any],
        enrichment_cache: Dict[str, Any],
    ) -> Optional[Tuple[Any, Any, Any, Any]]:
        asset_id = getattr(canonical, "asset_id", None)
        if not asset_id:
            logger.warning(
                "Skipping canonical %s because asset_id is missing or empty",
                getattr(canonical, "canonical_id", "<unknown>"),
            )
            return None

        asset = asset_cache.get(asset_id)
        if asset is None:
            try:
                asset = await self._asset_repo.get_asset(asset_id)
            except CosmosHttpResponseError as exc:
                logger.warning(
                    "Skipping canonical %s due to asset lookup error for asset_id %s: %s",
                    getattr(canonical, "canonical_id", "<unknown>"),
                    asset_id,
                    exc,
                )
                asset_cache[asset_id] = None
                return None
            asset_cache[asset_id] = asset
        if not asset:
            logger.warning(
                "Skipping canonical %s because asset %s was not found in Cosmos",
                getattr(canonical, "canonical_id", "<unknown>"),
                asset_id,
            )
            return None

        remediation = None
        if canonical.remediation_unit_id:
            remediation = remediation_cache.get(canonical.remediation_unit_id)
            if remediation is None:
                remediation = await self._remediation_repo.get_unit(canonical.remediation_unit_id)
                remediation_cache[canonical.remediation_unit_id] = remediation

        triage = await self._triage_repo.get_latest(canonical.canonical_id)

        enrichment = None
        if self._enrichment_repo:
            enrichment = enrichment_cache.get(canonical.canonical_id)
            if enrichment is None:
                enrichment = await self._enrichment_repo.get_enrichment(
                    canonical.canonical_id,
                    asset.asset_id,
                )
                enrichment_cache[canonical.canonical_id] = enrichment

        return asset, remediation, triage, enrichment

    @staticmethod
    def _passes_scope(scope: ChatScope, asset, remediation) -> bool:
        if scope.is_admin:
            return True
        if scope.applications and asset.application_context.application not in scope.applications:
            return False
        if scope.owner_groups and remediation and remediation.owner not in scope.owner_groups:
            return False
        return True

    def _has_kev_signal(self, enrichment) -> bool:
        if not enrichment:
            return False
        return any(self._is_kev_signal(signal) for signal in enrichment.threat_signals)

    @staticmethod
    def _is_kev_signal(signal) -> bool:
        if not signal:
            return False
        source = (signal.source or "").lower()
        signal_type = (signal.signal_type or "").lower()
        return "kev" in source or "kev" in signal_type or "known_exploited" in signal_type

    @staticmethod
    def _scope_dict(scope: ChatScope) -> Dict[str, Any]:
        return {
            "applications": sorted(scope.applications),
            "owner_groups": sorted(scope.owner_groups),
            "is_admin": scope.is_admin,
        }

    @staticmethod
    def _dedupe_citations(citations: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
        seen = set()
        unique: List[Dict[str, str]] = []
        for citation in citations:
            key = (citation.get("type"), citation.get("id"), citation.get("url"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(citation)
        return unique

    @staticmethod
    def _build_finding_entry(*, canonical, asset, triage, remediation) -> Dict[str, Any]:
        entry: Dict[str, Any] = {
            "canonical_id": canonical.canonical_id,
            "vuln_key": canonical.vuln_key,
            "severity": canonical.severity,
            "risk_tier": canonical.risk_tier,
            "status": canonical.status,
            "asset_id": asset.asset_id,
            "asset_application": asset.application_context.application,
            "owner": asset.application_context.owner,
            "last_observed": canonical.last_observed,
        }
        if triage:
            entry["triage"] = {
                "risk_score": triage.risk_score,
                "likelihood": triage.likelihood,
                "impact": triage.impact,
                "treatment": triage.treatment,
            }
        if remediation:
            entry["remediation_unit"] = {
                "remediation_unit_id": remediation.remediation_unit_id,
                "owner": remediation.owner,
                "status": remediation.status,
                "target_due_date": remediation.target_due_date,
            }
        return entry


__all__ = ["ChatService"]
