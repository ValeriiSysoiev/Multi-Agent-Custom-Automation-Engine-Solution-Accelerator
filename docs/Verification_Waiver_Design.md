# Verification & Waiver Automation Design

This note captures the next phase (Phase 5 – Verification Agent, Phase 6 – Waiver Workflow) building on the remediation pipeline now in place.

## 1. Objectives
- Ensure every remediated item supplies evidence that meets the verification policy; automate acceptance/rejection and re-open logic.
- Provide a waiver workflow that enforces compensating control requirements, expiry, approvals, and integrates with Jira (issue type 10022).
- Maintain full auditability (evidence metadata, waiver approvals, reason codes) and update Cosmos containers (`evidence`, `waivers`, `tickets`, `runs_events`).

## 2. Key Components
| Component | Description |
|-----------|-------------|
| `VerificationService` | Ingest evidence records, evaluate policy, update `tickets`/`remediation_units`, emit `runs_events`. |
| `EvidenceRepository` | Cosmos DAL for `evidence` container (already modelled). |
| `VerificationAgent` & tools | Agent-level orchestration to run verification batches, request additional evidence, raise alerts. |
| `WaiverService` | Manage waiver requests, approvals, compensating controls, expiries. |
| `WaiverRepository` | Cosmos DAL for `waivers`. |
| Jira integration | Ability to transition remediation tickets and create/update waiver issues (issue type 10022). |
| Alerting | Extend `runs_events` monitoring for verification/waiver events. |

## 3. Verification Workflow
1. **Intake**: evidence arrives via API/Jira webhook or manual upload -> stored in `evidence` container.
2. **Evaluation**: VerificationService fetches pending tickets (status `resolved`/`submitted`) and runs policy checks:
   - Validate evidence combinations vs. policy matrix (Critical/High/Medium/Low by bucket).
   - Ensure timestamps are post-fix and within verification window.
   - Confirm scope (matching canonical_id/remediation_unit_id).
3. **Decision**:
   - Accept ⇒ mark `tickets.status = verified`, update `remediation_unit.status`, recompute residual risk.
   - Reject ⇒ set evidence `verification_status = rejected`, update ticket to `reopened`, append reason.
   - Auto-reopen when policy timers expire (lack of evidence, recurrence, control expiry).
4. **Telemetry**: record in `runs_events` with metrics `accepted`, `rejected`, `auto_reopened` etc.
5. **Reminder & Escalation**: integrate with Azure Monitor or Graph notifications (future).

## 4. Waiver Workflow
1. **Request**: Triage/Remediation agent (or human) triggers waiver creation when durable fix not feasible. WaiverService creates Jira waiver issue and Cosmos `waivers` entry.
2. **Approval Logic**:
   - Validate required fields: business justification, compensating controls, expiry, owner.
   - Enforce control minimums by risk tier per policy (Critical requires ≥2 strong controls, etc.).
   - Track approval matrix (CISO/App VP etc.).
3. **Lifecycle**:
   - `requested` → `approved`/`rejected` transitions with timestamps.
   - On approval, remediation unit transitions to WAIVED; tickets updated with waiver link.
   - Expiry auto-check (runs nightly) -> re-open remediation or require renewal.
4. **Integration Points**:
   - `remediation_unit` retains `waiver_id` and residual risk rationale.
   - `runs_events` records waiver approvals/expirations.
   - Alerts for waivers approaching expiry or lacking evidence.

## 5. Data Model Checks
- `EvidenceRecord` already supports required metadata; extend with `policy_reason` field if needed.
- `WaiverRecord` in `messages_kernel` currently includes status, expiry, compensating controls; verify Cosmos repo to be created.
- `TicketRecord` should capture `waiver_status` for quick filtering.

## 6. Implementation Plan (high-level)
1. **Repositories**: add `EvidenceRepository`, `WaiverRepository` wrappers similar to remediation repositories.
2. **VerificationService** *(implemented)*:
   - Policy interpreter for evidence combinations and SLA windows.
   - Methods `process_pending_tickets(limit)` and `evaluate_evidence(remediation_unit_id)`.
   - Updates `tickets`, `remediation_units`, Jira ticket status (Verified/Reopened), evidence metadata, and `runs_events`.
3. **Verification CLI/Agent**: `run_verification.py` for scheduled job; agent wiring similar to triage/remediation.
4. **WaiverService** *(partially complete)*:
   - Create/update waiver records, enforce policy, integrate with Jira issue type 10022 (status field synchronisation live).
   - Compensating control minimums and approval matrix now enforced via `waiver_policy.yml`/`WaiverPolicy`.
   - Next: add escalation notifications, renewal tracking, and compensating-control telemetry.
5. **Tests**: service-level tests for verification (accepted/rejected/autoreopen) and waiver approval/expiry scenarios.
6. **Automation**: extend runbooks/scripts for verification & waiver jobs once services implemented.
   - *Status*: Expiry sweeps + renewal monitoring now live (`run_waiver_expiry.py` emits `waiver_expiry` and `waiver_monitor` events). Remaining work: notification hooks/escalations tied to the telemetry.

## 7. Dependencies / Inputs Needed
- Confirm Jira workflow transition IDs for waiver approval/closure.
- Final compensating control definitions mapping to automation (e.g., WAF rule ID, EDR policy).
- Recurrence detection hook (ingestion pipeline must alert verification when canonical finding reappears).
- Notification channels for escalations (email/Teams).

## 8. Next Steps
- Implement repositories + verification service (#1 & #2 above).
- Extend Jira client with waiver operations (create/update/transition).
- Build verification CLI + automation script, mirroring triage/remediation flow.
- After verification in place, tackle waiver controls + runbooks, then move to Phase 5/6 agent implementations. *(Renewal telemetry completed; next focus is integrating alerting/notifications and waiver renewal approvals.)*
