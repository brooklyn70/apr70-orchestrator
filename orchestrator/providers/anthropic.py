"""Anthropic provider adapter — pulls quota state from response headers.

Used to update QUOTAS.json after every Anthropic call (whether direct API or
Claude Code subprocess). Header source: high confidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Mapping

from ..tracker import QuotaState


def parse_quota_headers(headers: Mapping[str, str]) -> QuotaState:
    """Read `anthropic-ratelimit-*` headers into a QuotaState.

    Anthropic exposes (at least):
      - anthropic-ratelimit-requests-limit / -remaining / -reset
      - anthropic-ratelimit-tokens-limit / -remaining / -reset
      - anthropic-ratelimit-input-tokens-* / -output-tokens-*
    """
    def _int(key: str) -> int | None:
        v = headers.get(key)
        try:
            return int(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    return QuotaState(
        provider="anthropic",
        confidence="high",
        tokens_remaining=_int("anthropic-ratelimit-tokens-remaining"),
        requests_remaining=_int("anthropic-ratelimit-requests-remaining"),
        last_updated=datetime.now(timezone.utc).isoformat(),
        note="Headers-derived; resets per Anthropic policy.",
    )
