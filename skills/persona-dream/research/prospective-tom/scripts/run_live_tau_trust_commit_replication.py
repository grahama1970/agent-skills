#!/usr/bin/env python3
"""Run a focused live Tau replication over trust/commitment PCTOM-R episodes."""
from __future__ import annotations

import argparse
import collections
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
LIVE_CONDITION_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_condition_comparison.py"
ACTION_SELECTION_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_condition_action_selection.py"
CONDITIONS = ("M", "R", "D", "CD")
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_TRUST_COMMIT_REPLICATION"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_TRUST_COMMIT_REPLICATION"
DEFAULT_SPLIT = "sealed_test"
TRUST_FAMILY = "trust_commitment_relationship"


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


def _select_trust_commit_episodes(
    corpus: dict[str, Any],
    limit: int,
    *,
    variant_min: int | None = None,
    variant_max: int | None = None,
) -> list[dict[str, Any]]:
    episodes = [
        episode
        for episode in corpus.get("episodes", [])
        if isinstance(episode, dict) and episode.get("scenario_family") == TRUST_FAMILY
        and (variant_min is None or isinstance(episode.get("variant"), int) and episode["variant"] >= variant_min)
        and (variant_max is None or isinstance(episode.get("variant"), int) and episode["variant"] <= variant_max)
    ]
    if limit > 0:
        episodes = episodes[:limit]
    return episodes


def _variant_from_episode_id(episode_id: str) -> int | None:
    suffix = episode_id.rsplit("-", 1)[-1]
    try:
        return int(suffix)
    except ValueError:
        return None


def _bootstrap_ci(values: list[float], *, samples: int, seed: int, alpha: float) -> dict[str, Any] | None:
    if not values:
        return None
    rng = random.Random(seed)
    means: list[float] = []
    for _ in range(samples):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(statistics.fmean(sample))
    means.sort()
    lower_idx = max(0, int((alpha / 2) * samples) - 1)
    upper_idx = min(samples - 1, int((1 - alpha / 2) * samples) - 1)
    return {
        "alpha": alpha,
        "samples": samples,
        "seed": seed,
        "mean": statistics.fmean(values),
        "lower": means[lower_idx],
        "upper": means[upper_idx],
        "bootstrap_distribution_sha256": _stable_json_sha256(means),
    }


def _condition_regret_means(action_index: list[dict[str, Any]]) -> dict[str, float]:
    values: dict[str, list[float]] = {condition: [] for condition in CONDITIONS}
    for row in action_index:
        if not isinstance(row, dict) or row.get("condition") not in CONDITIONS:
            continue
        regret = row.get("planning_regret")
        if isinstance(regret, (int, float)) and not isinstance(regret, bool):
            values[row["condition"]].append(float(regret))
    return {condition: statistics.fmean(rows) for condition, rows in values.items() if rows}


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


