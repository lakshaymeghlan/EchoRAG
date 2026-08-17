"""FastAPI app. Single process, models preloaded at import (AUDIT D8)."""

import asyncio
import os
import pathlib
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from echorag import answer, embed, retrieve, stt
from echorag.schemas import Abstention

load_dotenv()

# Vercel-hosted frontend, separate origin from the API (AUDIT D9.1).
ALLOWED_ORIGINS = os.environ.get("ECHORAG_CORS", "*").split(",")


WARM_INTERVAL_S = 20

# Torch picks kernels per input shape, so warming one short string leaves longer
# ones cold — a 290 ms first encode against a 7 ms steady state, which blows the
# budget on its own. Warm a spread of lengths and both scripts.
WARM_INPUTS = [
    "warm",
    "what is a corporation and how is one formed",
    "कॉर्पोरेशन क्या है और यह कैसे बनता है",
    "a" * 240,
]


def _warm_once() -> None:
    embed.encode(WARM_INPUTS, is_query=True)
    embed.encode(WARM_INPUTS, is_query=False)


async def _keep_warm() -> None:
    """Self-ping so the first real request is never the cold one.

    That first request is the one a judge makes, so warmth is a feature rather
    than an optimisation. Self-contained instead of an external cron, so there
    is one less thing to configure at deploy time.
    """
    while True:
        await asyncio.sleep(WARM_INTERVAL_S)
        try:
            await asyncio.to_thread(_warm_once)
        except Exception:  # never let the warmer kill the app
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Warm both the encoder and the index before serving. A cold model load
    # inside the first request is an instant P100 violation (AUDIT D8).
    try:
        # No-op on container hosts, where fetch_index.py already ran. Needed on
        # serverless, which has no startup command and a fresh filesystem.
        retrieve.ensure_index()
        _warm_once()
        for q in ("what is a corporation", "कॉर्पोरेशन क्या है"):
            retrieve.retrieve(q, k=5)
        app.state.ready = True
    except Exception as exc:  # index missing -> fail loudly in /health, not per request
        app.state.ready = False
        app.state.error = str(exc)

    warmer = asyncio.create_task(_keep_warm())
    yield
    warmer.cancel()
    await stt.aclose()


app = FastAPI(title="EchoRAG", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


router = APIRouter()


@router.get("/health")
async def health() -> dict:
    """Deploy healthcheck and keep-warm target."""
    checks = {
        "sarvam_key": bool(os.environ.get("SARVAM_API_KEY")),
        "index_ready": bool(getattr(app.state, "ready", False)),
    }
    return {
        "status": "ok" if all(checks.values()) else "degraded",
        "version": app.version,
        "generator": os.environ.get("ECHORAG_GENERATOR", "none"),
        "checks": checks,
        "error": getattr(app.state, "error", None),
    }


def _payload(result, transcript: str, stt_ms: float | None) -> dict:
    """One response shape for both answers and abstentions — an abstention is a
    valid outcome, not an error (AUDIT §9)."""
    base = {
        "transcript": transcript,
        "spans": result.spans,
        "stt_ms": stt_ms,
        "slo_ms": answer.harness.BUDGET_MS,
    }
    if isinstance(result, Abstention):
        return {
            **base,
            "type": "abstention",
            "reason": result.reason,
            "text": result.message,
            "tool_calls": result.tool_calls,
        }
    return {
        **base,
        "type": "answer",
        "text": result.text,
        "confidence": result.confidence,
        "citations": result.citations,
        "source": result.source,
        "tool_calls": result.tool_calls,
    }


@router.post("/ask")
async def ask(text: str = Form(...)) -> dict:
    """Text in, answer out. This is the path the SLO covers."""
    result = await answer.answer_question(text)
    return _payload(result, text, stt_ms=None)


@router.post("/ask-voice")
async def ask_voice(audio: UploadFile = File(...)) -> dict:
    """Audio in, answer out. STT is measured but excluded from the SLO (§2.1)."""
    raw = await audio.read()
    if not raw:
        raise HTTPException(status_code=400, detail="empty audio")

    t0 = time.perf_counter()
    try:
        transcript = await stt.transcribe(raw, audio.filename or "audio.wav")
    except stt.STTError as exc:
        raise HTTPException(status_code=502, detail=f"speech-to-text failed: {exc}") from exc
    stt_ms = (time.perf_counter() - t0) * 1000

    result = await answer.answer_question(transcript.text)
    return _payload(result, transcript.text, stt_ms=stt_ms)


# Registered twice on purpose. Render serves the API at /health and /ask;
# Vercel Services routes /api/(.*) to this app WITHOUT stripping the prefix
# ("the service receives the original request path"), so it arrives as
# /api/ask. One router, both mount points, no per-host build.
app.include_router(router)
app.include_router(router, prefix="/api")


# --- static frontend -------------------------------------------------------
# Mounted LAST so it never shadows /ask, /ask-voice or /health. StaticFiles at
# "/" is a catch-all; registering it earlier would swallow the API routes.
#
# Built with: cd frontend && npm run build   (next.config.ts sets output:"export")
# Absent in local dev, where Next serves itself on :3000 — the app still starts.
_UI = pathlib.Path(__file__).resolve().parent.parent / "frontend" / "out"
if _UI.is_dir():
    app.mount("/", StaticFiles(directory=_UI, html=True), name="ui")
