import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

try:  # pragma: no branch - prefer real SDK
    import azure.core.exceptions  # type: ignore
except ModuleNotFoundError:  # pragma: no cover - fallback stubs
    import types

    if "azure" not in sys.modules:
        sys.modules["azure"] = types.ModuleType("azure")
    azure_core = sys.modules.setdefault("azure.core", types.ModuleType("azure.core"))
    azure_core_exceptions = sys.modules.setdefault(
        "azure.core.exceptions", types.ModuleType("azure.core.exceptions")
    )

    class ResourceNotFoundError(Exception):
        pass

    azure_core_exceptions.ResourceNotFoundError = ResourceNotFoundError

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from models.messages_kernel import (
    AgentType,
    AssetIdentifier,
    AssetIdentifierType,
    CanonicalFinding,
    FindingLifecycleStatus,
    ResidualRisk,
    RiskTier,
    RiskTreatmentStatus,
    RiskTreatmentTask,
    RiskTreatmentWorkflow,
    RunEventRecord,
)
from services.risk_treatment_sync import RiskTreatmentSync


class MemoryRiskTreatmentRepository:
    def __init__(self, tasks):
        self.tasks = tasks

    async def list_by_status(self, status, *, workflow=None, limit=100):  # noqa: ARG002
        result = [task for task in self.tasks if task.status == RiskTreatmentStatus.IN_PROGRESS]
        return result[:limit]

    async def upsert_task(self, task: RiskTreatmentTask):
        for idx, existing in enumerate(self.tasks):
            if existing.task_id == task.task_id:
                self.tasks[idx] = task
                return task
        self.tasks.append(task)
        return task


class MemoryCanonicalRepository:
    def __init__(self, finding: CanonicalFinding):
        self.finding = finding

    async def get_by_id(self, canonical_id, asset_id):
        if canonical_id == self.finding.canonical_id and asset_id == self.finding.asset_id:
            return self.finding
        return None

    async def upsert_finding(self, finding: CanonicalFinding):
        self.finding = finding
        return finding


class MemoryRunEventRepository:
    def __init__(self):
        self.events = []

    async def upsert_event(self, record: RunEventRecord):
        self.events.append(record)
        return record


class FakeJiraClient:
    def __init__(self, issues):
        self.issues = issues

    async def get_issue_fields(self, issue_key, *, fields=None):  # noqa: ARG002
        if issue_key not in self.issues:
            raise ValueError("Issue not found")
        return {"fields": self.issues[issue_key]}

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_sync_marks_task_completed_and_clears_follow_up():
    now = datetime.now(timezone.utc)
    canonical = CanonicalFinding(
        id="canon-1",
        canonical_id="canon-1",
        asset_id="asset-1",
        asset_identifiers=[AssetIdentifier(id_type=AssetIdentifierType.HOSTNAME, value="vm-1")],
        sources=[],
        vuln_key="CVE-2024-0001",
        severity="high",
        risk_tier=RiskTier.HIGH,
        status=FindingLifecycleStatus.TRIAGED,
        remediation_unit_id=None,
        treatment_follow_up_id="rt-1",
    )

    task = RiskTreatmentTask(
        id="rt-1",
        task_id="rt-1",
        canonical_id="canon-1",
        triage_id="tri-1",
        asset_id="asset-1",
        workflow=RiskTreatmentWorkflow.WAIVER,
        treatment="accept",
        risk_tier=RiskTier.HIGH,
        residual_risk=ResidualRisk(risk_tier=RiskTier.MEDIUM),
        status=RiskTreatmentStatus.IN_PROGRESS,
        ticket_key="CYB-100",
    )

    risk_repo = MemoryRiskTreatmentRepository([task])
    jira = FakeJiraClient(
        {
            "CYB-100": {
                "status": {"name": "Approved"},
                "customfield_10084": {"value": "Approved"},
                "customfield_10083": (now + timedelta(days=30)).isoformat(),
            }
        }
    )
    run_repo = MemoryRunEventRepository()

    syncer = RiskTreatmentSync(
        risk_repo=risk_repo,
        canonical_repo=MemoryCanonicalRepository(canonical),
        jira_ticket_client=jira,
        run_repo=run_repo,
    )

    metrics = await syncer.sync(limit=10)

    assert metrics["completed"] == 1
    assert metrics["waiver_completed"] == 1
    assert metrics["transfer_completed"] == 0
    updated_task = risk_repo.tasks[0]
    assert updated_task.status == RiskTreatmentStatus.COMPLETED
    assert updated_task.ticket_status == "Approved"
    assert updated_task.last_error is None
    assert updated_task.last_synced_at is not None
    assert canonical.treatment_follow_up_id is None
    assert canonical.status == FindingLifecycleStatus.WAIVED


@pytest.mark.asyncio
async def test_sync_marks_task_cancelled_on_rejection():
    canonical = CanonicalFinding(
        id="canon-2",
        canonical_id="canon-2",
        asset_id="asset-2",
        asset_identifiers=[AssetIdentifier(id_type=AssetIdentifierType.HOSTNAME, value="vm-2")],
        sources=[],
        vuln_key="CVE-2024-0002",
        severity="medium",
        risk_tier=RiskTier.MEDIUM,
        status=FindingLifecycleStatus.TRIAGED,
        treatment_follow_up_id="rt-2",
    )

    task = RiskTreatmentTask(
        id="rt-2",
        task_id="rt-2",
        canonical_id="canon-2",
        triage_id="tri-2",
        asset_id="asset-2",
        workflow=RiskTreatmentWorkflow.WAIVER,
        treatment="accept",
        risk_tier=RiskTier.MEDIUM,
        residual_risk=ResidualRisk(risk_tier=RiskTier.MEDIUM),
        status=RiskTreatmentStatus.IN_PROGRESS,
        ticket_key="CYB-200",
    )

    risk_repo = MemoryRiskTreatmentRepository([task])
    jira = FakeJiraClient({"CYB-200": {"status": {"name": "Rejected"}, "customfield_10084": {"value": "Rejected"}}})

    syncer = RiskTreatmentSync(
        risk_repo=risk_repo,
        canonical_repo=MemoryCanonicalRepository(canonical),
        jira_ticket_client=jira,
        run_repo=MemoryRunEventRepository(),
        approved_values={"approved"},
        rejected_values={"rejected"},
    )

    metrics = await syncer.sync(limit=10)

    assert metrics["cancelled"] == 1
    assert metrics["waiver_cancelled"] == 1
    assert metrics["transfer_cancelled"] == 0
    updated_task = risk_repo.tasks[0]
    assert updated_task.status == RiskTreatmentStatus.CANCELLED
    assert canonical.treatment_follow_up_id is None
    assert canonical.status == FindingLifecycleStatus.TRIAGED