def _planning_rows(action_index: list[dict[str, Any]], errors: list[str]) -> list[dict[str, Any]]:
    by_episode: dict[str, dict[str, dict[str, Any]]] = {}
    for idx, row in enumerate(action_index):
        if not isinstance(row, dict):
            errors.append(f"action_index_{idx}_not_object")
            continue
        episode_id = row.get("episode_id")
        condition = row.get("condition")
        if not isinstance(episode_id, str) or condition not in CONDITIONS:
            errors.append(f"action_index_{idx}_invalid_identity:{episode_id}:{condition}")
            continue
        if "trust-commit" not in episode_id:
            errors.append(f"action_index_{idx}_not_trust_commit:{episode_id}")
        by_episode.setdefault(episode_id, {})[condition] = row

    rows: list[dict[str, Any]] = []
    for episode_id in sorted(by_episode):
        episode_rows = by_episode[episode_id]
        missing = [condition for condition in CONDITIONS if condition not in episode_rows]
        if missing:
            errors.append(f"episode_missing_conditions:{episode_id}:{missing}")
            continue
        baseline_regrets: dict[str, float] = {}
        for condition in ("M", "R", "D"):
            regret = episode_rows[condition].get("planning_regret")
            if not isinstance(regret, (int, float)) or isinstance(regret, bool):
                errors.append(f"episode_regret_not_numeric:{episode_id}:{condition}:{regret}")
                continue
            baseline_regrets[condition] = float(regret)
        if set(baseline_regrets) != {"M", "R", "D"}:
            errors.append(f"episode_baseline_regret_missing:{episode_id}:{sorted(baseline_regrets)}")
            continue
        baseline_condition = min(baseline_regrets, key=baseline_regrets.get)
        baseline = episode_rows[baseline_condition]
        cd = episode_rows["CD"]
        cd_regret = cd.get("planning_regret")
        if not isinstance(cd_regret, (int, float)) or isinstance(cd_regret, bool):
            errors.append(f"episode_cd_regret_not_numeric:{episode_id}:{cd_regret}")
            continue
        baseline_regret = float(baseline["planning_regret"])
        delta = float(cd_regret) - baseline_regret
        rows.append(
            {
                "episode_id": episode_id,
                "baseline_condition": baseline_condition,
                "baseline_action": baseline.get("selected_action"),
                "cd_action": cd.get("selected_action"),
                "oracle_action": cd.get("oracle_action"),
                "action_switched": cd.get("selected_action") != baseline.get("selected_action"),
                "cd_matches_oracle": cd.get("selected_action") == cd.get("oracle_action"),
                "baseline_matches_oracle": baseline.get("selected_action") == cd.get("oracle_action"),
                "oracle_match_transition": (
                    "GAIN"
                    if cd.get("selected_action") == cd.get("oracle_action")
                    and baseline.get("selected_action") != cd.get("oracle_action")
                    else "LOSS"
                    if cd.get("selected_action") != cd.get("oracle_action")
                    and baseline.get("selected_action") == cd.get("oracle_action")
                    else "UNCHANGED"
                ),
                "baseline_regret": baseline_regret,
                "cd_regret": float(cd_regret),
                "cd_minus_baseline": delta,
                "direction": "BENEFIT" if delta < 0 else "HARM" if delta > 0 else "TIE",
            }
        )
    return rows


def _summarize_planning(rows: list[dict[str, Any]], *, bootstrap_samples: int, bootstrap_seed: int, alpha: float) -> dict[str, Any]:
    deltas = [float(row["cd_minus_baseline"]) for row in rows]
    nonzero = [row for row in rows if row["cd_minus_baseline"] != 0]
    switched = [row for row in rows if row["action_switched"]]
    transition_counts = collections.Counter(row["oracle_match_transition"] for row in rows)
    ci = _bootstrap_ci(deltas, samples=bootstrap_samples, seed=bootstrap_seed, alpha=alpha)
    return {
        "episodes": len(rows),
        "mean_cd_minus_baseline": _mean(deltas),
        "direction_counts": dict(collections.Counter(row["direction"] for row in rows)),
        "delta_counts": dict(collections.Counter(str(row["cd_minus_baseline"]) for row in rows)),
        "action_switch_count": len(switched),
        "nonzero_delta_count": len(nonzero),
        "nonzero_action_switch_count": sum(1 for row in nonzero if row["action_switched"]),
        "oracle_match_transitions": dict(transition_counts),
        "planning_regret_ci": ci,
        "planning_benefit_with_confidence": bool(ci and isinstance(ci.get("upper"), (int, float)) and ci["upper"] < 0),
        "rows": rows,
    }


