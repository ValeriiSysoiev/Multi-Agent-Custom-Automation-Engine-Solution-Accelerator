# Chat Agent Row-Level Security & Scope Mapping

## Purpose
Define how user context from Azure EasyAuth (or equivalent) is translated into the scope filters consumed by `ChatAccessPolicy`, and describe fallback behaviour, logging, and audit controls. This policy applies to both planner-driven chat tasks and the direct `/api/chat` endpoint.

## Scope Inputs
`auth_utils.get_authenticated_user_details` produces the following collections:
- `user_roles`: array of role strings (e.g., `Security.Admin`, `PlatformOps`)
- `groups`: extracted from JWT/EasyAuth claims (team identifiers, distribution lists)
- `applications`: extracted from claims or custom headers (application IDs/names)
- Future extension: `owner_groups`, `business_units`, etc., when the identity provider exposes them.

## Normalization Rules
1. Lowercase all values; trim whitespace.
2. Treat `user_roles` as platform-level assignments; normalize known roles into canonical names:
   - `security.admin`, `ciso`, `security_lead` → `Security.Admin`
   - `platformops`, `infrastructure`, `cloud_ops` → `Platform.Ops`
   - `application_owner`, `app_owner` → `App.Owner`
3. Map `applications` claim values to canonical application identifiers using the CMDB lookup table (see below).
4. `groups` values map to owner teams (e.g., Jira group ID, Azure AD group). Use `GroupMapping` for canonical owner names.

## Mapping Tables
Maintain the following JSON configuration in Key Vault (referenced through AppConfig) or the local fallback file `src/backend/config/chat_scope_mapping.json` (used in development/tests):

### `chat_rls_role_mapping.json`
```json
{
  "security.admin": { "type": "role", "scope": { "is_admin": true } },
  "ciso": { "type": "role", "scope": { "is_admin": true } },
  "platform.ops": { "type": "role", "scope": { "owner_groups": ["Platform Operations"] } },
  "app.owner": { "type": "role", "scope": { "applications": "__from_claim__" } }
}
```

### `chat_rls_group_mapping.json`
```json
{
  "91b4f...": "Payments Platform",
  "a83c1...": "Digital Banking",
  "e4fd2...": "Retail Stores"
}
```

### `chat_rls_application_mapping.json`
```json
{
  "payments_app": "Payments Platform",
  "crm": "Customer Relationship Management",
  "digitalbanking": "Digital Banking"
}
```

## Evaluation Algorithm
1. Load mappings at application startup and cache (invalidate every 15 minutes).
2. Normalize context values (lowercase, strip, deduplicate).
3. Initialize empty scope.
4. For each `user_role`:
   - If role exists in `role_mapping` and `is_admin` is true, return `ChatScope(is_admin=True)`.
   - Otherwise merge mapped `applications` or `owner_groups` into scope.
5. For each `group` claim:
   - If group ID appears in `chat_rls_group_mapping`, add mapped owner group to scope.
6. For each `applications` claim:
   - If claim maps to canonical application(s), add to scope.
7. If scope remains empty after role/group/application mapping:
   - Option A (default): raise `AccessDeniedError("No scope assigned")`.
   - Option B (configurable): apply fallback `default_owner_group` or require manual Linkage Review.

## Audit & Logging
- Log each `resolve_scope` evaluation at INFO with correlation ID and scope summary (excluding raw IDs).
- Log AccessDenied events at WARN.
- Store final scope struct in run events (`metrics.scope`).

## Governance
- Security team owns the JSON mappings; change control via Key Vault secret versioning.
- Review mapping tables quarterly and after major organizational changes.
- Document requests for new role/application mappings; treat as access control change.

## Future Enhancements
- Integrate Azure AD Graph/Entra ID to resolve application ownership dynamically.
- Support attribute-based controls (e.g., `data_classification`, `business_unit`).
- Add self-service scope viewer for auditors.
