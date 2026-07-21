#!/usr/bin/env python3
"""Diagnose mixed planning signal in balanced live Tau PCTOM-R aggregate rows."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_DIAGNOSTIC"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_BALANCED_PLANNING_DIAGNOSTIC"
AGGREGATE_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_AGGREGATE"
ROW_SCHEMA = "persona_dream.research.prospective_tom.live_tau_balanced_planning_aggregate_rows.v1"
FAMILIES = (
    "coordination_conflict",
    "information_asymmetry_false_belief",
    "preference_desire_uncertainty",
    "trust_commitment_relationship",
)
ZERO_WRITE_KEYS = (
    "memory_write_attempts",
    "provider_call_attempts",
    "canonical_memory_write_attempts",
    "identity_write_attempts",
    "source_memory_write_attempts",
)


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path, errors: list[str], label: str) -> Any:
    if not path.exists():
        errors.append(f"missing_{label}:{path}")
        return None
    if path.is_symlink():
        errors.append(f"symlink_{label}:{path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"malformed_{label}:{path}:{exc}")
        return None


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _counter(items: list[Any]) -> dict[str, int]:
    return dict(collections.Counter(str(item) for item in items))


def _validate_aggregate(receipt: dict[str, Any], rows_doc: dict[str, Any], rows_path: Path, errors: list[str]) -> list[dict[str, Any]]:
    if receipt.get("status") != AGGREGATE_PASS_STATUS:
        errors.append(f"aggregate_status_not_pass:{receipt.get('status')}")
    if receipt.get("mocked") is not False:
        errors.append(f"aggregate_mocked_not_false:{receipt.get('mocked')}")
    if receipt.get("live") is not True:
        errors.append(f"aggregate_live_not_true:{receipt.get('live')}")
    if receipt.get("fixture_backed") is not False:
        errors.append(f"aggregate_fixture_backed_not_false:{receipt.get('fixture_backed')}")
    if receipt.get("human_content_judgment_required") is not False:
        errors.append(f"aggregate_human_content_judgment_not_false:{receipt.get('human_content_judgment_required')}")
    if receipt.get("llm_judge_used") is not False:
        errors.append(f"aggregate_llm_judge_not_false:{receipt.get('llm_judge_used')}")
    if receipt.get("planning_benefit_with_confidence") is not False:
        errors.append(f"aggregate_planning_benefit_unexpected:{receipt.get('planning_benefit_with_confidence')}")
    for key in ZERO_WRITE_KEYS:
        if receipt.get(key) != 0:
            errors.append(f"aggregate_{key}_not_zero:{receipt.get(key)}")

    declared_rows = receipt.get("rows_path")
    if not isinstance(declared_rows, str) or Path(declared_rows).resolve() != rows_path.resolve():
        errors.append(f"aggregate_rows_path_mismatch:{declared_rows}:{rows_path}")
    declared_rows_sha = receipt.get("rows_sha256")
    if rows_path.exists() and declared_rows_sha != _file_sha256(rows_path):
        errors.append(f"aggregate_rows_sha256_mismatch:{declared_rows_sha}:{_file_sha256(rows_path)}")

    if rows_doc.get("schema") != ROW_SCHEMA:
        errors.append(f"rows_schema_mismatch:{rows_doc.get('schema')}:{ROW_SCHEMA}")
    rows = rows_doc.get("rows")
    if not isinstance(rows, list):
        errors.append("rows_not_list")
        return []
    if len(rows) != receipt.get("balanced_episode_count"):
        errors.append(f"row_count_mismatch:{len(rows)}:{receipt.get('balanced_episode_count')}")

    required = {
        "episode_id",
        "scenario_family",
        "baseline_condition",
        "baseline_action",
        "cd_action",
        "oracle_action",
        "action_switched",
        "baseline_regret",
        "cd_regret",
        "cd_minus_baseline",
        "direction",
        "oracle_match_transition",
        "source_receipt_path",
        "variant_min",
        "variant_max",
    }
    valid_rows: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row_{idx}_not_object")
            continue
        missing = sorted(required.difference(row))
        if missing:
            errors.append(f"row_{idx}_missing:{missing}")
            continue
        if row["scenario_family"] not in FAMILIES:
            errors.append(f"row_{idx}_unknown_family:{row['scenario_family']}")
        for key in ("baseline_regret", "cd_regret", "cd_minus_baseline"):
            if not isinstance(row.get(key), (int, float)) or isinstance(row.get(key), bool):
                errors.append(f"row_{idx}_{key}_not_number:{row.get(key)}")
        expected_delta = row["cd_regret"] - row["baseline_regret"]
        if abs(expected_delta - row["cd_minus_baseline"]) > 1e-9:
            errors.append(f"row_{idx}_delta_mismatch:{row['cd_minus_baseline']}:{expected_delta}")
        expected_direction = "BENEFIT" if expected_delta < 0 else "HARM" if expected_delta > 0 else "TIE"
        if row["direction"] != expected_direction:
            errors.append(f"row_{idx}_direction_mismatch:{row['direction']}:{expected_direction}")
        expected_transition = (
            "GAIN"
            if row["cd_action"] == row["oracle_action"] and row["baseline_action"] != row["oracle_action"]
            else "LOSS"
            if row["cd_action"] != row["oracle_action"] and row["baseline_action"] == row["oracle_action"]
            else "UNCHANGED"
        )
        if row["oracle_match_transition"] != expected_transition:
            errors.append(f"row_{idx}_oracle_transition_mismatch:{row['oracle_match_transition']}:{expected_transition}")
        if row["action_switched"] != (row["baseline_action"] != row["cd_action"]):
            errors.append(f"row_{idx}_action_switched_mismatch:{row['action_switched']}")
        valid_rows.append(row)
    return valid_rows


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    nonzero_rows = [row for row in rows if row["cd_minus_baseline"] != 0]
    switch_rows = [row for row in rows if row["action_switched"]]
    family_summary: dict[str, Any] = {}
    for family in FAMILIES:
        family_rows = [row for row in rows if row["scenario_family"] == family]
        family_switches = [row for row in family_rows if row["action_switched"]]
        family_summary[family] = {
            "rows": len(family_rows),
            "mean_cd_minus_baseline": _mean([float(row["cd_minus_baseline"]) for row in family_rows]),
            "direction_counts": _counter([row["direction"] for row in family_rows]),
            "oracle_match_transitions": _counter([row["oracle_match_transition"] for row in family_rows]),
            "action_switch_count": len(family_switches),
            "action_switch_transitions": _counter(
                [f"{row['baseline_action']} -> {row['cd_action']}" for row in family_switches]
            ),
        }

    transition_summary: dict[str, Any] = {}
    for transition in sorted({f"{row['baseline_action']} -> {row['cd_action']}" for row in switch_rows}):
        transition_rows = [
            row
            for row in switch_rows
            if f"{row['baseline_action']} -> {row['cd_action']}" == transition
        ]
        transition_summary[transition] = {
            "rows": len(transition_rows),
            "mean_cd_minus_baseline": _mean([float(row["cd_minus_baseline"]) for row in transition_rows]),
            "direction_counts": _counter([row["direction"] for row in transition_rows]),
            "oracle_match_transitions": _counter([row["oracle_match_transition"] for row in transition_rows]),
            "families": _counter([row["scenario_family"] for row in transition_rows]),
        }

    return {
        "rows": len(rows),
        "mean_cd_minus_baseline": _mean([float(row["cd_minus_baseline"]) for row in rows]),
        "direction_counts": _counter([row["direction"] for row in rows]),
        "oracle_match_transitions": _counter([row["oracle_match_transition"] for row in rows]),
        "action_switch_count": len(switch_rows),
        "nonzero_delta_count": len(nonzero_rows),
        "all_nonzero_rows_are_action_switches": all(row["action_switched"] for row in nonzero_rows),
        "all_action_switches_are_nonzero": all(row["cd_minus_baseline"] != 0 for row in switch_rows),
        "action_switch_direction_counts": _counter([row["direction"] for row in switch_rows]),
        "action_switch_oracle_transitions": _counter([row["oracle_match_transition"] for row in switch_rows]),
        "family_summary": family_summary,
        "action_switch_transition_summary": transition_summary,
        "nonzero_rows": nonzero_rows,
        "row_pattern_sha256": _stable_json_sha256(
            [
                {
                    "episode_id": row["episode_id"],
                    "scenario_family": row["scenario_family"],
                    "baseline_action": row["baseline_action"],
                    "cd_action": row["cd_action"],
                    "oracle_action": row["oracle_action"],
                    "cd_minus_baseline": row["cd_minus_baseline"],
                    "direction": row["direction"],
                    "oracle_match_transition": row["oracle_match_transition"],
                }
                for row in rows
            ]
        ),
    }


def _diagnostic_label(summary: dict[str, Any]) -> str:
    if summary["direction_counts"].get("BENEFIT") == summary["direction_counts"].get("HARM"):
        if summary["oracle_match_transitions"].get("GAIN") == summary["oracle_match_transitions"].get("LOSS"):
            return "ACTION_SWITCH_GAIN_LOSS_SYMMETRY"
    return "BALANCED_SIGNAL_REQUIRES_MORE_EVIDENCE"


def run_diagnostic(*, aggregate_receipt: Path, output_root: Path, receipt_out: Path) -> dict[str, Any]:
    started = time.monotonic()
    aggregate_receipt = aggregate_receipt.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    errors: list[str] = []

    receipt = _load_json(aggregate_receipt, errors, "aggregate_receipt")
    if not isinstance(receipt, dict):
        receipt = {}
    rows_path_value = receipt.get("rows_path")
    rows_path = Path(rows_path_value).resolve() if isinstance(rows_path_value, str) else aggregate_receipt.parent / "balanced_planning_rows.v17_22.aggregate.json"
    rows_doc = _load_json(rows_path, errors, "aggregate_rows")
    if not isinstance(rows_doc, dict):
        rows_doc = {}

    rows = _validate_aggregate(receipt, rows_doc, rows_path, errors)
    summary = _summarize(rows)
    diagnostic_label = _diagnostic_label(summary)
    summary_path = output_root / "balanced_planning_gain_loss_diagnostic_summary.json"
    _write_json(summary_path, {"schema": "persona_dream.research.prospective_tom.balanced_planning_gain_loss_summary.v1", **summary})

    expected_checks = {
        "aggregate_receipt_passed": receipt.get("status") == AGGREGATE_PASS_STATUS,
        "aggregate_rows_hash_recomputed": rows_path.exists() and receipt.get("rows_sha256") == _file_sha256(rows_path),
        "zero_unsupported_writes": all(receipt.get(key) == 0 for key in ZERO_WRITE_KEYS),
        "live_not_mocked": receipt.get("live") is True and receipt.get("mocked") is False and receipt.get("fixture_backed") is False,
        "no_llm_or_human_judge": receipt.get("llm_judge_used") is False and receipt.get("human_content_judgment_required") is False,
        "all_nonzero_rows_are_action_switches": summary["all_nonzero_rows_are_action_switches"],
        "all_action_switches_are_nonzero": summary["all_action_switches_are_nonzero"],
        "gain_loss_counts_balanced": summary["oracle_match_transitions"].get("GAIN") == summary["oracle_match_transitions"].get("LOSS"),
        "benefit_harm_counts_balanced": summary["direction_counts"].get("BENEFIT") == summary["direction_counts"].get("HARM"),
        "planning_benefit_with_confidence_false": receipt.get("planning_benefit_with_confidence") is False,
    }
    for key, value in expected_checks.items():
        if value is not True:
            errors.append(f"check_failed:{key}:{value}")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    diagnostic = {
        "schema": "persona_dream.research.prospective_tom.live_tau_balanced_planning_diagnostic_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "aggregate_receipt": str(aggregate_receipt),
        "aggregate_receipt_sha256": _file_sha256(aggregate_receipt) if aggregate_receipt.exists() else None,
        "rows_path": str(rows_path),
        "rows_sha256": _file_sha256(rows_path) if rows_path.exists() else None,
        "summary_path": str(summary_path),
        "summary_sha256": _file_sha256(summary_path) if summary_path.exists() else None,
        "mocked": False,
        "live": receipt.get("live") is True,
        "fixture_backed": False,
        "live_tau_originated_artifacts_consumed": receipt.get("live_tau_originated_artifacts_consumed") is True,
        "live_tau_reexecuted_by_diagnostic": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": 0,
        "tau_live_call_performed": 0,
        "tau_call_attempts_in_consumed_aggregate": receipt.get("tau_call_attempts_total"),
        "tau_live_call_performed_in_consumed_aggregate": receipt.get("tau_live_call_performed_total"),
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "checks": expected_checks,
        "counts": {
            "rows": summary["rows"],
            "action_switch_count": summary["action_switch_count"],
            "nonzero_delta_count": summary["nonzero_delta_count"],
            "direction_counts": summary["direction_counts"],
            "oracle_match_transitions": summary["oracle_match_transitions"],
            "action_switch_direction_counts": summary["action_switch_direction_counts"],
            "action_switch_oracle_transitions": summary["action_switch_oracle_transitions"],
        },
        "metrics": {
            "mean_cd_minus_baseline": summary["mean_cd_minus_baseline"],
            "family_summary": summary["family_summary"],
            "action_switch_transition_summary": summary["action_switch_transition_summary"],
            "row_pattern_sha256": summary["row_pattern_sha256"],
        },
        "diagnostic_conclusion": diagnostic_label,
        "planning_benefit_with_confidence": False,
        "errors": errors,
        "claims": {
            "proves": [
                "the balanced v17-22 aggregate rows hash-recompute against the accepted aggregate receipt",
                "the balanced nonzero planning-regret signal is entirely realized action switching",
                "the accepted balanced aggregate contains equal BENEFIT/HARM and GAIN/LOSS counts",
                "unsupported Memory/provider/canonical/identity/source-memory writes remain absent in the consumed aggregate and diagnostic",
            ]
            if status == PASS_STATUS
            else [
                "the balanced planning diagnostic failed closed before accepting a gain/loss explanation",
            ],
            "does_not_prove": [
                "confidence-bounded CD planning benefit",
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
                "that a larger or differently sampled balanced corpus will remain gain/loss symmetric",
                "that future Tau runs will reproduce the same action switches",
            ],
        },
    }
    diagnostic["receipt_sha256"] = _stable_json_sha256(
        {key: value for key, value in diagnostic.items() if key != "receipt_sha256"}
    )
    _write_json(receipt_out, diagnostic)
    return diagnostic


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aggregate-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "live_tau_balanced_planning_diagnostic_receipt.v1.json")
    receipt = run_diagnostic(
        aggregate_receipt=args.aggregate_receipt,
        output_root=args.output_root,
        receipt_out=receipt_out,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
