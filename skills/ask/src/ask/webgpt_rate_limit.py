"""Per-account rate-limit guard for the /ask webgpt oracle backend.

Multi-round ping-pong on `/ask webgpt /review-*` can fire many ChatGPT
requests in a short window — across multiple projects, retried verdicts,
content-aware follow-ups. ChatGPT Plus/Pro has a fixed per-3-hour cap
that's account-wide, so an unguarded loop can exhaust the quota mid-day.

This module tracks recent calls in a small JSON file at
~/.pi/webgpt-rate-limit.json and refuses to start a new call once the
configured per-hour cap is reached.

Env vars:
  ASK_WEBGPT_MAX_ROUNDS_PER_HOUR  (default 30)
  ASK_WEBGPT_RATE_LIMIT_FILE      (default ~/.pi/webgpt-rate-limit.json)
  ASK_WEBGPT_RATE_LIMIT_DISABLE   (any truthy value bypasses the guard)
"""

from __future__ import annotations

from .env import load_dotenv_once

load_dotenv_once()

import json
import os
import time
from pathlib import Path


_DEFAULT_PATH = Path.home() / ".pi" / "webgpt-rate-limit.json"
_DEFAULT_PER_HOUR = 30


class WebgptRateLimitError(RuntimeError):
    """Raised when the per-hour webgpt round budget is exhausted."""


def _rate_limit_path() -> Path:
    return Path(os.environ.get("ASK_WEBGPT_RATE_LIMIT_FILE", str(_DEFAULT_PATH)))


def _per_hour_cap() -> int:
    try:
        return max(1, int(os.environ.get("ASK_WEBGPT_MAX_ROUNDS_PER_HOUR", str(_DEFAULT_PER_HOUR))))
    except (TypeError, ValueError):
        return _DEFAULT_PER_HOUR


def _disabled() -> bool:
    return os.environ.get("ASK_WEBGPT_RATE_LIMIT_DISABLE", "").lower() in {"1", "true", "yes", "on"}


def _load(path: Path) -> list[float]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:
        return []
    if not isinstance(data, list):
        return []
    return [float(t) for t in data if isinstance(t, (int, float))]


def _save(path: Path, timestamps: list[float]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(timestamps))
        tmp.replace(path)
    except Exception:
        # Best-effort: never fail an oracle call because the rate-limit
        # log couldn't be written. The next call will recompute.
        pass


def _prune(timestamps: list[float], now: float, window_s: float = 3600.0) -> list[float]:
    cutoff = now - window_s
    return [t for t in timestamps if t >= cutoff]


def check_and_record(*, path: Path | None = None) -> dict:
    """Check whether a new round can start and atomically record the attempt.

    Returns a dict with the recent-window stats for logging. Raises
    WebgptRateLimitError when the per-hour cap has been hit.

    Safe to call from any process; the file is updated with a temp-replace
    so partial writes don't leave it corrupt. There is no inter-process
    lock — concurrent callers can briefly exceed the cap by 1-2 rounds.
    That's acceptable for a soft budget; tighter coordination would need
    a real lock or a daemon, which is overkill for the current workload.
    """
    if _disabled():
        return {"disabled": True}
    cap = _per_hour_cap()
    path = path or _rate_limit_path()
    now = time.time()
    timestamps = _prune(_load(path), now)
    if len(timestamps) >= cap:
        oldest_in_window = min(timestamps)
        retry_after_s = int(3600 - (now - oldest_in_window)) + 1
        raise WebgptRateLimitError(
            f"WebGPT round budget exhausted: {len(timestamps)}/{cap} rounds in the last hour.\n"
            f"Retry after ~{retry_after_s}s, or raise the cap via "
            f"ASK_WEBGPT_MAX_ROUNDS_PER_HOUR (current: {cap}), or set "
            f"ASK_WEBGPT_RATE_LIMIT_DISABLE=1 to bypass."
        )
    timestamps.append(now)
    _save(path, timestamps)
    return {
        "rounds_in_window": len(timestamps),
        "cap": cap,
        "window_seconds": 3600,
        "rate_limit_file": str(path),
    }
