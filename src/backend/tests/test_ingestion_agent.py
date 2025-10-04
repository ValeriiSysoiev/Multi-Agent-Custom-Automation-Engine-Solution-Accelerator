import json
import sys
from pathlib import Path
from typing import Dict, Optional

import pytest

TESTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = TESTS_DIR.parent

for path in (BACKEND_DIR, BACKEND_DIR.parent.parent):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)

from kernel_agents.ingestion_agent import IngestionAgent
from kernel_tools.ingestion_tools import IngestionTools
from models.messages_kernel import (
    ActionRequest,
    AgentMessage,
    AgentType,
    HumanFeedbackStatus,
    Plan,
    Step,
    StepStatus,
)


class _FakeMemoryStore:
    def __init__(self) -> None:
        self._plan: Optional[Plan] = None
        self.steps: Dict[str, Step] = {}
        self.messages: list[AgentMessage] = []

    async def get_step(self, step_id: str, session_id: str) -> Optional[Step]:
        step = self.steps.get(step_id)
        if step and step.session_id == session_id:
            return step
        return None

    async def update_step(self, step: Step) -> None:
        self.steps[step.id] = step

    async def add_item(self, item: AgentMessage) -> None:
        self.messages.append(item)


@pytest.mark.asyncio
async def test_ingestion_agent_publishes_summary(monkeypatch):
    summary = {
        "total_ingested": 5,
        "total_enriched": 3,
        "scanners": [
            {"scanner": "qualys_vm", "processed": 3, "canonical_count": 2},
            {"scanner": "defender_mdc", "processed": 2, "canonical_count": 1},
        ],
    }

    async def fake_run_ingestion_cycle() -> str:
        return json.dumps(summary)

    monkeypatch.setattr(
        IngestionTools,
        "run_ingestion_cycle",
        staticmethod(fake_run_ingestion_cycle),
    )

    memory = _FakeMemoryStore()

    step = Step(
        plan_id="plan-1",
        session_id="session-1",
        user_id="user-1",
        action="Run ingestion cycle",
        agent=AgentType.INGESTION,
        human_approval_status=HumanFeedbackStatus.accepted,
    )
    memory.steps[step.id] = step

    agent = object.__new__(IngestionAgent)
    agent._memory_store = memory  # type: ignore[attr-defined]
    agent._user_id = "user-1"  # type: ignore[attr-defined]
    agent._agent_name = AgentType.INGESTION.value  # type: ignore[attr-defined]

    request = ActionRequest(
        step_id=step.id,
        plan_id=step.plan_id,
        session_id=step.session_id,
        action="Run ingestion",
        agent=AgentType.INGESTION,
    )

    response_json = await agent.handle_action_request(request)  # type: ignore[misc]

    updated_step = memory.steps[step.id]
    assert updated_step.status == StepStatus.completed
    assert "Total findings ingested: 5" in updated_step.agent_reply

    assert memory.messages, "Expected ingestion agent to emit a message"
    message = memory.messages[0]
    assert "Scanner breakdown" in message.content
    assert message.source == AgentType.INGESTION.value

    response = json.loads(response_json)
    assert response["status"] == StepStatus.completed
    assert "Total findings enriched: 3" in response["result"]
