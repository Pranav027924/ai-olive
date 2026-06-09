import { Mic, MicOff } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";

interface VoiceRecorderProps {
  onClip: (file: File) => void;
  disabled?: boolean;
}

export function VoiceRecorder({ onClip, disabled }: VoiceRecorderProps): JSX.Element {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);

  useEffect(() => {
    return () => {
      mediaRecorder.current?.stream.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const start = async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunks.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.current.push(e.data);
      };
      recorder.onstop = () => {
        const blob = new Blob(chunks.current, { type: recorder.mimeType });
        const file = new File([blob], `clip-${Date.now()}.webm`, { type: recorder.mimeType });
        onClip(file);
        stream.getTracks().forEach((t) => t.stop());
      };
      mediaRecorder.current = recorder;
      recorder.start();
      setRecording(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const stop = () => {
    mediaRecorder.current?.stop();
    setRecording(false);
  };

  return (
    <div className="flex flex-col gap-1">
      <Button
        type="button"
        variant={recording ? "destructive" : "outline"}
        size="sm"
        onClick={recording ? stop : start}
        disabled={disabled}
        aria-label={recording ? "stop recording" : "start recording"}
      >
        {recording ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
        {recording ? "Stop" : "Record"}
      </Button>
      {error && <span className="text-xs text-destructive">{error}</span>}
    </div>
  );
}
