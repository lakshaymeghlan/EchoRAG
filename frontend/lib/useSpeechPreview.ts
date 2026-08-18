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
 * It also doubles as a silence detector so the user doesn't have to find the
 * stop button. That part needs care: `onend` fires for *any* reason the session
 * ended — an error, a denied permission, a browser idle timeout — not only
 * because the speaker stopped talking. Treating every `onend` as silence meant
 * that in a browser which blocks the speech endpoint (Brave does) the session
 * errored instantly, `onend` fired, recording stopped after a few
 * milliseconds, and the empty audio came back as a `no_speech` refusal the
 * moment the mic was pressed.
 *
 * So auto-submit now requires all three: no error, at least one transcript
 * result, and a plausible amount of elapsed time. Anything else leaves the
 * recording running and the user presses stop — which is why `failed` is
 * returned, so the UI can say so.
 */

// Below this, an `onend` cannot mean "they finished speaking".
const MIN_LISTEN_MS = 1200;

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

/** The constructor existing does not mean it works — Brave exposes it and then
 *  fails at runtime. Real support is only known once a session has run. */
export const speechPreviewSupported = () => Boolean(ctor());

export function useSpeechPreview(onSilence?: () => void) {
  const [caption, setCaption] = useState("");
  const [failed, setFailed] = useState(false);
  const ref = useRef<SpeechRecognitionLike | null>(null);
  const silenceRef = useRef(onSilence);
  silenceRef.current = onSilence;

  const start = useCallback(() => {
    setCaption("");
    setFailed(false);

    const Ctor = ctor();
    if (!Ctor) {
      setFailed(true);
      return false;
    }
    const rec = new Ctor();

    rec.lang = "en-IN"; // captions only; Sarvam handles the real transcription
    rec.continuous = true;
    rec.interimResults = true;

    let heardSomething = false;
    let errored = false;
    const startedAt = Date.now();

    rec.onresult = (e) => {
      let text = "";
      for (let i = 0; i < e.results.length; i++) text += e.results[i][0].transcript;
      if (text.trim()) heardSomething = true;
      setCaption(text.trim());
    };

    rec.onerror = () => {
      // Captions are unavailable — recording continues regardless, because the
      // audio path is MediaRecorder + Sarvam and does not depend on this.
      errored = true;
      setFailed(true);
    };

    rec.onend = () => {
      if (errored || !heardSomething || Date.now() - startedAt < MIN_LISTEN_MS) {
        setFailed(true); // no reliable silence signal; user stops manually
        return;
      }
      silenceRef.current?.();
    };

    try {
      rec.start();
      ref.current = rec;
      return true;
    } catch {
      setFailed(true);
      return false;
    }
  }, []);

  const stop = useCallback(() => {
    const rec = ref.current;
    ref.current = null;
    if (!rec) return;
    rec.onend = null; // a manual stop must not re-trigger the silence path
    rec.onerror = null;
    try {
      rec.stop();
    } catch {
      /* already stopped */
    }
  }, []);

  return { caption, setCaption, start, stop, failed };
}
