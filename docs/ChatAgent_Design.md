# Chat Agent Design

## Purpose & Scope
- Provide a natural-language assistant that answers questions using the authoritative data stored in Cosmos DB (findings, enrichment, triage, remediation, tickets, waivers, assets, runs).
- Serve security, risk, and operations personas with filtered insights that respect row-level access controls and audit requirements.
- Integrate with existing agent orchestration (`PlannerAgent` / `GroupChatManager`) without introducing new UI dependencies. The chat agent must be callable both from the planner and via a dedicated API endpoint for future frontend integration.

## Core Requirements
1. **Ground-Truth Responses**: Only data persisted in Cosmos DB is allowed; no live calls to scanners, Jira, or Power BI. Every answer must reference the underlying records (canonical IDs, remediation unit IDs, ticket keys, waiver IDs).
2. **Row-Level Security (RLS)**: Enforce role-based filters (e.g., platform teams, application owners, executives) so users only see assets, remediation units, tickets, and waivers within their scope. RLS logic must be deterministic and auditable.
3. **Auditability**: Log every query, applied filters, and returned IDs to `runs_events` (new `chat_qa` run_type). Store the rendered citations so auditors can reconstruct responses.
4. **Prompt Hygiene**: The LLM prompt must strictly instruct the model to answer with JSON and cite IDs. No creative speculation; if data is missing, the model must respond with an explicit “not found” message.
5. **Extensibility**: Support future expansion (e.g., conversational follow-ups, linkage review prompts) without reworking core architecture.

## Target Personas & Example Queries
| Persona | Example Questions |
|---------|-------------------|
| Platform Ops | “Show me High or Critical findings assigned to Platform Operations that are overdue.” |
| App Owner | “Which vulnerabilities are open on Customer Web and what are their remediation statuses?” |
| Risk/GRC | “List waivers expiring in the next 30 days and the pending approvals.” |
| Executive | “Summarise open KEV exposures by business service.” |

## Data Sources & Repositories
- `assets` (`AssetRepository`)
- `findings_canonical` (`CanonicalFindingRepository`)
- `enrichments` (`EnrichmentRepository`)
- `triage_items` (`TriageRepository`)
- `remediation_units` (`RemediationUnitRepository`)
- `tickets` (`TicketRepository`)
- `waivers` (`WaiverRepository`)
- `runs_events` (`RunEventRepository`) for telemetry

Each repository already handles Cosmos partitioning and serialisation. The chat agent will compose queries across repositories using filtered access scopes.

## Query Strategy
1. **Intent → Query Template Mapping**
   - Implement a lightweight intent classifier (rule-based + few-shot examples) to map questions onto predefined query templates (e.g., `open_findings_by_owner`, `waivers_due`, `tickets_by_risk`, `kev_exposures`, `executive_summary`). *(Implemented: classifier now handles KEV- and executive-summary requests alongside the original backlog intents.)*
   - Templates define required filters, optional aggregations, sort order, and output fields. This keeps Cosmos queries deterministic and prevents arbitrary SQL injection. *(Implemented: chat service shares a context loader across finding/KEV templates so new personas reuse the same logic.)*

2. **Template Execution**
   - For each template, build repository helper functions that accept the normalized filters (risk tier, application, due window, etc.) and return a structured payload ready for the LLM.
   - Where templates require multi-step aggregation (e.g., join Canonical → Remediation → Ticket), execute sequential repository calls and assemble the combined response in Python.

3. **Citation Bundle**
   - Each response includes `citations`: list of `{type, id, url?}` entries referencing canonical IDs, remediation unit IDs, ticket keys, waiver IDs, asset IDs.
   - Provide optional deep-link URLs (e.g., Jira ticket browse link, planned UI path) if available.

## Access Control & RLS
- **User Context**: Extend the planner request context to include `user_id`, `roles`, `team_ids`, `application_scopes`, and `is_exec`. Pull these from the API gateway or JWT claims.
- **Scope Filters**:
  - Platform teams → remediation units / tickets where `owner` matches team.
  - Application owners → assets/application context matching their app IDs.
  - Executives → broader access but still scoped to organisation (no tenant leakage).
- Implement a `ChatAccessPolicy` helper that computes allowed asset IDs / remediation unit IDs ahead of query execution and passes them to repository calls. Deny queries outright if scope resolves to empty.

## Prompt & Response Schema
- **System Prompt**:
  - Describe available data categories and instruct the model to stay factual, cite IDs, and answer in JSON.
  - Include fallback instructions (“If the answer cannot be derived from provided data, return `{ "answer": null, "reason": "not_found" }`”).

- **Response JSON Schema**:
  ```json
  {
    "answer": [
      {
        "summary": string,
        "details": { ... typed per template ... },
        "citations": [
          { "type": "canonical_finding", "id": "canon-web-01" },
          { "type": "ticket", "id": "SEED-TICKET-001", "url": "https://..." }
        ]
      }
    ],
    "metadata": {
      "query_template": "open_findings_by_owner",
      "filters": { ... },
      "limit": number
    }
  }
  ```

## Telemetry
- Log each chat invocation to `runs_events` with fields:
  - `agent_name=Chat_Agent`
  - `run_type="chat_qa"`
  - `metrics`: `{ "template": ..., "result_count": n, "rls_scope_count": m }`
  - `error`: populated on failure/denied scope

## Integration Plan
1. **Agent Factory**: Add `ChatAgent` registration to `AgentFactory` with dependency injection for repositories, access policy, and telemetry client.
2. **Planner**: Teach `PlannerAgent` to route `ChatRequest` intents to the chat agent (alongside ingestion/triage/remediation). Update `GroupChatManager` to support chat responses in conversation flow.
3. **API Surface**: Add `/api/chat` endpoint that invokes the chat agent directly with provided user context. Reuse same logic as planner to avoid duplication. *(Implemented 27 Sep – FastAPI route returning `ChatAnswer` models with RLS enforcement.)*
4. **Configuration**: Extend `app_config` / `config_kernel` to include chat-specific settings (default result limits, allowed templates, audit flag).

## Implementation Steps
1. Finalise intent → template catalogue (`chat_templates.yml`).
2. Build `ChatAccessPolicy` to resolve scopes.
3. Implement `ChatAgent` class + `ChatTools` (intent resolver, template executor, summarizer).
4. Add tests covering:
   - Intent classification
   - RLS enforcement (denied vs. scoped queries)
   - Citation format
   - Planner integration (ensuring chat tasks return structured responses)
5. Wire telemetry + API endpoint.
6. Document operational playbook: sample prompts, expected outputs, alerting on failures.

## Open Questions
- Detailed role mapping and source of user context (identity provider claims vs. custom mapping).
- Consent/monitoring requirements for query logs (GDPR/audit retention).
- How to handle long-form outputs (pagination vs. summarisation).
