# Automation & Alerting Runbook

This runbook explains how to schedule the AI VM batch jobs (triage now, remediation later) using Azure Container Apps Jobs and how to surface `runs_events` telemetry for alerting.

## 1. Prerequisites
- Azure CLI `azd`, `az` ≥ 2.49 installed and logged into the subscription that hosts `RG-AIVM`.
- Container Registry contains the backend image published by the existing `azd up` flow (tagged `aivm-prod-backend` by default).
- Environment variables seeded via `azd env set` (KEYVAULT_URI, COSMOSDB_*, etc.) and pushed to the Container App job definition.
- `run_triage.py` available inside the backend image (already part of repo under `src/backend/scripts/run_triage.py`).

## 2. Create/Update the Triage Batch Job
Use the helper script to create or update a Container Apps job that runs the triage cycle on a schedule (example: hourly). Adjust image/tag to match the deployed backend container.

```bash
# scripts/create_triage_job.sh
#!/usr/bin/env bash
set -euo pipefail

: "${AZURE_ENV_NAME:?Set via 'azd env set AZURE_ENV_NAME <name>'}"
: "${AZURE_RESOURCE_GROUP:?}"
: "${AZURE_LOCATION:=canadacentral}"
: "${TRIAGE_JOB_NAME:=aivm-triage-job}"
: "${TRIAGE_IMAGE:=<acr>.azurecr.io/aivm-prod-backend:latest}"

az containerapp job create \
  --name "$TRIAGE_JOB_NAME" \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --environment "$AZURE_ENV_NAME" \
  --trigger-type Scheduled \
  --cron-expression "0 * * * *" \
  --image "$TRIAGE_IMAGE" \
  --parallelism 1 \
  --replica-timeout 1800 \
  --replica-retry-limit 1 \
  --command "/bin/sh" "-c" "python -m scripts.run_triage --limit 100 --json" \
  --env-vars \ 
    KEYVAULT_URI="$(azd env get-value KEYVAULT_URI)" \ 
    COSMOSDB_ENDPOINT="$(azd env get-value COSMOSDB_ENDPOINT)" \ 
    COSMOSDB_DATABASE="$(azd env get-value COSMOSDB_DATABASE)" \ 
    AZURE_OPENAI_ENDPOINT="$(azd env get-value AZURE_OPENAI_ENDPOINT)" \ 
    TRIAGE_BATCH_LIMIT="100"
```

To update, rerun with the same name or supply `az containerapp job update`. Test an ad-hoc execution:

```bash
az containerapp job start --name "$TRIAGE_JOB_NAME" --resource-group "$AZURE_RESOURCE_GROUP"
```

## 3. Wiring Alerts via `runs_events`
1. **Log analytics**: ensure `runs_events` container emits diagnostics to Log Analytics (Azure Monitor). If not already configured, enable diagnostic settings on the Cosmos account and include the `runs_events` container.
2. **Alert rule**: create an Azure Monitor scheduled query alert running every 15 minutes:

```kusto
CosmosDBData
| where DatabaseName == "<database>"
| where CollectionName == "runs_events"
| extend payload = todynamic(Data)
| where payload.agent_name == "Remediation_Agent" or payload.agent_name == "Triage_Agent"
| where payload.status == "failed"
```

Trigger severity 2 if count ≥ 1; action group -> email/Teams.

3. **Dashboard**: create a Workbook referencing the same query with additional metrics (processed, skipped, etc.) to visualise batch health.

## 4. Remediation Batch Job
The remediation batch script now lives at `src/backend/scripts/run_remediation.py`. Provision a job alongside triage once you are ready to raise Jira tickets automatically:

```bash
# scripts/create_remediation_job.sh
export AZURE_ENV_NAME=$(azd env get-value AZURE_ENV_NAME)
export AZURE_RESOURCE_GROUP=$(azd env get-value AZURE_RESOURCE_GROUP)
export REMEDIATION_IMAGE=<acr>.azurecr.io/aivm-prod-backend:latest
export CRON_EXPRESSION="0 6 * * *"   # Daily at 06:00 UTC; adjust as needed

./scripts/create_remediation_job.sh
```

The remediation script honours `REMEDIATION_BATCH_LIMIT` and `REMEDIATION_ACTOR` environment variables, defaulting to 50 findings per run and `Remediation_Agent`. Jobs execute `python -m scripts.run_remediation --json` so metrics surface in `runs_events` with `agent_name == "Remediation_Agent"`.

