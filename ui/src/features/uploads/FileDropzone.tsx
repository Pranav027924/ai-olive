import { Paperclip } from "lucide-react";
import { useCallback, useRef, useState } from "react";

import { cn } from "@/lib/cn";

interface FileDropzoneProps {
  onFile: (file: File) => void;
  disabled?: boolean;
  accept?: string;
}

export function FileDropzone({ onFile, disabled, accept }: FileDropzoneProps): JSX.Element {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const pickFile = useCallback(
    (file: File | null | undefined) => {
      if (file) onFile(file);
    },
    [onFile],
  );

  return (
    <label
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (disabled) return;
        pickFile(e.dataTransfer.files?.[0]);
      }}
      className={cn(
        "flex h-9 cursor-pointer items-center gap-2 rounded-md border border-dashed border-border bg-background px-3 text-sm text-muted-foreground",
        dragging && "border-primary text-foreground",
        disabled && "cursor-not-allowed opacity-60",
      )}
      data-testid="file-dropzone"
    >
      <Paperclip className="h-4 w-4" />
      <span>Drop a file or click to upload</span>
      <input
        ref={inputRef}
        type="file"
        className="hidden"
        accept={accept}
        disabled={disabled}
        onChange={(e) => pickFile(e.target.files?.[0])}
      />
    </label>
  );
}
