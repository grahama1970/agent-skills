#!/usr/bin/env python3
"""Retained guard for agentic-evals proof discipline.

A guarded done answer that names an agentic-evals gate must cite a READY
agentic_evals.report.v2 receipt. Plain prose or a hand-written proof summary is
not enough.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "shame" / "run.sh"


def write_candidate(path: Path, status: dict[str, Any], intro: str = "") -> None:
    path.write_text(f"{intro}\n```json\n{json.dumps(status)}\n```\n", encoding="utf-8")


def preflight(path: Path) -> tuple[int, dict[str, Any]]:
    proc = subprocess.run([str(RUN), "preflight", str(path)], text=True, capture_output=True, timeout=30, check=False)
    return proc.returncode, json.loads(proc.stdout)


def base_status(proof: Path, command: str, result: str) -> dict[str, Any]:
    return {
        "schema": "pi.agent_status.v1",
        "goal": "Verify the focused $agentic-evals gate.",
        "state": "done",
        "answer": "The focused agentic-evals gate is READY.",
        "plain_answer": "The focused agentic-evals gate is verified READY.",
        "changed": ["checked the agentic-evals gate"],
        "verified": [{"command": command, "result": result}],
        "proof": [str(proof)],
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="shame-ae-proof-") as raw:
        tmp = Path(raw)
        summary = tmp / "summary.txt"
        summary.write_text("readiness=READY\n", encoding="utf-8")
        bad = tmp / "bad.md"
        write_candidate(bad, base_status(summary, f"read {summary}", "readiness=READY"))
        bad_code, bad_report = preflight(bad)
        assert bad_code == 1, bad_report
        assert "agentic_evals_proof_required" in bad_report["reason_codes"], bad_report

        report = tmp / "agentic-report.json"
        command = "skills/agentic-evals/run.sh run skills/project-state/fixtures/agentic_eval.json"
        report.write_text(
            json.dumps(
                {
                    "schema": "agentic_evals.report.v2",
                    "readiness": "READY",
                    "outcome_counts": {"PASS": 1, "FAIL": 0, "BLOCKED": 0, "NOT_TESTED": 0},
                    "cases": [{"name": "focused-gate", "outcome": "PASS", "argv": command.split()}],
                }
            ),
            encoding="utf-8",
        )
        good = tmp / "good.md"
        write_candidate(good, base_status(report, command, "READY"))
        good_code, good_report = preflight(good)
        assert good_code == 0, good_report
        assert good_report["decision"] == "pass", good_report

        print(json.dumps({
            "schema": "lazy_report_shame.agentic_evals_proof_required_eval.v1",
            "bad_rejected": True,
            "good_passed": True,
            "bad_reason": "agentic_evals_proof_required",
        }, indent=2))


if __name__ == "__main__":
    main()