Optional Jira custom fields:
- `JIRA_ACK_FIELD` — field ID for acknowledgement deadline. When set, the job populates the ack-by date calculated from the SLA.
- `JIRA_VERIFY_DUE_FIELD` — field ID for verification deadline. When set, the job populates the evidence due date alongside the standard due date (`customfield_10074`).
Both fields are stored in `TicketRecord.ack_due` / `.verify_due` regardless of Jira configuration, enabling downstream alerting.

Accept/transfer recommendations no longer appear as skipped metrics. Instead the job enqueues **risk-treatment tasks** in the new Cosmos container `risk_treatments` (`workflow` partition). Each execution surfaces `metrics.follow_up_accept` and `metrics.follow_up_transfer`; the `RemediationRunResult.follow_up_tasks` payload maps canonical IDs to task IDs (prefixed `rt-`). Use these task IDs to drive waiver or risk-transfer workflows and include the container in monitoring/dashboards (`RiskTreatmentStatus` values change to `completed` once downstream agents close the loop).

**Downstream expectations:**
- Waiver/risk-transfer automation must update `RiskTreatmentTask.status` from `pending` to `in_progress`/`completed` as work proceeds.
- When the follow-up is satisfied (e.g., waiver approved, third party assumes the risk), clear the canonical finding’s `treatment_follow_up_id` so the remediation queue no longer skips it.
- Persist audit notes on the task or related waiver/ticket to document the decision trail before marking the task `completed` or `cancelled`.
- If the decision changes (e.g., transfer denied), reset the task to `pending` or escalate back to triage so remediation can re-plan.
- SLA telemetry for acknowledgement/verification now runs via `scripts/run_remediation_sla_monitor.py`. The monitor writes `run_type="remediation_sla_monitor"` entries with metrics such as `ack_overdue`, `ack_due_within_1d`, `verify_overdue`, and `verify_due_within_7d`. Schedule it with Container Apps or Azure Functions as needed.

Suggested Log Analytics query for dashboards/alerts:

```kusto
CosmosDBData
| where CollectionName == "runs_events"
| extend payload = todynamic(Data)
| where payload.run_type == "remediation_sla_monitor"
| project TimeGenerated, ack_overdue = payload.metrics.ack_overdue, ack_due_1d = payload.metrics.ack_due_within_1d,
          verify_overdue = payload.metrics.verify_overdue, verify_due_3d = payload.metrics.verify_due_within_3d,
          status = payload.status
| order by TimeGenerated desc
```

To alert when acknowledgements breach, create a scheduled query rule on `payload.metrics.ack_overdue > 0` (e.g., 15-minute window, Severity 2) targeting the existing action group. Similarly, monitor `verify_overdue` for evidence deadlines.

## 5b. Risk Treatment Processor
- Script `src/backend/scripts/process_risk_treatments.py` evaluates pending `risk_treatments` tasks and creates Jira risk-acceptance/transfer tickets. On success it marks tasks `in_progress`, records ticket keys, and emits `run_type="risk_treatment_processor"` metrics (`waiver_created`, `transfer_created`, `skipped_missing_context`, `failed`).
- Deploy as a Container Apps job or Logic Apps timer similar to other automation scripts:

```bash
# scripts/process_risk_treatments.py
python -m scripts.process_risk_treatments --limit 25 --json
```

- Suggested alert query to catch stalled backlog:

```kusto
CosmosDBData
| where CollectionName == "runs_events"
| extend payload = todynamic(Data)
| where payload.run_type == "risk_treatment_processor"
| project TimeGenerated,
          waiver_created = payload.metrics.waiver_created,
          transfer_created = payload.metrics.transfer_created,
          failed = payload.metrics.failed,
          skipped = payload.metrics.skipped_missing_context,
          status = payload.status
| order by TimeGenerated desc
```

- Configure alerts when `payload.metrics.skipped_missing_context > 0` or `payload.metrics.failed > 0` to ensure missing enrichment/triage data is triaged quickly.
- Run events also populate `payload.metrics.waiver_completed`, `payload.metrics.transfer_completed`, `payload.metrics.waiver_cancelled`, and `payload.metrics.transfer_cancelled`. Use these for dashboards/alerts that track actual approvals versus denials.

## 5c. Approval & Closure Workflow

