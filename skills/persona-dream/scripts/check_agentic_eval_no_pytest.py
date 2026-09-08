#!/usr/bin/env python3
"""Reject Persona Dream agentic-eval cases that delegate proof to pytest."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def command_text(command: Any) -> str:
    if isinstance(command, list):
        return " ".join(str(part) for part in command)
    return str(command or "")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    offenders = []
    for case in fixture.get("cases") or []:
        text = command_text(case.get("command"))
        if "pytest" in text:
            offenders.append({"case": case.get("name") or case.get("id"), "command": text})
    receipt = {
        "schema": "persona_dream.agentic_eval_no_pytest_receipt.v1",
        "status": "PASS" if not offenders else "BLOCKED_SELF_SERVING_UNIT_TEST_DRIVER",
        "fixture": str(args.fixture),
        "case_count": len(fixture.get("cases") or []),
        "offenders": offenders,
        "claims": {
            "proves": "Persona Dream agentic-evals cases do not use pytest as the proof driver.",
            "does_not_prove": "The individual pipeline steps are correct; run agentic-evals for that.",
        },
    }
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0 if not offenders else 1


if __name__ == "__main__":
    raise SystemExit(main())
