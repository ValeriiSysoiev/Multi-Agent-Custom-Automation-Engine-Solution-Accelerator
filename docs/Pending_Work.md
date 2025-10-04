# Pending Work

## Test Suite / Automation
- Remove temporary pytest skips (Azure SDK) and refactor tests to use shared Azure stub helpers or recorded fixtures.
- Decide on integration vs fixture approach for Defender/Qualys smoke tests (live vs sample data).

## Housekeeping
- Remove residual legacy template files/docs once planner refactor is merged.
- Centralise Azure stub helpers in a common module (e.g., tests/shared/azure_stubs.py).
- Update the runbook with a manual smoke-test checklist (curl /api/chat, App Service UI load).
- Implement waiver/risk-transfer agents that consume `risk_treatments` tasks, update task status, clear `treatment_follow_up_id`, and persist audit outcomes.
