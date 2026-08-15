"use client";

import { useCallback, useRef, useState } from "react";

/**
 * Live caption while the user speaks — a UI affordance only.
 *
 * This is the browser's own SpeechRecognition, used purely so the text box
 * isn't empty while recording. It never reaches the pipeline: the audio still
 * goes to Sarvam, and Sarvam's transcript is what gets answered and shown as
 * "heard" (requirement 1 — speech-to-text is Sarvam).
 *
 * It doubles as a silence detector: `onend` fires when the speaker stops, which
 * lets us submit automatically instead of making the user find a stop button.
 */

type SpeechResultEvent = {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
};

type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((e: SpeechResultEvent) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
};

function ctor() {
  if (typeof window === "undefined") return undefined;
  const w = window as unknown as Record<string, new () => SpeechRecognitionLike>;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition;
}

export const speechPreviewSupported = () => Boolean(ctor());

export function useSpeechPreview(onSilence?: () => void) {
  const [caption, setCaption] = useState("");
  const ref = useRef<SpeechRecognitionLike | null>(null);
  const silenceRef = useRef(onSilence);
  silenceRef.current = onSilence;

  const start = useCallback(() => {
    setCaption("");
    const Ctor = ctor();
    if (!Ctor) return false;
    const rec = new Ctor();

    rec.lang = "en-IN"; // captions only; Sarvam handles the real transcription
    rec.continuous = true;
    rec.interimResults = true;

    rec.onresult = (e) => {
      let text = "";
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
      setCaption(text.trim());
    };
    rec.onend = () => silenceRef.current?.(); // speaker went quiet -> submit
    rec.onerror = () => {};

    try {
      rec.start();
      ref.current = rec;
      return true;
    } catch {
      return false;
    }
  }, []);

  const stop = useCallback(() => {
    const rec = ref.current;
    ref.current = null;
    if (!rec) return;
    rec.onend = null; // a manual stop must not re-trigger the silence path
    try {
      rec.stop();
    } catch {
      /* already stopped */
    }
  }, []);

  return { caption, setCaption, start, stop };
}
