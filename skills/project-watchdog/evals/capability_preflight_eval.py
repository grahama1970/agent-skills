#!/usr/bin/env python3
"""Fault-injection eval for the cron capability preflight (#1644).

Deterministic and fault-injected (mocked=true): monkeypatches each dependency
probe to fail one at a time and asserts the capability receipt names the failed
dependency, dispatch_allowed() pauses NEW leases, and restoring the probe plus a
fresh preflight auto-resumes dispatch. A stale and a missing receipt both refuse
dispatch with a retryable reason (no ops-discord, no human hold). Expected
outcomes were frozen before running against the candidate.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

WATCHDOG = Path(os.environ.get(
    "WATCHDOG_SCRIPTS",
    str(Path(__file__).resolve().parents[1] / "scripts"),
))
sys.path.insert(0, str(WATCHDOG))
from watchdog import capability_preflight as cp  # noqa: E402

DEPS = ("gh", "triage_runner", "memory", "ask")


def main() -> int:
    checks: list[dict] = []

    def check(name: str, got, expected, note: str = "") -> None:
        checks.append({"name": name, "passed": got == expected,
                       "got": got, "expected": expected, "note": note})

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        cp.config.state_root = lambda: root  # type: ignore[assignment]
        all_ok = {n: (lambda: (True, "ok")) for n in DEPS}

        # Fault-inject each dependency in turn.
        for broken in DEPS:
            probes = dict(all_ok)
            probes[broken] = lambda b=broken: (False, f"{b}_down")
            cp.PROBES = probes
            r = cp.run()
            check(f"receipt_names_{broken}", broken in r["failed"], True)
            check(f"dispatch_not_ready_{broken}", r["dispatch_ready"], False)
            allowed, why = cp.dispatch_allowed()
            check(f"dispatch_paused_{broken}", allowed, False)
            check(f"reason_dependency_down_{broken}", why["reason"], "capability_dependency_down")
            # retryable, not a human hold -> nothing to ops-discord.
            check(f"no_human_hold_{broken}", "human" in json.dumps(why).lower(), False)

        # Restore + fresh preflight auto-resumes.
        cp.PROBES = all_ok
        cp.run()
        allowed, why = cp.dispatch_allowed()
        check("auto_resume_after_restore", allowed, True)
        check("auto_resume_reason", why["reason"], "ready")

        # Stale receipt refuses (retryable).
        real = time.time
        cp.run()
        try:
            cp.time.time = lambda: real() + cp.DEFAULT_MAX_AGE_SECONDS + 10  # type: ignore[attr-defined]
            allowed, why = cp.dispatch_allowed()
            check("stale_receipt_refuses", allowed, False)
            check("stale_reason", why["reason"], "capability_receipt_stale")
        finally:
            cp.time.time = real  # type: ignore[attr-defined]

        # Missing receipt refuses with an actionable (non-human) reason.
        (root / cp.RECEIPT_FILE).unlink()
        allowed, why = cp.dispatch_allowed()
        check("missing_receipt_refuses", allowed, False)
        check("missing_reason", why["reason"], "no_capability_receipt")
        check("missing_has_next", "next" in why, True)

    passed = all(c["passed"] for c in checks)
    result = {"schema": "project_watchdog.capability_preflight_eval.v1",
              "mocked": True, "live": False, "passed": passed, "checks": checks}
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/watchdog-capability-preflight-result.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": passed,
                      "failing": [c["name"] for c in checks if not c["passed"]]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
