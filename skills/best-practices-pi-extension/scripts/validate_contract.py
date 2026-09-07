#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REQUIRED = [
    "Typed boundary first",
    "Shame-compatible status",
    "Bidirectional means peer-gated",
    "Use the owner bridge for terminal discovery",
    "Route failures through `$triage-error`",
    "Retained `$agentic-evals` before done",
    "TypeBox",
    "Pydantic",
    "pi.agent_status.v1",
    "lazy_report_shame.collab_question.v1",
    "lazy_report_shame.collab_answer.v1",
    "$ops-herdr",
]

path = Path(__file__).resolve().parents[1] / "SKILL.md"
text = path.read_text()
missing = [item for item in REQUIRED if item not in text]
if missing:
    print({"status": "FAIL", "missing": missing})
    sys.exit(1)
print({"status": "PASS", "checked": len(REQUIRED)})
