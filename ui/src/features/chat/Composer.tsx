import { ArrowUp, Loader2, Plus, Square } from "lucide-react";
import { type ReactNode, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { FileDropzone } from "@/features/uploads/FileDropzone";
import { VoiceRecorder } from "@/features/uploads/VoiceRecorder";
import { cn } from "@/lib/cn";

export interface ComposerProps {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
  busy?: boolean;
  streaming?: boolean;
  onCancel?: () => void;
  placeholder?: string;
  autoFocus?: boolean;
  /** Rendered on the bottom controls row, left of the send button (e.g. the model picker). */
  controls?: ReactNode;
  attach?: {
    onFile: (f: File) => void;
    onVoice: (f: File) => void;
    busy?: boolean;
    note?: string | null;
  };
}

/**
 * Chat composer with the two-row layout used by ChatGPT/Claude: the
 * textarea sits on top, and a controls row underneath holds the "+"
 * attach toggle (left) and the model picker + send/stop button (right).
 * Enter sends, Shift+Enter newlines.
 */
export function Composer({
  value,
  onChange,
  onSubmit,
  disabled,
  busy,
  streaming,
  onCancel,
  placeholder = "Ask anything",
  autoFocus,
  controls,
  attach,
}: ComposerProps): JSX.Element {
  const textarea = useRef<HTMLTextAreaElement>(null);
  const [showAttach, setShowAttach] = useState(false);

  // Auto-grow the textarea up to a cap.
  useEffect(() => {
    const el = textarea.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [value]);

  const canSend = !disabled && !busy && value.trim().length > 0;

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (canSend) onSubmit();
      }}
      className={cn(
        "flex flex-col gap-1.5 rounded-[28px] border border-border bg-background px-3 py-2.5",
        "shadow-sm transition-shadow focus-within:shadow-md",
      )}
    >
      {attach && showAttach && (
        <div className="flex flex-wrap items-center gap-2 px-1">
          <FileDropzone onFile={attach.onFile} />
          <VoiceRecorder onClip={attach.onVoice} />
          {attach.busy && (
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
              <Loader2 className="h-3 w-3 animate-spin" /> uploading
            </span>
          )}
          {attach.note && <span className="text-xs text-muted-foreground">{attach.note}</span>}
        </div>
      )}

      <textarea
        ref={textarea}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (canSend) onSubmit();
          }
        }}
        rows={1}
        placeholder={placeholder}
        aria-label="message-input"
        autoFocus={autoFocus}
        className={cn(
          "max-h-[200px] w-full resize-none bg-transparent px-2 py-1 text-[15px] leading-6",
          "placeholder:text-muted-foreground scrollbar-thin focus:outline-none",
        )}
      />

      {/* Controls row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-1">
          {attach && (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-9 w-9 shrink-0 rounded-full text-muted-foreground"
              onClick={() => setShowAttach((s) => !s)}
              aria-label="attach"
              aria-pressed={showAttach}
            >
              <Plus className="h-5 w-5" />
            </Button>
          )}
        </div>

        <div className="flex items-center gap-2">
          {controls}
          {streaming ? (
            <Button
              type="button"
              size="icon"
              onClick={onCancel}
              aria-label="cancel"
              className="h-9 w-9 shrink-0 rounded-full"
            >
              <Square className="h-4 w-4 fill-current" />
            </Button>
          ) : (
            <Button
              type="submit"
              size="icon"
              disabled={!canSend}
              aria-label="send"
              className="h-9 w-9 shrink-0 rounded-full disabled:opacity-30"
            >
              {busy ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ArrowUp className="h-5 w-5" />
              )}
            </Button>
          )}
        </div>
      </div>
    </form>
  );
}