Once the processor raises risk-acceptance/transfer tickets, humans must complete the approval cycle and ensure data is reflected on the remaining dashboards.

1. **Alert handling**
   - `risk-treatment-processor-alert` (Sev 2) triggers if any task cannot be enriched (`skipped_missing_context`) or fails to create a ticket; investigate immediately via Cosmos (`risk_treatments`) and planner backlog.
   - `risk-treatment-sync-stalled` (Sev 3) fires when no sync metrics (`waiver_completed`, `transfer_completed`, etc.) are recorded within 60 minutes. Treat as “stuck approvals” and review Jira for pending tickets.

2. **Planner / manual follow-up**
   - Use planner quick tasks (e.g., “Review risk treatment backlog”) to queue work for GRC / Vendor Management when alerts fire.
   - Within Jira, open the Risk Acceptance issue created by the processor. The ticket contains:
     - Context: Asset(s), Application/Service, Business Owner, Environment.
     - Risk tab: Risk score, likelihood, impact, KEV flag, internet exposure.
     - Treatment tab: Recommendation, SLA due date.
     - Evidence tab: Residual risk, compensating controls, triage link, CVEs.
     - Waiver tab: Waiver status & expiry fields for approvals.

3. **Approval path**
   - Waiver approvals follow the matrix documented in the AI VM Governance Handbook (Security Lead, Platform Lead, CISO/App VP for critical, etc.).
   - Update Jira workflow status to “Approved”/“Rejected” (or equivalent) once the required sign-offs are recorded. Ensure compensating controls and expiry dates are documented before approval.
   - If the decision is rejection/denial, add comments describing the follow-up remediation plan.

4. **Automation checks**
   - The `sync` job reads Jira status. When tickets move to Approved/Rejected:
     - `RiskTreatmentTask.status` transitions to `COMPLETED` (Approved) or `CANCELLED` (Rejected).
     - `canonical.treatment_follow_up_id` is cleared so remediation can replan if needed.
     - `runs_events` logs `risk_treatment_sync` metrics (`completed`, `cancelled`).
   - If sync metrics remain zero after approval, rerun `python -m scripts.sync_risk_treatments --limit 50 --json` manually and review Container Apps logs.

5. **Dashboards**
   - Update Power BI/Workbook visuals to include counts of `RiskTreatmentTask` by status (`pending`, `in_progress`, `completed`, `cancelled`).
   - Use Log Analytics query:

```kusto
CosmosDBData
| where CollectionName == "risk_treatments"
| extend payload = todynamic(Data)
| summarize count() by status = tostring(payload.status)
| order by status asc
```

6. **Post-closure**
   - For completed tasks, confirm the waiver issue references residual risk, evidence, and expiry. If a waiver expires later, the waiver-monitor job will continue to track renewal windows.
   - For cancelled tasks, triage should revisit the canonical finding. Remediation may need to re-open mitigation path if acceptance/transfer is not approved.

Update Azure Monitor alerts/dashboards to monitor `metrics.units`, `metrics.tickets`, and `status` for the remediation agent in addition to triage.

## 5. Verification Checklist
- `az containerapp job show` reports **Succeeded** runs.
- `runs_events` contains `status=completed` entries for triage job with expected metrics.
- Alerts fire on forced failure (simulate by revoking Key Vault access and running job; ensure alert triggers then restore access).
- **Triage validation harness**: run `uv run python -m pytest tests/services/test_triage_service.py` after updating configuration. The suite verifies unacceptable-condition floors (e.g., active exploitation on crown jewels) and LLM adjustments. Ensure environment variables `ENABLE_TRIAGE_LLM` and `TRIAGE_MODEL_DEPLOYMENT` are set per environment and that Cosmos `runs_events` reflects triage metrics after changes.

## 6. Verification Job
- Script `src/backend/scripts/run_verification.py` and tooling (`VerificationService`) enable automated evidence checks.
- Provision/update the job:

```bash
# scripts/create_verification_job.sh
export AZURE_ENV_NAME=$(azd env get-value AZURE_ENV_NAME)
export AZURE_RESOURCE_GROUP=$(azd env get-value AZURE_RESOURCE_GROUP)
export VERIFICATION_IMAGE=<acr>.azurecr.io/aivm-prod-backend:latest
export CRON_EXPRESSION="0 */6 * * *"  # Every 6 hours; adjust as required

./scripts/create_verification_job.sh
```

