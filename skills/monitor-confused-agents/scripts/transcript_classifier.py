"""Deterministic transcript classification for stopped Herdr panes."""

from __future__ import annotations

import re


GOAL_COMPLETE_PATTERNS = [
    r"\bgoal achieved\b",
    r"\bdone_with_receipt\b",
    r"\bachieved_with_receipt\s*:",
    r"\bimmutable goal\b.{0,180}\b(achieved|met|satisfied)\b",
]

GOAL_INCOMPLETE_PATTERNS = [
    r"\bgoal\b.{0,180}\b(blocked|unmet|not met|not achieved|remaining)\b",
    r"\bimmutable goal\b.{0,180}\b(blocked|unmet|not met|not achieved|remaining|unknown)\b",
]

EXHAUSTED_BLOCKER_PATTERN = (
    r"\bimmutable goal\s*:\s*blocked\s*:[^\n]+[\s\S]{0,800}"
    r"\bunblock attempts\s*:\s*brave-search\s*=\s*(used\s*:[^;\n]+|not_applicable\s*:[^;\n]+)\s*;\s*"
    r"webgpt\s*=\s*(used\s*:[^\n]+|not_applicable\s*:[^\n]+)"
)


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
    lowered = text.lower()
    if _find_patterns(lowered, GOAL_INCOMPLETE_PATTERNS):
        return {"state": "unmet", "source": "latest_transcript_region"}
    if _find_patterns(lowered, GOAL_COMPLETE_PATTERNS):
        return {"state": "achieved", "source": "latest_transcript_region"}
    if "immutable goal" in lowered:
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
    return bool(re.search(EXHAUSTED_BLOCKER_PATTERN, text, flags=re.IGNORECASE | re.MULTILINE))


def _find_patterns(text: str, patterns: list[str]) -> list[str]:
    return [pattern for pattern in patterns if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE | re.DOTALL)]
