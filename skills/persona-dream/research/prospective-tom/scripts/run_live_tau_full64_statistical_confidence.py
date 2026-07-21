#!/usr/bin/env python3
"""Compute confidence intervals over an accepted full64 live Tau sealed-test root.

This consumes existing live Tau-authored artifacts. It does not call Tau,
Memory, an LLM, a VLM, or a provider.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
STAT_SCRIPT = RESEARCH_ROOT / "scripts" / "run_sealed_test_statistical_confidence.py"
CONDITIONS = ("M", "R", "D", "CD")
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_FULL64_STATISTICAL_CONFIDENCE"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_FULL64_STATISTICAL_CONFIDENCE"
PRIMARY_METRIC = "belief_brier"
DEFAULT_SPLIT = "sealed_test"


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_stat = _load_module(STAT_SCRIPT, "pctom_sealed_test_statistical_confidence")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


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


def _receipt_path(root: Path, name: str) -> Path:
    return root / name


def _condition_receipt_path(root: Path) -> Path:
    return root / "live_tau_sealed_test_condition_comparison" / "live_tau_condition_comparison_receipt.v1.json"


def _action_receipt_path(root: Path) -> Path:
    return root / "live_tau_sealed_test_action_selection" / "live_tau_condition_action_selection_receipt.v1.json"


def _case_index_path(root: Path) -> Path:
    return root / "live_tau_sealed_test_condition_comparison" / "artifacts" / "live_condition_case_index.json"


def _action_index_path(root: Path) -> Path:
    return root / "live_tau_sealed_test_action_selection" / "artifacts" / "live_condition_action_decisions.json"


def _condition_means_from_regret(regret_by_episode: dict[str, dict[str, float]]) -> dict[str, float]:
    return {
        condition: _stat.statistics.fmean(rows[condition] for rows in regret_by_episode.values() if condition in rows)
        for condition in CONDITIONS
        if any(condition in rows for rows in regret_by_episode.values())
    }


def _validate_base_receipts(
    *,
    base_root: Path,
    base_receipt: dict[str, Any],
    condition_receipt: dict[str, Any],
    action_receipt: dict[str, Any],
    errors: list[str],
) -> None:
    if base_receipt.get("status") != "PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION":
        errors.append(f"base_status_not_pass:{base_receipt.get('status')}")
    expected = {
        "split": DEFAULT_SPLIT,
        "episode_limit": 64,
        "full_64_episode_replication": True,
        "live": True,
        "mocked": False,
        "fixture_backed": False,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
    }
    for key, value in expected.items():
        if base_receipt.get(key) != value:
            errors.append(f"base_{key}_mismatch:{base_receipt.get(key)}:{value}")
    counts = base_receipt.get("counts") if isinstance(base_receipt.get("counts"), dict) else {}
    if counts.get("episodes_consumed") != 64:
        errors.append(f"base_episodes_consumed_mismatch:{counts.get('episodes_consumed')}:64")
    if counts.get("cases") != 256:
        errors.append(f"base_cases_mismatch:{counts.get('cases')}:256")
    if counts.get("tau_call_attempts") != 256:
        errors.append(f"base_tau_call_attempts_mismatch:{counts.get('tau_call_attempts')}:256")
    if counts.get("tau_live_call_performed") != 256:
        errors.append(f"base_tau_live_call_performed_mismatch:{counts.get('tau_live_call_performed')}:256")
    for count_key in (
        "tau_authored_prediction_payloads_per_condition",
        "sealed_commitments_per_condition",
        "deterministic_scores_per_condition",
        "action_decisions_per_condition",
        "planning_regret_scores_per_condition",
    ):
        values = counts.get(count_key)
        if not isinstance(values, dict):
            errors.append(f"base_{count_key}_not_object")
            continue
        for condition in CONDITIONS:
            if values.get(condition) != 64:
                errors.append(f"base_{count_key}_mismatch:{condition}:{values.get(condition)}:64")

    checks = base_receipt.get("checks") if isinstance(base_receipt.get("checks"), dict) else {}
    for key in (
        "split_is_sealed_test",
        "live_tau_condition_receipt_passed",
        "live_tau_action_selection_receipt_passed",
        "tau_receipts_hash_bound",
        "conditions_have_tau_authored_prediction_payloads",
        "conditions_have_scores",
        "conditions_have_action_decisions",
        "llm_judge_absent",
        "human_content_judgment_absent",
        "unsupported_writes_absent",
    ):
        if checks.get(key) is not True:
            errors.append(f"base_check_not_true:{key}:{checks.get(key)}")
    if checks.get("outcome_visible_before_seal") is not False:
        errors.append(f"base_outcome_visible_before_seal_not_false:{checks.get('outcome_visible_before_seal')}")

    if condition_receipt.get("status") != "PASS_LIVE_TAU_PCTOM_CONDITION_COMPARISON":
        errors.append(f"condition_status_not_pass:{condition_receipt.get('status')}")
    if action_receipt.get("status") != "PASS_LIVE_TAU_PCTOM_CONDITION_ACTION_SELECTION":
        errors.append(f"action_status_not_pass:{action_receipt.get('status')}")
    if condition_receipt.get("tau_receipts_hash_bound") is not True:
        errors.append("condition_tau_receipts_hash_bound_not_true")
    for receipt, label in ((condition_receipt, "condition"), (action_receipt, "action")):
        if receipt.get("live") is not True:
            errors.append(f"{label}_live_not_true:{receipt.get('live')}")
        if receipt.get("mocked") is not False:
            errors.append(f"{label}_mocked_not_false:{receipt.get('mocked')}")
        if receipt.get("fixture_backed") is not False:
            errors.append(f"{label}_fixture_backed_not_false:{receipt.get('fixture_backed')}")

    for key in (
        "memory_write_attempts",
        "provider_call_attempts",
        "canonical_memory_write_attempts",
        "identity_write_attempts",
        "source_memory_write_attempts",
    ):
        if base_receipt.get(key) != 0:
            errors.append(f"base_{key}_not_zero:{base_receipt.get(key)}")
    if not base_root.exists() or base_root.is_symlink():
        errors.append(f"base_root_invalid:{base_root}")


def run_live_tau_full64_statistical_confidence(
    *,
    base_root: Path,
    output_root: Path,
    receipt_out: Path,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
) -> dict[str, Any]:
    started = time.monotonic()
    base_root = base_root.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts_root = output_root / "artifacts"
    artifacts_root.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []

    base_receipt_path = _receipt_path(base_root, "live_tau_sealed_test_replication_receipt.v1.json")
    condition_receipt_path = _condition_receipt_path(base_root)
    action_receipt_path = _action_receipt_path(base_root)
    case_index_path = _case_index_path(base_root)
    action_index_path = _action_index_path(base_root)

    base_receipt = _load_json(base_receipt_path, errors, "base_live_tau_full64_receipt")
    condition_receipt = _load_json(condition_receipt_path, errors, "condition_receipt")
    action_receipt = _load_json(action_receipt_path, errors, "action_receipt")
    case_index = _load_json(case_index_path, errors, "condition_case_index")
    action_index = _load_json(action_index_path, errors, "action_decision_index")
    if not isinstance(base_receipt, dict):
        base_receipt = {}
    if not isinstance(condition_receipt, dict):
        condition_receipt = {}
    if not isinstance(action_receipt, dict):
        action_receipt = {}
    if not isinstance(case_index, list):
        errors.append("condition_case_index_not_list")
        case_index = []
    if not isinstance(action_index, list):
        errors.append("action_decision_index_not_list")
        action_index = []

    _validate_base_receipts(
        base_root=base_root,
        base_receipt=base_receipt,
        condition_receipt=condition_receipt,
        action_receipt=action_receipt,
        errors=errors,
    )

    by_episode = _stat._case_metric_rows(case_index, errors)
    regret_by_episode = _stat._planning_regret_rows(action_index, errors)
    metric_means = {
        "belief_brier": _stat._condition_means(by_episode, "belief_brier"),
        "action_brier": _stat._condition_means(by_episode, "action_brier"),
    }
    regret_means = _condition_means_from_regret(regret_by_episode)
    belief_baseline = _stat._strongest_baseline(metric_means["belief_brier"])
    action_baseline = _stat._strongest_baseline(metric_means["action_brier"])
    regret_baseline = _stat._strongest_baseline(regret_means)
    if belief_baseline is None:
        errors.append("missing_belief_strongest_baseline")
        belief_baseline = "M"
    if action_baseline is None:
        errors.append("missing_action_strongest_baseline")
        action_baseline = "M"
    if regret_baseline is None:
        errors.append("missing_planning_regret_strongest_baseline")
        regret_baseline = "M"

    belief_deltas = _stat._paired_deltas(by_episode, metric="belief_brier", baseline_condition=belief_baseline)
    action_deltas = _stat._paired_deltas(by_episode, metric="action_brier", baseline_condition=action_baseline)
    regret_deltas = _stat._planning_deltas(regret_by_episode, baseline_condition=regret_baseline)
    for label, rows in (
        ("belief_brier", belief_deltas),
        ("action_brier", action_deltas),
        ("planning_regret", regret_deltas),
    ):
        if len(rows) != 64:
            errors.append(f"{label}_paired_delta_count_mismatch:{len(rows)}:64")

    belief_values = [row["cd_minus_baseline"] for row in belief_deltas]
    action_values = [row["cd_minus_baseline"] for row in action_deltas]
    regret_values = [row["cd_minus_baseline"] for row in regret_deltas]
    statistical_summary = {
        "schema": "persona_dream.research.prospective_tom.live_tau_full64_statistical_summary.v1",
        "base_live_tau_replication_receipt_sha256": _stat._file_sha256(base_receipt_path) if base_receipt_path.exists() else None,
        "primary_metric": PRIMARY_METRIC,
        "alpha": alpha,
        "bootstrap_samples": bootstrap_samples,
        "bootstrap_seed": bootstrap_seed,
        "condition_means": metric_means,
        "planning_regret_means": regret_means,
        "baseline_conditions": {
            "belief_brier": belief_baseline,
            "action_brier": action_baseline,
            "planning_regret": regret_baseline,
        },
        "paired_delta_counts": {
            "belief_brier": len(belief_deltas),
            "action_brier": len(action_deltas),
            "planning_regret": len(regret_deltas),
        },
        "paired_delta_confidence_intervals": {
            "belief_brier": _stat._bootstrap_ci(belief_values, samples=bootstrap_samples, seed=bootstrap_seed, alpha=alpha)
            if belief_values
            else None,
            "action_brier": _stat._bootstrap_ci(action_values, samples=bootstrap_samples, seed=bootstrap_seed + 1, alpha=alpha)
            if action_values
            else None,
            "planning_regret": _stat._bootstrap_ci(regret_values, samples=bootstrap_samples, seed=bootstrap_seed + 2, alpha=alpha)
            if regret_values
            else None,
        },
    }
    primary_ci = statistical_summary["paired_delta_confidence_intervals"]["belief_brier"] or {}
    action_ci = statistical_summary["paired_delta_confidence_intervals"]["action_brier"] or {}
    planning_ci = statistical_summary["paired_delta_confidence_intervals"]["planning_regret"] or {}
    primary_benefit_with_confidence = (
        isinstance(primary_ci.get("mean"), (int, float))
        and isinstance(primary_ci.get("upper"), (int, float))
        and primary_ci["mean"] < 0
        and primary_ci["upper"] < 0
    )
    action_benefit_with_confidence = (
        isinstance(action_ci.get("mean"), (int, float))
        and isinstance(action_ci.get("upper"), (int, float))
        and action_ci["mean"] < 0
        and action_ci["upper"] < 0
    )
    planning_benefit_with_confidence = (
        isinstance(planning_ci.get("mean"), (int, float))
        and isinstance(planning_ci.get("upper"), (int, float))
        and planning_ci["mean"] < 0
        and planning_ci["upper"] < 0
    )
    if not primary_benefit_with_confidence:
        errors.append(f"primary_confidence_interval_not_strictly_beneficial:{primary_ci}")

    paired_delta_bundle = {
        "schema": "persona_dream.research.prospective_tom.live_tau_full64_paired_deltas.v1",
        "base_live_tau_replication_receipt_sha256": statistical_summary["base_live_tau_replication_receipt_sha256"],
        "belief_brier": belief_deltas,
        "action_brier": action_deltas,
        "planning_regret": regret_deltas,
    }
    paired_delta_path = artifacts_root / "live_tau_full64_paired_deltas.json"
    statistical_summary_path = artifacts_root / "live_tau_full64_statistical_summary.json"
    _stat._write_json(paired_delta_path, paired_delta_bundle)
    _stat._write_json(statistical_summary_path, statistical_summary)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    counts = base_receipt.get("counts") if isinstance(base_receipt.get("counts"), dict) else {}
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_full64_statistical_confidence_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "base_root": str(base_root),
        "base_live_tau_replication_receipt": str(base_receipt_path),
        "base_live_tau_replication_receipt_sha256": statistical_summary["base_live_tau_replication_receipt_sha256"],
        "condition_receipt": str(condition_receipt_path),
        "condition_receipt_sha256": _stat._file_sha256(condition_receipt_path) if condition_receipt_path.exists() else None,
        "action_receipt": str(action_receipt_path),
        "action_receipt_sha256": _stat._file_sha256(action_receipt_path) if action_receipt_path.exists() else None,
        "case_index_path": str(case_index_path),
        "case_index_sha256": _stat._file_sha256(case_index_path) if case_index_path.exists() else None,
        "action_index_path": str(action_index_path),
        "action_index_sha256": _stat._file_sha256(action_index_path) if action_index_path.exists() else None,
        "paired_delta_path": str(paired_delta_path),
        "paired_delta_sha256": _stat._file_sha256(paired_delta_path),
        "statistical_summary_path": str(statistical_summary_path),
        "statistical_summary_sha256": _stat._file_sha256(statistical_summary_path),
        "split": base_receipt.get("split"),
        "episode_limit": base_receipt.get("episode_limit"),
        "conditions": list(CONDITIONS),
        "primary_metric": PRIMARY_METRIC,
        "primary_baseline_condition": belief_baseline,
        "primary_cd_minus_baseline_mean": primary_ci.get("mean"),
        "primary_cd_minus_baseline_ci": {
            "lower": primary_ci.get("lower"),
            "upper": primary_ci.get("upper"),
            "alpha": alpha,
            "bootstrap_samples": bootstrap_samples,
            "bootstrap_seed": bootstrap_seed,
        },
        "primary_benefit_with_confidence": primary_benefit_with_confidence,
        "action_benefit_with_confidence": action_benefit_with_confidence,
        "planning_benefit_with_confidence": planning_benefit_with_confidence,
        "llm_judge_used": False,
        "mocked": False,
        "live": True,
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "live_tau_reexecuted": False,
        "human_content_judgment_required": False,
        "tau_call_attempts": 0,
        "tau_live_call_performed": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "counts": {
            "episodes_consumed": counts.get("episodes_consumed"),
            "families_consumed": counts.get("families_consumed"),
            "cases": counts.get("cases"),
            "tau_authored_prediction_payloads_per_condition": counts.get("tau_authored_prediction_payloads_per_condition"),
            "sealed_commitments_per_condition": counts.get("sealed_commitments_per_condition"),
            "deterministic_scores_per_condition": counts.get("deterministic_scores_per_condition"),
            "action_decisions_per_condition": counts.get("action_decisions_per_condition"),
            "planning_regret_scores_per_condition": counts.get("planning_regret_scores_per_condition"),
            "paired_delta_counts": statistical_summary["paired_delta_counts"],
            "bootstrap_samples": bootstrap_samples,
        },
        "metrics": statistical_summary,
        "checks": {
            "base_receipt_passed": base_receipt.get("status") == "PASS_LIVE_TAU_PCTOM_SEALED_TEST_REPLICATION",
            "base_is_full64_live_tau": base_receipt.get("full_64_episode_replication") is True and base_receipt.get("live") is True,
            "base_tau_receipts_hash_bound": (base_receipt.get("checks") or {}).get("tau_receipts_hash_bound") is True
            if isinstance(base_receipt.get("checks"), dict)
            else False,
            "split_is_sealed_test": base_receipt.get("split") == DEFAULT_SPLIT,
            "episode_count_is_64": counts.get("episodes_consumed") == 64,
            "case_count_is_256": counts.get("cases") == 256,
            "all_conditions_have_64_sealed_commitments": all(
                (counts.get("sealed_commitments_per_condition") or {}).get(condition) == 64 for condition in CONDITIONS
            ),
            "all_conditions_have_64_scores": all(
                (counts.get("deterministic_scores_per_condition") or {}).get(condition) == 64 for condition in CONDITIONS
            ),
            "all_conditions_have_64_action_decisions": all(
                (counts.get("action_decisions_per_condition") or {}).get(condition) == 64 for condition in CONDITIONS
            ),
            "all_metrics_have_64_paired_deltas": all(
                statistical_summary["paired_delta_counts"].get(metric) == 64
                for metric in ("belief_brier", "action_brier", "planning_regret")
            ),
            "primary_metric_is_preregistered": PRIMARY_METRIC == "belief_brier",
            "strongest_baseline_is_allowed": belief_baseline in ("M", "R", "D"),
            "primary_confidence_interval_upper_below_zero": isinstance(primary_ci.get("upper"), (int, float))
            and primary_ci["upper"] < 0,
            "action_confidence_interval_upper_below_zero": isinstance(action_ci.get("upper"), (int, float))
            and action_ci["upper"] < 0,
            "planning_confidence_interval_upper_below_zero": isinstance(planning_ci.get("upper"), (int, float))
            and planning_ci["upper"] < 0,
            "llm_judge_absent": True,
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": True,
        },
        "errors": errors,
        "claims": {
            "proves": [
                "the accepted full64 live Tau sealed-test replication root was consumed without reexecuting Tau",
                "64 paired live Tau episodes were compared for the preregistered belief Brier metric",
                "the preregistered belief Brier CD-minus-strongest-baseline paired bootstrap confidence interval is below zero",
                "action Brier and planning-regret confidence intervals were computed and reported without upgrading them to proven benefits",
                "no human content judgment, LLM judge, Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the live Tau full64 statistical-confidence runner failed closed before claiming statistical benefit",
            ],
            "does_not_prove": [
                "planning-regret benefit unless planning_benefit_with_confidence is true",
                "action Brier benefit unless action_benefit_with_confidence is true",
                "production retry machinery over the full64 root",
                "live Memory recall in the sealed-test loop",
                "full external service fault injection",
                "complete live Phase 01-16 runtime execution",
                "paid provider execution",
                "video, audio, or semantic dream quality",
            ],
        },
    }
    receipt["receipt_sha256"] = _stat._stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _stat._write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260721)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "live_tau_full64_statistical_confidence_receipt.v1.json")
    receipt = run_live_tau_full64_statistical_confidence(
        base_root=args.base_root,
        output_root=args.output_root,
        receipt_out=receipt_out,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
        alpha=args.alpha,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
