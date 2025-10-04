"""Service responsible for risk triage of canonical findings."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional
from uuid import UUID, uuid4

from azure.identity.aio import ManagedIdentityCredential, DefaultAzureCredential
from helpers.azure_credential_utils import get_azure_credential_async

from models.messages_kernel import (
    AgentType,
    CanonicalFinding,
    EnrichmentRecord,
    FindingLifecycleStatus,
    OwnershipStatus,
    ResidualRisk,
    RiskTier,
    RunEventRecord,
    TriageRecord,
)
from repositories.canonical_finding_repository import CanonicalFindingRepository
from repositories.enrichment_repository import EnrichmentRepository
from repositories.run_event_repository import RunEventRepository
from repositories.triage_repository import TriageRepository
from services.http_client import AsyncHttpClient
from services.risk_calculator import RiskCalculator, RiskComputation, default_residual_risk
from services.triage_models import TriageLLMResponse, triage_response_schema

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "triage_prompt.txt"
COGNITIVE_SCOPE = "https://cognitiveservices.azure.com/.default"


class TriageService:
    """Coordinates deterministic and AI-assisted triage scoring."""

    def __init__(
        self,
        canonical_repo: Optional[CanonicalFindingRepository] = None,
        enrichment_repo: Optional[EnrichmentRepository] = None,
        triage_repo: Optional[TriageRepository] = None,
        run_repo: Optional[RunEventRepository] = None,
        risk_calculator: Optional[RiskCalculator] = None,
        enable_llm: Optional[bool] = None,
    ) -> None:
        self._canonical_repo = canonical_repo or CanonicalFindingRepository()
        self._enrichment_repo = enrichment_repo or EnrichmentRepository()
        self._triage_repo = triage_repo or TriageRepository()
        self._run_repo = run_repo or RunEventRepository()
        self._risk = risk_calculator or RiskCalculator()

        self._enable_llm = enable_llm if enable_llm is not None else self._env_flag("ENABLE_TRIAGE_LLM", True)
        self._llm_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self._llm_deployment = os.getenv("TRIAGE_MODEL_DEPLOYMENT") or os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        self._llm_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-11-20")
        self._system_prompt = self._load_system_prompt()

        self._llm_http: Optional[AsyncHttpClient] = None
        self._credential: Optional[ManagedIdentityCredential | DefaultAzureCredential] = None

    async def close(self) -> None:
        if self._llm_http:
            await self._llm_http.close()
            self._llm_http = None
        if self._credential:
            await self._credential.close()
            self._credential = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def triage_findings(self, limit: int = 20, actor: str = AgentType.TRIAGE.value) -> List[TriageRecord]:
        pending = await self._canonical_repo.list_pending_triage(limit=limit)
        if not pending:
            logger.info("No canonical findings pending triage")
            return []

        correlation_id = str(uuid4())
        started_at = datetime.now(timezone.utc)
        metrics: Dict[str, int] = {"processed": 0, "skipped_no_enrichment": 0, "triaged": 0}

        await self._run_repo.upsert_event(
            self._build_run_event(
                correlation_id=correlation_id,
                status="started",
                started_at=started_at,
                metrics=metrics,
            )
        )

        results: List[TriageRecord] = []
        for finding in pending:
            metrics["processed"] += 1
            record = await self.triage_single(finding, actor=actor)
            if record:
                results.append(record)
                metrics["triaged"] += 1
            else:
                metrics["skipped_no_enrichment"] += 1

        completed_at = datetime.now(timezone.utc)
        await self._run_repo.upsert_event(
            self._build_run_event(
                correlation_id=correlation_id,
                status="completed",
                started_at=started_at,
                completed_at=completed_at,
                metrics=metrics,
            )
        )

        logger.info(
            "Triage batch complete: triaged=%d skipped=%d", metrics["triaged"], metrics["skipped_no_enrichment"]
        )
        return results

    async def triage_single(
        self,
        finding: CanonicalFinding,
        *,
        actor: str = AgentType.TRIAGE.value,
    ) -> Optional[TriageRecord]:
        enrichment = await self._enrichment_repo.get_enrichment(finding.canonical_id, finding.asset_id)
        if not enrichment:
            logger.info("Skipping triage for %s: enrichment missing", finding.canonical_id)
            return None

        if finding.ownership_status == OwnershipStatus.LINKAGE_REVIEW:
            logger.info("Skipping triage for %s: ownership unresolved", finding.canonical_id)
            return None

        risk = self._risk.compute(finding, enrichment)
        llm_response = await self._maybe_invoke_llm(finding, enrichment, risk)

        final_likelihood = risk.likelihood.value
        final_impact = risk.impact.value
        final_tier = risk.risk_tier
        final_treatment = risk.recommended_treatment
        unacceptable_ids = [outcome.condition_id for outcome in risk.unacceptable_conditions]
        rationale = self._compose_rationale(risk)
        residual = default_residual_risk(final_tier)

        if llm_response:
            final_likelihood = max(1, min(5, llm_response.likelihood))
            final_impact = max(1, min(5, llm_response.impact))
            final_tier = self._highest_tier(final_tier, llm_response.risk_tier)
            final_treatment = llm_response.treatment
            unacceptable_ids = sorted(set(unacceptable_ids + llm_response.unacceptable_conditions))
            rationale = llm_response.rationale
            residual = ResidualRisk(
                risk_tier=final_tier,
                rationale=llm_response.residual_risk_rationale,
            )

        final_score = max(1, final_likelihood) * max(1, final_impact)

        supporting_inputs = self._supporting_inputs(finding, enrichment, risk, unacceptable_ids)
        if llm_response:
            metadata = {
                "compensating_controls": llm_response.compensating_controls,
                "waiver_justification": llm_response.waiver_justification,
                "waiver_expiry_days": llm_response.waiver_expiry_days,
                "risk_transfer_notes": llm_response.risk_transfer_notes,
            }
            # Remove empty values to keep payload compact
            metadata = {
                key: value
                for key, value in metadata.items()
                if (value is not None and value != [] and value != "")
            }
            if metadata:
                supporting_inputs["treatment_metadata"] = metadata

        previous = await self._triage_repo.get_latest(finding.canonical_id)
        triage_record = TriageRecord(
            id=str(uuid4()),
            triage_id=str(uuid4()),
            canonical_id=finding.canonical_id,
            created_by=actor,
            likelihood=final_likelihood,
            impact=final_impact,
            risk_score=final_score,
            risk_tier=final_tier,
            treatment=final_treatment,
            rationale=rationale,
            supporting_inputs=supporting_inputs,
            residual_risk=residual,
            supersedes=previous.triage_id if previous else None,
        )
        triage_record.timestamp = datetime.now(timezone.utc)

        await self._triage_repo.upsert_record(triage_record)

        finding.risk_tier = final_tier
        finding.status = FindingLifecycleStatus.TRIAGED
        finding.timestamp = datetime.now(timezone.utc)
        await self._canonical_repo.upsert_finding(finding)

        return triage_record

    # ------------------------------------------------------------------
    # LLM integration
    # ------------------------------------------------------------------
    async def _maybe_invoke_llm(
        self,
        finding: CanonicalFinding,
        enrichment: EnrichmentRecord,
        risk: RiskComputation,
    ) -> Optional[TriageLLMResponse]:
        if not self._enable_llm:
            return None
        if not self._llm_endpoint or not self._llm_deployment:
            logger.warning("LLM triage disabled: endpoint or deployment not configured")
            return None

        try:
            await self._ensure_llm_clients()
        except Exception as exc:  # pragma: no cover - fallback path
            logger.warning("LLM triage disabled due to credential error: %s", exc)
            return None

        assert self._llm_http is not None
        assert self._credential is not None

        token = await self._credential.get_token(COGNITIVE_SCOPE)
        headers = {
            "Authorization": f"Bearer {token.token}",
            "Content-Type": "application/json",
        }

        payload = {
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "text", "text": self._system_prompt}],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": self._build_user_prompt(finding, enrichment, risk),
                        }
                    ],
                },
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "TriageLLMResponse",
                    "schema": triage_response_schema(),
                },
            },
            "temperature": 0.0,
        }

        url = f"/openai/deployments/{self._llm_deployment}/responses?api-version={self._llm_api_version}"
        try:
            response = await self._llm_http.post(url, headers=headers, json=payload, expected_status=[200])
        except Exception as exc:  # pragma: no cover - network fallback
            logger.warning("LLM triage request failed: %s", exc)
            return None

        data = response.json()
        content = self._extract_content(data)
        if not content:
            logger.warning("LLM triage returned empty content: %s", data)
            return None

        try:
            return TriageLLMResponse.model_validate_json(content)
        except Exception as exc:
            logger.warning("Failed to parse LLM triage response: %s", exc)
            return None

    async def _ensure_llm_clients(self) -> None:
        if self._llm_http is None:
            self._llm_http = AsyncHttpClient(base_url=self._llm_endpoint, default_headers={"Accept": "application/json"})
        if self._credential is None:
            self._credential = await get_azure_credential_async()

    def _build_user_prompt(
        self,
        finding: CanonicalFinding,
        enrichment: EnrichmentRecord,
        risk: RiskComputation,
    ) -> str:
        context = {
            "finding": {
                "canonical_id": finding.canonical_id,
                "asset_id": finding.asset_id,
                "vuln_key": finding.vuln_key,
                "severity": finding.severity,
                "description": finding.description,
                "recommendations": finding.recommendations,
                "risk_tier": finding.risk_tier.value,
                "sources": [source.model_dump(exclude_none=True) for source in finding.sources],
            },
            "business_context": enrichment.application_context.model_dump(exclude_none=True),
            "exposure": enrichment.exposure.model_dump(exclude_none=True),
            "threat_signals": [signal.model_dump(exclude_none=True) for signal in enrichment.threat_signals],
            "risk_baseline": {
                "likelihood": risk.likelihood.value,
                "likelihood_reasons": risk.likelihood.reasons,
                "impact": risk.impact.value,
                "impact_reasons": risk.impact.reasons,
                "risk_score": risk.risk_score,
                "risk_tier": risk.risk_tier.value,
                "recommended_treatment": risk.recommended_treatment.value,
                "unacceptable_conditions": [
                    {
                        "id": outcome.condition_id,
                        "description": outcome.description,
                        "floor": outcome.enforced_tier.value,
                    }
                    for outcome in risk.unacceptable_conditions
                ],
            },
        }
        return json.dumps(context, indent=2, default=self._prompt_json_default)

    @staticmethod
    def _prompt_json_default(value):
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")

    def _extract_content(self, payload: Dict[str, object]) -> Optional[str]:
        output = payload.get("output") or payload.get("result")
        if isinstance(output, dict):
            message = output.get("message") or output.get("messages")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") in {"text", "output_text"}:
                            text = item.get("text") or item.get("content")
                            if isinstance(text, str) and text.strip():
                                return text
            if "output_text" in output:
                entries = output.get("output_text")
                if isinstance(entries, list) and entries:
                    first = entries[0]
                    if isinstance(first, dict):
                        text = first.get("text") or first.get("content")
                        if isinstance(text, str) and text.strip():
                            return text
        if "output" in payload and isinstance(payload["output"], list):
            for item in payload["output"]:
                if isinstance(item, dict):
                    message = item.get("message")
                    if isinstance(message, dict):
                        content = message.get("content")
                        if isinstance(content, list):
                            for piece in content:
                                text = piece.get("text") if isinstance(piece, dict) else None
                                if isinstance(text, str) and text.strip():
                                    return text
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _supporting_inputs(
        self,
        finding: CanonicalFinding,
        enrichment: EnrichmentRecord,
        risk: RiskComputation,
        unacceptable_ids: Iterable[str],
    ) -> Dict[str, object]:
        return {
            "likelihood_reasons": risk.likelihood.reasons,
            "impact_reasons": risk.impact.reasons,
            "unacceptable_conditions": list(unacceptable_ids),
            "baseline_risk_score": risk.risk_score,
            "threat_signals": [signal.model_dump(exclude_none=True) for signal in enrichment.threat_signals],
            "exposure": enrichment.exposure.model_dump(exclude_none=True),
            "business_context": enrichment.application_context.model_dump(exclude_none=True),
        }

    def _compose_rationale(self, risk: RiskComputation) -> str:
        parts = [
            f"Likelihood {risk.likelihood.value} ({'; '.join(risk.likelihood.reasons)})",
            f"Impact {risk.impact.value} ({'; '.join(risk.impact.reasons)})",
        ]
        if risk.unacceptable_conditions:
            floors = ", ".join(outcome.condition_id for outcome in risk.unacceptable_conditions)
            parts.append(f"Unacceptable outcomes enforced floors: {floors}")
        return " | ".join(parts)

    def _highest_tier(self, current: RiskTier, candidate: RiskTier) -> RiskTier:
        order = {
            RiskTier.VERY_LOW: 0,
            RiskTier.LOW: 1,
            RiskTier.MEDIUM: 2,
            RiskTier.HIGH: 3,
            RiskTier.CRITICAL: 4,
        }
        return candidate if order[candidate] > order[current] else current

    def _build_run_event(
        self,
        *,
        correlation_id: str,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        metrics: Optional[Dict[str, int]] = None,
    ):
        record = RunEventRecord(
            id=correlation_id,
            correlation_id=correlation_id,
            agent_name=AgentType.TRIAGE.value,
            run_type="triage_batch",
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            metrics=metrics or {},
        )
        record.timestamp = completed_at or started_at or datetime.now(timezone.utc)
        return record

    def _load_system_prompt(self) -> str:
        if SYSTEM_PROMPT_PATH.exists():
            return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8").strip()
        logger.warning("Triage system prompt not found; using fallback instructions")
        return (
            "You are the Triage Agent. Apply the risk methodology strictly, outputting JSON that matches the schema."
        )

    def _env_flag(self, name: str, default: bool) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {"1", "true", "yes"}


__all__ = ["TriageService"]
