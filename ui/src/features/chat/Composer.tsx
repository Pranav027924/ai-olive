import { ArrowUp, Loader2, Paperclip, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";

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
  attach?: {
    onFile: (f: File) => void;
    onVoice: (f: File) => void;
    busy?: boolean;
    note?: string | null;
  };
}

/**
 * ChatGPT-style rounded composer: a pill with an optional "+" attach
 * toggle on the left, an auto-growing textarea, and a circular
 * send/stop button on the right. Enter sends, Shift+Enter newlines.
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
    <div className="w-full">
      {attach && showAttach && (
        <div className="mb-2 flex flex-wrap items-center gap-2">
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

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (canSend) onSubmit();
        }}
        className={cn(
          "flex items-end gap-2 rounded-[28px] border border-border bg-background px-3 py-2",
          "shadow-sm focus-within:shadow-md transition-shadow",
        )}
      >
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
            <Paperclip className="h-5 w-5" />
          </Button>
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
            "flex-1 resize-none bg-transparent px-1 py-1.5 text-[15px] leading-6",
            "placeholder:text-muted-foreground focus:outline-none",
            "max-h-[200px] scrollbar-thin",
          )}
        />

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
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-5 w-5" />}
          </Button>
        )}
      </form>
    </div>
  );
}
