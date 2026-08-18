"use client";

import { useCallback, useRef, useState } from "react";
import { ShaderBackground } from "@/components/ui/kim";
import { askText, askVoice, type Result } from "@/lib/api";
import { useRecorder } from "@/lib/useRecorder";
import { speechPreviewSupported, useSpeechPreview } from "@/lib/useSpeechPreview";

// Every one of these is verified against the deployed index by
// scripts/verify_demo.py — the live service cites a passage the dataset marked
// gold. Re-run that script after changing which index shard is deployed.
//
// The first two are the same question in both languages, which is the point of
// the shared multilingual space. Do not put an unverified query here: the
// deployed corpus is a shard, so an unmatched question still returns its
// nearest neighbour and reads as a hallucination. "कॉर्पोरेशन क्या है?" and
// "who invented the telephone" were both removed for exactly that.
const EXAMPLES = [
  { label: "how fast does an eagle travel", hint: "English" },
  { label: "बाज़ कितनी तेजी से यात्रा करता है", hint: "Hindi" },
  { label: "stubhub toll free number", hint: "exact fact" },
  { label: "what is my bank account balance", hint: "refused" },
];

// Ordered so the meter reads left to right in the order the pipeline runs.
const STAGES = [
  { key: "embed", color: "var(--color-sand)", label: "embed" },
  { key: "retrieve", color: "var(--color-mint)", label: "retrieve" },
  { key: "extract", color: "var(--color-deep)", label: "answer" },
] as const;

/** The product's whole claim, drawn to scale. Each stage is sized as a fraction
 *  of the 200ms budget, so headroom is visible rather than asserted. */
function LatencyMeter({ spans, budget }: { spans: Record<string, number>; budget: number }) {
  const total = spans.total ?? 0;
  const within = total <= budget;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between gap-4">
        <span className="font-mono text-[11px] uppercase tracking-[0.18em] text-sand/45">
          pipeline latency
        </span>
        <span className="font-mono text-xs tabular-nums text-sand/45">
          budget {budget.toFixed(0)}ms
        </span>
      </div>

      <div
        className="flex h-2 w-full overflow-hidden rounded-full bg-abyss/60 ring-1 ring-inset ring-white/10"
        role="img"
        aria-label={`${total.toFixed(0)} milliseconds of a ${budget} millisecond budget`}
      >
        {STAGES.map(({ key, color }) => {
          const ms = spans[key];
          if (!ms) return null;
          return (
            <div
              key={key}
              className="h-full transition-[width] duration-500 ease-out"
              style={{ width: `${Math.min((ms / budget) * 100, 100)}%`, background: color }}
            />
          );
        })}
      </div>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        {STAGES.map(({ key, color, label }) =>
          spans[key] === undefined ? null : (
            <span key={key} className="flex items-center gap-2 font-mono text-xs text-sand/60">
              <span
                className="size-2 rounded-full"
                style={{ background: color }}
                aria-hidden
              />
              {label}
              <span className="tabular-nums text-sand/90">{spans[key].toFixed(1)}ms</span>
            </span>
          ),
        )}
        <span
          className={`ml-auto font-mono text-xs tabular-nums ${
            within ? "text-mint" : "text-clay"
          }`}
        >
          {total.toFixed(1)}ms {within ? "· within budget" : "· over budget"}
        </span>
      </div>
    </div>
  );
}

