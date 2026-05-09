"""Transcript discovery and JSONL extraction."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .utils import parse_timestamp, to_iso


@dataclass
class TranscriptEntry:
    line_number: int
    path: str
    timestamp: str | None
    data: dict[str, Any]


def discover_transcripts(project_root: Path, limit: int = 50) -> list[Path]:
    """Find likely Codex/Claude transcript JSONL files without assuming one runtime."""
    candidates: list[Path] = []
    search_roots = [
        project_root / ".codex",
        project_root / ".claude",
        Path.home() / ".codex" / "sessions",
        Path.home() / ".codex" / "history.jsonl",
        Path.home() / ".claude" / "projects",
    ]

    for root in search_roots:
        if not root.exists():
            continue
        if root.is_file() and root.suffix == ".jsonl":
            candidates.append(root)
            continue
        if root.is_dir():
            candidates.extend(root.rglob("*.jsonl"))

    # Sort newest first and dedupe.
    unique = sorted(set(candidates), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return unique[:limit]


def timestamp_from_entry(entry: dict[str, Any]) -> Any:
    """Pull timestamp from common transcript/hook fields."""
    for key in ("timestamp", "created_at", "created_at_epoch", "time", "ts", "at"):
        if key in entry:
            return entry[key]
    message = entry.get("message")
    if isinstance(message, dict):
        for key in ("timestamp", "created_at", "time"):
            if key in message:
                return message[key]
    return None


def read_jsonl(path: Path, since: str | None = None, tail: int | None = None) -> list[TranscriptEntry]:
    """Read a transcript JSONL file and return parsed entries.

    Malformed lines are represented as data={"_parse_error": ...} so the cleaner can
    count them without failing the scan.
    """
    since_dt = parse_timestamp(since) if since else None
    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if tail and tail > 0:
        start_line = max(0, len(raw_lines) - tail)
        indexed_lines = list(enumerate(raw_lines[start_line:], start=start_line + 1))
    else:
        indexed_lines = list(enumerate(raw_lines, start=1))

    entries: list[TranscriptEntry] = []
    for line_number, line in indexed_lines:
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            if not isinstance(data, dict):
                data = {"value": data}
        except json.JSONDecodeError as exc:
            data = {"_parse_error": str(exc), "raw_excerpt": line[:500]}

        dt = parse_timestamp(timestamp_from_entry(data))
        if since_dt and dt and dt < since_dt:
            continue
        entries.append(
            TranscriptEntry(
                line_number=line_number,
                path=str(path),
                timestamp=to_iso(dt),
                data=data,
            )
        )
    return entries


def read_many(paths: Iterable[Path], since: str | None = None, tail: int | None = None) -> list[TranscriptEntry]:
    entries: list[TranscriptEntry] = []
    for path in paths:
        entries.extend(read_jsonl(path, since=since, tail=tail))
    entries.sort(key=lambda e: (e.timestamp or "", e.path, e.line_number))
    return entries
