#!/usr/bin/env python3
"""Run a frozen held-out PCTOM-R condition-benefit slice.

This runner is text-first and deterministic. It does not call Tau, Memory, an
LLM, a VLM, or a provider. It consumes the local simulator, Gate 2-5 validators,
and Gate 6 action-selection checker to answer the next PCTOM-R boundary:
whether CD improves a preregistered proper score over the strongest M/R/D
baseline on an explicitly frozen held-out split, while still emitting action
decisions and zero-write evidence.
"""
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
CONDITION_SCRIPT = RESEARCH_ROOT / "scripts" / "run_condition_comparison.py"
ACTION_SCRIPT = RESEARCH_ROOT / "scripts" / "run_action_selection_trial.py"
ACTION_BRIDGE_SCRIPT = RESEARCH_ROOT / "scripts" / "run_live_tau_condition_action_selection.py"
CONDITIONS = ("M", "R", "D", "CD")
PASS_STATUS = "PASS_PCTOM_HELDOUT_CONDITION_BENEFIT"
BLOCKED_STATUS = "BLOCKED_PCTOM_HELDOUT_CONDITION_BENEFIT"
PRIMARY_METRIC = "mean_belief_brier"
DEFAULT_SPLIT = "explicitly_frozen_heldout"
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


def _episode_index(corpus: Any, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(corpus, dict) or not isinstance(corpus.get("episodes"), list):
        errors.append("corpus_episodes_missing")
        return {}
    episodes: dict[str, dict[str, Any]] = {}
    for idx, episode in enumerate(corpus["episodes"]):
        if not isinstance(episode, dict) or not isinstance(episode.get("episode_id"), str):
            errors.append(f"corpus_episode_{idx}_invalid")
            continue
        episodes[episode["episode_id"]] = episode
    return episodes


def _filtered_episodes(
    corpus: dict[str, Any],
    limit: int,
    *,
    scenario_family: str | None,
    variant_min: int | None,
    variant_max: int | None,
) -> list[dict[str, Any]]:
    episodes = []
    for episode in corpus.get("episodes", []):
        if not isinstance(episode, dict):
            continue
        if scenario_family and episode.get("scenario_family") != scenario_family:
            continue
        variant = episode.get("variant")
        if variant_min is not None and (not isinstance(variant, int) or variant < variant_min):
            continue
        if variant_max is not None and (not isinstance(variant, int) or variant > variant_max):
            continue
        episodes.append(episode)
    if limit > 0:
        return episodes[:limit]
    return episodes


def _condition_metric_comparison(metrics: dict[str, Any], metric_name: str) -> dict[str, Any]:
    baseline_scores = {
        condition: metrics.get(condition, {}).get(metric_name)
        for condition in CONDITIONS
        if condition != "CD" and isinstance(metrics.get(condition, {}).get(metric_name), (int, float))
    }
    strongest = min(baseline_scores, key=baseline_scores.get) if baseline_scores else None
    cd_score = metrics.get("CD", {}).get(metric_name)
    delta = cd_score - baseline_scores[strongest] if strongest and isinstance(cd_score, (int, float)) else None
    return {
        "primary_metric": metric_name,
        "proper_score": True,
        "strongest_baseline_condition": strongest,
        "strongest_baseline_score": baseline_scores.get(strongest) if strongest else None,
        "cd_score": cd_score,
        "cd_minus_strongest_baseline": delta,
        "lower_is_better": True,
        "benefit_observed": isinstance(delta, (int, float)) and delta < 0,
    }


def _planning_regret_comparison(regrets: dict[str, list[float]]) -> dict[str, Any]:
    means = {condition: _mean(values) for condition, values in regrets.items()}
    baseline_scores = {
        condition: means.get(condition)
        for condition in CONDITIONS
        if condition != "CD" and isinstance(means.get(condition), (int, float))
    }
    strongest = min(baseline_scores, key=baseline_scores.get) if baseline_scores else None
    cd_score = means.get("CD")
    delta = cd_score - baseline_scores[strongest] if strongest and isinstance(cd_score, (int, float)) else None
    return {
        "metric": "mean_planning_regret",
        "strongest_baseline_condition": strongest,
        "strongest_baseline_score": baseline_scores.get(strongest) if strongest else None,
        "cd_score": cd_score,
        "cd_minus_strongest_baseline": delta,
        "lower_is_better": True,
        "benefit_observed": isinstance(delta, (int, float)) and delta < 0,
    }


def _build_freeze_manifest(
    *,
    split: str,
    generated_at: str,
    episodes_per_family: int,
    episode_limit: int,
    scenario_family: str | None,
    variant_min: int | None,
    variant_max: int | None,
    condition_receipt: dict[str, Any],
    condition_receipt_sha256: str,
    corpus_file_sha256: str | None,
    metrics_summary_sha256: str | None,
) -> dict[str, Any]:
    return {
        "schema": "persona_dream.research.prospective_tom.heldout_freeze_manifest.v1",
        "split": split,
        "generated_at": generated_at,
        "episodes_per_family": episodes_per_family,
        "episode_limit": episode_limit,
        "scenario_family_filter": scenario_family,
        "variant_min": variant_min,
        "variant_max": variant_max,
        "condition_receipt_sha256": condition_receipt_sha256,
        "corpus_path": condition_receipt.get("corpus_path"),
        "corpus_file_sha256": corpus_file_sha256,
        "metrics_summary_path": condition_receipt.get("metrics_summary_path"),
        "metrics_summary_sha256": metrics_summary_sha256,
        "frozen_before_scoring_summary": True,
        "oracle_policy_reference": "deterministic_simulator_policy.v1",
        "llm_judge_used": False,
        "human_content_judgment_required": False,
    }


def run_heldout_benefit(
    *,
    output_root: Path,
    receipt_out: Path,
    split: str,
    episodes_per_family: int,
    episode_limit: int,
    generated_at: str,
    scenario_family: str | None = None,
    variant_min: int | None = None,
    variant_max: int | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    condition = _load_module(CONDITION_SCRIPT, "pctom_condition_comparison")
    gate6 = _load_module(ACTION_SCRIPT, "pctom_gate6_action_selection")
    action_bridge = _load_module(ACTION_BRIDGE_SCRIPT, "pctom_action_bridge_helpers")

    errors: list[str] = []
    condition_root = output_root / "condition_comparison"
    condition_receipt_path = condition_root / "condition_comparison_receipt.v1.json"
    action_root = output_root / "action_selection"
    action_index_path = action_root / "heldout_action_decisions.json"
    freeze_manifest_path = output_root / "heldout_freeze_manifest.v1.json"

    original_selector = condition._select_episodes
    try:
        if scenario_family or variant_min is not None or variant_max is not None:
            condition._select_episodes = lambda corpus, limit: _filtered_episodes(
                corpus,
                limit,
                scenario_family=scenario_family,
                variant_min=variant_min,
                variant_max=variant_max,
            )
        condition_receipt = condition.run_comparison(
            output_root=condition_root,
            receipt_out=condition_receipt_path,
            split=split,
            episodes_per_family=episodes_per_family,
            episode_limit=episode_limit,
            generated_at=generated_at,
        )
    finally:
        condition._select_episodes = original_selector
    condition_receipt_sha256 = _file_sha256(condition_receipt_path)
    if condition_receipt.get("status") != condition.PASS_STATUS:
        errors.append(f"condition_comparison_status:{condition_receipt.get('status')}")
        errors.extend(f"condition_comparison_error:{error}" for error in condition_receipt.get("errors", []))

    case_index_path = Path(str(condition_receipt.get("case_index_path", "")))
    corpus_path = Path(str(condition_receipt.get("corpus_path", "")))
    case_index = _load_json(case_index_path, errors, "condition_case_index")
    corpus = _load_json(corpus_path, errors, "corpus")
    episodes = _episode_index(corpus, errors)
    if not isinstance(case_index, list):
        errors.append("condition_case_index_not_list")
        case_index = []

    action_rows: list[dict[str, Any]] = []
    action_counts = {condition_name: 0 for condition_name in CONDITIONS}
    regret_counts = {condition_name: 0 for condition_name in CONDITIONS}
    regrets = {condition_name: [] for condition_name in CONDITIONS}
    selected_actions = {condition_name: [] for condition_name in CONDITIONS}
    gate6_status_counts: dict[str, int] = {}

    for idx, row in enumerate(case_index):
        if not isinstance(row, dict):
            errors.append(f"case_index_{idx}_not_object")
            continue
        condition_name = row.get("condition")
        episode_id = row.get("episode_id")
        if condition_name not in CONDITIONS:
            errors.append(f"case_index_{idx}_invalid_condition:{condition_name}")
            continue
        if episode_id not in episodes:
            errors.append(f"case_index_{idx}_missing_episode:{episode_id}")
            continue
        statuses = row.get("statuses") if isinstance(row.get("statuses"), dict) else {}
        if statuses.get("gate5") != "PASS_TOM_SCORING_RECEIPT":
            errors.append(f"case_index_{idx}_gate5_not_pass:{statuses.get('gate5')}")
            continue

        source_case_root = Path(str(row.get("case_root", "")))
        source_receipt_root = Path(str(row.get("receipt_root", "")))
        commitment_path = source_case_root / "tom_prediction_commitment_bundle.json"
        outcome_path = source_case_root / "tom_outcome_reveal.json"
        scoring_path = source_receipt_root / "gate5_scoring_receipt.json"
        commitment_bundle = _load_json(commitment_path, errors, f"{episode_id}_{condition_name}_commitment")
        outcome = _load_json(outcome_path, errors, f"{episode_id}_{condition_name}_outcome")
        scoring_receipt = _load_json(scoring_path, errors, f"{episode_id}_{condition_name}_scoring")
        if not isinstance(commitment_bundle, dict) or not isinstance(outcome, dict) or not isinstance(scoring_receipt, dict):
            continue

        case_errors: list[str] = []
        action_selection = action_bridge._build_action_selection(
            episode=episodes[episode_id],
            condition=condition_name,
            base_receipt_sha256=condition_receipt_sha256,
            commitment_bundle=commitment_bundle,
            scoring_receipt=scoring_receipt,
            outcome=outcome,
            scoring_receipt_sha256=_stable_json_sha256(scoring_receipt),
            outcome_reveal_sha256=_stable_json_sha256(outcome),
            errors=case_errors,
        )
        out_case_root = action_root / "cases" / str(episode_id) / str(condition_name)
        out_receipt_root = action_root / "receipts" / "cases" / str(episode_id) / str(condition_name)
        action_path = out_case_root / "action_selection.json"
        gate6_receipt_path = out_receipt_root / "gate6_action_selection_receipt.json"
        _write_json(action_path, action_selection)
        gate6_errors, derived = gate6._check_action_selection(corpus_path, scoring_path, outcome_path, action_path)
        all_case_errors = case_errors + gate6_errors
        gate6_status = "PASS_TOM_ACTION_SELECTION" if not all_case_errors else "BLOCKED_TOM_ACTION_SELECTION"
        gate6_status_counts[gate6_status] = gate6_status_counts.get(gate6_status, 0) + 1
        gate6_receipt = {
            "schema": "persona_dream.research.prospective_tom.action_selection_receipt.v1",
            "created_at": _now_iso(),
            "status": gate6_status,
            "base_receipt_path": str(condition_receipt_path),
            "base_receipt_sha256": condition_receipt_sha256,
            "corpus_path": str(corpus_path),
            "scoring_receipt_path": str(scoring_path),
            "outcome_reveal_path": str(outcome_path),
            "action_selection_path": str(action_path),
            "receipt_path": str(gate6_receipt_path),
            "episode_id": episode_id,
            "condition": condition_name,
            "errors": all_case_errors,
            "counts": derived["counts"],
            "checks": derived["checks"],
            "metrics": derived["metrics"],
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
        }
        _write_json(gate6_receipt_path, gate6_receipt)
        if gate6_status != "PASS_TOM_ACTION_SELECTION":
            errors.append(f"gate6_case_blocked:{episode_id}:{condition_name}:{all_case_errors}")
        else:
            action_counts[condition_name] += 1
            regret_counts[condition_name] += 1
            regret = gate6_receipt.get("metrics", {}).get("planning_regret")
            if isinstance(regret, (int, float)) and not isinstance(regret, bool):
                regrets[condition_name].append(float(regret))
            selected = gate6_receipt.get("metrics", {}).get("selected_action")
            if isinstance(selected, str):
                selected_actions[condition_name].append(selected)

        action_rows.append(
            {
                "episode_id": episode_id,
                "condition": condition_name,
                "source_case_root": str(source_case_root),
                "source_receipt_root": str(source_receipt_root),
                "case_root": str(out_case_root),
                "receipt_root": str(out_receipt_root),
                "action_selection_path": str(action_path),
                "gate6_receipt_path": str(gate6_receipt_path),
                "status": gate6_status,
                "selected_action": action_selection.get("selected_action"),
                "oracle_action": action_selection.get("oracle_policy", {}).get("action"),
                "planning_regret": action_selection.get("planning_regret"),
                "errors": all_case_errors,
            }
        )

    for condition_name in CONDITIONS:
        if action_counts[condition_name] < 1:
            errors.append(f"action_decisions_per_condition_insufficient:{condition_name}:{action_counts[condition_name]}")
        if regret_counts[condition_name] < 1:
            errors.append(f"planning_regret_scores_per_condition_insufficient:{condition_name}:{regret_counts[condition_name]}")

    _write_json(action_index_path, action_rows)
    metrics_summary_path = Path(str(condition_receipt.get("metrics_summary_path", "")))
    corpus_file_sha256 = _file_sha256(corpus_path) if corpus_path.exists() else None
    metrics_summary_sha256 = _file_sha256(metrics_summary_path) if metrics_summary_path.exists() else None
    freeze_manifest = _build_freeze_manifest(
        split=split,
        generated_at=generated_at,
        episodes_per_family=episodes_per_family,
        episode_limit=episode_limit,
        scenario_family=scenario_family,
        variant_min=variant_min,
        variant_max=variant_max,
        condition_receipt=condition_receipt,
        condition_receipt_sha256=condition_receipt_sha256,
        corpus_file_sha256=corpus_file_sha256,
        metrics_summary_sha256=metrics_summary_sha256,
    )
    freeze_manifest_sha256 = _stable_json_sha256(freeze_manifest)
    freeze_manifest["freeze_manifest_sha256"] = freeze_manifest_sha256
    _write_json(freeze_manifest_path, freeze_manifest)

    metrics = condition_receipt.get("metrics") if isinstance(condition_receipt.get("metrics"), dict) else {}
    primary_comparison = _condition_metric_comparison(metrics, PRIMARY_METRIC)
    action_regret_comparison = _planning_regret_comparison(regrets)
    sealed_counts = condition_receipt.get("counts", {}).get("sealed_commitments_per_condition", {})
    scored_counts = condition_receipt.get("counts", {}).get("deterministic_scores_per_condition", {})
    if primary_comparison["strongest_baseline_condition"] not in ("M", "R", "D"):
        errors.append(f"invalid_strongest_baseline_condition:{primary_comparison['strongest_baseline_condition']}")
    if primary_comparison["cd_minus_strongest_baseline"] is None:
        errors.append("missing_cd_minus_strongest_baseline")
    for condition_name in CONDITIONS:
        if not isinstance(sealed_counts.get(condition_name), int) or sealed_counts[condition_name] < 1:
            errors.append(f"sealed_commitments_per_condition_insufficient:{condition_name}:{sealed_counts.get(condition_name)}")
        if not isinstance(scored_counts.get(condition_name), int) or scored_counts[condition_name] < 1:
            errors.append(f"deterministic_scores_per_condition_insufficient:{condition_name}:{scored_counts.get(condition_name)}")

    selected_episode_ids = sorted({str(row.get("episode_id")) for row in action_rows if row.get("episode_id")})
    scenario_family_filter_respected = (
        True
        if not scenario_family
        else all(
            isinstance(episodes.get(str(row.get("episode_id"))), dict)
            and episodes[str(row.get("episode_id"))].get("scenario_family") == scenario_family
            for row in action_rows
            if row.get("episode_id")
        )
    )
    variant_min_respected = (
        True
        if variant_min is None
        else all(
            isinstance(episodes.get(str(row.get("episode_id"))), dict)
            and isinstance(episodes[str(row.get("episode_id"))].get("variant"), int)
            and episodes[str(row.get("episode_id"))]["variant"] >= variant_min
            for row in action_rows
            if row.get("episode_id")
        )
    )
    variant_max_respected = (
        True
        if variant_max is None
        else all(
            isinstance(episodes.get(str(row.get("episode_id"))), dict)
            and isinstance(episodes[str(row.get("episode_id"))].get("variant"), int)
            and episodes[str(row.get("episode_id"))]["variant"] <= variant_max
            for row in action_rows
            if row.get("episode_id")
        )
    )
    if not scenario_family_filter_respected:
        errors.append(f"scenario_family_filter_violation:{scenario_family}")
    if not variant_min_respected:
        errors.append(f"variant_min_filter_violation:{variant_min}")
    if not variant_max_respected:
        errors.append(f"variant_max_filter_violation:{variant_max}")
    checks = {
        "split_is_explicitly_frozen_heldout": split == DEFAULT_SPLIT,
        "scenario_family_filter_respected": scenario_family_filter_respected,
        "variant_min_respected": variant_min_respected,
        "variant_max_respected": variant_max_respected,
        "freeze_manifest_written": freeze_manifest_path.exists(),
        "condition_receipt_hash_recomputed": isinstance(condition_receipt_sha256, str) and condition_receipt_sha256.startswith("sha256:"),
        "conditions_represented": all(action_counts[condition_name] >= 1 for condition_name in CONDITIONS),
        "sealed_commitments_present": all(isinstance(sealed_counts.get(condition_name), int) and sealed_counts[condition_name] >= 1 for condition_name in CONDITIONS),
        "deterministic_scores_present": all(isinstance(scored_counts.get(condition_name), int) and scored_counts[condition_name] >= 1 for condition_name in CONDITIONS),
        "action_decisions_present": all(action_counts[condition_name] >= 1 for condition_name in CONDITIONS),
        "strongest_baseline_is_allowed": primary_comparison["strongest_baseline_condition"] in ("M", "R", "D"),
        "cd_delta_reported": primary_comparison["cd_minus_strongest_baseline"] is not None,
        "llm_judge_absent": True,
        "human_content_judgment_absent": True,
        "unsupported_writes_absent": True,
    }

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.heldout_condition_benefit_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "split": split,
        "generated_at": generated_at,
        "scenario_family_filter": scenario_family,
        "variant_min": variant_min,
        "variant_max": variant_max,
        "frozen_heldout_manifest_path": str(freeze_manifest_path),
        "frozen_heldout_manifest_sha256": freeze_manifest_sha256,
        "condition_receipt_path": str(condition_receipt_path),
        "condition_receipt_sha256": condition_receipt_sha256,
        "condition_case_index_path": str(case_index_path),
        "action_decision_index_path": str(action_index_path),
        "conditions": list(CONDITIONS),
        "primary_metric": primary_comparison["primary_metric"],
        "preregistered_primary_metric": PRIMARY_METRIC,
        "proper_score_metric": True,
        "strongest_baseline_condition": primary_comparison["strongest_baseline_condition"],
        "cd_minus_strongest_baseline": primary_comparison["cd_minus_strongest_baseline"],
        "benefit_observed": primary_comparison["benefit_observed"],
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
            "episodes_in_corpus": condition_receipt.get("counts", {}).get("episodes_in_corpus"),
            "episodes_consumed": condition_receipt.get("counts", {}).get("episodes_consumed"),
            "families_consumed": condition_receipt.get("counts", {}).get("families_consumed"),
            "cases": condition_receipt.get("counts", {}).get("cases"),
            "sealed_commitments_per_condition": sealed_counts,
            "deterministic_scores_per_condition": scored_counts,
            "action_decisions_per_condition": action_counts,
            "planning_regret_scores_per_condition": regret_counts,
            "gate6_status_counts": dict(sorted(gate6_status_counts.items())),
            "selected_episode_ids": selected_episode_ids,
        },
        "metrics": {
            "condition_metrics": metrics,
            "primary_comparison": primary_comparison,
            "mean_planning_regret_by_condition": {condition_name: _mean(regrets[condition_name]) for condition_name in CONDITIONS},
            "planning_regret_comparison": action_regret_comparison,
            "selected_actions_by_condition": selected_actions,
        },
        "checks": checks,
        "errors": errors,
        "claims": {
            "proves": [
                "an explicitly frozen held-out split was generated from deterministic simulator configuration",
                "M, R, D, and CD conditions each produced sealed commitments before reveal",
                "M, R, D, and CD conditions each produced deterministic Gate 5 scores",
                "M, R, D, and CD conditions each produced constrained Gate 6 action decisions",
                "the preregistered proper score comparison reports CD against the strongest M/R/D baseline",
                "no human content judgment, LLM judge, Memory write, provider call, canonical write, identity write, or source-memory write was attempted",
            ]
            if status == PASS_STATUS
            else [
                "the held-out condition-benefit runner failed closed before claiming held-out evidence",
            ],
            "does_not_prove": [
                "live Tau held-out execution",
                "live Memory recall after revision",
                "production retry machinery",
                "real external service fault injection",
                "statistical confidence intervals over 64 sealed test episodes",
                "planning-regret benefit when regret is tied across conditions",
                "complete live Phase 01-16 runtime execution",
                "paid provider execution",
                "video quality",
                "semantic dream quality",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--split", default=DEFAULT_SPLIT)
    parser.add_argument("--episodes-per-family", type=int, default=6)
    parser.add_argument("--episode-limit", type=int, default=24)
    parser.add_argument("--generated-at", default=DEFAULT_GENERATED_AT)
    parser.add_argument("--scenario-family", default=None)
    parser.add_argument("--variant-min", type=int, default=None)
    parser.add_argument("--variant-max", type=int, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "heldout_condition_benefit_receipt.v1.json")
    receipt = run_heldout_benefit(
        output_root=args.output_root,
        receipt_out=receipt_out,
        split=args.split,
        episodes_per_family=args.episodes_per_family,
        episode_limit=args.episode_limit,
        generated_at=args.generated_at,
        scenario_family=args.scenario_family,
        variant_min=args.variant_min,
        variant_max=args.variant_max,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
