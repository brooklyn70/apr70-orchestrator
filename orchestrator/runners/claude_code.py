"""Claude Code subprocess runner.

Spawns `claude code` in non-interactive mode, captures output, returns the
session result. v1: blocking, single-task; v2+ may parallelize.

The Anthropic API key is inherited from the environment (set in .env).
"""
from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str


def run_claude_code(
    *,
    prompt: str,
    work_dir: Path,
    model: str | None = None,
    timeout_sec: int = 1800,
) -> RunResult:
    """Run `claude --print "<prompt>"` in `work_dir`.

    `--print` makes Claude Code respond once and exit (non-interactive).
    The model can be overridden via `--model`.

    Note: This runner does NOT yet capture token usage from the response —
    Claude Code's CLI doesn't surface that to stdout in a structured way as
    of v1. v2 will add API-mode tracking (call Anthropic SDK directly for
    short tasks) so usage is precisely measured. For v1, we estimate from
    prompt + output token counts via tiktoken/anthropic tokenizer.
    """
    cmd = ["claude", "--print", prompt]
    if model:
        cmd.extend(["--model", model])

    proc = subprocess.run(
        cmd,
        cwd=str(work_dir),
        capture_output=True,
        text=True,
        timeout=timeout_sec,
    )
    return RunResult(
        returncode=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def quote_for_log(cmd: list[str]) -> str:
    return " ".join(shlex.quote(c) for c in cmd)
