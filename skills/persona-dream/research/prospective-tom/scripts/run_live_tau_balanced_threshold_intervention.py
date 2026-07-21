#!/usr/bin/env python3
"""Run deterministic action-threshold ablations over balanced live Tau PCTOM-R rows."""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import statistics
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_LIVE_TAU_PCTOM_BALANCED_THRESHOLD_INTERVENTION"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_BALANCED_THRESHOLD_INTERVENTION"
AGGREGATE_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_AGGREGATE"
DIAGNOSTIC_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_DIAGNOSTIC"
ROW_SCHEMA = "persona_dream.research.prospective_tom.live_tau_balanced_planning_aggregate_rows.v1"
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


def _counter(values: list[Any]) -> dict[str, int]:
    return dict(collections.Counter(str(value) for value in values))


def _direction(delta: float) -> str:
    if delta < -1e-9:
        return "BENEFIT"
    if delta > 1e-9:
        return "HARM"
    return "TIE"


def _oracle_transition(row: dict[str, Any], action: str) -> str:
    baseline_action = row["baseline_action"]
    oracle_action = row["oracle_action"]
    if action == oracle_action and baseline_action != oracle_action:
        return "GAIN"
    if action != oracle_action and baseline_action == oracle_action:
        return "LOSS"
    return "UNCHANGED"


def _transition(row: dict[str, Any]) -> str:
    return f"{row['baseline_action']} -> {row['cd_action']}"


def _validate_inputs(
    *,
    aggregate_receipt: dict[str, Any],
    diagnostic_receipt: dict[str, Any],
    rows_doc: dict[str, Any],
    rows_path: Path,
    errors: list[str],
) -> list[dict[str, Any]]:
    if aggregate_receipt.get("status") != AGGREGATE_PASS_STATUS:
        errors.append(f"aggregate_status_not_pass:{aggregate_receipt.get('status')}")
    if diagnostic_receipt.get("status") != DIAGNOSTIC_PASS_STATUS:
        errors.append(f"diagnostic_status_not_pass:{diagnostic_receipt.get('status')}")
    if diagnostic_receipt.get("diagnostic_conclusion") != "ACTION_SWITCH_GAIN_LOSS_SYMMETRY":
        errors.append(f"diagnostic_conclusion_unexpected:{diagnostic_receipt.get('diagnostic_conclusion')}")
    for receipt_label, receipt in (("aggregate", aggregate_receipt), ("diagnostic", diagnostic_receipt)):
        if receipt.get("mocked") is not False:
            errors.append(f"{receipt_label}_mocked_not_false:{receipt.get('mocked')}")
        if receipt.get("live") is not True:
            errors.append(f"{receipt_label}_live_not_true:{receipt.get('live')}")
        if receipt.get("fixture_backed") is not False:
            errors.append(f"{receipt_label}_fixture_backed_not_false:{receipt.get('fixture_backed')}")
        if receipt.get("human_content_judgment_required") is not False:
            errors.append(f"{receipt_label}_human_content_judgment_not_false:{receipt.get('human_content_judgment_required')}")
        if receipt.get("llm_judge_used") is not False:
            errors.append(f"{receipt_label}_llm_judge_not_false:{receipt.get('llm_judge_used')}")
        if receipt.get("planning_benefit_with_confidence") is not False:
            errors.append(f"{receipt_label}_planning_benefit_unexpected:{receipt.get('planning_benefit_with_confidence')}")
        for key in ZERO_WRITE_KEYS:
            if receipt.get(key) != 0:
                errors.append(f"{receipt_label}_{key}_not_zero:{receipt.get(key)}")

    if rows_doc.get("schema") != ROW_SCHEMA:
        errors.append(f"rows_schema_mismatch:{rows_doc.get('schema')}:{ROW_SCHEMA}")
    if aggregate_receipt.get("rows_sha256") != _file_sha256(rows_path):
        errors.append(f"aggregate_rows_sha_mismatch:{aggregate_receipt.get('rows_sha256')}:{_file_sha256(rows_path)}")
    if diagnostic_receipt.get("rows_sha256") != _file_sha256(rows_path):
        errors.append(f"diagnostic_rows_sha_mismatch:{diagnostic_receipt.get('rows_sha256')}:{_file_sha256(rows_path)}")

    rows = rows_doc.get("rows")
    if not isinstance(rows, list):
        errors.append("rows_not_list")
        return []
    valid_rows: list[dict[str, Any]] = []
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
    }
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"row_{idx}_not_object")
            continue
        missing = sorted(required.difference(row))
        if missing:
            errors.append(f"row_{idx}_missing:{missing}")
            continue
        for key in ("baseline_regret", "cd_regret", "cd_minus_baseline"):
            if not isinstance(row.get(key), (int, float)) or isinstance(row.get(key), bool):
                errors.append(f"row_{idx}_{key}_not_number:{row.get(key)}")
        expected_delta = float(row["cd_regret"]) - float(row["baseline_regret"])
        if abs(expected_delta - float(row["cd_minus_baseline"])) > 1e-9:
            errors.append(f"row_{idx}_delta_mismatch:{row['cd_minus_baseline']}:{expected_delta}")
        if row["direction"] != _direction(expected_delta):
            errors.append(f"row_{idx}_direction_mismatch:{row['direction']}:{_direction(expected_delta)}")
        if row["oracle_match_transition"] != _oracle_transition(row, str(row["cd_action"])):
            errors.append(
                f"row_{idx}_oracle_transition_mismatch:{row['oracle_match_transition']}:{_oracle_transition(row, str(row['cd_action']))}"
            )
        if row["action_switched"] != (row["baseline_action"] != row["cd_action"]):
            errors.append(f"row_{idx}_action_switched_mismatch:{row['action_switched']}")
        valid_rows.append(row)
    return valid_rows


