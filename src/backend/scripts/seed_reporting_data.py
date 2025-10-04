"""Seed representative VM lifecycle data for reporting exports."""

from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from types import ModuleType
from typing import Dict, List
from uuid import uuid4

from pydantic import BaseModel, Field as PydanticField

try:  # pragma: no cover - runtime convenience for local execution
    import semantic_kernel  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - seed script fallback
    semantic_kernel = ModuleType("semantic_kernel")
    sys.modules["semantic_kernel"] = semantic_kernel
    kernel_pydantic_module = ModuleType("semantic_kernel.kernel_pydantic")
    sys.modules["semantic_kernel.kernel_pydantic"] = kernel_pydantic_module

    class _KernelBaseModel(BaseModel):
        class Config:
            arbitrary_types_allowed = True
            use_enum_values = True

    kernel_pydantic_module.KernelBaseModel = _KernelBaseModel
    kernel_pydantic_module.Field = PydanticField

    semantic_kernel_kernel_module = ModuleType("semantic_kernel.kernel")
    semantic_kernel_kernel_module.Kernel = object
    sys.modules["semantic_kernel.kernel"] = semantic_kernel_kernel_module

try:  # pragma: no cover - prefer real SDK if available
    from azure.ai.projects.aio import AIProjectClient as _AIProjectClientCheck  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - stub only when SDK absent
    if "azure" not in sys.modules:
        sys.modules["azure"] = ModuleType("azure")
    azure_ai_module = sys.modules.setdefault("azure.ai", ModuleType("azure.ai"))
    azure_ai_projects_module = sys.modules.setdefault(
        "azure.ai.projects", ModuleType("azure.ai.projects")
    )
    azure_ai_projects_aio_module = sys.modules.setdefault(
        "azure.ai.projects.aio", ModuleType("azure.ai.projects.aio")
    )

    class _DummyAIProjectClient:  # pragma: no cover - minimal stub for config import
        async def close(self) -> None:
            return

    azure_ai_projects_aio_module.AIProjectClient = _DummyAIProjectClient
else:  # pragma: no cover - discard unused binding
    del _AIProjectClientCheck

from models.messages_kernel import (
    ApplicationContext,
    AssetIdentifier,
    AssetIdentifierType,
    AssetRecord,
    CanonicalFinding,
    ConfidenceLevel,
    ExposureSurface,
    EnrichmentRecord,
    FindingLifecycleStatus,
    OwnershipStatus,
    RemediationBucket,
    RemediationUnitRecord,
    ResidualRisk,
    RiskTier,
    SourceReference,
    ThreatSignal,
    TicketRecord,
    TicketStatus,
    TriageRecord,
    TreatmentRecommendation,
)
from repositories.asset_repository import AssetRepository
from repositories.canonical_finding_repository import CanonicalFindingRepository
from repositories.enrichment_repository import EnrichmentRepository
from repositories.remediation_unit_repository import RemediationUnitRepository
from repositories.ticket_repository import TicketRepository
from repositories.triage_repository import TriageRepository


SeedScenario = Dict[str, object]


