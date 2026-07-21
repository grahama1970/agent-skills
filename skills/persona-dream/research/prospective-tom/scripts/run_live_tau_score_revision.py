#!/usr/bin/env python3
"""Score a live Tau PCTOM-R commitment and write a non-destructive revision."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
RESEARCH_ROOT = ROOT / "research" / "prospective-tom"
DEFAULT_CORPUS = RESEARCH_ROOT / "fixtures" / "gate1" / "development" / "social_episode_corpus.v1.json"
GATE5_SCRIPT = RESEARCH_ROOT / "scripts" / "reveal_and_score_trial.py"
GATE7_SCRIPT = RESEARCH_ROOT / "scripts" / "check_tom_belief_revision.py"
PASS_STATUS = "PASS_LIVE_TAU_PCTOM_SCORE_REVISION"
BLOCKED_STATUS = "BLOCKED_LIVE_TAU_PCTOM_SCORE_REVISION"
EPSILON = 1e-6


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


def _episode_by_id(corpus: dict[str, Any], episode_id: str) -> dict[str, Any]:
    for episode in corpus.get("episodes", []):
        if isinstance(episode, dict) and episode.get("episode_id") == episode_id:
            return episode
    raise RuntimeError(f"episode_not_found:{episode_id}")


def _labels_by_signature(episode: dict[str, Any]) -> dict[tuple[Any, Any, Any, Any, Any], str]:
    labels: dict[tuple[Any, Any, Any, Any, Any], str] = {}
    for label in episode.get("ground_truth_tom_labels", []):
        if not isinstance(label, dict):
            continue
        key = (
            label.get("perspective_order"),
            label.get("subject"),
            label.get("target"),
            label.get("mental_state_type"),
            label.get("proposition"),
        )
        value = label.get("value")
        if isinstance(value, str) and value:
            labels[key] = value
    return labels


def _factual_distribution_ids(distribution_bundle: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for distribution in distribution_bundle.get("distributions", []):
        if not isinstance(distribution, dict):
            continue
        if distribution.get("counterfactual") is False and isinstance(distribution.get("hypothesis_id"), str):
            ids.append(distribution["hypothesis_id"])
    return ids


def _outcome_reveal(
    *,
    episode: dict[str, Any],
    distribution_bundle: dict[str, Any],
    branch_bundle: dict[str, Any],
    commitment_bundle: dict[str, Any],
) -> dict[str, Any]:
    episode_id = episode["episode_id"]
    commitment = commitment_bundle["commitments"][0]
    prediction_id = commitment["prediction_id"]
    hidden_state_labels: dict[str, str] = {}
    label_map = _labels_by_signature(episode)
    for distribution in distribution_bundle.get("distributions", []):
        if not isinstance(distribution, dict) or distribution.get("counterfactual") is True:
            continue
        key = (
            distribution.get("perspective_order"),
            distribution.get("subject"),
            distribution.get("target"),
            distribution.get("mental_state_type"),
            distribution.get("proposition"),
        )
        if distribution.get("hypothesis_id") in hidden_state_labels:
            continue
        hidden_state_labels[distribution["hypothesis_id"]] = label_map.get(key, "UNKNOWN")
    factual_branch_ids = [
        branch.get("branch_id")
        for branch in branch_bundle.get("branches", [])
        if isinstance(branch, dict) and branch.get("branch_type") == "factual"
    ]
    factual_branch_id = next((branch_id for branch_id in factual_branch_ids if isinstance(branch_id, str)), None)
    payload = commitment.get("prediction_payload", {})
    predicted_actions = payload.get("predicted_next_action_distribution") if isinstance(payload, dict) else []
    top_action = None
    if isinstance(predicted_actions, list) and predicted_actions:
        top_action = max(
            (entry for entry in predicted_actions if isinstance(entry, dict)),
            key=lambda entry: float(entry.get("probability") or 0.0),
        ).get("value")
    return {
        "schema": "persona_dream.research.prospective_tom.tom_outcome_reveal.v1",
        "outcome_id": f"live-tau-outcome-{episode_id}",
        "episode_id": episode_id,
        "prediction_id": prediction_id,
        "outcome_visible": True,
        "reveal_complete": True,
        "revealed_at": _now_iso(),
        "canonical_memory_write": False,
        "actual_next_action": episode.get("actual_next_action"),
        "hidden_state_labels": hidden_state_labels,
        "equivalent_formulation_checks": [
            {
                "check_id": "live-tau-eq-action-paraphrase-001",
                "formulation_id": "same-question-paraphrase-001",
                "prediction_id": prediction_id,
                "expected_top_action": top_action,
            }
        ],
        "factual_branch_id": factual_branch_id,
        "literal_history_branch_ids": [factual_branch_id] if factual_branch_id else [],
    }


def _probabilities(entries: list[dict[str, Any]]) -> dict[str, float]:
    return {str(entry["value"]): float(entry["probability"]) for entry in entries}


def _posterior_distribution(prior_entries: list[dict[str, Any]], actual_label: str) -> list[dict[str, Any]]:
    prior = _probabilities(prior_entries)
    values = list(prior)
    if actual_label not in prior:
        values.append(actual_label)
        prior[actual_label] = 0.0
    actual_prior = prior.get(actual_label, 0.0)
    increase = min(0.18, 1.0 - actual_prior)
    remaining_scale = (1.0 - actual_prior - increase) / (1.0 - actual_prior) if actual_prior < 1.0 else 1.0
    posterior = {}
    for value in values:
        if value == actual_label:
            posterior[value] = actual_prior + increase
        else:
            posterior[value] = prior.get(value, 0.0) * remaining_scale
    total = sum(posterior.values())
    if total <= 0:
        return [{"value": "UNKNOWN", "probability": 1.0}]
    normalized = [{"value": value, "probability": probability / total} for value, probability in posterior.items()]
    # Keep deterministic order from the prior distribution, with any inserted label last.
    return normalized


def _belief_revision(
    *,
    distribution_bundle: dict[str, Any],
    scoring_receipt: dict[str, Any],
    outcome: dict[str, Any],
) -> dict[str, Any]:
    scores = scoring_receipt["metrics"]["belief_scores"]
    factual_scores = [score for score in scores if isinstance(score, dict) and isinstance(score.get("hypothesis_id"), str)]
    if not factual_scores:
        raise RuntimeError("scoring_receipt_has_no_belief_scores")
    score = factual_scores[0]
    prior_hypothesis_id = score["hypothesis_id"]
    prior = next(
        distribution
        for distribution in distribution_bundle["distributions"]
        if distribution.get("hypothesis_id") == prior_hypothesis_id
    )
    actual_label = score["actual_label"]
    posterior = _posterior_distribution(prior["distribution"], actual_label)
    return {
        "schema": "persona_dream.research.prospective_tom.tom_belief_revision.v1",
        "revision_id": f"live-tau-revision-{outcome['episode_id']}-{prior_hypothesis_id}",
        "episode_id": outcome["episode_id"],
        "prediction_id": outcome["prediction_id"],
        "prior_hypothesis_id": prior_hypothesis_id,
        "prior_distribution": prior,
        "prior_distribution_sha256": _stable_json_sha256(prior),
        "prior_audit_ref": {
            "distribution_bundle_sha256": _stable_json_sha256(distribution_bundle),
            "hypothesis_id": prior_hypothesis_id,
        },
        "observed_outcome_id": outcome["outcome_id"],
        "outcome_reveal_sha256": _stable_json_sha256(outcome),
        "scoring_receipt_sha256": _stable_json_sha256(scoring_receipt),
        "prediction_error": {
            "actual_label": actual_label,
            "prior_actual_probability": score["actual_probability"],
            "brier": score["brier"],
            "log_loss": score["log_loss"],
            "top_correct": score["top_correct"],
        },
        "surprise": score["log_loss"],
        "posterior_distribution": posterior,
        "posterior_distribution_sha256": _stable_json_sha256(posterior),
        "update_reason": (
            "Deterministic simulator outcome reveal supplied the actual ToM label; "
            "posterior updates current-use probability while preserving the sealed prior."
        ),
        "update_evidence_refs": [{"scope": "outcome_reveal", "source_id": outcome["outcome_id"]}],
        "supersedes_for_current_use": True,
        "prior_remains_auditable": True,
        "canonical_memory_write": False,
        "identity_write": False,
        "source_memory_write": False,
        "evidence_mutations": [],
    }


def build_receipt(
    *,
    live_tau_root: Path,
    corpus_path: Path,
    output_root: Path,
    receipt_out: Path,
) -> dict[str, Any]:
    started = time.monotonic()
    live_tau_root = live_tau_root.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts_root = output_root / "artifacts"
    receipts_root = output_root / "receipts"
    outcome_path = artifacts_root / "tom_outcome_reveal.json"
    scoring_receipt_path = receipts_root / "tom_scoring_receipt.json"
    revision_path = artifacts_root / "tom_belief_revision.json"
    revision_check_receipt_path = receipts_root / "belief_revision_check_receipt.json"
    errors: list[str] = []
    scoring_receipt: dict[str, Any] | None = None
    revision_check_receipt: dict[str, Any] | None = None

    live_tau_receipt_path = live_tau_root / "live_tau_gate2_4_receipt.v1.json"
    distribution_path = live_tau_root / "artifacts" / "tom_belief_distribution_bundle.json"
    branch_path = live_tau_root / "artifacts" / "counterfactual_branch_bundle.json"
    commitment_path = live_tau_root / "artifacts" / "tom_prediction_commitment_bundle.json"

    gate5 = _load_module(GATE5_SCRIPT, "persona_dream_pctom_gate5_score")
    gate7 = _load_module(GATE7_SCRIPT, "persona_dream_pctom_gate7_revision")

    try:
        live_tau_receipt = _load_json(live_tau_receipt_path)
        if live_tau_receipt.get("status") != "PASS_LIVE_TAU_PCTOM_GATE2_4":
            errors.append(f"live_tau_status:{live_tau_receipt.get('status')}")
        if live_tau_receipt.get("tau_live_call_performed") is not True:
            errors.append("live_tau_call_not_performed")
        if live_tau_receipt.get("memory_write_attempts") != 0:
            errors.append(f"live_tau_memory_write_attempts:{live_tau_receipt.get('memory_write_attempts')}")
        if live_tau_receipt.get("provider_call_attempts") != 0:
            errors.append(f"live_tau_provider_call_attempts:{live_tau_receipt.get('provider_call_attempts')}")

        corpus = _load_json(corpus_path)
        distribution_bundle = _load_json(distribution_path)
        branch_bundle = _load_json(branch_path)
        commitment_bundle = _load_json(commitment_path)
        episode = _episode_by_id(corpus, str(live_tau_receipt.get("episode_id")))
        outcome = _outcome_reveal(
            episode=episode,
            distribution_bundle=distribution_bundle,
            branch_bundle=branch_bundle,
            commitment_bundle=commitment_bundle,
        )
        _write_json(outcome_path, outcome)

        scoring_receipt = gate5.build_receipt(
            corpus_path,
            distribution_path,
            branch_path,
            commitment_path,
            outcome_path,
            scoring_receipt_path,
        )
        if scoring_receipt.get("status") != "PASS_TOM_SCORING_RECEIPT":
            errors.append(f"gate5_status:{scoring_receipt.get('status')}")
            errors.extend(f"gate5_error:{error}" for error in scoring_receipt.get("errors", []))

        if scoring_receipt.get("status") == "PASS_TOM_SCORING_RECEIPT":
            revision = _belief_revision(
                distribution_bundle=distribution_bundle,
                scoring_receipt=scoring_receipt,
                outcome=outcome,
            )
            _write_json(revision_path, revision)
            revision_check_receipt = gate7.build_receipt(
                distribution_path,
                scoring_receipt_path,
                outcome_path,
                revision_path,
                revision_check_receipt_path,
            )
            if revision_check_receipt.get("status") != "PASS_TOM_BELIEF_REVISION":
                errors.append(f"gate7_status:{revision_check_receipt.get('status')}")
                errors.extend(f"gate7_error:{error}" for error in revision_check_receipt.get("errors", []))
    except Exception as exc:
        errors.append(f"live_tau_score_revision_failed:{exc}")
        live_tau_receipt = None

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    scoring_counts = scoring_receipt.get("counts") if scoring_receipt else {}
    revision_counts = revision_check_receipt.get("counts") if revision_check_receipt else {}
    receipt = {
        "schema": "persona_dream.research.prospective_tom.live_tau_score_revision_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "live_tau_root": str(live_tau_root),
        "corpus_path": str(corpus_path.resolve()),
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "mocked": False,
        "live": bool(live_tau_receipt and live_tau_receipt.get("tau_live_call_performed") is True),
        "live_service_call_attempts": 0,
        "live_tau_originated_commitment_consumed": bool(
            live_tau_receipt and live_tau_receipt.get("status") == "PASS_LIVE_TAU_PCTOM_GATE2_4"
        ),
        "fixture_backed": False,
        "deterministic_simulator_corpus_fixture_backed": True,
        "human_content_judgment_required": False,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "live_tau_receipt_path": str(live_tau_receipt_path),
        "outcome_reveal_path": str(outcome_path),
        "gate5_scoring_receipt_path": str(scoring_receipt_path),
        "gate5_status": scoring_receipt.get("status") if scoring_receipt else None,
        "belief_revision_path": str(revision_path),
        "gate7_revision_receipt_path": str(revision_check_receipt_path),
        "gate7_status": revision_check_receipt.get("status") if revision_check_receipt else None,
        "counts": {
            "gate5": scoring_counts,
            "gate7": revision_counts,
        },
        "metrics": {
            "gate5_action": (scoring_receipt or {}).get("metrics", {}).get("action"),
            "gate5_calibration": (scoring_receipt or {}).get("metrics", {}).get("calibration"),
            "gate5_counterfactual": (scoring_receipt or {}).get("metrics", {}).get("counterfactual"),
            "gate7": (revision_check_receipt or {}).get("metrics", {}),
        },
        "errors": errors,
        "claims": {
            "proves": [
                "a live Tau-originated sealed commitment was consumed without editing the sealed prediction",
                "the deterministic simulator outcome was revealed only after the sealed commitment",
                "Gate 5 scoring computed action, belief, calibration, consistency, and counterfactual metrics from the Tau-authored commitment",
                "Gate 7 belief revision preserved the sealed prior and wrote a hash-bound posterior without canonical/source/identity writes",
                "no Memory write, provider call, new Tau call, or human content judgment was required",
            ]
            if status == PASS_STATUS
            else [
                "the live Tau score/revision bridge produced an inspectable fail-closed receipt",
            ],
            "does_not_prove": [
                "held-out prediction benefit over baselines",
                "statistical calibration over many episodes",
                "second-order live Tau scoring if the consumed live Tau bundle contains only first-order factual hypotheses",
                "live Memory recall for the same scored trial",
                "longitudinal recall after belief revision",
                "real service fault injection or causal replay",
                "complete Phase 01-16 runtime execution",
                "paid provider execution or video quality",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-tau-root", type=Path, required=True)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "live_tau_score_revision_receipt.v1.json")
    receipt = build_receipt(
        live_tau_root=args.live_tau_root,
        corpus_path=args.corpus,
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
