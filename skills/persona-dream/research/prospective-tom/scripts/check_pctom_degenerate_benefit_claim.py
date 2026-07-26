#!/usr/bin/env python3
"""Fail closed when a benefit-with-confidence claim rests on zero-variance deltas.

`run_sealed_test_statistical_confidence.py` is pre-execution gate 2 of the sealed
powered-trial protocol. It emits `primary_benefit_with_confidence` from a paired
bootstrap over per-episode deltas. If every episode carries the SAME delta, the
bootstrap is degenerate: every resample returns the identical mean, the interval
collapses to a point, and `upper < 0` becomes true by construction rather than by
measurement. The gate then reports statistical confidence for a constant.

That is the live condition today. `run_condition_comparison.py` assigns beliefs
from a static CONDITION_PROFILES ladder (belief_true: M 0.45, R 0.55, D 0.62,
CD 0.70) that does not depend on the episode, its hidden state, or any dream
content, so all 64 sealed_test episodes score an identical belief Brier per
condition and CD "wins" the preregistered primary hypothesis before any Tau call
is made.

This checker does not repair the corpus. GOAL.md's Next Critical Path explicitly
rules out corpus-tuning to force a CD win, so the correct response is to refuse
the claim, not to reshape the data behind it.

Inputs:  a sealed_test statistical-confidence receipt and its paired-delta artifact.
Outputs: one JSON receipt with per-metric variance and a PASS/BLOCKED verdict.
Failures: a benefit claim over deltas with fewer than MIN_DISTINCT distinct
          values blocks; so does a missing or unreadable input.
"""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

from pctom_r2_phase1_lib import SCHEMA_PREFIX, file_sha256, now_iso, write_json

PASS_STATUS = "PASS_PCTOM_NON_DEGENERATE_BENEFIT_CLAIM"
BLOCKED_STATUS = "BLOCKED_PCTOM_DEGENERATE_BENEFIT_CLAIM"
MIN_DISTINCT = 2
DELTA_KEY = "cd_minus_baseline"
CLAIM_FIELDS = {
    "belief_brier": "primary_benefit_with_confidence",
    "planning_regret": "planning_benefit_with_confidence",
}


def delta_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = [row[DELTA_KEY] for row in rows if isinstance(row.get(DELTA_KEY), (int, float))]
    distinct = sorted(set(values))
    return {
        "n": len(values),
        "distinct": len(distinct),
        "variance": statistics.pvariance(values) if len(values) > 1 else 0.0,
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "degenerate": len(distinct) < MIN_DISTINCT,
    }


def check(receipt_path: Path, deltas_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    deltas = json.loads(deltas_path.read_text(encoding="utf-8"))

    metrics: dict[str, Any] = {}
    for metric, rows in deltas.items():
        if not isinstance(rows, list) or not rows:
            continue
        stats = delta_stats(rows)
        claim_field = CLAIM_FIELDS.get(metric)
        claimed = bool(receipt.get(claim_field)) if claim_field else False
        stats["claim_field"] = claim_field
        stats["benefit_claimed"] = claimed
        if claimed and stats["degenerate"]:
            errors.append(
                f"degenerate_benefit_claim:{metric}:{claim_field}:distinct={stats['distinct']}"
            )
        metrics[metric] = stats

    # A collapsed interval is the same defect seen from the receipt's own side.
    interval = receipt.get("primary_cd_minus_baseline_ci") or {}
    lower, upper = interval.get("lower"), interval.get("upper")
    if isinstance(lower, (int, float)) and isinstance(upper, (int, float)) and lower == upper:
        if receipt.get("primary_benefit_with_confidence"):
            errors.append(f"collapsed_primary_confidence_interval:lower==upper=={lower}")

    return {
        "schema": f"{SCHEMA_PREFIX}.pctom_degenerate_benefit_claim_receipt.v1",
        "created_at": now_iso(),
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "source_receipt": str(receipt_path),
        "source_receipt_sha256": file_sha256(receipt_path),
        "paired_delta_path": str(deltas_path),
        "paired_delta_sha256": file_sha256(deltas_path),
        "min_distinct_required": MIN_DISTINCT,
        "primary_metric": receipt.get("primary_metric"),
        "metrics": metrics,
        "errors": errors,
        "mocked": False,
        "live": False,
        "fixture_backed": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "claims": {
            "proves": [
                "whether each paired-delta series carries any episode-to-episode variance",
                "whether a benefit-with-confidence field is asserted over a constant series",
            ],
            "does_not_prove": [
                "that a non-degenerate series demonstrates counterfactual-dream benefit",
                "the correctness of the underlying scoring or corpus",
                "live Tau execution or powered-trial readiness",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Block benefit claims built on zero-variance deltas.")
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--deltas", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path)
    args = parser.parse_args()

    result = check(args.receipt, args.deltas)
    if args.receipt_out:
        write_json(args.receipt_out, result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["status"] == BLOCKED_STATUS else 0


if __name__ == "__main__":
    raise SystemExit(main())
