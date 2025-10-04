import os
import sys

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pytest

from services.chat_access_policy import AccessDeniedError, ChatAccessPolicy


def test_admin_role_all_access():
    policy = ChatAccessPolicy(admin_roles=["admin"])
    scope = policy.resolve_scope({"roles": ["Admin"]})
    assert scope.is_admin
    assert scope.applications == set()


def test_scope_from_applications():
    policy = ChatAccessPolicy()
    scope = policy.resolve_scope({"applications": ["Customer Web", "Billing"]})
    assert not scope.is_admin
    assert scope.applications == {"Customer Web", "Billing"}


def test_scope_requires_data():
    policy = ChatAccessPolicy()
    with pytest.raises(AccessDeniedError):
        policy.resolve_scope({"roles": []})


def test_roles_used_as_owner_groups():
    policy = ChatAccessPolicy()
    scope = policy.resolve_scope({"roles": ["platform-ops"]})
    assert not scope.is_admin
    assert scope.owner_groups == {"platform-ops"}


def test_missing_context_denied():
    policy = ChatAccessPolicy()
    with pytest.raises(AccessDeniedError):
        policy.resolve_scope(None)


def test_role_mapping_applications_from_claim():
    policy = ChatAccessPolicy(
        role_mapping={
            "app.owner": {"applications_from_claim": True}
        }
    )
    scope = policy.resolve_scope({"roles": ["app.owner"], "applications": ["payments"]})
    assert scope.applications == {"payments"}


def test_group_mapping_applied():
    policy = ChatAccessPolicy(
        group_mapping={"group-1": "Payments Platform"}
    )
    scope = policy.resolve_scope({"groups": ["group-1"]})
    assert scope.owner_groups == {"Payments Platform"}


def test_from_config_file(tmp_path):
    config_path = tmp_path / "chat_scope.json"
    config_path.write_text(
        """
{
  "admin_roles": ["security.admin"],
  "role_mapping": {
    "platform.ops": {"owner_groups": ["Platform Operations"]}
  }
}
        """,
        encoding="utf-8",
    )

    policy = ChatAccessPolicy.from_config_file(config_path)
    scope = policy.resolve_scope({"roles": ["platform.ops"]})
    assert scope.owner_groups == {"Platform Operations"}
