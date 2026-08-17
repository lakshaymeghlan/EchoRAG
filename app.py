"""HuggingFace Spaces entry point — Gradio UI + the FastAPI app mounted at /api.

Why Gradio rather than serving the Next.js build directly: the free Spaces tier
is ZeroGPU-only (cpu-basic needs PRO), and ZeroGPU refuses to start unless it
detects a @spaces.GPU function *during a Gradio app's startup*. A bare uvicorn
process fails with "No @spaces.GPU function detected during startup".

So on the Space, Gradio is the UI. The Next.js frontend still builds and runs
locally (`cd frontend && npm run dev`) and is served by FastAPI outside Spaces.

The pipeline is untouched and entirely CPU — the GPU probe below is never called.

    /            Gradio UI (mic + text)
    /api/ask     text -> answer, with per-stage timings
    /api/health  readiness + index status
"""

import asyncio
import os
import pathlib
import subprocess
import sys
import time

import gradio as gr

PORT = int(os.environ.get("PORT", 7860))

# --- ZeroGPU startup requirement -------------------------------------------
# Never called. Present only so the platform's startup scan succeeds; the whole
# request path runs on CPU (torch.cuda.is_available() is False there).
try:
    import spaces

    @spaces.GPU(duration=1)
    def _zerogpu_probe() -> str:
        return "echorag runs on CPU"

except Exception as exc:  # noqa: BLE001
    print(f"[app] spaces unavailable: {exc}", file=sys.stderr)


def fetch_index() -> None:
    """Spaces disk is ephemeral and the index is 723 MB, so pull it each boot.
    Measured ~8 s inside HF's network. Never fatal — a missing index surfaces on
    /api/health instead of killing the container."""
    try:
        subprocess.run([sys.executable, "scripts/fetch_index.py"], check=False, timeout=900)
    except Exception as exc:  # noqa: BLE001
        print(f"[app] index fetch failed: {exc}", file=sys.stderr)


fetch_index()

from echorag import embed, retrieve, stt  # noqa: E402  (must follow fetch_index)
from echorag.answer import answer_question  # noqa: E402
from echorag.api import app as fastapi_app  # noqa: E402
from echorag.harness import BUDGET_MS  # noqa: E402

EXAMPLES = [
    "what is a corporation?",
    "कॉर्पोरेशन क्या है?",
    "who invented the telephone",
    "what is my bank account balance",
]


def _warm() -> None:
    """Warm the encoder and index before the first user arrives. A cold first
    encode measured 290 ms against a 7 ms steady state.

    Also sets the readiness flag /api/health reads: FastAPI does NOT run a
    sub-app's lifespan when it is mounted, so the app's own startup hook never
    fires here and would otherwise report index_ready:false forever.
    """
    try:
        embed.encode(["warm", "कॉर्पोरेशन क्या है और यह कैसे बनता है"], is_query=True)
        retrieve.retrieve("what is a corporation", k=5)
        fastapi_app.state.ready = True
        print("[app] warm")
    except Exception as exc:  # noqa: BLE001
        fastapi_app.state.ready = False
        fastapi_app.state.error = str(exc)
        print(f"[app] warmup failed: {exc}", file=sys.stderr)


def _render(result, transcript: str, stt_ms: float | None) -> tuple[str, str]:
    """Return (answer markdown, timing markdown)."""
    spans = result.spans
    total = spans.get("total", 0.0)
    ok = total <= BUDGET_MS
    refused = type(result).__name__ == "Abstention"

    head = f"**Declined** · `{result.reason}`" if refused else "**Answer**"
    body = getattr(result, "message", None) or getattr(result, "text", "")

    lines = [head, "", f"### {body}", ""]
    if transcript:
        lines.append(f"*heard:* “{transcript}”")
    if getattr(result, "citations", None):
        lines.append(f"*source passage:* `{result.citations[0]}`")
    if getattr(result, "confidence", None) is not None:
        lines.append(f"*confidence:* `{result.confidence:.3f}`")

    stages = "  ·  ".join(
        f"**{k}** {v:.1f} ms" for k, v in spans.items() if k != "total"
    )
    verdict = "✅ within" if ok else "⚠️ over"
    timing = [
        f"{stages}",
        "",
        f"### {total:.1f} ms — {verdict} the {BUDGET_MS:.0f} ms budget",
    ]
    if stt_ms is not None:
        timing.append(
            f"\n*speech-to-text {stt_ms:.0f} ms (Sarvam — measured, outside the budget)*"
        )
    if getattr(result, "tool_calls", None):
        calls = ", ".join(f"`{c['tool']}` {c['ms']} ms" for c in result.tool_calls)
        timing.append(f"\n*tool calls:* {calls}")

    return "\n".join(lines), "\n".join(timing)


