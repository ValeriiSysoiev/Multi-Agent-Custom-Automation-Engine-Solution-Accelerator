# Risk Treatment Workflow Plan

Date: 2025-09-29
Owner: Codex (AI VM transformation agent)

## Objective
Close the loop on risk-treatment tasks generated when triage recommends `accept` or `transfer`. Ensure these tasks drive the appropriate waiver or risk-transfer workflows, update Cosmos state, and provide telemetry/alerts.

## Current State
- `RiskTreatmentTask` records (Cosmos container `risk_treatments`) capture:
  - `workflow` (`waiver` or `risk_transfer`)
  - `canonical_id`, `triage_id`, `asset_id`
  - Application/owner context (when available)
  - Residual risk & rationale from triage
  - `status` (defaults to `pending`)
- Triage LLM now supplies `compensating_controls`, `waiver_justification`, and optional `waiver_expiry_days`; these values are stored in `treatment_metadata` and copied to the task when created.
- `RiskTreatmentProcessor` files the initial Risk Acceptance/Transfer ticket and marks the task `in_progress`.
- `RiskTreatmentSync` polls Jira for approval/rejection, moves tasks to `completed`/`cancelled`, clears canonical `treatment_follow_up_id`, and updates run events (`risk_treatment_sync`).
- Azure Monitor alerts (`risk-treatment-processor-alert`, `risk-treatment-sync-stalled`) raise Sev 2/3 notifications when processor failures or stalled approvals occur so GRC/Vendor teams can intervene.
- Canonical findings store `treatment_follow_up_id` to prevent remediation from re-processing items until follow-up is complete.
- Automation now raises Jira tickets and syncs approvals, but human reviewers must move the tickets through the Risk Acceptance workflow to reach closure.

## Desired Workflow
1. **Discovery**
   - Periodic job lists `risk_treatments` with `status == pending`.
   - Produce telemetry (e.g., `run_type = "risk_treatment_monitor"`) for dashboards/alerting.
2. **Routing**
   - For `workflow == waiver`:
     - Create or update waiver intake records (Jira issue type `Risk Acceptance`, custom fields per policy).
     - Populate waiver justification with triage rationale + residual risk.
     - Require expiry date & compensating controls per policy (prompt operator if missing).
   - For `workflow == risk_transfer`:
     - Create risk-transfer issue (e.g., Jira `Risk Acceptance` with status `Transfer`) or integrate with external risk register.
     - Capture third-party/vendor metadata when available.
3. **Progress Tracking**
   - Processor sets `RiskTreatmentTask.status = in_progress`, stores linkage (`ticket_key`, `ticket_url`), and records metrics in `runs_events`.
   - Alerts notify owners if the processor skips tasks or fails.
4. **Closure**
   - When waiver approved or risk-transfer completed in Jira, the sync job:
     - Moves task `status` to `completed`.
     - Clears `treatment_follow_up_id` on the canonical finding.
     - Captures the Jira status/expiry, updates run events (`risk_treatment_sync`).
   - Planner boards/reporting can key off `risk_treatments` where `status == completed` and `ticket_status == Approved`.
5. **Exception Handling**
   - If waiver rejected or transfer denied, sync sets `status = cancelled`, clears the canonical follow-up, and remediation re-enters the queue (finding status `triaged`).
   - Owners should add Jira comments documenting the decision and any compensating actions; alerts ensure the queue does not stall.

## Data Gaps
- **Waiver creation inputs**: `WaiverService.request_waiver` requires a `RemediationUnitRecord`, compensating controls, expiry date, and justification. Accept/transfer triage currently lacks these inputs. Options:
  1. Extend `RiskTreatmentTask` with `justification`, `proposed_expiry`, `compensating_controls`, `remediation_unit_snapshot`.
  2. Or prompt human operator (via planner/UI) to supply details before automation calls `WaiverService`.
- **Risk-transfer destination**: Need confirmation on destination system (Jira issue type vs. external risk register). Document API/fields required.
- **Ownership**: Determine responsible team for monitoring & action (e.g., GRC owns waiver tasks, Vendor Management owns transfer tasks).

## Proposed Implementation Steps
1. **Schema enhancement**
   - Add optional fields to `RiskTreatmentTask` (`justification`, `proposed_expiry`, `controls`, `ticket_key`, `ticket_url`).
   - Update repositories/tests accordingly.
2. **Monitoring job**
   - Implement `RiskTreatmentMonitorService` producing run events (`risk_treatment_monitor`) with counts per workflow/status.
   - CLI `scripts/run_risk_treatment_monitor.py` for scheduling.
3. **Waiver automation**
   - New `RiskTreatmentProcessor` service to process waiver tasks with sufficient data.
   - For each task:
     - Validate required fields; if missing, log and leave `pending`.
     - Create waiver via `WaiverService.request_waiver` (potentially creating a lightweight remediation unit snapshot if none exists).
     - Update task status/links, clear canonical follow-up ID.
4. **Risk-transfer stub**
   - Until integration target defined, create placeholder Jira issue or log run event instructing manual action.
   - Document manual steps in runbook.
5. **Planner integration (optional)**
   - Expose risk-treatment tasks via planner quick actions (e.g., "Prepare waiver for canonical X").
6. **Alerting**
   - Extend runbook with Kusto queries for `risk_treatment_monitor` events.
   - Add dashboard cards for pending/overdue tasks by workflow.
7. **Testing**
   - Unit tests for new services (waiver creation, canonical updates, monitor metrics).
   - Integration test ensuring tasks move from `pending` → `completed` and canonical records reset.

## Open Questions
- Who supplies compensating controls and expiry data for automated waivers?
- Should waiver tasks create dedicated remediation units or link directly to canonical findings?
- What is the authoritative risk-transfer system? Jira issue type (10022) vs. separate API?

## Next Actions
1. Confirm data requirements with stakeholders (compensating controls, expiry, justification).
2. Extend `RiskTreatmentTask` schema to capture required metadata.
3. Build monitoring job & CLI.
4. Implement waiver processor once inputs agreed.

This document will evolve as integrations are confirmed.
