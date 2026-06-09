/**
 * Thin fetch helpers + endpoint constants.
 *
 * The dev vite server proxies `/api/chat` → 127.0.0.1:8001 and
 * `/api/dashboard` → 127.0.0.1:8004 (see vite.config.ts). In prod
 * builds these paths land on whatever ingress is configured.
 */
import type {
  AttachmentView,
  CostView,
  CreateSessionRequest,
  ErrorRateView,
  LatencyView,
  SessionView,
  ThroughputView,
  WindowKey,
} from "./types";

export const CHAT_BASE = "/api/chat";
export const DASHBOARD_BASE = "/api/dashboard";

class HttpError extends Error {
  constructor(public readonly status: number, message: string) {
    super(message);
  }
}

async function request<T>(input: string, init?: RequestInit): Promise<T> {
  const response = await fetch(input, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    ...init,
  });
  if (!response.ok) {
    throw new HttpError(response.status, await response.text());
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// ---------- Sessions ----------

export function listSessions(): Promise<SessionView[]> {
  return request<SessionView[]>(`${CHAT_BASE}/sessions`);
}

export function createSession(body: CreateSessionRequest): Promise<SessionView> {
  return request<SessionView>(`${CHAT_BASE}/sessions`, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function getSession(sessionId: string): Promise<SessionView> {
  return request<SessionView>(`${CHAT_BASE}/sessions/${sessionId}`);
}

// ---------- Messages ----------

export function sendUserMessage(sessionId: string, content: string): Promise<unknown> {
  return request(`${CHAT_BASE}/chat/${sessionId}/messages`, {
    method: "POST",
    body: JSON.stringify({ content }),
  });
}

export function cancelStream(sessionId: string): Promise<unknown> {
  return request(`${CHAT_BASE}/chat/${sessionId}/cancel`, { method: "POST" });
}

// ---------- Attachments ----------

export async function uploadFile(sessionId: string, file: File): Promise<AttachmentView> {
  return uploadAttachment(sessionId, file, "files");
}

export async function uploadVoice(sessionId: string, file: File): Promise<AttachmentView> {
  return uploadAttachment(sessionId, file, "voice");
}

async function uploadAttachment(
  sessionId: string,
  file: File,
  endpoint: "files" | "voice",
): Promise<AttachmentView> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${CHAT_BASE}/sessions/${sessionId}/${endpoint}`, {
    method: "POST",
    body: form,
  });
  if (!response.ok) {
    throw new HttpError(response.status, await response.text());
  }
  return (await response.json()) as AttachmentView;
}

// ---------- Dashboard ----------

export function getLatency(window: WindowKey): Promise<LatencyView> {
  return request<LatencyView>(`${DASHBOARD_BASE}/metrics/latency?window=${window}`);
}

export function getThroughput(window: WindowKey): Promise<ThroughputView> {
  return request<ThroughputView>(`${DASHBOARD_BASE}/metrics/throughput?window=${window}`);
}

export function getErrorRate(window: WindowKey): Promise<ErrorRateView> {
  return request<ErrorRateView>(`${DASHBOARD_BASE}/metrics/error-rate?window=${window}`);
}

export function getCost(window: WindowKey): Promise<CostView> {
  return request<CostView>(`${DASHBOARD_BASE}/metrics/cost?window=${window}`);
}

export { HttpError };
