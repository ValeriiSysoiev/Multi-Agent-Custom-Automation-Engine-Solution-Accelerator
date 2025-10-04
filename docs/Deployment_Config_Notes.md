# Deployment & Configuration Notes (AI VM Backend)

## Environment Variables
Set these for the backend service (e.g., ACA/Container Apps):

| Variable | Description |
|----------|-------------|
| `COSMOSDB_ENDPOINT` | Endpoint for Cosmos DB account. |
| `COSMOSDB_DATABASE` | Database name (e.g., `ai-vm`). |
| `KEYVAULT_URI` | Vault URI for secret retrieval (required). |
| `JIRA_BASE_URL` | `https://cyberairnd.atlassian.net`. |
| `JIRA_PROJECT_KEY` | `CYB` (default). |
| `JIRA_VR_ID` | `10021` (Vulnerability Remediation issue type). |
| `JIRA_TEST_APP_NAME` | (Optional) App name for integration test AQL lookup. |
| `JIRA_TEST_HOST_NAME` | (Optional) Host name for integration test AQL lookup. |
| `QUALYS_BASE_URL` | `https://qualysapi.qg3.apps.qualys.com`. |
| `SUBSCRIPTION_ID` | Azure subscription for Defender ingestion (`66e84420-9ef4-4264-aedb-7beacbfe9e81`). |
| `DEFENDER_MODE` | `mdc` (for Defender for Cloud assessments) or future `mde`. |
| `POWERBI_WORKSPACE_ID` | `8f802077-e058-4aac-ae18-0335bbbf59ab` (reporting workspace). |
| `POWERBI_TENANT_ID` | `6059f654-466e-4240-afef-51d8d9b51a82`. |
| `POWERBI_CLIENT_ID` | `712006fa-1cbd-4f92-9fce-6f6a2ef23d42`. |

## Key Vault Secrets
Store the following secret names/values in Key Vault (referenced via managed identity):

- `JIRA-PAT` – Base64-encoded `email:PAT` string for Jira service account.
- `QUALYS-API-USER`, `QUALYS-API-PASS` – Qualys API credentials.
- `POWERBI-CLIENT-SECRET` – Service principal secret/certificate for dataset refresh.
- Additional scanner-specific secrets as needed.

## Dependencies & Lockfile
After updating `pyproject.toml` (httpx, tenacity, azure-keyvault-secrets, msal, xmltodict, lxml), regenerate the lockfile:

```bash
cd src/backend
uv lock
```

Ensure the Docker build (uv-based) picks up the new dependencies.

## Managed Identity & RBAC
- Backend Container App must have a system-assigned managed identity with:
  - Key Vault Secrets User (get/list) on `KEYVAULT_URI`.
  - Cosmos DB Data Contributor on the target Cosmos account.
  - Reader/Security Reader roles for Defender for Cloud (if using user-assigned identity, adjust accordingly).
- Qualys/Jira use service account secrets only; no Azure RBAC.

## Container App Rollback References
Keep the latest backend image reference handy for emergency rollbacks. After the 28 Sep chat deployment the active image is:

| Component | Image Tag | Digest |
|-----------|-----------|--------|
| Chat API backend | `acraivmprod.azurecr.io/macaebackend:chat-api-20250928d` | `sha256:261bbddbf142e2a43fab4e3f2febe1df0c28b3526cfdbbb024491eb75d0c2327` |
Archive earlier tags/digests in the release notes once they are safe to purge; prune inactive Container Apps revisions after each verification so only the healthy revision remains (currently `ca-aivmprodcliu3--0000005`).

## Egress Allow-List
Allow outbound to:
- `*.atlassian.net` (Jira Cloud)
- `qualysapi.*.apps.qualys.com`
- `management.azure.com` (Defender API)
- `login.microsoftonline.com` (AAD token)
- `api.powerbi.com`

## Integration Tests
- Run manually (not CI default) with real data; set env vars and ensure MI permissions.
- Artifacts saved under `artifacts/<provider>/` for verification.
