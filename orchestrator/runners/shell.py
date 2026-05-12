"""Shell command runner.

Executes a literal shell script captured from the TASK line.
Used for [nas-shell] tasks — Docker, git, system ops — where
Claude Code subprocess is the wrong tool.

Task line format:
  - [ ] [p4] [nas-shell] SHELL: <command1> && <command2> ...

Everything after 'SHELL:' is passed to bash -c verbatim.
Multi-line commands can use && or ; as separators.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str


SHELL_PREFIX = "SHELL:"


def is_shell_task(task_text: str) -> bool:
    """Return True if the task text contains a SHELL: command block."""
    return SHELL_PREFIX in task_text


def extract_shell_command(task_text: str) -> str:
    """Extract the command string after 'SHELL:' from the task text."""
    idx = task_text.index(SHELL_PREFIX)
    return task_text[idx + len(SHELL_PREFIX):].strip()


def run_shell(
    *,
    task_text: str,
    work_dir: Path,
    timeout_sec: int = 1800,
) -> RunResult:
    """Run the shell command embedded in the task text.

    Executes via bash -c so &&, pipes, and multi-statement sequences work.
    stdout and stderr are captured and returned for Telegram reporting.
    """
    command = extract_shell_command(task_text)
    print(f"[shell-runner] executing: {command[:120]}{'...' if len(command) > 120 else ''}")

    proc = subprocess.run(
        ["bash", "-c", command],
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
