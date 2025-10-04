# Phase 4 – Remediation/SLA Configuration Assessment

Date: 2025-09-29
Reviewer: Codex (AI VM transformation agent)

## Summary
Reviewed the remediation pipeline to confirm it honours the governance SLA tables and treatment guidance. The service (`RemediationService`) and policy (`RemediationPolicy`) already calculate bucket/tier/environment SLAs, generate sets of canonical findings for Jira tickets, and populate custom fields. The table below captures validation status and remaining tasks for Phase 4.

## Validation Checklist
| Area | Status | Notes |
|------|--------|-------|
| SLA lookup per bucket/tier/environment | ✅ | `remediation_policy.get_sla` reads `config/remediation_sla.yml`; verified defaults map to governance appendix tables. |
| Ticket payload includes risk/treatment metadata | ✅ | `JiraTicketData` sets custom fields 10068–10081 (risk tier/score, likelihood, impact, treatment, bucket, KEV, exposure, CVEs). |
| Due date alignment | ✅ | `sla_due` and Jira `duedate` both use the calculated `due_hours`. Description section exposes verification time. |
| Assignment SLA (ack_hours) represented | ✅ | Ack deadlines stored in `TicketRecord.ack_due`, added to Jira custom field when configured, and highlighted in ticket description. |
| Verify window tracked | ✅ | Verification deadlines stored in `TicketRecord.verify_due`, exposed in Jira fields/description alongside due date. |
| Treatment handling | ✅ | `mitigate`/`avoid` continue through remediation; `accept`/`transfer` now create risk treatment follow-up tasks routed to waiver or risk-transfer workflows. |
| Control bucket (compensating controls) | ✅ | Ticket summary/description adapt to “Implement control …” and include control guidance when bucket is CONTROL. |
| Run events & metrics | ✅ | `remediation_batch` run events capture processed/units/tickets counts. |

## Recommended Follow-Up Actions
1. **Assignment SLA tracking**: Implemented via `TicketRecord.ack_due`, optional Jira custom field (`JIRA_ACK_FIELD`), and the `remediation_sla_monitor` telemetry; configure dashboards/alerts using the Kusto query in the runbook.
2. **Verification SLA tracking**: Implemented via `TicketRecord.verify_due`, optional Jira custom field (`JIRA_VERIFY_DUE_FIELD`), and the new monitor; enable alerts for `verify_overdue`/`verify_due_within_*` as required by policy.
3. **Treatment-specific flows**:
   - Define behaviour for `TreatmentRecommendation.AVOID` (e.g., emphasise control decommission or service retirement steps in description).
   - Risk treatment processor now files Jira Risk Acceptance/Transfer tickets; next wire downstream approval/closure automation to flip `RiskTreatmentStatus` to `completed`/`cancelled`, clear `treatment_follow_up_id`, and capture audit notes when decisions land.
4. **Documentation**: Capture the SLA/treatment mapping decisions and the skip reasons in the runbook for SOC visibility.

## Artifacts Reviewed
- `src/backend/services/remediation_service.py`
- `src/backend/services/remediation_policy.py`
- `src/backend/config/remediation_sla.yml`
- `src/backend/services/jira_ticket_client.py`
- `src/backend/tests/services/test_remediation_service.py`
- `docs/AI_VM_Governance_Handbook.md` (SLA appendix)

These notes inform the next Phase 4 tasks to close the gaps above.
