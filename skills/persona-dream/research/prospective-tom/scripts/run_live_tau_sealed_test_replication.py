#!/usr/bin/env python3
"""Run bounded live Tau replication of the PCTOM-R sealed-test loop."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import statistics
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
LIVE_CONDITION_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_condition_comparison.py"
ACTION_SELECTION_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_condition_action_selection.py"
CONDITIONS = ("M", "R", "D", "CD")
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION"
DEFAULT_SPLIT = "sealed_test"


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


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _condition_metric_means(case_index: list[dict[str, Any]], metric_name: str) -> dict[str, float]:
    values: dict[str, list[float]] = {condition: [] for condition in CONDITIONS}
    for row in case_index:
        if not isinstance(row, dict) or row.get("condition") not in CONDITIONS:
            continue
        metrics = row.get("scoring_metrics") if isinstance(row.get("scoring_metrics"), dict) else {}
        if metric_name == "belief_brier":
            belief_scores = metrics.get("belief_scores") if isinstance(metrics.get("belief_scores"), list) else []
            numeric = [
                float(score["brier"])
                for score in belief_scores
                if isinstance(score, dict)
                and isinstance(score.get("brier"), (int, float))
                and not isinstance(score.get("brier"), bool)
            ]
            mean_value = _mean(numeric)
        else:
            action = metrics.get("action") if isinstance(metrics.get("action"), dict) else {}
            value = action.get("brier")
            mean_value = float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
        if mean_value is not None:
            values[row["condition"]].append(mean_value)
    return {condition: statistics.fmean(rows) for condition, rows in values.items() if rows}


def _condition_regret_means(action_index: list[dict[str, Any]]) -> dict[str, float]:
    values: dict[str, list[float]] = {condition: [] for condition in CONDITIONS}
    for row in action_index:
        if not isinstance(row, dict) or row.get("condition") not in CONDITIONS:
            continue
        regret = row.get("planning_regret")
        if isinstance(regret, (int, float)) and not isinstance(regret, bool):
            values[row["condition"]].append(float(regret))
    return {condition: statistics.fmean(rows) for condition, rows in values.items() if rows}


def _strongest_baseline(values: dict[str, float]) -> str | None:
    baselines = {condition: values[condition] for condition in ("M", "R", "D") if condition in values}
    return min(baselines, key=baselines.get) if baselines else None


def _comparison(values: dict[str, float], metric: str) -> dict[str, Any]:
    baseline = _strongest_baseline(values)
    cd_value = values.get("CD")
    baseline_value = values.get(baseline) if baseline else None
    return {
        "metric": metric,
        "strongest_baseline_condition": baseline,
        "strongest_baseline_value": baseline_value,
        "cd_value": cd_value,
        "cd_minus_strongest_baseline": (cd_value - baseline_value)
        if isinstance(cd_value, (int, float)) and isinstance(baseline_value, (int, float))
        else None,
        "lower_is_better": True,
    }


def _validate_counts(receipt: dict[str, Any], action_receipt: dict[str, Any], expected_per_condition: int, errors: list[str]) -> None:
    counts = receipt.get("counts") if isinstance(receipt.get("counts"), dict) else {}
    sealed = counts.get("sealed_commitments_per_condition") if isinstance(counts.get("sealed_commitments_per_condition"), dict) else {}
    scored = counts.get("deterministic_scores_per_condition") if isinstance(counts.get("deterministic_scores_per_condition"), dict) else {}
    action_counts = (
        action_receipt.get("counts", {}).get("action_decisions_per_condition")
        if isinstance(action_receipt.get("counts"), dict)
        else {}
    )
    regret_counts = (
        action_receipt.get("counts", {}).get("deterministic_reward_or_regret_scores_per_condition")
        if isinstance(action_receipt.get("counts"), dict)
        else {}
    )
    for condition in CONDITIONS:
        if sealed.get(condition) != expected_per_condition:
            errors.append(f"sealed_commitments_per_condition_mismatch:{condition}:{sealed.get(condition)}:{expected_per_condition}")
        if scored.get(condition) != expected_per_condition:
            errors.append(f"deterministic_scores_per_condition_mismatch:{condition}:{scored.get(condition)}:{expected_per_condition}")
        if action_counts.get(condition) != expected_per_condition:
            errors.append(f"action_decisions_per_condition_mismatch:{condition}:{action_counts.get(condition)}:{expected_per_condition}")
        if regret_counts.get(condition) != expected_per_condition:
            errors.append(f"planning_regret_scores_per_condition_mismatch:{condition}:{regret_counts.get(condition)}:{expected_per_condition}")


def run_replication(
    *,
    output_root: Path,
    receipt_out: Path,
    split: str,
    episodes_per_family: int,
    episode_limit: int,
    model: str | None,
    timeout_s: float,
    gate0_case_root: Path | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    gate0_case_root = gate0_case_root.resolve() if gate0_case_root is not None else None
    live_condition = _load_module(LIVE_CONDITION_SCRIPT, "pctom_live_tau_condition_comparison")
    action_selection = _load_module(ACTION_SELECTION_SCRIPT, "pctom_live_tau_condition_action_selection")
    errors: list[str] = []

    condition_root = output_root / "live_tau_sealed_test_condition_comparison"
    condition_receipt_path = condition_root / "live_tau_condition_comparison_receipt.v1.json"
    action_root = output_root / "live_tau_sealed_test_action_selection"
    action_receipt_path = action_root / "live_tau_condition_action_selection_receipt.v1.json"
    summary_path = output_root / "artifacts" / "live_tau_sealed_test_replication_summary.json"

    condition_receipt = live_condition.run_live_comparison(
        output_root=condition_root,
        receipt_out=condition_receipt_path,
        split=split,
        episodes_per_family=episodes_per_family,
        episode_limit=episode_limit,
        model=model,
        timeout_s=timeout_s,
        gate0_case_root=gate0_case_root,
    )
    if condition_receipt.get("status") != live_condition.PASS_STATUS:
        errors.append(f"live_condition_status:{condition_receipt.get('status')}")
        errors.extend(f"live_condition_error:{error}" for error in condition_receipt.get("errors", []))

    action_receipt = action_selection.run_bridge(condition_root, action_root, action_receipt_path)
    if action_receipt.get("status") != action_selection.PASS_STATUS:
        errors.append(f"action_selection_status:{action_receipt.get('status')}")
        errors.extend(f"action_selection_error:{error}" for error in action_receipt.get("errors", []))

    condition_case_index_path = Path(str(condition_receipt.get("case_index_path", "")))
    action_decision_index_path = Path(str(action_receipt.get("decision_index", "")))
    case_index = _load_json(condition_case_index_path, errors, "condition_case_index")
    action_index = _load_json(action_decision_index_path, errors, "action_decision_index")
    if not isinstance(case_index, list):
        errors.append("condition_case_index_not_list")
        case_index = []
    if not isinstance(action_index, list):
        errors.append("action_decision_index_not_list")
        action_index = []

    expected_cases = episode_limit * len(CONDITIONS)
    counts = condition_receipt.get("counts") if isinstance(condition_receipt.get("counts"), dict) else {}
    if condition_receipt.get("split") != DEFAULT_SPLIT:
        errors.append(f"split_not_sealed_test:{condition_receipt.get('split')}")
    if counts.get("episodes_consumed") != episode_limit:
        errors.append(f"episodes_consumed_mismatch:{counts.get('episodes_consumed')}:{episode_limit}")
    if counts.get("cases") != expected_cases:
        errors.append(f"case_count_mismatch:{counts.get('cases')}:{expected_cases}")
    if condition_receipt.get("tau_call_attempts") != expected_cases:
        errors.append(f"tau_call_attempts_mismatch:{condition_receipt.get('tau_call_attempts')}:{expected_cases}")
    if condition_receipt.get("tau_live_call_performed") != expected_cases:
        errors.append(f"tau_live_call_performed_mismatch:{condition_receipt.get('tau_live_call_performed')}:{expected_cases}")
    if condition_receipt.get("tau_receipts_hash_bound") is not True:
        errors.append("tau_receipts_hash_bound_false")
    _validate_counts(condition_receipt, action_receipt, episode_limit, errors)

    belief_means = _condition_metric_means(case_index, "belief_brier")
    action_means = _condition_metric_means(case_index, "action_brier")
    regret_means = _condition_regret_means(action_index)
    summary = {
        "schema": "persona_dream.research.prospective_tom.live_tau_sealed_test_replication_summary.v1",
        "split": split,
        "episode_limit": episode_limit,
        "full_64_episode_replication": episode_limit == 64,
        "condition_means": {
            "belief_brier": belief_means,
            "action_brier": action_means,
            "planning_regret": regret_means,
        },
        "comparisons": {
            "belief_brier": _comparison(belief_means, "belief_brier"),
            "action_brier": _comparison(action_means, "action_brier"),
            "planning_regret": _comparison(regret_means, "planning_regret"),
        },
        "condition_receipt_sha256": _file_sha256(condition_receipt_path) if condition_receipt_path.exists() else None,
        "action_receipt_sha256": _file_sha256(action_receipt_path) if action_receipt_path.exists() else None,
    }
    _write_json(summary_path, summary)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    full_64_replication = split == DEFAULT_SPLIT and episode_limit == 64
    replication_claim = (
        "the full 64-episode sealed-test split was executed with live Tau-authored M/R/D/CD prediction payloads"
        if full_64_replication
        else "a sealed-test split subset was executed with live Tau-authored M/R/D/CD prediction payloads"
    )
    does_not_prove = [
        "statistical confidence for live Tau CD benefit on the full sealed test",
        "production retry machinery",
        "complete live Phase 01-16 runtime execution",
        "paid provider execution",
        "video, audio, or semantic dream quality",
    ]
    if not full_64_replication:
        does_not_prove.insert(0, "full 64-episode live Tau replication")
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_sealed_test_replication_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "split": split,
        "episodes_per_family": episodes_per_family,
        "episode_limit": episode_limit,
        "conditions": list(CONDITIONS),
        "full_64_episode_replication": episode_limit == 64,
        "gate0_case_root": str(gate0_case_root) if gate0_case_root else None,
        "gate0_attribution_overlay_used": condition_receipt.get("gate0_attribution_overlay_used") is True,
        "gate0_attribution_record_count": condition_receipt.get("gate0_attribution_record_count"),
        "live_tau_condition_comparison_receipt": str(condition_receipt_path),
        "live_tau_condition_comparison_receipt_sha256": _file_sha256(condition_receipt_path)
        if condition_receipt_path.exists()
        else None,
        "live_tau_action_selection_receipt": str(action_receipt_path),
        "live_tau_action_selection_receipt_sha256": _file_sha256(action_receipt_path)
        if action_receipt_path.exists()
        else None,
        "summary_path": str(summary_path),
        "summary_sha256": _file_sha256(summary_path) if summary_path.exists() else None,
        "metrics": summary,
        "counts": {
            "episodes_consumed": counts.get("episodes_consumed"),
            "families_consumed": counts.get("families_consumed"),
            "cases": counts.get("cases"),
            "tau_authored_prediction_payloads_per_condition": counts.get("sealed_commitments_per_condition"),
            "sealed_commitments_per_condition": counts.get("sealed_commitments_per_condition"),
            "deterministic_scores_per_condition": counts.get("deterministic_scores_per_condition"),
            "action_decisions_per_condition": action_receipt.get("counts", {}).get("action_decisions_per_condition")
            if isinstance(action_receipt.get("counts"), dict)
            else None,
            "planning_regret_scores_per_condition": action_receipt.get("counts", {}).get(
                "deterministic_reward_or_regret_scores_per_condition"
            )
            if isinstance(action_receipt.get("counts"), dict)
            else None,
            "tau_call_attempts": condition_receipt.get("tau_call_attempts"),
            "tau_live_call_performed": condition_receipt.get("tau_live_call_performed"),
        },
        "checks": {
            "split_is_sealed_test": split == DEFAULT_SPLIT,
            "live_tau_condition_receipt_passed": condition_receipt.get("status") == live_condition.PASS_STATUS,
            "live_tau_action_selection_receipt_passed": action_receipt.get("status") == action_selection.PASS_STATUS,
            "outcome_visible_before_seal": False,
            "tau_receipts_hash_bound": condition_receipt.get("tau_receipts_hash_bound") is True,
            "gate0_attribution_loaded_if_requested": (
                gate0_case_root is None
                or condition_receipt.get("gate0_attribution_overlay_used") is True
            ),
            "conditions_have_tau_authored_prediction_payloads": all(
                (counts.get("sealed_commitments_per_condition") or {}).get(condition) == episode_limit
                for condition in CONDITIONS
            ),
            "conditions_have_scores": all(
                (counts.get("deterministic_scores_per_condition") or {}).get(condition) == episode_limit
                for condition in CONDITIONS
            ),
            "conditions_have_action_decisions": all(
                (action_receipt.get("counts", {}).get("action_decisions_per_condition") or {}).get(condition)
                == episode_limit
                for condition in CONDITIONS
            )
            if isinstance(action_receipt.get("counts"), dict)
            else False,
            "llm_judge_absent": True,
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": True,
        },
        "mocked": False,
        "live": condition_receipt.get("live") is True and action_receipt.get("live") is True,
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "llm_judge_used": False,
        "human_content_judgment_required": False,
        "tau_call_attempts": condition_receipt.get("tau_call_attempts"),
        "tau_live_call_performed": condition_receipt.get("tau_live_call_performed"),
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "errors": errors,
        "claims": {
            "proves": [
                replication_claim,
                "accepted predictions were sealed before deterministic outcome reveal",
                "accepted predictions were scored by Gate 5 without human content judgment",
                "accepted predictions fed constrained Gate 6 action selection and planning-regret scoring",
                "Tau receipts were hash-bound into prediction commitments",
                "no Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the live Tau sealed-test replication bridge failed closed before claiming accepted replication evidence",
            ],
            "does_not_prove": does_not_prove,
        },
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--split", default=DEFAULT_SPLIT)
    parser.add_argument("--episodes-per-family", type=int, default=16)
    parser.add_argument("--episode-limit", type=int, default=4)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=240.0)
    parser.add_argument("--gate0-case-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "live_tau_sealed_test_replication_receipt.v1.json")
    receipt = run_replication(
        output_root=args.output_root,
        receipt_out=receipt_out,
        split=args.split,
        episodes_per_family=args.episodes_per_family,
        episode_limit=args.episode_limit,
        model=args.model,
        timeout_s=args.timeout_s,
        gate0_case_root=args.gate0_case_root,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
