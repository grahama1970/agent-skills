#!/usr/bin/env python3
"""Run live Tau PCTOM-R planning replication over a balanced scenario slice."""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.util
import json
import multiprocessing as mp
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
FAMILIES = (
    "information_asymmetry_false_belief",
    "preference_desire_uncertainty",
    "trust_commitment_relationship",
    "coordination_conflict",
)
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_REPLICATION"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_BALANCED_PLANNING_REPLICATION"
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


def _select_balanced_episodes(
    corpus: dict[str, Any],
    episodes_per_family: int,
    *,
    variant_min: int | None,
    variant_max: int | None,
) -> list[dict[str, Any]]:
    by_family: dict[str, list[dict[str, Any]]] = {family: [] for family in FAMILIES}
    for episode in corpus.get("episodes", []):
        if not isinstance(episode, dict):
            continue
        family = episode.get("scenario_family")
        variant = episode.get("variant")
        if family not in by_family or not isinstance(variant, int):
            continue
        if variant_min is not None and variant < variant_min:
            continue
        if variant_max is not None and variant > variant_max:
            continue
        by_family[family].append(episode)

    selected: list[dict[str, Any]] = []
    for family in FAMILIES:
        selected.extend(by_family[family][:episodes_per_family])
    return selected


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


def _family_from_episode_id(episode_id: str) -> str:
    if "-info-asym-" in episode_id:
        return "information_asymmetry_false_belief"
    if "-pref-desire-" in episode_id:
        return "preference_desire_uncertainty"
    if "-trust-commit-" in episode_id:
        return "trust_commitment_relationship"
    if "-coordination-conflict-" in episode_id or "-coord-conflict-" in episode_id:
        return "coordination_conflict"
    return "unknown"


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
        by_episode.setdefault(episode_id, {})[condition] = row

    rows: list[dict[str, Any]] = []
    for episode_id in sorted(by_episode):
        episode_rows = by_episode[episode_id]
        missing = [condition for condition in CONDITIONS if condition not in episode_rows]
        if missing:
            errors.append(f"episode_missing_conditions:{episode_id}:{missing}")
            continue
        regrets: dict[str, float] = {}
        for condition in CONDITIONS:
            regret = episode_rows[condition].get("planning_regret")
            if not isinstance(regret, (int, float)) or isinstance(regret, bool):
                errors.append(f"episode_regret_not_numeric:{episode_id}:{condition}:{regret}")
                continue
            regrets[condition] = float(regret)
        if set(regrets) != set(CONDITIONS):
            continue
        baseline_condition = min(("M", "R", "D"), key=lambda condition: regrets[condition])
        baseline = episode_rows[baseline_condition]
        cd = episode_rows["CD"]
        delta = regrets["CD"] - regrets[baseline_condition]
        family = _family_from_episode_id(episode_id)
        rows.append(
            {
                "episode_id": episode_id,
                "scenario_family": family,
                "baseline_condition": baseline_condition,
                "baseline_action": baseline.get("selected_action"),
                "cd_action": cd.get("selected_action"),
                "oracle_action": cd.get("oracle_action"),
                "action_switched": cd.get("selected_action") != baseline.get("selected_action"),
                "baseline_regret": regrets[baseline_condition],
                "cd_regret": regrets["CD"],
                "cd_minus_baseline": delta,
                "direction": "BENEFIT" if delta < 0 else "HARM" if delta > 0 else "TIE",
                "oracle_match_transition": (
                    "GAIN"
                    if cd.get("selected_action") == cd.get("oracle_action")
                    and baseline.get("selected_action") != cd.get("oracle_action")
                    else "LOSS"
                    if cd.get("selected_action") != cd.get("oracle_action")
                    and baseline.get("selected_action") == cd.get("oracle_action")
                    else "UNCHANGED"
                ),
            }
        )
    return rows