SCENARIOS: List[SeedScenario] = [
    {
        "asset_id": "asset-web-01",
        "hostname": "web-01.corp.example",
        "application": "Customer Web",
        "business_service": "E-Commerce",
        "owner": "alice.nguyen@example.com",
        "canonical_id": "canon-web-01",
        "vuln_key": "CVE-2024-1111",
        "severity": "High",
        "cvss": 8.1,
        "risk_tier": RiskTier.HIGH,
        "likelihood": 4,
        "impact": 4,
        "treatment": TreatmentRecommendation.MITIGATE,
        "description": "Apache HTTP Server mod_proxy SSRF vulnerability allows remote attackers to pivot through reverse proxy configuration.",
        "recommendations": "Apply the vendor patch and restrict proxy access to trusted upstream endpoints.",
        "bucket": RemediationBucket.PATCH,
        "remediation_name": "Patch Apache HTTP Server",
        "owner_group": "Platform Operations",
        "due_in_days": 5,
        "ticket_id": "SEED-TICKET-001",
        "ticket_status": TicketStatus.IN_PROGRESS,
        "ticket_assignee": "platform.oncall@example.com",
    },
    {
        "asset_id": "asset-db-01",
        "hostname": "sql-01.corp.example",
        "application": "Billing Database",
        "business_service": "Finance",
        "owner": "maria.fernandez@example.com",
        "canonical_id": "canon-db-01",
        "vuln_key": "CVE-2023-4456",
        "severity": "Medium",
        "cvss": 6.5,
        "risk_tier": RiskTier.MEDIUM,
        "likelihood": 3,
        "impact": 3,
        "treatment": TreatmentRecommendation.MITIGATE,
        "description": "PostgreSQL extension vulnerability enabling privilege escalation on specific versions.",
        "recommendations": "Upgrade PostgreSQL to the fixed minor release and revoke unused extensions.",
        "bucket": RemediationBucket.PATCH,
        "remediation_name": "Upgrade PostgreSQL cluster",
        "owner_group": "Database Engineering",
        "due_in_days": 15,
        "ticket_id": "SEED-TICKET-002",
        "ticket_status": TicketStatus.OPEN,
        "ticket_assignee": "dba.team@example.com",
    },
    {
        "asset_id": "asset-api-01",
        "hostname": "api-01.corp.example",
        "application": "Public API Gateway",
        "business_service": "Digital Platform",
        "owner": "ryan.chen@example.com",
        "canonical_id": "canon-api-01",
        "vuln_key": "CVE-2024-22005",
        "severity": "Critical",
        "cvss": 9.8,
        "risk_tier": RiskTier.CRITICAL,
        "likelihood": 5,
        "impact": 5,
        "treatment": TreatmentRecommendation.MITIGATE,
        "description": "Fortinet SSL VPN authentication bypass allowing unauthenticated remote code execution.",
        "recommendations": "Apply emergency patch, rotate credentials, and enforce MFA on exposed VPN portals.",
        "bucket": RemediationBucket.CONFIG,
        "remediation_name": "Harden SSL VPN gateway",
        "owner_group": "Network Security",
        "due_in_days": 2,
        "ticket_id": "SEED-TICKET-003",
        "ticket_status": TicketStatus.RESOLVED,
        "ticket_assignee": "netsec.ops@example.com",
    },
]