def _candidate_action(row: dict[str, Any], policy_id: str) -> str:
    transition = _transition(row)
    if policy_id == "keep_observed_cd_policy":
        return str(row["cd_action"])
    if policy_id == "block_all_cd_action_switches" and row["action_switched"]:
        return str(row["baseline_action"])
    if policy_id == "block_wait_to_offer_cooperation" and transition == "WAIT -> OFFER_COOPERATION":
        return str(row["baseline_action"])
    if policy_id == "block_set_boundary_to_ask_clarifying" and transition == "SET_BOUNDARY -> ASK_CLARIFYING_QUESTION":
        return str(row["baseline_action"])
    if policy_id == "block_wait_to_ask_clarifying" and transition == "WAIT -> ASK_CLARIFYING_QUESTION":
        return str(row["baseline_action"])
    return str(row["cd_action"])


def _evaluate_policy(rows: list[dict[str, Any]], policy_id: str) -> dict[str, Any]:
    adjusted_rows: list[dict[str, Any]] = []
    deltas: list[float] = []
    for row in rows:
        selected_action = _candidate_action(row, policy_id)
        intervention_changed_action = selected_action != row["cd_action"]
        adjusted_delta = 0.0 if selected_action == row["baseline_action"] else float(row["cd_minus_baseline"])
        deltas.append(adjusted_delta)
        adjusted_rows.append(
            {
                "episode_id": row["episode_id"],
                "scenario_family": row["scenario_family"],
                "baseline_condition": row["baseline_condition"],
                "baseline_action": row["baseline_action"],
                "observed_cd_action": row["cd_action"],
                "intervened_cd_action": selected_action,
                "oracle_action": row["oracle_action"],
                "original_cd_minus_baseline": row["cd_minus_baseline"],
                "intervened_cd_minus_baseline": adjusted_delta,
                "original_direction": row["direction"],
                "intervened_direction": _direction(adjusted_delta),
                "original_oracle_match_transition": row["oracle_match_transition"],
                "intervened_oracle_match_transition": _oracle_transition(row, selected_action),
                "original_action_switch": row["action_switched"],
                "intervened_action_switch": selected_action != row["baseline_action"],
                "intervention_changed_action": intervention_changed_action,
                "original_transition": _transition(row),
            }
        )

    changed = [row for row in adjusted_rows if row["intervention_changed_action"]]
    avoided_harms = [
        row
        for row in changed
        if row["original_direction"] == "HARM" and row["intervened_direction"] == "TIE"
    ]
    lost_benefits = [
        row
        for row in changed
        if row["original_direction"] == "BENEFIT" and row["intervened_direction"] == "TIE"
    ]
    return {
        "policy_id": policy_id,
        "rows": len(adjusted_rows),
        "mean_cd_minus_baseline": _mean(deltas),
        "direction_counts": _counter([row["intervened_direction"] for row in adjusted_rows]),
        "oracle_match_transitions": _counter([row["intervened_oracle_match_transition"] for row in adjusted_rows]),
        "changed_action_count": len(changed),
        "avoided_harm_count": len(avoided_harms),
        "lost_benefit_count": len(lost_benefits),
        "net_avoided_harm_minus_lost_benefit": len(avoided_harms) - len(lost_benefits),
        "changed_transition_counts": _counter([row["original_transition"] for row in changed]),
        "changed_family_counts": _counter([row["scenario_family"] for row in changed]),
        "mean_improvement_vs_observed": None,
        "rows_detail": adjusted_rows,
    }


