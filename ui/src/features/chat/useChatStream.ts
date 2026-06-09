import { useCallback, useRef, useState } from "react";

import { streamChat } from "@/api/sse";

export type StreamStatus = "idle" | "streaming" | "completed" | "cancelled" | "errored";

export interface UseChatStreamResult {
  status: StreamStatus;
  text: string;
  error: string | null;
  start: (sessionId: string) => Promise<void>;
  abort: () => void;
  reset: () => void;
}

export function useChatStream(): UseChatStreamResult {
  const [status, setStatus] = useState<StreamStatus>("idle");
  const [text, setText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const controller = useRef<AbortController | null>(null);

  const start = useCallback(async (sessionId: string) => {
    controller.current?.abort();
    const ctrl = new AbortController();
    controller.current = ctrl;
    setText("");
    setError(null);
    setStatus("streaming");
    await streamChat(
      sessionId,
      {
        onChunk: (delta) => setText((prev) => prev + delta),
        onFinished: (payload) => setStatus(payload.state),
        onError: (err) => {
          setError(err instanceof Error ? err.message : String(err));
          setStatus("errored");
        },
      },
      ctrl.signal,
    );
  }, []);

  const abort = useCallback(() => {
    controller.current?.abort();
    setStatus((s) => (s === "streaming" ? "cancelled" : s));
  }, []);

  const reset = useCallback(() => {
    setText("");
    setError(null);
    setStatus("idle");
  }, []);

  return { status, text, error, start, abort, reset };
}
