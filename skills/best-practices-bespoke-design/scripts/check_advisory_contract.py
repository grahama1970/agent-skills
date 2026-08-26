#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "SKILL.md"


REQUIRED = [
    "Default to **targeted advisory repair**, not formal certification.",
    "Do not block a small repair because a full brand brief, competitor set, or formal",
    "Missing formal receipts, blind raters, crop",
    "Do not list missing formal gates as failures",
    "For targeted advisory and ordinary release-risk work, return:",
]

FORBIDDEN = [
    "Every run must report two separate verdicts when both are relevant",
    "Every status update and handoff must name:",
    "Default to `release-risk` for live website work.",
]


def main() -> int:
    text = SKILL.read_text(encoding="utf-8")
    missing = [needle for needle in REQUIRED if needle not in text]
    forbidden = [needle for needle in FORBIDDEN if needle in text]
    if missing or forbidden:
        if missing:
            print("missing advisory contract markers:")
            for item in missing:
                print(f"- {item}")
        if forbidden:
            print("stale strict contract markers still present:")
            for item in forbidden:
                print(f"- {item}")
        return 1
    print("PASS: advisory-first bespoke design contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
