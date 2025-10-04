export type ChatRole = "user" | "assistant";

export interface ChatCitation {
  type: string;
  id: string;
  url?: string | null;
}

export interface ChatAnswerModel {
  intent: string;
  question: string;
  filters: Record<string, unknown>;
  scope: Record<string, unknown>;
  results: Array<Record<string, unknown>>;
  citations: ChatCitation[];
  session_id: string;
  run_id?: string;
}

export interface ChatMessageModel {
  id: string;
  role: ChatRole;
  text?: string;
  answer?: ChatAnswerModel;
  timestamp: string;
  error?: string;
}
