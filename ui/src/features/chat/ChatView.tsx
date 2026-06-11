import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { cancelStream, getSession, sendUserMessage, uploadFile, uploadVoice } from "@/api/client";
import type { MessageView } from "@/api/types";
import { Markdown } from "@/components/Markdown";
import { Composer } from "@/features/chat/Composer";
import { useChatStream } from "@/features/chat/useChatStream";

export function ChatView(): JSX.Element {
  const { sessionId = "" } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const session = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => getSession(sessionId),
    enabled: !!sessionId,
  });
  const stream = useChatStream();
  const [input, setInput] = useState("");
  const scroller = useRef<HTMLDivElement>(null);
  const autoStarted = useRef<string | null>(null);

  const refreshSession = () => qc.invalidateQueries({ queryKey: ["session", sessionId] });

  // Keep pinned to the latest content.
  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [stream.text, session.data?.messages.length]);

  // Arriving from the home composer: the first user message is already
  // posted, so kick the stream once.
  useEffect(() => {
    const wants = (location.state as { autostream?: boolean } | null)?.autostream;
    if (wants && sessionId && autoStarted.current !== sessionId) {
      autoStarted.current = sessionId;
      navigate(location.pathname, { replace: true, state: {} });
      void (async () => {
        await stream.start(sessionId);
        await refreshSession();
      })();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.state, sessionId]);

  const send = useMutation({
    mutationFn: async () => {
      const content = input.trim();
      if (!content) throw new Error("empty");
      await sendUserMessage(sessionId, content);
      setInput("");
      await refreshSession();
      await stream.start(sessionId);
      await refreshSession();
    },
  });

  const upload = useMutation({
    mutationFn: ({ file, kind }: { file: File; kind: "file" | "voice" }) =>
      kind === "voice" ? uploadVoice(sessionId, file) : uploadFile(sessionId, file),
    onSuccess: refreshSession,
  });

  const cancel = useMutation({
    mutationFn: () => cancelStream(sessionId),
    onSuccess: () => stream.abort(),
  });

  if (session.isPending) {
    return <div className="grid h-full place-items-center text-muted-foreground">Loading…</div>;
  }
  if (session.isError || !session.data) {
    return (
      <div className="grid h-full place-items-center text-destructive">Failed to load chat.</div>
    );
  }

  const messages = session.data.messages;
  const lastIsAssistant = messages.at(-1)?.role === "assistant";
  const showLiveAssistant =
    stream.status === "streaming" || (stream.status === "completed" && !lastIsAssistant);

  return (
    <div className="grid h-full grid-rows-[auto_1fr_auto]">
      {/* Slim header */}
      <header className="flex items-center gap-2 px-4 py-3">
        <span className="truncate text-sm font-medium">{session.data.title || "New chat"}</span>
      </header>

      {/* Transcript */}
      <div ref={scroller} className="overflow-y-auto scrollbar-thin" data-testid="transcript">
        <div className="mx-auto flex max-w-3xl flex-col gap-6 px-4 py-6">
          {messages.map((m) => (
            <Bubble key={m.id} message={m} />
          ))}

          {showLiveAssistant && (
            <div data-testid="stream-text" className="text-[15px] leading-7">
              <Markdown content={stream.text} />
              {stream.status === "streaming" && (
                <span className="ml-0.5 inline-block h-4 w-2 animate-pulse bg-foreground/70 align-middle" />
              )}
            </div>
          )}

          {stream.status === "errored" && (
            <p className="text-sm text-destructive">{stream.error || "Stream failed."}</p>
          )}
        </div>
      </div>

      {/* Composer */}
      <div className="px-4 pb-4">
        <div className="mx-auto max-w-3xl">
          <Composer
            value={input}
            onChange={setInput}
            onSubmit={() => send.mutate()}
            busy={send.isPending}
            streaming={stream.status === "streaming"}
            onCancel={() => cancel.mutate()}
            placeholder="Reply…"
            attach={{
              onFile: (file) => upload.mutate({ file, kind: "file" }),
              onVoice: (file) => upload.mutate({ file, kind: "voice" }),
              busy: upload.isPending,
              note: upload.data ? `${upload.data.filename} — ${upload.data.parse_status}` : null,
            }}
            controls={
              <span
                title={`${session.data.provider} · ${session.data.model}`}
                className="rounded-full border border-border px-3 py-1.5 text-sm text-muted-foreground"
              >
                {session.data.model}
              </span>
            }
          />
          <p className="mt-2 text-center text-[11px] text-muted-foreground">
            AI-OLive can make mistakes. Responses are logged for analytics.
          </p>
        </div>
      </div>
    </div>
  );
}

function Bubble({ message }: { message: MessageView }): JSX.Element {
  const isUser = message.role === "user";
  if (isUser) {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] whitespace-pre-wrap rounded-3xl bg-muted px-4 py-2.5 text-[15px] leading-7">
          {message.content}
        </div>
      </div>
    );
  }
  return (
    <div className="text-[15px] leading-7">
      <Markdown content={message.content} />
    </div>
  );
}
