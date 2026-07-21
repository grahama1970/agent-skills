#!/usr/bin/env python3
"""Run deterministic PCTOM-R M/R/D/CD condition comparison instrumentation."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
BUILD_CORPUS_SCRIPT = RESEARCH_ROOT / "scripts" / "build_social_episode_corpus.py"
CHECK_CORPUS_SCRIPT = RESEARCH_ROOT / "scripts" / "check_social_episode_corpus.py"
GATE2_SCRIPT = RESEARCH_ROOT / "scripts" / "check_tom_belief_distributions.py"
GATE3_SCRIPT = RESEARCH_ROOT / "scripts" / "check_counterfactual_branches.py"
GATE4_SCRIPT = RESEARCH_ROOT / "scripts" / "check_tom_prediction_commitments.py"
GATE5_SCRIPT = RESEARCH_ROOT / "scripts" / "reveal_and_score_trial.py"
CONDITIONS = ("M", "R", "D", "CD")
PASS_STATUS = "PASS_PCTOM_CONDITION_COMPARISON"
BLOCKED_STATUS = "BLOCKED_PCTOM_CONDITION_COMPARISON"


CONDITION_PROFILES = {
    "M": {
        "belief_true": 0.45,
        "belief_false": 0.25,
        "belief_unknown": 0.30,
        "action": (1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0),
        "uncertainty": 0.45,
        "method": "memory_only_prior",
    },
    "R": {
        "belief_true": 0.55,
        "belief_false": 0.25,
        "belief_unknown": 0.20,
        "action": (0.50, 0.30, 0.20),
        "uncertainty": 0.35,
        "method": "textual_reflection_prior",
    },
    "D": {
        "belief_true": 0.62,
        "belief_false": 0.23,
        "belief_unknown": 0.15,
        "action": (0.25, 0.50, 0.25),
        "uncertainty": 0.30,
        "method": "single_trajectory_dream_prior",
    },
    "CD": {
        "belief_true": 0.70,
        "belief_false": 0.20,
        "belief_unknown": 0.10,
        "action": (0.20, 0.30, 0.50),
        "uncertainty": 0.22,
        "method": "counterfactual_dream_prior",
    },
}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot_load_module:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _visible_refs(episode: dict[str, Any]) -> list[dict[str, str]]:
    episode_id = episode["episode_id"]
    refs = [{"scope": "social_episode_access", "source_id": f"{episode_id}:information_access_by_agent"}]
    history = episode.get("observable_history") or []
    if history:
        refs.insert(0, {"scope": "social_episode_observation", "source_id": f"{episode_id}:observable_history:0"})
    if len(history) > 1:
        refs.append({"scope": "social_episode_observation", "source_id": f"{episode_id}:observable_history:1"})
    return refs


def _distribution_entries(profile: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"value": "TRUE", "probability": profile["belief_true"]},
        {"value": "FALSE", "probability": profile["belief_false"]},
        {"value": "UNKNOWN", "probability": profile["belief_unknown"]},
    ]


def _action_distribution(actions: list[str], weights: tuple[float, float, float]) -> list[dict[str, Any]]:
    if not actions:
        return [{"value": "UNKNOWN", "probability": 1.0}]
    if len(actions) == 1:
        return [{"value": actions[0], "probability": 1.0}]
    if len(actions) == 2:
        return [
            {"value": actions[0], "probability": 0.55},
            {"value": actions[1], "probability": 0.45},
        ]
    return [{"value": action, "probability": weights[idx]} for idx, action in enumerate(actions[:3])]


def _top_action(distribution: list[dict[str, Any]]) -> str:
    return max(distribution, key=lambda entry: float(entry["probability"]))["value"]


def _label_lookup(episode: dict[str, Any]) -> dict[int, dict[str, Any]]:
    labels: dict[int, dict[str, Any]] = {}
    for label in episode.get("ground_truth_tom_labels", []):
        if isinstance(label, dict) and label.get("perspective_order") in (1, 2):
            labels[int(label["perspective_order"])] = label
    return labels


def _distribution_bundle(episode: dict[str, Any], condition: str) -> dict[str, Any]:
    profile = CONDITION_PROFILES[condition]
    episode_id = episode["episode_id"]
    labels = _label_lookup(episode)
    refs = _visible_refs(episode)
    distributions = []
    for order in (1, 2):
        label = labels[order]
        distributions.append(
            {
                "hypothesis_id": f"{episode_id}-{condition.lower()}-tom{order}-factual",
                "episode_id": episode_id,
                "perspective_order": order,
                "subject": label["subject"],
                "target": label["target"],
                "mental_state_type": label["mental_state_type"],
                "proposition": label["proposition"],
                "distribution": _distribution_entries(profile),
                "evidence_refs": refs,
                "prediction_horizon": "next_action",
                "counterfactual": False,
                "counterfactual_context": None,
                "abstain": False,
                "support_status": "supported",
            }
        )
    first = labels[1]
    distributions.append(
        {
            "hypothesis_id": f"{episode_id}-{condition.lower()}-tom1-counterfactual",
            "episode_id": episode_id,
            "perspective_order": 1,
            "subject": first["subject"],
            "target": first["target"],
            "mental_state_type": first["mental_state_type"],
            "proposition": first["proposition"],
            "distribution": _distribution_entries(profile),
            "evidence_refs": [
                {
                    "scope": "synthetic_counterfactual",
                    "source_id": f"{episode_id}:{condition}:do-counterpart-policy-alternative",
                }
            ],
            "prediction_horizon": "next_action",
            "counterfactual": True,
            "counterfactual_context": {
                "synthetic": True,
                "condition": condition,
                "intervention_id": f"{episode_id}-{condition.lower()}-do-policy-alternative",
            },
            "abstain": False,
            "support_status": "supported",
        }
    )
    return {
        "schema": "persona_dream.research.prospective_tom.tom_belief_distribution_bundle.v1",
        "episode_id": episode_id,
        "sealed": True,
        "outcome_visible": False,
        "canonical_memory_write": False,
        "condition": condition,
        "distributions": distributions,
    }


def _branch_bundle(episode: dict[str, Any], condition: str, action_dist: list[dict[str, Any]]) -> dict[str, Any]:
    episode_id = episode["episode_id"]
    actions = episode.get("allowed_next_actions") or []
    counterfactual_dist = [{"value": action, "probability": 0.0} for action in actions]
    counterfactual_dist.append({"value": "UNKNOWN", "probability": 1.0})
    held_fixed = [
        "counterpart_goals.kai_primary_goal",
        "information_access_by_agent",
        "observable_history",
    ]
    return {
        "schema": "persona_dream.research.prospective_tom.counterfactual_branch_bundle.v1",
        "episode_id": episode_id,
        "outcome_visible": False,
        "canonical_memory_write": False,
        "condition": condition,
        "branches": [
            {
                "branch_id": f"{episode_id}-{condition.lower()}-factual",
                "episode_id": episode_id,
                "branch_type": "factual",
                "synthetic": False,
                "intervention": None,
                "source_evidence_refs": _visible_refs(episode),
                "held_fixed": held_fixed,
                "predicted_bdi_distribution_refs": [
                    f"{episode_id}-{condition.lower()}-tom1-factual",
                    f"{episode_id}-{condition.lower()}-tom2-factual",
                ],
                "predicted_action_distribution": action_dist,
                "expected_observation": f"{condition} factual branch preserves the visible social history.",
                "uncertainty": CONDITION_PROFILES[condition]["uncertainty"],
            },
            {
                "branch_id": f"{episode_id}-{condition.lower()}-counterfactual",
                "episode_id": episode_id,
                "branch_type": "counterfactual",
                "synthetic": True,
                "intervention": {
                    "intervention_id": f"{episode_id}-{condition.lower()}-do-policy-alternative",
                    "episode_id": episode_id,
                    "intervened_variable": "counterpart_policy.expected_actual_next_action",
                    "intervened_value": "UNKNOWN",
                    "held_fixed": held_fixed,
                    "expected_observation": "The counterpart policy is replaced by an unspecified alternative.",
                    "synthetic": True,
                },
                "source_evidence_refs": _visible_refs(episode),
                "held_fixed": held_fixed,
                "predicted_bdi_distribution_refs": [f"{episode_id}-{condition.lower()}-tom1-counterfactual"],
                "predicted_action_distribution": counterfactual_dist,
                "expected_observation": f"{condition} counterfactual branch is synthetic and not literal history.",
                "uncertainty": min(1.0, CONDITION_PROFILES[condition]["uncertainty"] + 0.15),
            },
        ],
    }


def _commitment_bundle(
    episode: dict[str, Any],
    condition: str,
    distribution_bundle: dict[str, Any],
    branch_bundle: dict[str, Any],
    action_dist: list[dict[str, Any]],
    sealed_at: str,
) -> dict[str, Any]:
    episode_id = episode["episode_id"]
    prediction_payload = {
        "episode_id": episode_id,
        "condition": condition,
        "outcome_visible": False,
        "branch_refs": [
            f"{episode_id}-{condition.lower()}-factual",
            f"{episode_id}-{condition.lower()}-counterfactual",
        ],
        "belief_distribution_refs": [
            f"{episode_id}-{condition.lower()}-tom1-factual",
            f"{episode_id}-{condition.lower()}-tom2-factual",
            f"{episode_id}-{condition.lower()}-tom1-counterfactual",
        ],
        "evidence_refs": _visible_refs(episode),
        "predicted_next_action_distribution": action_dist,
        "abstain": False,
        "condition_method": CONDITION_PROFILES[condition]["method"],
    }
    model_receipts = [
        {
            "receipt_id": f"{episode_id}-{condition.lower()}-deterministic-condition-prior",
            "model": "deterministic_pctom_condition_prior.v1",
            "condition": condition,
            "live_call_performed": False,
            "mocked": False,
            "notes": "No LLM judge or provider call; deterministic protocol instrumentation.",
        }
    ]
    evidence_bundle = {
        "distribution_bundle_sha256": _stable_json_sha256(distribution_bundle),
        "branch_bundle_sha256": _stable_json_sha256(branch_bundle),
        "branch_refs": prediction_payload["branch_refs"],
        "belief_distribution_refs": prediction_payload["belief_distribution_refs"],
        "source_evidence_refs": _visible_refs(episode),
    }
    commitment = {
        "prediction_id": f"{episode_id}-{condition.lower()}-prediction",
        "episode_id": episode_id,
        "condition": condition,
        "sealed_at": sealed_at,
        "outcome_visible": False,
        "canonical_memory_write": False,
        "prediction_payload": prediction_payload,
        "prediction_payload_sha256": _stable_json_sha256(prediction_payload),
        "model_receipts": model_receipts,
        "model_receipts_sha256": _stable_json_sha256(model_receipts),
        "evidence_bundle": evidence_bundle,
        "evidence_bundle_sha256": _stable_json_sha256(evidence_bundle),
    }
    return {
        "schema": "persona_dream.research.prospective_tom.tom_prediction_commitment_bundle.v1",
        "episode_id": episode_id,
        "sealed": True,
        "outcome_visible": False,
        "canonical_memory_write": False,
        "commitments": [commitment],
    }


def _outcome_reveal(
    episode: dict[str, Any],
    condition: str,
    commitment_bundle: dict[str, Any],
    action_dist: list[dict[str, Any]],
    revealed_at: str,
) -> dict[str, Any]:
    episode_id = episode["episode_id"]
    labels = _label_lookup(episode)
    hidden_state_labels = {
        f"{episode_id}-{condition.lower()}-tom1-factual": labels[1]["value"],
        f"{episode_id}-{condition.lower()}-tom2-factual": labels[2]["value"],
    }
    prediction_id = commitment_bundle["commitments"][0]["prediction_id"]
    return {
        "schema": "persona_dream.research.prospective_tom.tom_outcome_reveal.v1",
        "outcome_id": f"{episode_id}-{condition.lower()}-outcome",
        "episode_id": episode_id,
        "prediction_id": prediction_id,
        "revealed_at": revealed_at,
        "outcome_visible": True,
        "reveal_complete": True,
        "canonical_memory_write": False,
        "actual_next_action": episode["actual_next_action"],
        "hidden_state_labels": hidden_state_labels,
        "factual_branch_id": f"{episode_id}-{condition.lower()}-factual",
        "literal_history_branch_ids": [f"{episode_id}-{condition.lower()}-factual"],
        "equivalent_formulation_checks": [
            {
                "check_id": f"{episode_id}-{condition.lower()}-equivalent-action",
                "formulation_id": "same-question-paraphrase-001",
                "prediction_id": prediction_id,
                "expected_top_action": _top_action(action_dist),
            }
        ],
    }


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _summarize(case_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_condition: dict[str, dict[str, list[float]]] = {
        condition: {"action_brier": [], "action_log_loss": [], "belief_brier": [], "belief_log_loss": []}
        for condition in CONDITIONS
    }
    for row in case_rows:
        condition = row["condition"]
        metrics = row["scoring_metrics"]
        action = metrics.get("action") or {}
        if isinstance(action.get("brier"), (int, float)):
            by_condition[condition]["action_brier"].append(float(action["brier"]))
        if isinstance(action.get("log_loss"), (int, float)):
            by_condition[condition]["action_log_loss"].append(float(action["log_loss"]))
        for belief in metrics.get("belief_scores") or []:
            if isinstance(belief.get("brier"), (int, float)):
                by_condition[condition]["belief_brier"].append(float(belief["brier"]))
            if isinstance(belief.get("log_loss"), (int, float)):
                by_condition[condition]["belief_log_loss"].append(float(belief["log_loss"]))
    summary: dict[str, Any] = {}
    for condition, values in by_condition.items():
        summary[condition] = {
            "cases": len([row for row in case_rows if row["condition"] == condition]),
            "mean_action_brier": _mean(values["action_brier"]),
            "mean_action_log_loss": _mean(values["action_log_loss"]),
            "mean_belief_brier": _mean(values["belief_brier"]),
            "mean_belief_log_loss": _mean(values["belief_log_loss"]),
        }
    baseline_scores = {
        condition: row["mean_action_brier"]
        for condition, row in summary.items()
        if condition != "CD" and isinstance(row.get("mean_action_brier"), (int, float))
    }
    strongest = min(baseline_scores, key=baseline_scores.get) if baseline_scores else None
    cd_score = summary.get("CD", {}).get("mean_action_brier")
    summary["comparison"] = {
        "primary_metric": "mean_action_brier",
        "strongest_baseline_condition": strongest,
        "strongest_baseline_mean_action_brier": baseline_scores.get(strongest) if strongest else None,
        "cd_mean_action_brier": cd_score,
        "cd_minus_strongest_baseline": (cd_score - baseline_scores[strongest])
        if strongest and isinstance(cd_score, (int, float))
        else None,
        "lower_is_better": True,
    }
    return summary


def _select_episodes(corpus: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    episodes = list(corpus.get("episodes") or [])
    if limit <= 0 or limit >= len(episodes):
        return episodes
    by_family: dict[str, list[dict[str, Any]]] = {}
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        family = str(episode.get("scenario_family") or "unknown")
        by_family.setdefault(family, []).append(episode)
    selected: list[dict[str, Any]] = []
    family_names = sorted(by_family)
    round_index = 0
    while len(selected) < limit:
        added = False
        for family in family_names:
            family_episodes = by_family[family]
            if round_index < len(family_episodes):
                selected.append(family_episodes[round_index])
                added = True
                if len(selected) >= limit:
                    break
        if not added:
            break
        round_index += 1
    return selected


def run_comparison(
    *,
    output_root: Path,
    receipt_out: Path,
    split: str,
    episodes_per_family: int,
    episode_limit: int,
) -> dict[str, Any]:
    started = time.monotonic()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts_root = output_root / "artifacts"
    receipts_root = output_root / "receipts"
    corpus_path = artifacts_root / "social_episode_corpus.v1.json"
    corpus_build_receipt_path = receipts_root / "social_episode_corpus_build_receipt.json"
    corpus_check_receipt_path = receipts_root / "social_episode_corpus_check_receipt.json"

    build_corpus = _load_module(BUILD_CORPUS_SCRIPT, "persona_dream_pctom_build_corpus")
    check_corpus = _load_module(CHECK_CORPUS_SCRIPT, "persona_dream_pctom_check_corpus")
    gate2 = _load_module(GATE2_SCRIPT, "persona_dream_pctom_gate2")
    gate3 = _load_module(GATE3_SCRIPT, "persona_dream_pctom_gate3")
    gate4 = _load_module(GATE4_SCRIPT, "persona_dream_pctom_gate4")
    gate5 = _load_module(GATE5_SCRIPT, "persona_dream_pctom_gate5")

    corpus = build_corpus.build_corpus(split, episodes_per_family)
    _write_json(corpus_path, corpus)
    corpus_build_receipt = {
        "schema": "persona_dream.research.prospective_tom.social_episode_corpus_build_receipt.v1",
        "created_at": _now_iso(),
        "status": "PASS_SOCIAL_EPISODE_CORPUS_BUILT",
        "output": str(corpus_path),
        "corpus_sha256": _stable_json_sha256(corpus),
        "episodes_sha256": corpus["episodes_sha256"],
        "split": split,
        "episode_count": corpus["episode_count"],
        "family_counts": corpus["family_counts"],
        "mocked": False,
        "live": False,
        "fixture_backed": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
    }
    _write_json(corpus_build_receipt_path, corpus_build_receipt)
    corpus_check_receipt = check_corpus.build_receipt(
        corpus_path,
        corpus_check_receipt_path,
        expect_total=episodes_per_family * 4,
        expect_per_family=episodes_per_family,
    )

    errors: list[str] = []
    if corpus_check_receipt.get("status") != "PASS_SOCIAL_EPISODE_CORPUS":
        errors.append(f"corpus_check_status:{corpus_check_receipt.get('status')}")
        errors.extend(f"corpus_check_error:{error}" for error in corpus_check_receipt.get("errors", []))

    selected = _select_episodes(corpus, episode_limit)
    case_rows: list[dict[str, Any]] = []
    sealed_counts = {condition: 0 for condition in CONDITIONS}
    scored_counts = {condition: 0 for condition in CONDITIONS}
    status_counts: dict[str, int] = {}
    for episode_index, episode in enumerate(selected):
        for condition_index, condition in enumerate(CONDITIONS):
            profile = CONDITION_PROFILES[condition]
            action_dist = _action_distribution(episode["allowed_next_actions"], profile["action"])
            sealed_at = f"2026-07-21T03:{episode_index:02d}:{condition_index:02d}Z"
            revealed_at = f"2026-07-21T04:{episode_index:02d}:{condition_index:02d}Z"
            case_root = artifacts_root / "cases" / episode["episode_id"] / condition
            case_receipts = receipts_root / "cases" / episode["episode_id"] / condition
            distribution_path = case_root / "tom_belief_distribution_bundle.json"
            branch_path = case_root / "counterfactual_branch_bundle.json"
            commitment_path = case_root / "tom_prediction_commitment_bundle.json"
            outcome_path = case_root / "tom_outcome_reveal.json"
            gate2_receipt_path = case_receipts / "gate2_distribution_check_receipt.json"
            gate3_receipt_path = case_receipts / "gate3_branch_check_receipt.json"
            gate4_receipt_path = case_receipts / "gate4_commitment_check_receipt.json"
            gate5_receipt_path = case_receipts / "gate5_scoring_receipt.json"

            distribution_bundle = _distribution_bundle(episode, condition)
            branch_bundle = _branch_bundle(episode, condition, action_dist)
            commitment_bundle = _commitment_bundle(
                episode,
                condition,
                distribution_bundle,
                branch_bundle,
                action_dist,
                sealed_at,
            )
            outcome = _outcome_reveal(episode, condition, commitment_bundle, action_dist, revealed_at)
            _write_json(distribution_path, distribution_bundle)
            _write_json(branch_path, branch_bundle)
            _write_json(commitment_path, commitment_bundle)
            _write_json(outcome_path, outcome)

            receipts = {
                "gate2": gate2.build_receipt(corpus_path, distribution_path, gate2_receipt_path),
                "gate3": gate3.build_receipt(corpus_path, distribution_path, branch_path, gate3_receipt_path),
                "gate4": gate4.build_receipt(corpus_path, distribution_path, branch_path, commitment_path, gate4_receipt_path),
                "gate5": gate5.build_receipt(
                    corpus_path,
                    distribution_path,
                    branch_path,
                    commitment_path,
                    outcome_path,
                    gate5_receipt_path,
                ),
            }
            case_statuses = {name: receipt.get("status") for name, receipt in receipts.items()}
            for status in case_statuses.values():
                status_counts[str(status)] = status_counts.get(str(status), 0) + 1
            if case_statuses["gate4"] == "PASS_TOM_PREDICTION_COMMITMENTS":
                sealed_counts[condition] += 1
            if case_statuses["gate5"] == "PASS_TOM_SCORING_RECEIPT":
                scored_counts[condition] += 1
            for name, receipt in receipts.items():
                if not str(receipt.get("status", "")).startswith("PASS_"):
                    errors.append(f"{episode['episode_id']}:{condition}:{name}:{receipt.get('status')}")
                    errors.extend(f"{episode['episode_id']}:{condition}:{name}_error:{error}" for error in receipt.get("errors", []))
            case_rows.append(
                {
                    "episode_id": episode["episode_id"],
                    "condition": condition,
                    "prediction_id": commitment_bundle["commitments"][0]["prediction_id"],
                    "actual_next_action": episode["actual_next_action"],
                    "top_action": _top_action(action_dist),
                    "case_root": str(case_root),
                    "receipt_root": str(case_receipts),
                    "statuses": case_statuses,
                    "scoring_metrics": receipts["gate5"].get("metrics", {}),
                }
            )

    if set(sealed_counts) != set(CONDITIONS) or any(count < 1 for count in sealed_counts.values()):
        errors.append(f"sealed_commitments_per_condition_insufficient:{sealed_counts}")
    if set(scored_counts) != set(CONDITIONS) or any(count < 1 for count in scored_counts.values()):
        errors.append(f"deterministic_scores_per_condition_insufficient:{scored_counts}")
    summary = _summarize(case_rows)
    case_index_path = artifacts_root / "condition_case_index.json"
    metrics_path = artifacts_root / "condition_metrics_summary.json"
    _write_json(case_index_path, case_rows)
    _write_json(metrics_path, summary)

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.condition_comparison_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "split": split,
        "corpus_path": str(corpus_path),
        "corpus_build_receipt_path": str(corpus_build_receipt_path),
        "corpus_check_receipt_path": str(corpus_check_receipt_path),
        "case_index_path": str(case_index_path),
        "metrics_summary_path": str(metrics_path),
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
            "episodes_in_corpus": corpus["episode_count"],
            "episodes_consumed": len(selected),
            "families_consumed": len({episode.get("scenario_family") for episode in selected}),
            "conditions": len(CONDITIONS),
            "cases": len(case_rows),
            "sealed_commitments_per_condition": sealed_counts,
            "deterministic_scores_per_condition": scored_counts,
            "status_counts": dict(sorted(status_counts.items())),
        },
        "metrics": summary,
        "errors": errors,
        "claims": {
            "proves": [
                "a calibration social episode corpus was generated and accepted by the Gate 1 checker",
                "M, R, D, and CD condition commitments were sealed before deterministic outcome reveal",
                "each condition has at least one deterministic Gate 5 score",
                "Brier and log-loss metrics were aggregated by condition",
                "no Memory write, provider call, Tau call, canonical memory write, identity write, source-memory write, or human content judgment was required",
            ]
            if status == PASS_STATUS
            else [
                "the condition comparison runner produced an inspectable fail-closed receipt",
            ],
            "does_not_prove": [
                "live model prediction benefit",
                "paid provider execution",
                "external service fault injection",
                "production retry machinery",
                "longitudinal recall after revision",
                "complete live Phase 01-16 runtime execution",
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
    parser.add_argument("--split", default="calibration")
    parser.add_argument("--episodes-per-family", type=int, default=6)
    parser.add_argument("--episode-limit", type=int, default=4)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "condition_comparison_receipt.v1.json")
    receipt = run_comparison(
        output_root=args.output_root,
        receipt_out=receipt_out,
        split=args.split,
        episodes_per_family=args.episodes_per_family,
        episode_limit=args.episode_limit,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