def _summarize_interventions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    observed = _evaluate_policy(rows, "keep_observed_cd_policy")
    policies = [
        observed,
        _evaluate_policy(rows, "block_wait_to_offer_cooperation"),
        _evaluate_policy(rows, "block_set_boundary_to_ask_clarifying"),
        _evaluate_policy(rows, "block_wait_to_ask_clarifying"),
        _evaluate_policy(rows, "block_all_cd_action_switches"),
    ]
    observed_mean = observed["mean_cd_minus_baseline"]
    for policy in policies:
        policy["mean_improvement_vs_observed"] = (
            None
            if observed_mean is None or policy["mean_cd_minus_baseline"] is None
            else observed_mean - policy["mean_cd_minus_baseline"]
        )

    by_id = {policy["policy_id"]: policy for policy in policies}
    conclusion = "THRESHOLD_INTERVENTION_INCONCLUSIVE"
    wait_offer = by_id["block_wait_to_offer_cooperation"]
    boundary_ask = by_id["block_set_boundary_to_ask_clarifying"]
    if (
        (wait_offer["mean_improvement_vs_observed"] or 0.0) > 0
        and wait_offer["net_avoided_harm_minus_lost_benefit"] > 0
        and (boundary_ask["mean_improvement_vs_observed"] or 0.0) < 0
    ):
        conclusion = "RAISE_COOPERATION_THRESHOLD_KEEP_CLARIFYING_THRESHOLD_UNPROVEN"

    return {
        "observed_policy_mean_cd_minus_baseline": observed_mean,
        "policy_summaries": [
            {key: value for key, value in policy.items() if key != "rows_detail"}
            for policy in policies
        ],
        "policy_rows": {policy["policy_id"]: policy["rows_detail"] for policy in policies},
        "threshold_intervention_conclusion": conclusion,
    }


