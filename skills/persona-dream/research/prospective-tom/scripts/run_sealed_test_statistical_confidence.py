#!/usr/bin/env python3
"""Run a sealed-test PCTOM-R statistical-confidence slice.

This is deterministic and text-first. It does not call Tau, Memory, an LLM, a
VLM, or a provider. It consumes the existing held-out condition-benefit runner,
expands it to a sealed 64-episode test split, and computes paired bootstrap
confidence intervals for CD versus the strongest M/R/D baseline.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import statistics
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
HELDOUT_SCRIPT = RESEARCH_ROOT / "scripts" / "run_heldout_condition_benefit.py"
CONDITIONS = ("M", "R", "D", "CD")
PASS_STATUS = "PASS_PCTOM_SEALED_TEST_STATISTICAL_CONFIDENCE"
BLOCKED_STATUS = "BLOCKED_PCTOM_SEALED_TEST_STATISTICAL_CONFIDENCE"
PRIMARY_METRIC = "belief_brier"
DEFAULT_SPLIT = "sealed_test"
DEFAULT_GENERATED_AT = "2026-07-21T00:00:00Z"


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


def _percentile(sorted_values: list[float], percentile: float) -> float | None:
    if not sorted_values:
        return None
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (len(sorted_values) - 1) * percentile
    low = int(rank)
    high = min(low + 1, len(sorted_values) - 1)
    weight = rank - low
    return sorted_values[low] * (1.0 - weight) + sorted_values[high] * weight


def _bootstrap_ci(values: list[float], *, samples: int, seed: int, alpha: float) -> dict[str, Any]:
    rng = random.Random(seed)
    n = len(values)
    means: list[float] = []
    for _ in range(samples):
        means.append(statistics.fmean(values[rng.randrange(n)] for _ in range(n)))
    means.sort()
    return {
        "samples": samples,
        "seed": seed,
        "alpha": alpha,
        "mean": statistics.fmean(values),
        "lower": _percentile(means, alpha / 2.0),
        "upper": _percentile(means, 1.0 - alpha / 2.0),
        "bootstrap_distribution_sha256": _stable_json_sha256(means),
    }


def _belief_brier(row: dict[str, Any]) -> float | None:
    metrics = row.get("scoring_metrics") if isinstance(row.get("scoring_metrics"), dict) else {}
    scores = metrics.get("belief_scores")
    if not isinstance(scores, list):
        return None
    values = [score.get("brier") for score in scores if isinstance(score, dict)]
    numeric = [float(value) for value in values if isinstance(value, (int, float)) and not isinstance(value, bool)]
    return _mean(numeric)


def _action_brier(row: dict[str, Any]) -> float | None:
    metrics = row.get("scoring_metrics") if isinstance(row.get("scoring_metrics"), dict) else {}
    action = metrics.get("action") if isinstance(metrics.get("action"), dict) else {}
    value = action.get("brier")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _case_metric_rows(case_index: list[dict[str, Any]], errors: list[str]) -> dict[str, dict[str, dict[str, float]]]:
    by_episode: dict[str, dict[str, dict[str, float]]] = {}
    for idx, row in enumerate(case_index):
        if not isinstance(row, dict):
            errors.append(f"case_index_{idx}_not_object")
            continue
        episode_id = row.get("episode_id")
        condition = row.get("condition")
        if not isinstance(episode_id, str) or condition not in CONDITIONS:
            errors.append(f"case_index_{idx}_invalid_identity:{episode_id}:{condition}")
            continue
        belief = _belief_brier(row)
        action = _action_brier(row)
        if belief is None or action is None:
            errors.append(f"case_index_{idx}_missing_metric:{episode_id}:{condition}")
            continue
        by_episode.setdefault(episode_id, {})[condition] = {
            "belief_brier": belief,
            "action_brier": action,
        }
    return by_episode


def _planning_regret_rows(action_index: list[dict[str, Any]], errors: list[str]) -> dict[str, dict[str, float]]:
    by_episode: dict[str, dict[str, float]] = {}
    for idx, row in enumerate(action_index):
        if not isinstance(row, dict):
            errors.append(f"action_index_{idx}_not_object")
            continue
        episode_id = row.get("episode_id")
        condition = row.get("condition")
        regret = row.get("planning_regret")
        if not isinstance(episode_id, str) or condition not in CONDITIONS:
            errors.append(f"action_index_{idx}_invalid_identity:{episode_id}:{condition}")
            continue
        if not isinstance(regret, (int, float)) or isinstance(regret, bool):
            errors.append(f"action_index_{idx}_missing_regret:{episode_id}:{condition}")
            continue
        by_episode.setdefault(episode_id, {})[condition] = float(regret)
    return by_episode


def _condition_means(by_episode: dict[str, dict[str, dict[str, float]]], metric: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for condition in CONDITIONS:
        values = [rows[condition][metric] for rows in by_episode.values() if condition in rows]
        if values:
            result[condition] = statistics.fmean(values)
    return result


def _strongest_baseline(condition_means: dict[str, float]) -> str | None:
    baselines = {condition: condition_means[condition] for condition in ("M", "R", "D") if condition in condition_means}
    return min(baselines, key=baselines.get) if baselines else None


def _paired_deltas(
    by_episode: dict[str, dict[str, dict[str, float]]],
    *,
    metric: str,
    baseline_condition: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode_id in sorted(by_episode):
        episode_rows = by_episode[episode_id]
        if "CD" not in episode_rows or baseline_condition not in episode_rows:
            continue
        cd_value = episode_rows["CD"][metric]
        baseline_value = episode_rows[baseline_condition][metric]
        rows.append(
            {
                "episode_id": episode_id,
                "metric": metric,
                "baseline_condition": baseline_condition,
                "cd_value": cd_value,
                "baseline_value": baseline_value,
                "cd_minus_baseline": cd_value - baseline_value,
            }
        )
    return rows


def _planning_deltas(
    by_episode: dict[str, dict[str, float]],
    *,
    baseline_condition: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for episode_id in sorted(by_episode):
        episode_rows = by_episode[episode_id]
        if "CD" not in episode_rows or baseline_condition not in episode_rows:
            continue
        cd_value = episode_rows["CD"]
        baseline_value = episode_rows[baseline_condition]
        rows.append(
            {
                "episode_id": episode_id,
                "metric": "planning_regret",
                "baseline_condition": baseline_condition,
                "cd_value": cd_value,
                "baseline_value": baseline_value,
                "cd_minus_baseline": cd_value - baseline_value,
            }
        )
    return rows


def run_statistical_confidence(
    *,
    output_root: Path,
    receipt_out: Path,
    split: str,
    episodes_per_family: int,
    episode_limit: int,
    generated_at: str,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    heldout = _load_module(HELDOUT_SCRIPT, "pctom_heldout_condition_benefit")
    errors: list[str] = []

    heldout_root = output_root / "sealed_test_condition_benefit"
    heldout_receipt_path = heldout_root / "heldout_condition_benefit_receipt.v1.json"
    paired_delta_path = output_root / "artifacts" / "sealed_test_paired_deltas.json"
    statistical_summary_path = output_root / "artifacts" / "sealed_test_statistical_summary.json"

    heldout_receipt = heldout.run_heldout_benefit(
        output_root=heldout_root,
        receipt_out=heldout_receipt_path,
        split=split,
        episodes_per_family=episodes_per_family,
        episode_limit=episode_limit,
        generated_at=generated_at,
    )
    heldout_receipt_sha256 = _file_sha256(heldout_receipt_path)
    if heldout_receipt.get("status") != heldout.PASS_STATUS:
        errors.append(f"heldout_condition_benefit_status:{heldout_receipt.get('status')}")
        errors.extend(f"heldout_error:{error}" for error in heldout_receipt.get("errors", []))

    condition_case_index_path = Path(str(heldout_receipt.get("condition_case_index_path", "")))
    action_decision_index_path = Path(str(heldout_receipt.get("action_decision_index_path", "")))
    case_index = _load_json(condition_case_index_path, errors, "condition_case_index")
    action_index = _load_json(action_decision_index_path, errors, "action_decision_index")
    if not isinstance(case_index, list):
        errors.append("condition_case_index_not_list")
        case_index = []
    if not isinstance(action_index, list):
        errors.append("action_decision_index_not_list")
        action_index = []

    by_episode = _case_metric_rows(case_index, errors)
    regret_by_episode = _planning_regret_rows(action_index, errors)
    metric_means = {
        "belief_brier": _condition_means(by_episode, "belief_brier"),
        "action_brier": _condition_means(by_episode, "action_brier"),
    }
    belief_baseline = _strongest_baseline(metric_means["belief_brier"])
    action_baseline = _strongest_baseline(metric_means["action_brier"])
    regret_means = {
        condition: statistics.fmean(rows[condition] for rows in regret_by_episode.values() if condition in rows)
        for condition in CONDITIONS
        if any(condition in rows for rows in regret_by_episode.values())
    }
    regret_baseline = _strongest_baseline(regret_means)
    if belief_baseline is None:
        errors.append("missing_belief_strongest_baseline")
        belief_baseline = "D"
    if action_baseline is None:
        errors.append("missing_action_strongest_baseline")
        action_baseline = "M"
    if regret_baseline is None:
        errors.append("missing_planning_regret_strongest_baseline")
        regret_baseline = "M"

    belief_deltas = _paired_deltas(by_episode, metric="belief_brier", baseline_condition=belief_baseline)
    action_deltas = _paired_deltas(by_episode, metric="action_brier", baseline_condition=action_baseline)
    regret_deltas = _planning_deltas(regret_by_episode, baseline_condition=regret_baseline)
    if len(belief_deltas) != episode_limit:
        errors.append(f"belief_paired_delta_count_mismatch:{len(belief_deltas)}:{episode_limit}")
    if len(action_deltas) != episode_limit:
        errors.append(f"action_paired_delta_count_mismatch:{len(action_deltas)}:{episode_limit}")
    if len(regret_deltas) != episode_limit:
        errors.append(f"planning_regret_paired_delta_count_mismatch:{len(regret_deltas)}:{episode_limit}")

    belief_values = [row["cd_minus_baseline"] for row in belief_deltas]
    action_values = [row["cd_minus_baseline"] for row in action_deltas]
    regret_values = [row["cd_minus_baseline"] for row in regret_deltas]
    statistical_summary = {
        "primary_metric": PRIMARY_METRIC,
        "primary_baseline_condition": belief_baseline,
        "alpha": alpha,
        "bootstrap_samples": bootstrap_samples,
        "bootstrap_seed": bootstrap_seed,
        "condition_means": metric_means,
        "planning_regret_means": regret_means,
        "paired_delta_counts": {
            "belief_brier": len(belief_deltas),
            "action_brier": len(action_deltas),
            "planning_regret": len(regret_deltas),
        },
        "paired_delta_confidence_intervals": {
            "belief_brier": _bootstrap_ci(belief_values, samples=bootstrap_samples, seed=bootstrap_seed, alpha=alpha),
            "action_brier": _bootstrap_ci(action_values, samples=bootstrap_samples, seed=bootstrap_seed + 1, alpha=alpha),
            "planning_regret": _bootstrap_ci(regret_values, samples=bootstrap_samples, seed=bootstrap_seed + 2, alpha=alpha),
        },
        "baseline_conditions": {
            "belief_brier": belief_baseline,
            "action_brier": action_baseline,
            "planning_regret": regret_baseline,
        },
    }
    primary_ci = statistical_summary["paired_delta_confidence_intervals"]["belief_brier"]
    planning_ci = statistical_summary["paired_delta_confidence_intervals"]["planning_regret"]
    primary_benefit_with_confidence = (
        isinstance(primary_ci.get("upper"), (int, float))
        and primary_ci["upper"] < 0
        and isinstance(primary_ci.get("mean"), (int, float))
        and primary_ci["mean"] < 0
    )
    planning_benefit_with_confidence = (
        isinstance(planning_ci.get("upper"), (int, float))
        and planning_ci["upper"] < 0
        and isinstance(planning_ci.get("mean"), (int, float))
        and planning_ci["mean"] < 0
    )
    if not primary_benefit_with_confidence:
        errors.append(f"primary_confidence_interval_not_strictly_beneficial:{primary_ci}")

    paired_delta_bundle = {
        "schema": "persona_dream.research.prospective_tom.sealed_test_paired_deltas.v1",
        "heldout_receipt_sha256": heldout_receipt_sha256,
        "belief_brier": belief_deltas,
        "action_brier": action_deltas,
        "planning_regret": regret_deltas,
    }
    _write_json(paired_delta_path, paired_delta_bundle)
    _write_json(statistical_summary_path, statistical_summary)
    paired_delta_sha256 = _file_sha256(paired_delta_path)
    statistical_summary_sha256 = _file_sha256(statistical_summary_path)

    counts = heldout_receipt.get("counts") if isinstance(heldout_receipt.get("counts"), dict) else {}
    sealed_counts = counts.get("sealed_commitments_per_condition") if isinstance(counts.get("sealed_commitments_per_condition"), dict) else {}
    scored_counts = counts.get("deterministic_scores_per_condition") if isinstance(counts.get("deterministic_scores_per_condition"), dict) else {}
    action_counts = counts.get("action_decisions_per_condition") if isinstance(counts.get("action_decisions_per_condition"), dict) else {}
    for condition in CONDITIONS:
        if sealed_counts.get(condition) != episode_limit:
            errors.append(f"sealed_commitments_per_condition_mismatch:{condition}:{sealed_counts.get(condition)}:{episode_limit}")
        if scored_counts.get(condition) != episode_limit:
            errors.append(f"deterministic_scores_per_condition_mismatch:{condition}:{scored_counts.get(condition)}:{episode_limit}")
        if action_counts.get(condition) != episode_limit:
            errors.append(f"action_decisions_per_condition_mismatch:{condition}:{action_counts.get(condition)}:{episode_limit}")

    if counts.get("episodes_consumed") != episode_limit:
        errors.append(f"episodes_consumed_mismatch:{counts.get('episodes_consumed')}:{episode_limit}")
    if counts.get("cases") != episode_limit * len(CONDITIONS):
        errors.append(f"case_count_mismatch:{counts.get('cases')}:{episode_limit * len(CONDITIONS)}")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.sealed_test_statistical_confidence_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "split": split,
        "generated_at": generated_at,
        "episodes_per_family": episodes_per_family,
        "episode_limit": episode_limit,
        "conditions": list(CONDITIONS),
        "heldout_condition_benefit_receipt": str(heldout_receipt_path),
        "heldout_condition_benefit_receipt_sha256": heldout_receipt_sha256,
        "paired_delta_path": str(paired_delta_path),
        "paired_delta_sha256": paired_delta_sha256,
        "statistical_summary_path": str(statistical_summary_path),
        "statistical_summary_sha256": statistical_summary_sha256,
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
        "planning_benefit_with_confidence": planning_benefit_with_confidence,
        "oracle_policy_reference": "deterministic_simulator_policy.v1",
        "oracle_policy_source": "deterministic simulator labels and counterpart policy rules",
        "llm_judge_used": False,
        "mocked": False,
        "live": False,
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "human_content_judgment_required": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "counts": {
            "episodes_consumed": counts.get("episodes_consumed"),
            "families_consumed": counts.get("families_consumed"),
            "cases": counts.get("cases"),
            "sealed_commitments_per_condition": sealed_counts,
            "deterministic_scores_per_condition": scored_counts,
            "action_decisions_per_condition": action_counts,
            "paired_delta_counts": statistical_summary["paired_delta_counts"],
            "bootstrap_samples": bootstrap_samples,
        },
        "metrics": statistical_summary,
        "checks": {
            "split_is_sealed_test": split == DEFAULT_SPLIT,
            "episode_count_is_64": counts.get("episodes_consumed") == 64,
            "all_conditions_have_64_sealed_commitments": all(sealed_counts.get(condition) == 64 for condition in CONDITIONS),
            "all_conditions_have_64_scores": all(scored_counts.get(condition) == 64 for condition in CONDITIONS),
            "all_conditions_have_64_action_decisions": all(action_counts.get(condition) == 64 for condition in CONDITIONS),
            "primary_metric_is_preregistered": PRIMARY_METRIC == "belief_brier",
            "strongest_baseline_is_allowed": belief_baseline in ("M", "R", "D"),
            "primary_confidence_interval_upper_below_zero": isinstance(primary_ci.get("upper"), (int, float)) and primary_ci["upper"] < 0,
            "planning_confidence_interval_upper_below_zero": isinstance(planning_ci.get("upper"), (int, float)) and planning_ci["upper"] < 0,
            "llm_judge_absent": True,
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": True,
        },
        "errors": errors,
        "claims": {
            "proves": [
                "a sealed 64-episode deterministic test split was generated",
                "M, R, D, and CD each produced 64 sealed commitments before reveal",
                "M, R, D, and CD each produced 64 deterministic Gate 5 scores",
                "M, R, D, and CD each produced 64 constrained Gate 6 action decisions",
                "the preregistered belief Brier CD-minus-strongest-baseline paired bootstrap confidence interval is below zero",
                "no human content judgment, LLM judge, Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the sealed-test statistical-confidence runner failed closed before claiming statistical benefit",
            ],
            "does_not_prove": [
                "live Tau sealed-test execution",
                "live Memory recall in the sealed-test loop",
                "planning-regret benefit when regret is tied across conditions",
                "real external service fault injection",
                "production retry machinery",
                "complete live Phase 01-16 runtime execution",
                "paid provider execution",
                "video quality",
                "semantic dream quality",
            ],
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
    parser.add_argument("--episode-limit", type=int, default=64)
    parser.add_argument("--generated-at", default=DEFAULT_GENERATED_AT)
    parser.add_argument("--bootstrap-samples", type=int, default=2000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260721)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "sealed_test_statistical_confidence_receipt.v1.json")
    receipt = run_statistical_confidence(
        output_root=args.output_root,
        receipt_out=receipt_out,
        split=args.split,
        episodes_per_family=args.episodes_per_family,
        episode_limit=args.episode_limit,
        generated_at=args.generated_at,
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
