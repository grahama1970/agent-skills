#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"


REQUIRED = [
    "## Current Evidence Gate",
    "current_evidence",
    "historical_context",
    "not_established",
    "context may explain why a decision was made",
    "current defect or current recommendation",
    "first check\nwhether it has already been implemented before listing it as a next action",
    "Do not produce a ranked design-change list from stale evidence.",
    "reviewing an old screenshot, stale CDP marker, previous commit, or memory",
    "listing a historical recommendation as a current action without first checking",
]

REQUIRED_OUTPUT_MARKERS = [
    "- evidence_status: current_evidence | historical_context | not_established",
    "- surface: <URL, route, screenshot, file, or component>",
    "- checked_at: <absolute timestamp or \"user-provided current screenshot\">",
    "- artifact: <command, marker, screenshot, source path, or receipt>",
]


def main() -> int:
    text = SKILL.read_text(encoding="utf-8")
    missing = [needle for needle in REQUIRED + REQUIRED_OUTPUT_MARKERS if needle not in text]
    if missing:
        print("missing stale-design prevention contract markers:")
        for item in missing:
            print(f"- {item}")
        return 1
    print("PASS: current-design evidence gate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