def _summarize_planning(
    rows: list[dict[str, Any]],
    *,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
) -> dict[str, Any]:
    deltas = [float(row["cd_minus_baseline"]) for row in rows]
    ci = _bootstrap_ci(deltas, samples=bootstrap_samples, seed=bootstrap_seed, alpha=alpha)
    return {
        "episodes": len(rows),
        "families": sorted({row["scenario_family"] for row in rows}),
        "episodes_per_family": dict(collections.Counter(row["scenario_family"] for row in rows)),
        "mean_cd_minus_baseline": _mean(deltas),
        "direction_counts": dict(collections.Counter(row["direction"] for row in rows)),
        "action_switch_count": sum(1 for row in rows if row["action_switched"]),
        "nonzero_delta_count": sum(1 for row in rows if row["cd_minus_baseline"] != 0),
        "oracle_match_transitions": dict(collections.Counter(row["oracle_match_transition"] for row in rows)),
        "planning_regret_ci": ci,
        "planning_benefit_with_confidence": bool(ci and isinstance(ci.get("upper"), (int, float)) and ci["upper"] < 0),
        "row_pattern_sha256": _stable_json_sha256(
            [
                {
                    "episode_id": row["episode_id"],
                    "baseline_action": row["baseline_action"],
                    "cd_action": row["cd_action"],
                    "delta": row["cd_minus_baseline"],
                    "direction": row["direction"],
                }
                for row in rows
            ]
        ),
    }


