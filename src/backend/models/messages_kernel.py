import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, ClassVar, Dict, List, Literal, Optional

from pydantic import model_validator

try:
    from semantic_kernel.kernel_pydantic import Field, KernelBaseModel
except ModuleNotFoundError:  # pragma: no cover - test fallback
    from pydantic import BaseModel as KernelBaseModel, Field  # type: ignore


# Classes specifically for handling runtime interrupts
class GetHumanInputMessage(KernelBaseModel):
    """Message requesting input from a human."""

    content: str


class GroupChatMessage(KernelBaseModel):
    """Message in a group chat."""

    body: Any
    source: str
    session_id: str
    target: str = ""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    def __str__(self):
        content = self.body.content if hasattr(self.body, "content") else str(self.body)
        return f"GroupChatMessage(source={self.source}, content={content})"


class DataType(str, Enum):
    """Enumeration of possible data types for documents in the database."""

    session = "session"
    plan = "plan"
    step = "step"
    message = "message"
    agent_message = "agent_message"
    finding_raw = "finding_raw"
    sync_state = "sync_state"
    finding_canonical = "finding_canonical"
    enrichment = "enrichment"
    triage = "triage"
    remediation_unit = "remediation_unit"
    ticket = "ticket"
    evidence = "evidence"
    asset = "asset"
    run_event = "run_event"
    waiver = "waiver"
    chat_query = "chat_query"
    risk_treatment = "risk_treatment"


class RiskTier(str, Enum):
    """Risk tiers derived from likelihood × impact scoring."""

    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RemediationBucket(str, Enum):
    """Remediation workstreams considered by the platform."""

    PATCH = "patch"
    CONFIG = "config"
    CODE = "code"
    CONTROL = "control"


class FindingLifecycleStatus(str, Enum):
    """Lifecycle states for canonical vulnerability records."""

    OPEN = "open"
    TRIAGED = "triaged"
    IN_REMEDIATION = "in_remediation"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    VERIFIED = "verified"
    WAIVED = "waived"
    REOPENED = "reopened"


class VerificationStatus(str, Enum):
    """Status of verification/evidence review."""

    PENDING = "pending"
    SUBMITTED = "submitted"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class TicketStatus(str, Enum):
    """Ticket lifecycle tracked inside the platform."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    VERIFIED = "verified"
    CLOSED = "closed"
    REOPENED = "reopened"
    WAIVED = "waived"


class WaiverStatus(str, Enum):
    """Waiver approval lifecycle."""

    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class OwnershipStatus(str, Enum):
    """Ownership resolution state for assets or findings."""

    CONFIRMED = "confirmed"
    PROVISIONAL = "provisional"
    LINKAGE_REVIEW = "linkage_review"
    UNKNOWN = "unknown"


class ConfidenceLevel(str, Enum):
    """Confidence attached to enrichment or threat signals."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EvidenceType(str, Enum):
    """Evidence types supported by the verification policy."""

    TARGETED_RESCAN = "targeted_rescan"
    CONFIG_PROOF = "config_proof"
    CHANGE_RECORD = "change_record"
    SBOM_DIFF = "sbom_diff"
    FUNCTIONAL_PROBE = "functional_probe"
    CONTROL_TELEMETRY = "control_telemetry"
    VENDOR_ATTESTATION = "vendor_attestation"
    OTHER = "other"


class TreatmentRecommendation(str, Enum):
    """Risk treatment recommendations produced during triage."""

    MITIGATE = "mitigate"
    ACCEPT = "accept"
    TRANSFER = "transfer"
    AVOID = "avoid"


class AgentType(str, Enum):
    """Enumeration of agent types used in the AI VM workflow."""

    HUMAN = "Human_Agent"
    GENERIC = "Generic_Agent"
    GROUP_CHAT_MANAGER = "Group_Chat_Manager"
    PLANNER = "Planner_Agent"
    INGESTION = "Ingestion_Agent"
    DEDUPLICATION = "Deduplication_Agent"
    ENRICHMENT = "Enrichment_Agent"
    TRIAGE = "Triage_Agent"
    REMEDIATION = "Remediation_Agent"
    VERIFICATION = "Verification_Agent"
    WAIVER = "Waiver_Agent"
    REPORTING = "Reporting_Agent"
    CHAT = "Chat_Agent"


