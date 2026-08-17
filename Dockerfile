# EchoRAG — one container serving the UI and the API on port 7860.
#
# Build locally:  docker build -t echorag . && docker run -p 7860:7860 \
#                   -e SARVAM_API_KEY=... -e ECHORAG_INDEX_REPO=user/echorag-index echorag
# On HF Spaces:   just push; Spaces builds this file automatically.

# ---------------------------------------------------------------- frontend
FROM node:22-slim AS frontend

WORKDIR /app/frontend

# Copy manifests first so this layer caches — dependencies only reinstall when
# package.json changes, not on every source edit.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# next.config.ts sets output:"export", so this writes static files to out/.
# Empty API URL -> the bundle calls /ask on its own origin (no CORS).
ENV NEXT_PUBLIC_API_URL=""
RUN npm run build

# ---------------------------------------------------------------- backend
FROM python:3.12-slim

# curl for the healthcheck; git for huggingface_hub's LFS downloads.
RUN apt-get update && apt-get install -y --no-install-recommends curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# CPU-only torch: the default wheel bundles ~340 MB of CUDA libraries for a GPU
# this container will never have. Installed first and separately so the big
# layer is cached independently of our own dependency list.
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch

COPY pyproject.toml README.md ./
COPY echorag/ ./echorag/
RUN pip install --no-cache-dir -e ".[learn]" "huggingface_hub>=0.25"

COPY scripts/ ./scripts/
COPY --from=frontend /app/frontend/out ./frontend/out

# Bake the encoder into the image (~120 MB) so a cold start is not also a
# model download. Without this the first boot pulls it from the Hub.
RUN python -c "from echorag import embed; embed.encode(['warm'], is_query=True)"

# HF Spaces runs as uid 1000 and the container filesystem is read-only except
# for what we own — the index is downloaded at boot, so this must be writable.
RUN useradd -m -u 1000 app && chown -R app:app /app
USER app
ENV HF_HOME=/app/.cache/huggingface

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s \
    CMD curl -fsS http://localhost:7860/health || exit 1

# Fetch the index if absent, then serve. One worker on purpose: the model and
# index are per-process, so a second worker would double memory for no gain.
CMD ["sh", "-c", "python scripts/fetch_index.py && exec uvicorn echorag.api:app --host 0.0.0.0 --port 7860"]
