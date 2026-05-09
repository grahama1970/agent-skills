"""Shared utility helpers."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PRIVATE_TAG_RE = re.compile(r"<private>.*?</private>", re.IGNORECASE | re.DOTALL)
CLAUDE_MEM_CONTEXT_RE = re.compile(r"<claude-mem-context>.*?</claude-mem-context>", re.IGNORECASE | re.DOTALL)
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def get_working_dir() -> Path:
    return Path(os.environ.get("PROJECT_DRIFT_CWD") or os.getcwd()).resolve()


def strip_private_text(value: str) -> str:
    value = PRIVATE_TAG_RE.sub("[private redacted]", value)
    value = CLAUDE_MEM_CONTEXT_RE.sub("[memory context redacted]", value)
    value = ANSI_RE.sub("", value)
    return value


def stable_hash(value: Any, prefix: str = "h") -> str:
    raw = json.dumps(value, sort_keys=True, default=str).encode("utf-8", errors="replace")
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()[:16]}"


def truncate_text(value: Any, max_chars: int = 1600) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        try:
            value = json.dumps(value, ensure_ascii=False, indent=2, default=str)
        except TypeError:
            value = str(value)
    value = strip_private_text(value)
    if len(value) <= max_chars:
        return value
    digest = stable_hash(value, prefix="sha")
    head = value[: max_chars // 2]
    tail = value[-max_chars // 2 :]
    return f"{head}\n\n[truncated {len(value) - max_chars} chars; {digest}]\n\n{tail}"


def parse_maybe_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


def parse_timestamp(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Accept seconds or milliseconds.
        if value > 10_000_000_000:
            value = value / 1000
        return datetime.fromtimestamp(float(value), tz=timezone.utc)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            pass
        # Common Claude/Codex JSONL timestamp formats sometimes use epoch strings.
        try:
            return parse_timestamp(float(text))
        except ValueError:
            return None
    return None


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def first_present(mapping: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def safe_read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def safe_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")
