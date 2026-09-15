#!/usr/bin/env python3
"""Retain the #1658 blocked-fixer false-close incident as a regression guard."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "watchdog_v2.py"
SPEC = importlib.util.spec_from_file_location("watchdog_v2", SOURCE)
assert SPEC and SPEC.loader
watchdog = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = watchdog
SPEC.loader.exec_module(watchdog)


def main() -> None:
    receipt = json.loads((ROOT / "evals" / "receipts" / "issue-1658.json").read_text(encoding="utf-8"))
    assert receipt["outcome"] == "success"
    assert "Blocked, reporting rather than continuing" in receipt["pi_subagents"]["fixer"]["stdout"]
    assert receipt["pi_subagents"]["fixer"]["parsed"] is None
    assert not watchdog.reviewer_passed({"ok": True, "reviewer": {"result": {"ok": True}, "status": {"verdict": "PASS"}}, "fixer": {"status": None}})
    print("PROJECT_WATCHDOG_HISTORICAL_FALSE_CLOSE_DETECTED")


if __name__ == "__main__":
    main()
