"""Orchestrator entry point.

v1 — brutally small loop:
  1. Read TASKS.md in the site work tree (default: work_dir/TASKS.md), first unchecked line.
  2. Run Claude Code subprocess in work_dir with the task as prompt.
  3. Estimate token usage; append USAGE.jsonl under state_dir.
  4. Append a note to BRIEF.md in the site repo (default: work_dir/BRIEF.md).
  5. Mark the task done in TASKS.md; commit/push when GITHUB_TOKEN is set.
  6. Exit.

Multi-provider routing, fallback logic, GUI dispatch, daemon mode — all v2+.

Usage:
  python -m orchestrator.main --once       # run one task and exit
  python -m orchestrator.main --dry-run    # show what would run; don't execute
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
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


def send_telegram_notification(message: str) -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("[orchestrator] Missing Telegram tokens in environment, skipping notification.")
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": message}).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=data)
        urllib.request.urlopen(req, timeout=10)
        print("[orchestrator] Telegram notification sent.")
    except Exception as e:
        print(f"[orchestrator] Telegram notification failed: {e}")


def mark_task_done(tasks_md: Path, line_no: int) -> None:
    """Rewrite TASKS.md to change [ ] to [x] for the completed task."""
    lines = tasks_md.read_text(encoding="utf-8").splitlines()
    if 0 <= line_no - 1 < len(lines):
        lines[line_no - 1] = lines[line_no - 1].replace("[ ]", "[x]", 1)
        tasks_md.write_text("\n".join(lines) + "\n", encoding="utf-8")


def git_push_changes(work_dir: Path, tasks_md: Path, message: str) -> None:
    """Commit and push each distinct git root (work tree and/or task file repo)."""
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        print("[orchestrator] Missing GITHUB_TOKEN, skipping git sync.")
        return

    subprocess.run(["git", "config", "--global", "user.email", "orchestrator@apr70.com"], check=False)
    subprocess.run(["git", "config", "--global", "user.name", "APR70 Orchestrator"], check=False)

    seen_roots: set[Path] = set()
    for repo_dir in (work_dir, tasks_md.parent):
        key = repo_dir.resolve()
        if key in seen_roots:
            continue
        seen_roots.add(key)
        if not (repo_dir / ".git").exists():
            continue
        # Mounted repos (e.g. /work on Synology) are often owned by host UID; Git
        # refuses operations unless the directory is marked safe.
        subprocess.run(
            ["git", "config", "--global", "--add", "safe.directory", str(repo_dir.resolve())],
            check=False,
        )
        try:
            remote_out = subprocess.run(
                ["git", "-C", str(repo_dir), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=True,
            )
            remote_url = remote_out.stdout.strip()
            if "github.com" in remote_url and "x-access-token" not in remote_url:
                new_url = remote_url.replace("https://github.com/", f"https://x-access-token:{github_token}@github.com/")
                subprocess.run(["git", "-C", str(repo_dir), "remote", "set-url", "origin", new_url], check=True)

            subprocess.run(["git", "-C", str(repo_dir), "add", "."], check=True)
            status = subprocess.run(["git", "-C", str(repo_dir), "status", "--porcelain"], capture_output=True, text=True)
            if status.stdout.strip():
                subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", message], check=True)
                subprocess.run(["git", "-C", str(repo_dir), "push"], check=True)
                print(f"[orchestrator] Successfully pushed changes in {repo_dir}")
        except Exception as e:
            print(f"[orchestrator] Git sync failed in {repo_dir}: {e}")


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
    brief_msg = (
        f"Ran task `{task_text}` via claude_code subprocess. "
        f"Returncode={result.returncode}; ~{tokens_in}+{tokens_out} tokens "
        f"(est ${record.est_cost_usd}). USAGE.jsonl appended."
    )
    mark_task_done(tasks_md, line_no)
    append_brief_note(cfg.brief_path, brief_msg)
    git_push_changes(cfg.work_dir, tasks_md, f"Orchestrator completed: {task_text[:50]}")
    send_telegram_notification(
        "Orchestrator run finished\n\n"
        f"Task: {task_text}\n"
        f"Exit: {result.returncode}; est ${record.est_cost_usd}\n"
        f"{cfg.tasks_path} line {line_no} marked done."
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
