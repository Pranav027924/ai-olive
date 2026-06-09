import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createSession, listSessions } from "@/api/client";
import type { Provider } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/cn";

const PROVIDERS: { value: Provider; label: string; defaultModel: string }[] = [
  { value: "anthropic", label: "Anthropic", defaultModel: "claude-opus-4-7" },
  { value: "openai", label: "OpenAI", defaultModel: "gpt-4o-mini" },
  { value: "gemini", label: "Gemini", defaultModel: "gemini-2.0-flash" },
  { value: "deepseek", label: "DeepSeek", defaultModel: "deepseek-chat" },
];

export function SessionList(): JSX.Element {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const sessions = useQuery({ queryKey: ["sessions"], queryFn: listSessions });

  const [provider, setProvider] = useState<Provider>("anthropic");
  const [title, setTitle] = useState("");

  const create = useMutation({
    mutationFn: () => {
      const conf = PROVIDERS.find((p) => p.value === provider);
      return createSession({
        provider,
        model: conf?.defaultModel ?? "claude-opus-4-7",
        title: title.trim() || null,
      });
    },
    onSuccess: (session) => {
      qc.invalidateQueries({ queryKey: ["sessions"] });
      navigate(`/sessions/${session.id}`);
    },
  });

  return (
    <div className="container py-6 space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>New session</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid gap-3 sm:grid-cols-[1fr_180px_auto] items-end"
            onSubmit={(e) => {
              e.preventDefault();
              create.mutate();
            }}
            aria-label="new-session-form"
          >
            <label className="grid gap-1">
              <span className="text-xs uppercase text-muted-foreground">Title</span>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="Untitled"
                className="h-9 rounded-md border border-border bg-background px-3 text-sm"
              />
            </label>
            <label className="grid gap-1">
              <span className="text-xs uppercase text-muted-foreground">Provider</span>
              <select
                value={provider}
                onChange={(e) => setProvider(e.target.value as Provider)}
                className="h-9 rounded-md border border-border bg-background px-3 text-sm"
              >
                {PROVIDERS.map((p) => (
                  <option key={p.value} value={p.value}>
                    {p.label}
                  </option>
                ))}
              </select>
            </label>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
              Create
            </Button>
          </form>
        </CardContent>
      </Card>

      <section>
        <h2 className="mb-3 text-sm font-medium uppercase text-muted-foreground">
          Sessions
        </h2>
        {sessions.isPending ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : sessions.isError ? (
          <p className="text-sm text-destructive">Failed to load sessions.</p>
        ) : sessions.data && sessions.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No sessions yet.</p>
        ) : (
          <ul className="grid gap-2" data-testid="session-list">
            {sessions.data?.map((s) => (
              <li key={s.id}>
                <button
                  onClick={() => navigate(`/sessions/${s.id}`)}
                  className={cn(
                    "w-full rounded-md border border-border bg-card p-3 text-left hover:bg-accent",
                    "flex items-center justify-between",
                  )}
                >
                  <span className="flex flex-col">
                    <span className="font-medium">{s.title || "Untitled"}</span>
                    <span className="text-xs text-muted-foreground">
                      {s.provider} / {s.model} · {s.messages.length} messages
                    </span>
                  </span>
                  <span className="text-xs text-muted-foreground">{s.status}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
