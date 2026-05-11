"""Orchestrator entry point.

v1 — brutally small loop:
  1. Read TASKS.md in the site work tree (default: work_dir/TASKS.md), first unchecked line.
  2. Run Claude Code subprocess in work_dir with the task as prompt.
  3. Estimate token usage; append USAGE.jsonl under state_dir.
  4. Append a note to BRIEF.md in the site repo (default: work_dir/BRIEF.md).
  5. Mark the task done in TASKS.md; commit/push when GITHUB_TOKEN is set.
  6. Exit.

Optional: --loop for repeated runs on the NAS (see README).

Usage:
  python -m orchestrator.main --once       # run one task and exit
  python -m orchestrator.main --dry-run    # show task selection; don't execute
  python -m orchestrator.main --loop       # repeat every --loop-interval-sec (default 900)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from .config import load_config
from .runners.claude_code import run_claude_code
from .tracker import append_usage, make_record


TASK_LINE_RE = re.compile(r"^\s*-\s*\[\s*\]\s*(.+?)\s*$")
TOOL_TAG_RE = re.compile(r"\[((?:cursor\+)?claude|gemini|cline|nas-headless|requires-gui)\]")
DEDUPE_FILE = ".telegram_last_notify.json"
TELEGRAM_DEDUPE_SECONDS = int(os.environ.get("ORCHESTRATOR_TELEGRAM_DEDUPE_SEC", "240"))
CLIP_SUMMARY = int(os.environ.get("ORCHESTRATOR_TELEGRAM_MAX_LINES", "30"))


def find_first_open_task(tasks_md: Path) -> tuple[int, str] | None:
    """Return (1-indexed line number, task text) for the first unchecked task, else None."""
    if not tasks_md.exists():
        return None
    for idx, line in enumerate(tasks_md.read_text(encoding="utf-8").splitlines(), start=1):
        m = TASK_LINE_RE.match(line)
        if m:
            return idx, m.group(1).strip()
    return None


def git_ensure_safe_dir(repo_dir: Path) -> None:
    subprocess.run(
        ["git", "config", "--global", "--add", "safe.directory", str(repo_dir.resolve())],
        check=False,
    )


def worktree_status_summary(repo_dir: Path, *, max_lines: int = CLIP_SUMMARY) -> str:
    """Short git status --short for Telegram (what Claude touched before orchestrator commits)."""
    if not (repo_dir / ".git").exists():
        return f"{repo_dir}: not a git repo"
    git_ensure_safe_dir(repo_dir)
    st = subprocess.run(
        ["git", "-C", str(repo_dir), "status", "--short"],
        capture_output=True,
        text=True,
    )
    body = st.stdout.strip()
    if not body:
        return f"{repo_dir.name}: clean (no path changes detected before commit)."
    lines = body.split("\n")[:max_lines]
    suffix = ""
    total = len(body.split("\n"))
    if total > max_lines:
        suffix = f"\n... +{total - max_lines} more paths"
    return f"{repo_dir.name} working tree:\n" + "\n".join(lines) + suffix


def routing_blurb(task_line: str) -> str:
    m = TOOL_TAG_RE.search(task_line)
    tag = m.group(1) if m else None
    guide = {
        "cursor+claude": "Use Cursor Agent ( Claude ) in apr70-pictures — interactive IDE edits + review.",
        "claude": "Use Claude (Pro or long Code session) — architecture / reasoning-heavy backlog lines.",
        "gemini": "Use Gemini-capable tooling — visuals / multimodal QA.",
        "cline": "Cline or scripted CLI edits — mechanical refactors.",
        "nas-headless": "Orchestrator on NAS (--once / --loop) — no GUI; ensure /work repo is cloned and git clean.",
        "requires-gui": "Marco GUI review — do not assume merge until you visually sign off.",
    }
    extra = ""
    if tag == "requires-gui":
        extra = "\nBlock auto-merge until you approve."
    if not tag:
        return "Suggested owner: Unknown tag in TASK line — refine TASK format."
    return f"Suggested: {guide.get(tag, tag)}{extra}"


def git_push_changes(work_dir: Path, tasks_md: Path, message: str) -> list[str]:
    """Commit and push each distinct git root. Return human-readable outcome lines."""
    github_token = os.environ.get("GITHUB_TOKEN")
    if not github_token:
        return ["Git: skipped (GITHUB_TOKEN unset). TASKS/BRIEF may be edited on disk only."]

    subprocess.run(["git", "config", "--global", "user.email", "orchestrator@apr70.com"], check=False)
    subprocess.run(["git", "config", "--global", "user.name", "APR70 Orchestrator"], check=False)

    lines_out: list[str] = []
    seen_roots: set[Path] = set()
    for repo_dir in (work_dir, tasks_md.parent):
        key = repo_dir.resolve()
        if key in seen_roots:
            continue
        seen_roots.add(key)
        if not (repo_dir / ".git").exists():
            continue
        git_ensure_safe_dir(repo_dir)
        label = repo_dir.name or str(repo_dir)
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
                lines_out.append(f"Git: {label} — pushed commit to origin.")
            else:
                lines_out.append(f"Git: {label} — nothing to commit.")
        except Exception as e:
            lines_out.append(f"Git: {label} — FAILED ({e}).")
    return lines_out


def telegram_signature(line_no: int, task_text: str) -> str:
    digest = hashlib.sha256(task_text.encode("utf-8")).hexdigest()[:16]
    return f"L{line_no}:{digest}"


def telegram_should_skip_duplicate(state_dir: Path, signature: str) -> bool:
    path = state_dir / DEDUPE_FILE
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("signature") != signature:
            return False
        ts = float(data.get("t", 0))
        age = datetime.now(timezone.utc).timestamp() - ts
        return age >= 0 and age < TELEGRAM_DEDUPE_SECONDS
    except (json.JSONDecodeError, OSError, TypeError):
        return False


def telegram_record_sent(state_dir: Path, signature: str) -> None:
    path = state_dir / DEDUPE_FILE
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {"signature": signature, "t": datetime.now(timezone.utc).timestamp()}
    path.write_text(json.dumps(payload), encoding="utf-8")


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
    # Plain text mode; roadmap text can exceed old limits — Telegram max ~4096; clip defensively.
    body = message if len(message) < 3900 else message[:3890] + "\n...[clipped]"
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": body}).encode("utf-8")
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


def clip_stdout_tail(text: str, max_chars: int = 2200) -> str:
    t = text.strip()
    if len(t) <= max_chars:
        return t if t else "(no stdout)"
    return "...(stdout clipped)\n" + t[-max_chars:]


def run_once(*, dry_run: bool = False) -> int:
    cfg = load_config()
    tasks_md = cfg.tasks_path
    open_task = find_first_open_task(tasks_md)
    if open_task is None:
        msg = f"[orchestrator] No open tasks in {tasks_md}. Nothing to do."
        print(msg)
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
    pre_commit_summary = worktree_status_summary(cfg.work_dir)
    git_lines = git_push_changes(cfg.work_dir, tasks_md, f"Orchestrator completed: {task_text[:50]}")

    next_task = find_first_open_task(tasks_md)
    if next_task is None:
        next_block = (
            "\nNEXT: backlog empty under current rules.\n"
            "\nMARCO REVIEW NOW:\n"
            "- git pull apr70-pictures (and optionally apr70-orchestrator)\n"
            "- skim BRIEF.md + TASKS.md\n"
            "- verify deliverables cited in TASK lines exist on disk"
        )
    else:
        nl, nt = next_task
        next_block = (
            f"\nNEXT TASK (TASKS.md line {nl}):\n{nt}\n\n"
            f"{routing_blurb(nt)}\n\n"
            "MARCO REVIEW NOW (this run):\n"
            "- Claude Code subprocess may have omitted files despite exit 0; compare git lines above vs TASK deliverable paths.\n"
            "- Pull main and open TASKS Phase section for unchecked items needing your eyes."
        )

    telegram_body = (
        "Orchestrator run finished.\n\n"
        f"DONE TASK (line {line_no}):\n{task_text}\n\n"
        f"MODEL: {cfg.model}\n"
        f"Claude Code exit: {result.returncode}\n"
        f"Estimated USAGE (rough): ~{tokens_in}+{tokens_out} tokens, est ${record.est_cost_usd}\n\n"
        f"Working tree snapshot (TASKS check-off + BRIEF note + Claude changes, before push):\n{pre_commit_summary}\n\n"
        + "\n".join(git_lines)
        + "\n\n"
        f"Stdout tail:\n{clip_stdout_tail(result.stdout)}\n\n"
        "----\n"
        f"BRIEF update: appended to {cfg.brief_path}\n"
        f"USAGE log: appended to {cfg.usage_path}"
        + next_block
    )

    sig = telegram_signature(line_no, task_text)
    if telegram_should_skip_duplicate(cfg.state_dir, sig):
        print(f"[orchestrator] Telegram suppressed (duplicate event within {TELEGRAM_DEDUPE_SECONDS}s for {sig}).")
    else:
        send_telegram_notification(telegram_body)
        telegram_record_sent(cfg.state_dir, sig)

    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(prog="apr70-orchestrator")
    parser.add_argument("--once", action="store_true", help="Run one task and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Show task selection; don't execute.")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep running tasks with sleep between iterations (NAS orchestration mode).",
    )
    parser.add_argument(
        "--loop-interval-sec",
        type=int,
        default=900,
        help="Sleep seconds between loop iterations when --loop is set (default 900).",
    )
    args = parser.parse_args()

    if args.loop:
        if args.dry_run:
            return run_once(dry_run=True)
        print(f"[orchestrator] Loop mode interval={args.loop_interval_sec}s; Ctrl+C to stop.")
        while True:
            run_once(dry_run=False)
            print(f"[orchestrator] sleeping {args.loop_interval_sec}s...")
            time.sleep(args.loop_interval_sec)

    return run_once(dry_run=args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
