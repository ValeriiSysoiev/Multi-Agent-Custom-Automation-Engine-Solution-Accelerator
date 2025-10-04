# Reporting Dataset Export & Refresh Plan

## Objectives
- Provide curated data extracts for Power BI workspace `AI VM Reporting` (ID `8f802077-e058-4aac-ae18-0335bbbf59ab`).
- Support SLA, risk posture, verification, waiver, and lifecycle dashboards with drill-down to canonical records.
- Deliver refresh automation using the existing backend container (ACA job) and Power BI service principal (App ID `712006fa-1cbd-4f92-9fce-6f6a2ef23d42`).

## Dataset Scope
| Table | Purpose | Source Container(s) | Key Fields |
|-------|---------|---------------------|------------|
| `facts_findings` | Canonical vulnerability records with dedup + enrichment context | `findings_canonical`, `enrichments` | canonical_id, asset_id, vuln_key, severity, status, risk_tier, remediation_unit_id |
| `facts_triage` | Risk assessment outputs per canonical finding | `triage_items` | triage_id, canonical_id, likelihood, impact, risk_score, treatment, residual_risk |
| `facts_remediation_units` | Remediation units and ticket states | `remediation_units` | remediation_unit_id, bucket, risk_tier, status, due_dates |
| `facts_tickets` | Ticket linkage and SLA tracking | `tickets` | ticket_id, remediation_unit_id, status, due_at, verified_at, sla_breached |
| `facts_verification` | Evidence and verification outcomes | `evidence` | ticket_id, verification_status, evidence_type, captured_at, source_uri |
| `facts_runs` | Agent telemetry for operations dashboards | `runs_events` | agent_name, run_type, status, metrics, timestamps |
| `dim_assets` | Asset context | `assets` | asset_id, applications, owner, criticality, environment |
| `dim_time` | Pre-generated calendar (for reporting windows) | generated | date_key, day/week/month/quarter |
| `facts_runs` | Agent telemetry for operations dashboards | `runs_events` | agent_name, run_type, status, metrics, timestamps |

> Current push dataset: **AI VM Push v2** (`de1a1867-5e8a-40c3-8587-ed7912d33609`). An attempt to switch to **AI VM Starter** (`acc0156b-8e36-474b-8324-5d1f32359fc9`) on 29 Sep failed because that dataset did not contain the `facts_*` tables; we reverted by provisioning the new push dataset and redeploying (`chat-api-20251002j`). Ensure the container image is rebuilt with the correct AAD tenant (`6059f654-466e-4240-afef-51d8d9b51a82`) before redeploying—Cosmos telemetry previously showed the deprecated tenant `9a09d156-1962-4643-a52e-5dc17076ebaa`, causing MSAL authority errors until fixed.

### Metrics & Calculations
- Backlog (open canonical findings by risk tier).
- SLA performance: compare `tickets.due_at` vs `verified_at`/`status`.
- Verification compliance: ratio of `VerificationStatus.ACCEPTED` within window.
- Waiver coverage: active vs expired with compensating control counts.
- MTTR: difference between `runs_events` ingestion timestamps and verification/waiver closure.

## Export Mechanism
- Implement `ReportingExportService` reading from Cosmos repositories and emitting parquet/CSV to Azure Blob Storage (same region: Canada Central).
- Output path: `reports/aivm/<date>/` with per-table parquet files (partitioned by date).
- Expose CLI `run_reporting_export.py` to orchestrate extraction.
- Use `azure-storage-blob` SDK (add dependency in `pyproject.toml`) with Managed Identity; container `aivm-reporting` under existing storage account (provisioned in infra template or new resource).

## Power BI Refresh
1. Upload parquet/CSV into dedicated storage container (`aivm-reporting` on storage account `stgaivmreporting`).
2. Configure Power BI dataset using Synapse/Direct Lake or incremental refresh via dataflow.
3. Automation:
   - After export, call Power BI REST API using service principal secret (`POWERBI-CLIENT-SECRET` in Key Vault) to trigger refresh.
   - Endpoint: `POST https://api.powerbi.com/v1.0/myorg/groups/{workspaceId}/datasets/{datasetId}/refreshes` with `{ "notifyOption": "NoNotification" }`.
   - Store dataset ID alongside workspace ID in configuration (`config/reporting.yml`).

## Automation
- New script `create_reporting_job.sh` to schedule nightly exports (e.g., `0 2 * * *`).
- Environment variables: `REPORTING_STORAGE_ACCOUNT`, `REPORTING_CONTAINER`, `POWERBI_WORKSPACE_ID`, `POWERBI_DATASET_ID`.
- Job command: `python -m scripts.run_reporting_export --refresh-powerbi`.
- Extend `docs/Automation_Runbook.md` with reporting section and alert query (monitor `runs_events` with `run_type="reporting_export"`).

## Tasks Breakdown
1. **Infrastructure**: ensure storage container available; update Bicep if required.
2. **Configuration**: add `config/reporting.yml` for workspace/dataset/storage metadata.
3. **Service Implementation**:
   - `ReportingExportService` with repository aggregation methods.
   - Helpers for parquet writing (use `pyarrow`/`pandas` if acceptable; else CSV).
   - Power BI refresh client (MSAL -> Acquire token -> POST refresh).
4. **CLI**: `run_reporting_export.py` with options `--date-range`, `--refresh-powerbi`, `--verbose`.
5. **Automation**: `create_reporting_job.sh`, runbook updates, tests.
6. **Testing**: unit tests mocking repositories + blob client; integration (optional) writing to temp storage emulator or file system.

## Open Questions
- Storage account details for reporting exports (existing vs new).
- Dataset ID captured in `artifacts/powerbi/push_dataset_meta_20251002i.json` (currently `de1a1867-5e8a-40c3-8587-ed7912d33609`; switching again requires provisioning all `facts_*` tables before redeploying).
- Preferred file format (parquet recommended for Power BI performance).
- Incremental export window (daily delta vs full snapshot).
