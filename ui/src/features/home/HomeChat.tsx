import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Code2, Lightbulb, ListChecks, MoreHorizontal, Sparkles } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createSession, sendUserMessage } from "@/api/client";
import type { Provider } from "@/api/types";
import { Logo } from "@/components/Logo";
import { Dropdown } from "@/components/ui/dropdown";
import { Composer } from "@/features/chat/Composer";
import { PROVIDERS, defaultModelFor } from "@/lib/providers";
import { usePrefsStore } from "@/stores/prefs";

const SUGGESTIONS = [
  { icon: Sparkles, label: "Explain", prompt: "Explain this in simple terms: " },
  { icon: ListChecks, label: "Summarize", prompt: "Summarize the following: " },
  { icon: Code2, label: "Code", prompt: "Write code that " },
  { icon: Lightbulb, label: "Brainstorm", prompt: "Brainstorm ideas for " },
  { icon: MoreHorizontal, label: "More", prompt: "" },
];

export function HomeChat(): JSX.Element {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const provider = usePrefsStore((s) => s.provider);
  const setProvider = usePrefsStore((s) => s.setProvider);
  const [input, setInput] = useState("");

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
    <div className="mx-auto flex h-full w-full max-w-3xl flex-col items-center justify-center px-4 pb-16">
      <Logo className="mb-6 h-16 w-16" />
      <h1 className="text-center font-serif text-[40px] font-medium leading-tight tracking-tight">
        Good to see you.
      </h1>
      <p className="mb-10 mt-2 text-center text-lg text-muted-foreground">
        How can I help you today?
      </p>

      <div className="w-full">
        <Composer
          value={input}
          onChange={setInput}
          onSubmit={() => start.mutate()}
          busy={start.isPending}
          placeholder="Ask anything..."
          autoFocus
          attach={{ onFile: () => {}, onVoice: () => {} }}
          controls={
            <Dropdown<Provider>
              aria-label="provider"
              value={provider}
              onChange={setProvider}
              placement="top"
              align="right"
              options={PROVIDERS.map((p) => ({
                value: p.value,
                label: p.label,
                hint: p.defaultModel,
              }))}
            />
          }
        />

        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {SUGGESTIONS.map((s) => (
            <button
              key={s.label}
              onClick={() => setInput(s.prompt)}
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-background px-3.5 py-2 text-sm text-foreground/80 hover:bg-accent"
            >
              <s.icon className="h-4 w-4 text-muted-foreground" />
              {s.label}
            </button>
          ))}
        </div>

        {start.isError && (
          <p className="mt-4 text-center text-sm text-destructive">
            Couldn’t start the chat. Is the backend running?
          </p>
        )}
      </div>
    </div>
  );
}