def run_intervention(
    *,
    aggregate_receipt_path: Path,
    diagnostic_receipt_path: Path,
    output_root: Path,
    receipt_out: Path,
) -> dict[str, Any]:
    started = time.monotonic()
    aggregate_receipt_path = aggregate_receipt_path.resolve()
    diagnostic_receipt_path = diagnostic_receipt_path.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    errors: list[str] = []

    aggregate_receipt = _load_json(aggregate_receipt_path, errors, "aggregate_receipt")
    diagnostic_receipt = _load_json(diagnostic_receipt_path, errors, "diagnostic_receipt")
    aggregate_receipt = aggregate_receipt if isinstance(aggregate_receipt, dict) else {}
    diagnostic_receipt = diagnostic_receipt if isinstance(diagnostic_receipt, dict) else {}
    rows_path_value = aggregate_receipt.get("rows_path")
    rows_path = Path(rows_path_value).resolve() if isinstance(rows_path_value, str) else aggregate_receipt_path.parent / "balanced_planning_rows.v17_22.aggregate.json"
    rows_doc = _load_json(rows_path, errors, "aggregate_rows")
    rows_doc = rows_doc if isinstance(rows_doc, dict) else {}
    rows = _validate_inputs(
        aggregate_receipt=aggregate_receipt,
        diagnostic_receipt=diagnostic_receipt,
        rows_doc=rows_doc,
        rows_path=rows_path,
        errors=errors,
    )
    intervention_summary = _summarize_interventions(rows)

    artifacts_root = output_root / "artifacts"
    summary_path = artifacts_root / "balanced_threshold_intervention_summary.json"
    rows_path_out = artifacts_root / "balanced_threshold_intervention_rows.json"
    _write_json(
        summary_path,
        {
            "schema": "persona_dream.research.prospective_tom.balanced_threshold_intervention_summary.v1",
            **intervention_summary,
        },
    )
    _write_json(
        rows_path_out,
        {
            "schema": "persona_dream.research.prospective_tom.balanced_threshold_intervention_rows.v1",
            "policy_rows": intervention_summary["policy_rows"],
        },
    )

    checks = {
        "aggregate_receipt_passed": aggregate_receipt.get("status") == AGGREGATE_PASS_STATUS,
        "diagnostic_receipt_passed": diagnostic_receipt.get("status") == DIAGNOSTIC_PASS_STATUS,
        "rows_hash_recomputed": rows_path.exists()
        and aggregate_receipt.get("rows_sha256") == _file_sha256(rows_path)
        and diagnostic_receipt.get("rows_sha256") == _file_sha256(rows_path),
        "zero_unsupported_writes": all(aggregate_receipt.get(key) == 0 for key in ZERO_WRITE_KEYS)
        and all(diagnostic_receipt.get(key) == 0 for key in ZERO_WRITE_KEYS),
        "live_not_mocked": aggregate_receipt.get("live") is True
        and diagnostic_receipt.get("live") is True
        and aggregate_receipt.get("mocked") is False
        and diagnostic_receipt.get("mocked") is False,
        "no_llm_or_human_judge": aggregate_receipt.get("llm_judge_used") is False
        and diagnostic_receipt.get("llm_judge_used") is False
        and aggregate_receipt.get("human_content_judgment_required") is False
        and diagnostic_receipt.get("human_content_judgment_required") is False,
        "cooperation_threshold_ablation_improves_observed_mean": any(
            policy["policy_id"] == "block_wait_to_offer_cooperation"
            and (policy["mean_improvement_vs_observed"] or 0.0) > 0
            for policy in intervention_summary["policy_summaries"]
        ),
        "set_boundary_clarify_ablation_does_not_improve_observed_mean": any(
            policy["policy_id"] == "block_set_boundary_to_ask_clarifying"
            and (policy["mean_improvement_vs_observed"] or 0.0) < 0
            for policy in intervention_summary["policy_summaries"]
        ),
    }
    for key, value in checks.items():
        if value is not True:
            errors.append(f"check_failed:{key}:{value}")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_balanced_threshold_intervention_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "aggregate_receipt": str(aggregate_receipt_path),
        "aggregate_receipt_sha256": _file_sha256(aggregate_receipt_path) if aggregate_receipt_path.exists() else None,
        "diagnostic_receipt": str(diagnostic_receipt_path),
        "diagnostic_receipt_sha256": _file_sha256(diagnostic_receipt_path) if diagnostic_receipt_path.exists() else None,
        "rows_path": str(rows_path),
        "rows_sha256": _file_sha256(rows_path) if rows_path.exists() else None,
        "summary_path": str(summary_path),
        "summary_sha256": _file_sha256(summary_path) if summary_path.exists() else None,
        "policy_rows_path": str(rows_path_out),
        "policy_rows_sha256": _file_sha256(rows_path_out) if rows_path_out.exists() else None,
        "mocked": False,
        "live": aggregate_receipt.get("live") is True and diagnostic_receipt.get("live") is True,
        "fixture_backed": False,
        "live_tau_originated_artifacts_consumed": aggregate_receipt.get("live_tau_originated_artifacts_consumed") is True,
        "live_tau_reexecuted_by_intervention": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": 0,
        "tau_live_call_performed": 0,
        "tau_call_attempts_in_consumed_aggregate": aggregate_receipt.get("tau_call_attempts_total"),
        "tau_live_call_performed_in_consumed_aggregate": aggregate_receipt.get("tau_live_call_performed_total"),
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "checks": checks,
        "counts": {
            "rows": len(rows),
            "policy_count": len(intervention_summary["policy_summaries"]),
        },
        "threshold_intervention_conclusion": intervention_summary["threshold_intervention_conclusion"],
        "metrics": {
            "observed_policy_mean_cd_minus_baseline": intervention_summary["observed_policy_mean_cd_minus_baseline"],
            "policy_summaries": intervention_summary["policy_summaries"],
        },
        "planning_benefit_with_confidence": False,
        "errors": errors,
        "claims": {
            "proves": [
                "the balanced v17-22 action-switch signal is more harmed by WAIT -> OFFER_COOPERATION switches than by clarifying-question switches",
                "blocking WAIT -> OFFER_COOPERATION would improve the observed balanced mean in this accepted aggregate",
                "blocking SET_BOUNDARY -> ASK_CLARIFYING_QUESTION would worsen the observed balanced mean in this accepted aggregate",
                "the threshold intervention consumed live-originated aggregate evidence without new Tau, Memory, provider, canonical, identity, or source-memory writes",
            ]
            if status == PASS_STATUS
            else [
                "the threshold intervention failed closed before accepting a threshold-policy interpretation",
            ],
            "does_not_prove": [
                "an implementable no-oracle runtime policy",
                "confidence-bounded CD planning benefit",
                "that future Tau runs will reproduce the same threshold pattern",
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aggregate-receipt", type=Path, required=True)
    parser.add_argument("--diagnostic-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "live_tau_balanced_threshold_intervention_receipt.v1.json")
    receipt = run_intervention(
        aggregate_receipt_path=args.aggregate_receipt,
        diagnostic_receipt_path=args.diagnostic_receipt,
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
