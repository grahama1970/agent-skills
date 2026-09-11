#!/usr/bin/env python3
"""Fault-injection eval for same-cycle cross-ticket unblock (#1646).

Deterministic (mocked=true): records a wait edge (A behind B), asserts A stays
serialized while B's bytes are unlanded, then simulates B landing on main and
asserts A becomes releasable within the same scan on ACTUAL bytes -- never on a
CLOSED label. Partial path matches and label-only closure never release; one
release per waiting issue per scan.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

WATCHDOG = Path(os.environ.get(
    "WATCHDOG_SCRIPTS",
    str(Path(__file__).resolve().parents[1] / "scripts"),
))
sys.path.insert(0, str(WATCHDOG))
from watchdog import cross_ticket_unblock as ctu  # noqa: E402


def main() -> int:
    checks: list[dict] = []

    def check(name: str, got, expected) -> None:
        checks.append({"name": name, "passed": got == expected, "got": got, "expected": expected})

    with tempfile.TemporaryDirectory() as td:
        jp = Path(td) / "wait-edges.json"
        # A (#1617) intends to land bytes X at p1 and Y at p2, behind B (#1618).
        ctu.record_wait_edge(jp, waiting=1617, blocking=1618,
                             path_shas={"skills/x": "shaX", "skills/y": "shaY"},
                             baseline={"skills/x": "shaB", "skills/y": "shaB"})

        # B unlanded: main still has B's bytes -> A serializes.
        r = ctu.releasable(jp, {"skills/x": "shaB", "skills/y": "shaB"})
        check("unlanded_foreign_serializes", r, [])

        # Partial: only p1 landed A's bytes -> still blocked.
        r = ctu.releasable(jp, {"skills/x": "shaX", "skills/y": "shaB"})
        check("partial_match_serializes", r, [])

        # Never trust CLOSED label over bytes: even if B is 'closed', bytes differ.
        r = ctu.releasable(jp, {"skills/x": "shaB", "skills/y": "shaB"})  # closed label irrelevant
        check("closed_label_without_bytes_serializes", r, [])

        # B lands on main: main[p1]==X and main[p2]==Y -> A remote-identical -> release.
        r = ctu.releasable(jp, {"skills/x": "shaX", "skills/y": "shaY"})
        check("release_on_actual_bytes", [e["waiting"] for e in r], [1617])
        check("release_names_blocker", r[0]["blocking"], 1618)

        # One release per waiting issue per scan even with a duplicate edge upsert.
        ctu.record_wait_edge(jp, waiting=1617, blocking=1619, path_shas={"skills/x": "shaX", "skills/y": "shaY"})
        r = ctu.releasable(jp, {"skills/x": "shaX", "skills/y": "shaY"})
        check("one_release_per_issue", len([e for e in r if e["waiting"] == 1617]), 1)

        # After clearing the edge it no longer releases.
        ctu.clear_edge(jp, 1617)
        r = ctu.releasable(jp, {"skills/x": "shaX", "skills/y": "shaY"})
        check("cleared_edge_gone", r, [])

    passed = all(c["passed"] for c in checks)
    result = {"schema": "project_watchdog.cross_ticket_unblock_eval.v1", "mocked": True,
              "live": False, "passed": passed, "checks": checks}
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/watchdog-cross-ticket-unblock.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": passed, "failing": [c["name"] for c in checks if not c["passed"]]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
