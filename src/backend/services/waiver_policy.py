"""Policy helpers enforcing waiver control and approval rules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Tuple

import yaml

from models.messages_kernel import CompensatingControl, RiskTier

_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "waiver_policy.yml"


@dataclass
class ControlRequirement:
    min_controls: int
    strong_types: Set[str]


@dataclass
class ApprovalRequirement:
    required_roles: List[str]


class WaiverPolicy:
    """Loads waiver policy and evaluates requests/approvals."""

    def __init__(self, config: Optional[Dict[str, object]] = None) -> None:
        raw = config or self._load_config()
        self._controls = self._parse_controls(raw.get("control_requirements", {}))
        self._approvals = self._parse_approvals(raw.get("approval_matrix", {}))

    def validate_controls(
        self,
        risk_tier: RiskTier,
        controls: Iterable[CompensatingControl],
    ) -> Tuple[bool, Optional[str]]:
        tier_key = self._tier_key(risk_tier)
        requirement = self._controls.get(tier_key)
        if not requirement:
            return True, None

        normalized_controls = [
            (control.control_type or "").strip().lower()
            for control in controls
        ]
        total_controls = len([name for name in normalized_controls if name])
        if total_controls < requirement.min_controls:
            return (
                False,
                f"Risk tier {tier_key} requires at least {requirement.min_controls} compensating controls; "
                f"only {total_controls} provided.",
            )

        if requirement.strong_types:
            strong_matches = {
                ctrl for ctrl in normalized_controls if ctrl in requirement.strong_types
            }
            if len(strong_matches) < requirement.min_controls:
                needed = ", ".join(sorted(requirement.strong_types))
                return (
                False,
                f"Risk tier {tier_key} controls must include at least {requirement.min_controls} strong types "
                    f"({needed}); received {', '.join(sorted(strong_matches)) or 'none' }.",
                )

        return True, None

    def validate_role(self, risk_tier: RiskTier, role: str) -> Tuple[bool, Optional[str]]:
        tier_key = self._tier_key(risk_tier)
        requirement = self._approvals.get(tier_key)
        if not requirement:
            return True, None
        normalized = role.strip().lower()
        if normalized not in requirement.required_roles:
            allowed = ", ".join(requirement.required_roles)
            return (
                False,
                f"Role '{role}' is not permitted to approve {tier_key} waivers. Allowed roles: {allowed}.",
            )
        return True, None

    def is_fully_approved(self, risk_tier: RiskTier, roles: Iterable[str]) -> bool:
        tier_key = self._tier_key(risk_tier)
        requirement = self._approvals.get(tier_key)
        if not requirement:
            return True
        provided = {role.strip().lower() for role in roles}
        return all(role in provided for role in requirement.required_roles)

    def pending_roles(self, risk_tier: RiskTier, roles: Iterable[str]) -> List[str]:
        tier_key = self._tier_key(risk_tier)
        requirement = self._approvals.get(tier_key)
        if not requirement:
            return []
        provided = {role.strip().lower() for role in roles}
        return [role for role in requirement.required_roles if role not in provided]

    @staticmethod
    def _load_config() -> Dict[str, object]:
        if not _CONFIG_PATH.exists():
            raise FileNotFoundError(f"Waiver policy file not found at {_CONFIG_PATH}")
        with _CONFIG_PATH.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
        if not isinstance(data, dict):
            raise ValueError("Waiver policy must be a mapping")
        return data

    @staticmethod
    def _parse_controls(raw: Dict[str, object]) -> Dict[str, ControlRequirement]:
        requirements: Dict[str, ControlRequirement] = {}
        for tier, values in raw.items():
            if not isinstance(values, dict):
                continue
            min_controls = int(values.get("min_controls", 0))
            strong = values.get("strong_types", [])
            strong_set = {item.strip().lower() for item in strong if isinstance(item, str)}
            requirements[tier] = ControlRequirement(min_controls=min_controls, strong_types=strong_set)
        return requirements

    @staticmethod
    def _parse_approvals(raw: Dict[str, object]) -> Dict[str, ApprovalRequirement]:
        matrix: Dict[str, ApprovalRequirement] = {}
        for tier, values in raw.items():
            if not isinstance(values, dict):
                continue
            roles = [role.strip().lower() for role in values.get("required_roles", []) if isinstance(role, str)]
            matrix[tier] = ApprovalRequirement(required_roles=roles)
        return matrix

    @staticmethod
    def _tier_key(risk_tier: RiskTier | str) -> str:
        if isinstance(risk_tier, RiskTier):
            return risk_tier.value
        return str(risk_tier).strip().lower()


__all__ = ["WaiverPolicy"]
