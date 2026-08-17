"""HuggingFace Spaces entry point.

Spaces runs `python app.py` and expects something listening on port 7860. We
serve our own FastAPI app there, which already carries:

    /            the built Next.js UI   (frontend/out, committed to git)
    /ask         text -> answer
    /ask-voice   audio -> Sarvam -> answer
    /health      readiness + index status

Why the gradio SDK when there is no Gradio interface: the Docker SDK is paid,
and the gradio SDK is the free tier that still lets us run an arbitrary Python
server on 7860. Gradio itself is not in the request path and adds no latency.

The index is 723 MB and gitignored, and Spaces disk is ephemeral, so it is
downloaded before the server starts — set ECHORAG_INDEX_REPO in Space settings.
"""

import os
import subprocess
import sys

PORT = int(os.environ.get("PORT", 7860))

# ZeroGPU refuses to start a Space with no @spaces.GPU function ("No @spaces.GPU
# function detected during startup"), and the free Gradio tier is ZeroGPU-only —
# cpu-basic needs PRO. This function is never called: the whole pipeline is CPU
# (torch.cuda.is_available() is False on the request path). It exists purely to
# satisfy the platform's startup check.
try:
    import spaces

    @spaces.GPU(duration=1)
    def _zerogpu_probe() -> str:
        return "echorag runs on CPU"

except Exception as exc:  # noqa: BLE001 — never let this block the server
    print(f"[app] spaces import skipped: {exc}", file=sys.stderr)


def fetch_index() -> None:
    """Pull the prebuilt index. Never fatal — a missing index shows up as
    `index_ready: false` on /health, which is far easier to debug than a
    container that refuses to boot."""
    try:
        subprocess.run([sys.executable, "scripts/fetch_index.py"], check=False, timeout=900)
    except Exception as exc:  # noqa: BLE001
        print(f"[app] index fetch failed: {exc}", file=sys.stderr)


if __name__ == "__main__":
    fetch_index()

    import uvicorn

    # Single worker on purpose: the encoder and the memory-mapped index are
    # per-process, so a second worker would double memory for no throughput win
    # on a 2-vCPU box.
    uvicorn.run("echorag.api:app", host="0.0.0.0", port=PORT, workers=1, log_level="info")
