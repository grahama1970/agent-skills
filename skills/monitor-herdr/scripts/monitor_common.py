#!/usr/bin/env python3
"""Shared paths, timestamps, and receipt writers for the monitor-herdr modules.

Split out of monitor_herdr.py so the feature modules beside it can use these
without importing the monitor back and creating a cycle.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
STATE_ROOT = Path.home() / ".local" / "state" / "monitor-herdr"
LOG_DIR = STATE_ROOT / "logs"
RECEIPT_ROOT = STATE_ROOT / "receipts"
STATE_PATH = STATE_ROOT / "state.json"
TICKET_CACHE_PATH = STATE_ROOT / "ticket-cache.json"
LOCK_DIR = STATE_ROOT / "lock"
LOCK_PATH = STATE_ROOT / "monitor.lock"
FILE_VIEWER_PLUGIN_ID = "herdr-file-viewer"
FILE_VIEWER_ENTRYPOINT = "file-viewer"

# Shared by the classifier and the prompt submitter.
EARLY_STOP_PATTERNS = [
    r"\bwhat remains\b",
    r"\bremaining work\b",
    r"\bif continuing\b",
    r"\bif you want\b",
    r"\bcould pursue next steps\b",
    r"\bbroader route audit\b",
    r"\bstop condition reached\b",
    r"\bstop hook \((?:blocked|stopped)\)",
    r"\bstatus response blocked as too vague\b",
    r"\bclosure claim lacks deterministic proof\b",
    r"\bclosure claim blocked\b",
]

HUMAN_BLOCKER_PATTERNS = [
    r"\bneeds human\b",
    r"\bhuman intervention\b",
    r"\bhuman decision\b",
    r"\bwaiting for human\b",
    r"\bmissing credential\b",
    r"\bmissing secret\b",
    r"\bmissing api key\b",
    r"\bapproval required\b",
    r"\bexternal state\b",
    r"\bcannot obtain\b",
    r"\bblocked_by_systemic_failure\b",
]


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    RECEIPT_ROOT.mkdir(parents=True, exist_ok=True)
def timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
def current_epoch() -> int:
    return int(datetime.now(UTC).timestamp())
def log_event(run_id: str, message: str, **fields: Any) -> None:
    event = {"ts": now_iso(), "run_id": run_id, "message": message, **fields}
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "monitor-herdr.log").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True) + "\n")
def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp_path.replace(path)
def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")


def redact_api_record(record: dict[str, Any]) -> dict[str, Any]:
    clean = json.loads(json.dumps(record))
    result = clean.get("response", {}).get("result", {})
    if isinstance(result, dict):
        read = result.get("read")
        if isinstance(read, dict) and isinstance(read.get("text"), str) and len(read["text"]) > 1200:
            read["text"] = read["text"][-1200:]
        panes = result.get("panes")
        if isinstance(panes, list) and len(panes) > 30:
            result["panes"] = panes[:30]
            result["panes_truncated"] = len(panes) - 30
    return clean
