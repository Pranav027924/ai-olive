import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createSession, sendUserMessage } from "@/api/client";
import type { Provider } from "@/api/types";
import { Composer } from "@/features/chat/Composer";
import { PROVIDERS, defaultModelFor } from "@/lib/providers";

/**
 * ChatGPT-style empty state: a centered greeting and composer. The
 * session is created lazily on the first message, then we navigate to
 * the chat view and auto-start the stream.
 */
export function HomeChat(): JSX.Element {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [input, setInput] = useState("");
  const [provider, setProvider] = useState<Provider>("anthropic");

  const start = useMutation({
    mutationFn: async () => {
      const content = input.trim();
      if (!content) throw new Error("empty");
      const session = await createSession({
        provider,
        model: defaultModelFor(provider),
        title: content.slice(0, 60),
      });
      await sendUserMessage(session.id, content);
      return session.id;
    },
    onSuccess: (id) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      navigate(`/sessions/${id}`, { state: { autostream: true } });
    },
  });

  return (
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col items-center justify-center px-4">
      <h1 className="mb-8 text-center text-3xl font-semibold tracking-tight">
        Ready when you are.
      </h1>

      <div className="w-full">
        <Composer
          value={input}
          onChange={setInput}
          onSubmit={() => start.mutate()}
          busy={start.isPending}
          placeholder="Ask anything"
          autoFocus
        />
        <div className="mt-3 flex justify-center">
          <select
            value={provider}
            onChange={(e) => setProvider(e.target.value as Provider)}
            aria-label="provider"
            className="rounded-full border border-border bg-background px-3 py-1 text-xs text-muted-foreground hover:bg-accent focus:outline-none"
          >
            {PROVIDERS.map((p) => (
              <option key={p.value} value={p.value}>
                {p.label}
              </option>
            ))}
          </select>
        </div>
        {start.isError && (
          <p className="mt-3 text-center text-sm text-destructive">
            Couldn’t start the chat. Is the backend running?
          </p>
        )}
      </div>
    </div>
  );
}
