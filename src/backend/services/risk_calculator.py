"""Risk scoring utilities derived from the IS Risk Management Methodology."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import yaml

from models.messages_kernel import (
    ApplicationContext,
    CanonicalFinding,
    EnrichmentRecord,
    ExposureSurface,
    ResidualRisk,
    RiskTier,
    TreatmentRecommendation,
)

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "risk_methodology.yml"


@dataclass
class LikelihoodResult:
    value: int
    reasons: List[str]


@dataclass
class ImpactResult:
    value: int
    reasons: List[str]


@dataclass
class UnacceptableOutcome:
    condition_id: str
    description: str
    enforced_tier: RiskTier


@dataclass
class RiskComputation:
    likelihood: LikelihoodResult
    impact: ImpactResult
    risk_score: int
    risk_tier: RiskTier
    unacceptable_conditions: List[UnacceptableOutcome]
    recommended_treatment: TreatmentRecommendation


@lru_cache(maxsize=1)
def _load_config() -> Dict[str, object]:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"Risk methodology configuration not found at {_CONFIG_PATH}")
    with _CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
        if not isinstance(data, dict):
            raise ValueError("Risk methodology configuration must be a mapping")
        return data


def _normalize_key(value: Optional[str]) -> str:
    return (value or "").strip().lower()


class RiskCalculator:
    """Encapsulates deterministic risk calculations for triage."""

    def __init__(self, config: Optional[Dict[str, object]] = None) -> None:
        self._config = config or _load_config()
        self._likelihood = self._config.get("likelihood", {})
        self._impact = self._config.get("impact", {})
        self._unacceptable = self._config.get("unacceptable_conditions", [])
        self._thresholds = self._config.get("risk_score_thresholds", [])
        self._treatment_defaults = self._config.get("treatment_defaults", {})

    def compute(self, finding: CanonicalFinding, enrichment: EnrichmentRecord) -> RiskComputation:
        likelihood = self._compute_likelihood(finding, enrichment)
        impact = self._compute_impact(enrichment.application_context, enrichment.exposure)
        score = max(1, likelihood.value) * max(1, impact.value)
        tier = self._score_to_tier(score)
        unacceptable = self._evaluate_unacceptable_conditions(finding, enrichment)

        for outcome in unacceptable:
            tier = self._apply_risk_floor(tier, outcome.enforced_tier)
            score = max(score, self._tier_min_score(outcome.enforced_tier))

        recommended = self._treatment_for_tier(tier)

        return RiskComputation(
            likelihood=likelihood,
            impact=impact,
            risk_score=score,
            risk_tier=tier,
            unacceptable_conditions=unacceptable,
            recommended_treatment=recommended,
        )

    # ------------------------------------------------------------------
    # Likelihood
    # ------------------------------------------------------------------
    def _compute_likelihood(self, finding: CanonicalFinding, enrichment: EnrichmentRecord) -> LikelihoodResult:
        reasons: List[str] = []
        base = self._likelihood_base_from_severity(finding.severity, finding.risk_tier)
        reasons.append(f"Base likelihood {base} from severity '{finding.severity or finding.risk_tier.value}'")

        base = self._adjust_for_exposure(base, enrichment.exposure, reasons)
        base = self._adjust_for_controls(base, enrichment.exposure, reasons)
        base = self._adjust_for_threat_signals(base, enrichment, reasons)

        base = max(1, min(5, base))
        return LikelihoodResult(value=base, reasons=reasons)

    def _likelihood_base_from_severity(self, severity: Optional[str], fallback_tier: RiskTier) -> int:
        severity_map = self._likelihood.get("base_severity_map", {})
        if severity:
            key = severity.lower()
            if key in severity_map:
                return int(severity_map[key])
        tier_map = {
            RiskTier.CRITICAL: 5,
            RiskTier.HIGH: 4,
            RiskTier.MEDIUM: 3,
            RiskTier.LOW: 2,
            RiskTier.VERY_LOW: 1,
        }
        return tier_map.get(fallback_tier, 3)

    def _adjust_for_exposure(self, base: int, exposure: ExposureSurface, reasons: List[str]) -> int:
        modifiers = self._likelihood.get("exposure_modifiers", {})
        if exposure.internet_facing:
            base = self._apply_modifier(base, modifiers.get("internet_facing"), reasons, "Internet-facing asset")
        else:
            base = self._apply_modifier(base, modifiers.get("internal_only"), reasons, "Internal-only exposure")

        if exposure.authentication_required is False:
            base = self._apply_modifier(
                base,
                modifiers.get("no_authentication"),
                reasons,
                "Service lacks authentication",
            )

        segment = _normalize_key(exposure.network_segment)
        if segment:
            sensitive = {"dmz", "perimeter", "edge", "external"}
            if any(keyword in segment for keyword in sensitive):
                base = self._apply_modifier(
                    base,
                    modifiers.get("sensitive_network_segment"),
                    reasons,
                    f"Network segment '{exposure.network_segment}'",
                )
        return base

    def _adjust_for_controls(self, base: int, exposure: ExposureSurface, reasons: List[str]) -> int:
        modifiers = self._likelihood.get("control_modifiers", {})
        for control, enabled in (exposure.control_coverage or {}).items():
            if not enabled:
                continue
            modifier = modifiers.get(control)
            if modifier is None:
                continue
            base = self._apply_modifier(base, modifier, reasons, f"Control '{control}' coverage")
        return base

    def _adjust_for_threat_signals(self, base: int, enrichment: EnrichmentRecord, reasons: List[str]) -> int:
        weights = self._likelihood.get("threat_signal_weights", {})
        epss_thresholds = self._likelihood.get("epss_thresholds", {})
        for signal in enrichment.threat_signals:
            signal_type = _normalize_key(signal.signal_type)
            weight = None
            if signal_type in weights:
                weight = weights[signal_type]
            elif "known_exploited" in signal_type:
                weight = weights.get("known_exploited")
            elif "malware" in signal_type or "ransom" in signal_type:
                weight = weights.get("active_malware")

            details = signal.details or {}
            if signal_type == "exploit_probability":
                score = details.get("score") or details.get("epss")
                if isinstance(score, (float, int)):
                    if score >= float(epss_thresholds.get("high", 0.9)):
                        weight = max(weight or 0, 2)
                        reasons.append(f"EPSS score {score:.2f} ≥ high threshold")
                    elif score >= float(epss_thresholds.get("medium", 0.5)):
                        weight = max(weight or 0, 1)
                        reasons.append(f"EPSS score {score:.2f} ≥ medium threshold")
            if weight:
                base = self._apply_modifier(base, weight, reasons, f"Threat signal {signal.source}:{signal.signal_type}")
            elif signal_type == "vulnerability_intel":
                exploitation = _normalize_key(str(details.get("exploitation")))
                if exploitation == "active":
                    base = self._apply_modifier(base, 2, reasons, "Defender TI reports active exploitation")
                elif exploitation in {"exploited", "likely"}:
                    base = self._apply_modifier(base, 1, reasons, "Defender TI indicates elevated exploitation")
        return base

    def _apply_modifier(self, base: int, modifier: Optional[float], reasons: List[str], reason: str) -> int:
        if modifier is None or math.isclose(modifier, 0):
            return base
        new_value = base + int(modifier)
        reasons.append(f"{reason}: {'+' if modifier > 0 else ''}{int(modifier)}")
        return new_value

    # ------------------------------------------------------------------
    # Impact
    # ------------------------------------------------------------------
    def _compute_impact(self, context: ApplicationContext, exposure: ExposureSurface) -> ImpactResult:
        reasons: List[str] = []
        base = self._impact_from_criticality(context, reasons)
        base = self._adjust_for_environment(base, context, reasons)
        base = self._adjust_for_data_classification(base, context, reasons)
        base = self._adjust_for_crown_jewel(base, context, reasons)
        base = self._adjust_for_internet_exposure(base, exposure, reasons)
        base = max(1, min(5, base))
        return ImpactResult(value=base, reasons=reasons)

    def _impact_from_criticality(self, context: ApplicationContext, reasons: List[str]) -> int:
        criticality_map = self._impact.get("criticality_map", {})
        criticality_key = _normalize_key(context.criticality)
        if criticality_key in criticality_map:
            value = int(criticality_map[criticality_key])
            reasons.append(f"Base impact {value} from criticality '{context.criticality}'")
            return value
        value = int(criticality_map.get("unknown", 3))
        reasons.append("Base impact 3 from unknown criticality")
        return value

    def _adjust_for_environment(self, base: int, context: ApplicationContext, reasons: List[str]) -> int:
        env_adjust = self._impact.get("environment_adjustment", {})
        key = _normalize_key(context.environment)
        if not key:
            return base
        modifier = env_adjust.get(key)
        if modifier is None:
            return base
        return self._apply_modifier(base, modifier, reasons, f"Environment '{context.environment}'")

    def _adjust_for_data_classification(self, base: int, context: ApplicationContext, reasons: List[str]) -> int:
        weights = self._impact.get("data_classification_weights", {})
        tags = context.tags or {}
        for value in tags.values():
            if not isinstance(value, str):
                continue
            key = _normalize_key(value)
            for candidate, weight in weights.items():
                if candidate in key:
                    base = max(base, int(weight))
                    reasons.append(f"Data classification '{value}' sets impact ≥ {int(weight)}")
        return base

    def _adjust_for_crown_jewel(self, base: int, context: ApplicationContext, reasons: List[str]) -> int:
        crown_tags = self._impact.get("crown_jewel_tags", [])
        text_candidates = [context.application, context.business_service]
        text_candidates.extend(v for v in (context.tags or {}).values() if isinstance(v, str))
        for value in filter(None, text_candidates):
            key = _normalize_key(value)
            if any(tag in key for tag in crown_tags):
                if base < 5:
                    reasons.append(f"Crown jewel context '{value}' elevates impact to 5")
                return max(base, 5)
        return base

    def _adjust_for_internet_exposure(self, base: int, exposure: ExposureSurface, reasons: List[str]) -> int:
        if exposure.internet_facing:
            return self._apply_modifier(base, 1, reasons, "Internet-facing asset increases blast radius")
        return base

    # ------------------------------------------------------------------
    # Unacceptable conditions
    # ------------------------------------------------------------------
    def _evaluate_unacceptable_conditions(
        self,
        finding: CanonicalFinding,
        enrichment: EnrichmentRecord,
    ) -> List[UnacceptableOutcome]:
        outcomes: List[UnacceptableOutcome] = []
        for item in self._unacceptable:
            condition_id = item.get("id")
            desc = item.get("description", "")
            floor = self._parse_risk_tier(item.get("risk_floor"))
            if not condition_id or floor is None:
                continue
            if self._condition_applies(condition_id, finding, enrichment):
                outcomes.append(
                    UnacceptableOutcome(
                        condition_id=condition_id,
                        description=desc,
                        enforced_tier=floor,
                    )
                )
        return outcomes

    def _condition_applies(
        self,
        condition_id: str,
        finding: CanonicalFinding,
        enrichment: EnrichmentRecord,
    ) -> bool:
        context = enrichment.application_context
        exposure = enrichment.exposure
        condition_id = condition_id.lower()

        if condition_id == "outage_gt_24h":
            return self._is_high_availability_asset(context) and _normalize_key(context.environment) in {"prod", "production"}
        if condition_id == "large_data_breach":
            return self._is_sensitive_data_asset(context)
        if condition_id == "regulatory_non_compliance":
            return self._is_sensitive_data_asset(context) or self._has_regulatory_tag(context)
        if condition_id == "trust_impact":
            return self._matches_trust_keywords(context) or exposure.internet_facing and self._is_customer_service(context)
        if condition_id == "active_exploitation_crown_jewel":
            return (
                self._has_active_exploitation(enrichment)
                and exposure.internet_facing
                and self._is_crown_jewel_asset(context)
            )
        return False

    def _is_high_availability_asset(self, context: ApplicationContext) -> bool:
        crit = _normalize_key(context.criticality)
        return crit in {"tier0", "tier1", "mission critical", "crown jewel"}

    def _is_sensitive_data_asset(self, context: ApplicationContext) -> bool:
        tags = context.tags or {}
        tag_values = [context.application, context.business_service]
        tag_values.extend(v for v in tags.values() if isinstance(v, str))
        combined = " ".join(filter(None, tag_values)).lower()
        keywords = {"pii", "phi", "pci", "payment", "customer data", "sensitive", "regulated"}
        return any(keyword in combined for keyword in keywords)

    def _has_regulatory_tag(self, context: ApplicationContext) -> bool:
        tags = context.tags or {}
        for value in tags.values():
            if isinstance(value, str) and any(k in value.lower() for k in ("regulatory", "sox", "pci", "hipaa", "gdpr")):
                return True
        return False

    def _matches_trust_keywords(self, context: ApplicationContext) -> bool:
        keywords = {"payments", "checkout", "login", "identity", "customer", "storefront", "loyalty"}
        for value in filter(None, [context.application, context.business_service]):
            key = value.lower()
            if any(word in key for word in keywords):
                return True
        for value in (context.tags or {}).values():
            if isinstance(value, str) and any(word in value.lower() for word in keywords):
                return True
        return False

    def _is_customer_service(self, context: ApplicationContext) -> bool:
        for value in filter(None, [context.application, context.business_service]):
            key = value.lower()
            if any(keyword in key for keyword in ("customer", "user", "client")):
                return True
        return False

    def _is_crown_jewel_asset(self, context: ApplicationContext) -> bool:
        tags = context.tags or {}
        candidates = [context.application, context.business_service]
        candidates.extend(v for v in tags.values() if isinstance(v, str))
        crown_tags = self._impact.get("crown_jewel_tags", [])
        for value in filter(None, candidates):
            key = _normalize_key(value)
            if any(tag in key for tag in crown_tags):
                return True
        return False

    def _has_active_exploitation(self, enrichment: EnrichmentRecord) -> bool:
        for signal in enrichment.threat_signals:
            signal_type = _normalize_key(signal.signal_type)
            if "known_exploited" in signal_type or "kev" in signal_type:
                return True
            if signal_type in {"defender_alert", "active_malware"}:
                return True
            if signal_type == "exploit_probability":
                details = signal.details or {}
                score = details.get("score") or details.get("epss")
                try:
                    score_val = float(score)
                except (TypeError, ValueError):
                    continue
                if score_val >= float(self._likelihood.get("epss_thresholds", {}).get("high", 0.9)):
                    return True
        return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _apply_risk_floor(self, current: RiskTier, floor: RiskTier) -> RiskTier:
        order = {
            RiskTier.VERY_LOW: 0,
            RiskTier.LOW: 1,
            RiskTier.MEDIUM: 2,
            RiskTier.HIGH: 3,
            RiskTier.CRITICAL: 4,
        }
        return current if order[current] >= order[floor] else floor

    def _tier_min_score(self, tier: RiskTier) -> int:
        mapping = {
            RiskTier.CRITICAL: 20,
            RiskTier.HIGH: 12,
            RiskTier.MEDIUM: 5,
            RiskTier.LOW: 3,
            RiskTier.VERY_LOW: 1,
        }
        return mapping[tier]

    def _score_to_tier(self, score: int) -> RiskTier:
        thresholds = sorted(self._thresholds, key=lambda item: item.get("min_score", 0), reverse=True)
        for entry in thresholds:
            min_score = int(entry.get("min_score", 0))
            tier = self._parse_risk_tier(entry.get("tier"))
            if tier and score >= min_score:
                return tier
        return RiskTier.VERY_LOW

    def _parse_risk_tier(self, value: Optional[str]) -> Optional[RiskTier]:
        if not value:
            return None
        lookup = {
            "critical": RiskTier.CRITICAL,
            "high": RiskTier.HIGH,
            "medium": RiskTier.MEDIUM,
            "low": RiskTier.LOW,
            "very_low": RiskTier.VERY_LOW,
            "very low": RiskTier.VERY_LOW,
        }
        return lookup.get(value.lower())

    def _treatment_for_tier(self, tier: RiskTier) -> TreatmentRecommendation:
        value = self._treatment_defaults.get(tier.value) or self._treatment_defaults.get(tier.value.replace("_", ""))
        if not value:
            return TreatmentRecommendation.MITIGATE
        mapping = {
            "mitigate": TreatmentRecommendation.MITIGATE,
            "accept": TreatmentRecommendation.ACCEPT,
            "transfer": TreatmentRecommendation.TRANSFER,
            "avoid": TreatmentRecommendation.AVOID,
        }
        return mapping.get(value.lower(), TreatmentRecommendation.MITIGATE)

    def serialize(self) -> str:
        """Return current configuration as a JSON string (for diagnostics)."""
        return json.dumps(self._config, indent=2)


def default_residual_risk(tier: RiskTier) -> ResidualRisk:
    """Create a residual risk shell aligned with methodology defaults for downstream use."""
    return ResidualRisk(
        risk_tier=tier,
        rationale="Residual risk to be recalculated after remediation evidence is verified.",
    )
