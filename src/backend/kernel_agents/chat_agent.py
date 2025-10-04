"""Chat agent orchestrating QA responses over Cosmos data."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Dict, List, Optional

from app_config import config
from context.cosmos_memory_kernel import CosmosMemoryContext
from event_utils import track_event_if_configured
from kernel_agents.agent_base import BaseAgent
from models.messages_kernel import (ActionRequest, ActionResponse, AgentMessage,
                                    AgentType, StepStatus)
from semantic_kernel.functions import KernelFunction
from services.chat_access_policy import AccessDeniedError
from services.chat_service import ChatService

try:  # pragma: no cover - optional dependency during unit tests
    from azure.ai.agents.models import Agent as AzureAgentModel
except (ModuleNotFoundError, ImportError):  # pragma: no cover - test fallback
    AzureAgentModel = None  # type: ignore

logger = logging.getLogger(__name__)


class ChatAgent(BaseAgent):
    """Agent that answers natural-language questions using stored VM data."""

    def __init__(
        self,
        *,
        session_id: str,
        user_id: str,
        memory_store: CosmosMemoryContext,
        chat_service: ChatService,
        tools: Optional[List[KernelFunction]] = None,
        system_message: Optional[str] = None,
        agent_name: str = AgentType.CHAT.value,
        client=None,
        definition=None,
    ) -> None:
        self._chat_service = chat_service
        if not system_message:
            system_message = self.default_system_message(agent_name)
        super().__init__(
            agent_name=agent_name,
            session_id=session_id,
            user_id=user_id,
            memory_store=memory_store,
            tools=tools or [],
            system_message=system_message,
            client=client,
            definition=definition,
        )

    @classmethod
    async def create(cls, **kwargs: Dict[str, object]) -> "ChatAgent":
        session_id = kwargs.get("session_id")
        user_id = kwargs.get("user_id")
        memory_store = kwargs.get("memory_store")
        chat_service = kwargs.get("chat_service")
        if chat_service is None:
            raise ValueError("chat_service dependency is required for ChatAgent")

        system_message = kwargs.get("system_message")
        agent_name = kwargs.get("agent_name")
        client = kwargs.get("client")
        tools = kwargs.get("tools")
        definition = kwargs.get("definition")

        if definition is None:
            instructions = system_message or cls.default_system_message(agent_name)
            try:
                logger.info("Initializing ChatAgent definition")
                definition = await cls._create_azure_ai_agent_definition(
                    agent_name=agent_name or AgentType.CHAT.value,
                    instructions=instructions,
                    temperature=0.0,
                    response_format=None,
                    client=client,
                )
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.warning(
                    "Falling back to local ChatAgent definition: %s", exc
                )
                if AzureAgentModel is not None:
                    definition = AzureAgentModel(
                        model=config.AZURE_OPENAI_DEPLOYMENT_NAME,
                        name=agent_name or AgentType.CHAT.value,
                        instructions=instructions,
                    )
                else:
                    definition = SimpleNamespace(
                        id=None,
                        name=agent_name or AgentType.CHAT.value,
                        description=None,
                        instructions=instructions,
                        model=config.AZURE_OPENAI_DEPLOYMENT_NAME,
                    )

        return cls(
            session_id=session_id,
            user_id=user_id,
            memory_store=memory_store,
            chat_service=chat_service,
            tools=tools,
            system_message=system_message,
            agent_name=agent_name,
            client=client,
            definition=definition,
        )

    @staticmethod
    def default_system_message(agent_name: Optional[str] = None) -> str:
        return (
            "You are the Chat Agent for the AI Vulnerability Management platform. "
            "Answer questions using only the data returned by your tooling. "
            "Respond with JSON containing an array of results and citations."
        )

    async def handle_action_request(self, action_request: ActionRequest) -> str:
        step = await self._memory_store.get_step(
            action_request.step_id, action_request.session_id
        )
        if not step:
            response = ActionResponse(
                step_id=action_request.step_id,
                status=StepStatus.failed,
                message="Step not found in memory.",
            )
            return response.json()

        try:
            question = action_request.action.strip()
            user_context = getattr(step, "metadata", None)
            payload = await self._chat_service.answer_question(
                question=question,
                user_context=user_context,
            )
            response_content = json.dumps(
                payload,
                default=self._json_serializer,
                ensure_ascii=False,
            )

            await self._memory_store.add_item(
                AgentMessage(
                    session_id=action_request.session_id,
                    user_id=self._user_id,
                    plan_id=action_request.plan_id,
                    content=response_content,
                    source=self._agent_name,
                    step_id=action_request.step_id,
                )
            )
            track_event_if_configured(
                "ChatAgent response stored",
                {
                    "session_id": action_request.session_id,
                    "user_id": self._user_id,
                    "plan_id": action_request.plan_id,
                    "step_id": action_request.step_id,
                    "intent": payload.get("intent"),
                    "result_count": len(payload.get("results", [])),
                },
            )

            step.status = StepStatus.completed
            step.agent_reply = response_content
            await self._memory_store.update_step(step)

            response = ActionResponse(
                step_id=action_request.step_id,
                plan_id=action_request.plan_id,
                session_id=action_request.session_id,
                result=response_content,
                status=StepStatus.completed,
            )
            return response.json()

        except AccessDeniedError as exc:
            logger.warning("Chat access denied: %s", exc)
            error_payload = json.dumps(
                {"error": "access_denied", "message": str(exc)},
                ensure_ascii=False,
            )
            step.status = StepStatus.failed
            step.agent_reply = error_payload
            await self._memory_store.update_step(step)
            await self._memory_store.add_item(
                AgentMessage(
                    session_id=action_request.session_id,
                    user_id=self._user_id,
                    plan_id=action_request.plan_id,
                    content=error_payload,
                    source=self._agent_name,
                    step_id=action_request.step_id,
                )
            )
            track_event_if_configured(
                "ChatAgent access denied",
                {
                    "session_id": action_request.session_id,
                    "user_id": self._user_id,
                    "plan_id": action_request.plan_id,
                    "step_id": action_request.step_id,
                },
            )
            response = ActionResponse(
                step_id=action_request.step_id,
                plan_id=action_request.plan_id,
                session_id=action_request.session_id,
                result=error_payload,
                status=StepStatus.failed,
            )
            return response.json()

        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("ChatAgent failed to answer question: %s", exc)
            step.status = StepStatus.failed
            step.agent_reply = str(exc)
            await self._memory_store.update_step(step)
            response = ActionResponse(
                step_id=action_request.step_id,
                plan_id=action_request.plan_id,
                session_id=action_request.session_id,
                result=json.dumps({"error": "unknown", "message": str(exc)}),
                status=StepStatus.failed,
            )
            return response.json()

    @staticmethod
    def _json_serializer(value):
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.isoformat()
        return value


__all__ = ["ChatAgent"]