class StepStatus(str, Enum):
    """Enumeration of possible statuses for a step."""

    planned = "planned"
    awaiting_feedback = "awaiting_feedback"
    approved = "approved"
    rejected = "rejected"
    action_requested = "action_requested"
    completed = "completed"
    failed = "failed"


class PlanStatus(str, Enum):
    """Enumeration of possible statuses for a plan."""

    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"


class HumanFeedbackStatus(str, Enum):
    """Enumeration of human feedback statuses."""

    requested = "requested"
    accepted = "accepted"
    rejected = "rejected"


class MessageRole(str, Enum):
    """Message roles compatible with Semantic Kernel."""

    system = "system"
    user = "user"
    assistant = "assistant"
    function = "function"


class BaseDataModel(KernelBaseModel):
    """Base data model with common fields."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: Optional[datetime] = Field(default_factory=lambda: datetime.now(timezone.utc))
    ttl_seconds: Optional[int] = None
    legal_hold: bool = False
    data_class: Optional[str] = None
    region_origin: Optional[str] = None


class AssetIdentifierType(str, Enum):
    """Types of identifiers that can describe an asset."""

    CLOUD_RESOURCE_ID = "cloud_resource_id"
    SCANNER_AGENT_ID = "scanner_agent_id"
    HOSTNAME = "hostname"
    MAC_ADDRESS = "mac_address"
    IP_ADDRESS = "ip_address"
    OTHER = "other"


class AssetIdentifier(KernelBaseModel):
    """Represents a single identifier associated with an asset."""

    id_type: AssetIdentifierType
    value: str
    source: Optional[str] = None
    last_observed: Optional[datetime] = None


class SourceReference(KernelBaseModel):
    """Reference to a scanner/source record backing a canonical finding."""

    scanner_id: str
    external_id: str
    first_seen: datetime
    last_seen: datetime
    severity: Optional[str] = None
    raw_finding_id: Optional[str] = None
    status: Optional[str] = None


class ThreatSignal(KernelBaseModel):
    """Threat intelligence or exploit signal associated with a finding."""

    source: str
    signal_type: str
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    details: Optional[Dict[str, Any]] = None
    retrieved_at: Optional[datetime] = None


class ExposureSurface(KernelBaseModel):
    """Exposure metadata for an asset or finding."""

    internet_facing: bool = False
    authentication_required: Optional[bool] = None
    network_segment: Optional[str] = None
    control_coverage: Dict[str, bool] = Field(default_factory=dict)


class ApplicationContext(KernelBaseModel):
    """Business metadata describing asset/application ownership."""

    application: Optional[str] = None
    business_service: Optional[str] = None
    owner: Optional[str] = None
    owner_email: Optional[str] = None
    environment: Optional[str] = None
    criticality: Optional[str] = None
    tags: Dict[str, Any] = Field(default_factory=dict)
    completeness: ConfidenceLevel = ConfidenceLevel.LOW


class ResidualRisk(KernelBaseModel):
    """Residual risk captured after remediation or waiver."""

    risk_tier: RiskTier
    risk_score: Optional[int] = None
    likelihood: Optional[int] = None
    impact: Optional[int] = None
    rationale: Optional[str] = None


class CompensatingControl(KernelBaseModel):
    """Compensating control applied when durable fix is delayed."""

    control_type: str
    description: str
    coverage_scope: Optional[str] = None
    implemented_at: Optional[datetime] = None
    verification_evidence_ids: List[str] = Field(default_factory=list)
    owner: Optional[str] = None
    valid_until: Optional[datetime] = None


class LinkageReviewInfo(KernelBaseModel):
    """Metadata tracking linkage review queue state."""

    status: OwnershipStatus = OwnershipStatus.UNKNOWN
    queued_at: Optional[datetime] = None
    sla_due: Optional[datetime] = None
    notes: Optional[str] = None


# Basic message class for Semantic Kernel compatibility
class ChatMessage(KernelBaseModel):
    """Base class for chat messages in Semantic Kernel format."""

    role: MessageRole
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_semantic_kernel_dict(self) -> Dict[str, Any]:
        """Convert to format expected by Semantic Kernel."""
        return {
            "role": self.role.value,
            "content": self.content,
            "metadata": self.metadata,
        }


class StoredMessage(BaseDataModel):
    """Message stored in the database with additional metadata."""

    data_type: Literal["message"] = Field("message")
    session_id: str
    user_id: str
    role: MessageRole
    content: str
    plan_id: Optional[str] = None
    step_id: Optional[str] = None
    source: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_chat_message(self) -> ChatMessage:
        """Convert to ChatMessage format."""
        return ChatMessage(
            role=self.role,
            content=self.content,
            metadata={
                "source": self.source,
                "plan_id": self.plan_id,
                "step_id": self.step_id,
                "session_id": self.session_id,
                "user_id": self.user_id,
                "message_id": self.id,
                **self.metadata,
            },
        )


class AgentMessage(BaseDataModel):
    """Base class for messages sent between agents."""

    data_type: Literal["agent_message"] = Field("agent_message")
    session_id: str
    user_id: str
    plan_id: str
    content: str
    source: str
    step_id: Optional[str] = None


class Session(BaseDataModel):
    """Represents a user session."""

    data_type: Literal["session"] = Field("session")
    user_id: str
    current_status: str
    message_to_user: Optional[str] = None


class Plan(BaseDataModel):
    """Represents a plan containing multiple steps."""

    data_type: Literal["plan"] = Field("plan")
    session_id: str
    user_id: str
    initial_goal: str
    overall_status: PlanStatus = PlanStatus.in_progress
    source: str = AgentType.PLANNER.value
    summary: Optional[str] = None
    human_clarification_request: Optional[str] = None
    human_clarification_response: Optional[str] = None


class Step(BaseDataModel):
    """Represents an individual step (task) within a plan."""

    data_type: Literal["step"] = Field("step")
    plan_id: str
    session_id: str  # Partition key
    user_id: str
    action: str
    agent: AgentType
    status: StepStatus = StepStatus.planned
    agent_reply: Optional[str] = None
    human_feedback: Optional[str] = None
    human_approval_status: Optional[HumanFeedbackStatus] = HumanFeedbackStatus.requested
    updated_action: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    _legacy_agent_map: ClassVar[Dict[str, str]] = {
        "Hr_Agent": AgentType.HUMAN.value,
        "Marketing_Agent": AgentType.HUMAN.value,
        "Procurement_Agent": AgentType.HUMAN.value,
        "Product_Agent": AgentType.GENERIC.value,
        "Tech_Support_Agent": AgentType.GENERIC.value,
    }

    @model_validator(mode="before")
    @classmethod
    def _map_legacy_agent(cls, data: Any) -> Any:
        if isinstance(data, dict):
            agent_value = data.get("agent")
            if isinstance(agent_value, str):
                legacy = cls._legacy_agent_map.get(agent_value)
                if legacy:
                    data["agent"] = legacy
        return data


class ThreadIdAgent(BaseDataModel):
    """Represents an individual thread_id."""

    data_type: Literal["thread"] = Field("thread")
    session_id: str  # Partition key
    user_id: str
    thread_id: str


class AzureIdAgent(BaseDataModel):
    """Represents an individual thread_id."""

    data_type: Literal["agent"] = Field("agent")
    session_id: str  # Partition key
    user_id: str
    action: str
    agent: AgentType
    agent_id: str

    @model_validator(mode="before")
    @classmethod
    def _map_legacy_agent(cls, data: Any) -> Any:
        if isinstance(data, dict):
            agent_value = data.get("agent")
            if isinstance(agent_value, str):
                legacy = Step._legacy_agent_map.get(agent_value)
                if legacy:
                    data["agent"] = legacy
        return data


class PlanWithSteps(Plan):
    """Plan model that includes the associated steps."""

    steps: List[Step] = Field(default_factory=list)
    total_steps: int = 0
    planned: int = 0
    awaiting_feedback: int = 0
    approved: int = 0
    rejected: int = 0
    action_requested: int = 0
    completed: int = 0
    failed: int = 0

    def update_step_counts(self):
        """Update the counts of steps by their status."""
        status_counts = {
            StepStatus.planned: 0,
            StepStatus.awaiting_feedback: 0,
            StepStatus.approved: 0,
            StepStatus.rejected: 0,
            StepStatus.action_requested: 0,
            StepStatus.completed: 0,
            StepStatus.failed: 0,
        }

        for step in self.steps:
            status_counts[step.status] += 1

        self.total_steps = len(self.steps)
        self.planned = status_counts[StepStatus.planned]
        self.awaiting_feedback = status_counts[StepStatus.awaiting_feedback]
        self.approved = status_counts[StepStatus.approved]
        self.rejected = status_counts[StepStatus.rejected]
        self.action_requested = status_counts[StepStatus.action_requested]
        self.completed = status_counts[StepStatus.completed]
        self.failed = status_counts[StepStatus.failed]

        # Mark the plan as complete if the sum of completed and failed steps equals the total number of steps
        if self.completed + self.failed == self.total_steps:
            self.overall_status = PlanStatus.completed


# Message classes for communication between agents
class InputTask(KernelBaseModel):
    """Message representing the initial input task from the user."""

    session_id: str
    description: str  # Initial goal
    metadata: Optional[Dict[str, Any]] = None


class ChatQuery(KernelBaseModel):
    """Chat query payload for direct chat requests."""

    question: str
    session_id: Optional[str] = None
    limit: Optional[int] = Field(default=20, ge=1, le=100)


class ChatAnswer(KernelBaseModel):
    """Structured chat response returned to clients."""

    intent: str
    question: str
    filters: Dict[str, Any] = Field(default_factory=dict)
    scope: Dict[str, Any] = Field(default_factory=dict)
    results: List[Dict[str, Any]] = Field(default_factory=list)
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    session_id: str
    run_id: Optional[str] = None


class UserLanguage(KernelBaseModel):
    language: str


class ApprovalRequest(KernelBaseModel):
    """Message sent to HumanAgent to request approval for a step."""

    step_id: str
    plan_id: str
    session_id: str
    user_id: str
    action: str
    agent: AgentType


class HumanFeedback(KernelBaseModel):
    """Message containing human feedback on a step."""

    step_id: Optional[str] = None
    plan_id: str
    session_id: str
    approved: bool
    human_feedback: Optional[str] = None
    updated_action: Optional[str] = None


class HumanClarification(KernelBaseModel):
    """Message containing human clarification on a plan."""

    plan_id: str
    session_id: str
    human_clarification: str


class ActionRequest(KernelBaseModel):
    """Message sent to an agent to perform an action."""

    step_id: str
    plan_id: str
    session_id: str
    action: str
    agent: AgentType


class ActionResponse(KernelBaseModel):
    """Message containing the response from an agent after performing an action."""

    step_id: str
    plan_id: str
    session_id: str
    result: str
    status: StepStatus  # Should be 'completed' or 'failed'


class PlanStateUpdate(KernelBaseModel):
    """Optional message for updating the plan state."""

    plan_id: str
    session_id: str
    overall_status: PlanStatus


# Semantic Kernel chat message handler
class SKChatHistory:
    """Helper class to work with Semantic Kernel chat history."""

    def __init__(self, memory_store):
        """Initialize with a memory store."""
        self.memory_store = memory_store

    async def add_system_message(
        self, session_id: str, user_id: str, content: str, **kwargs
    ):
        """Add a system message to the chat history."""
        message = StoredMessage(
            session_id=session_id,
            user_id=user_id,
            role=MessageRole.system,
            content=content,
            **kwargs,
        )
        await self._store_message(message)
        return message

    async def add_user_message(
        self, session_id: str, user_id: str, content: str, **kwargs
    ):
        """Add a user message to the chat history."""
        message = StoredMessage(
            session_id=session_id,
            user_id=user_id,
            role=MessageRole.user,
            content=content,
            **kwargs,
        )
        await self._store_message(message)
        return message

    async def add_assistant_message(
        self, session_id: str, user_id: str, content: str, **kwargs
    ):
        """Add an assistant message to the chat history."""
        message = StoredMessage(
            session_id=session_id,
            user_id=user_id,
            role=MessageRole.assistant,
            content=content,
            **kwargs,
        )
        await self._store_message(message)
        return message

    async def add_function_message(
        self, session_id: str, user_id: str, content: str, **kwargs
    ):
        """Add a function result message to the chat history."""
        message = StoredMessage(
            session_id=session_id,
            user_id=user_id,
            role=MessageRole.function,
            content=content,
            **kwargs,
        )
        await self._store_message(message)
        return message

    async def _store_message(self, message: StoredMessage):
        """Store a message in the memory store."""
        # Convert to dictionary for storage
        message_dict = message.model_dump()

        # Use memory store to save the message
        # This assumes your memory store has an upsert_async method that takes a collection name and data
        await self.memory_store.upsert_async(
            f"message_{message.session_id}", message_dict
        )

    async def get_chat_history(
        self, session_id: str, limit: int = 100
    ) -> List[ChatMessage]:
        """Retrieve chat history for a session."""
        # Query messages from the memory store
        # This assumes your memory store has a method to query items
        messages = await self.memory_store.query_items(
            f"message_{session_id}", limit=limit
        )

        # Convert to ChatMessage objects
        chat_messages = []
        for msg_dict in messages:
            msg = StoredMessage.model_validate(msg_dict)
            chat_messages.append(msg.to_chat_message())

        return chat_messages

    async def clear_history(self, session_id: str):
        """Clear chat history for a session."""
        # This assumes your memory store has a method to delete a collection
        await self.memory_store.delete_collection_async(f"message_{session_id}")


# Define the expected structure of the LLM response
class PlannerResponseStep(KernelBaseModel):
    action: str
    agent: AgentType


class PlannerResponsePlan(KernelBaseModel):
    initial_goal: str
    steps: List[PlannerResponseStep]
    summary_plan_and_steps: str
    human_clarification_request: Optional[str] = None


# Helper class for Semantic Kernel function calling
class SKFunctionRegistry:
    """Helper class to register and execute functions in Semantic Kernel."""

    def __init__(self, kernel):
        """Initialize with a Semantic Kernel instance."""
        self.kernel = kernel
        self.functions = {}

    def register_function(self, name: str, function_obj, description: str = None):
        """Register a function with the kernel."""
        self.functions[name] = {
            "function": function_obj,
            "description": description or "",
        }

        # Register with the kernel's function registry
        # The exact implementation depends on Semantic Kernel's API
        # This is a placeholder - adjust according to the actual SK API
        if hasattr(self.kernel, "register_function"):
            self.kernel.register_function(name, function_obj, description)

    async def execute_function(self, name: str, **kwargs):
        """Execute a registered function."""
        if name not in self.functions:
            raise ValueError(f"Function {name} not registered")

        function_obj = self.functions[name]["function"]
        # Execute the function
        # This might vary based on SK's execution model
        return await function_obj(**kwargs)


class RawFinding(BaseDataModel):
    """Raw scanner payload (sanitized) stored for replay/audit."""

    data_type: Literal[DataType.finding_raw.value] = Field(
        DataType.finding_raw.value
    )
    scanner_id: str
    ingestion_id: str
    asset_identifiers: List[AssetIdentifier] = Field(default_factory=list)
    normalized_signature: str
    recorded_at: datetime
    payload_preview: Optional[Dict[str, Any]] = None
    redaction_applied: bool = False


class SyncStateRecord(BaseDataModel):
    """Tracks incremental ingestion cursors for scanners."""

    data_type: Literal[DataType.sync_state.value] = Field(
        DataType.sync_state.value
    )
    scanner_id: str
    last_seen_timestamp: Optional[datetime] = None
    last_seen_id: Optional[str] = None
    cursor: Optional[str] = None
    status: Optional[str] = None
    retry_after: Optional[datetime] = None


class CanonicalFinding(BaseDataModel):
    """Deduplicated vulnerability-on-asset record."""

    data_type: Literal[DataType.finding_canonical.value] = Field(
        DataType.finding_canonical.value
    )
    canonical_id: str
    asset_id: str
    asset_identifiers: List[AssetIdentifier] = Field(default_factory=list)
    sources: List[SourceReference] = Field(default_factory=list)
    vuln_key: str
    cwe: Optional[str] = None
    cvss_score: Optional[float] = None
    severity: Optional[str] = None
    risk_tier: RiskTier
    status: FindingLifecycleStatus = FindingLifecycleStatus.OPEN
    remediation_bucket: RemediationBucket = RemediationBucket.PATCH
    description: Optional[str] = None
    recommendations: Optional[str] = None
    first_observed: Optional[datetime] = None
    last_observed: Optional[datetime] = None
    ownership_status: OwnershipStatus = OwnershipStatus.UNKNOWN
    linkage_review: Optional[LinkageReviewInfo] = None
    remediation_unit_id: Optional[str] = None
    treatment_follow_up_id: Optional[str] = None


class EnrichmentRecord(BaseDataModel):
    """Business and threat enrichment for a canonical finding."""

    data_type: Literal[DataType.enrichment.value] = Field(
        DataType.enrichment.value
    )
    canonical_id: str
    asset_id: str
    application_context: ApplicationContext = Field(default_factory=ApplicationContext)
    exposure: ExposureSurface = Field(default_factory=ExposureSurface)
    threat_signals: List[ThreatSignal] = Field(default_factory=list)
    enrichment_version: Optional[str] = None


class TriageRecord(BaseDataModel):
    """Risk assessment output with rationale and treatment."""

    data_type: Literal[DataType.triage.value] = Field(
        DataType.triage.value
    )
    triage_id: str
    canonical_id: str
    created_by: str
    likelihood: int
    impact: int
    risk_score: int
    risk_tier: RiskTier
    treatment: TreatmentRecommendation
    rationale: str
    supporting_inputs: Dict[str, Any] = Field(default_factory=dict)
    residual_risk: ResidualRisk
    supersedes: Optional[str] = None


class RemediationUnitRecord(BaseDataModel):
    """Represents a remediation unit grouping multiple findings."""

    data_type: Literal[DataType.remediation_unit.value] = Field(
        DataType.remediation_unit.value
    )
    remediation_unit_id: str
    name: Optional[str] = None
    bucket: RemediationBucket
    risk_tier: RiskTier
    status: FindingLifecycleStatus = FindingLifecycleStatus.IN_REMEDIATION
    canonical_ids: List[str] = Field(default_factory=list)
    target_due_date: Optional[datetime] = None
    owner: Optional[str] = None
    notes: Optional[str] = None


class TicketRecord(BaseDataModel):
    """Represents linkage to an external ticketing system."""

    data_type: Literal[DataType.ticket.value] = Field(
        DataType.ticket.value
    )
    ticket_id: str
    remediation_unit_id: str
    external_key: str
    url: Optional[str] = None
    status: TicketStatus
    assigned_to: Optional[str] = None
    opened_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    verified_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    ack_due: Optional[datetime] = None
    verify_due: Optional[datetime] = None
    sla_breached: bool = False


class RiskTreatmentWorkflow(str, Enum):
    """Workflows applied to non-mitigate treatments."""

    WAIVER = "waiver"
    RISK_TRANSFER = "risk_transfer"


class RiskTreatmentStatus(str, Enum):
    """Lifecycle of treatment follow-up tasks."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RiskTreatmentTask(BaseDataModel):
    """Tracks follow-up required for accept/transfer treatments."""

    data_type: Literal[DataType.risk_treatment.value] = Field(
        DataType.risk_treatment.value
    )
    task_id: str
    canonical_id: str
    triage_id: str
    asset_id: str
    asset_owner: Optional[str] = None
    application: Optional[str] = None
    workflow: RiskTreatmentWorkflow
    treatment: TreatmentRecommendation
    risk_tier: RiskTier
    residual_risk: ResidualRisk
    status: RiskTreatmentStatus = RiskTreatmentStatus.PENDING
    rationale: Optional[str] = None
    requested_by: Optional[str] = None
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    justification: Optional[str] = None
    compensating_controls: List[str] = Field(default_factory=list)
    proposed_expiry: Optional[datetime] = None
    triage_reference: Optional[str] = None
    ticket_key: Optional[str] = None
    ticket_url: Optional[str] = None
    ticket_status: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    last_error: Optional[str] = None
    notes: Optional[str] = None


