# Frontend Deployment TODO List

## Objective
Deploy the refreshed Risk Chat UI (tag `acraivmprod.azurecr.io/macaefrontend:chat-ui-20251002a`) alongside backend tag `acraivmprod.azurecr.io/macaebackend:chat-api-20251002b`.

## Tasks
- [x] Redeploy `aivm-reporting-job` with push dataset backfill and confirm the manual validation run succeeds. *(Initial revert to `b03fe872-7cdc-4895-9792-218e1b00da4e` exposed missing tables; replaced with `de1a1867-5e8a-40c3-8587-ed7912d33609` and validated via run `aivm-reporting-job-rrelxkh`.)*
- [x] Pull `aivm-reporting-job-mqew4xq` console output from `ContainerAppConsoleLogs_CL`, log RunId/metrics, address the failure, and rerun until export succeeds. *Dataset recreated as `de1a1867-5e8a-40c3-8587-ed7912d33609`; run `aivm-reporting-job-rrelxkh` (correlation `dc6053f2-9c63-4029-ab55-6d5ee5a13c1d`) completed with `pbi_rows_*` metrics.*
- [ ] Confirm local workspace is up to date and review pending changes relevant to the frontend UI deployment.
- [x] Build the React bundle (`npm install`, `npm run build`).
- [x] Authenticate to ACR (`az acr login --name acraivmprod`).
- [x] Build the container image `acraivmprod.azurecr.io/macaefrontend:chat-ui-20251002a` (linux/amd64 via `docker buildx`).
- [x] Push the image to ACR.
- [x] Update the frontend App Service container image to the new tag. *(Now running `chat-ui-20251002a`, built for linux/amd64 with updated planner copy/icons.)*
- [x] Smoke-test `/chat` in the deployed environment (UI render, session reset, inline toasts, navigation links).
- [x] Verify telemetry ingestion (Cosmos `runs_events`, Log Analytics custom tables).
- [x] Investigate backend 500 response from `/api/input_task` (ChatAgent definition regression).
- [x] Rebuild/push backend image with chat/planner fixes and update Container App to new tag (`chat-api-20251002e`).
- [x] Re-run `/api/chat` + `/api/input_task` validation post-redeploy; confirm telemetry (Cosmos `runs_events`, Log Analytics/App Insights`).
- [x] Diagnose 503 responses post-deploy (inspect Kudu logs, confirm startup command/port, review container health).
- [x] Document results and outstanding issues in `docs/Frontend_Deployment_Issue_Log.md`.

## Dependencies / Notes
- Requires Azure CLI authenticated to the target subscription (confirm before running deployment commands).
- Ensure environment variables used by the frontend (API base URL, auth headers) remain unchanged by the container update.
- Keep prior image tag noted for rollback if issues arise.

## Follow-up / Tech Debt
- [ ] File ticket: migrate FastAPI `on_event` handlers to lifespan API to clear deprecation warnings.
- [ ] File ticket: await planner integration tests (upgrade AsyncMock patterns) to remove coroutine warnings.
- [ ] Audit and remove legacy stubs/seed data left from HR template (check `tests/services` fixtures and unused assets).
