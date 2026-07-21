"""Deterministic transcript classification for stopped Herdr panes."""

from __future__ import annotations

import re


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


def transcript_goal_claim(text: str) -> dict[str, str]:
    line = structured_line_value(text, "Immutable Goal")
    if line:
        lowered = line.lower()
        if lowered.startswith("achieved_with_receipt:") or lowered == "done_with_receipt":
            return {"state": "achieved", "source": "immutable_goal_line"}
        if lowered.startswith("blocked:"):
            return {"state": "blocked", "source": "immutable_goal_line"}
        if lowered.startswith(("not_met", "unknown")):
            return {"state": "unmet", "source": "immutable_goal_line"}
        return {"state": "mentioned", "source": "immutable_goal_line"}
    if re.search(r"^\s*goal achieved\b", text, flags=re.IGNORECASE | re.MULTILINE):
        return {"state": "achieved", "source": "status_line"}
    if re.search(r"^\s*done_with_receipt\b", text, flags=re.IGNORECASE | re.MULTILINE):
        return {"state": "achieved", "source": "status_line"}
    if "immutable goal" in text.lower():
        return {"state": "mentioned", "source": "latest_transcript_region"}
    return {"state": "none", "source": "latest_transcript_region"}


def goal_allows_stop(text: str, *, goal_found: bool, has_early_markers: bool) -> bool:
    if has_early_markers:
        return False
    if exhausted_blocker_claim(text):
        return True
    claim = transcript_goal_claim(text)
    if not goal_found and claim["state"] == "none":
        return True
    return claim["state"] == "achieved"


def exhausted_blocker_claim(text: str) -> bool:
    goal = structured_line_value(text, "Immutable Goal")
    attempts = structured_line_value(text, "Unblock Attempts")
    if not goal or not goal.lower().startswith("blocked:") or not attempts:
        return False
    parsed = parse_unblock_attempts(attempts)
    brave = parsed.get("brave-search")
    reviewer = parsed.get("browser-oracle") or parsed.get("webgpt")
    return bool(valid_attempt_value(brave) and valid_attempt_value(reviewer))


def structured_line_value(text: str, label: str) -> str:
    match = re.search(rf"^\s*{re.escape(label)}\s*:\s*(.+?)\s*$", text, flags=re.IGNORECASE | re.MULTILINE)
    return match.group(1).strip() if match else ""


def parse_unblock_attempts(text: str) -> dict[str, str]:
    attempts: dict[str, str] = {}
    for part in text.split(";"):
        if "=" not in part:
            continue
        key, value = part.split("=", 1)
        attempts[key.strip().lower()] = value.strip()
    return attempts


def valid_attempt_value(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.lower()
    return lowered.startswith("used:") or lowered.startswith("not_applicable:")
