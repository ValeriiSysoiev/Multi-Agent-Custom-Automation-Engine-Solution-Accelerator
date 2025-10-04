/**
 * Enumerations used throughout the application
 */

/**
 * Enumeration of agent types.
 */
export enum AgentType {
    HUMAN = "Human_Agent",
    GENERIC = "Generic_Agent",
    GROUP_CHAT_MANAGER = "Group_Chat_Manager",
    PLANNER = "Planner_Agent",
    INGESTION = "Ingestion_Agent",
    DEDUPLICATION = "Deduplication_Agent",
    ENRICHMENT = "Enrichment_Agent",
    TRIAGE = "Triage_Agent",
    REMEDIATION = "Remediation_Agent",
    VERIFICATION = "Verification_Agent",
    WAIVER = "Waiver_Agent",
    REPORTING = "Reporting_Agent",
    CHAT = "Chat_Agent"
}

export enum role {
    user = "user",
    assistant = "assistant"
}
/**
 * Enumeration of possible statuses for a step.
 */
export enum StepStatus {
    PLANNED = "planned",
    AWAITING_FEEDBACK = "awaiting_feedback",
    APPROVED = "approved",
    REJECTED = "rejected",
    ACTION_REQUESTED = "action_requested",
    COMPLETED = "completed",
    FAILED = "failed"
}

/**
 * Enumeration of possible statuses for a plan.
 */
export enum PlanStatus {
    IN_PROGRESS = "in_progress",
    COMPLETED = "completed",
    FAILED = "failed"
}

/**
 * Enumeration of human feedback statuses.
 */
export enum HumanFeedbackStatus {
    REQUESTED = "requested",
    ACCEPTED = "accepted",
    REJECTED = "rejected"
}
