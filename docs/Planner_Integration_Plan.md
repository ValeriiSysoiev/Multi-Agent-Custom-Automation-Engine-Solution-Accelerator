# Multi-Agent Planner Integration Plan (AI VM Transformation)

## Context
The Risk Chat assistant is in production, but the Multi-Agent Planner UI and backend are still aligned with the original accelerator template (HR, Marketing, Procurement flows). Requests from the planner UI currently fail (HTTP 405) because the frontend proxy does not forward planner API calls to the backend. Even when the API is reachable, the backend PlannerAgent and GroupChatManager still advertise the legacy agent roster and instructions, meaning any generated plans would reference the wrong agents/tools. Quick task tiles and copy are also template defaults.

To bring the planner online for the AI Vulnerability Management (AI VM) workflow we need a coordinated front-end and back-end refactor that enables the VM-specific agents (ingestion, deduplication, enrichment, triage, remediation, verification, waiver, reporting, chat) and removes the template personas.

## Current Gaps
- **API proxy**: The App Service FastAPI wrapper exposes `/api/chat` only; all other `/api/*` calls (e.g., `/api/input_task`) return 405 because the route is not forwarded to the backend Container App.
- **Frontend content**: Quick task cards, empty states, and copy mention HR/mobile scenarios instead of VM operations.
- **Agent registry**: `AgentFactory`, `PlannerAgent`, and `GroupChatManager` still register HR/Marketing/etc. and surface their tools to the LLM, so plans would target the wrong agents even after the proxy is fixed.
- **Agent catalog**: No dedicated agent types exist yet for deduplication, enrichment, waiver, or reporting; Planner instructions do not describe the AI VM pipeline.
- **Transformation ledger**: Documentation does not yet track the planner refactor scope or dependencies.

## Target State
- Frontend FastAPI proxy forwards **all** planner/plan execution API routes to the backend (GET/POST/PUT/DELETE) while keeping bespoke handling for `/api/chat` and `/api/user_browser_language`.
- Planner UI surfaces AI VM quick tasks (e.g., *Ingest latest vulnerability scans*, *Review triage backlog*, *Prepare waiver review package*) with relevant icons/copy.
- Backend planner orchestration advertises and instantiates only the AI VM agents:
  - Ingestion, Deduplication, Enrichment, Triage, Remediation, Verification, Waiver, Reporting, Chat, Human (fallback).
  - Planner instructions describe the VM lifecycle, expected sequencing, and human checkpoints.
  - GroupChatManager uses the same roster and routes actions accordingly.
- New agent/tool scaffolding for Deduplication, Enrichment, Waiver, and Reporting as needed with clear TODO items (implementation can be staged after planner refactor if required).
- Transformation docs updated with the new backlog items so downstream engineers can execute work in tracked phases.

## Implementation Tracks
1. **Frontend gateway & UX refresh**
   - Add a catch-all `@app.api_route("/api/{path:path}", methods=[...])` in `frontend_server.py` to proxy planner endpoints (input_task, plans, steps, etc.) to the backend base URL, preserving headers/methods.
   - Update quick task metadata in `src/models/homeInput.tsx` with AI VM scenarios and icons; adjust supporting copy (`HomeInput`, left nav labels if needed).
   - Verify TaskService transformations still clean agent labels once legacy agents are removed (update helper functions accordingly).

2. **Backend agent & planner refactor**
   - Update `AgentType` enum (or at minimum `_available_agents` lists) to remove HR/Marketing/Procurement references and add the VM agents.
   - Extend `AgentFactory` with new agent classes (`DeduplicationAgent`, `EnrichmentAgent`, `WaiverAgent`, `ReportingAgent`) or stubs that wrap existing services.
   - Adjust `PlannerAgent` available agents, tool catalog, and instruction template to reflect the VM lifecycle (ingest → dedup → enrich → triage → remediation → verification → waiver/reporting). Ensure tool documents exist for new agents.
   - Update `GroupChatManager` to the same roster and to cleanly route actions to the new agent types.
   - Ensure plan persistence, messaging, and the UI (`TaskService.cleanTextToSpaces`) recognise the new agent labels.

3. **Documentation & backlog updates**
   - Record this plan in the transformation ledger and status checklist (refer to updates in `docs/Active_Working_Context.md`, `docs/ImplementationStatus.md`, and `docs/Transformation_Issue_Log.md`).
   - Capture testing requirements (API proxy integration, planner smoke tests, agent unit coverage) and deployment notes for future runs.

4. **Validation & rollout**
   - Local smoke tests: run planner API via `uv run pytest tests/handlers/test_input_task_endpoint.py` and manual `/api/input_task` POST.
   - Frontend e2e: use the deployed App Service to create a plan and ensure steps reference AI VM agents.
   - Update runbooks/rollback entries once the new images (frontend + backend) are pushed.

## Open Questions / Dependencies
- Deduplication and enrichment services exist but not as first-class agents/tools. Decide whether to expose them as standalone agents or orchestrate via ingestion.
- Waiver/Reporting agents require tool definitions that call existing services (`WaiverService`, `ReportingExportService`). Scope TBD.
- Production EasyAuth scopes for planner: ensure once anonymous fallback is removed the planner still resolves user context for RLS.

## Next Steps
1. Implement the documentation/backlog updates (this plan, transformation log entries).
2. Execute Track 1 (proxy + UI refresh) to restore planner connectivity.
3. Execute Track 2 in phases, starting with agent roster cleanup (disable legacy agents) before introducing new tool scaffolding.
4. Add automated planner smoke tests post-refactor.

### Additional Technical Considerations (Per Integration Review)
- Proxy shim must support all HTTP verbs **and** streaming responses (SSE/streamed JSON). FastAPI's `StreamingResponse` should be passed through without buffering so future planner updates can emit incremental progress.
- Update `TaskService.cleanTextToSpaces`/`cleanHRAgent` (and related tests) once the legacy agent labels disappear to avoid UI glitches.
- Planner integration tests (`tests/test_planner_agent_integration.py`, `tests/test_group_chat_manager_integration.py`, handler smoke tests) need roster/tool expectations updated in the same PR.
- Seed data is optional; if you want demo-ready plans before live ingestion, re-run `scripts/seed_reporting_data.py` after refactor, but plan to clear it once production ingestion is active.
