import logging
from typing import Dict, List, Optional

from context.cosmos_memory_kernel import CosmosMemoryContext
from kernel_agents.agent_base import BaseAgent
from kernel_tools.verification_tools import VerificationTools
from models.messages_kernel import AgentType
from semantic_kernel.functions import KernelFunction


class VerificationAgent(BaseAgent):
    """Agent orchestrating verification of remediation evidence."""

    def __init__(
        self,
        session_id: str,
        user_id: str,
        memory_store: CosmosMemoryContext,
        tools: Optional[List[KernelFunction]] = None,
        system_message: Optional[str] = None,
        agent_name: str = AgentType.VERIFICATION.value,
        client=None,
        definition=None,
    ) -> None:
        if not tools:
            tool_funcs = VerificationTools.get_all_kernel_functions()
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
    ) -> "VerificationAgent":
        session_id = kwargs.get("session_id")
        user_id = kwargs.get("user_id")
        memory_store = kwargs.get("memory_store")
        tools = kwargs.get("tools")
        system_message = kwargs.get("system_message")
        agent_name = kwargs.get("agent_name")
        client = kwargs.get("client")

        try:
            logging.info("Initializing VerificationAgent definition")
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
        except Exception as exc:  # pragma: no cover
            logging.error("Failed to create Azure AI Agent for VerificationAgent: %s", exc)
            raise

    @staticmethod
    def default_system_message(agent_name: Optional[str] = None) -> str:
        return (
            "You are the Verification Agent for the AI Vulnerability Management platform. "
            "Review remediation tickets awaiting evidence, apply the verification policy, update ticket status, "
            "and summarize accepted vs rejected evidence." 
        )

    @property
    def plugins(self):
        return VerificationTools.get_all_kernel_functions()
