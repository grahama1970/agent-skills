#!/usr/bin/env python3
"""Fleet reconciler eval (#1649).

Deterministic (mocked=true): a dirty fleet state carrying one of every residue
class maps each nonterminal object to exactly one of the four dispositions with
zero unclassified; the drained version reconciles to an empty disposition list
with drained=True (second pass idempotently empty); a genuinely unknown
nonterminal object parks as a human_only_blocker rather than looping.
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
from watchdog import reconciler  # noqa: E402


def dirty() -> dict:
    return {
        "issues": [
            {"number": 1, "runnable": True, "requires_human_input": False},
            {"number": 2, "runnable": False, "requires_human_input": True},
        ],
        "journals": [
            {"id": "j1", "settled": False, "retryable": True, "lease_released": True},
            {"id": "j2", "settled": False, "retryable": False, "lease_released": False},
            {"id": "j3", "settled": True},
        ],
        "leases": [{"issue": 9, "orphan": True}, {"issue": 10, "orphan": False}],
        "tau_runs": [
            {"id": "t1", "terminal": True, "awaiting_close": True},
            {"id": "t2", "terminal": True, "awaiting_proof": True},
            {"id": "t3", "terminal": False},
        ],
        "owned_bytes": [
            {"issue": 3, "path": "p", "remote_identical": False, "has_wait_edge": True},
            {"issue": 4, "path": "q", "remote_identical": False, "has_wait_edge": False},
            {"issue": 5, "path": "r", "remote_identical": True},
        ],
    }


def drained_state() -> dict:
    return {
        "issues": [],  # parked human blocker de-listed after disposition
        "journals": [{"id": "j3", "settled": True}],
        "leases": [{"issue": 10, "orphan": False}],
        "tau_runs": [{"id": "t3", "terminal": False}],
        "owned_bytes": [{"issue": 5, "path": "r", "remote_identical": True}],
    }


def main() -> int:
    checks: list[dict] = []

    def check(name: str, got, expected) -> None:
        checks.append({"name": name, "passed": got == expected, "got": got, "expected": expected})

    r = reconciler.reconcile(dirty())
    disp = {x["object"]: x["disposition"] for x in r["dispositions"]}
    check("unclassified_zero", r["unclassified"], 0)
    check("issue1_resume", disp["issue:1"], "resume_machine_work")
    check("issue2_human", disp["issue:2"], "human_only_blocker")
    check("journal_retryable_resume", disp["journal:j1"], "resume_machine_work")
    check("journal_stuck_settle", disp["journal:j2"], "settle_native_lifecycle")
    check("journal_settled_absent", "journal:j3" in disp, False)
    check("orphan_lease_settle", disp["lease:9"], "settle_native_lifecycle")
    check("healthy_lease_absent", "lease:10" in disp, False)
    check("tau_close_settle", disp["tau:t1"], "settle_native_lifecycle")
    check("tau_proof_resume", disp["tau:t2"], "resume_machine_work")
    check("tau_running_absent", "tau:t3" in disp, False)
    check("owned_waitedge_wait", disp["owned:3:p"], "wait_on_dependency")
    check("owned_no_edge_resume", disp["owned:4:q"], "resume_machine_work")
    check("owned_identical_absent", "owned:5:r" in disp, False)
    check("every_disposition_in_closed_set",
          all(d in reconciler.DISPOSITIONS for d in disp.values()), True)
    check("dirty_not_drained", r["drained"], False)

    # Drained: second pass idempotently empty, drained True (human blocker parked).
    r2 = reconciler.reconcile(drained_state())
    check("drained_dispositions_empty", r2["dispositions"], [])
    check("drained_true", r2["drained"], True)

    passed = all(c["passed"] for c in checks)
    result = {"schema": "project_watchdog.fleet_reconciler_eval.v1", "mocked": True,
              "live": False, "passed": passed, "checks": checks}
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/watchdog-fleet-reconciler.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": passed, "failing": [c["name"] for c in checks if not c["passed"]]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
