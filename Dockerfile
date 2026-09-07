# syntax=docker/dockerfile:1
FROM python:3.14-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /srv

# System deps kept minimal on purpose (smaller attack surface + faster
# Cloud Run cold starts). Add build-essential only if a dependency needs it.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-gcp.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-gcp.txt

COPY app ./app

# Run as non-root (Phase 13 security requirement).
RUN useradd --create-home --uid 1001 appuser
USER appuser

EXPOSE 8080

# Cloud Run injects $PORT; default to 8080 for local `docker run`.
ENV PORT=8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD curl -f http://localhost:${PORT}/healthz || exit 1

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
