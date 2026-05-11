"""Runtime configuration for the orchestrator. Reads .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    anthropic_api_key: str
    state_dir: Path
    work_dir: Path
    model: str
    tasks_path: Path
    brief_path: Path

    @property
    def usage_path(self) -> Path:
        return self.state_dir / "USAGE.jsonl"

    @property
    def quotas_path(self) -> Path:
        return self.state_dir / "QUOTAS.json"


def load_config() -> Config:
    repo_root = Path(__file__).resolve().parent.parent
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Copy .env.example to .env and fill it in."
        )
    state_dir = Path(os.environ.get("ORCHESTRATOR_STATE_DIR", repo_root / "state")).resolve()
    work_dir = Path(
        os.environ.get("ORCHESTRATOR_WORK_DIR", repo_root.parent / "apr70-pictures")
    ).resolve()
    model = os.environ.get("ORCHESTRATOR_MODEL", "claude-sonnet-4-5")

    tasks_default = work_dir / "TASKS.md"
    brief_default = work_dir / "BRIEF.md"
    tasks_path = Path(os.environ.get("ORCHESTRATOR_TASKS_PATH", str(tasks_default))).resolve()
    brief_path = Path(os.environ.get("ORCHESTRATOR_BRIEF_PATH", str(brief_default))).resolve()

    state_dir.mkdir(parents=True, exist_ok=True)
    return Config(
        anthropic_api_key=api_key,
        state_dir=state_dir,
        work_dir=work_dir,
        model=model,
        tasks_path=tasks_path,
        brief_path=brief_path,
    )
