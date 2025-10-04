import os
import sys
from datetime import datetime, timezone

import pytest

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from types import ModuleType
from pydantic import BaseModel, Field as PydanticField

if "semantic_kernel" not in sys.modules:
    semantic_kernel_module = ModuleType("semantic_kernel")
    sys.modules["semantic_kernel"] = semantic_kernel_module

    kernel_pydantic_module = ModuleType("semantic_kernel.kernel_pydantic")
    sys.modules["semantic_kernel.kernel_pydantic"] = kernel_pydantic_module
    semantic_kernel_module.kernel_pydantic = kernel_pydantic_module

    class _KernelBaseModel(BaseModel):
        class Config:
            arbitrary_types_allowed = True
            use_enum_values = True

    kernel_pydantic_module.KernelBaseModel = _KernelBaseModel
    kernel_pydantic_module.Field = PydanticField

from models.messages_kernel import (
    ApplicationContext,
    AssetIdentifier,
    AssetIdentifierType,
    CanonicalFinding,
    ConfidenceLevel,
    EnrichmentRecord,
    ExposureSurface,
    FindingLifecycleStatus,
    OwnershipStatus,
    RiskTier,
    SourceReference,
    ThreatSignal,
)
from services.risk_calculator import RiskCalculator


def _canonical(severity: str = "high", risk_tier: RiskTier = RiskTier.HIGH) -> CanonicalFinding:
    identifier = AssetIdentifier(
        id_type=AssetIdentifierType.CLOUD_RESOURCE_ID,
        value="/subscriptions/123/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/app1",
        source="defender",
    )
    source = SourceReference(
        scanner_id="defender",
        external_id="ext-1",
        first_seen=datetime.now(timezone.utc),
        last_seen=datetime.now(timezone.utc),
        severity=severity,
    )
    finding = CanonicalFinding(
        id="canon-1",
        canonical_id="canon-1",
        asset_id="asset-1",
        asset_identifiers=[identifier],
        sources=[source],
        vuln_key="CVE-2024-0001",
        severity=severity,
        risk_tier=risk_tier,
        status=FindingLifecycleStatus.OPEN,
        description="Test vulnerability",
        recommendations="Apply latest patch",
        first_observed=datetime.now(timezone.utc),
        last_observed=datetime.now(timezone.utc),
    )
    finding.ownership_status = OwnershipStatus.CONFIRMED
    return finding


def _enrichment(
    *,
    criticality: str = "Tier0",
    environment: str = "Prod",
    internet_facing: bool = True,
    authentication_required: bool | None = False,
    control_coverage: dict[str, bool] | None = None,
    threat_signals: list[ThreatSignal] | None = None,
    tags: dict[str, str] | None = None,
    application: str = "Payments API",
    business_service: str = "Checkout",
) -> EnrichmentRecord:
    context = ApplicationContext(
        application=application,
        business_service=business_service,
        owner="App Owner",
        owner_email="owner@example.com",
        environment=environment,
        criticality=criticality,
        completeness=ConfidenceLevel.HIGH,
        tags=tags or {},
    )
    exposure = ExposureSurface(
        internet_facing=internet_facing,
        authentication_required=authentication_required,
        network_segment="DMZ",
        control_coverage=control_coverage or {"waf": True, "edr": True},
    )
    record = EnrichmentRecord(
        id="canon-1",
        canonical_id="canon-1",
        asset_id="asset-1",
        application_context=context,
        exposure=exposure,
        threat_signals=threat_signals or [],
    )
    return record


def test_risk_calculator_known_exploited_elevates_to_critical():
    calculator = RiskCalculator()
    finding = _canonical(severity="critical", risk_tier=RiskTier.CRITICAL)
    signal = ThreatSignal(source="cisa", signal_type="known_exploited")
    enrichment = _enrichment(
        threat_signals=[signal], tags={"application_data_classification": "Regulated"}
    )

    result = calculator.compute(finding, enrichment)

    assert result.likelihood.value == 5
    assert result.impact.value == 5
    assert result.risk_tier == RiskTier.CRITICAL
    condition_ids = {item.condition_id for item in result.unacceptable_conditions}
    assert "outage_gt_24h" in condition_ids
    assert "large_data_breach" in condition_ids
    assert "active_exploitation_crown_jewel" in condition_ids


def test_risk_calculator_internal_dev_asset_results_in_medium():
    calculator = RiskCalculator()
    finding = _canonical(severity="medium", risk_tier=RiskTier.MEDIUM)
    enrichment = _enrichment(
        criticality="Tier2",
        environment="Dev",
        internet_facing=False,
        authentication_required=True,
        control_coverage={"waf": True, "edr": True},
        threat_signals=[],
        tags={},
        application="Internal Tool",
        business_service="Reporting",
    )

    result = calculator.compute(finding, enrichment)

    assert result.likelihood.value <= 3
    assert result.impact.value <= 3
    assert result.risk_tier in {RiskTier.MEDIUM, RiskTier.LOW, RiskTier.VERY_LOW}
    assert not result.unacceptable_conditions


def test_data_classification_adjusts_impact():
    calculator = RiskCalculator()
    finding = _canonical(severity="high", risk_tier=RiskTier.HIGH)
    enrichment = _enrichment(
        tags={"application_data_classification": "PCI"},
        application="Billing Platform",
        business_service="Finance",
        internet_facing=True,
    )
    pci_result = calculator.compute(finding, enrichment)

    enrichment.application_context.tags["application_data_classification"] = "Internal"
    internal_result = calculator.compute(finding, enrichment)

    assert pci_result.impact.value >= internal_result.impact.value
    assert pci_result.risk_tier.value >= internal_result.risk_tier.value
def test_active_exploitation_crown_jewel_forces_critical_even_with_lower_impact():
    calculator = RiskCalculator()
    finding = _canonical(severity="medium", risk_tier=RiskTier.MEDIUM)
    signal = ThreatSignal(source="kev", signal_type="Known_Exploited")
    enrichment = _enrichment(
        criticality="Tier1",
        environment="Prod",
        internet_facing=True,
        authentication_required=True,
        control_coverage={"waf": True, "edr": True},
        threat_signals=[signal],
        tags={"portfolio": "payments"},
        application="Checkout Gateway",
        business_service="Customer Checkout",
    )

    result = calculator.compute(finding, enrichment)

    assert result.risk_tier == RiskTier.CRITICAL
    condition_ids = {item.condition_id for item in result.unacceptable_conditions}
    assert "active_exploitation_crown_jewel" in condition_ids
