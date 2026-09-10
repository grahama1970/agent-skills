"""Fleet SLO report derived exclusively from durable receipts (#1645).

No unattended-success measurement existed. This computes the fleet health SLOs
from receipt records alone and emits a NORMALIZED report: every derived list is
sorted and every float rounded, and the report is serialized with sorted keys,
so a shuffled-order rerun over the same receipts yields byte-equivalent output.

Receipt-coverage incompleteness is itself a red signal: a receipt missing a
field a metric needs is counted in ``coverage.incomplete`` and flips
``health`` to ``red`` rather than being silently dropped.

Input: a list of receipt dicts. Recognized fields (all optional; absence is
tracked, never guessed):
  status                     COMPLETED | BLOCKED | SKIPPED | ...
  requires_human_input       bool
  canary                     bool (organic needs_human excludes canaries)
  dispatched_at, closed_at   epoch seconds (dispatch->native-close latency)
  queued_wait_seconds        serialization wait for this dispatch
  seat_verdict               "PASS"|"FAIL"|"NEEDS_ATTENTION"|None
  seat_verdict_recovered     bool (a None verdict later recovered from bytes)
  stop_reason                e.g. capability_preflight_not_ready
  alert_pushed               bool
  reconciliation_pending     bool (retained op not settled/released)
  machine_actionable_age_s   age of an unresolved requires_human_input:false item
"""
from __future__ import annotations

from typing import Any

SCHEMA = "project_watchdog.fleet_slo.v1"
_LATENCY_FIELDS = ("dispatched_at", "closed_at")


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    if len(s) == 1:
        return round(s[0], 3)
    # Nearest-rank on a 0..1 position; deterministic and order-independent.
    idx = min(len(s) - 1, max(0, round(p * (len(s) - 1))))
    return round(s[idx], 3)


def _ratio(num: int, den: int) -> float | None:
    return None if den == 0 else round(num / den, 4)


def compute(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    terminal = {"COMPLETED", "BLOCKED", "SKIPPED"}
    dispatched = closes = organic_terminal = organic_needs_human = 0
    verdict_none = verdict_recovered = capability_failures = 0
    alerts = reconciliation_debt = 0
    latencies: list[float] = []
    waits: list[float] = []
    machine_ages: list[float] = []
    incomplete: list[str] = []

    for i, r in enumerate(receipts):
        status = str(r.get("status") or "")
        rid = str(r.get("run_id") or r.get("id") or f"idx-{i}")
        is_canary = bool(r.get("canary"))
        if status:
            dispatched += 1
        if r.get("alert_pushed"):
            alerts += 1
        if r.get("reconciliation_pending"):
            reconciliation_debt += 1
        if r.get("stop_reason") == "capability_preflight_not_ready":
            capability_failures += 1
        if "seat_verdict" in r:
            if r.get("seat_verdict") is None:
                verdict_none += 1
                if r.get("seat_verdict_recovered"):
                    verdict_recovered += 1
        if status == "COMPLETED":
            closes += 1
            if all(f in r for f in _LATENCY_FIELDS):
                latencies.append(float(r["closed_at"]) - float(r["dispatched_at"]))
            else:
                incomplete.append(f"{rid}:missing_latency_fields")
        if "queued_wait_seconds" in r:
            waits.append(float(r["queued_wait_seconds"]))
        if status in terminal and not is_canary:
            organic_terminal += 1
            if r.get("requires_human_input") is True:
                organic_needs_human += 1
        if r.get("machine_actionable_age_s") is not None and not r.get("resolved"):
            machine_ages.append(float(r["machine_actionable_age_s"]))
        if not status:
            incomplete.append(f"{rid}:missing_status")

    report: dict[str, Any] = {
        "schema": SCHEMA,
        "receipts_seen": len(receipts),
        "dispatched": dispatched,
        "unattended_success_rate": _ratio(closes, dispatched),
        "dispatch_to_close_latency_p50": _pct(latencies, 0.50),
        "dispatch_to_close_latency_p95": _pct(latencies, 0.95),
        "organic_needs_human_ratio": _ratio(organic_needs_human, organic_terminal),
        "seat_verdict_none_frequency": _ratio(verdict_none, dispatched),
        "seat_verdict_recovery_rate": _ratio(verdict_recovered, verdict_none),
        "serialization_wait_p50": _pct(waits, 0.50),
        "serialization_wait_p95": _pct(waits, 0.95),
        "capability_failures": capability_failures,
        "reconciliation_debt": reconciliation_debt,
        "alert_volume": alerts,
        "unresolved_machine_actionable_age_max": (round(max(machine_ages), 3) if machine_ages else None),
        "coverage": {"receipts": len(receipts), "incomplete": sorted(incomplete)},
    }
    # Health: any coverage gap is red; else amber if needs_human target is
    # exceeded, else green.
    ratio = report["organic_needs_human_ratio"]
    if report["coverage"]["incomplete"]:
        report["health"] = "red"
    elif ratio is not None and ratio > 0.01:
        report["health"] = "amber"
    else:
        report["health"] = "green"
    return report