- Monitor `runs_events` for `agent_name == "Verification_Agent"` (metrics `processed`, `verified`, `reopened`). Suggested alert query:

```kusto
CosmosDBData
| where CollectionName == "runs_events"
| extend payload = todynamic(Data)
| where payload.agent_name == "Verification_Agent" and payload.status == "failed"
```

- Verification runs transition Jira tickets (Verified/Reopened) and log evidence summaries in `customfield_10075`; ensure the service account retains transition rights.

## 7. Waiver Expiry & Renewal Job
- Script `src/backend/scripts/run_waiver_expiry.py` now performs two actions in a single run:
  1. Sweep for expired waivers and transition them in Jira (`run_type="waiver_expiry"` metrics capture `expired`).
  2. Evaluate renewal windows/pending approvals and emit telemetry (`run_type="waiver_monitor"`) with metrics such as `due_within_7d`, `due_within_3d`, `due_within_1d`, `pending_decision`, `missing_expiry`, and `overdue`.
- Provision/update the scheduled job:

```bash
# scripts/create_waiver_job.sh
export AZURE_ENV_NAME=$(azd env get-value AZURE_ENV_NAME)
export AZURE_RESOURCE_GROUP=$(azd env get-value AZURE_RESOURCE_GROUP)
export CONTAINERAPPS_ENV_NAME=cae-aivmprodcliu3        # override if azd env differs
export WAIVER_IMAGE=acraivmprod.azurecr.io/macaebackend:waiver-monitor
export CRON_EXPRESSION="0 1 * * *"                     # Daily at 01:00 UTC; adjust cadence as needed
export JIRA_BASE_URL=https://cyberairnd.atlassian.net
export JIRA_USER_EMAIL=ValeriiSysoiev@CyberAIRnD.onmicrosoft.com
# Optionally override the renewal windows (defaults to 7,3,1 days)
export WAIVER_MONITOR_WINDOWS="7,3,1"
# Log Analytics configuration (required for waiver telemetry alerts)
export LOG_ANALYTICS_WORKSPACE_ID=7f2bc68e-22c2-4de2-b209-21bbe2047d6d
export LOG_ANALYTICS_SHARED_KEY=$(az monitor log-analytics workspace get-shared-keys \
  --resource-group RG-AIVM \
  --workspace-name log-aivm-reporting \
  --query primarySharedKey -o tsv)
export LOG_ANALYTICS_LOG_TYPE=WaiverMonitorMetrics
# Supply registry credentials if the job needs to refresh the ACR secret
export REGISTRY_USERNAME=acraivmprod
export REGISTRY_PASSWORD=<acr-admin-password>
# Backend (Container App) rollback tag for chat API
export CHAT_API_IMAGE=acraivmprod.azurecr.io/macaebackend:chat-api-20250928d  # digest sha256:261bbddbf142e2a43fab4e3f2febe1df0c28b3526cfdbbb024491eb75d0c2327

./scripts/create_waiver_job.sh

# The script will upsert the Container Apps job (falling back to 'create' if missing),
# then patch the command/args/env via 'az containerapp job update'. If args ever drift
# you can explicitly reapply:
az containerapp job update \
  --name aivm-waiver-expiry-job \
  --resource-group RG-AIVM \
  --yaml /tmp/waiver_job.yaml   # template generated from az containerapp job show -o yaml

- Current status: manual runs complete successfully; the 26 Sep 05:29 UTC execution (`aivm-waiver-expiry-job-cwk0ul6`) processed seeded fixtures and logged non-zero waiver metrics (`total_active=2`, `pending_decision=1`, `due_within_7d=2`, `due_within_3d=1`) plus Log Analytics row `RunId_s=bd4c39cb-647a-400c-8a91-273918baa7fb`—monitor alerts, then delete the seed waivers once notifications are confirmed.
```

- Recommended alert for missed expiries:

```kusto
CosmosDBData
| where CollectionName == "runs_events"
| extend payload = todynamic(Data)
| where payload.run_type == "waiver_expiry" and payload.status == "failed"
```

- Dashboards should track `payload.metrics.expired` to confirm stale waivers are cleared; combine with Jira/waiver views for expiring soon items.
- Monitoring alert (renewal window breach):

```kusto
CosmosDBData
| where CollectionName == "runs_events"
| extend payload = todynamic(Data)
| where payload.run_type == "waiver_monitor" and tostring(payload.metrics.pending_decision) <> "0"
```

