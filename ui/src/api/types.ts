/**
 * Hand-mirrored types for the chat-service + dashboard-service
 * payloads the UI actually consumes. These mirror the backend
 * Pydantic schemas; running `npm run openapi:gen` against a local
 * stack overwrites `src/api/__generated__/*.ts` with the canonical
 * types so we can diff against these mirrors during code review.
 */

export type Provider = "anthropic" | "openai" | "gemini" | "deepseek";

export interface MessageView {
  id: string;
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  seq: number;
  status: "pending" | "complete" | "cancelled" | "error";
  created_at: string;
}

export interface SessionView {
  id: string;
  user_id: string;
  title: string | null;
  system_prompt: string | null;
  provider: Provider;
  model: string;
  status: "active" | "cancelled" | "completed" | "archived" | "deleted";
  created_at: string;
  updated_at: string;
  messages: MessageView[];
}

export interface CreateSessionRequest {
  title?: string | null;
  system_prompt?: string | null;
  provider?: Provider;
  model?: string;
}

export interface AttachmentView {
  id: string;
  session_id: string;
  kind: "file" | "audio" | "image";
  filename: string;
  mime_type: string;
  size_bytes: number;
  parse_status: "pending" | "complete" | "failed";
  parsed_text: string | null;
  transcript: string | null;
  created_at: string;
}

export type WindowKey = "1h" | "24h" | "7d";

export interface LatencyView {
  window: WindowKey;
  p50: number;
  p95: number;
  p99: number;
}

export interface ThroughputView {
  window: WindowKey;
  request_count: number;
}

export interface ErrorRateView {
  window: WindowKey;
  error_rate: number;
}

export interface CostRowView {
  provider: string;
  cost_usd: number;
}

export interface CostView {
  window: WindowKey;
  breakdown: CostRowView[];
}
