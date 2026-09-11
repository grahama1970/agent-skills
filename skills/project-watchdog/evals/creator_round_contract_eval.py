#!/usr/bin/env python3
"""Creator-round contract eval (#1655).

Deterministic (mocked=true): the repair task the watchdog compiles must give the
CREATOR ROUND a propose-and-commit contract (no VERDICT, not expected to have run
the proof) and confine the "proof must have actually run" rule to the REVIEWER
ROUND. This is what stops the local claude lane from fail-closing its own first
round for lacking proof that belongs to later rounds. Seat-family agnostic: the
same split holds for the non-codex local lane and the codex lane.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WATCHDOG = Path(os.environ.get(
    "WATCHDOG_SCRIPTS",
    str(Path(__file__).resolve().parents[1] / "scripts"),
))
sys.path.insert(0, str(WATCHDOG))
from watchdog.handlers import build_repair_task  # noqa: E402


def main() -> int:
    checks: list[dict] = []

    def check(name, got, expected):
        checks.append({"name": name, "passed": got == expected, "got": got, "expected": expected})

    task = build_repair_task(repo="grahama1970/agent-skills", issue_number=1655,
                             issue_title="t", issue_body="BODY", targets=["skills/x"])
    creator = task.split("REVIEWER ROUND")[0]
    reviewer = task.split("REVIEWER ROUND", 1)[1]

    check("has_creator_round", "CREATOR ROUND" in task, True)
    check("has_reviewer_round", "REVIEWER ROUND" in task, True)
    check("creator_commits", "CREATOR: DONE" in creator, True)
    check("creator_defers_proof",
          "not expected to have run the ticket's proof command" in creator.replace("NOT ", "not "), True)
    # The fail-closed "proof must have actually run" rule must NOT sit in the creator round.
    check("creator_has_no_proof_gate", "proof command has actually run" not in creator, True)
    check("reviewer_owns_proof_gate", "proof command has actually run" in reviewer, True)
    check("only_reviewer_emits_verdict", "only the reviewer emits it" in reviewer, True)
    check("ticket_body_included", "BODY" in task, True)

    passed = all(c["passed"] for c in checks)
    result = {"schema": "project_watchdog.creator_round_contract_eval.v1", "mocked": True,
              "live": False, "passed": passed, "checks": checks}
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/watchdog-creator-round.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": passed, "failing": [c["name"] for c in checks if not c["passed"]]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