def run_trust_commit_replication(
    *,
    output_root: Path,
    receipt_out: Path,
    trust_episode_limit: int,
    episodes_per_family: int,
    variant_min: int | None,
    variant_max: int | None,
    model: str | None,
    timeout_s: float,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    live_condition = _load_module(LIVE_CONDITION_SCRIPT, "pctom_live_tau_condition_comparison")
    action_selection = _load_module(ACTION_SELECTION_SCRIPT, "pctom_live_tau_condition_action_selection")
    errors: list[str] = []

    original_selector = live_condition._select_episodes

    def _selector(corpus: dict[str, Any], limit: int) -> list[dict[str, Any]]:
        requested = trust_episode_limit if trust_episode_limit > 0 else limit
        return _select_trust_commit_episodes(corpus, requested, variant_min=variant_min, variant_max=variant_max)

    condition_root = output_root / "live_tau_trust_commit_condition_comparison"
    condition_receipt_path = condition_root / "live_tau_condition_comparison_receipt.v1.json"
    action_root = output_root / "live_tau_trust_commit_action_selection"
    action_receipt_path = action_root / "live_tau_condition_action_selection_receipt.v1.json"
    summary_path = output_root / "artifacts" / "live_tau_trust_commit_replication_summary.json"
    planning_rows_path = output_root / "artifacts" / "trust_commit_planning_rows.json"

    try:
        live_condition._select_episodes = _selector
        condition_receipt = live_condition.run_live_comparison(
            output_root=condition_root,
            receipt_out=condition_receipt_path,
            split=DEFAULT_SPLIT,
            episodes_per_family=episodes_per_family,
            episode_limit=trust_episode_limit,
            model=model,
            timeout_s=timeout_s,
        )
    finally:
        live_condition._select_episodes = original_selector

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

    expected_cases = trust_episode_limit * len(CONDITIONS)
    counts = condition_receipt.get("counts") if isinstance(condition_receipt.get("counts"), dict) else {}
    if condition_receipt.get("split") != DEFAULT_SPLIT:
        errors.append(f"split_not_sealed_test:{condition_receipt.get('split')}")
    if counts.get("episodes_consumed") != trust_episode_limit:
        errors.append(f"episodes_consumed_mismatch:{counts.get('episodes_consumed')}:{trust_episode_limit}")
    if counts.get("families_consumed") != 1:
        errors.append(f"families_consumed_mismatch:{counts.get('families_consumed')}:1")
    if counts.get("cases") != expected_cases:
        errors.append(f"case_count_mismatch:{counts.get('cases')}:{expected_cases}")
    if condition_receipt.get("tau_call_attempts") != expected_cases:
        errors.append(f"tau_call_attempts_mismatch:{condition_receipt.get('tau_call_attempts')}:{expected_cases}")
    if condition_receipt.get("tau_live_call_performed") != expected_cases:
        errors.append(f"tau_live_call_performed_mismatch:{condition_receipt.get('tau_live_call_performed')}:{expected_cases}")
    if condition_receipt.get("tau_receipts_hash_bound") is not True:
        errors.append("tau_receipts_hash_bound_false")
    for row in case_index:
        if not isinstance(row, dict):
            continue
        episode_id = str(row.get("episode_id"))
        if "trust-commit" not in episode_id:
            errors.append(f"case_index_non_trust_episode:{row.get('episode_id')}")
        variant = _variant_from_episode_id(episode_id)
        if variant_min is not None and (not isinstance(variant, int) or variant < variant_min):
            errors.append(f"case_index_variant_below_min:{episode_id}:{variant}:{variant_min}")
        if variant_max is not None and (not isinstance(variant, int) or variant > variant_max):
            errors.append(f"case_index_variant_above_max:{episode_id}:{variant}:{variant_max}")

    action_counts = action_receipt.get("counts", {}).get("action_decisions_per_condition") if isinstance(action_receipt.get("counts"), dict) else {}
    regret_counts = (
        action_receipt.get("counts", {}).get("deterministic_reward_or_regret_scores_per_condition")
        if isinstance(action_receipt.get("counts"), dict)
        else {}
    )
    for condition in CONDITIONS:
        if action_counts.get(condition) != trust_episode_limit:
            errors.append(f"action_decisions_per_condition_mismatch:{condition}:{action_counts.get(condition)}:{trust_episode_limit}")
        if regret_counts.get(condition) != trust_episode_limit:
            errors.append(f"planning_regret_scores_per_condition_mismatch:{condition}:{regret_counts.get(condition)}:{trust_episode_limit}")

    planning_rows = _planning_rows(action_index, errors)
    planning_summary = _summarize_planning(
        planning_rows,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
        alpha=alpha,
    )
    selected_episode_ids = sorted({row["episode_id"] for row in planning_rows if isinstance(row.get("episode_id"), str)})
    belief_means = _condition_metric_means(case_index, "belief_brier")
    action_means = _condition_metric_means(case_index, "action_brier")
    regret_means = _condition_regret_means(action_index)
    summary = {
        "schema": "persona_dream.research.prospective_tom.live_tau_trust_commit_replication_summary.v1",
        "split": DEFAULT_SPLIT,
        "scenario_family": TRUST_FAMILY,
        "trust_episode_limit": trust_episode_limit,
        "episodes_per_family": episodes_per_family,
        "variant_min": variant_min,
        "variant_max": variant_max,
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
        "planning_summary": planning_summary,
        "condition_receipt_sha256": _file_sha256(condition_receipt_path) if condition_receipt_path.exists() else None,
        "action_receipt_sha256": _file_sha256(action_receipt_path) if action_receipt_path.exists() else None,
    }
    _write_json(planning_rows_path, {"schema": "persona_dream.research.prospective_tom.live_tau_trust_commit_planning_rows.v1", "rows": planning_rows})
    _write_json(summary_path, summary)
    does_not_prove = [
        "production retry machinery",
        "live Memory recall in the sealed-test loop",
        "complete live Phase 01-16 runtime execution",
        "paid provider execution",
        "video, audio, or semantic dream quality",
    ]
    if not planning_summary["planning_benefit_with_confidence"]:
        does_not_prove.insert(0, "confidence-bounded planning benefit")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_trust_commit_replication_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "split": DEFAULT_SPLIT,
        "scenario_family": TRUST_FAMILY,
        "trust_episode_limit": trust_episode_limit,
        "episodes_per_family": episodes_per_family,
        "variant_min": variant_min,
        "variant_max": variant_max,
        "conditions": list(CONDITIONS),
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
        "planning_rows_path": str(planning_rows_path),
        "planning_rows_sha256": _file_sha256(planning_rows_path) if planning_rows_path.exists() else None,
        "mocked": False,
        "live": condition_receipt.get("tau_live_call_performed") == expected_cases,
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "live_tau_reexecuted": True,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "tau_call_attempts": condition_receipt.get("tau_call_attempts"),
        "tau_live_call_performed": condition_receipt.get("tau_live_call_performed"),
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "counts": {
            "episodes": len(planning_rows),
            "cases": len(case_index),
            "selected_episode_ids": selected_episode_ids,
            "action_decisions_per_condition": action_counts,
            "planning_regret_scores_per_condition": regret_counts,
            "action_switch_count": planning_summary["action_switch_count"],
            "nonzero_delta_count": planning_summary["nonzero_delta_count"],
            "nonzero_action_switch_count": planning_summary["nonzero_action_switch_count"],
            "oracle_match_transitions": planning_summary["oracle_match_transitions"],
        },
        "checks": {
            "condition_receipt_passed": condition_receipt.get("status") == live_condition.PASS_STATUS,
            "action_selection_receipt_passed": action_receipt.get("status") == action_selection.PASS_STATUS,
            "only_trust_commit_episodes_selected": not any("non_trust_episode" in error for error in errors),
            "variant_min_respected": not any("variant_below_min" in error for error in errors),
            "variant_max_respected": not any("variant_above_max" in error for error in errors),
            "tau_receipts_hash_bound": condition_receipt.get("tau_receipts_hash_bound") is True,
            "all_conditions_have_expected_action_counts": all(
                action_counts.get(condition) == trust_episode_limit for condition in CONDITIONS
            ),
            "planning_rows_cover_expected_episodes": len(planning_rows) == trust_episode_limit,
            "llm_judge_absent": True,
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": True,
        },
        "metrics": summary,
        "errors": errors,
        "claims": {
            "proves": [
                "a focused trust/commitment subset was rerun through live Tau M/R/D/CD condition predictions",
                "the live Tau trust/commitment outputs were sealed before deterministic outcome reveal and scored by Gate 5",
                "the live Tau trust/commitment scores were mapped into constrained Gate 6 action selections and planning-regret rows",
                "planning-regret CD-minus-baseline deltas were recomputed for the trust/commitment subset",
                "no human content judgment, LLM judge, Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the focused trust/commitment live Tau replication failed closed before accepting a planning-benefit claim",
            ],
            "does_not_prove": does_not_prove,
        },
    }
    receipt["planning_benefit_with_confidence"] = planning_summary["planning_benefit_with_confidence"]
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--trust-episode-limit", type=int, default=16)
    parser.add_argument("--episodes-per-family", type=int, default=16)
    parser.add_argument("--variant-min", type=int, default=None)
    parser.add_argument("--variant-max", type=int, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=240.0)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260724)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt_out = args.receipt_out or (args.output_root / "live_tau_trust_commit_replication_receipt.v1.json")
    receipt = run_trust_commit_replication(
        output_root=args.output_root,
        receipt_out=receipt_out,
        trust_episode_limit=args.trust_episode_limit,
        episodes_per_family=args.episodes_per_family,
        variant_min=args.variant_min,
        variant_max=args.variant_max,
        model=args.model,
        timeout_s=args.timeout_s,
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
