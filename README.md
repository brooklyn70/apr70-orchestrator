# apr70-orchestrator

Python daemon that coordinates AI agent work for [APR 70 Pictures v3](https://github.com/brooklyn70/apr70-pictures). Runs on Marco's Synology NAS as the "unified brain" — picks tasks from a backlog, dispatches them to the right tool/provider, tracks token usage with confidence levels, and updates a single `BRIEF.md` so Marco does one human-in-the-loop pass per day instead of being in every session.

## Status

**v1 — brutally small.** The first working loop, not a meta-platform:

- **One** runner: Claude Code subprocess.
- **One** provider: Anthropic API.
- **One** task type: pick first task from `state/TASKS.md`, execute, log, update `state/BRIEF.md`, stop.
- **One** USAGE.jsonl entry written end-to-end.
- **One** quota lookup using anthropic-ratelimit response headers.

That's v1. Multi-provider routing, fallback logic, GUI dispatch, agent frameworks — all v2+.

## Layout

```
apr70-orchestrator/
  orchestrator/        # Python source
    main.py            # entry point: one-shot or daemon mode
    providers/         # API adapters (anthropic.py, openai.py, openrouter.py, google.py)
    runners/           # subprocess wrappers (claude_code.py, cline.py, shell.py)
    tracker.py         # USAGE.jsonl + QUOTAS.json
    config.py          # paths, settings
  state/               # mounted volume on NAS; readable by orchestrator + agents
    TASKS.md           # priority-ordered backlog (synced from apr70-pictures repo)
    BRIEF.md           # current state, hook-updated
    USAGE.jsonl        # append-only spend log
    QUOTAS.json        # current quota state per provider, with confidence level
  scripts/             # ops helpers (start, stop, tail-log, etc.)
  docs/                # design notes
  Dockerfile
  docker-compose.yml
  pyproject.toml       # Python 3.12+, hatch or uv for packaging
  .env.example
```

## Running locally (Mac)

```
cp .env.example .env       # paste ANTHROPIC_API_KEY
uv venv && source .venv/bin/activate
uv pip install -e .
python -m orchestrator.main --once
```

## Running on NAS (production)

```
ssh apr70-nas
cd /volume1/apps/apr70-orchestrator
sudo docker compose up -d
sudo docker compose logs -f orchestrator
```

## Confidence levels

`QUOTAS.json` carries a `confidence` field per provider:

| Provider | Confidence |
|---|---|
| Anthropic API, OpenAI API, OpenRouter, Google AI Studio | `high` (response headers) |
| Cursor Pro fast-request count | `medium` (scraped) |
| Antigravity, Claude.ai web | `low` (agent self-report) |

The daily summary in BRIEF.md cites confidence per line so Marco knows which numbers are real vs. directional.
