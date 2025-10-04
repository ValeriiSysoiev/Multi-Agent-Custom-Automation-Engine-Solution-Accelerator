# Implementation Status

## Phase 1 – Data Model & Storage
- [x] Extended Pydantic models for AI VM (canonical findings, enrichment, triage, remediation units, tickets, evidence, assets, runs, waivers).
- [x] Updated Cosmos repository mapping and documented container/TTL/index plan.
- [x] Captured governance policies in AI VM Handbook.

## Phase 2 – Agent Refactor (In Progress)
- [x] Shared services: httpx client with retries, Key Vault integration, Cosmos repositories.
- [x] Defender & Qualys ingestion services implemented.
- [x] Integration test scaffolds (Jira, Qualys, Defender) with artifact capture per harness.
- [x] Dedup/Enrichment design captured in `docs/Dedup_Enrichment_Design.md`.
- [x] Regenerate `uv.lock` after dependency updates.
- [x] Implement DeduplicationService & EnrichmentService per design.
- [x] Wire ingestion services into orchestration (Defender/Qualys pipeline agentised).
- [x] Implement triage service & agent (risk scoring, LLM prompt, Cosmos persistence).
- [x] Add triage/remediation CLI runners and Container Apps job scripts.
- [x] Implement remediation agent and workflows.
- [x] Implement verification agent/service (policy config, Jira transitions, evidence summary, CLI, tests).
- [x] Implement waiver service scaffolding (Jira linkage, status updates, Cosmos persistence, batch expiry, policy enforcement).
- [x] Reporting dataset export & refresh pipeline (Power BI integration) – image rebuilt, job redeployed, manual (24 Sep) and scheduled (25 Sep 02:00 UTC) runs succeeded; storage/refresh validated via health check. Seed script executed 26 Sep to produce demo dataset (assets/tickets/remediation units), reporting job `aivm-reporting-job-bu40m0h` confirmed non-zero outputs for Parquet + Power BI refresh. Cleanup pending once production ingestion replaces seed data. Push-dataset publishing path implemented 27 Sep (config flag `push_dataset_enabled`, Power BI row replacement) with unit coverage; refresh trigger now optional when push mode is active. ⚠️ 29 Sep regression (dataset `acc0156b-8e36-474b-8324-5d1f32359fc9` missing `facts_*`) resolved by provisioning new push dataset `de1a1867-5e8a-40c3-8587-ed7912d33609`, rebuilding the backend as `chat-api-20251002j`, and validating manual run `aivm-reporting-job-rrelxkh` (correlation `dc6053f2-9c63-4029-ab55-6d5ee5a13c1d`) with full `pbi_rows_*` metrics. Scheduled run monitoring remains.
- [x] Chat agent scaffolding – added `ChatAgent`, intent classifier/access policy, Cosmos query service, planner/group-chat wiring, and FastAPI `/api/chat` endpoint with direct RLS-aware responses. Rule-based intents now cover KEV exposure and executive-summary templates in addition to the original backlog views. `/chat` frontend page now consumes the API; 28 Sep redeploys (`chat-api-20250928c` → `chat-api-20250928d`, revision `ca-aivmprodcliu3--0000005`) validated end-to-end with Cosmos `chat_qa` runs (`b266d100-061c-4cd0-96c7-b497856218d4`, `a9cbcf33-155e-46c5-a488-0957b4d720df`) and App Insights `ChatQueryProcessed` events. Anonymous/unauthenticated requests now fall back to the sample DevAdmin scope until production EasyAuth roles are wired. Remaining work is mapping production RLS and polishing the UX as telemetry matures.
- [x] Multi-Agent Planner integration (docs/Planner_Integration_Plan.md): proxy planner APIs, retire legacy agents/tools, align planner instructions/UI with the AI VM lifecycle, and validate planner API access through App Service (OPTIONS 204 + POST 422 without payload).
- [x] Removed legacy accelerator agent enums (HR/Marketing/Procurement/Product/Tech Support) so front-end/back-end rosters only surface AI VM agents.
- Waiver renewal monitoring: `run_waiver_expiry.py` executes successfully with Jira MI auth and configurable `WAIVER_MONITOR_WINDOWS`; seeded fixtures (`seed-ru-pending`, `seed-ru-due`) drove the 26 Sep 05:29 UTC execution (`aivm-waiver-expiry-job-cwk0ul6`) to emit non-zero metrics (`total_active=2`, `pending_decision=1`, `due_within_7d=2`, `due_within_3d=1`) and Log Analytics row `RunId_s=bd4c39cb-647a-400c-8a91-273918baa7fb`. Cleanup of the seed data remains once alert notifications are verified (after the next scheduled run).
- Reporting export validation: Seed script (`scripts/seed_reporting_data.py`) inserted 3-scenario fixtures (assets/tickets `SEED-*`), and manual run `aivm-reporting-job-bu40m0h` (26 Sep 13:04 UTC) produced blob prefix `reports/aivm/20250926/` with `powerbi_refresh_triggered=1` (Cosmos event `e6147c9c-fbc5-4ecc-b660-9f78558dcf17`).

## Phase 4 – Risk & Remediation Enhancements (In Progress)
- [x] Added `active_exploitation_crown_jewel` override and unit coverage (triage now floors such cases at Critical).
- [x] Introduced triage validation harness (`tests/services/test_triage_service.py`) and documented its usage in the runbook.
- [x] Remediation pipeline now surfaces acknowledgement/verification deadlines (`ack_due`, `verify_due`) via `TicketRecord` and Jira custom fields; control bucket tickets use control-specific messaging.
- [x] Route `TreatmentRecommendation.ACCEPT` / `TRANSFER` findings to waiver/risk workflows (currently skipped with metrics).
- [x] Wire alerts/dashboards for new SLA deadlines (`ack_due`, `verify_due`).
- [x] Risk treatment automation creates Jira Risk Acceptance/Transfer tickets, updates `risk_treatments` status, and records processor telemetry.
- [x] Risk treatment sync job reconciles Jira status, clears canonical follow-ups, and emits `risk_treatment_sync` run events.

## Notes
- Documentation: `docs/Phase2_Agent_Refactor_Plan.md`, `docs/Cosmos_Schema_and_Migration.md`, `/docs/defender/*`, `/docs/qualys/*`, `docs/defender_timeout_issue_log.md`, `docs/Automation_Runbook.md`.
- Reporting health check: `scripts/check_reporting_health.py` provides on-demand validation (freshness, Power BI refresh flag, blob presence) and was used to validate the 25 Sep scheduled run.
- Artifacts saved under `/artifacts/<provider>/` by integration tests.
- Ingestion, triage, remediation, and verification agents callable via planner/CLI (`run_triage.py`, `run_remediation.py`, `run_verification.py`); next focus is planner prompt refinement and verification/waiver automation.
- Compensating control/waiver automation: waiver service + repos in place; next step is wiring approval matrix & Jira transitions.
