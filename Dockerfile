# EchoRAG API container. Runs anywhere Docker does; sized for small free tiers.
#
# Build locally:  docker build -t echorag . && docker run -p 8080:8080 \
#                   -e SARVAM_API_KEY=... -e ECHORAG_INDEX_REPO=user/echorag-index echorag
#
# No torch. The encoder runs the published ONNX int8 graph through onnxruntime
# (AUDIT D2), which took peak RSS from ~1 GB to ~600 MB and the image from
# ~2 GB to ~300 MB, at identical recall and slightly better MRR.
#
# The UI is not in here — it is a Next.js static export on Vercel, which is free,
# always on, and needs no container. This image is the API only.

FROM python:3.12-slim

# curl for healthchecks; git for huggingface_hub's LFS downloads.
RUN apt-get update && apt-get install -y --no-install-recommends curl git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.md ./
COPY echorag/ ./echorag/
# Base deps only — no [index] (datasets is build-time) and no [learn] (torch).
RUN pip install --no-cache-dir -e "."

COPY scripts/ ./scripts/

# Bake the tokenizer and the 118 MB ONNX graph into the image so a cold start is
# not also a model download. Set HF_HOME first so the cache lands somewhere the
# unprivileged user below can still read.
ENV HF_HOME=/app/.cache/huggingface
RUN python -c "from echorag import embed; embed.encode(['warm'], is_query=True)"

# Run unprivileged. /app must stay writable: the index is downloaded at boot.
RUN useradd -m -u 1000 app && chown -R app:app /app
USER app

# Render and Cloud Run both inject PORT; the default keeps local runs working.
ENV PORT=8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=180s \
    CMD curl -fsS "http://localhost:${PORT}/health" || exit 1

# Fetch the index if absent, then serve. One worker on purpose: the model and
# index are per-process, so a second worker would double memory for no gain —
# which matters a lot on a 512 MB tier.
# Shell form so ${PORT} expands at runtime rather than being a literal.
CMD python scripts/fetch_index.py && exec uvicorn echorag.api:app --host 0.0.0.0 --port ${PORT}
