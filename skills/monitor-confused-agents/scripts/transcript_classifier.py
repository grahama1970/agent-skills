"""Deterministic transcript classification for stopped Herdr panes."""

from __future__ import annotations

import re
from pathlib import Path


def latest_transcript_region(text: str, limit: int = 2800) -> str:
    if not text:
        return ""
    text = strip_monitor_prompt(text)
    parts = re.split(r"\n[^\n]*Worked for [^\n]*\n", text)
    region = parts[-1] if parts else text
    return region[-limit:]


def strip_monitor_prompt(text: str) -> str:
    return re.sub(
        r"RESTART CHECK FROM monitor-confused-agents[\s\S]*?(?=\n\s*gpt-[^\n]*·)",
        "",
        text,
        flags=re.IGNORECASE,
    )


def transcript_goal_claim(text: str, *, project_root: Path | None = None) -> dict[str, str]:
    block = latest_operational_block(text)
    line = structured_line_value(block, "Immutable Goal")
    if line:
        lowered = line.lower()
        if lowered.startswith("achieved_with_receipt:"):
            receipt = line.split(":", 1)[1].strip()
            return {"state": "achieved" if path_inside_project(receipt, project_root) else "unmet", "source": "immutable_goal_line"}
        if lowered == "done_with_receipt":
            return {"state": "achieved", "source": "immutable_goal_line"}
        if lowered.startswith("blocked:"):
            return {"state": "blocked", "source": "immutable_goal_line"}
        if lowered.startswith(("not_met", "unknown")):
            return {"state": "unmet", "source": "immutable_goal_line"}
        return {"state": "mentioned", "source": "immutable_goal_line"}
    if re.search(r"^\s*(?:gpt-[^\n]*\s+.*?\s+)?Goal achieved(?:\s*\([^)]*\))?\s*$", block, flags=re.MULTILINE):
        return {"state": "achieved", "source": "status_line"}
    if re.search(r"^\s*(?:gpt-[^\n]*\s+.*?\s+)?Goal blocked(?:\s*\([^)]*\))?\s*$", block, flags=re.MULTILINE):
        return {"state": "blocked", "source": "status_line"}
    if re.search(r"^\s*DONE_WITH_RECEIPT(?:\s|$)", block, flags=re.MULTILINE):
        return {"state": "achieved", "source": "status_line"}
    if "immutable goal" in block.lower():
        return {"state": "mentioned", "source": "latest_transcript_region"}
    return {"state": "none", "source": "latest_transcript_region"}


def goal_allows_stop(text: str, *, goal_found: bool, has_early_markers: bool, project_root: Path | None = None) -> bool:
    if has_early_markers:
        return False
    if exhausted_blocker_claim(text, project_root=project_root):
        return True
    claim = transcript_goal_claim(text, project_root=project_root)
    if not goal_found and claim["state"] == "none":
        return True
    return claim["state"] == "achieved"


def exhausted_blocker_claim(text: str, *, project_root: Path | None = None) -> bool:
    block = latest_operational_block(text)
    goal = structured_line_value(block, "Immutable Goal")
    attempts = structured_line_value(block, "Unblock Attempts")
    if not goal or not goal.lower().startswith("blocked:") or not attempts:
        return False
    parsed = parse_unblock_attempts(attempts)
    brave = parsed.get("brave-search")
    reviewer = parsed.get("browser-oracle")
    return bool(valid_attempt_value(brave, project_root=project_root) and valid_attempt_value(reviewer, project_root=project_root))


def latest_operational_block(text: str) -> str:
    """Return the newest status block so old unblock attempts cannot satisfy a new blocker."""
    matches = list(re.finditer(r"^\s*(?:Status/Phase|Immutable Goal)\s*:", text, flags=re.IGNORECASE | re.MULTILINE))
    if not matches:
        return text
    return text[matches[-1].start():]


def structured_line_value(text: str, label: str) -> str:
    matches = list(re.finditer(rf"^\s*{re.escape(label)}\s*:\s*(.+?)\s*$", text, flags=re.IGNORECASE | re.MULTILINE))
    return matches[-1].group(1).strip() if matches else ""


def parse_unblock_attempts(text: str) -> dict[str, str]:
    attempts: dict[str, str] = {}
    for part in text.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        attempts[key.strip().lower()] = value.strip()
    return attempts


def valid_attempt_value(value: str | None, *, project_root: Path | None = None) -> bool:
    if not value:
        return False
    lowered = value.lower()
    if lowered.startswith("not_applicable:"):
        return bool(value.split(":", 1)[1].strip())
    if lowered.startswith("used:"):
        return path_inside_project(value.split(":", 1)[1].strip(), project_root)
    return False


def path_inside_project(value: str, project_root: Path | None) -> bool:
    if not value:
        return False
    path = Path(value).expanduser()
    if not path.is_absolute():
        if project_root is None:
            return True
        path = project_root / path
    try:
        resolved = path.resolve()
    except OSError:
        return False
    if project_root is None:
        return resolved.is_file()
    try:
        root = project_root.resolve()
    except OSError:
        return False
    return resolved.is_file() and resolved.is_relative_to(root)
