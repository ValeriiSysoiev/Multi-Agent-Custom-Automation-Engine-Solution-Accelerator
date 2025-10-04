# Active Working Context (Compact Summary)

## Phase Progress
- Phase 2: Ingestion, Dedup, Enrichment complete.
- Phase 3: Triage service/agent, CLI, policy config complete.
- Phase 4: Remediation service/agent/CLI, SLA policy complete.
- Phase 4 (Verification): Policy config, repositories, VerificationService, agent, tests, CLI, automation scripts complete.
- Phase 5 (Waiver): WaiverService, repositories, Jira integration, policy enforcement, renewal monitoring code in place; seeded fixtures (`seed-ru-pending`, `seed-ru-due`) drove the 26 Sep 05:29 UTC run (`aivm-waiver-expiry-job-cwk0ul6`) to log non-zero metrics (`pending_decision`, `due_within_*`) with Log Analytics row `RunId_s=bd4c39cb-647a-400c-8a91-273918baa7fb`; remove the fixtures after alert validation.
- Phase 6 (Reporting): Manual (24 Sep) and scheduled (25 Sep) runs succeeded; 26 Sep manual rerun (`aivm-reporting-job-bu40m0h`) over seeded fixtures produced blob prefix `reports/aivm/20250926/` with Power BI refresh flagged. Seed dataset includes assets `asset-web-01`/`asset-db-01`/`asset-api-01`, canonical `canon-*`, tickets `SEED-TICKET-00*`; remove once production ingestion is live. 27 Sep addition: optional Power BI push-dataset publishing (`push_dataset_enabled`) now replaces table rows without relying on Power Query refresh; use `scripts/create_powerbi_push_dataset.py` to provision the dataset and capture the new ID. ⚠️ 29 Sep regression after swapping datasets resolved by creating `AI VM Push v2` (`de1a1867-5e8a-40c3-8587-ed7912d33609`) and deploying `chat-api-20251002j`; manual run `aivm-reporting-job-rrelxkh` completed with full `pbi_rows_*` metrics. Monitor nightly schedule and plan seed-data cleanup once live ingestion fills the new dataset.
- Phase 7 (Chat): Chat agent design documented; implemented chat access policy, intent classifier, Cosmos-backed query service, agent factory wiring, and FastAPI `/api/chat` endpoint that reuses the shared service with row-level security. Planner/GroupChat now recognise `Chat_Agent`; intent catalogue covers open findings, KEV exposures, waiver/ticket queries, and executive summaries. Frontend `/chat` route surfaces the experience; 28 Sep deployments (`chat-api-20250928c/d`) return 200 responses with runs `b266d100-061c-4cd0-96c7-b497856218d4` and `a9cbcf33-155e-46c5-a488-0957b4d720df`. Requests that arrive without EasyAuth context now fall back to the DevAdmin sample scope until production RLS is wired.

## Automation
- Scripts: `create_triage_job.sh`, `create_remediation_job.sh`, `create_verification_job.sh`, `create_waiver_job.sh`, `create_reporting_job.sh` schedule Container Apps jobs.
- Health check CLI `scripts/check_reporting_health.py` verifies reporting job freshness, optional Power BI refresh, and blob outputs.
- Waiver job (`run_waiver_expiry.py`) runs cleanly with managed identity + Jira auth; current image (`waiver-monitor`) inserts `waiver_monitor` rows into `runs_events`. `WaiverMonitorMetrics_CL` now shows `Source_s == 'waiver_monitor'` with `RunId_s` populated (manual seeds remain for reference); alerts are active and ready once counts exceed zero.
- Runbook (`docs/Automation_Runbook.md`) details scheduling & alerting.

## Key Docs
- `docs/ImplementationStatus.md`: up-to-date checklist.
- `docs/Transformation_Issue_Log.md`: latest completed tasks including verification/waiver.
- `docs/Verification_Waiver_Design.md`: design for upcoming verification/waiver enhancements.

## Remaining Focus
### Temporary Overrides
- Defender ingestion is temporarily disabled in code (`src/backend/services/vulnerability_pipeline.py`) to avoid the Microsoft.Security sub-assessment 404 encountered during the demo. Re-enable the ingestion block once the Defender API issue is resolved.

### In Flight
1. Multi-Agent Planner integration complete: proxy now handles OPTIONS (204) ahead of planner POSTs, legacy agents removed, quick tasks aligned. Next validation step is end-to-end `/api/input_task` execution with production EasyAuth scope.
2. Monitor triage/remediation/verification/waiver/reporting jobs via `runs_events` alerts; roll out Azure Monitor rules per runbook guidance.
3. Waiver escalation via `waiver_monitor` telemetry operational; next wire alert rules and stakeholder notifications to the new metrics.
4. Seed datasets for non-zero exports (or transition to live ingestion), rotate secrets, and stand up dashboards using exported data or the new push dataset.
5. Remediation follow-ups: accept/transfer treatments queue risk-treatment tasks; the processor now creates Jira risk-acceptance/transfer tickets and the sync job updates tasks when Jira moves to Approved/Rejected, clearing canonical follow-ups. SLA monitor still emits `ack_due`/`verify_due` metrics for alerting.
6. Map production chat RLS (role/application/owner mappings) and wire Key Vault configuration before promoting the chat experience beyond dev; validate `/api/input_task` with real EasyAuth scope and prod triage LLM deployment values.
