"""Policy evaluation for remediation verification evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import yaml

from models.messages_kernel import EvidenceType, RemediationBucket, RiskTier

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "verification_policy.yml"


@dataclass
class VerificationRule:
    required_sets: List[List[EvidenceType]]


@dataclass
class VerificationPolicyEntry:
    rule: VerificationRule
    window: timedelta


@lru_cache(maxsize=1)
def _load_config() -> Dict[str, object]:
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"Verification policy file not found at {_CONFIG_PATH}")
    with _CONFIG_PATH.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("Verification policy must be a mapping")
    return data


class VerificationPolicy:
    """Reads verification requirements and checks evidence coverage."""

    def __init__(self, config: Optional[Dict[str, object]] = None) -> None:
        raw = config or _load_config()
        self._policy = raw.get("policy", {})
        self._windows = raw.get("windows_hours", {})

    def get_policy(self, risk_tier: RiskTier, bucket: RemediationBucket) -> VerificationPolicyEntry:
        tier_key = risk_tier.value
        bucket_key = bucket.value
        tier_map = self._policy.get(tier_key, {})
        if not tier_map:
            tier_map = self._policy.get("default", {})
        requirement = tier_map.get(bucket_key) or tier_map.get("default")
        if not requirement:
            raise KeyError(f"No verification rule for tier={tier_key} bucket={bucket_key}")
        required_sets = [
            [EvidenceType(item) for item in group]
            for group in requirement.get("required", [])
        ]
        if not required_sets:
            raise ValueError(f"Verification rule missing required sets for tier={tier_key} bucket={bucket_key}")
        window_hours = int(self._windows.get(tier_key, self._windows.get("default", 168)))
        return VerificationPolicyEntry(rule=VerificationRule(required_sets), window=timedelta(hours=window_hours))

    def is_satisfied(
        self,
        entry: VerificationPolicyEntry,
        evidence_types: Iterable[EvidenceType],
    ) -> bool:
        evidence_set = set(evidence_types)
        for requirement in entry.rule.required_sets:
            if set(requirement).issubset(evidence_set):
                return True
        return False