class EvidenceRecord(BaseDataModel):
    """Verification evidence captured for remediation."""

    data_type: Literal[DataType.evidence.value] = Field(
        DataType.evidence.value
    )
    evidence_id: str
    canonical_id: Optional[str] = None
    remediation_unit_id: Optional[str] = None
    ticket_id: Optional[str] = None
    evidence_type: EvidenceType
    source_uri: Optional[str] = None
    submitted_by: Optional[str] = None
    captured_at: datetime
    verifier_id: Optional[str] = None
    verification_status: VerificationStatus = VerificationStatus.PENDING
    details: Optional[Dict[str, Any]] = None




class AssetRecord(BaseDataModel):
    """Authoritative asset inventory metadata."""

    data_type: Literal[DataType.asset.value] = Field(DataType.asset.value)
    asset_id: str
    identifiers: List[AssetIdentifier] = Field(default_factory=list)
    application_context: ApplicationContext = Field(default_factory=ApplicationContext)
    ownership_status: OwnershipStatus = OwnershipStatus.UNKNOWN
    linkage_review: Optional[LinkageReviewInfo] = None


class RunEventRecord(BaseDataModel):
    """Telemetry for agent runs and background jobs."""

    data_type: Literal[DataType.run_event.value] = Field(
        DataType.run_event.value
    )
    correlation_id: str
    agent_name: str
    run_type: Optional[str] = None
    status: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    metrics: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None


class WaiverApproval(KernelBaseModel):
    """Tracks individual approvals with role attribution."""

    approver: str
    role: str
    approved_at: datetime


class WaiverRecord(BaseDataModel):
    """Stores waiver/exception approvals and compensating controls."""

    data_type: Literal[DataType.waiver.value] = Field(
        DataType.waiver.value
    )
    waiver_id: str
    remediation_unit_id: str
    risk_tier: RiskTier
    status: WaiverStatus = WaiverStatus.REQUESTED
    requested_by: str
    requested_at: datetime
    justification: str
    compensating_controls: List[CompensatingControl] = Field(default_factory=list)
    residual_risk: ResidualRisk
    ticket_id: Optional[str] = None
    ticket_key: Optional[str] = None
    ticket_url: Optional[str] = None
    approvals: List[WaiverApproval] = Field(default_factory=list)
    approved_by: Optional[List[str]] = None
    approved_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    renewal_count: int = 0
    verification_plan: Optional[str] = None

# Backward compatibility aliases
LegacyAssetRecord = AssetRecord
LegacyAssetIdentifier = AssetIdentifier
AssetRecordLegacy = AssetRecord
AssetIdentifierLegacy = AssetIdentifier
