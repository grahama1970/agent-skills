"""Deterministic Phase 4 scoring and abstention helpers."""
from __future__ import annotations

import math
from copy import deepcopy
from pathlib import Path
from typing import Any

from pctom_r2_phase1_lib import file_sha256, load_json, now_iso, rel, stable_json_sha256, write_json


SCHEMA_PREFIX = "persona_dream.research.prospective_tom"
EPSILON = 1e-9
MIN_PROBABILITY = 1e-12
SCORE_KINDS = {"action", "belief"}


def default_phase4_paths(root: Path) -> dict[str, Path]:
    return {
        "corpus": root / "fixtures/gate1/development/social_episode_corpus.v1.json",
        "distributions": root / "fixtures/gate2/positive/distributions_ok/tom_belief_distribution_bundle.json",
        "branches": root / "fixtures/gate3/positive/branches_ok/counterfactual_branch_bundle.json",
        "covered_commitments": root / "fixtures/gate5/positive/scoring_ok/tom_prediction_commitment_bundle.json",
        "abstained_commitments": root / "fixtures/phase4/abstention_case/tom_prediction_commitment_bundle.json",
        "outcome": root / "fixtures/gate5/positive/scoring_ok/tom_outcome_reveal.json",
        "covered_receipt": root / "receipts/pctom-deterministic-scoring-covered.v1.json",
        "abstained_receipt": root / "receipts/pctom-deterministic-scoring-abstained.v1.json",
    }


def derive_abstention_commitment(covered_bundle: dict[str, Any]) -> dict[str, Any]:
    abstained = deepcopy(covered_bundle)
    for commitment in abstained.get("commitments") or []:
        payload = commitment.get("prediction_payload")
        if isinstance(payload, dict):
            payload["abstain"] = True
            commitment["prediction_payload_sha256"] = stable_json_sha256(payload)
    return abstained


def write_abstention_fixture(root: Path, output_path: Path) -> dict[str, Any]:
    errors: list[str] = []
    covered = load_json(default_phase4_paths(root)["covered_commitments"], errors, "covered_commitments")
    if not isinstance(covered, dict):
        raise SystemExit(f"cannot build abstention fixture: {errors}")
    abstained = derive_abstention_commitment(covered)
    write_json(output_path, abstained)
    return abstained


def score_distribution(entries: Any, actual: str) -> dict[str, Any]:
    if not isinstance(entries, list) or not entries:
        return {"errors": ["distribution_not_nonempty_list"]}
    probs: dict[str, float] = {}
    total = 0.0
    errors: list[str] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"distribution_{index}_not_object")
            continue
        value = entry.get("value")
        probability = entry.get("probability")
        if not isinstance(value, str) or not value:
            errors.append(f"distribution_{index}_missing_value")
            continue
        if not isinstance(probability, (int, float)) or isinstance(probability, bool):
            errors.append(f"distribution_{index}_invalid_probability:{probability}")
            continue
        probs[value] = float(probability)
        total += float(probability)
    if abs(total - 1.0) > EPSILON:
        errors.append(f"distribution_sum:{total:.12f}")
    labels = set(probs) | {actual}
    actual_probability = probs.get(actual, 0.0)
    top_value = max(probs.items(), key=lambda item: item[1])[0] if probs else None
    return {
        "errors": errors,
        "brier": sum((probs.get(label, 0.0) - (1.0 if label == actual else 0.0)) ** 2 for label in labels),
        "log_loss": -math.log(max(actual_probability, MIN_PROBABILITY)),
        "actual_probability": actual_probability,
        "top_value": top_value,
        "top_correct": top_value == actual,
    }


