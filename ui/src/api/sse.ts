/**
 * Lightweight SSE reader for `GET /chat/{id}/stream`.
 *
 * The browser EventSource API would technically work, but the
 * chat-service uses arbitrary event names (`started`, `chunk`,
 * `finished`) which forces us to attach listeners *before*
 * connecting — error-prone. Using fetch + a streaming reader keeps
 * the parser in our hands.
 */
import { CHAT_BASE } from "./client";

export interface ChatStreamHandlers {
  onStarted?: (payload: { assistant_message_id: string; seq: number }) => void;
  onChunk?: (text: string) => void;
  onFinished?: (payload: {
    state: "completed" | "cancelled" | "errored";
    content: string;
    error: string | null;
  }) => void;
  onError?: (err: unknown) => void;
}

export async function streamChat(
  sessionId: string,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${CHAT_BASE}/chat/${sessionId}/stream`, {
    method: "GET",
    headers: { Accept: "text/event-stream" },
    signal,
  });
  if (!response.body) {
    handlers.onError?.(new Error("response had no body"));
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let eventName = "message";
  let dataLines: string[] = [];

  const dispatch = () => {
    if (dataLines.length === 0) return;
    const data = dataLines.join("\n");
    dataLines = [];
    try {
      const parsed = JSON.parse(data);
      if (eventName === "started") handlers.onStarted?.(parsed);
      else if (eventName === "chunk") handlers.onChunk?.(parsed.text ?? "");
      else if (eventName === "finished") handlers.onFinished?.(parsed);
    } catch (err) {
      handlers.onError?.(err);
    }
    eventName = "message";
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let newlineIdx: number;
      while ((newlineIdx = buffer.indexOf("\n")) !== -1) {
        const line = buffer.slice(0, newlineIdx).replace(/\r$/, "");
        buffer = buffer.slice(newlineIdx + 1);

        if (line === "") {
          dispatch();
        } else if (line.startsWith("event:")) {
          eventName = line.slice(6).trim();
        } else if (line.startsWith("data:")) {
          dataLines.push(line.slice(5).trimStart());
        }
      }
    }
    dispatch();
  } catch (err) {
    if ((err as { name?: string }).name !== "AbortError") {
      handlers.onError?.(err);
    }
  }
}