- Use the `runs_events` payload (field `metrics.escalations`) to identify specific waivers needing action; pair with Jira issue keys for follow-up. The job honours `WAIVER_MONITOR_WINDOWS` env var and defaults to 7/3/1-day reminders.
- Saved queries: `WaiverMonitorAlert` and `WaiverExpiryFailures` were created in workspace `log-aivm-reporting` to drive Azure Monitor scheduled-query alerts. Action group `ag-waiver-alerts` (Global) is provisioned with the operations mailbox. Cosmos diagnostics stream operational telemetry, while the waiver job now pushes its metrics directly to Log Analytics via the Data Collector API once the `LOG_ANALYTICS_*` env vars are configured; schedule the alert rule after confirming records land in the custom table.
- Quick verification: `az monitor log-analytics query --workspace 7f2bc68e-22c2-4de2-b209-21bbe2047d6d --analytics-query "WaiverMonitorMetrics_CL | sort by TimeGenerated desc | take 5"`. If the table returns `SEM0100`, push a one-off record with `services.LogAnalyticsClient` (see `docs/Reporting_Job_Issue_Log.md`) to materialise the schema before wiring alerts.
- Chat API telemetry sanity check (post-redeploy):
  ```bash
  az monitor log-analytics query \
    --workspace 7f2bc68e-22c2-4de2-b209-21bbe2047d6d \
    --analytics-query "AppEvents | where TimeGenerated > ago(1h) and Name == 'ChatQueryProcessed' | project TimeGenerated, Properties" \
    --timespan PT1H

  python - <<'PY'
  from azure.identity import DefaultAzureCredential
  from azure.cosmos import CosmosClient
  cred = DefaultAzureCredential(exclude_interactive_browser_credential=False)
  client = CosmosClient('https://cosmos-aivmprodcliu3.documents.azure.com:443/', credential=cred)
  container = client.get_database_client('macae').get_container_client('runs_events')
  query = "SELECT TOP 5 c.timestamp, c.id, c.metrics.intent, c.metrics.result_count FROM c WHERE c.run_type = 'chat_qa' ORDER BY c.timestamp DESC"
  for item in container.query_items(query, enable_cross_partition_query=True):
      print(item)
  PY
  ```
  - Saved search `chatqueryprocessed` (category `AutomationAlerts`) captures the above query for dashboards.
  - Scheduled query alert `chat-api-telemetry-gap` (15 minute window, action group `ag-waiver-alerts`) raises Sev2 if no `ChatQueryProcessed` events land.
- Saved search refresh (excludes manual seed rows):
  ```bash
  az monitor log-analytics workspace saved-search update \
    --resource-group RG-AIVM \
    --workspace-name log-aivm-reporting \
    --name waivermonitoralert \
    --display-name "Waiver Monitor Pending Decisions" \
    --category AutomationAlerts \
    --saved-query "WaiverMonitorMetrics_CL | where Source_s == 'waiver_monitor' | extend PendingDecision = toint(PendingDecision_d), DueWithin1d = toint(DueWithin1d_d), Overdue = toint(Overdue_d) | where PendingDecision > 0 or Overdue > 0 or DueWithin1d > 0 | project TimeGenerated, RunId = RunId_s, PendingDecision, Overdue, DueWithin1d"
  ```
- Scheduled query alert (15-minute cadence) targeting `ag-waiver-alerts`:
  ```bash
  az monitor scheduled-query create \
    --name waiver-monitor-pending-decisions \
    --resource-group RG-AIVM \
    --scopes /subscriptions/66e84420-9ef4-4264-aedb-7beacbfe9e81/resourceGroups/RG-AIVM/providers/Microsoft.OperationalInsights/workspaces/log-aivm-reporting \
    --action-groups /subscriptions/66E84420-9EF4-4264-AEDB-7BEACBFE9E81/resourceGroups/RG-AIVM/providers/microsoft.insights/actionGroups/ag-waiver-alerts \
    --severity 2 \
    --evaluation-frequency 15m \
    --window-size 15m \
    --description "Alert when waiver_monitor metrics show pending decisions/overdue" \
    --condition "count 'WaiverMonitorAlertQuery' > 0" \
    --condition-query "WaiverMonitorAlertQuery=\"WaiverMonitorMetrics_CL | where Source_s == 'waiver_monitor' | extend PendingDecision = toint(PendingDecision_d), DueWithin1d = toint(DueWithin1d_d), Overdue = toint(Overdue_d) | where PendingDecision > 0 or Overdue > 0 or DueWithin1d > 0\""
  ```

