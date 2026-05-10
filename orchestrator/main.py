"""Orchestrator entry point.

v1 — brutally small loop:
  1. Read state/TASKS.md, find first unchecked top-task.
  2. Run Claude Code subprocess in the work_dir with the task as prompt.
  3. Estimate token usage; append USAGE.jsonl entry.
  4. Append a one-line note to state/BRIEF.md.
  5. Exit.

Multi-provider routing, fallback logic, GUI dispatch, daemon mode — all v2+.

Usage:
  python -m orchestrator.main --once       # run one task and exit
  python -m orchestrator.main --dry-run    # show what would run; don't execute
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config
from .runners.claude_code import run_claude_code
from .tracker import append_usage, make_record


TASK_LINE_RE = re.compile(r"^\s*-\s*\[\s*\]\s*(.+?)\s*$")


def find_first_open_task(tasks_md: Path) -> tuple[int, str] | None:
    """Return (1-indexed line number, task text) for the first unchecked task, else None."""
    if not tasks_md.exists():
        return None
    for idx, line in enumerate(tasks_md.read_text(encoding="utf-8").splitlines(), start=1):
        m = TASK_LINE_RE.match(line)
        if m:
            return idx, m.group(1).strip()
    return None


def append_brief_note(brief_md: Path, note: str) -> None:
    brief_md.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sep = "\n" if brief_md.exists() and brief_md.read_text(encoding="utf-8").strip() else ""
    with brief_md.open("a", encoding="utf-8") as fh:
        fh.write(f"{sep}\n## Orchestrator note ({stamp})\n\n{note}\n")


def estimate_tokens(text: str) -> int:
    """Crude token estimate: ~4 chars per token. Refine in v2 with the real tokenizer."""
    return max(1, len(text) // 4)


def run_once(*, dry_run: bool = False) -> int:
    cfg = load_config()
    tasks_md = cfg.tasks_path
    open_task = find_first_open_task(tasks_md)
    if open_task is None:
        print(f"[orchestrator] No open tasks in {tasks_md}. Nothing to do.")
        return 0

    line_no, task_text = open_task
    print(f"[orchestrator] picked task @ line {line_no}: {task_text}")
    print(f"[orchestrator] cwd for run: {cfg.work_dir}")
    print(f"[orchestrator] model: {cfg.model}")

    if dry_run:
        print("[orchestrator] --dry-run: not executing.")
        return 0

    result = run_claude_code(
        prompt=task_text,
        work_dir=cfg.work_dir,
        model=cfg.model,
        timeout_sec=1800,
    )
    print(f"[orchestrator] subprocess exited with code={result.returncode}")
    if result.stderr:
        print(f"[orchestrator] stderr (first 500 chars): {result.stderr[:500]}")

    tokens_in = estimate_tokens(task_text)
    tokens_out = estimate_tokens(result.stdout)
    record = make_record(
        provider="anthropic",
        model=cfg.model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        task_id=f"line-{line_no}",
        notes="claude_code subprocess (v1 estimated tokens)",
    )
    append_usage(cfg.usage_path, record)
    append_brief_note(
        cfg.brief_path,
        (
            f"Ran task `{task_text}` via claude_code subprocess. "
            f"Returncode={result.returncode}; ~{tokens_in}+{tokens_out} tokens "
            f"(est ${record.est_cost_usd}). USAGE.jsonl appended."
        ),
    )
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(prog="apr70-orchestrator")
    parser.add_argument("--once", action="store_true", help="Run one task and exit (default).")
    parser.add_argument("--dry-run", action="store_true", help="Show task selection; don't run.")
    args = parser.parse_args()

    return run_once(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
