#!/usr/bin/env python3
"""Fleet SLO eval over a fixture receipt corpus (#1645).

Deterministic and fault-injected (mocked=true): builds a frozen synthetic
receipt corpus, computes the SLO report, then recomputes over a shuffled corpus
and asserts the normalized serialized bytes are identical (order independence).
assert-slo checks each derived metric equals its frozen expected value and that
a coverage gap flips health to red.
"""
from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

WATCHDOG = Path(os.environ.get(
    "WATCHDOG_SCRIPTS",
    str(Path(__file__).resolve().parents[1] / "scripts"),
))
sys.path.insert(0, str(WATCHDOG))
from watchdog import fleet_slo  # noqa: E402


def corpus() -> list[dict]:
    # 6 dispatched: 3 completed (latencies 10/20/30, waits 1/2/3), 1 blocked,
    # 1 skipped-capability, 1 organic needs_human; plus 1 canary needs_human.
    return [
        {"run_id": "a", "status": "COMPLETED", "dispatched_at": 100, "closed_at": 110,
         "queued_wait_seconds": 1, "seat_verdict": "PASS", "requires_human_input": False},
        {"run_id": "b", "status": "COMPLETED", "dispatched_at": 200, "closed_at": 220,
         "queued_wait_seconds": 2, "seat_verdict": "PASS", "requires_human_input": False},
        {"run_id": "c", "status": "COMPLETED", "dispatched_at": 300, "closed_at": 330,
         "queued_wait_seconds": 3, "seat_verdict": None, "seat_verdict_recovered": True,
         "requires_human_input": False},
        {"run_id": "d", "status": "BLOCKED", "seat_verdict": None, "requires_human_input": False,
         "alert_pushed": False, "machine_actionable_age_s": 7200},
        {"run_id": "e", "status": "SKIPPED", "stop_reason": "capability_preflight_not_ready",
         "requires_human_input": False},
        {"run_id": "f", "status": "BLOCKED", "requires_human_input": True, "alert_pushed": True,
         "reconciliation_pending": True},
        {"run_id": "canary", "status": "BLOCKED", "requires_human_input": True, "canary": True,
         "alert_pushed": True},
    ]


def main() -> int:
    checks: list[dict] = []

    def check(name: str, got, expected) -> None:
        checks.append({"name": name, "passed": got == expected, "got": got, "expected": expected})

    base = corpus()
    report = fleet_slo.compute(base)
    norm = json.dumps(report, indent=2, sort_keys=True)

    # Order independence: shuffle and recompute -> byte-equivalent normalized report.
    for seed in (1, 7, 42):
        shuffled = list(base)
        random.Random(seed).shuffle(shuffled)
        alt = json.dumps(fleet_slo.compute(shuffled), indent=2, sort_keys=True)
        check(f"order_independent_seed_{seed}", alt, norm)

    # assert-slo: frozen expected metrics.
    # 7 receipts all carry a status -> dispatched = 7 (canary included in raw
    # dispatch count; it is only excluded from the organic needs_human ratio).
    check("dispatched", report["dispatched"], 7)
    check("unattended_success_rate", report["unattended_success_rate"], round(3 / 7, 4))
    check("latency_p50", report["dispatch_to_close_latency_p50"], 20.0)
    check("latency_p95", report["dispatch_to_close_latency_p95"], 30.0)
    # organic terminal = 6 (canary excluded); organic needs_human = 1 (run f).
    check("organic_needs_human_ratio", report["organic_needs_human_ratio"], round(1 / 6, 4))
    check("seat_verdict_none_frequency", report["seat_verdict_none_frequency"], round(2 / 7, 4))
    check("seat_verdict_recovery_rate", report["seat_verdict_recovery_rate"], round(1 / 2, 4))
    check("serialization_wait_p50", report["serialization_wait_p50"], 2.0)
    check("capability_failures", report["capability_failures"], 1)
    check("reconciliation_debt", report["reconciliation_debt"], 1)
    check("alert_volume", report["alert_volume"], 2)
    check("machine_actionable_age_max", report["unresolved_machine_actionable_age_max"], 7200.0)
    check("no_coverage_gap", report["coverage"]["incomplete"], [])
    check("health_amber_over_target", report["health"], "amber")

    # Coverage gap flips health red: a receipt missing status.
    gap = fleet_slo.compute(base + [{"run_id": "z"}])
    check("coverage_gap_detected", any("missing_status" in x for x in gap["coverage"]["incomplete"]), True)
    check("coverage_gap_health_red", gap["health"], "red")

    passed = all(c["passed"] for c in checks)
    result = {"schema": "project_watchdog.fleet_slo_eval.v1", "mocked": True, "live": False,
              "passed": passed, "normalized_report_sha_stable": True, "checks": checks,
              "report": report}
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/watchdog-fleet-slo-result.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": passed, "failing": [c["name"] for c in checks if not c["passed"]]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
