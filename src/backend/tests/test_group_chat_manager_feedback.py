from typing import Any, Dict, List, Optional

import pytest

from kernel_agents.group_chat_manager import GroupChatManager
from models.messages_kernel import (
    AgentMessage,
    AgentType,
    HumanFeedback,
    HumanFeedbackStatus,
    InputTask,
    Plan,
    Step,
    StepStatus,
)


class _FakeMemoryStore:
    def __init__(self) -> None:
        self._plan: Optional[Plan] = None
        self.steps: Dict[str, Step] = {}
        self.messages: List[AgentMessage] = []

    async def add_plan(self, plan: Plan) -> None:
        self._plan = plan

    async def update_plan(self, plan: Plan) -> None:
        self._plan = plan

    async def get_plan_by_session(self, session_id: str) -> Optional[Plan]:
        return self._plan

    async def add_step(self, step: Step) -> None:
        self.steps[step.id] = step

    async def update_step(self, step: Step) -> None:
        self.steps[step.id] = step

    async def get_step(self, step_id: str, session_id: str) -> Optional[Step]:
        return self.steps.get(step_id)

    async def get_steps_by_plan(self, plan_id: str) -> List[Step]:
        return list(self.steps.values())

    async def add_item(self, item: AgentMessage) -> None:
        if isinstance(item, AgentMessage):
            self.messages.append(item)


class _DummyAgent:
    def __init__(self) -> None:
        self.requests: List[Any] = []

    async def handle_action_request(self, action_request) -> None:  # pragma: no cover - simple stub
        self.requests.append(action_request)


class _DummyPlanner:
    def __init__(self) -> None:
        self.requests: List[InputTask] = []

    async def handle_input_task(self, task: InputTask) -> None:  # pragma: no cover - simple stub
        self.requests.append(task)


def _make_manager(memory: _FakeMemoryStore, agent_map: Dict[str, Any]) -> GroupChatManager:
    manager = object.__new__(GroupChatManager)
    manager._memory_store = memory
    manager._agent_instances = agent_map
    manager._user_id = "user"
    manager._available_agents = list(agent_map.keys())
    manager._agent_tools_list = []
    manager._agent_name = AgentType.GROUP_CHAT_MANAGER.value
    manager._azure_ai_agent = None
    return manager


@pytest.mark.asyncio
async def test_handle_human_feedback_rejects_step_without_update():
    memory = _FakeMemoryStore()
    plan = Plan(session_id="sid", user_id="user", initial_goal="demo", summary="demo summary")
    await memory.add_plan(plan)

    step = Step(
        plan_id=plan.id,
        session_id="sid",
        user_id="user",
        action="Run ingestion for Qualys",
        agent=AgentType.INGESTION,
    )
    await memory.add_step(step)

    dummy_agent = _DummyAgent()
    planner_stub = _DummyPlanner()
    manager = _make_manager(
        memory,
        {
            AgentType.PLANNER.value: planner_stub,
            AgentType.INGESTION.value: dummy_agent,
        },
    )

    feedback = HumanFeedback(
        plan_id=plan.id,
        session_id="sid",
        approved=False,
        human_feedback="Need to adjust scope",
        step_id=step.id,
    )

    await manager.handle_human_feedback(feedback)

    stored_step = memory.steps[step.id]
    assert stored_step.status == StepStatus.rejected
    assert stored_step.human_approval_status == HumanFeedbackStatus.rejected
    assert not dummy_agent.requests  # no downstream agent invoked
    assert planner_stub.requests, "Planner should be invoked to regenerate plan after rejection"
    replan_request = planner_stub.requests[0]
    assert replan_request.metadata["replan_of"] == plan.id
    assert replan_request.metadata["rejected_step_id"] == step.id


@pytest.mark.asyncio
async def test_handle_human_feedback_rejects_with_updated_action_triggers_reexecution():
    memory = _FakeMemoryStore()
    plan = Plan(session_id="sid", user_id="user", initial_goal="demo", summary="demo summary")
    await memory.add_plan(plan)

    step = Step(
        plan_id=plan.id,
        session_id="sid",
        user_id="user",
        action="Run ingestion for Qualys",
        agent=AgentType.TRIAGE,
    )
    await memory.add_step(step)

    dummy_agent = _DummyAgent()
    planner_stub = _DummyPlanner()
    manager = _make_manager(
        memory,
        {
            AgentType.PLANNER.value: planner_stub,
            AgentType.TRIAGE.value: dummy_agent,
        },
    )

    feedback = HumanFeedback(
        plan_id=plan.id,
        session_id="sid",
        approved=False,
        human_feedback="Use remediation-specific scoring",
        updated_action="Recalculate risk score with compensating controls",
        step_id=step.id,
    )

    await manager.handle_human_feedback(feedback)

    stored_step = memory.steps[step.id]
    assert stored_step.status == StepStatus.action_requested
    assert stored_step.updated_action == "Recalculate risk score with compensating controls"
    assert dummy_agent.requests, "Updated action should trigger downstream agent execution"
    request = dummy_agent.requests[0]
    assert "Recalculate risk score" in request.action
    assert not planner_stub.requests, "Planner should not be re-invoked when updated action is supplied"
