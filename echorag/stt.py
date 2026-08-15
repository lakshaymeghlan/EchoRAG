"""Sarvam speech-to-text. Not inside the 200ms SLO — the pipeline clock starts
once a transcript exists (AUDIT §2.1)."""

import asyncio
import os
import random
import time

import httpx

from echorag.schemas import Transcript

ENDPOINT = "https://api.sarvam.ai/speech-to-text"
MODEL = "saaras:v3"  # auto-detects language; saarika:v2.5 is deprecated
MAX_AUDIO_SECONDS = 30  # Sarvam hard limit

_RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3

_client: httpx.AsyncClient | None = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=5.0))
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


class STTError(RuntimeError):
    pass


async def transcribe(audio: bytes, filename: str = "audio.wav") -> Transcript:
    """Retries 408/409/429/5xx and connection errors only. Retrying other 4xx
    would just burn credits on a request that will never succeed."""
    key = os.environ.get("SARVAM_API_KEY")
    if not key:
        raise STTError("SARVAM_API_KEY is not set (see .env.example)")

    started = time.monotonic()
    last: Exception | None = None

    for attempt in range(_MAX_ATTEMPTS):
        try:
            resp = await _get_client().post(
                ENDPOINT,
                headers={"api-subscription-key": key},
                data={"model": MODEL, "mode": "transcribe"},
                files={"file": (filename, audio, "audio/wav")},
            )
            if resp.status_code in _RETRY_STATUS:
                raise httpx.HTTPStatusError(
                    f"retryable {resp.status_code}", request=resp.request, response=resp
                )
            if resp.status_code >= 400:
                raise STTError(f"Sarvam {resp.status_code}: {resp.text[:300]}")

            body = resp.json()
            return Transcript(
                text=(body.get("transcript") or "").strip(),
                language_code=body.get("language_code"),
                request_id=body.get("request_id"),
                latency_ms=(time.monotonic() - started) * 1000,
            )

        except (httpx.HTTPStatusError, httpx.TransportError) as exc:
            last = exc
            if attempt == _MAX_ATTEMPTS - 1:
                break
            # ponytail: local retry; moves into harness.py's shared breaker in Phase 3.
            await asyncio.sleep((0.2 * 2**attempt) + random.uniform(0, 0.1))

    raise STTError(f"Sarvam unreachable after {_MAX_ATTEMPTS} attempts: {last}")


if __name__ == "__main__":
    # python -m echorag.stt <audio.wav>   (<=30s, 16kHz mono)
    import pathlib
    import sys

    from dotenv import load_dotenv

    load_dotenv()

    if len(sys.argv) != 2:
        sys.exit("usage: python -m echorag.stt <audio.wav>")

    path = pathlib.Path(sys.argv[1])
    result = asyncio.run(transcribe(path.read_bytes(), path.name))
    print(f"transcript : {result.text!r}")
    print(f"language   : {result.language_code}")
    print(f"T_stt      : {result.latency_ms:.0f} ms")
    assert result.text, "empty transcript — check the audio is speech"
