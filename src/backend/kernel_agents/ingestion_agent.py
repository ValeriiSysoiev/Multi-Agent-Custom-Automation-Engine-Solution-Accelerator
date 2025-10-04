import json
import logging
from typing import Dict, List, Optional

from context.cosmos_memory_kernel import CosmosMemoryContext
from kernel_agents.agent_base import BaseAgent
from kernel_tools.ingestion_tools import IngestionTools
from event_utils import track_event_if_configured
from models.messages_kernel import (
    ActionRequest,
    ActionResponse,
    AgentMessage,
    AgentType,
    StepStatus,
)
from semantic_kernel.functions import KernelFunction


class IngestionAgent(BaseAgent):
    """Agent responsible for orchestrating scanner ingestion runs."""

    def __init__(
        self,
        session_id: str,
        user_id: str,
        memory_store: CosmosMemoryContext,
        tools: Optional[List[KernelFunction]] = None,
        system_message: Optional[str] = None,
        agent_name: str = AgentType.INGESTION.value,
        client=None,
        definition=None,
    ) -> None:
        if not tools:
            tool_funcs = IngestionTools.get_all_kernel_functions()
            tools = [KernelFunction.from_method(func) for func in tool_funcs.values()]

        if not system_message:
            system_message = self.default_system_message(agent_name)

        super().__init__(
            agent_name=agent_name,
            session_id=session_id,
            user_id=user_id,
            memory_store=memory_store,
            tools=tools,
            system_message=system_message,
            client=client,
            definition=definition,
        )

    @classmethod
    async def create(
        cls,
        **kwargs: Dict[str, str],
    ) -> "IngestionAgent":
        session_id = kwargs.get("session_id")
        user_id = kwargs.get("user_id")
        memory_store = kwargs.get("memory_store")
        tools = kwargs.get("tools")
        system_message = kwargs.get("system_message")
        agent_name = kwargs.get("agent_name")
        client = kwargs.get("client")

        try:
            logging.info("Initializing IngestionAgent definition")

            agent_definition = await cls._create_azure_ai_agent_definition(
                agent_name=agent_name,
                instructions=system_message or cls.default_system_message(agent_name),
                temperature=0.0,
                response_format=None,
            )

            return cls(
                session_id=session_id,
                user_id=user_id,
                memory_store=memory_store,
                tools=tools,
                system_message=system_message,
                agent_name=agent_name,
                client=client,
                definition=agent_definition,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logging.error("Failed to create Azure AI Agent for IngestionAgent: %s", exc)
            raise

    @staticmethod
    def default_system_message(agent_name: Optional[str] = None) -> str:
        return (
            "You are the Ingestion Agent for the AI Vulnerability Management platform. "
            "Run the provided ingestion tools to collect vulnerability findings from Qualys and Defender, "
            "update Cosmos DB, and summarize the results. Report scanner coverage, counts of processed findings, "
            "and any notable errors."
        )

    @property
    def plugins(self):
        return IngestionTools.get_all_kernel_functions()

    async def handle_action_request(self, action_request: ActionRequest) -> str:
        step = await self._memory_store.get_step(
            action_request.step_id, action_request.session_id
        )

        if not step:
            response = ActionResponse(
                step_id=action_request.step_id,
                plan_id=action_request.plan_id,
                session_id=action_request.session_id,
                result="Step not found in memory.",
                status=StepStatus.failed,
            )
            return response.json()

        try:
            raw_summary = await IngestionTools.run_ingestion_cycle()
            summary = self._parse_summary(raw_summary)
            message_text = self._format_summary(summary)
            status = StepStatus.completed
        except Exception as exc:  # pragma: no cover - defensive guard
            logging.exception("Ingestion pipeline failed: %s", exc)
            message_text = f"Ingestion pipeline failed: {exc}"
            status = StepStatus.failed

        step.status = status
        step.agent_reply = message_text
        await self._memory_store.update_step(step)

        await self._memory_store.add_item(
            AgentMessage(
                session_id=action_request.session_id,
                user_id=self._user_id,
                plan_id=action_request.plan_id,
                content=message_text,
                source=self._agent_name,
                step_id=action_request.step_id,
            )
        )

        track_event_if_configured(
            "Ingestion agent completed step",
            {
                "session_id": action_request.session_id,
                "user_id": self._user_id,
                "plan_id": action_request.plan_id,
                "step_id": action_request.step_id,
                "status": status,
            },
        )

        response = ActionResponse(
            step_id=action_request.step_id,
            plan_id=action_request.plan_id,
            session_id=action_request.session_id,
            result=message_text,
            status=status,
        )

        return response.json()

    @staticmethod
    def _parse_summary(raw_summary: str) -> Dict[str, object]:
        try:
            return json.loads(raw_summary) if raw_summary else {}
        except json.JSONDecodeError:
            return {"raw": raw_summary or ""}

    @staticmethod
    def _format_summary(summary: Dict[str, object]) -> str:
        total_ingested = summary.get("total_ingested")
        total_enriched = summary.get("total_enriched")
        scanners: List[Dict[str, object]] = summary.get("scanners") or []

        if summary.get("raw"):
            return str(summary.get("raw"))

        lines: List[str] = ["Ingestion pipeline completed."]

        if total_ingested is not None:
            lines.append(f"Total findings ingested: {total_ingested}")
        if total_enriched is not None:
            lines.append(f"Total findings enriched: {total_enriched}")

        if scanners:
            lines.append("Scanner breakdown:")
            for scanner in scanners:
                name = scanner.get("scanner", "unknown")
                processed = scanner.get("processed", 0)
                canonical = scanner.get("canonical_count", 0)
                lines.append(
                    f"- {name}: processed {processed} findings (canonical {canonical})"
                )
        else:
            lines.append("No findings were ingested during this run.")

        return "\n".join(lines)
