#!/usr/bin/env python3
"""Audit PCTOM-R2 Phase 4 deterministic scoring and abstention evidence."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from pctom_phase4_scoring_lib import SCORE_KINDS, default_phase4_paths, score_distribution
from pctom_r2_phase1_lib import ROOT_DEFAULT, SCHEMA_PREFIX, file_sha256, load_json, now_iso, rel, stable_json_sha256, write_json


PASS_STATUS = "PASS_PCTOM_DETERMINISTIC_SCORING_SURFACE"
BLOCKED_STATUS = "BLOCKED_PCTOM_DETERMINISTIC_SCORING_SURFACE"
EPSILON = 1e-9


def _isclose(left: Any, right: Any) -> bool:
    return isinstance(left, (int, float)) and isinstance(right, (int, float)) and abs(float(left) - float(right)) <= EPSILON


def _source_by_artifact(surface: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        row.get("artifact"): row
        for row in surface.get("source_files") or []
        if isinstance(row, dict) and isinstance(row.get("artifact"), str)
    }


def _load_sources(root: Path, surface: dict[str, Any], errors: list[str]) -> dict[str, Any]:
    sources: dict[str, Any] = {}
    for artifact, row in _source_by_artifact(surface).items():
        path_value = row.get("path")
        if not isinstance(path_value, str) or not path_value:
            errors.append(f"source_missing_path:{artifact}")
            continue
        full = root / path_value
        if not full.exists():
            errors.append(f"source_missing:{artifact}:{path_value}")
            continue
        if row.get("sha256") != file_sha256(full):
            errors.append(f"source_sha_mismatch:{artifact}:{path_value}")
        sources[artifact] = load_json(full, errors, artifact)
    return sources


def _episode_index(corpus: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        episode.get("episode_id"): episode
        for episode in corpus.get("episodes") or []
        if isinstance(episode, dict) and isinstance(episode.get("episode_id"), str)
    }


def _distribution_index(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        item.get("hypothesis_id"): item
        for item in bundle.get("distributions") or []
        if isinstance(item, dict) and isinstance(item.get("hypothesis_id"), str)
    }


def _commitment(bundle: dict[str, Any]) -> dict[str, Any]:
    commitments = bundle.get("commitments")
    if isinstance(commitments, list) and commitments and isinstance(commitments[0], dict):
        return commitments[0]
    return {}


def _expected_score_rows(sources: dict[str, Any], case_id: str, commitment_artifact: str) -> list[dict[str, Any]]:
    corpus = sources.get("corpus") if isinstance(sources.get("corpus"), dict) else {}
    distributions = sources.get("distributions") if isinstance(sources.get("distributions"), dict) else {}
    outcome = sources.get("outcome") if isinstance(sources.get("outcome"), dict) else {}
    commitment_bundle = sources.get(commitment_artifact) if isinstance(sources.get(commitment_artifact), dict) else {}
    commitment = _commitment(commitment_bundle)
    payload = commitment.get("prediction_payload") if isinstance(commitment.get("prediction_payload"), dict) else {}
    hidden_labels = outcome.get("hidden_state_labels") if isinstance(outcome.get("hidden_state_labels"), dict) else {}
    rows: list[dict[str, Any]] = []
    action_actual = outcome.get("actual_next_action")
    action_score = score_distribution(payload.get("predicted_next_action_distribution"), str(action_actual))
    rows.append({
        "case_id": case_id,
        "score_kind": "action",
        "score_id": "action",
        "brier": action_score.get("brier"),
        "log_loss": action_score.get("log_loss"),
        "actual_probability": action_score.get("actual_probability"),
        "top_value": action_score.get("top_value"),
        "top_correct": action_score.get("top_correct"),
    })
    distribution_index = _distribution_index(distributions)
    for hypothesis_id in payload.get("belief_distribution_refs") or []:
        distribution = distribution_index.get(hypothesis_id)
        if not distribution or distribution.get("counterfactual") is True:
            continue
        actual_label = hidden_labels.get(hypothesis_id)
        belief_score = score_distribution(distribution.get("distribution"), str(actual_label))
        rows.append({
            "case_id": case_id,
            "score_kind": "belief",
            "score_id": hypothesis_id,
            "actual_label": actual_label,
            "perspective_order": distribution.get("perspective_order"),
            "brier": belief_score.get("brier"),
            "log_loss": belief_score.get("log_loss"),
            "actual_probability": belief_score.get("actual_probability"),
            "top_value": belief_score.get("top_value"),
            "top_correct": belief_score.get("top_correct"),
        })
    # Keep the corpus dependency explicit so source substitutions cannot remove it unused.
    episode_id = outcome.get("episode_id")
    if episode_id not in _episode_index(corpus):
        rows.append({"case_id": case_id, "score_kind": "source_error", "score_id": "episode_missing"})
    return rows


def _row_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return str(row.get("case_id")), str(row.get("score_kind")), str(row.get("score_id"))


def audit_surface_data(root: Path, surface: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    if surface.get("schema") != f"{SCHEMA_PREFIX}.pctom_deterministic_scoring_surface.v1":
        errors.append(f"invalid_surface_schema:{surface.get('schema')}")
    sources = _load_sources(root, surface, errors)
    score_rows = surface.get("proper_score_rows")
    risk_rows = surface.get("risk_coverage_rows")
    if not isinstance(score_rows, list):
        errors.append("proper_score_rows_not_list")
        score_rows = []
    if not isinstance(risk_rows, list):
        errors.append("risk_coverage_rows_not_list")
        risk_rows = []

    expected_rows = _expected_score_rows(sources, "covered_prediction", "covered_commitments")
    expected_rows.extend(_expected_score_rows(sources, "abstained_prediction", "abstained_commitments"))
    expected_by_key = {_row_key(row): row for row in expected_rows}
    observed_by_key = {_row_key(row): row for row in score_rows if isinstance(row, dict)}
    for key, expected in expected_by_key.items():
        observed = observed_by_key.get(key)
        if observed is None:
            errors.append(f"scoring_metric_tamper:missing_score_row:{key}")
            continue
        for metric in ("brier", "log_loss", "actual_probability"):
            if not _isclose(observed.get(metric), expected.get(metric)):
                errors.append(f"scoring_metric_tamper:{key}:{metric}:{observed.get(metric)}:{expected.get(metric)}")
        if observed.get("top_value") != expected.get("top_value"):
            errors.append(f"scoring_metric_tamper:{key}:top_value:{observed.get('top_value')}:{expected.get('top_value')}")
        if observed.get("top_correct") != expected.get("top_correct"):
            errors.append(f"scoring_metric_tamper:{key}:top_correct:{observed.get('top_correct')}:{expected.get('top_correct')}")
    for key in sorted(set(observed_by_key) - set(expected_by_key)):
        errors.append(f"scoring_metric_tamper:unexpected_score_row:{key}")

    risk_by_case = {
        row.get("case_id"): row for row in risk_rows
        if isinstance(row, dict) and isinstance(row.get("case_id"), str)
    }
    covered = risk_by_case.get("covered_prediction")
    abstained = risk_by_case.get("abstained_prediction")
    if not covered:
        errors.append("abstention_accounting:covered_prediction_missing")
    else:
        if covered.get("abstained") is not False:
            errors.append(f"abstention_accounting:covered_abstained_flag:{covered.get('abstained')}")
        if covered.get("coverage") != 1.0:
            errors.append(f"abstention_accounting:covered_coverage:{covered.get('coverage')}")
        if not isinstance(covered.get("selective_accuracy"), (int, float)):
            errors.append(f"abstention_accounting:covered_selective_accuracy_missing:{covered.get('selective_accuracy')}")
    if not abstained:
        errors.append("abstention_accounting:abstained_prediction_missing")
    else:
        if abstained.get("abstained") is not True:
            errors.append(f"abstention_accounting:abstained_flag:{abstained.get('abstained')}")
        if abstained.get("coverage") != 0.0:
            errors.append(f"abstention_accounting:abstained_coverage:{abstained.get('coverage')}")
        if abstained.get("selective_accuracy") != 0.0:
            errors.append(f"abstention_accounting:abstained_selective_accuracy:{abstained.get('selective_accuracy')}")
    for row in score_rows:
        if not isinstance(row, dict):
            errors.append("proper_score_row_not_object")
            continue
        if row.get("score_kind") not in SCORE_KINDS:
            errors.append(f"scoring_metric_tamper:invalid_score_kind:{row.get('score_kind')}")

    counts = {
        "case_rows": len(surface.get("case_rows") or []),
        "proper_score_rows": len(score_rows),
        "expected_score_rows": len(expected_rows),
        "brier_rows": sum(1 for row in score_rows if isinstance(row, dict) and isinstance(row.get("brier"), (int, float))),
        "log_loss_rows": sum(1 for row in score_rows if isinstance(row, dict) and isinstance(row.get("log_loss"), (int, float))),
        "risk_coverage_rows": len(risk_rows),
        "covered_rows": 1 if covered else 0,
        "abstention_rows": 1 if abstained else 0,
        "metric_recomputation_mismatches": sum(1 for error in errors if error.startswith("scoring_metric_tamper:")),
        "abstention_accounting_errors": sum(1 for error in errors if error.startswith("abstention_accounting:")),
        "source_mismatches": sum(1 for error in errors if error.startswith("source_")),
    }
    return errors, counts


def _status_for_errors(errors: list[str]) -> str:
    if any(error.startswith("abstention_accounting:") for error in errors):
        return "BLOCKED_PCTOM_ABSTENTION_ACCOUNTING"
    if any(error.startswith("source_") for error in errors):
        return "BLOCKED_PCTOM_SCORING_SOURCE_MISMATCH"
    if any(error.startswith("scoring_metric_tamper:") for error in errors):
        return "BLOCKED_PCTOM_SCORING_METRIC_TAMPER"
    return "PASS_PCTOM_SCORING_SURFACE_CASE"


def _negative_cases(surface: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    cases: list[tuple[str, str, dict[str, Any]]] = []
    brier = deepcopy(surface)
    brier["proper_score_rows"][0]["brier"] = float(brier["proper_score_rows"][0]["brier"]) + 0.01
    cases.append(("brier-substitution", "BLOCKED_PCTOM_SCORING_METRIC_TAMPER", brier))

    log_loss = deepcopy(surface)
    log_loss["proper_score_rows"][0]["log_loss"] = 0.0
    cases.append(("log-loss-substitution", "BLOCKED_PCTOM_SCORING_METRIC_TAMPER", log_loss))

    covered_coverage = deepcopy(surface)
    for row in covered_coverage["risk_coverage_rows"]:
        if row.get("case_id") == "covered_prediction":
            row["coverage"] = 0.0
    cases.append(("covered-coverage-zero", "BLOCKED_PCTOM_ABSTENTION_ACCOUNTING", covered_coverage))

    abstained_coverage = deepcopy(surface)
    for row in abstained_coverage["risk_coverage_rows"]:
        if row.get("case_id") == "abstained_prediction":
            row["coverage"] = 1.0
    cases.append(("abstained-coverage-one", "BLOCKED_PCTOM_ABSTENTION_ACCOUNTING", abstained_coverage))

    missing_abstention = deepcopy(surface)
    missing_abstention["risk_coverage_rows"] = [
        row for row in missing_abstention["risk_coverage_rows"]
        if row.get("case_id") != "abstained_prediction"
    ]
    cases.append(("missing-abstention-row", "BLOCKED_PCTOM_ABSTENTION_ACCOUNTING", missing_abstention))

    source_hash = deepcopy(surface)
    source_hash["source_files"][0]["sha256"] = "sha256:" + "0" * 64
    cases.append(("source-hash-substitution", "BLOCKED_PCTOM_SCORING_SOURCE_MISMATCH", source_hash))
    return cases


def audit_surface(root: Path, evidence_path: Path, receipt_out: Path) -> dict[str, Any]:
    errors: list[str] = []
    surface = load_json(evidence_path, errors, "deterministic_scoring_surface")
    if not isinstance(surface, dict):
        surface = {}
    surface_errors, counts = audit_surface_data(root, surface)
    errors.extend(surface_errors)

    negative_results: list[dict[str, Any]] = []
    for case_name, expected_status, mutated in _negative_cases(surface):
        mutation_errors, mutation_counts = audit_surface_data(root, mutated)
        observed_status = _status_for_errors(mutation_errors)
        blocked_as_expected = observed_status == expected_status
        if not blocked_as_expected:
            errors.append(f"negative_fixture_not_blocked:{case_name}:{observed_status}:{expected_status}")
        negative_results.append({
            "fixture": case_name,
            "expected_status": expected_status,
            "observed_status": observed_status,
            "blocked_as_expected": blocked_as_expected,
            "counts": mutation_counts,
            "errors": mutation_errors,
        })
    counts["negative_fixtures"] = len(negative_results)
    counts["negative_fixtures_blocked"] = sum(1 for row in negative_results if row.get("blocked_as_expected") is True)
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": f"{SCHEMA_PREFIX}.pctom_deterministic_scoring_audit_receipt.v1",
        "created_at": now_iso(),
        "status": status,
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "human_content_judgment_rows": 0,
        "llm_judge_rows": 0,
        "evidence_path": rel(root, evidence_path),
        "evidence_sha256": file_sha256(evidence_path) if evidence_path.exists() else "",
        "source_paths": {name: rel(root, path) for name, path in default_phase4_paths(root).items()},
        "counts": counts,
        "scoring_checks": {
            "proper_metric_rows_recomputed": counts["metric_recomputation_mismatches"] == 0,
            "brier_rows_present": counts["brier_rows"] == counts["expected_score_rows"],
            "log_loss_rows_present": counts["log_loss_rows"] == counts["expected_score_rows"],
            "covered_prediction_accounted": counts["covered_rows"] == 1,
            "abstained_prediction_accounted": counts["abstention_rows"] == 1,
            "abstention_accounting_errors_absent": counts["abstention_accounting_errors"] == 0,
            "source_hashes_match": counts["source_mismatches"] == 0,
            "negative_mutations_fail_closed": counts["negative_fixtures_blocked"] == counts["negative_fixtures"],
        },
        "negative_fixture_results": negative_results,
        "errors": errors,
        "claims": {
            "proves": [
                "deterministic local scoring surface recomputes Brier score, log loss, actual probability, and top-label correctness for action and first-/second-order belief rows",
                "deterministic local scoring surface accounts for one covered prediction and one abstained prediction with explicit risk-coverage fields",
                "metric substitution, source hash substitution, and abstention accounting mutations fail closed",
            ] if status == PASS_STATUS else [
                "deterministic scoring surface audit failed closed before Phase 4 acceptance",
            ],
            "does_not_prove": [
                "live prediction benefit over baselines",
                "statistical calibration over a held-out corpus",
                "semantic dream quality",
                "belief revision",
                "pipeline reliability under service faults",
                "paid provider execution",
                "production Phase 01-16 runtime execution",
            ],
        },
    }
    receipt["receipt_sha256"] = stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt = audit_surface(args.root, args.evidence, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(args.receipt_out)
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
