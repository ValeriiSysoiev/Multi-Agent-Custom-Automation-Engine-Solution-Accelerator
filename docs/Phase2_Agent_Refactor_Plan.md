# Phase 2 – Agent & Tool Refactor Plan

This document outlines how we will replace the sample MACAE agents with AI Vulnerability Management (AI VM) agents, the sequence of work, required dependencies, and integration touchpoints.

## Overview
Phase 2 introduces domain-specific agents that operate on the new Cosmos data model and external integrations (scanner APIs, Jira, etc.). The refactor is broken into stages to control scope and allow incremental testing.

## Agent Lineup & Responsibilities
| Agent | Purpose | Key Inputs | Outputs |
|-------|---------|-----------|---------|
| `DefenderIngestionAgent` | Pull vulnerability data from Microsoft Defender (MDE TVM or ARM Assessments). | Azure credentials, watermarks | `RawFinding`, `CanonicalFinding` (initial), `SyncStateRecord` |
| `QualysIngestionAgent` | Pull detections from Qualys (JSON/XML). | Qualys API credentials, watermarks | `RawFinding`, initial `CanonicalFinding`, `SyncStateRecord` |
| `DeduplicationAgent` | Consolidate raw findings into canonical records, compute identity, merge provenance. | Raw findings, existing canonical records | Updated `CanonicalFinding`, `SourceReference` |
| `EnrichmentAgent` | Augment canonical records with business/threat context (Jira Assets, Defender TI, KEV, NVD). | Canonical IDs, enrichment APIs | `EnrichmentRecord`, update `AssetRecord`, threat signals |
| `TriageAgent` | Apply risk methodology (likelihood × impact, unacceptable overrides) + treatment recommendation. | Canonical/enrichment input, risk policy | `TriageRecord`, residual risk stored |
| `RemediationAgent` | Group findings, create/update remediation units and Jira tickets, apply SLAs. | Triage output, SLA matrices, Jira API | `RemediationUnitRecord`, `TicketRecord` |
| `VerificationAgent` | Process evidence submissions, auto-reopen logic, verification status updates. | Evidence input, verification policy | `EvidenceRecord`, ticket transitions |
| `ReportingAgent` | Feed Power BI datasets/dashboards once integration details provided. | Cosmos data, Power BI API | Dataset refresh, reporting snapshots |
| `ChatAgent` (QA) | Answer ground-truth questions using Cosmos data. | Cosmos queries | Role-based responses |

## Implementation Sequence
1. **Shared Services**
   - Create shared HTTP/Key Vault utility layer: `httpx` client with retry/backoff, secret retrieval via Key Vault/Managed Identity, consistent logging.
   - Build repository classes for each Cosmos collection with CRUD/stored procedure equivalents as needed.
2. **Ingestion Stage**
   - Implement Defender and Qualys ingestion agents, writing to `RawFinding` + `SyncStateRecord` + initial `CanonicalFinding` (without enrichment/triage fields).
   - Incorporate canonical mapper and identity function (hash of asset key + vuln key + location signature).
   - Develop ingestion CLI or job harness to run both agents sequentially.
   - ✅ Ingestion Agent and `run_ingestion_cycle` tool implemented (`kernel_agents/ingestion_agent.py`, `kernel_tools/ingestion_tools.py`).
3. **Deduplication**
   - Create DeduplicationAgent merging `RawFinding` into `CanonicalFinding`, preserving source provenance, updating lifecycle status.
   - Implement idempotent merges via upsert logic (delta on severity/last_seen/first_seen).
   - Detailed merge rules outlined in `docs/Dedup_Enrichment_Design.md`.
4. **Enrichment**
   - EnrichmentAgent queries Jira Assets, Defender TI, KEV/NVD; populates `EnrichmentRecord` and `AssetRecord` (identifiers list, ownership status).
   - Ownership fallback: promote to Linkage Review queue if owner unresolved.
   - Design decisions captured alongside dedup logic in `docs/Dedup_Enrichment_Design.md`.
5. **Triage**
   - ✅ TriageAgent now reads canonical + enrichment data, applies the risk methodology (likelihood/impact, unacceptable overrides), and stores `TriageRecord` with residual risk links (`services/risk_calculator.py`, `services/triage_service.py`, `kernel_agents/triage_agent.py`).
   - CLI + job automation available via `run_triage.py`/`scripts/create_triage_job.sh`; tests live under `src/backend/tests/services/`.
6. **Remediation**
   - ✅ RemediationAgent implemented: groups triaged findings, computes SLA from `config/remediation_sla.yml`, persists `RemediationUnitRecord`/`TicketRecord`, and creates Jira VR tickets via `services/jira_ticket_client.py`.
   - Automation ready through `run_remediation.py` and `scripts/create_remediation_job.sh`; compensating-control handling to follow in waiver phase.
7. **Verification**
   - ✅ VerificationAgent now evaluates evidence against policy, transitions Jira tickets (Verified/Reopened), and records summaries; next add webhooks/alerting for evidence intake.
   - Manage Linkage Review queue (ownership issues).
8. **Waiver Workflow**
   - ✅ WaiverService handles creation/approval/expiry, Jira waiver ticket creation, policy enforcement (controls + approval matrix), and Cosmos persistence; WaiverAgent wiring is forthcoming.
   - Remaining: auto-reopen logic tied to verification outcomes, renewal alerts, and waiver escalation workflows.
9. **Reporting**
   - Reporting export service + CLI scaffold in place (Cosmos → Blob, Power BI refresh trigger); managed identity credential fix checked in, awaiting container image rebuild/deploy. ReportingAgent will consume these datasets next.
10. **Chat/QA Agent**
   - Implement ground-truth query capability with row-level security filters. (In progress – access policy, intent classifier, and query service delivered 26 Sep.)

## Integration Test Hooks
- Real-data harness (Jira, Qualys, Defender) implemented under `tests/integration`, capturing artifacts in `/artifacts/<provider>/`.
- Defender: assessments/sub-assessments fetch, artifact dumps (`assessments.json`, `subassessments.json`, `ingestion_count.json`).
- Qualys: detection list + KB samples (`detections.json`, `kb.json`), mapped canonical samples, incremental check.
- Jira: create/update/transition flow with asset linkage, evidence validator check, and transitions artifact.

## Outstanding Inputs / Dependencies
- **Qualys**: API shard base URL, sample payload to confirm field mapping.
- **Defender**: choose integration path (MDE TVM vs. ARM assessments) per environment; sample payloads.
- **Power BI**: workspace/app info and dataset refresh flow.
- **Container creation**: implementation in infrastructure (Bicep or script) to provision new Cosmos containers.

## Next Steps
1. Build shared service layer and ingestion agents (Defender/Qualys).
2. Design repositories/services for canonical/dedup operations.
3. Implement dedup and enrichment pipelines with integration tests.
4. Continue through triage→remediation→verification→waiver per plan.
