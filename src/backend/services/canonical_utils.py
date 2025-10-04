"""Helper utilities for mapping scanner data into canonical findings."""

from __future__ import annotations

import hashlib
from typing import Dict, Optional

from models.messages_kernel import (
    AssetIdentifier,
    AssetIdentifierType,
    FindingLifecycleStatus,
    RemediationBucket,
    RiskTier,
)

SEVERITY_TO_RISK_TIER: Dict[str, RiskTier] = {
    "critical": RiskTier.CRITICAL,
    "high": RiskTier.HIGH,
    "medium": RiskTier.MEDIUM,
    "low": RiskTier.LOW,
    "very_low": RiskTier.VERY_LOW,
    "info": RiskTier.VERY_LOW,
}

QUALYS_SEVERITY_TO_RISK_TIER: Dict[int, RiskTier] = {
    5: RiskTier.CRITICAL,
    4: RiskTier.HIGH,
    3: RiskTier.MEDIUM,
    2: RiskTier.LOW,
    1: RiskTier.VERY_LOW,
    0: RiskTier.VERY_LOW,
}


def generate_canonical_id(asset_key: str, vuln_key: str, location_signature: Optional[str] = None) -> str:
    """Generate a deterministic canonical identifier."""

    basis = "|".join(filter(None, [asset_key, vuln_key, location_signature or ""]))
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def normalize_severity(value: str) -> str:
    return value.lower()


def map_severity_to_risk_tier(severity: str) -> RiskTier:
    return SEVERITY_TO_RISK_TIER.get(severity.lower(), RiskTier.MEDIUM)


def map_qualys_severity(value: int) -> RiskTier:
    return QUALYS_SEVERITY_TO_RISK_TIER.get(value, RiskTier.MEDIUM)


def make_asset_identifier(id_type: AssetIdentifierType, value: str, source: Optional[str] = None) -> AssetIdentifier:
    return AssetIdentifier(id_type=id_type, value=value, source=source)


def default_remediation_bucket() -> RemediationBucket:
    return RemediationBucket.PATCH


def default_finding_status() -> FindingLifecycleStatus:
    return FindingLifecycleStatus.OPEN
