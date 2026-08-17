# EchoRAG API container. Targets Google Cloud Run; runs anywhere Docker does.
#
# Build locally:  docker build -t echorag . && docker run -p 8080:8080 \
#                   -e SARVAM_API_KEY=... -e ECHORAG_INDEX_REPO=user/echorag-index echorag
# Deploy:         gcloud run deploy echorag --source . --memory 2Gi
#
# The UI is not in here — it is a Next.js static export on Vercel, which is free,
# always on, and needs no container. This image is the API only.

FROM python:3.12-slim

# curl for local healthchecks; git for huggingface_hub's LFS downloads.
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
# ".[learn]" despite the name: embed.py imports sentence_transformers, which
# lives in that extra. AUDIT D2 planned ONNX int8 for serving and we never
# switched — the extra is load-bearing in production until we do.
RUN pip install --no-cache-dir -e ".[learn]" "huggingface_hub>=0.25"

COPY scripts/ ./scripts/

# Bake the encoder into the image (~120 MB) so a cold start is not also a model
# download. The 723 MB index is NOT baked in — it would make every build upload
# 723 MB of context. It is fetched at boot instead (scripts/fetch_index.py).
RUN python -c "from echorag import embed; embed.encode(['warm'], is_query=True)"

# Run unprivileged. HF_HOME must be writable: the index lands under /app at boot.
RUN useradd -m -u 1000 app && chown -R app:app /app
USER app
ENV HF_HOME=/app/.cache/huggingface

# Cloud Run injects PORT (8080) and ignores EXPOSE; the default keeps
# `docker run -p 8080:8080` working locally.
ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s \
    CMD curl -fsS "http://localhost:${PORT}/health" || exit 1

# Fetch the index if absent, then serve. One worker on purpose: the model and
# index are per-process, so a second worker would double memory for no gain.
# Shell form so ${PORT} expands at runtime rather than being a literal.
CMD python scripts/fetch_index.py && exec uvicorn echorag.api:app --host 0.0.0.0 --port ${PORT}
