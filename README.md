# apr70-orchestrator

Python daemon that coordinates AI agent work for [APR 70 Pictures v3](https://github.com/brooklyn70/apr70-pictures). Runs on Marco's Synology NAS as the "unified brain" — picks tasks from a backlog, dispatches them to the right tool/provider, tracks token usage with confidence levels, and updates a single `BRIEF.md` so Marco does one human-in-the-loop pass per day instead of being in every session.

## Status

**v1 — brutally small.** The first working loop, not a meta-platform:

- **One** runner: Claude Code subprocess.
- **One** provider: Anthropic API.
- **One** task type: pick first task from the site repo `TASKS.md` (under `ORCHESTRATOR_WORK_DIR`), execute, log, update that repo's `BRIEF.md`, stop.
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
  state/               # mounted volume on NAS; spend + quota (not TASKS/BRIEF)
    USAGE.jsonl
    QUOTAS.json
  # TASKS.md + BRIEF.md live in the site repo (see ORCHESTRATOR_WORK_DIR).
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

The container idles with `sleep infinity` so you trigger work explicitly (or use loop mode below).

```
ssh apr70-nas
cd /volume1/apps/apr70-orchestrator
export PATH="/usr/local/bin:$PATH"   # docker + git on DSM
sudo /usr/local/bin/docker compose up -d --build
sudo /usr/local/bin/docker exec apr70-orchestrator op run -- python -m orchestrator.main --once
```

### What "orchestrate" means here

The NAS is already on: the stack is Docker on Synology 24/7. The question is only **when one task runs**. Two options:

1. **Manual trigger** — SSH in and run `--once` whenever you want exactly one backlog line executed.
2. **Loop mode** — run the engine continuously on the NAS:

```
sudo /usr/local/bin/docker exec apr70-orchestrator op run -- \\
  python -m orchestrator.main --loop --loop-interval-sec 900
```

(`900` = 15 minutes between tasks; adjust or use host `cron` calling `--once` instead.)

Each task still uses **Claude Code** inside the container (`claude --print ...`); `nas-headless` items in `TASKS.md` mean "do not require Marco's Mac / Cursor — the NAS can execute this line autonomously."

Telegram now includes: working tree snapshot, git push result, Claude stdout tail, **next** TASK line, and routing text derived from the `[cursor+claude]` style tags. Duplicate alerts for the same finished line within a few minutes are suppressed (see `.telegram_last_notify.json` under `state/`).

## Confidence levels

`QUOTAS.json` carries a `confidence` field per provider:

| Provider | Confidence |
|---|---|
| Anthropic API, OpenAI API, OpenRouter, Google AI Studio | `high` (response headers) |
| Cursor Pro fast-request count | `medium` (scraped) |
| Antigravity, Claude.ai web | `low` (agent self-report) |

The daily summary in BRIEF.md cites confidence per line so Marco knows which numbers are real vs. directional.
