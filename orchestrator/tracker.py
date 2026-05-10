"""USAGE.jsonl writer and QUOTAS.json updater.

Append-only USAGE log. QUOTAS reflects the most recent state per provider with
a confidence level so downstream readers know how much to trust the numbers.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

Confidence = Literal["high", "medium", "low"]


@dataclass
class UsageRecord:
    ts: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    est_cost_usd: float
    task_id: str | None = None
    notes: str | None = None


@dataclass
class QuotaState:
    provider: str
    confidence: Confidence
    tokens_remaining: int | None = None
    requests_remaining: int | None = None
    est_credits_remaining_usd: float | None = None
    last_updated: str | None = None
    note: str | None = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def append_usage(usage_path: Path, record: UsageRecord) -> None:
    """Append one JSON line to USAGE.jsonl."""
    usage_path.parent.mkdir(parents=True, exist_ok=True)
    with usage_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(record)) + "\n")


def write_quota(quotas_path: Path, state: QuotaState) -> None:
    """Replace the entry for `state.provider` in QUOTAS.json."""
    state.last_updated = state.last_updated or _now()
    current: dict[str, dict] = {}
    if quotas_path.exists():
        try:
            current = json.loads(quotas_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current = {}
    current[state.provider] = asdict(state)
    quotas_path.parent.mkdir(parents=True, exist_ok=True)
    quotas_path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")


def estimate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Rough Anthropic pricing as of mid-2025; refine with provider response when available."""
    rates_per_million = {
        "claude-sonnet-4-5": (3.0, 15.0),
        "claude-opus-4": (15.0, 75.0),
        "claude-haiku-4": (0.80, 4.0),
    }
    in_rate, out_rate = rates_per_million.get(model, (3.0, 15.0))
    return (tokens_in / 1_000_000.0) * in_rate + (tokens_out / 1_000_000.0) * out_rate


def make_record(
    *,
    provider: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    task_id: str | None = None,
    notes: str | None = None,
) -> UsageRecord:
    return UsageRecord(
        ts=_now(),
        provider=provider,
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        est_cost_usd=round(estimate_cost_usd(model, tokens_in, tokens_out), 4),
        task_id=task_id,
        notes=notes,
    )
