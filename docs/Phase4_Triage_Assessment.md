# Phase 4 – Triage Configuration Assessment

Date: 2025-09-29
Reviewer: Codex (AI VM transformation agent)

## Summary
A configuration and code review was completed to confirm that the triage service, risk calculator, and LLM prompt align with the IS Risk Management Methodology (ref. AI VM Governance Handbook). The current implementation already encodes the core rubric (likelihood × impact, unacceptable overrides, treatment defaults). The following table captures the validation status and gaps to address in subsequent Phase 4 work items.

## Validation Checklist
| Area | Status | Notes |
|------|--------|-------|
| Deterministic calculator implements rubric (severity → likelihood, criticality/data classification → impact, unacceptable floors) | ✅ | `services/risk_calculator.py` uses `risk_methodology.yml`. New `active_exploitation_crown_jewel` override validated via unit tests. |
| Residual risk defaults recorded with triage records | ✅ | `triage_service.py` uses `default_residual_risk`; residual rationale updated post-LLM when provided. |
| Treatment recommendation defaults match governance policy | ✅ | All tiers default to `mitigate` except Very Low (`accept`). Review after SLA refinements (no change required now). |
| Triage LLM prompt enforces risk matrix, unacceptable overrides, treatment/tier rules | ✅ | `prompts/triage_prompt.txt` explicitly states score → tier mapping, unacceptable outcomes, treatment list; temperature 0.0, JSON schema enforced. |
| LLM returns treatment metadata | ✅ | `TriageLLMResponse` now supplies compensating controls, waiver justification, and expiry guidance stored in `supporting_inputs['treatment_metadata']` for downstream automation. |
| LLM deployment configuration | ⚠️ | Uses env vars `TRIAGE_MODEL_DEPLOYMENT`/`AZURE_OPENAI_DEPLOYMENT_NAME` and `ENABLE_TRIAGE_LLM`. Need environment validation once prod deployment names are final. |
| Deterministic vs LLM reconciliation | ✅ | Automated harness (`tests/services/test_triage_service.py`) covers unacceptable-condition overrides and LLM adjustments; run via `uv run python -m pytest tests/services/test_triage_service.py`. |
| Telemetry | ✅ | `RunEventRepository` captures processed/triaged counts, correlation IDs. |
| Documentation | ⚠️ | No public-facing runbook yet for triage configuration. Add Phase 4 notes to `Automation_Runbook.md` when LLM validation is completed. |

## Recommended Follow-Up Actions
1. **Deployment validation**: Confirm `TRIAGE_MODEL_DEPLOYMENT` and `ENABLE_TRIAGE_LLM` values in each environment. Document the expected configuration in `Deployment_Config_Notes.md`.
2. **Runbook update**: Extend `docs/Automation_Runbook.md` with a triage section describing toggles, env vars, and the manual validation script (done).

## Artifacts Reviewed
- `docs/AI_VM_Governance_Handbook.md`
- `src/backend/config/risk_methodology.yml`
- `src/backend/services/risk_calculator.py`
- `src/backend/services/triage_service.py`
- `src/backend/prompts/triage_prompt.txt`
- `src/backend/tests/services/test_risk_calculator.py`

No code changes were required at this stage beyond the override already implemented (see transformation log entry 2025-09-29). Future Phase 4 tasks will focus on the validation harness and runbook documentation described above.
