"""FastAPI app. Single process, models preloaded at import (AUDIT D8)."""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from echorag import stt

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 1+ loads the encoder and opens LanceDB here, so a cold model load
    # can never happen inside a request.
    yield
    await stt.aclose()


app = FastAPI(title="EchoRAG", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    """Deploy healthcheck and keep-warm target."""
    checks = {"sarvam_key": bool(os.environ.get("SARVAM_API_KEY"))}
    return {
        "status": "ok" if all(checks.values()) else "degraded",
        "version": app.version,
        "phase": 0,
        "generator": os.environ.get("ECHORAG_GENERATOR", "none"),
        "checks": checks,
    }