- Reporting export job:

```bash
# scripts/create_reporting_job.sh
export AZURE_ENV_NAME=$(azd env get-value AZURE_ENV_NAME)
export CONTAINERAPPS_ENV_NAME=cae-aivmprodcliu3     # override if azd env differs
export AZURE_RESOURCE_GROUP=$(azd env get-value AZURE_RESOURCE_GROUP)
export REPORTING_IMAGE=acraivmprod.azurecr.io/macaebackend:latest
export CRON_EXPRESSION="0 2 * * *"   # Daily at 02:00 UTC; adjust as required
export AZURE_MANAGED_IDENTITY_CLIENT_ID=c6c2af5b-d1c9-4b02-9b8e-5894e89cb9cd
export REPORTING_MANAGED_IDENTITY_CLIENT_ID=$AZURE_MANAGED_IDENTITY_CLIENT_ID

./scripts/create_reporting_job.sh
```

- Before scheduling, populate `src/backend/config/reporting.yml` with the storage account/container (in Canada Central) and, once known, the Power BI dataset ID. Without a dataset id the job skips the refresh trigger.
- To publish via Power BI push datasets instead of Power Query refreshes, set `push_dataset_enabled: true`, create the dataset once with `python -m scripts.create_powerbi_push_dataset --dataset-name "AI VM Push"`, and copy the new dataset ID back into `reporting.yml`. The export job will then replace rows table-by-table and skip the legacy refresh call (metrics appear as `pbi_rows_<table>` in `runs_events`). Ensure the target dataset exposes the full `facts_*` / `dim_assets` tables before switching IDs—29 Sep regression traced to using `acc0156b-8e36-474b-8324-5d1f32359fc9` without those tables, later resolved by provisioning `AI VM Push v2` (`de1a1867-5e8a-40c3-8587-ed7912d33609`) and redeploying `chat-api-20251002j`. If the Azure AD tenant rotates, set `PBI_TENANT_ID` (or `POWERBI_TENANT_ID` / `AZURE_TENANT_ID`) on the Container Apps job before redeploying so the exporter uses the new tenant without waiting on image rebuild.
- After redeploying, run `az containerapp job start --name aivm-reporting-job --resource-group RG-AIVM` to validate the new image/config before relying solely on the schedule.
- Alert query:

```kusto
CosmosDBData
| where CollectionName == "runs_events"
| extend payload = todynamic(Data)
| where payload.run_type == "reporting_export" and payload.status == "failed"
```

- Monitor `payload.metrics` for row counts and `powerbi_refresh_triggered` to verify dataset refresh requests.
- Health check (on-demand or after alerts):

```bash
python -m scripts.check_reporting_health --require-refresh --check-storage --json
```

This script inspects the latest `reporting_export` event in Cosmos, enforces a freshness window (override with `--max-age-hours`), optionally requires a Power BI refresh flag, and validates that blobs exist for the most recent date segment. Ensure Power BI client secrets and any temporary storage keys used for troubleshooting are stored in Key Vault and rotated after verification.

Keep this runbook alongside deployment docs; adjust cron/parameters as production cadence evolves.

## 7. Manual Smoke Checklist
- `curl -sS -X POST https://app-aivmprodcliu3.azurewebsites.net/api/chat -H "Content-Type: application/json" -d '{"question":"Ping","session_id":"smoke-run","limit":1}'` — confirm HTTP 200 payload with a `run_id`.
- `curl -sSL https://app-aivmprodcliu3.azurewebsites.net/ | head` — spot-check that the React shell renders.
- `az monitor log-analytics query --workspace <workspace-id> --analytics-query "AppEvents | where TimeGenerated > ago(15m) and Name == 'ChatQueryProcessed'" --timespan PT15M` — verify chat telemetry landed in Log Analytics.
- `az cosmosdb sql container query-items --account-name cosmos-aivmprodcliu3 --database-name macae --name runs_events --query "SELECT TOP 5 c.timestamp, c.metrics.intent FROM c WHERE c.run_type='chat_qa' ORDER BY c.timestamp DESC"` — confirm the latest smoke run appears in `runs_events`.
- Log the run ID and timestamp in `docs/Frontend_Deployment_Issue_Log.md` once complete.
