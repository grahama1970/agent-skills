"""Detect Kimi web UI capacity / busy responses (not a completed answer).

Kimi sometimes returns short system messages instead of a real reply, for example:
  - "System is currently busy. Please try again later."
  - "Capacity is busy. Please wait or upgrade"

Surf kimi.submit and /ask webkimi must treat these as retryable failures, not
successful oracle completions (even if a sentinel accidentally appears).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

_KIMI_CAPACITY_STRONG = (
    re.compile(r"system\s+is\s+currently\s+busy", re.IGNORECASE),
    re.compile(r"capacity\s+is\s+busy", re.IGNORECASE),
)

_KIMI_CAPACITY_COMPOUND = (
    re.compile(
        r"system\s+is\s+currently\s+busy.*please\s+try\s+again\s+later",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"capacity\s+is\s+busy.*please\s+wait.*upgrade",
        re.IGNORECASE | re.DOTALL,
    ),
)


def is_kimi_capacity_busy(text: str) -> bool:
    """Return True when *text* looks like Kimi's capacity/busy system message."""
    sample = (text or "").strip()
    if len(sample) < 12:
        return False
    if any(p.search(sample) for p in _KIMI_CAPACITY_STRONG):
        return True
    if any(p.search(sample) for p in _KIMI_CAPACITY_COMPOUND):
        return True
    lowered = sample.lower()
    if "please try again later" in lowered and (
        "currently busy" in lowered or "system is" in lowered
    ):
        return True
    if "please wait" in lowered and "upgrade" in lowered and "capacity" in lowered:
        return True
    return False


def classify_kimi_response(text: str) -> str:
    """Classify assistant text: ``capacity_busy`` or ``ok``."""
    return "capacity_busy" if is_kimi_capacity_busy(text) else "ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Classify Kimi assistant text")
    parser.add_argument("--text", default="", help="Inline text to classify")
    parser.add_argument("--text-file", default="", help="Read text from file")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    args = parser.parse_args(argv)
    if args.text_file:
        body = Path(args.text_file).read_text(encoding="utf-8", errors="replace")
    else:
        body = args.text
    classification = classify_kimi_response(body)
    busy = classification == "capacity_busy"
    if args.json:
        print(json.dumps({"capacity_busy": busy, "classification": classification}))
    else:
        print(classification)
    return 2 if busy else 0


if __name__ == "__main__":
    raise SystemExit(main())


class KimiCapacityBusyError(RuntimeError):
    """Kimi returned a capacity/busy system message instead of a real answer."""

    def __init__(self, message: str = "", *, response_excerpt: str = "") -> None:
        detail = message or (
            "Kimi web UI reported system/capacity busy. "
            "Wait and retry, try another tab, or upgrade the Kimi account."
        )
        if response_excerpt:
            excerpt = response_excerpt.strip().replace("\n", " ")[:240]
            detail = f"{detail}\n\nKimi message excerpt: {excerpt}"
        super().__init__(detail)
        self.response_excerpt = response_excerpt
