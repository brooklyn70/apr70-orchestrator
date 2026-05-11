# APR 70 orchestrator — Synology NAS; secrets via `op run` (see docker-compose / docs)
FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    nodejs \
    npm \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# 1Password CLI — `op run` injects secrets from op:// references in env
RUN curl -sS https://cache.agilebits.com/dist/1P/op2/pkg/v2.29.0/op_linux_amd64_v2.29.0.zip -o op.zip \
    && unzip -q op.zip \
    && mv op /usr/local/bin/ \
    && rm op.zip

RUN npm install -g @anthropic-ai/claude-code

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
COPY orchestrator ./orchestrator

RUN uv pip install --system -e .

ENV ORCHESTRATOR_STATE_DIR=/state
ENV ORCHESTRATOR_WORK_DIR=/work

VOLUME ["/state", "/work"]

# Default one-shot; NAS compose often overrides with `sleep infinity` for manual exec.
CMD ["op", "run", "--", "python", "-m", "orchestrator.main", "--once"]
