"use client";

import { useCallback, useRef, useState } from "react";

// Below this there is nothing for Sarvam to transcribe, and sending it wastes a
// round trip to be told so. Roughly a quarter-second of Opus.
const MIN_AUDIO_BYTES = 1200;

/** MediaRecorder wrapper. Sarvam caps audio at 30s, so we stop at 25s. */
export function useRecorder(onDone: (blob: Blob) => void, maxMs = 25_000) {
  const [recording, setRecording] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stop = useCallback(() => {
    if (timer.current) clearTimeout(timer.current);
    recorder.current?.stop();
    // Release the mic, or the browser keeps showing the recording indicator.
    recorder.current?.stream.getTracks().forEach((t) => t.stop());
    setRecording(false);
  }, []);

  const start = useCallback(async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks: Blob[] = [];
      const mr = new MediaRecorder(stream);

      mr.ondataavailable = (e) => e.data.size > 0 && chunks.push(e.data);
      mr.onstop = () => {
        const blob = new Blob(chunks, { type: mr.mimeType });
        if (blob.size < MIN_AUDIO_BYTES) {
          setError("Didn't hear anything — hold the mic a moment longer, or type instead.");
          return;
        }
        onDone(blob);
      };

      recorder.current = mr;
      mr.start();
      setRecording(true);
      timer.current = setTimeout(stop, maxMs);
    } catch {
      setError("Microphone blocked. Allow access, or type your question instead.");
    }
  }, [onDone, maxMs, stop]);

  return { recording, error, start, stop };
}
