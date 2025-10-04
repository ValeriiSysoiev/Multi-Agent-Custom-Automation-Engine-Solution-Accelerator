"""Agent that coordinates enrichment operations."""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

from context.cosmos_memory_kernel import CosmosMemoryContext
from kernel_agents.agent_base import BaseAgent
from kernel_tools.enrichment_tools import EnrichmentTools
from models.messages_kernel import AgentType
from semantic_kernel.functions import KernelFunction


class EnrichmentAgent(BaseAgent):
    """Agent responsible for enriching canonical findings with business and threat context."""

    def __init__(
        self,
        session_id: str,
        user_id: str,
        memory_store: CosmosMemoryContext,
        tools: Optional[List[KernelFunction]] = None,
        system_message: Optional[str] = None,
        agent_name: str = AgentType.ENRICHMENT.value,
        client=None,
        definition=None,
    ) -> None:
        if not tools:
            tool_funcs = EnrichmentTools.get_all_kernel_functions()
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
    async def create(cls, **kwargs: Dict[str, str]) -> "EnrichmentAgent":
        session_id = kwargs.get("session_id")
        user_id = kwargs.get("user_id")
        memory_store = kwargs.get("memory_store")
        tools = kwargs.get("tools")
        system_message = kwargs.get("system_message")
        agent_name = kwargs.get("agent_name")
        client = kwargs.get("client")

        try:
            logging.info("Initializing EnrichmentAgent definition")
            definition = await cls._create_azure_ai_agent_definition(
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
                definition=definition,
            )
        except Exception as exc:  # pragma: no cover - defensive logging
            logging.error("Failed to create EnrichmentAgent: %s", exc)
            raise

    @staticmethod
    def default_system_message(agent_name: Optional[str] = None) -> str:
        return (
            "You are the Enrichment Agent for the AI Vulnerability Management platform. "
            "Use the provided tools to attach asset ownership, business context, and threat intelligence "
            "to canonical findings. Prioritise filling ownership gaps and capture a concise summary of your run."
        )


__all__ = ["EnrichmentAgent"]
