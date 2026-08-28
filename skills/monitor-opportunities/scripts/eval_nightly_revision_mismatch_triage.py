#!/usr/bin/env python3
"""Regression guard for the nightly revision-mismatch triage loop."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


INCIDENT = {
    "code": "NIGHTLY_REVISION_MISMATCH",
    "message": (
        "Expected 06f73f000188c5f448f7184335058506b86c5211, "
        "got 1368ee62e3a8fe5fd4d991ff897019267df2d34b"
    ),
    "status": "ERROR",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _run(argv: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=False)


def main() -> int:
    repo = _repo_root()
    triage = repo / "skills" / "triage-error" / "run.sh"
    ticket = repo / "skills" / "ticket" / "run.sh"
    signal = json.dumps(INCIDENT, separators=(",", ":"))

    classified = _run(
        [
            str(triage),
            "classify",
            "--text",
            signal,
            "--layer",
            "monitor-opportunities",
        ],
        cwd=repo,
    )
    if classified.returncode != 0:
        print("TRIAGE_COMMAND_FAILED", classified.stderr[-1000:], file=sys.stderr)
        return 1
    report = json.loads(classified.stdout)
    expected_code = "monitor_opportunities_nightly_revision_mismatch"
    if report.get("code") != expected_code:
        print(f"REVISION_MISMATCH_UNCLASSIFIED code={report.get('code')}", file=sys.stderr)
        return 1
    if report.get("ambiguous") is not False:
        print("REVISION_MISMATCH_STILL_AMBIGUOUS", file=sys.stderr)
        return 1
    next_command = str(report.get("next_command") or "")
    for required in (
        "skills/monitor-opportunities/run.sh schedule --promoted-stage0",
        "skills/ticket",
        "route:ops_or_scheduler",
        "project-watchdog",
    ):
        if required not in next_command:
            print(f"TRIAGE_NEXT_COMMAND_MISSING {required}", file=sys.stderr)
            return 1

    ticket_preview = _run(
        [
            str(ticket),
            "bug",
            "Repair stale monitor-opportunities nightly scheduler revision pin",
            "--target",
            "skills/monitor-opportunities",
            "--observed",
            "[monitor_opportunities_nightly_revision_mismatch] scheduler log emitted NIGHTLY_REVISION_MISMATCH from a stale --expected-revision pin.",
            "--expected",
            "The nightly scheduler registration tracks the intended worktree revision and any recurring mismatch is classified, ticketed, and routable to project-watchdog.",
            "--repro",
            "skills/triage-error/run.sh classify --text '<NIGHTLY_REVISION_MISMATCH receipt>' --layer monitor-opportunities",
            "--proof",
            "skills/agentic-evals/run.sh run skills/monitor-opportunities/fixtures/agentic_eval.json --case nightly-revision-mismatch-triage-regression-2026-08-28 --output /tmp/monitor-opportunities-nightly-revision-mismatch-agentic-eval.json",
            "--route",
            "ops_or_scheduler",
            "--label",
            "agent-work",
            "--label",
            "type:bug",
            "--label",
            "route:ops_or_scheduler",
            "--required-skill",
            "monitor-opportunities",
            "--required-skill",
            "triage-error",
            "--required-skill",
            "agentic-evals",
            "--json",
        ],
        cwd=repo,
    )
    if ticket_preview.returncode != 0:
        print("TICKET_PREVIEW_FAILED", ticket_preview.stderr[-1200:], file=sys.stderr)
        return 1
    for marker in (
        "Repair stale monitor-opportunities nightly scheduler revision pin",
        "route:ops_or_scheduler",
        "agent-work",
        "NIGHTLY_REVISION_MISMATCH",
    ):
        if marker not in ticket_preview.stdout:
            print(f"TICKET_PREVIEW_MISSING {marker}", file=sys.stderr)
            return 1

    print(
        "NIGHTLY_REVISION_MISMATCH_TRIAGE_OK "
        f"code={report['code']} ambiguous={report['ambiguous']} recoverable={report['recoverable']}"
    )
    print("TICKET_PREVIEW_ROUTABLE_OK route=ops_or_scheduler label=agent-work")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
