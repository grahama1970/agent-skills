#!/usr/bin/env python3
"""Reveal and deterministically score a PCTOM-R Gate 5 prospective ToM trial."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_TOM_SCORING_RECEIPT"
BLOCKED_STATUS = "BLOCKED_TOM_SCORING_RECEIPT"
EPSILON = 1e-6
MIN_PROBABILITY = 1e-12


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


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


def _parse_time(value: Any, prefix: str, errors: list[str]) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{prefix}_missing_timestamp")
        return None
    try:
        normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = dt.datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc)
    except Exception:
        errors.append(f"{prefix}_invalid_timestamp:{value}")
        return None


def _episode_index(corpus: Any, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(corpus, dict):
        errors.append("corpus_not_object")
        return {}
    episodes = corpus.get("episodes")
    if not isinstance(episodes, list):
        errors.append("corpus_episodes_not_list")
        return {}
    index: dict[str, dict[str, Any]] = {}
    for idx, episode in enumerate(episodes):
        if not isinstance(episode, dict):
            errors.append(f"episode_{idx}_not_object")
            continue
        episode_id = episode.get("episode_id")
        if not isinstance(episode_id, str) or not episode_id:
            errors.append(f"episode_{idx}_missing_episode_id")
            continue
        index[episode_id] = episode
    return index


def _distribution_index(bundle: Any, errors: list[str]) -> tuple[str | None, dict[str, dict[str, Any]]]:
    if not isinstance(bundle, dict):
        errors.append("distribution_bundle_not_object")
        return None, {}
    episode_id = bundle.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        errors.append("distribution_bundle_missing_episode_id")
        episode_id = None
    if bundle.get("schema") != "persona_dream.research.prospective_tom.tom_belief_distribution_bundle.v1":
        errors.append(f"invalid_distribution_bundle_schema:{bundle.get('schema')}")
    if bundle.get("sealed") is not True:
        errors.append("distribution_bundle_not_sealed")
    if bundle.get("outcome_visible") is not False:
        errors.append("distribution_bundle_outcome_visible_not_false")
    index: dict[str, dict[str, Any]] = {}
    for idx, distribution in enumerate(bundle.get("distributions") or []):
        if not isinstance(distribution, dict):
            errors.append(f"distribution_{idx}_not_object")
            continue
        hypothesis_id = distribution.get("hypothesis_id")
        if not isinstance(hypothesis_id, str) or not hypothesis_id:
            errors.append(f"distribution_{idx}_missing_hypothesis_id")
            continue
        index[hypothesis_id] = distribution
    return episode_id, index


def _branch_index(bundle: Any, errors: list[str]) -> tuple[str | None, dict[str, dict[str, Any]]]:
    if not isinstance(bundle, dict):
        errors.append("branch_bundle_not_object")
        return None, {}
    episode_id = bundle.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        errors.append("branch_bundle_missing_episode_id")
        episode_id = None
    if bundle.get("schema") != "persona_dream.research.prospective_tom.counterfactual_branch_bundle.v1":
        errors.append(f"invalid_branch_bundle_schema:{bundle.get('schema')}")
    if bundle.get("outcome_visible") is not False:
        errors.append("branch_bundle_outcome_visible_not_false")
    index: dict[str, dict[str, Any]] = {}
    for idx, branch in enumerate(bundle.get("branches") or []):
        if not isinstance(branch, dict):
            errors.append(f"branch_{idx}_not_object")
            continue
        branch_id = branch.get("branch_id")
        if not isinstance(branch_id, str) or not branch_id:
            errors.append(f"branch_{idx}_missing_branch_id")
            continue
        index[branch_id] = branch
    return episode_id, index


def _commitment_index(bundle: Any, errors: list[str]) -> tuple[str | None, dict[str, dict[str, Any]]]:
    if not isinstance(bundle, dict):
        errors.append("commitment_bundle_not_object")
        return None, {}
    episode_id = bundle.get("episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        errors.append("commitment_bundle_missing_episode_id")
        episode_id = None
    if bundle.get("schema") != "persona_dream.research.prospective_tom.tom_prediction_commitment_bundle.v1":
        errors.append(f"invalid_commitment_bundle_schema:{bundle.get('schema')}")
    if bundle.get("sealed") is not True:
        errors.append("commitment_bundle_not_sealed")
    if bundle.get("outcome_visible") is not False:
        errors.append("commitment_bundle_outcome_visible_not_false")
    if bundle.get("canonical_memory_write") is not False:
        errors.append("commitment_bundle_canonical_memory_write_not_false")
    index: dict[str, dict[str, Any]] = {}
    for idx, commitment in enumerate(bundle.get("commitments") or []):
        if not isinstance(commitment, dict):
            errors.append(f"commitment_{idx}_not_object")
            continue
        prediction_id = commitment.get("prediction_id")
        if not isinstance(prediction_id, str) or not prediction_id:
            errors.append(f"commitment_{idx}_missing_prediction_id")
            continue
        index[prediction_id] = commitment
    return episode_id, index


def _check_commitment_hashes(commitment: dict[str, Any], errors: list[str]) -> None:
    payload = commitment.get("prediction_payload")
    model_receipts = commitment.get("model_receipts")
    evidence_bundle = commitment.get("evidence_bundle")
    if not isinstance(payload, dict):
        errors.append("commitment_prediction_payload_not_object")
        payload = {}
    if not isinstance(model_receipts, list):
        errors.append("commitment_model_receipts_not_list")
        model_receipts = []
    if not isinstance(evidence_bundle, dict):
        errors.append("commitment_evidence_bundle_not_object")
        evidence_bundle = {}
    if commitment.get("prediction_payload_sha256") != _stable_json_sha256(payload):
        errors.append("commitment_prediction_payload_sha256_mismatch")
    if commitment.get("model_receipts_sha256") != _stable_json_sha256(model_receipts):
        errors.append("commitment_model_receipts_sha256_mismatch")
    if commitment.get("evidence_bundle_sha256") != _stable_json_sha256(evidence_bundle):
        errors.append("commitment_evidence_bundle_sha256_mismatch")
    if commitment.get("outcome_visible") is not False:
        errors.append("commitment_outcome_visible_not_false")
    if commitment.get("canonical_memory_write") is not False:
        errors.append("commitment_canonical_memory_write_not_false")
    if commitment.get("revision_of") not in (None, ""):
        errors.append("commitment_revision_of_not_allowed")
    if commitment.get("edited_after_reveal") not in (None, False):
        errors.append("commitment_edited_after_reveal_not_false")


def _distribution_sum(entries: Any, prefix: str, errors: list[str]) -> dict[str, float]:
    if not isinstance(entries, list) or not entries:
        errors.append(f"{prefix}_distribution_not_nonempty_list")
        return {}
    probs: dict[str, float] = {}
    total = 0.0
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"{prefix}_distribution_{idx}_not_object")
            continue
        value = entry.get("value")
        probability = entry.get("probability")
        if not isinstance(value, str) or not value:
            errors.append(f"{prefix}_distribution_{idx}_missing_value")
            continue
        if not isinstance(probability, (int, float)) or isinstance(probability, bool):
            errors.append(f"{prefix}_distribution_{idx}_invalid_probability:{probability}")
            continue
        if probability < 0 or probability > 1:
            errors.append(f"{prefix}_distribution_{idx}_probability_out_of_range:{probability}")
        probs[value] = float(probability)
        total += float(probability)
    if abs(total - 1.0) > EPSILON:
        errors.append(f"{prefix}_distribution_sum:{total:.6f}")
    return probs


def _score_categorical(entries: Any, actual: str, prefix: str, errors: list[str]) -> dict[str, Any]:
    probs = _distribution_sum(entries, prefix, errors)
    if not probs:
        return {"brier": None, "log_loss": None, "actual_probability": None, "top_value": None, "top_correct": False}
    if actual not in probs:
        errors.append(f"{prefix}_actual_value_missing_from_distribution:{actual}")
    labels = set(probs) | {actual}
    brier = sum((probs.get(label, 0.0) - (1.0 if label == actual else 0.0)) ** 2 for label in labels)
    actual_probability = max(probs.get(actual, 0.0), MIN_PROBABILITY)
    top_value = max(probs.items(), key=lambda item: item[1])[0]
    return {
        "brier": brier,
        "log_loss": -math.log(actual_probability),
        "actual_probability": probs.get(actual, 0.0),
        "top_value": top_value,
        "top_correct": top_value == actual,
    }


def _calibration(scored_items: list[dict[str, Any]]) -> dict[str, Any]:
    bins = [
        ("0.00-0.50", 0.0, 0.5),
        ("0.50-0.75", 0.5, 0.75),
        ("0.75-1.00", 0.75, 1.0000001),
    ]
    bucket_rows = []
    ece = 0.0
    total = len(scored_items)
    for name, lower, upper in bins:
        items = [item for item in scored_items if lower <= item["confidence"] < upper]
        if not items:
            bucket_rows.append({"bucket": name, "count": 0, "accuracy": None, "mean_confidence": None})
            continue
        accuracy = sum(1.0 if item["correct"] else 0.0 for item in items) / len(items)
        mean_confidence = sum(item["confidence"] for item in items) / len(items)
        ece += (len(items) / total) * abs(accuracy - mean_confidence) if total else 0.0
        bucket_rows.append({"bucket": name, "count": len(items), "accuracy": accuracy, "mean_confidence": mean_confidence})
    return {"expected_calibration_error": ece, "buckets": bucket_rows}


def _total_variation(a_entries: Any, b_entries: Any, errors: list[str]) -> float | None:
    a = _distribution_sum(a_entries, "counterfactual_factual_action", errors)
    b = _distribution_sum(b_entries, "counterfactual_intervention_action", errors)
    if not a or not b:
        return None
    labels = set(a) | set(b)
    return 0.5 * sum(abs(a.get(label, 0.0) - b.get(label, 0.0)) for label in labels)


def _score_trial(
    corpus_path: Path,
    distributions_path: Path,
    branches_path: Path,
    commitments_path: Path,
    outcome_path: Path,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    corpus = _load_json(corpus_path, errors, "corpus")
    distribution_bundle = _load_json(distributions_path, errors, "distribution_bundle")
    branch_bundle = _load_json(branches_path, errors, "branch_bundle")
    commitment_bundle = _load_json(commitments_path, errors, "commitment_bundle")
    outcome = _load_json(outcome_path, errors, "outcome_reveal")

    episodes = _episode_index(corpus, errors)
    distribution_episode_id, distributions = _distribution_index(distribution_bundle, errors)
    branch_episode_id, branches = _branch_index(branch_bundle, errors)
    commitment_episode_id, commitments = _commitment_index(commitment_bundle, errors)

    counts = {
        "commitments_scored": 0,
        "action_scores": 0,
        "belief_scores": 0,
        "first_order_scores": 0,
        "second_order_scores": 0,
        "equivalent_formulation_checks": 0,
        "counterfactual_pairs": 0,
        "literal_history_branch_ids": 0,
        "synthetic_literal_history_branch_ids": 0,
    }
    metrics: dict[str, Any] = {
        "action": None,
        "belief_scores": [],
        "calibration": None,
        "risk_coverage": None,
        "consistency": None,
        "counterfactual": None,
    }
    checks = {
        "outcome_revealed_after_seal": False,
        "commitment_hashes_recomputed": True,
        "actual_action_allowed": False,
        "action_scored": False,
        "first_order_scored": False,
        "second_order_scored": False,
        "calibration_computed": False,
        "consistency_computed": False,
        "counterfactual_metrics_computed": False,
        "false_history_rate_zero": False,
        "no_canonical_memory_write": False,
    }

    if not isinstance(outcome, dict):
        errors.append("outcome_reveal_not_object")
        return errors, {"counts": counts, "metrics": metrics, "checks": checks}
    if outcome.get("schema") != "persona_dream.research.prospective_tom.tom_outcome_reveal.v1":
        errors.append(f"invalid_outcome_reveal_schema:{outcome.get('schema')}")
    if outcome.get("outcome_visible") is not True:
        errors.append("outcome_reveal_outcome_visible_not_true")
    if outcome.get("reveal_complete") is not True:
        errors.append("outcome_reveal_not_complete")
    if outcome.get("canonical_memory_write") is not False:
        errors.append("outcome_reveal_canonical_memory_write_not_false")
    checks["no_canonical_memory_write"] = outcome.get("canonical_memory_write") is False

    episode_id = outcome.get("episode_id")
    prediction_id = outcome.get("prediction_id")
    if not isinstance(episode_id, str) or not episode_id:
        errors.append("outcome_reveal_missing_episode_id")
        episode = None
    else:
        episode = episodes.get(episode_id)
        if episode is None:
            errors.append(f"outcome_episode_not_in_corpus:{episode_id}")
    if episode_id not in {distribution_episode_id, branch_episode_id, commitment_episode_id}:
        errors.append(f"episode_mismatch:{episode_id}:{distribution_episode_id}:{branch_episode_id}:{commitment_episode_id}")
    if not isinstance(prediction_id, str) or not prediction_id:
        errors.append("outcome_reveal_missing_prediction_id")
        commitment = None
    else:
        commitment = commitments.get(prediction_id)
        if commitment is None:
            errors.append(f"outcome_prediction_not_in_commitments:{prediction_id}")

    actual_next_action = outcome.get("actual_next_action")
    allowed_actions = set(episode.get("allowed_next_actions") or []) if episode else set()
    if not isinstance(actual_next_action, str) or not actual_next_action:
        errors.append("outcome_reveal_missing_actual_next_action")
    elif allowed_actions and actual_next_action not in allowed_actions:
        errors.append(f"outcome_actual_next_action_not_allowed:{actual_next_action}")
    else:
        checks["actual_action_allowed"] = True

    if commitment:
        before_error_count = len(errors)
        _check_commitment_hashes(commitment, errors)
        checks["commitment_hashes_recomputed"] = len(errors) == before_error_count
        sealed_at = _parse_time(commitment.get("sealed_at"), "commitment_sealed_at", errors)
        revealed_at = _parse_time(outcome.get("revealed_at"), "outcome_revealed_at", errors)
        if sealed_at and revealed_at:
            if revealed_at <= sealed_at:
                errors.append(f"outcome_revealed_not_after_seal:{outcome.get('revealed_at')}:{commitment.get('sealed_at')}")
            else:
                checks["outcome_revealed_after_seal"] = True

        payload = commitment.get("prediction_payload") if isinstance(commitment.get("prediction_payload"), dict) else {}
        action_score = _score_categorical(payload.get("predicted_next_action_distribution"), str(actual_next_action), "action", errors)
        metrics["action"] = action_score
        if action_score["brier"] is not None:
            counts["action_scores"] += 1
            checks["action_scored"] = True

        scored_items: list[dict[str, Any]] = []
        if action_score["top_value"] is not None:
            scored_items.append({
                "kind": "action",
                "confidence": float(action_score["actual_probability"] or 0.0),
                "correct": bool(action_score["top_correct"]),
            })

        hidden_state_labels = outcome.get("hidden_state_labels")
        if not isinstance(hidden_state_labels, dict):
            errors.append("outcome_hidden_state_labels_not_object")
            hidden_state_labels = {}
        for dist_ref in payload.get("belief_distribution_refs") or []:
            distribution = distributions.get(dist_ref)
            if not distribution:
                errors.append(f"unresolved_belief_distribution_ref:{dist_ref}")
                continue
            if distribution.get("counterfactual") is True:
                continue
            actual_label = hidden_state_labels.get(dist_ref)
            if not isinstance(actual_label, str) or not actual_label:
                errors.append(f"missing_hidden_state_label:{dist_ref}")
                continue
            belief_score = _score_categorical(distribution.get("distribution"), actual_label, f"belief_{dist_ref}", errors)
            belief_score.update({
                "hypothesis_id": dist_ref,
                "perspective_order": distribution.get("perspective_order"),
                "actual_label": actual_label,
            })
            metrics["belief_scores"].append(belief_score)
            if belief_score["brier"] is not None:
                counts["belief_scores"] += 1
                if distribution.get("perspective_order") == 1:
                    counts["first_order_scores"] += 1
                if distribution.get("perspective_order") == 2:
                    counts["second_order_scores"] += 1
                scored_items.append({
                    "kind": f"belief:{dist_ref}",
                    "confidence": float(belief_score["actual_probability"] or 0.0),
                    "correct": bool(belief_score["top_correct"]),
                })
        checks["first_order_scored"] = counts["first_order_scores"] > 0
        checks["second_order_scored"] = counts["second_order_scores"] > 0

        if scored_items:
            metrics["calibration"] = _calibration(scored_items)
            checks["calibration_computed"] = True
        abstain = payload.get("abstain")
        covered = abstain is False
        metrics["risk_coverage"] = {
            "coverage": 1.0 if covered else 0.0,
            "selective_accuracy": 1.0 if covered and action_score["top_correct"] else 0.0,
            "abstained": abstain is True,
        }

        eq_checks = outcome.get("equivalent_formulation_checks")
        consistency_pass = 0
        if isinstance(eq_checks, list) and eq_checks:
            for idx, check in enumerate(eq_checks):
                if not isinstance(check, dict):
                    errors.append(f"equivalent_formulation_{idx}_not_object")
                    continue
                counts["equivalent_formulation_checks"] += 1
                if check.get("prediction_id") != prediction_id:
                    errors.append(f"equivalent_formulation_{idx}_prediction_mismatch:{check.get('prediction_id')}:{prediction_id}")
                    continue
                if check.get("expected_top_action") == action_score["top_value"]:
                    consistency_pass += 1
                else:
                    errors.append(f"equivalent_formulation_{idx}_top_action_mismatch:{check.get('expected_top_action')}:{action_score['top_value']}")
            metrics["consistency"] = {
                "checks": counts["equivalent_formulation_checks"],
                "passed": consistency_pass,
                "score": consistency_pass / counts["equivalent_formulation_checks"] if counts["equivalent_formulation_checks"] else None,
            }
            checks["consistency_computed"] = counts["equivalent_formulation_checks"] > 0
        else:
            errors.append("equivalent_formulation_checks_missing")

        branch_refs = [ref for ref in payload.get("branch_refs") or [] if isinstance(ref, str)]
        factual_branches = [branches[ref] for ref in branch_refs if ref in branches and branches[ref].get("branch_type") == "factual"]
        counterfactual_branches = [branches[ref] for ref in branch_refs if ref in branches and branches[ref].get("branch_type") == "counterfactual"]
        tv_values: list[float] = []
        for factual in factual_branches:
            for counterfactual in counterfactual_branches:
                tv = _total_variation(factual.get("predicted_action_distribution"), counterfactual.get("predicted_action_distribution"), errors)
                if tv is not None:
                    tv_values.append(tv)
                    counts["counterfactual_pairs"] += 1
        literal_history_branch_ids = outcome.get("literal_history_branch_ids")
        if not isinstance(literal_history_branch_ids, list):
            errors.append("literal_history_branch_ids_not_list")
            literal_history_branch_ids = []
        synthetic_literal = 0
        for branch_id in literal_history_branch_ids:
            counts["literal_history_branch_ids"] += 1
            branch = branches.get(branch_id)
            if not branch:
                errors.append(f"literal_history_branch_unresolved:{branch_id}")
                continue
            if branch.get("synthetic") is True:
                synthetic_literal += 1
        counts["synthetic_literal_history_branch_ids"] = synthetic_literal
        false_history_rate = synthetic_literal / counts["literal_history_branch_ids"] if counts["literal_history_branch_ids"] else 0.0
        factual_branch_id = outcome.get("factual_branch_id")
        factual_branch = branches.get(factual_branch_id) if isinstance(factual_branch_id, str) else None
        if not factual_branch or factual_branch.get("synthetic") is True:
            errors.append(f"factual_branch_not_resolved_or_synthetic:{factual_branch_id}")
        metrics["counterfactual"] = {
            "causal_sensitivity_total_variation_mean": sum(tv_values) / len(tv_values) if tv_values else None,
            "counterfactual_pairs": len(tv_values),
            "false_history_rate": false_history_rate,
            "synthetic_literal_history_branch_ids": synthetic_literal,
        }
        checks["counterfactual_metrics_computed"] = bool(tv_values)
        checks["false_history_rate_zero"] = false_history_rate == 0.0
        if false_history_rate != 0.0:
            errors.append(f"false_history_rate_nonzero:{false_history_rate:.6f}")

        counts["commitments_scored"] = 1

    return errors, {
        "counts": counts,
        "checks": checks,
        "metrics": metrics,
        "commitment_bundle_sha256": _stable_json_sha256(commitment_bundle) if isinstance(commitment_bundle, dict) else None,
        "outcome_reveal_sha256": _stable_json_sha256(outcome) if isinstance(outcome, dict) else None,
    }


def build_receipt(
    corpus_path: Path,
    distributions_path: Path,
    branches_path: Path,
    commitments_path: Path,
    outcome_path: Path,
    receipt_out: Path,
) -> dict[str, Any]:
    errors, derived = _score_trial(corpus_path, distributions_path, branches_path, commitments_path, outcome_path)
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.tom_scoring_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "corpus_path": str(corpus_path.resolve()),
        "distribution_bundle_path": str(distributions_path.resolve()),
        "branch_bundle_path": str(branches_path.resolve()),
        "commitment_bundle_path": str(commitments_path.resolve()),
        "outcome_reveal_path": str(outcome_path.resolve()),
        "receipt_path": str(receipt_out.resolve()),
        "errors": errors,
        "counts": derived["counts"],
        "checks": derived["checks"],
        "metrics": derived["metrics"],
        "commitment_bundle_sha256": derived["commitment_bundle_sha256"],
        "outcome_reveal_sha256": derived["outcome_reveal_sha256"],
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "claims": {
            "proves": [
                "the supplied sealed prediction commitment was scored only after outcome reveal",
                "action prediction Brier score and log loss were computed deterministically",
                "first- and second-order ToM label scores were computed from simulator labels",
                "calibration, risk-coverage, and formulation consistency metrics were computed",
                "counterfactual discrimination and false-history checks were computed",
                "prediction edits after reveal and canonical memory writes are absent",
            ]
            if status == PASS_STATUS
            else [
                "the scorer produced a fail-closed receipt for an invalid reveal or scoring boundary",
            ],
            "does_not_prove": [
                "model prediction benefit over baselines",
                "statistical calibration over a held-out corpus",
                "belief revision",
                "action-selection reward or regret",
                "Tau text-call execution",
                "live Memory recall",
                "fault-injection reliability",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--distributions", type=Path, required=True)
    parser.add_argument("--branches", type=Path, required=True)
    parser.add_argument("--commitments", type=Path, required=True)
    parser.add_argument("--outcome", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = build_receipt(
        args.corpus,
        args.distributions,
        args.branches,
        args.commitments,
        args.outcome,
        args.receipt_out,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
