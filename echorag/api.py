"""FastAPI app. AUDIT.md D8: single process, models preloaded at import.

Phase 0 ships /health only. /ask arrives in Phase 3, the mic UI in Phase 5.
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from echorag import stt

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Phase 1+ loads the ONNX encoder and opens LanceDB here, so a cold model
    # load can never happen inside a request (AUDIT.md D8).
    yield
    await stt.aclose()


app = FastAPI(title="EchoRAG", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict:
    """Fails loudly at startup rather than at first request (AUDIT.md §11).

    Phase 0 checks config only. Phase 1 adds an index-present check, and this
    endpoint becomes the deploy healthcheck + keep-warm target (AUDIT.md D10).
    """
    checks = {"sarvam_key": bool(os.environ.get("SARVAM_API_KEY"))}
    return {
        "status": "ok" if all(checks.values()) else "degraded",
        "version": app.version,
        "phase": 0,
        "generator": os.environ.get("ECHORAG_GENERATOR", "none"),
        "checks": checks,
    }
