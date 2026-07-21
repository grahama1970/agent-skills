#!/usr/bin/env python3
"""Validate deterministic PCTOM-R Gate 7 non-destructive belief revision."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_TOM_BELIEF_REVISION"
BLOCKED_STATUS = "BLOCKED_TOM_BELIEF_REVISION"
EPSILON = 1e-6


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


def _distribution_index(bundle: Any, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(bundle, dict):
        errors.append("distribution_bundle_not_object")
        return {}
    if bundle.get("schema") != "persona_dream.research.prospective_tom.tom_belief_distribution_bundle.v1":
        errors.append(f"invalid_distribution_bundle_schema:{bundle.get('schema')}")
    if bundle.get("sealed") is not True:
        errors.append("distribution_bundle_not_sealed")
    if bundle.get("outcome_visible") is not False:
        errors.append("distribution_bundle_outcome_visible_not_false")
    if bundle.get("canonical_memory_write") is not False:
        errors.append("distribution_bundle_canonical_memory_write_not_false")
    index: dict[str, dict[str, Any]] = {}
    distributions = bundle.get("distributions")
    if not isinstance(distributions, list):
        errors.append("distribution_bundle_distributions_not_list")
        return index
    for idx, distribution in enumerate(distributions):
        if not isinstance(distribution, dict):
            errors.append(f"distribution_{idx}_not_object")
            continue
        hypothesis_id = distribution.get("hypothesis_id")
        if not isinstance(hypothesis_id, str) or not hypothesis_id:
            errors.append(f"distribution_{idx}_missing_hypothesis_id")
            continue
        index[hypothesis_id] = distribution
    return index


def _belief_score_index(scoring_receipt: Any, errors: list[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(scoring_receipt, dict):
        errors.append("scoring_receipt_not_object")
        return {}
    if scoring_receipt.get("schema") != "persona_dream.research.prospective_tom.tom_scoring_receipt.v1":
        errors.append(f"invalid_scoring_receipt_schema:{scoring_receipt.get('schema')}")
    if scoring_receipt.get("status") != "PASS_TOM_SCORING_RECEIPT":
        errors.append(f"scoring_receipt_not_pass:{scoring_receipt.get('status')}")
    if scoring_receipt.get("memory_write_attempts") not in (0, None):
        errors.append(f"scoring_receipt_memory_write_attempts_nonzero:{scoring_receipt.get('memory_write_attempts')}")
    scores = scoring_receipt.get("metrics", {}).get("belief_scores")
    if not isinstance(scores, list):
        errors.append("scoring_receipt_belief_scores_not_list")
        return {}
    index: dict[str, dict[str, Any]] = {}
    for idx, score in enumerate(scores):
        if not isinstance(score, dict):
            errors.append(f"belief_score_{idx}_not_object")
            continue
        hypothesis_id = score.get("hypothesis_id")
        if not isinstance(hypothesis_id, str) or not hypothesis_id:
            errors.append(f"belief_score_{idx}_missing_hypothesis_id")
            continue
        index[hypothesis_id] = score
    return index


def _check_distribution(entries: Any, prefix: str, errors: list[str]) -> dict[str, float]:
    if not isinstance(entries, list) or not entries:
        errors.append(f"{prefix}_distribution_not_nonempty_list")
        return {}
    total = 0.0
    probabilities: dict[str, float] = {}
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
        total += float(probability)
        probabilities[value] = float(probability)
    if abs(total - 1.0) > EPSILON:
        errors.append(f"{prefix}_distribution_sum:{total:.6f}")
    return probabilities


def _number(value: Any, prefix: str, errors: list[str]) -> float | None:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        errors.append(f"{prefix}_not_number:{value}")
        return None
    return float(value)


def _check_revision(
    distribution_bundle_path: Path,
    scoring_receipt_path: Path,
    outcome_path: Path,
    revision_path: Path,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    distribution_bundle = _load_json(distribution_bundle_path, errors, "distribution_bundle")
    scoring_receipt = _load_json(scoring_receipt_path, errors, "scoring_receipt")
    outcome = _load_json(outcome_path, errors, "outcome_reveal")
    revision = _load_json(revision_path, errors, "belief_revision")

    distributions = _distribution_index(distribution_bundle, errors)
    belief_scores = _belief_score_index(scoring_receipt, errors)
    distribution_bundle_sha256 = _stable_json_sha256(distribution_bundle) if isinstance(distribution_bundle, dict) else None
    scoring_receipt_sha256 = _stable_json_sha256(scoring_receipt) if isinstance(scoring_receipt, dict) else None
    outcome_reveal_sha256 = _stable_json_sha256(outcome) if isinstance(outcome, dict) else None

    counts = {
        "prior_hypotheses_checked": 0,
        "prediction_error_fields_checked": 0,
        "posterior_distribution_values": 0,
        "evidence_update_refs": 0,
        "forbidden_write_attempts": 0,
    }
    checks = {
        "scoring_receipt_passed": False,
        "outcome_reveal_complete": False,
        "prior_resolves": False,
        "prior_snapshot_matches": False,
        "prior_hash_matches": False,
        "prediction_error_matches_scoring": False,
        "posterior_distribution_sums_to_one": False,
        "posterior_hash_matches": False,
        "prior_remains_auditable": False,
        "no_evidence_mutation": False,
        "no_canonical_or_identity_write": False,
    }
    metrics = {
        "prior_hypothesis_id": None,
        "actual_label": None,
        "prior_actual_probability": None,
        "surprise": None,
        "posterior_actual_probability": None,
    }

    if isinstance(scoring_receipt, dict) and scoring_receipt.get("status") == "PASS_TOM_SCORING_RECEIPT":
        checks["scoring_receipt_passed"] = True
    if not isinstance(outcome, dict):
        errors.append("outcome_reveal_not_object")
        outcome = {}
    if outcome.get("schema") != "persona_dream.research.prospective_tom.tom_outcome_reveal.v1":
        errors.append(f"invalid_outcome_reveal_schema:{outcome.get('schema')}")
    if outcome.get("outcome_visible") is not True:
        errors.append("outcome_visible_not_true")
    if outcome.get("reveal_complete") is not True:
        errors.append("outcome_reveal_not_complete")
    if outcome.get("canonical_memory_write") is not False:
        errors.append("outcome_canonical_memory_write_not_false")
    if outcome.get("reveal_complete") is True and outcome.get("outcome_visible") is True:
        checks["outcome_reveal_complete"] = True

    if not isinstance(revision, dict):
        errors.append("belief_revision_not_object")
        return errors, {"counts": counts, "checks": checks, "metrics": metrics}
    if revision.get("schema") != "persona_dream.research.prospective_tom.tom_belief_revision.v1":
        errors.append(f"invalid_belief_revision_schema:{revision.get('schema')}")
    if revision.get("canonical_memory_write") is not False:
        errors.append("belief_revision_canonical_memory_write_not_false")
        counts["forbidden_write_attempts"] += 1
    if revision.get("identity_write") is not False:
        errors.append("belief_revision_identity_write_not_false")
        counts["forbidden_write_attempts"] += 1
    if revision.get("source_memory_write") is not False:
        errors.append("belief_revision_source_memory_write_not_false")
        counts["forbidden_write_attempts"] += 1
    if counts["forbidden_write_attempts"] == 0:
        checks["no_canonical_or_identity_write"] = True

    evidence_mutations = revision.get("evidence_mutations")
    if evidence_mutations != []:
        errors.append(f"evidence_mutations_not_empty:{evidence_mutations}")
    else:
        checks["no_evidence_mutation"] = True

    if revision.get("scoring_receipt_sha256") != scoring_receipt_sha256:
        errors.append(f"scoring_receipt_sha256_mismatch:{revision.get('scoring_receipt_sha256')}:{scoring_receipt_sha256}")
    if revision.get("outcome_reveal_sha256") != outcome_reveal_sha256:
        errors.append(f"outcome_reveal_sha256_mismatch:{revision.get('outcome_reveal_sha256')}:{outcome_reveal_sha256}")
    if revision.get("observed_outcome_id") != outcome.get("outcome_id"):
        errors.append(f"observed_outcome_id_mismatch:{revision.get('observed_outcome_id')}:{outcome.get('outcome_id')}")
    if revision.get("prediction_id") != outcome.get("prediction_id"):
        errors.append(f"prediction_id_mismatch:{revision.get('prediction_id')}:{outcome.get('prediction_id')}")
    if revision.get("episode_id") != outcome.get("episode_id"):
        errors.append(f"episode_id_mismatch:{revision.get('episode_id')}:{outcome.get('episode_id')}")

    prior_hypothesis_id = revision.get("prior_hypothesis_id")
    metrics["prior_hypothesis_id"] = prior_hypothesis_id
    prior = distributions.get(prior_hypothesis_id) if isinstance(prior_hypothesis_id, str) else None
    score = belief_scores.get(prior_hypothesis_id) if isinstance(prior_hypothesis_id, str) else None
    counts["prior_hypotheses_checked"] = 1
    if prior is None:
        errors.append(f"unresolved_prior_hypothesis_id:{prior_hypothesis_id}")
    else:
        checks["prior_resolves"] = True
    if score is None:
        errors.append(f"unresolved_scoring_belief_score:{prior_hypothesis_id}")

    prior_distribution = revision.get("prior_distribution")
    if not isinstance(prior_distribution, dict):
        errors.append("prior_distribution_not_object")
        prior_distribution = {}
    if prior is not None and prior_distribution == prior:
        checks["prior_snapshot_matches"] = True
    elif prior is not None:
        errors.append("prior_distribution_does_not_match_sealed_hypothesis")
    prior_hash = _stable_json_sha256(prior_distribution)
    if revision.get("prior_distribution_sha256") == prior_hash:
        checks["prior_hash_matches"] = True
    else:
        errors.append(f"prior_distribution_sha256_mismatch:{revision.get('prior_distribution_sha256')}:{prior_hash}")

    prior_audit_ref = revision.get("prior_audit_ref")
    if not isinstance(prior_audit_ref, dict):
        errors.append("prior_audit_ref_not_object")
    else:
        if prior_audit_ref.get("distribution_bundle_sha256") != distribution_bundle_sha256:
            errors.append(
                f"prior_audit_ref_distribution_bundle_sha256_mismatch:{prior_audit_ref.get('distribution_bundle_sha256')}:{distribution_bundle_sha256}"
            )
        if prior_audit_ref.get("hypothesis_id") != prior_hypothesis_id:
            errors.append(f"prior_audit_ref_hypothesis_mismatch:{prior_audit_ref.get('hypothesis_id')}:{prior_hypothesis_id}")
    if revision.get("prior_remains_auditable") is True:
        checks["prior_remains_auditable"] = True
    else:
        errors.append("prior_remains_auditable_not_true")
    if revision.get("supersedes_for_current_use") is not True:
        errors.append("supersedes_for_current_use_not_true")

    prediction_error = revision.get("prediction_error")
    if not isinstance(prediction_error, dict):
        errors.append("prediction_error_not_object")
        prediction_error = {}
    if score is not None:
        actual_label = score.get("actual_label")
        metrics["actual_label"] = actual_label
        prior_actual_probability = _number(prediction_error.get("prior_actual_probability"), "prediction_error_prior_actual_probability", errors)
        supplied_brier = _number(prediction_error.get("brier"), "prediction_error_brier", errors)
        supplied_log_loss = _number(prediction_error.get("log_loss"), "prediction_error_log_loss", errors)
        counts["prediction_error_fields_checked"] = 3
        if prediction_error.get("actual_label") != actual_label:
            errors.append(f"prediction_error_actual_label_mismatch:{prediction_error.get('actual_label')}:{actual_label}")
        if prior_actual_probability is not None and abs(prior_actual_probability - float(score.get("actual_probability"))) > EPSILON:
            errors.append(f"prediction_error_probability_mismatch:{prior_actual_probability:.6f}:{float(score.get('actual_probability')):.6f}")
        if supplied_brier is not None and abs(supplied_brier - float(score.get("brier"))) > EPSILON:
            errors.append(f"prediction_error_brier_mismatch:{supplied_brier:.6f}:{float(score.get('brier')):.6f}")
        if supplied_log_loss is not None and abs(supplied_log_loss - float(score.get("log_loss"))) > EPSILON:
            errors.append(f"prediction_error_log_loss_mismatch:{supplied_log_loss:.6f}:{float(score.get('log_loss')):.6f}")
        surprise = _number(revision.get("surprise"), "surprise", errors)
        if surprise is not None:
            metrics["surprise"] = surprise
            if abs(surprise - float(score.get("log_loss"))) > EPSILON:
                errors.append(f"surprise_log_loss_mismatch:{surprise:.6f}:{float(score.get('log_loss')):.6f}")
        metrics["prior_actual_probability"] = score.get("actual_probability")

    posterior = revision.get("posterior_distribution")
    posterior_probs = _check_distribution(posterior, "posterior", errors)
    counts["posterior_distribution_values"] = len(posterior_probs)
    if posterior_probs and not any(error.startswith("posterior_distribution_sum") for error in errors):
        checks["posterior_distribution_sums_to_one"] = True
    posterior_hash = _stable_json_sha256(posterior) if isinstance(posterior, list) else None
    if revision.get("posterior_distribution_sha256") == posterior_hash:
        checks["posterior_hash_matches"] = True
    else:
        errors.append(f"posterior_distribution_sha256_mismatch:{revision.get('posterior_distribution_sha256')}:{posterior_hash}")
    actual_label = metrics["actual_label"]
    if isinstance(actual_label, str) and actual_label in posterior_probs:
        metrics["posterior_actual_probability"] = posterior_probs[actual_label]

    update_refs = revision.get("update_evidence_refs")
    if not isinstance(update_refs, list) or not update_refs:
        errors.append("update_evidence_refs_not_nonempty_list")
        update_refs = []
    for idx, ref in enumerate(update_refs):
        if not isinstance(ref, dict):
            errors.append(f"update_evidence_ref_{idx}_not_object")
            continue
        if ref.get("scope") != "outcome_reveal" or ref.get("source_id") != outcome.get("outcome_id"):
            errors.append(f"update_evidence_ref_{idx}_mismatch:{ref}")
            continue
        counts["evidence_update_refs"] += 1

    error_prefixes = (
        "prediction_error_actual_label_mismatch",
        "prediction_error_probability_mismatch",
        "prediction_error_brier_mismatch",
        "prediction_error_log_loss_mismatch",
        "surprise_log_loss_mismatch",
    )
    checks["prediction_error_matches_scoring"] = not any(error.startswith(error_prefixes) for error in errors)
    return errors, {"counts": counts, "checks": checks, "metrics": metrics}


def build_receipt(
    distribution_bundle_path: Path,
    scoring_receipt_path: Path,
    outcome_path: Path,
    revision_path: Path,
    receipt_out: Path,
) -> dict[str, Any]:
    errors, derived = _check_revision(distribution_bundle_path, scoring_receipt_path, outcome_path, revision_path)
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.belief_revision_check_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "distribution_bundle_path": str(distribution_bundle_path.resolve()),
        "scoring_receipt_path": str(scoring_receipt_path.resolve()),
        "outcome_reveal_path": str(outcome_path.resolve()),
        "belief_revision_path": str(revision_path.resolve()),
        "receipt_path": str(receipt_out.resolve()),
        "errors": errors,
        "counts": derived["counts"],
        "checks": derived["checks"],
        "metrics": derived["metrics"],
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "tau_call_attempts": 0,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "claims": {
            "proves": [
                "the supplied belief revision consumes a PASS Gate 5 scoring receipt",
                "the prior hypothesis resolves to a sealed Gate 2 distribution and remains auditable",
                "prediction error and surprise recompute from the scoring receipt",
                "the posterior distribution is a new hash-bound distribution without rewriting the prior",
                "outcome reveal evidence is referenced as an update, not rewritten as source memory",
                "canonical memory, identity, and source-memory writes are absent",
            ]
            if status == PASS_STATUS
            else [
                "the checker produced a fail-closed receipt for an invalid belief-revision boundary",
            ],
            "does_not_prove": [
                "live Tau belief-revision generation",
                "live Memory recall",
                "longitudinal recall after revision",
                "fault-injection reliability",
                "semantic quality of the posterior explanation",
                "provider or video execution",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distributions", type=Path, required=True)
    parser.add_argument("--scoring-receipt", type=Path, required=True)
    parser.add_argument("--outcome", type=Path, required=True)
    parser.add_argument("--belief-revision", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = build_receipt(args.distributions, args.scoring_receipt, args.outcome, args.belief_revision, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
