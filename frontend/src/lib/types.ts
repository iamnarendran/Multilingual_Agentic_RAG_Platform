export type User = { id: string; email: string; name: string; created_at: string };

export type DocumentInfo = {
  id: string;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  status: "processing" | "ready" | "failed";
  error: string | null;
  language: string | null;
  page_count: number | null;
  chunk_count: number;
  ocr_pages: number;
  warnings: string[] | null;
  created_at: string;
};

export type ConversationInfo = { id: string; title: string; created_at: string; updated_at: string };

export type AgentName = "language" | "router" | "planner" | "retriever" | "grader" | "generator" | "validator";

export type Step = {
  agent: AgentName;
  label: string;
  status: "running" | "done" | "error";
  summary?: string;
  data?: Record<string, unknown>;
  ms?: number;
};

export type Source = {
  index: number;
  document_id: string;
  filename: string;
  page: number | null;
  page_end: number | null;
  text: string;
  score: number | null;
  language: string | null;
};

export type Validation = { grounded: boolean | null; score: number | null; issues: string[]; error?: string };

export type MessageStatus = "streaming" | "complete" | "stopped" | "error";

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  status: MessageStatus;
  steps: Step[];
  sources: Source[];
  validation: Validation | null;
  language: string | null;
  queryType: string | null;
  error: string | null;
  latencyMs: number | null;
};

export type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  language: string | null;
  query_type: string | null;
  sources: Source[] | null;
  trace: Step[] | null;
  validation: Validation | null;
  usage: { latency_ms?: number } | null;
  status: "complete" | "stopped" | "error";
  created_at: string;
};

export type ConversationDetail = ConversationInfo & { messages: StoredMessage[] };

export type Health = {
  status: string;
  llm: { configured: boolean; generator_model: string; fast_model: string };
  ocr: { enabled: boolean; languages: string[] };
  limits: { max_upload_mb: number; extensions: string[] };
};