export default function Home() {
  const [result, setResult] = useState<Result | null>(null);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<string | null>(null);
  const [text, setText] = useState("");

  const run = useCallback(async (fn: () => Promise<Result>) => {
    setBusy(true);
    setFailure(null);
    try {
      setResult(await fn());
    } catch (e) {
      setFailure(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }, []);

  // Recording -> Sarvam. The caption below is display only.
  const onRecorded = useCallback((blob: Blob) => run(() => askVoice(blob)), [run]);
  const { recording, error: micError, start, stop } = useRecorder(onRecorded);

  const stopRef = useRef(stop);
  stopRef.current = stop;

  // Browser caption doubles as a silence detector: when the speaker stops, we
  // stop the recorder, which fires onRecorded and submits. No stop button hunt.
  const preview = useSpeechPreview(() => stopRef.current());

  const beginRecording = () => {
    setText("");
    preview.start();
    start();
  };

  const endRecording = () => {
    preview.stop();
    stop();
  };

  const submit = (q: string) => {
    if (!q.trim() || busy) return;
    setText(q);
    run(() => askText(q));
  };

  // While recording, the box mirrors the live caption; otherwise it is the input.
  const boxValue = recording ? preview.caption : text;

  const refused = result?.type === "abstention";

  return (
    <div className="relative min-h-screen w-full overflow-hidden bg-abyss">
      <ShaderBackground className="pointer-events-none absolute inset-0" />
      {/* Scrim: the shader is beautiful but text needs a floor to sit on. */}
      <div
        className="pointer-events-none absolute inset-0 bg-gradient-to-b from-abyss/85 via-abyss/60 to-abyss/90"
        aria-hidden
      />

      <main className="relative mx-auto flex min-h-screen max-w-3xl flex-col justify-center gap-10 px-6 py-16 sm:px-10">
        <header className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <span className="size-1.5 rounded-full bg-mint" aria-hidden />
            <span className="font-mono text-[11px] uppercase tracking-[0.22em] text-mint/70">
              voice rag · msmarco-xi
            </span>
          </div>
          <h1 className="font-display text-6xl leading-[0.95] tracking-tight text-sand sm:text-7xl">
            Echo<span className="italic text-mint">RAG</span>
          </h1>
          <p className="max-w-xl text-[15px] leading-relaxed text-sand/60">
            Ask in Hindi or English. Every answer is a verbatim span of a retrieved
            passage — or an honest refusal.{" "}
            <span className="text-sand/40">
              Retrieval to answer in under 200&nbsp;milliseconds.
            </span>
          </p>
        </header>

        <section className="flex flex-col gap-4">
          {/* One bordered shell holding an optional status row above the input
              row. The status line used to be absolutely positioned at -top-5,
              which put it in the shell's padding and clipped it against the
              border. */}
          <div
            className={`rounded-2xl border bg-gradient-to-b from-white/[0.04] to-transparent p-2 backdrop-blur-xl transition-all duration-300 focus-within:border-mint/40 ${
              recording
                ? "border-mint/40 shadow-[0_0_0_1px_rgba(127,222,190,0.15),0_0_40px_-8px_rgba(127,222,190,0.35)]"
                : "border-white/10"
            }`}
          >
            {recording && (
              <div className="flex items-center gap-2 px-2 pb-2 pt-1">
                <span className="flex items-end gap-[3px]" aria-hidden>
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="w-[3px] animate-pulse rounded-full bg-mint/70"
                      style={{ height: `${6 + i * 3}px`, animationDelay: `${i * 140}ms` }}
                    />
                  ))}
                </span>
                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-mint/60">
                  live caption · sarvam transcribes on stop
                </span>
              </div>
            )}

            <div className="flex items-center gap-3">
            <button
              onClick={recording ? endRecording : beginRecording}
              disabled={busy && !recording}
              aria-label={recording ? "Stop recording" : "Record a question"}
              className={`grid size-11 shrink-0 place-items-center rounded-xl transition disabled:opacity-40 ${
                recording
                  ? "pulse-ring bg-mint text-abyss"
                  : "bg-sand/10 text-sand hover:bg-sand/20"
              }`}
            >
              {recording ? (
                <span className="size-3 rounded-[3px] bg-abyss" aria-hidden />
              ) : (
                <svg viewBox="0 0 24 24" className="size-5" fill="none" aria-hidden>
                  <path
                    d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3Z"
                    stroke="currentColor"
                    strokeWidth="1.6"
                  />
                  <path
                    d="M19 11a7 7 0 0 1-14 0M12 18v3"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                  />
                </svg>
              )}
            </button>

            <div className="min-w-0 flex-1">
              <input
                value={boxValue}
                onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && submit(text)}
                readOnly={recording}
                placeholder={
                  recording
                    ? speechPreviewSupported()
                      ? "Listening…"
                      : "Recording… press stop when done"
                    : "Ask a question, or press record"
                }
                aria-label="Question"
                className={`w-full bg-transparent px-1 text-[15px] leading-relaxed outline-none placeholder:text-sand/30 ${
                  recording ? "text-mint" : "text-sand"
                }`}
              />
            </div>

            <button
              onClick={() => submit(text)}
              disabled={busy || recording || !text.trim()}
              className="shrink-0 rounded-xl bg-mint px-5 py-2.5 font-mono text-xs uppercase tracking-widest text-abyss transition hover:bg-sand disabled:cursor-not-allowed disabled:opacity-25"
            >
              Ask
            </button>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map(({ label, hint }) => (
              <button
                key={label}
                onClick={() => submit(label)}
                disabled={busy}
                className="group flex items-center gap-2 rounded-full border border-white/10 px-3 py-1.5 text-[13px] text-sand/60 transition hover:border-mint/40 hover:text-sand disabled:opacity-30"
              >
                {label}
                <span className="font-mono text-[10px] uppercase tracking-wider text-sand/25 group-hover:text-mint/60">
                  {hint}
                </span>
              </button>
            ))}
          </div>
        </section>

        <section className="min-h-[13rem]" aria-live="polite">
          {micError && (
            <div className="rounded-xl border border-clay/25 bg-clay/[0.06] px-4 py-3 text-sm text-clay">
              {micError}
            </div>
          )}
          {/* Clamped and wrapped. The old version appended "is the API running
              on :8000?" unconditionally, which is wrong anywhere but local dev,
              and printed the raw body — so a routing mistake rendered a whole
              HTML error document into the page. */}
          {failure && (
            <div className="rounded-xl border border-clay/25 bg-clay/[0.06] px-4 py-3">
              <p className="font-mono text-[11px] uppercase tracking-[0.16em] text-clay/70">
                request failed
              </p>
              <p className="mt-1 line-clamp-3 break-words font-mono text-sm text-clay">
                {failure}
              </p>
            </div>
          )}

          {busy && (
            <div className="flex items-center gap-3 font-mono text-xs uppercase tracking-[0.2em] text-sand/40">
              <span className="size-1.5 animate-pulse rounded-full bg-mint" aria-hidden />
              working
            </div>
          )}

          {result && !busy && (
            <article className="rise flex flex-col gap-6 rounded-2xl border border-white/10 bg-abyss/45 p-6 backdrop-blur-xl sm:p-8">
              <div className="flex flex-wrap items-center gap-3">
                <span
                  className={`font-mono text-[11px] uppercase tracking-[0.18em] ${
                    refused ? "text-clay" : "text-mint"
                  }`}
                >
                  {refused ? `declined · ${result.reason}` : "answer"}
                </span>
                {result.confidence !== undefined && (
                  <span className="font-mono text-[11px] tabular-nums text-sand/35">
                    confidence {result.confidence.toFixed(3)}
                  </span>
                )}
                {result.citations?.length ? (
                  <span className="font-mono text-[11px] text-sand/35">
                    passage {result.citations.join(", ")}
                  </span>
                ) : null}
              </div>

              <p
                className={`font-display text-2xl leading-snug sm:text-[28px] ${
                  refused ? "text-sand/70" : "text-sand"
                }`}
              >
                {result.text}
              </p>

              {result.transcript && (
                <p className="border-l-2 border-mint/25 pl-4 text-sm text-sand/45">
                  heard <span className="italic text-sand/70">{result.transcript}</span>
                  {result.stt_ms != null && (
                    <span className="ml-2 font-mono text-xs tabular-nums text-sand/30">
                      speech-to-text {result.stt_ms.toFixed(0)}ms · measured, outside the budget
                    </span>
                  )}
                </p>
              )}

              <div className="border-t border-white/10 pt-5">
                <LatencyMeter spans={result.spans} budget={result.slo_ms} />
              </div>
            </article>
          )}
        </section>

        <footer className="font-mono text-[11px] leading-relaxed text-sand/25">
          99,985 passages · multilingual-e5-small · LanceDB hybrid retrieval · RRF fusion
          <br />
          answers extracted, never generated — nothing to hallucinate
        </footer>
      </main>
    </div>
  );
}