def metric_rows_from_receipt(case_id: str, receipt: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    metrics = receipt.get("metrics") if isinstance(receipt.get("metrics"), dict) else {}
    action = metrics.get("action") if isinstance(metrics.get("action"), dict) else None
    if action:
        rows.append({
            "case_id": case_id,
            "score_kind": "action",
            "score_id": "action",
            "actual_label": None,
            "brier": action.get("brier"),
            "log_loss": action.get("log_loss"),
            "actual_probability": action.get("actual_probability"),
            "top_value": action.get("top_value"),
            "top_correct": action.get("top_correct"),
        })
    for belief in metrics.get("belief_scores") or []:
        if not isinstance(belief, dict):
            continue
        rows.append({
            "case_id": case_id,
            "score_kind": "belief",
            "score_id": belief.get("hypothesis_id"),
            "actual_label": belief.get("actual_label"),
            "perspective_order": belief.get("perspective_order"),
            "brier": belief.get("brier"),
            "log_loss": belief.get("log_loss"),
            "actual_probability": belief.get("actual_probability"),
            "top_value": belief.get("top_value"),
            "top_correct": belief.get("top_correct"),
        })
    return rows


def risk_row_from_receipt(case_id: str, receipt: dict[str, Any]) -> dict[str, Any]:
    metrics = receipt.get("metrics") if isinstance(receipt.get("metrics"), dict) else {}
    risk = metrics.get("risk_coverage") if isinstance(metrics.get("risk_coverage"), dict) else {}
    calibration = metrics.get("calibration") if isinstance(metrics.get("calibration"), dict) else {}
    return {
        "case_id": case_id,
        "coverage": risk.get("coverage"),
        "selective_accuracy": risk.get("selective_accuracy"),
        "abstained": risk.get("abstained"),
        "expected_calibration_error": calibration.get("expected_calibration_error"),
        "calibration_bucket_count": len(calibration.get("buckets") or []),
    }


def source_file_rows(root: Path, paths: dict[str, Path]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for label, path in paths.items():
        if not path.exists():
            rows.append({"artifact": label, "path": rel(root, path), "sha256": ""})
            continue
        rows.append({"artifact": label, "path": rel(root, path), "sha256": file_sha256(path)})
    return rows


def build_surface(root: Path, evidence_out: Path, covered_receipt: dict[str, Any], abstained_receipt: dict[str, Any]) -> dict[str, Any]:
    paths = default_phase4_paths(root)
    relevant_paths = {
        "corpus": paths["corpus"],
        "distributions": paths["distributions"],
        "branches": paths["branches"],
        "covered_commitments": paths["covered_commitments"],
        "abstained_commitments": paths["abstained_commitments"],
        "outcome": paths["outcome"],
        "covered_receipt": paths["covered_receipt"],
        "abstained_receipt": paths["abstained_receipt"],
    }
    proper_rows = metric_rows_from_receipt("covered_prediction", covered_receipt)
    proper_rows.extend(metric_rows_from_receipt("abstained_prediction", abstained_receipt))
    risk_rows = [
        risk_row_from_receipt("covered_prediction", covered_receipt),
        risk_row_from_receipt("abstained_prediction", abstained_receipt),
    ]
    case_rows = [
        {
            "case_id": "covered_prediction",
            "receipt_path": rel(root, paths["covered_receipt"]),
            "receipt_sha256": file_sha256(paths["covered_receipt"]),
            "status": covered_receipt.get("status"),
            "abstention_expected": False,
        },
        {
            "case_id": "abstained_prediction",
            "receipt_path": rel(root, paths["abstained_receipt"]),
            "receipt_sha256": file_sha256(paths["abstained_receipt"]),
            "status": abstained_receipt.get("status"),
            "abstention_expected": True,
        },
    ]
    counts = {
        "case_rows": len(case_rows),
        "proper_score_rows": len(proper_rows),
        "brier_rows": sum(1 for row in proper_rows if isinstance(row.get("brier"), (int, float))),
        "log_loss_rows": sum(1 for row in proper_rows if isinstance(row.get("log_loss"), (int, float))),
        "risk_coverage_rows": len(risk_rows),
        "covered_rows": sum(1 for row in risk_rows if row.get("abstained") is False),
        "abstention_rows": sum(1 for row in risk_rows if row.get("abstained") is True),
        "calibration_rows": sum(1 for row in risk_rows if isinstance(row.get("expected_calibration_error"), (int, float))),
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "human_content_judgment_rows": 0,
        "llm_judge_rows": 0,
    }
    evidence = {
        "schema": f"{SCHEMA_PREFIX}.pctom_deterministic_scoring_surface.v1",
        "created_at": now_iso(),
        "status": "DETERMINISTIC_SCORING_SURFACE_BUILT",
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "human_content_judgment_rows": 0,
        "llm_judge_rows": 0,
        "source_files": source_file_rows(root, relevant_paths),
        "case_rows": case_rows,
        "proper_score_rows": proper_rows,
        "risk_coverage_rows": risk_rows,
        "counts": counts,
        "claims": {
            "proves": [
                "Gate 5 fixture scoring receipts expose deterministic Brier, log-loss, calibration, and risk-coverage values for covered and abstained predictions",
                "the abstention surface contains one covered prediction row and one abstained prediction row with explicit coverage/selective-accuracy accounting",
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
    write_json(evidence_out, evidence)
    return evidence
