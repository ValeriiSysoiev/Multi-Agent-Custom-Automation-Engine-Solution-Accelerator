"""Utilities for interpreting remediation SLA configuration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from models.messages_kernel import RemediationBucket, RiskTier

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "remediation_sla.yml"


@dataclass
class RemediationSLA:
    ack: timedelta
    due: timedelta
    verify: timedelta
    emergency_ok: bool = False


@lru_cache(maxsize=1)
def _load_config() -> Dict[str, Any]:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"Remediation SLA config not found at {_CONFIG_PATH}")
    with _CONFIG_PATH.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Remediation SLA config must be a mapping")
    return payload


class RemediationPolicy:
    """Reads SLA definitions and exposes lookup helpers."""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self._raw = config or _load_config()
        self._sla = self._raw.get("sla", {})

    def get_sla(
        self,
        bucket: RemediationBucket,
        risk_tier: RiskTier,
        environment: Optional[str],
    ) -> RemediationSLA:
        bucket_key = bucket.value.lower()
        tier_key = risk_tier.value
        tier_map = self._sla.get(bucket_key, {})
        env_key = self._normalize_environment(environment)

        entry = self._resolve_entry(tier_map, tier_key, env_key)
        if entry is None:
            raise KeyError(
                f"No SLA entry for bucket={bucket_key}, tier={tier_key}, environment={env_key}"
            )

        ack = timedelta(hours=int(entry.get("ack_hours", 0)))
        due = timedelta(hours=int(entry.get("due_hours", 0)))
        verify = timedelta(hours=int(entry.get("verify_hours", 0)))
        emergency = bool(entry.get("emergency_ok", False))
        return RemediationSLA(ack=ack, due=due, verify=verify, emergency_ok=emergency)

    def _resolve_entry(
        self,
        tier_map: Dict[str, Any],
        tier_key: str,
        env_key: str,
    ) -> Optional[Dict[str, Any]]:
        # Prefer exact tier
        if tier_key not in tier_map:
            return self._fallback_by_tier(tier_map, tier_key)
        env_map = tier_map[tier_key] or {}
        return self._env_lookup(env_map, env_key)

    def _fallback_by_tier(
        self,
        tier_map: Dict[str, Any],
        tier_key: str,
    ) -> Optional[Dict[str, Any]]:
        order = [RiskTier.CRITICAL.value, RiskTier.HIGH.value, RiskTier.MEDIUM.value, RiskTier.LOW.value, RiskTier.VERY_LOW.value]
        if tier_key not in order:
            order.insert(0, tier_key)
        for key in order:
            if key in tier_map:
                return self._env_lookup(tier_map[key], "default")
        if "default" in tier_map:
            return self._env_lookup(tier_map["default"], "default")
        return None

    def _env_lookup(self, env_map: Dict[str, Any], env_key: str) -> Optional[Dict[str, Any]]:
        if env_key in env_map:
            return env_map[env_key]
        if "default" in env_map:
            return env_map["default"]
        return None

    def _normalize_environment(self, environment: Optional[str]) -> str:
        if not environment:
            return "default"
        value = environment.strip().lower()
        mapping = {
            "prod": "prod",
            "production": "prod",
            "uat": "uat",
            "stage": "uat",
            "staging": "uat",
            "dev": "dev",
            "development": "dev",
            "test": "dev",
            "shared": "default",
            "non-prod": "uat",
        }
        return mapping.get(value, "default")


__all__ = ["RemediationPolicy", "RemediationSLA"]
