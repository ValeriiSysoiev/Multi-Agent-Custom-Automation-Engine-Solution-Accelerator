# AI VM Transformation – Lessons Learned

These notes capture the friction points we hit while converting the accelerator from the legacy HR/Marketing demo to the AI Vulnerability Management (AI VM) workflow. Future teams can use this as a checklist before embarking on similar refactors.

## 1. Inventory Existing Test Stubs First
- The accelerator ships with tests that pre-stub whole modules (e.g., `models.messages_kernel`, `helpers.azure_credential_utils`). Removing or renaming agents without updating those stubs results in hard-to-debug `ImportError`/`AttributeError` failures.
- **Action:** Before refactoring, list the tests that install shims. Update or delete them as part of the same PR that changes the agents so runtime code and harness stay aligned.

## 2. Treat Azure Dependencies as First‑Class Requirements
- The new VM agents rely on Cosmos DB, Key Vault, Azure Identity, Defender, Qualys, Power BI, etc. Tests and local runs must either install the SDKs or supply faithful mocks; otherwise every import crashes.
- **Action:** Document the “minimum Azure SDK set” (`azure-identity`, `azure-cosmos`, `azure-keyvault-secrets`, `azure-monitor-opentelemetry`, `azure-core`, etc.) in `requirements-test.txt` or the README. Provide uv/install instructions for contributors and CI.

## 3. Planner & UI Are Tightly Coupled to Agent Names
- Planner prompts, quick-task cards, and tests all referenced `Hr_Agent`, `Marketing_Agent`, etc. Replacing agents without touching the UI left the planner unusable.
- **Action:** Update instructions, quick-task metadata, and planner tests in lockstep with any agent change. Draft a UI/Planner checklist covering prompts, tool docs, and front-end copy.

## 4. Integration vs Stubbed Tests – Decide Early
- Some suites mocked every dependency; others assumed live services. Once we installed the real SDKs, the stubs masked true behaviour (and vice versa).
- **Action:** Classify each test as integration or unit. For integration tests, use recorded fixtures or require explicit credentials (and document the expectation). For unit tests, provide maintainable helpers rather than ad-hoc stubs inside each test file.

## 5. Smoke Tests After Major Refactors
- The deployed Risk Chat never regressed, but manual confidence checks (`curl /api/chat`, load `/chat` in the App Service) caught issues faster than waiting for CI.
- **Action:** Add a “Smoke Test” section to the runbook: execute `/api/chat`, confirm the React shell loads, and capture the run_id. Run this whenever agents/planner/infra change.

## 6. Document External Config Early
- Every agent needs environment variables (Qualys/Jira credentials, Cosmos endpoints, Power BI IDs). Missing secrets caused repeated restarts during testing.
- **Action:** Maintain an up-to-date configuration checklist (Key Vault secrets, Env vars, role assignments) in `docs/Deployment_Config_Notes.md` and refer to it in every transformation plan.

## 7. Scope of Planner Changes
- Swapping from HR to VM agents introduced several new classes (`DeduplicationAgent`, `EnrichmentAgent`, `WaiverAgent`, `ReportingAgent`) that had no tests. Bringing them into the planner exposed missing tool docs and plan prompts.
- **Action:** Whenever new agents are introduced, provide tool documentation alongside planner instructions and create at least one smoke test for the planner flow.

## 8. Managed Identity and Key Vault Access in Production
- **Critical Issue:** All agents worked perfectly in local testing but failed in production with 404 errors accessing Key Vault secrets (QUALYS-API-USER, JIRA-PAT, POWERBI-CLIENT-SECRET).
- **Root Cause:** The authentication differs between dev and prod:
  - Dev (`APP_ENV=dev`): Uses `DefaultAzureCredential` which includes Azure CLI credentials from developer's `az login`
  - Prod (`APP_ENV=prod` or unset): Uses `ManagedIdentityCredential` ONLY, which requires explicit configuration
- **What Was Missing:**
  1. No `AZURE_CLIENT_ID` environment variable set in Container App
  2. Managed identity had no Key Vault access permissions (RBAC role assignment missing)
- **Solution:**
  ```bash
  # 1. Add AZURE_CLIENT_ID to Container App
  az containerapp update --name <app-name> --resource-group <rg> \
    --set-env-vars "AZURE_CLIENT_ID=<managed-identity-client-id>"

  # 2. Grant Key Vault access (for RBAC-enabled vaults)
  az role assignment create --role "Key Vault Secrets User" \
    --assignee <identity-principal-id> --scope <vault-resource-id>

  # 3. Restart Container App
  az containerapp revision restart --name <app-name> --resource-group <rg>
  ```
- **Action:**
  - Always explicitly configure `AZURE_CLIENT_ID` for user-assigned managed identities
  - Test with production authentication locally: set `APP_ENV=prod` and use `az login --identity`
  - Document all Key Vault secrets with exact names (respect hyphen vs underscore conventions)
  - Verify BOTH identity assignment AND permission grants before deployment
  - This single fix resolves access for ALL agents in the Container App

Capturing these lessons ensures future transformations happen deliberately, with SDK dependencies, planner/UI alignment, authentication configuration, and tests all considered up front.