def run_balanced_replication(
    *,
    output_root: Path,
    receipt_out: Path,
    family_episode_limit: int,
    episodes_per_family: int,
    variant_min: int | None,
    variant_max: int | None,
    model: str | None,
    timeout_s: float,
    outer_timeout_s: float | None,
    bootstrap_samples: int,
    bootstrap_seed: int,
    alpha: float,
    gate0_case_root: Path | None = None,
    reuse_condition_root: Path | None = None,
    reuse_action_root: Path | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    live_condition = _load_module(LIVE_CONDITION_SCRIPT, "pctom_live_tau_condition_comparison")
    action_selection = _load_module(ACTION_SELECTION_SCRIPT, "pctom_live_tau_condition_action_selection")
    errors: list[str] = []

    condition_root = output_root / "live_tau_balanced_condition_comparison"
    condition_receipt_path = condition_root / "live_tau_condition_comparison_receipt.v1.json"
    action_root = output_root / "live_tau_balanced_action_selection"
    action_receipt_path = action_root / "live_tau_condition_action_selection_receipt.v1.json"
    summary_path = output_root / "artifacts" / "live_tau_balanced_planning_summary.json"
    planning_rows_path = output_root / "artifacts" / "balanced_planning_rows.json"
    gate0_case_root = gate0_case_root.resolve() if gate0_case_root is not None else None

    if reuse_condition_root is not None:
        condition_root = reuse_condition_root.resolve()
        condition_receipt_path = condition_root / "live_tau_condition_comparison_receipt.v1.json"
        condition_receipt = _load_json(condition_receipt_path, errors, "reuse_condition_receipt")
        if not isinstance(condition_receipt, dict):
            condition_receipt = {}
    else:
        original_selector = live_condition._select_episodes

        def _selector(corpus: dict[str, Any], _limit: int) -> list[dict[str, Any]]:
            return _select_balanced_episodes(
                corpus,
                family_episode_limit,
                variant_min=variant_min,
                variant_max=variant_max,
            )

        def _run_condition_once() -> dict[str, Any]:
            try:
                live_condition._select_episodes = _selector
                return live_condition.run_live_comparison(
                    output_root=condition_root,
                    receipt_out=condition_receipt_path,
                    split=DEFAULT_SPLIT,
                    episodes_per_family=episodes_per_family,
                    episode_limit=family_episode_limit * len(FAMILIES),
                    model=model,
                    timeout_s=timeout_s,
                    gate0_case_root=gate0_case_root,
                )
            finally:
                live_condition._select_episodes = original_selector

        if outer_timeout_s is None:
            try:
                condition_receipt = _run_condition_once()
            except Exception as exc:
                errors.append(f"condition_exception:{type(exc).__name__}:{exc}")
                condition_receipt = {}
        else:
            ctx = mp.get_context("fork")
            queue: Any = ctx.Queue()

            def _child() -> None:
                try:
                    queue.put({"ok": True, "receipt": _run_condition_once()})
                except Exception as exc:  # pragma: no cover - child process transport
                    queue.put({"ok": False, "error": f"{type(exc).__name__}:{exc}"})

            process = ctx.Process(target=_child)
            process.start()
            process.join(outer_timeout_s)
            if process.is_alive():
                process.terminate()
                process.join(5)
                errors.append(f"condition_outer_timeout_s:{outer_timeout_s}")
                condition_receipt = {}
            elif not queue.empty():
                result = queue.get()
                if result.get("ok") is True and isinstance(result.get("receipt"), dict):
                    condition_receipt = result["receipt"]
                else:
                    errors.append(f"condition_child_error:{result.get('error')}")
                    condition_receipt = {}
            else:
                errors.append(f"condition_child_no_result:exitcode:{process.exitcode}")
                condition_receipt = {}

    if condition_receipt.get("status") != live_condition.PASS_STATUS:
        errors.append(f"live_condition_status:{condition_receipt.get('status')}")
        errors.extend(f"live_condition_error:{error}" for error in condition_receipt.get("errors", []))

    if reuse_action_root is not None:
        action_root = reuse_action_root.resolve()
        action_receipt_path = action_root / "live_tau_condition_action_selection_receipt.v1.json"
        action_receipt = _load_json(action_receipt_path, errors, "reuse_action_receipt")
        if not isinstance(action_receipt, dict):
            action_receipt = {}
    else:
        if condition_receipt.get("status") == live_condition.PASS_STATUS:
            action_receipt = action_selection.run_bridge(condition_root, action_root, action_receipt_path)
        else:
            action_receipt = {}
            errors.append("action_selection_skipped_without_passed_condition_receipt")
    if action_receipt.get("status") != action_selection.PASS_STATUS:
        errors.append(f"action_selection_status:{action_receipt.get('status')}")
        errors.extend(f"action_selection_error:{error}" for error in action_receipt.get("errors", []))

    condition_outer_timeout_blocked = any(error.startswith("condition_outer_timeout_s:") for error in errors)
    condition_blocked_before_case_acceptance = (
        condition_outer_timeout_blocked
        and condition_receipt.get("status") is None
        and action_receipt.get("status") is None
    )

    case_index_value = condition_receipt.get("case_index_path")
    if isinstance(case_index_value, str) and case_index_value:
        case_index = _load_json(Path(case_index_value), errors, "condition_case_index")
        if not isinstance(case_index, list):
            errors.append("condition_case_index_not_list")
            case_index = []
    else:
        if not condition_blocked_before_case_acceptance:
            errors.append("missing_condition_case_index_path")
        case_index = []

    action_index_value = action_receipt.get("decision_index")
    if isinstance(action_index_value, str) and action_index_value:
        action_index = _load_json(Path(action_index_value), errors, "action_decision_index")
        if not isinstance(action_index, list):
            errors.append("action_decision_index_not_list")
            action_index = []
    else:
        if not condition_blocked_before_case_acceptance:
            errors.append("missing_action_decision_index_path")
        action_index = []

    expected_episodes = family_episode_limit * len(FAMILIES)
    expected_cases = expected_episodes * len(CONDITIONS)
    counts = condition_receipt.get("counts") if isinstance(condition_receipt.get("counts"), dict) else {}
    if not condition_blocked_before_case_acceptance:
        if counts.get("episodes_consumed") != expected_episodes:
            errors.append(f"episodes_consumed_mismatch:{counts.get('episodes_consumed')}:{expected_episodes}")
        if counts.get("families_consumed") != len(FAMILIES):
            errors.append(f"families_consumed_mismatch:{counts.get('families_consumed')}:{len(FAMILIES)}")
        if counts.get("cases") != expected_cases:
            errors.append(f"case_count_mismatch:{counts.get('cases')}:{expected_cases}")
        if condition_receipt.get("tau_call_attempts") != expected_cases:
            errors.append(f"tau_call_attempts_mismatch:{condition_receipt.get('tau_call_attempts')}:{expected_cases}")
        if condition_receipt.get("tau_live_call_performed") != expected_cases:
            errors.append(f"tau_live_call_performed_mismatch:{condition_receipt.get('tau_live_call_performed')}:{expected_cases}")
        if condition_receipt.get("tau_receipts_hash_bound") is not True:
            errors.append("tau_receipts_hash_bound_false")

    planning_rows = _planning_rows(action_index, errors)
    planning_summary = _summarize_planning(
        planning_rows,
        bootstrap_samples=bootstrap_samples,
        bootstrap_seed=bootstrap_seed,
        alpha=alpha,
    )
    if not condition_blocked_before_case_acceptance:
        if len(planning_rows) != expected_episodes:
            errors.append(f"planning_rows_mismatch:{len(planning_rows)}:{expected_episodes}")
        if set(planning_summary["families"]) != set(FAMILIES):
            errors.append(f"planning_families_mismatch:{planning_summary['families']}")
        for family in FAMILIES:
            if planning_summary["episodes_per_family"].get(family) != family_episode_limit:
                errors.append(
                    f"planning_family_count_mismatch:{family}:{planning_summary['episodes_per_family'].get(family)}:{family_episode_limit}"
                )

    action_counts = action_receipt.get("counts", {}).get("action_decisions_per_condition") if isinstance(action_receipt.get("counts"), dict) else {}
    regret_counts = (
        action_receipt.get("counts", {}).get("deterministic_reward_or_regret_scores_per_condition")
        if isinstance(action_receipt.get("counts"), dict)
        else {}
    )
    if not condition_blocked_before_case_acceptance:
        for condition in CONDITIONS:
            if action_counts.get(condition) != expected_episodes:
                errors.append(f"action_decisions_per_condition_mismatch:{condition}:{action_counts.get(condition)}:{expected_episodes}")
            if regret_counts.get(condition) != expected_episodes:
                errors.append(f"planning_regret_scores_per_condition_mismatch:{condition}:{regret_counts.get(condition)}:{expected_episodes}")

    summary = {
        "schema": "persona_dream.research.prospective_tom.live_tau_balanced_planning_summary.v1",
        "split": DEFAULT_SPLIT,
        "family_episode_limit": family_episode_limit,
        "episodes_per_family": episodes_per_family,
        "variant_min": variant_min,
        "variant_max": variant_max,
        "condition_regret_means": _condition_regret_means(action_index),
        "planning_summary": planning_summary,
        "condition_receipt_sha256": _file_sha256(condition_receipt_path) if condition_receipt_path.exists() else None,
        "action_receipt_sha256": _file_sha256(action_receipt_path) if action_receipt_path.exists() else None,
    }
    baseline = _strongest_baseline(summary["condition_regret_means"])
    cd_value = summary["condition_regret_means"].get("CD")
    baseline_value = summary["condition_regret_means"].get(baseline) if baseline else None
    summary["comparison"] = {
        "metric": "planning_regret",
        "strongest_baseline_condition": baseline,
        "strongest_baseline_value": baseline_value,
        "cd_value": cd_value,
        "cd_minus_strongest_baseline": (cd_value - baseline_value)
        if isinstance(cd_value, (int, float)) and isinstance(baseline_value, (int, float))
        else None,
        "lower_is_better": True,
    }
    _write_json(planning_rows_path, {"schema": "persona_dream.research.prospective_tom.live_tau_balanced_planning_rows.v1", "rows": planning_rows})
    _write_json(summary_path, summary)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    does_not_prove = [
        "live Memory recall in the sealed-test loop",
        "permanently deployed external production retry service",
        "complete live Phase 01-16 runtime execution",
        "paid provider execution",
        "video, audio, or semantic dream quality",
    ]
    if not planning_summary["planning_benefit_with_confidence"]:
        does_not_prove.insert(0, "confidence-bounded planning benefit")
    live_tau_originated_artifacts_consumed = (
        condition_receipt.get("tau_live_call_performed") == expected_cases
        and condition_receipt.get("status") == live_condition.PASS_STATUS
        and action_receipt.get("live_tau_originated_artifacts_consumed") is True
        and action_receipt.get("status") == action_selection.PASS_STATUS
    )
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_balanced_planning_replication_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "split": DEFAULT_SPLIT,
        "family_episode_limit": family_episode_limit,
        "episodes_per_family": episodes_per_family,
        "variant_min": variant_min,
        "variant_max": variant_max,
        "gate0_case_root": str(gate0_case_root) if gate0_case_root is not None else None,
        "timeout_s": timeout_s,
        "outer_timeout_s": outer_timeout_s,
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
        "live_tau_reexecuted": reuse_condition_root is None,
        "live_tau_reexecuted_by_this_command": reuse_condition_root is None,
        "live_tau_originated_artifacts_consumed": live_tau_originated_artifacts_consumed,
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
            "families": planning_summary["families"],
            "episodes_per_family": planning_summary["episodes_per_family"],
            "action_decisions_per_condition": action_counts,
            "planning_regret_scores_per_condition": regret_counts,
            "action_switch_count": planning_summary["action_switch_count"],
            "nonzero_delta_count": planning_summary["nonzero_delta_count"],
            "oracle_match_transitions": planning_summary["oracle_match_transitions"],
        },
        "checks": {
            "condition_outer_timeout_contained_if_triggered": (
                not condition_outer_timeout_blocked
                or (
                    condition_blocked_before_case_acceptance
                    and "action_selection_skipped_without_passed_condition_receipt" in errors
                )
            ),
            "condition_blocked_before_case_acceptance": condition_blocked_before_case_acceptance,
            "condition_receipt_passed": condition_receipt.get("status") == live_condition.PASS_STATUS,
            "action_selection_receipt_passed": action_receipt.get("status") == action_selection.PASS_STATUS,
            "gate0_attribution_loaded_if_requested": (
                gate0_case_root is None
                or condition_receipt.get("gate0_attribution_overlay_used") is True
                or condition_blocked_before_case_acceptance
            ),
            "all_four_families_selected": set(planning_summary["families"]) == set(FAMILIES),
            "balanced_family_counts": all(
                planning_summary["episodes_per_family"].get(family) == family_episode_limit for family in FAMILIES
            ),
            "tau_receipts_hash_bound": condition_receipt.get("tau_receipts_hash_bound") is True,
            "all_conditions_have_expected_action_counts": all(
                action_counts.get(condition) == expected_episodes for condition in CONDITIONS
            ),
            "planning_rows_cover_expected_episodes": len(planning_rows) == expected_episodes,
            "llm_judge_absent": True,
            "human_content_judgment_absent": True,
            "unsupported_writes_absent": True,
        },
        "metrics": summary,
        "planning_benefit_with_confidence": planning_summary["planning_benefit_with_confidence"],
        "errors": errors,
        "claims": {
            "proves": [
                (
                    "a balanced four-family sealed-test slice was run through live Tau M/R/D/CD condition predictions"
                    if reuse_condition_root is None
                    else "a balanced four-family sealed-test slice consumed hash-bound live Tau M/R/D/CD condition artifacts"
                ),
                "the live Tau outputs were sealed before deterministic outcome reveal and scored by Gate 5",
                "the live Tau scores were mapped into constrained Gate 6 action selections and planning-regret rows",
                "planning-regret CD-minus-baseline deltas were recomputed across all four scenario families",
                "no human content judgment, LLM judge, Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the balanced live Tau planning replication failed closed before accepting a balanced planning claim",
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
    parser.add_argument("--family-episode-limit", type=int, default=2)
    parser.add_argument("--episodes-per-family", type=int, default=24)
    parser.add_argument("--variant-min", type=int, default=None)
    parser.add_argument("--variant-max", type=int, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-s", type=float, default=240.0)
    parser.add_argument("--outer-timeout-s", type=float, default=None)
    parser.add_argument("--bootstrap-samples", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260726)
    parser.add_argument("--alpha", type=float, default=0.05)
    parser.add_argument("--gate0-case-root", type=Path, default=None)
    parser.add_argument("--reuse-condition-root", type=Path, default=None)
    parser.add_argument("--reuse-action-root", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt_out = args.receipt_out or (args.output_root / "live_tau_balanced_planning_replication_receipt.v1.json")
    receipt = run_balanced_replication(
        output_root=args.output_root,
        receipt_out=receipt_out,
        family_episode_limit=args.family_episode_limit,
        episodes_per_family=args.episodes_per_family,
        variant_min=args.variant_min,
        variant_max=args.variant_max,
        model=args.model,
        timeout_s=args.timeout_s,
        outer_timeout_s=args.outer_timeout_s,
        bootstrap_samples=args.bootstrap_samples,
        bootstrap_seed=args.bootstrap_seed,
        alpha=args.alpha,
        gate0_case_root=args.gate0_case_root,
        reuse_condition_root=args.reuse_condition_root,
        reuse_action_root=args.reuse_action_root,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
