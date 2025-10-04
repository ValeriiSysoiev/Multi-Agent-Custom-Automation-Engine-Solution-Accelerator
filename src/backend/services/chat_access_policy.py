"""Row-level access policy helpers for chat responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Optional, Set

import json


@dataclass
class ChatScope:
    """Resolved access scope for a chat request."""

    applications: Set[str] = field(default_factory=set)
    owner_groups: Set[str] = field(default_factory=set)
    is_admin: bool = False


class AccessDeniedError(Exception):
    """Raised when a user has no scope to view requested data."""


class ChatAccessPolicy:
    """Resolve row-level access scopes for chat queries."""

    def __init__(
        self,
        admin_roles: Optional[Iterable[str]] = None,
        role_mapping: Optional[Mapping[str, Mapping[str, object]]] = None,
        group_mapping: Optional[Mapping[str, str]] = None,
        application_mapping: Optional[Mapping[str, Iterable[str] | str]] = None,
        default_owner_groups: Optional[Iterable[str]] = None,
    ) -> None:
        self._admin_roles = {
            role.lower()
            for role in (admin_roles or ["admin", "security_admin", "executive"])
        }
        self._role_mapping = {
            key.lower(): value for key, value in (role_mapping or {}).items()
        }
        self._group_mapping = {
            key.lower(): value for key, value in (group_mapping or {}).items()
        }
        self._application_mapping = {
            key.lower(): value for key, value in (application_mapping or {}).items()
        }
        self._default_owner_groups = set(default_owner_groups or [])

    def resolve_scope(self, user_context: Optional[Mapping[str, object]]) -> ChatScope:
        """Return the resolved scope for a given user context."""

        if not user_context:
            raise AccessDeniedError("Missing user context; cannot determine access scope")

        roles = self._normalise_values(user_context.get("roles"))
        lowered_roles = {role.lower() for role in roles}
        if lowered_roles & self._admin_roles:
            return ChatScope(is_admin=True)

        applications = self._normalise_values(user_context.get("applications"))
        owner_groups = self._normalise_values(user_context.get("owner_groups"))
        groups = self._normalise_values(user_context.get("groups"))

        scope_applications: Set[str] = set()
        scope_owner_groups: Set[str] = set()

        # Role-based mapping
        for role in lowered_roles:
            mapping = self._role_mapping.get(role)
            if not mapping:
                continue
            if self._bool_mapping_value(mapping.get("is_admin")):
                return ChatScope(is_admin=True)
            if mapping.get("applications_from_claim"):
                scope_applications.update(applications)
            mapped_apps = mapping.get("applications")
            if mapped_apps:
                scope_applications.update(self._normalise_values(mapped_apps))
            mapped_owners = mapping.get("owner_groups")
            if mapped_owners:
                scope_owner_groups.update(self._normalise_values(mapped_owners))

        # Group-based mapping
        for group in groups:
            mapped = self._group_mapping.get(group.lower())
            if mapped:
                scope_owner_groups.add(mapped)

        # Application mapping
        for app in applications:
            mapped = self._application_mapping.get(app.lower())
            if mapped:
                scope_applications.update(self._normalise_values(mapped))
            else:
                scope_applications.add(app)

        # Include owner groups explicitly specified on context
        scope_owner_groups.update(owner_groups)

        if not scope_applications:
            scope_applications.update(applications)

        if not scope_owner_groups and self._default_owner_groups:
            scope_owner_groups.update(self._default_owner_groups)

        if not scope_owner_groups and roles:
            scope_owner_groups.update(roles)

        if not scope_applications and not scope_owner_groups:
            raise AccessDeniedError("No scope assigned to the current user context")

        return ChatScope(
            applications=scope_applications,
            owner_groups=scope_owner_groups,
            is_admin=False,
        )

    @staticmethod
    def _normalise_values(value: Optional[object]) -> Set[str]:
        if not value:
            return set()
        if isinstance(value, str):
            return {value.strip()}
        if isinstance(value, Mapping):
            return {str(v).strip() for v in value.values() if str(v).strip()}
        if isinstance(value, Iterable):
            return {str(v).strip() for v in value if str(v).strip()}
        return {str(value).strip()}

    @staticmethod
    def _bool_mapping_value(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes", "on"}
        return False

    @classmethod
    def from_config_file(cls, path: Path) -> "ChatAccessPolicy":
        if not path.exists():
            raise FileNotFoundError(f"Chat access policy config not found at {path}")
        with path.open("r", encoding="utf-8") as handle:
            config = json.load(handle)

        return cls(
            admin_roles=config.get("admin_roles"),
            role_mapping=config.get("role_mapping"),
            group_mapping=config.get("group_mapping"),
            application_mapping=config.get("application_mapping"),
            default_owner_groups=config.get("default_owner_groups"),
        )


__all__ = ["ChatAccessPolicy", "ChatScope", "AccessDeniedError"]
