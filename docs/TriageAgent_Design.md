# Triage Agent Design

## 1. Purpose
The Triage Agent applies the organisation's risk methodology to each canonical vulnerability finding. It consolidates technical, business, and threat context; determines likelihood and impact (including unacceptable outcome overrides); calculates the composite risk score; recommends the appropriate treatment; and records a complete audit trail in Cosmos DB. Output from the Triage Agent becomes the authoritative risk record and drives remediation, waiver, and reporting workflows.

## 2. Inputs & Dependencies
| Data Source | Details |
|-------------|---------|
| `CanonicalFinding` (Cosmos `findings_canonical`) | Asset identifiers, vulnerability key, severity, lifecycle status, source references. |
| `EnrichmentRecord` (Cosmos `enrichments`) | Business context (owner, criticality, environment, tags), threat signals (KEV, Defender TI, EPSS), exposure metadata. |
| `RunEvent` telemetry | For logging triage job runs and failures. |
| Risk methodology artifacts | Likelihood & impact rubrics, unacceptable conditions, treatment rules, residual risk definitions (from IS Risk Management Methodology). |
| SLA Matrix | Used later for remediation planning but referenced during triage to tag SLA tier. |
| Verification & waiver policies | Needed for recommended next steps metadata. |

Dependencies that must be available before execution:
- Enrichment pipeline populates business + threat context.
- References to canonical findings are stable (dedup service in place).
- Configuration store for risk rules (see Section 3.4).

## 3. Processing Flow
1. **Selection:** Load canonical IDs requiring triage (status `OPEN` or `REOPENED`, or flagged for re-triage after enrichment changes).
2. **Context assembly:** Join canonical finding with enrichment record and threat signals. Ensure asset owner/application criticality are resolved; if missing, mark status `LINKAGE_REVIEW` and skip.
3. **Deterministic pre-processing:**
   - Compute baseline likelihood/impact from rubric tables.
   - Evaluate unacceptable outcome rules (eg. potential >24h outage, >100 data subjects). Escalate provisional risk tier when matched.
   - Aggregate control modifiers (eg. WAF coverage) and compensating controls currently active.
4. **LLM-assisted reasoning:** Prompt the triage LLM with structured context to:
   - Summarise exploitation scenario(s).
   - Validate/adjust likelihood & impact ranges based on context.
   - Recommend treatment (`mitigate`, `accept`, `transfer`, `avoid`).
   - Suggest remediation focus (patch vs config vs control) and note residual risk assumptions.
   The prompt enforces a strict JSON schema returning: `likelihood`, `impact`, `risk_score`, `risk_tier`, `treatment`, `rationale`, `residual_risk`, `unacceptable_conditions_triggered`.
5. **Post-processing & validation:**
   - Recompute risk score (likelihood × impact) and compare with LLM output; flag discrepancies.
   - Map treatment to SLA tier using matrix.
   - Persist `TriageRecord` (append-only) and link to canonical finding; update canonical status to `TRIAGED`.
   - Log run details in `RunEvent` with correlation ID.

## 4. Prompt & Configuration Design
- **Prompt template:**
  - Provides structured sections: Vulnerability summary, Asset criticality, Exposure indicators, Threat signals, Historical occurrences, Compensating controls.
  - Embeds key policy statements (risk appetite, unacceptable conditions, residual risk definition).
  - Requests JSON output conforming to `TriageRecord` schema fields.
- **Configuration sources:**
  - YAML/JSON config file `config/risk_methodology.yml` capturing rubrics, control modifiers, unacceptable conditions, treatment rules.
  - Environment variable `TRIAGE_MODEL_DEPLOYMENT` to select Azure OpenAI deployment.
  - Optional feature flags: `ENABLE_TRIAGE_LLM` to allow fallback deterministic scoring.

## 5. Service & Agent Components
| Component | Responsibility |
|-----------|----------------|
| `services/triage_service.py` | Core orchestration: fetch findings, assemble context, invoke LLM, apply deterministic checks, persist records. |
| `kernel_tools/triage_tools.py` | Exposes triage functions to agents (eg. `process_findings`, `triage_single_finding`). |
| `kernel_agents/triage_agent.py` | Agent wrapper with system prompt referencing methodology; uses triage tools. |
| `repositories/triage_repository.py` | Cosmos CRUD helpers for `triage_items` container. |
| `tests/integration/test_triage_service.py` | End-to-end triage tests (with mocked LLM + sample data). |
| `docs/TriageAgent_Design.md` | Living design document (this file). |

## 6. Output & Persistence
- **Cosmos container:** `triage_items` (partitioned by `canonical_id`).
- **Record type:** `TriageRecord` already defined in `models/messages_kernel.py` (fields: likelihood, impact, risk_score, treatment, rationale, residual_risk, supporting_inputs, supersedes).
- **Linkages:** Write `triage_id` into canonical finding history (`FindingLifecycleStatus.TRIAGED`). Append reference to remediation planning queue.
- **Telemetry:** Emit `RunEventRecord` capturing counts processed, escalations, and errors. Include `assessment_version` for reproducibility.

## 7. Error Handling & Retriable Scenarios
- Missing enrichment → skip with status `OwnershipStatus.LINKAGE_REVIEW` and log.
- LLM failure → retry (exponential backoff). After max attempts, mark triage as failed and raise alert.
- Schema validation errors → log to `run_events`, store raw response for manual inspection.
- SLA/treatment mismatches → include warnings in `supporting_inputs` for downstream review.

## 8. Implementation Plan
1. **Configuration layer** ✅ Risk rubric encoded in `config/risk_methodology.yml`; helper utilities live in `services/risk_calculator.py`.
2. **Service scaffolding** ✅ `TriageService` implemented with repository integration and run-event telemetry.
3. **LLM prompt & validator** ✅ Prompt stored in `prompts/triage_prompt.txt`; schema enforcement via `services/triage_models.py`.
4. **Agent and tools** ✅ Tools/agent registered (`kernel_tools/triage_tools.py`, `kernel_agents/triage_agent.py`, planner updated).
5. **Testing** ✅ Unit tests added under `src/backend/tests/services/` covering scoring + triage persistence with LLM disabled.
6. **Operationalisation** ▶️ Next: add scheduled execution (CLI/Container Apps job) and extend runbooks once deployment cadence defined.

## 9. Open Questions
- Confirm final JSON schema for LLM output (need approved field names / data types).
- Determine cadence (on-demand via agent vs scheduled job) and concurrency limits.
- Decide whether to persist deterministic pre-check results (control modifiers, unacceptable flags) as structured arrays for analytics.
- Clarify approach for re-triage triggers (eg. enrichment changes, new threat signals) to avoid duplicate records.

## 10. Next Actions
1. Finalise LLM schema/response review with risk owners; tune prompt thresholds as feedback arrives.
2. Integrate triage execution into scheduled automation (e.g., `run_triage.py` / Container Apps job) with environment-specific cadence.
3. Expand monitoring: capture triage run metrics in dashboards and alerting (tie into `runs_events` container).
