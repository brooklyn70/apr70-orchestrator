# APR 70 orchestrator — runs Python daemon on Synology NAS
FROM python:3.12-slim AS base

WORKDIR /app

# System deps: git (for syncing state), curl (healthchecks), ca-certs (HTTPS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager) for production
RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY orchestrator ./orchestrator

RUN uv pip install --system -e .

# Default state dir mounted as a volume
ENV ORCHESTRATOR_STATE_DIR=/state
ENV ORCHESTRATOR_WORK_DIR=/work

VOLUME ["/state", "/work"]

# Default: one-shot mode. NAS docker-compose can override to daemon.
CMD ["python", "-m", "orchestrator.main", "--once"]