def ask_text(question: str) -> tuple[str, str]:
    if not question or not question.strip():
        return "*Type a question, or record one.*", ""
    result = asyncio.run(answer_question(question.strip()))
    return _render(result, transcript="", stt_ms=None)


def ask_voice(path: str | None) -> tuple[str, str, str]:
    """Audio -> Sarvam -> pipeline. Returns (transcript, answer, timings)."""
    if not path:
        return "", "*No audio recorded.*", ""

    audio = pathlib.Path(path).read_bytes()
    t0 = time.perf_counter()
    try:
        transcript = asyncio.run(stt.transcribe(audio, pathlib.Path(path).name))
    except stt.STTError as exc:
        return "", f"**Speech-to-text failed** — {exc}", ""
    stt_ms = (time.perf_counter() - t0) * 1000

    result = asyncio.run(answer_question(transcript.text))
    answer_md, timing_md = _render(result, transcript.text, stt_ms)
    return transcript.text, answer_md, timing_md


with gr.Blocks(
    title="EchoRAG",
    theme=gr.themes.Soft(primary_hue="teal", neutral_hue="slate"),
) as demo:
    gr.Markdown(
        f"""
        # EchoRAG
        Voice RAG over **MSMARCO-XI** — 99,985 passages, Hindi and English.
        Every answer is a **verbatim span** of a retrieved passage, or an honest refusal.
        Retrieval to answer in under **{BUDGET_MS:.0f} ms**.
        """
    )

    with gr.Tab("Speak"):
        mic = gr.Audio(sources=["microphone"], type="filepath", label="Ask a question")
        heard = gr.Textbox(label="Sarvam transcript", interactive=False)
        v_answer = gr.Markdown()
        v_timing = gr.Markdown()
        mic.stop_recording(ask_voice, inputs=mic, outputs=[heard, v_answer, v_timing])

    with gr.Tab("Type"):
        box = gr.Textbox(label="Question", placeholder="what is a corporation?")
        go = gr.Button("Ask", variant="primary")
        t_answer = gr.Markdown()
        t_timing = gr.Markdown()
        gr.Examples(EXAMPLES, inputs=box, label="Try these — the last one is refused")
        go.click(ask_text, inputs=box, outputs=[t_answer, t_timing])
        box.submit(ask_text, inputs=box, outputs=[t_answer, t_timing])

    gr.Markdown(
        "---\n"
        "`multilingual-e5-small` · LanceDB · RRF fusion · **no LLM** — answers are "
        "extracted, never generated, so there is nothing to hallucinate.\n\n"
        "JSON API: [`/api/ask`](/api/ask) · [`/api/health`](/api/health)"
    )

if __name__ == "__main__":
    _warm()

    # launch() builds its own FastAPI instance, so a mount added to demo.app
    # beforehand is discarded. prevent_thread_lock returns once the server is
    # up; mount then, and block explicitly.
    demo.queue(max_size=16).launch(
        server_name="0.0.0.0", server_port=PORT, prevent_thread_lock=True
    )

    # The same app the benchmarks hit, so /api/ask and /api/health stay live.
    demo.app.mount("/api", fastapi_app)
    print(f"[app] mounted FastAPI at /api (routes: {len(demo.app.routes)})")

    demo.block_thread()
