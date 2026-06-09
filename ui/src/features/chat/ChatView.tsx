import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, Send, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  cancelStream,
  getSession,
  sendUserMessage,
  uploadFile,
  uploadVoice,
} from "@/api/client";
import type { MessageView } from "@/api/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FileDropzone } from "@/features/uploads/FileDropzone";
import { VoiceRecorder } from "@/features/uploads/VoiceRecorder";
import { useChatStream } from "./useChatStream";

export function ChatView(): JSX.Element {
  const { sessionId = "" } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const session = useQuery({
    queryKey: ["session", sessionId],
    queryFn: () => getSession(sessionId),
    enabled: !!sessionId,
  });
  const stream = useChatStream();
  const [input, setInput] = useState("");
  const transcript = useRef<HTMLDivElement>(null);

  useEffect(() => {
    transcript.current?.scrollTo({ top: transcript.current.scrollHeight });
  }, [stream.text, session.data?.messages.length]);

  const refreshSession = () => qc.invalidateQueries({ queryKey: ["session", sessionId] });

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

  if (!sessionId) return <p className="container py-6">Missing session id.</p>;
  if (session.isPending) return <p className="container py-6">Loading session…</p>;
  if (session.isError || !session.data)
    return <p className="container py-6 text-destructive">Failed to load session.</p>;

  return (
    <div className="grid h-full grid-rows-[auto_1fr_auto]">
      <header className="border-b border-border bg-card px-4 py-2 flex items-center gap-2">
        <Button variant="ghost" size="icon" onClick={() => navigate("/")} aria-label="back">
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <h1 className="font-semibold">{session.data.title || "Untitled"}</h1>
        <span className="text-xs text-muted-foreground">
          {session.data.provider} / {session.data.model}
        </span>
      </header>

      <div ref={transcript} className="overflow-y-auto px-4 py-4 space-y-3" data-testid="transcript">
        {session.data.messages.map((m) => (
          <Bubble key={m.id} message={m} />
        ))}
        {stream.status === "streaming" || stream.status === "completed" ? (
          <Card>
            <CardContent>
              <p className="text-xs uppercase text-muted-foreground">assistant</p>
              <p data-testid="stream-text" className="whitespace-pre-wrap text-sm">
                {stream.text}
                {stream.status === "streaming" && <span className="animate-pulse">▍</span>}
              </p>
            </CardContent>
          </Card>
        ) : null}
        {stream.status === "errored" && (
          <p className="text-sm text-destructive">{stream.error || "Stream failed"}</p>
        )}
      </div>

      <form
        className="border-t border-border bg-card px-4 py-3 flex flex-col gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (!send.isPending) send.mutate();
        }}
      >
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Say something…"
            className="flex-1 resize-none rounded-md border border-border bg-background px-3 py-2 text-sm"
            rows={2}
            aria-label="message-input"
          />
          <div className="flex flex-col gap-2">
            <Button type="submit" disabled={send.isPending || !input.trim()} aria-label="send">
              {send.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              Send
            </Button>
            <Button
              type="button"
              variant="destructive"
              size="sm"
              onClick={() => cancel.mutate()}
              disabled={stream.status !== "streaming"}
              aria-label="cancel"
            >
              <X className="h-4 w-4" /> Cancel
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FileDropzone onFile={(file) => upload.mutate({ file, kind: "file" })} />
          <VoiceRecorder onClip={(file) => upload.mutate({ file, kind: "voice" })} />
          {upload.isPending && (
            <span className="text-xs text-muted-foreground inline-flex items-center gap-1">
              <Loader2 className="h-3 w-3 animate-spin" /> uploading
            </span>
          )}
          {upload.data && (
            <span className="text-xs text-muted-foreground">
              {upload.data.filename} — {upload.data.parse_status}
            </span>
          )}
        </div>
      </form>
    </div>
  );
}

function Bubble({ message }: { message: MessageView }): JSX.Element {
  const isUser = message.role === "user";
  return (
    <Card className={isUser ? "bg-accent" : undefined}>
      <CardContent>
        <p className="text-xs uppercase text-muted-foreground">{message.role}</p>
        <p className="whitespace-pre-wrap text-sm">{message.content}</p>
      </CardContent>
    </Card>
  );
}
