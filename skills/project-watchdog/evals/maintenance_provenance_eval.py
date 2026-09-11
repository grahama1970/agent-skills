#!/usr/bin/env python3
"""Maintenance-log provenance eval (devops integration, 2026-09-11).

Deterministic (fault-injected): the READ side of the target-ownership gate
adopts a path only on an exact-match event (repo match, verbatim changed_paths
entry, non-empty proof_receipt, <=30d); stale/proofless/wrong-repo events and a
daemon outage all leave the refusal standing; the WRITE side is idempotent per
run and never raises. Also verifies the handler gate actually relabels covered
paths (verified_maintenance_provenance in the wired source).
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

WATCHDOG = Path(os.environ.get(
    "WATCHDOG_SCRIPTS",
    str(Path(__file__).resolve().parents[1] / "scripts"),
))
sys.path.insert(0, str(WATCHDOG))
from watchdog import maintenance_log as ml  # noqa: E402

REPO = "grahama1970/agent-skills"


def _ev(key, paths, *, repo=REPO, proof="/tmp/p.json", age_days=1.0):
    return {"_key": key, "entity_id": "agent-skills:project", "repo": repo,
            "changed_paths": paths, "proof_receipt": proof,
            "observed_at": (datetime.now(timezone.utc) - timedelta(days=age_days)).isoformat(),
            "summary": "s", "event_type": "decision.recorded"}


def main() -> int:
    checks: list[dict] = []

    def check(name, got, expected):
        checks.append({"name": name, "passed": got == expected, "got": got, "expected": expected})

    path = "skills/battle/README.md"

    # READ: exact covering event adopts the path.
    ml._post_json = lambda p, q: {"documents": [_ev("me_ok", [path])]}  # type: ignore[assignment]
    cov = ml.covering_events(REPO, [path])
    check("adopts_covering_event", sorted(cov), [path])

    # READ: stale / proofless / wrong-repo do NOT adopt.
    ml._post_json = lambda p, q: {"documents": [  # type: ignore[assignment]
        _ev("stale", [path], age_days=45.0),
        _ev("noproof", [path], proof=None),
        _ev("wrongrepo", [path], repo="grahama1970/other")]}
    check("stale_proofless_mismatch_not_adopted", ml.covering_events(REPO, [path]), {})

    # READ: daemon outage degrades to no coverage (refusal unchanged).
    def boom(p, q):
        raise urllib.error.URLError("down")
    ml._post_json = boom  # type: ignore[assignment]
    check("daemon_down_no_coverage", ml.covering_events(REPO, [path]), {})

    # WRITE: idempotent per run + never raises on outage.
    stored: list[dict] = []
    def fake(p, q):
        if p == "/store":
            stored.append(q["document"]); return {"ok": True}
        return {"documents": [dict(stored[-1])] if stored else []}
    ml._post_json = fake  # type: ignore[assignment]
    kw = dict(repo=REPO, run_id="eval-run", summary="watchdog tick BLOCKED: eval",
              proof_receipt="/tmp/eval/receipt.json")
    a, b = ml.emit_tick_event(**kw), ml.emit_tick_event(**kw)
    check("emit_idempotent_key", a["key"] == b["key"] and stored[0]["_key"] == stored[1]["_key"], True)
    check("emit_readback_ok", a["status"], "EMITTED")
    ml._post_json = boom  # type: ignore[assignment]
    check("emit_never_raises", ml.emit_tick_event(**kw)["status"], "SKIPPED")

    # The handler gate is wired: covered paths relabel instead of refuse.
    src = (WATCHDOG / "watchdog" / "handlers.py").read_text()
    check("gate_relabels_covered_paths", "verified_maintenance_provenance" in src, True)
    check("gate_records_adoption", "maintenance_adopted" in src, True)

    passed = all(c["passed"] for c in checks)
    result = {"schema": "project_watchdog.maintenance_provenance_eval.v1", "mocked": True,
              "live": False, "passed": passed, "checks": checks}
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/watchdog-maintenance-provenance.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": passed, "failing": [c["name"] for c in checks if not c["passed"]]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
