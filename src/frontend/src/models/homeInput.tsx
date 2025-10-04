import {
    DatabaseArrowDown20Regular,
    ShieldCheckmark20Regular,
    ClipboardTaskListLtr20Regular,
    ArrowTrendingLines20Regular,
} from "@fluentui/react-icons";

export interface QuickTask {
    id: string;
    title: string;
    description: string;
    icon: React.ReactNode;
}

export const quickTasks: QuickTask[] = [
    {
        id: "ingest",
        title: "Ingest latest scans",
        description: "Pull the newest Qualys and Defender results and highlight what changed.",
        icon: <DatabaseArrowDown20Regular />,
    },
    {
        id: "triage",
        title: "Review triage backlog",
        description: "Score today's backlog and surface the riskiest findings for action.",
        icon: <ShieldCheckmark20Regular />,
    },
    {
        id: "remediation",
        title: "Prepare remediation wave",
        description: "Bundle high-risk items and generate the Jira work needed to fix them.",
        icon: <ClipboardTaskListLtr20Regular />,
    },
    {
        id: "lifecycle",
        title: "Run end-to-end VM cycle",
        description: "Kick off ingestion, dedup, enrichment, triage, remediation, verification, and reporting in sequence.",
        icon: <ArrowTrendingLines20Regular />,
    },
];

export interface HomeInputProps {
    onInputSubmit: (input: string) => void;
    onQuickTaskSelect: (taskDescription: string) => void;
}
