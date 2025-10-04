# AI Vulnerability Management Governance Handbook

This handbook consolidates all policies and operating rules that guide the transformation of the Multi-Agent Custom Automation Engine (MACAE) into an AI-powered Vulnerability Management (AI VM) platform. It is the single source of truth for risk methodology, SLAs, verification, waiver governance, data management, and integration controls. Update this document whenever policies change.

## Table of Contents
1. [Overview & Objectives](#overview--objectives)
2. [Risk Methodology](#risk-methodology)
3. [SLA Matrix & Escalations](#sla-matrix--escalations)
4. [Verification Policy](#verification-policy)
5. [Exception & Waiver Process](#exception--waiver-process)
6. [Identity & Ownership Rules](#identity--ownership-rules)
7. [Chat Agent Row-Level Security](#chat-agent-row-level-security)
8. [Credential & Integration Strategy](#credential--integration-strategy)
9. [Data Residency & Retention](#data-residency--retention)
10. [Reporting & Audit Expectations](#reporting--audit-expectations)
11. [Change Control & Emergency Windows](#change-control--emergency-windows)
12. [Glossary & References](#glossary--references)
13. [Appendix A – SLA Tables](#appendix-a--sla-tables)
14. [Appendix B – Waiver Approver Matrix](#appendix-b--waiver-approver-matrix)
15. [Appendix C – Evidence Combinations](#appendix-c--evidence-combinations)

---

## 1. Overview & Objectives
- **Mission**: Deliver a risk-driven, auditable vulnerability management process that ingests, deduplicates, enriches, triages, remediates, verifies, and reports on vulnerabilities.
- **Risk Appetite**: Low. Avoid >24h outages, sensitive data breaches (>100 individuals), regulatory/contractual non-compliance, and material loss of stakeholder trust.
- **Scope**: All assets and applications enrolled in the AI VM platform, including cloud, on-prem, and third-party systems.

---

## 2. Risk Methodology
- **Scoring**: Likelihood (1–5) × Impact (1–5).
- **Impact determination**: Choose the highest applicable among financial, operational, confidentiality-integrity-availability (CIA), compliance, and reputational impacts.
- **Risk bands**:
  - Very Low (1–2)
  - Low (3–4)
  - Medium (5–10)
  - High (12–16)
  - Critical (20–25)
- **Unacceptable outcomes** (trigger automatic elevation to High/Critical):
  - Potential interruption >24h
  - Breach of sensitive data affecting >100 individuals
  - Regulatory or contractual non-compliance
  - Material loss of stakeholder trust
- **Overrides**: If triage identifies any unacceptable condition or active exploitation (KEV, internet-facing crown jewels), treat the finding as Critical with emergency remediation requirements.

---

## 3. SLA Matrix & Escalations
- **Environments**: PROD, UAT/STG, DEV/INT, SHARED/NON-PROD.
- **Buckets**: PATCH, CONFIG, CODE, CONTROL (compensating control).
- **Highlights** (full tables in Appendix A):
  - Critical PATCH (PROD): assignment ≤2 hours, completion ≤48 hours (emergency allowed), verification ≤24 hours.
  - Critical CONFIG (PROD): assignment ≤2 hours, completion ≤24 hours, verification ≤24 hours.
  - Critical CODE (PROD): assignment ≤4 hours, completion ≤10 days (with CONTROL applied), verification ≤3 business days.
  - CONTROL required when durable fixes cannot meet Critical/High due dates.
- **Escalation ladder**:
  - Assignment breach: notify team owner + SecOps; move to hot queue.
  - 50% timer with no plan: notify App/Service Owner + Platform Manager; schedule change.
  - T-24h to due with no booking: escalate to Director; emergency or waiver required.
  - Due date breach: escalate to VP/CISO; treat Critical/unacceptable as incidents with weekly executive status.
  - Verification failure/reopen: escalate one level above prior; RCA ≤5 business days.

---

## 4. Verification Policy
- See Appendix C for evidence combinations.
- **Deadlines**: Critical 24–72h, High ≤5 business days, Medium ≤7 business days, Low ≤10 business days.
- **Separation of duties**: Implementer ≠ Verifier; Critical/High require security lead approval.
- **Auto-reopen triggers**: missing/invalid evidence, recurrence within 30 days, probe/control failure, control expiry, change rollback, new policy triggers.
- **Residual risk**: recalculate after verification, store alongside evidence references.

---

## 5. Exception & Waiver Process
- **Eligibility**: Only when SLA cannot be met due to vendor dependency, high blast radius, blackouts, or resource constraints—and only if unacceptable outcomes are mitigated by compensating controls.
- **Waiver package**: risk details, justification, compensating controls, residual risk, expiry, verification plan, owner/accountable executive, change plan.
- **Compensating control minimums**:
  - Critical: at least two strong controls (e.g., WAF + ACL/EDR) with config + telemetry proof.
  - High: at least one strong control with verification.
  - Medium: recommended if durable fix >30 days.
  - Low: optional; document rationale if none.
- **Approvals**: see Appendix B.
- **Expiry & renewal**: Critical ≤30 days, High ≤60, Medium ≤90, Low ≤120. Renewal requires updated residual risk and plan; caps on consecutive waivers (Critical 1, High 2, Medium 3, Low 3).
- **Workflow**: request → policy checks → approval routing → monitor → expiry/closure; system enforces CC minimums, decision SLAs, auto-reopen on expiry or CC failure.
- **Reporting**: dashboards for active waivers, expiries, residual risk, KEV/internet-exposed waivers; maintain immutable waiver register; quarterly audit.

---

## 6. Identity & Ownership Rules
- **Asset identity precedence**: Cloud resource ID → Scanner/agent ID → Hostname/FQDN → MAC/Hardware UUID → IP address.
- **Implementation**: store all observed IDs; canonical key is highest-precedence. Re-link when higher-precedence ID discovered.
- **Ownership fallback**:
  1. CMDB relationships.
  2. Tags/metadata (cloud tags, k8s labels).
  3. Environment/location-based provisional owner (e.g., Cloud Ops, Net Ops), with SLA for confirmation.
  4. Linkage Review queue if owner remains unknown.
- **Linkage Review queue**:
  - SLA: Critical/High confirmed ≤3 business days; Medium/Low ≤10 business days.
  - Managed by Cybersecurity/GRC; escalate to governance council if overdue.
  - Track attempts, resolution, final owner; target <5% unmapped assets.

---

## 7. Chat Agent Row-Level Security
- User context derived from EasyAuth/JWT claims (`user_roles`, `groups`, `applications`) is normalized and mapped to `ChatScope`.
- Role, group, and application mappings are stored in Key Vault JSON (e.g., `chat_rls_role_mapping.json`) and cached by the application; Security owns change control.
- `ChatAccessPolicy` enforces scope (applications/owner groups) before Cosmos queries; missing scope raises `AccessDeniedError` unless a configured fallback owner group applies.
- `/api/chat` and planner-driven flows log resolved scope in `runs_events.metrics.scope`; AccessDenied is logged at WARN for audit trails.
- See `docs/ChatAgent_RLS_Policy.md` for detailed mapping rules, logging expectations, and governance cadence.

---

## 8. Credential & Integration Strategy
- **Key Vault**: central credential store; agents use system-assigned managed identity with get/list permissions only.
- **Integrations**:
  - Qualys: service account user/password; rotate every 90 days.
  - Defender for Cloud: managed identity (Security Reader); no secrets.
  - Jira Assets/ITSM: service account PAT; rotate every 90 days.
  - Defender TI: managed identity (Threat Intelligence Reader).
  - KEV feed: public.
  - NVD: API key; rotate annually.
  - Power BI: Azure AD app registration (secret or cert); rotate annually; workspace contributor role with dataset/workspace RW scopes.
- **Governance**: credential register, rotation alerts, MFA for service accounts, quarterly review.

---

## 8. Data Residency & Retention
- **Residency**:
  - Primary region: Canada Central. Secondary: Canada East (geo-redundant reads, manual failover).
  - Analytics exports remain in-region. No cross-region diagnostics/logs.
  - Continuous backup (PITR) with 30-day retention; restore operations stay within region pair.
- **Retention defaults**:
  - `findings_raw`: 90 days; optional Blob archive ≤12 months; redact secrets; legal holds override TTL.
  - `findings_canonical`: 24 months; optional minimal index or cold export; legal holds allowed.
  - `triage_items`: 36 months; append-only; legal holds.
  - `tickets`: 36 months post-Verified (or 18 months post-Resolved without verification); maintain stub/export.
  - `evidence`: 60 months; artifacts in Blob; metadata TTL must align with Blob retention; legal holds.
- **Lifecycle**: container TTLs with item overrides; soft-delete patterns; nightly export to Blob; lifecycle rules (hot→cool→archive); quarterly restore drill; schema versioning; purge audits.
- **Privacy**: no secrets or personal identifiers; data minimization; classification tags (`data_class`, `region_origin`); document subject access process.
- **Data Model**: Pydantic classes (`RawFinding`, `CanonicalFinding`, `TriageRecord`, `RemediationUnitRecord`, `TicketRecord`, `EvidenceRecord`, `AssetRecord`, `WaiverRecord`, etc.) encode governance metadata (`ttl_seconds`, `legal_hold`, `data_class`, `region_origin`) and align to the identity, SLA, verification, and waiver rules described in this handbook.

---

## 9. Reporting & Audit Expectations
- **Dashboards**: backlog vs SLA, verification timers, reopen reasons, residual risk trend, KEV coverage, waivers by tier/BU/environment, Linkage Review metrics.
- **Audit**: immutable records for plans, triage, remediations, verifications, waivers; quarterly audit sampling; store residual risk with each decision.

---

## 10. Change Control & Emergency Windows
- **Normal windows**: production follows CAB schedule (weekly/bi-weekly); UAT at least 24h before PROD; DEV/INT business hours; respect BU blackouts.
- **Emergency windows**:
  - Available for Critical or unacceptable scenarios; requires on-call duty manager + security on-call; post-facto CAB ≤2 business days.
  - CONFIG/PATCH can deploy immediately with rollback plan; CODE emergencies only if CONTROLs insufficient.
  - Document residual risk and emergency rationale.
- **Blackouts**: recorded per BU; Critical/unacceptable items may bypass with executive approval.

---

## 11. Glossary & References
- **Canonical ID**: Stable identifier for a vulnerability-on-asset (asset key + vuln key + location + evidence fingerprint).
- **Residual risk**: Risk after remediation/controls; recalculated post-verification/waiver.
- **KEV**: Known Exploited Vulnerabilities list (CISA).
- **SBOM**: Software Bill of Materials.
- **CC**: Compensating Control.
- **Linkage Review**: Queue for vulnerabilities without confirmed owner/application.

**References**:
- Risk Methodology (internal document)
- SLA tables (Appendix A)
- Waiver matrix (Appendix B)
- Verification evidence combinations (Appendix C)
- Chat Agent RLS Policy (`docs/ChatAgent_RLS_Policy.md`)

---

## Appendix A – SLA Tables

### PATCH Remediation Bucket

| Risk Tier | Environment | Assignment SLA | Completion SLA | Verification SLA |
|-----------|-------------|----------------|----------------|------------------|
| Critical  | PROD        | 2 hours        | 48 hours (emergency OK) | 24 hours (re-scan + config proof; add probe if internet/crown jewel) |
| Critical  | UAT/STG     | 4 hours        | 72 hours       | 24 hours |
| Critical  | DEV/INT     | 8 hours        | 5 business days | 2 business days |
| High      | PROD        | 1 business day | 5 calendar days | 2 business days |
| High      | UAT/STG     | 1 business day | 7 calendar days | 3 business days |
| High      | DEV/INT     | 2 business days | 12 calendar days | 3 business days |
| Medium    | PROD        | 3 business days | 20 calendar days | 5 business days |
| Medium    | UAT/STG     | 5 business days | 30 calendar days | 5 business days |
| Medium    | DEV/INT     | 5 business days | 45 calendar days | 5 business days |
| Low (incl. Very Low) | Any | 10 business days | 90 calendar days | 10 business days |

### CONFIG Remediation Bucket

| Risk Tier | Environment | Assignment SLA | Completion SLA | Verification SLA |
|-----------|-------------|----------------|----------------|------------------|
| Critical  | PROD        | 2 hours        | 24 hours (emergency OK) | 24 hours (config proof + functional probe) |
| Critical  | UAT/STG     | 4 hours        | 48 hours       | 24 hours |
| Critical  | DEV/INT     | 8 hours        | 3 business days | 2 business days |
| High      | PROD        | 1 business day | 5 calendar days | 2 business days |
| High      | UAT/STG     | 1 business day | 7 calendar days | 3 business days |
| High      | DEV/INT     | 2 business days | 10 calendar days | 3 business days |
| Medium    | PROD        | 3 business days | 15 calendar days | 5 business days |
| Medium    | UAT/STG     | 5 business days | 25 calendar days | 5 business days |
| Medium    | DEV/INT     | 5 business days | 35 calendar days | 5 business days |
| Low (incl. Very Low) | Any | 10 business days | 60 calendar days | 10 business days |

### CODE Remediation Bucket

| Risk Tier | Environment | Assignment SLA | Completion SLA | Verification SLA |
|-----------|-------------|----------------|----------------|------------------|
| Critical  | PROD        | 4 hours        | 10 calendar days (apply CONTROL if code delayed) | 3 business days (change record + SBOM diff + focused test) |
| Critical  | UAT/STG     | 8 hours        | 12 calendar days | 3 business days |
| Critical  | DEV/INT     | 1 business day | 12 calendar days | 3 business days |
| High      | PROD        | 2 business days | 20 calendar days | 5 business days |
| High      | UAT/STG     | 2 business days | 25 calendar days | 5 business days |
| High      | DEV/INT     | 3 business days | 30 calendar days | 5 business days |
| Medium    | PROD        | 5 business days | 45 calendar days | 7 business days |
| Medium    | UAT/STG     | 7 business days | 60 calendar days | 7 business days |
| Medium    | DEV/INT     | 7 business days | 75 calendar days | 7 business days |
| Low (incl. Very Low) | Any | 10 business days | 120 calendar days | 10 business days |

### CONTROL (Compensating Controls)

| Risk Tier | Environment | Assignment SLA | Completion SLA | Verification SLA |
|-----------|-------------|----------------|----------------|------------------|
| Critical  | PROD        | 1 hour         | 24 hours       | 24 hours (policy + telemetry; control reduces exposure until durable fix) |
| Critical  | UAT/STG     | 2 hours        | 24 hours       | 24 hours |
| Critical  | DEV/INT     | 4 hours        | 2 business days | 2 business days |
| High      | Any         | 1 business day | 3 business days | 2 business days |
| Medium    | Any         | 3 business days | 10 business days | 5 business days |
| Low (incl. Very Low) | Any | 5 business days | 20 business days | 5 business days |

---

## Appendix B – Waiver Approver Matrix

| Risk Tier | Initial Review | Final Approval (minimum) | Executive Notice | Comments |
|-----------|----------------|---------------------------|------------------|----------|
| Critical (20–25) | Security Lead + Platform Lead | CISO (or delegate) + App VP/BU Head | Mandatory | Privacy/Compliance co-sign if regulated data or safety impact. |
| High (12–16) | Security Lead + Platform Lead | Security Director + App/Product Director | Required if internet-exposed or regulated data | Privacy/Compliance co-sign as needed. |
| Medium (5–10) | VM Program Manager | Security Manager | Optional | Waiver caps apply (≤3 consecutive). |
| Low (1–4) | VM Analyst | VM Lead | Not required | Document rationale if no CC applied. |

Decision SLAs: Critical ≤8 business hours, High ≤2 business days, Medium/Low ≤5 business days. Approvers may not self-approve; implementers cannot be final approvers.

---

## Appendix C – Evidence Combinations

| Risk Tier | Bucket | Required Evidence | Notes |
|-----------|--------|-------------------|-------|
| Critical  | PATCH  | Targeted re-scan **and** config/state proof; add functional probe for internet-exposed/crown jewel assets. | Elevate to Critical whenever unacceptable outcomes are possible. |
| Critical  | CONFIG | Config/state proof **and** functional probe. | |
| Critical  | CODE   | Change record + build/PR + SBOM/library diff **and** focused security test/probe. | Add re-scan when signature-based. |
| Critical  | CONTROL | Control policy in effect **and** telemetry showing coverage/blocks. | CONTROL reduces exposure until durable fix; does not close the finding. |
| High      | PATCH  | Any two of: targeted re-scan, config/state proof, functional probe (prefer re-scan + config). | |
| High      | CONFIG | Config/state proof **and** either functional probe or targeted re-scan. | |
| High      | CODE   | Change record + SBOM/library diff **and** focused test or targeted re-scan (when available). | |
| High      | CONTROL | Policy in effect **and** one telemetry sample confirming enforcement. | |
| Medium    | PATCH  | Config/state proof or targeted re-scan (both encouraged when feasible). | If unacceptable scenario arises, treat as High. |
| Medium    | CONFIG | Config/state proof (functional probe recommended for external-facing services). | |
| Medium    | CODE   | Change record + build/PR **and** unit/integration test or SBOM diff. | |
| Medium    | CONTROL | Policy in effect (telemetry recommended). | |
| Low (inc. Very Low) | Any | One primary artifact per bucket: PATCH → config proof or re-scan; CONFIG → config proof; CODE → change record + SBOM diff or unit test; CONTROL → policy in effect. | Treat as next tier if unacceptable scenario flagged. |

Evidence quality criteria: scope match, timestamp after change (within verification window), authentic source, reproducible (commands/queries), traceable (stored in evidence collection with ticket/canonical IDs).

Verification deadlines: Critical 24–72h; High ≤5 business days; Medium ≤7 business days; Low ≤10 business days.

Auto-reopen triggers: missing/invalid evidence, recurrence within 30 days, probe failure, control expiry/disabled, change rollback, policy triggers requiring stronger proof.

---

**Change Log**
- YYYY-MM-DD – Initial version capturing risk methodology, SLA tables, verification evidence combinations, waiver governance, identity/ownership rules, credential strategy, and data policies.
