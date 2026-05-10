# BRIEF — apr70-orchestrator (v1)

**Updated:** 2026-05-09 (initial bootstrap)
**Status:** Pre-deploy. Code authored locally; not yet running on NAS.

## What's done

- Repo scaffolded: `orchestrator/` Python package with `main.py`, `tracker.py`, `providers/anthropic.py`, `runners/claude_code.py`, `config.py`.
- Dockerfile + docker-compose.yml ready.
- v1 smoke-test task in state/TASKS.md.
- README + .env.example documented.

## What's next

- Push to GitHub.
- Deploy to NAS at `/volume1/apps/apr70-orchestrator/`.
- Run smoke test: `docker compose run --rm orchestrator python -m orchestrator.main --dry-run` first, then a real run once `ANTHROPIC_API_KEY` is in `.env.nas`.
- Wire orchestrator's `state/` to point at apr70-pictures' `TASKS.md` so it consumes the real backlog (v2 — needs `git` sync logic).

## Open questions for Marco

- Do you have an Anthropic API key separate from your Claude Pro subscription? The orchestrator subprocess runs `claude code` which uses whatever auth Claude Code is configured with. For v1 we can rely on your existing `claude code` setup. Direct API calls (for token-precise tracking) need a separate API key — Pro/Max plans have API access via `console.anthropic.com`.

## Spend log (last 7 days)

Empty.