async def seed_scenario(
    scenario: SeedScenario,
    *,
    asset_repo: AssetRepository,
    canonical_repo: CanonicalFindingRepository,
    enrichment_repo: EnrichmentRepository,
    triage_repo: TriageRepository,
    remediation_repo: RemediationUnitRepository,
    ticket_repo: TicketRepository,
    now: datetime,
) -> None:
    owner_email = scenario["owner"]
    asset = AssetRecord(
        asset_id=scenario["asset_id"],
        identifiers=[
            AssetIdentifier(
                id_type=AssetIdentifierType.HOSTNAME,
                value=scenario["hostname"],
                source="seed-script",
                last_observed=now,
            ),
        ],
        application_context=ApplicationContext(
            application=scenario["application"],
            business_service=scenario["business_service"],
            owner=scenario["owner"],
            owner_email=owner_email,
            environment="prod",
            criticality="tier0" if scenario["risk_tier"] == RiskTier.CRITICAL else "tier1",
            tags={"seed": True},
            completeness=ConfidenceLevel.HIGH,
        ),
        ownership_status=OwnershipStatus.CONFIRMED,
    )
    asset.id = asset.asset_id
    asset.timestamp = now
    await asset_repo.upsert_asset(asset)

    canonical = CanonicalFinding(
        canonical_id=scenario["canonical_id"],
        asset_id=scenario["asset_id"],
        asset_identifiers=asset.identifiers,
        sources=[
            SourceReference(
                scanner_id="seed-scanner",
                external_id=str(uuid4()),
                first_seen=now - timedelta(days=7),
                last_seen=now,
                severity=scenario["severity"],
                status=FindingLifecycleStatus.OPEN.value,
            )
        ],
        vuln_key=scenario["vuln_key"],
        cvss_score=scenario["cvss"],
        severity=scenario["severity"],
        risk_tier=scenario["risk_tier"],
        status=FindingLifecycleStatus.TRIAGED,
        remediation_bucket=scenario["bucket"],
        description=scenario["description"],
        recommendations=scenario["recommendations"],
        first_observed=now - timedelta(days=14),
        last_observed=now,
        ownership_status=OwnershipStatus.CONFIRMED,
    )
    canonical.id = canonical.canonical_id
    canonical.timestamp = now
    await canonical_repo.upsert_finding(canonical)

    enrichment = EnrichmentRecord(
        canonical_id=canonical.canonical_id,
        asset_id=canonical.asset_id,
        application_context=asset.application_context,
        exposure=ExposureSurface(
            internet_facing=scenario["risk_tier"] in {RiskTier.CRITICAL, RiskTier.HIGH},
            authentication_required=False,
            network_segment="dmz" if scenario["risk_tier"] in {RiskTier.CRITICAL, RiskTier.HIGH} else "internal",
            control_coverage={"waf": scenario["bucket"] == RemediationBucket.CONFIG},
        ),
        threat_signals=[
            ThreatSignal(
                source="seed",
                signal_type="kev",
                confidence=ConfidenceLevel.MEDIUM,
                details={"kiln": "seed"},
            )
        ],
        enrichment_version="seed-2025-09-26",
    )
    enrichment.id = canonical.canonical_id
    enrichment.timestamp = now
    await enrichment_repo.upsert_enrichment(enrichment)

    risk_score = scenario["likelihood"] * scenario["impact"]
    triage = TriageRecord(
        triage_id=f"triage-{canonical.canonical_id}",
        canonical_id=canonical.canonical_id,
        created_by="seed-script",
        likelihood=scenario["likelihood"],
        impact=scenario["impact"],
        risk_score=risk_score,
        risk_tier=scenario["risk_tier"],
        treatment=scenario["treatment"],
        rationale="Seeded triage decision for reporting validation.",
        supporting_inputs={"seed": True},
        residual_risk=ResidualRisk(
            risk_tier=scenario["risk_tier"],
            risk_score=risk_score,
            rationale="Residual risk mirrors initial assessment for seed data.",
        ),
    )
    triage.id = triage.triage_id
    triage.timestamp = now
    await triage_repo.upsert_record(triage)

    remediation = RemediationUnitRecord(
        remediation_unit_id=f"ru-{canonical.canonical_id}",
        name=scenario["remediation_name"],
        bucket=scenario["bucket"],
        risk_tier=scenario["risk_tier"],
        status=FindingLifecycleStatus.IN_REMEDIATION,
        canonical_ids=[canonical.canonical_id],
        target_due_date=now + timedelta(days=scenario["due_in_days"]),
        owner=scenario["owner_group"],
        notes="Seed remediation unit for reporting demo",
    )
    remediation.id = remediation.remediation_unit_id
    remediation.timestamp = now
    await remediation_repo.upsert_unit(remediation)

    ticket = TicketRecord(
        ticket_id=scenario["ticket_id"],
        remediation_unit_id=remediation.remediation_unit_id,
        external_key=scenario["ticket_id"],
        url=f"https://cyberairnd.atlassian.net/browse/{scenario['ticket_id']}",
        status=scenario["ticket_status"],
        assigned_to=scenario["ticket_assignee"],
        opened_at=now - timedelta(days=3),
        due_at=remediation.target_due_date,
        sla_breached=False,
    )
    ticket.id = ticket.ticket_id
    ticket.timestamp = now
    await ticket_repo.upsert_ticket(ticket)


async def main() -> None:
    now = datetime.now(timezone.utc)

    asset_repo = AssetRepository()
    canonical_repo = CanonicalFindingRepository()
    enrichment_repo = EnrichmentRepository()
    triage_repo = TriageRepository()
    remediation_repo = RemediationUnitRepository()
    ticket_repo = TicketRepository()

    for scenario in SCENARIOS:
        await seed_scenario(
            scenario,
            asset_repo=asset_repo,
            canonical_repo=canonical_repo,
            enrichment_repo=enrichment_repo,
            triage_repo=triage_repo,
            remediation_repo=remediation_repo,
            ticket_repo=ticket_repo,
            now=now,
        )

    print("Seeded reporting sample data for", len(SCENARIOS), "scenarios.")


if __name__ == "__main__":  # pragma: no cover - manual execution entrypoint
    asyncio.run(main())
