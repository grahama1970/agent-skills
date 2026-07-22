#!/usr/bin/env python3
"""Audit PCTOM-R hard success criteria without overstating scope."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_SUCCESS_CRITERIA_AUDIT"
BLOCKED_STATUS = "BLOCKED_PCTOM_SUCCESS_CRITERIA_AUDIT"
SCHEMA = "persona_dream.research.prospective_tom.success_criteria_audit_receipt.v1"
REQUIRED_GOAL_COVERAGE_IDS = 15


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _stable_json_sha256(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _load_json(path: Path, errors: list[str], label: str) -> Any:
    if not path.exists():
        errors.append(f"missing_{label}:{path}")
        return None
    if path.is_symlink():
        errors.append(f"symlink_{label}:{path}")
        return None
    if not path.is_file():
        errors.append(f"{label}_not_file:{path}")
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append(f"malformed_{label}:{path}:{exc}")
        return None


def _num(value: Any) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _status_pass(receipt: dict[str, Any], expected: str | None = None) -> bool:
    status = receipt.get("status")
    if expected is not None:
        return status == expected
    return isinstance(status, str) and status.startswith("PASS_")


def _forbidden_write_count(receipt: dict[str, Any]) -> int:
    total = 0
    for key in (
        "actual_provider_call_attempts",
        "provider_calls",
        "provider_call_count",
        "canonical_memory_writes",
        "identity_writes",
        "source_memory_writes",
        "canonical_write_violations",
        "identity_write_violations",
        "source_memory_write_violations",
    ):
        value = receipt.get(key)
        if isinstance(value, bool):
            total += int(value)
        elif isinstance(value, int):
            total += value
    return total


def _receipt_ref(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path),
        "status": receipt.get("status"),
        "schema": receipt.get("schema"),
        "mocked": receipt.get("mocked"),
        "live": receipt.get("live"),
        "fixture_backed": receipt.get("fixture_backed"),
        "human_content_judgment_required": receipt.get("human_content_judgment_required"),
        "llm_judge_used": receipt.get("llm_judge_used"),
        "file_sha256": _file_sha256(path),
        "receipt_sha256": receipt.get("receipt_sha256"),
    }


def run(
    *,
    prediction_receipt_path: Path,
    planning_receipt_path: Path,
    goal_coverage_receipt_path: Path,
    repeated_full64_receipt_path: Path | None,
    calibration_abstention_receipt_path: Path | None,
    unsupported_abstention_receipt_path: Path | None,
    output_root: Path,
    receipt_out: Path,
    fixture_backed: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    errors: list[str] = []
    prediction_receipt_path = prediction_receipt_path.resolve()
    planning_receipt_path = planning_receipt_path.resolve()
    goal_coverage_receipt_path = goal_coverage_receipt_path.resolve()
    repeated_full64_receipt_path = repeated_full64_receipt_path.resolve() if repeated_full64_receipt_path else None
    calibration_abstention_receipt_path = (
        calibration_abstention_receipt_path.resolve() if calibration_abstention_receipt_path else None
    )
    unsupported_abstention_receipt_path = (
        unsupported_abstention_receipt_path.resolve() if unsupported_abstention_receipt_path else None
    )
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    prediction = _load_json(prediction_receipt_path, errors, "prediction_receipt")
    planning = _load_json(planning_receipt_path, errors, "planning_receipt")
    coverage = _load_json(goal_coverage_receipt_path, errors, "goal_coverage_receipt")
    repeated = (
        _load_json(repeated_full64_receipt_path, errors, "repeated_full64_receipt")
        if repeated_full64_receipt_path
        else None
    )
    calibration_abstention = (
        _load_json(calibration_abstention_receipt_path, errors, "calibration_abstention_receipt")
        if calibration_abstention_receipt_path
        else None
    )
    unsupported_abstention = (
        _load_json(unsupported_abstention_receipt_path, errors, "unsupported_abstention_receipt")
        if unsupported_abstention_receipt_path
        else None
    )
    prediction = prediction if isinstance(prediction, dict) else {}
    planning = planning if isinstance(planning, dict) else {}
    coverage = coverage if isinstance(coverage, dict) else {}
    repeated = repeated if isinstance(repeated, dict) else None
    calibration_abstention = calibration_abstention if isinstance(calibration_abstention, dict) else None
    unsupported_abstention = unsupported_abstention if isinstance(unsupported_abstention, dict) else None

    if not _status_pass(prediction, "PASS_PCTOM_SEALED_TEST_STATISTICAL_CONFIDENCE"):
        errors.append(f"prediction_receipt_status_not_expected:{prediction.get('status')}")
    if prediction.get("mocked") is not False:
        errors.append(f"prediction_receipt_mocked_not_false:{prediction.get('mocked')}")
    if prediction.get("live") is not False:
        errors.append(f"prediction_receipt_live_not_false:{prediction.get('live')}")
    if prediction.get("llm_judge_used") is True:
        errors.append("prediction_receipt_llm_judge_used_true")
    if prediction.get("human_content_judgment_required") is True:
        errors.append("prediction_receipt_human_content_judgment_required_true")
    if _forbidden_write_count(prediction):
        errors.append("prediction_receipt_forbidden_write_counter_nonzero")

    p_metrics = prediction.get("metrics") if isinstance(prediction.get("metrics"), dict) else {}
    p_counts = prediction.get("counts") if isinstance(prediction.get("counts"), dict) else {}
    primary_metric = p_metrics.get("primary_metric")
    primary_baseline = p_metrics.get("primary_baseline_condition")
    belief_ci = (
        p_metrics.get("paired_delta_confidence_intervals", {}).get("belief_brier")
        if isinstance(p_metrics.get("paired_delta_confidence_intervals"), dict)
        else None
    )
    belief_ci = belief_ci if isinstance(belief_ci, dict) else {}
    belief_upper = _num(belief_ci.get("upper"))
    belief_mean = _num(belief_ci.get("mean"))
    prediction_benefit_with_confidence = bool(
        primary_metric == "belief_brier"
        and primary_baseline in {"M", "R", "D"}
        and belief_upper is not None
        and belief_upper < 0
        and belief_mean is not None
        and belief_mean < 0
        and p_counts.get("episodes_consumed") == 64
        and p_counts.get("cases") == 256
        and p_counts.get("paired_delta_counts", {}).get("belief_brier") == 64
    )
    if not prediction_benefit_with_confidence:
        errors.append(
            "prediction_benefit_with_confidence_not_proven:"
            f"metric={primary_metric}:baseline={primary_baseline}:mean={belief_mean}:upper={belief_upper}:"
            f"episodes={p_counts.get('episodes_consumed')}:cases={p_counts.get('cases')}"
        )

    if not _status_pass(planning, "PASS_LIVE_TAU_PCTOM_BALANCED_PLANNING_REPLICATION"):
        errors.append(f"planning_receipt_status_not_expected:{planning.get('status')}")
    if planning.get("mocked") is not False:
        errors.append(f"planning_receipt_mocked_not_false:{planning.get('mocked')}")
    if planning.get("live") is not True:
        errors.append(f"planning_receipt_live_not_true:{planning.get('live')}")
    if planning.get("llm_judge_used") is True:
        errors.append("planning_receipt_llm_judge_used_true")
    if planning.get("human_content_judgment_required") is True:
        errors.append("planning_receipt_human_content_judgment_required_true")
    if _forbidden_write_count(planning):
        errors.append("planning_receipt_forbidden_write_counter_nonzero")

    pl_metrics = planning.get("metrics") if isinstance(planning.get("metrics"), dict) else {}
    pl_counts = planning.get("counts") if isinstance(planning.get("counts"), dict) else {}
    comparison = pl_metrics.get("comparison") if isinstance(pl_metrics.get("comparison"), dict) else {}
    planning_summary = pl_metrics.get("planning_summary") if isinstance(pl_metrics.get("planning_summary"), dict) else {}
    planning_ci = (
        planning_summary.get("planning_regret_ci") if isinstance(planning_summary.get("planning_regret_ci"), dict) else {}
    )
    planning_upper = _num(planning_ci.get("upper"))
    planning_mean = _num(planning_ci.get("mean"))
    planning_delta = _num(comparison.get("cd_minus_strongest_baseline"))
    planning_benefit_with_confidence = bool(
        planning.get("planning_benefit_with_confidence") is True
        and planning_summary.get("planning_benefit_with_confidence") is True
        and comparison.get("metric") == "planning_regret"
        and comparison.get("lower_is_better") is True
        and planning_upper is not None
        and planning_upper < 0
        and planning_mean is not None
        and planning_mean < 0
        and planning_delta is not None
        and planning_delta < 0
        and pl_counts.get("episodes") == 32
        and pl_counts.get("cases") == 128
    )
    if not planning_benefit_with_confidence:
        errors.append(
            "planning_benefit_with_confidence_not_proven:"
            f"mean={planning_mean}:upper={planning_upper}:delta={planning_delta}:"
            f"episodes={pl_counts.get('episodes')}:cases={pl_counts.get('cases')}"
        )

    if not _status_pass(coverage, "PASS_PCTOM_GOAL_COVERAGE"):
        errors.append(f"goal_coverage_status_not_expected:{coverage.get('status')}")
    c_counts = coverage.get("counts") if isinstance(coverage.get("counts"), dict) else {}
    coverage_complete = bool(
        c_counts.get("required_coverage_ids") == REQUIRED_GOAL_COVERAGE_IDS
        and c_counts.get("coverage_ids_seen") == REQUIRED_GOAL_COVERAGE_IDS
        and c_counts.get("coverage_ids_missing") == 0
        and c_counts.get("negative_evidence_receipts", 0) >= 10
        and c_counts.get("live_positive_evidence_receipts", 0) >= 16
        and coverage.get("mocked") is False
    )
    if not coverage_complete:
        errors.append(f"goal_coverage_incomplete:{c_counts}")

    repeated_same_scope_success = False
    repeated_summary: dict[str, Any] | None = None
    if repeated is not None:
        if not _status_pass(repeated, "PASS_LIVE_TAU_PCTOM_FULL64_REPEATED_RUN_SUMMARY"):
            errors.append(f"repeated_full64_status_not_expected:{repeated.get('status')}")
        if repeated.get("mocked") is not False:
            errors.append(f"repeated_full64_mocked_not_false:{repeated.get('mocked')}")
        if repeated.get("live") is not True:
            errors.append(f"repeated_full64_live_not_true:{repeated.get('live')}")
        if repeated.get("llm_judge_used") is True:
            errors.append("repeated_full64_llm_judge_used_true")
        if repeated.get("human_content_judgment_required") is True:
            errors.append("repeated_full64_human_content_judgment_required_true")
        if _forbidden_write_count(repeated):
            errors.append("repeated_full64_forbidden_write_counter_nonzero")

        r_counts = repeated.get("counts") if isinstance(repeated.get("counts"), dict) else {}
        r_metrics = repeated.get("metrics") if isinstance(repeated.get("metrics"), dict) else {}
        belief = r_metrics.get("belief_brier") if isinstance(r_metrics.get("belief_brier"), dict) else {}
        planning_metric = r_metrics.get("planning_regret") if isinstance(r_metrics.get("planning_regret"), dict) else {}
        belief_ci = (
            belief.get("cd_minus_strongest_baseline_ci")
            if isinstance(belief.get("cd_minus_strongest_baseline_ci"), dict)
            else {}
        )
        repeated_planning_ci = (
            planning_metric.get("cd_minus_strongest_baseline_ci")
            if isinstance(planning_metric.get("cd_minus_strongest_baseline_ci"), dict)
            else {}
        )
        checks = repeated.get("checks") if isinstance(repeated.get("checks"), dict) else {}
        repeated_same_scope_success = bool(
            belief.get("benefit_with_confidence") is True
            and planning_metric.get("benefit_with_confidence") is True
            and _num(belief_ci.get("upper")) is not None
            and _num(belief_ci.get("upper")) < 0
            and _num(repeated_planning_ci.get("upper")) is not None
            and _num(repeated_planning_ci.get("upper")) < 0
            and belief.get("paired_rows") == 128
            and planning_metric.get("paired_rows") == 128
            and r_counts.get("source_roots") == 2
            and r_counts.get("accepted_source_runs") == 2
            and r_counts.get("episode_metric_rows") == 128
            and r_counts.get("tau_live_calls_consumed") == 512
            and checks.get("all_source_runs_passed") is True
            and checks.get("all_source_runs_gate0_attributed") is True
            and checks.get("all_source_runs_have_64_metric_rows") is True
            and checks.get("unsupported_writes_absent") is True
        )
        if not repeated_same_scope_success:
            errors.append(
                "repeated_full64_same_scope_success_not_proven:"
                f"belief={belief}:planning={planning_metric}:counts={r_counts}:checks={checks}"
            )
        repeated_summary = {
            "scope": "two live Tau full64 Gate 0-attributed sealed-test runs",
            "source_roots": r_counts.get("source_roots"),
            "accepted_source_runs": r_counts.get("accepted_source_runs"),
            "episode_metric_rows": r_counts.get("episode_metric_rows"),
            "tau_live_calls_consumed": r_counts.get("tau_live_calls_consumed"),
            "belief_brier_mean": belief_ci.get("mean"),
            "belief_brier_ci_upper": belief_ci.get("upper"),
            "planning_regret_mean": repeated_planning_ci.get("mean"),
            "planning_regret_ci_upper": repeated_planning_ci.get("upper"),
            "belief_brier_benefit_with_confidence": belief.get("benefit_with_confidence"),
            "planning_regret_benefit_with_confidence": planning_metric.get("benefit_with_confidence"),
        }

    calibration_surface_audited = False
    unsupported_evidence_abstention_exercised = False
    calibration_summary: dict[str, Any] | None = None
    if calibration_abstention is not None:
        if not _status_pass(calibration_abstention, "PASS_PCTOM_CALIBRATION_ABSTENTION_AUDIT"):
            errors.append(f"calibration_abstention_status_not_expected:{calibration_abstention.get('status')}")
        if calibration_abstention.get("mocked") is not False:
            errors.append(f"calibration_abstention_mocked_not_false:{calibration_abstention.get('mocked')}")
        if calibration_abstention.get("live") is not True:
            errors.append(f"calibration_abstention_live_not_true:{calibration_abstention.get('live')}")
        if calibration_abstention.get("llm_judge_used") is True:
            errors.append("calibration_abstention_llm_judge_used_true")
        if calibration_abstention.get("human_content_judgment_required") is True:
            errors.append("calibration_abstention_human_content_judgment_required_true")
        if _forbidden_write_count(calibration_abstention):
            errors.append("calibration_abstention_forbidden_write_counter_nonzero")
        ca_counts = calibration_abstention.get("counts") if isinstance(calibration_abstention.get("counts"), dict) else {}
        ca_metrics = calibration_abstention.get("metrics") if isinstance(calibration_abstention.get("metrics"), dict) else {}
        ca_checks = calibration_abstention.get("checks") if isinstance(calibration_abstention.get("checks"), dict) else {}
        calibration_surface_audited = bool(
            ca_counts.get("source_roots") == 2
            and ca_counts.get("raw_case_rows") == 512
            and ca_counts.get("calibration_rows") == 512
            and ca_counts.get("risk_coverage_rows") == 512
            and ca_counts.get("calibration_bucket_items") == 1536
            and ca_checks.get("source_mode_live_hash_bound") is True
            and ca_checks.get("calibration_present_for_all_rows") is True
            and ca_checks.get("risk_coverage_present_for_all_rows") is True
            and ca_checks.get("audited_rows_match_expected_shape") is True
        )
        if not calibration_surface_audited:
            errors.append(
                "calibration_surface_not_audited:"
                f"counts={ca_counts}:metrics={ca_metrics}:checks={ca_checks}"
            )
        calibration_summary = {
            "scope": "two live Tau full64 Gate 0-attributed Gate 5 case indexes",
            "source_roots": ca_counts.get("source_roots"),
            "raw_case_rows": ca_counts.get("raw_case_rows"),
            "calibration_rows": ca_counts.get("calibration_rows"),
            "risk_coverage_rows": ca_counts.get("risk_coverage_rows"),
            "abstained_rows": ca_counts.get("abstained_rows"),
            "mean_expected_calibration_error": ca_metrics.get("mean_expected_calibration_error"),
            "mean_coverage": ca_metrics.get("mean_coverage"),
            "mean_selective_accuracy": ca_metrics.get("mean_selective_accuracy"),
            "abstention_observed": ca_metrics.get("abstention_observed"),
            "calibration_surface_audited": calibration_surface_audited,
            "abstention_observed_in_full64_surface": ca_metrics.get("abstention_observed"),
        }

    unsupported_summary: dict[str, Any] | None = None
    if unsupported_abstention is not None:
        if not _status_pass(unsupported_abstention, "PASS_PCTOM_UNSUPPORTED_EVIDENCE_ABSTENTION"):
            errors.append(f"unsupported_abstention_status_not_expected:{unsupported_abstention.get('status')}")
        if unsupported_abstention.get("mocked") is not False:
            errors.append(f"unsupported_abstention_mocked_not_false:{unsupported_abstention.get('mocked')}")
        if unsupported_abstention.get("llm_judge_used") is True:
            errors.append("unsupported_abstention_llm_judge_used_true")
        if unsupported_abstention.get("human_content_judgment_required") is True:
            errors.append("unsupported_abstention_human_content_judgment_required_true")
        if _forbidden_write_count(unsupported_abstention):
            errors.append("unsupported_abstention_forbidden_write_counter_nonzero")
        ua_counts = unsupported_abstention.get("counts") if isinstance(unsupported_abstention.get("counts"), dict) else {}
        ua_checks = unsupported_abstention.get("checks") if isinstance(unsupported_abstention.get("checks"), dict) else {}
        unsupported_evidence_abstention_exercised = bool(
            ua_counts.get("families") == 4
            and ua_counts.get("case_rows") == 4
            and ua_counts.get("unsupported_distribution_rows") == 8
            and ua_counts.get("gate2_pass") == 4
            and ua_counts.get("gate5_pass") == 4
            and ua_counts.get("risk_coverage_rows") == 4
            and ua_counts.get("abstained_rows") == 4
            and ua_checks.get("four_families_exercised") is True
            and ua_checks.get("gate2_unsupported_abstention_passed") is True
            and ua_checks.get("gate5_abstention_scored") is True
            and ua_checks.get("unsupported_evidence_abstention_exercised") is True
            and ua_checks.get("unsupported_writes_absent") is True
        )
        if not unsupported_evidence_abstention_exercised:
            errors.append(f"unsupported_evidence_abstention_not_exercised:counts={ua_counts}:checks={ua_checks}")
        unsupported_summary = {
            "scope": "deterministic unsupported-evidence abstention exercise over four social episode families",
            "families": ua_counts.get("families"),
            "case_rows": ua_counts.get("case_rows"),
            "unsupported_distribution_rows": ua_counts.get("unsupported_distribution_rows"),
            "gate2_pass": ua_counts.get("gate2_pass"),
            "gate5_pass": ua_counts.get("gate5_pass"),
            "risk_coverage_rows": ua_counts.get("risk_coverage_rows"),
            "abstained_rows": ua_counts.get("abstained_rows"),
            "unsupported_evidence_abstention_exercised": unsupported_evidence_abstention_exercised,
        }

    same_scope_joint_success = (
        prediction_receipt_path == planning_receipt_path
        and prediction_benefit_with_confidence
        and planning_benefit_with_confidence
    ) or repeated_same_scope_success
    full_hard_success_criteria_met = bool(
        same_scope_joint_success
        and coverage_complete
        and prediction_benefit_with_confidence
        and planning_benefit_with_confidence
        and calibration_surface_audited
        and unsupported_evidence_abstention_exercised
    )

    criteria = {
        "prediction_benefit": {
            "status": "SCOPED_PROVEN",
            "scope": "deterministic sealed64 full split",
            "metric": "belief_brier",
            "baseline_condition": primary_baseline,
            "mean_cd_minus_baseline": belief_mean,
            "ci_upper": belief_upper,
            "episodes": p_counts.get("episodes_consumed"),
            "cases": p_counts.get("cases"),
        },
        "planning_benefit": {
            "status": "SCOPED_PROVEN",
            "scope": "live Tau balanced variants 17-24 slice",
            "metric": "planning_regret",
            "mean_cd_minus_baseline": planning_mean,
            "ci_upper": planning_upper,
            "episodes": pl_counts.get("episodes"),
            "cases": pl_counts.get("cases"),
        },
        "pipeline_reliability": {
            "status": "SCOPED_PROVEN",
            "scope": "current goal coverage manifest",
            "coverage_ids_seen": c_counts.get("coverage_ids_seen"),
            "negative_evidence_receipts": c_counts.get("negative_evidence_receipts"),
            "live_positive_evidence_receipts": c_counts.get("live_positive_evidence_receipts"),
        },
        "same_scope_joint_prediction_and_planning": {
            "status": "NOT_PROVEN" if not same_scope_joint_success else "PROVEN",
            "reason": (
                "prediction benefit and planning benefit are currently proven by different receipts/scopes"
                if not same_scope_joint_success
                else "same-scope repeated full64 evidence proves prediction and planning benefit"
            ),
            "repeated_full64": repeated_summary,
        },
        "calibration_and_abstention": {
            "status": (
                "PROVEN"
                if calibration_surface_audited and unsupported_evidence_abstention_exercised
                else "PARTIAL_PROVEN"
                if calibration_surface_audited
                else "NOT_PROVEN"
            ),
            "reason": (
                "calibration and risk-coverage fields are audited, but unsupported-evidence abstention rows were not observed"
                if calibration_surface_audited and not unsupported_evidence_abstention_exercised
                else "calibration and abstention evidence is missing or failed"
                if not calibration_surface_audited
                else "calibration/risk-coverage and abstention behavior were both exercised"
            ),
            "calibration_abstention": calibration_summary,
            "unsupported_abstention": unsupported_summary,
        },
    }

    receipt = {
        "schema": SCHEMA,
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "generated_at": _now_iso(),
        "mocked": False,
        "live": False,
        "fixture_backed": fixture_backed,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "prediction_receipt": _receipt_ref(prediction_receipt_path, prediction),
        "planning_receipt": _receipt_ref(planning_receipt_path, planning),
        "goal_coverage_receipt": _receipt_ref(goal_coverage_receipt_path, coverage),
        "repeated_full64_receipt": _receipt_ref(repeated_full64_receipt_path, repeated)
        if repeated_full64_receipt_path is not None and isinstance(repeated, dict)
        else None,
        "calibration_abstention_receipt": _receipt_ref(calibration_abstention_receipt_path, calibration_abstention)
        if calibration_abstention_receipt_path is not None and isinstance(calibration_abstention, dict)
        else None,
        "unsupported_abstention_receipt": _receipt_ref(unsupported_abstention_receipt_path, unsupported_abstention)
        if unsupported_abstention_receipt_path is not None and isinstance(unsupported_abstention, dict)
        else None,
        "criteria": criteria,
        "summary": {
            "prediction_benefit_with_confidence": prediction_benefit_with_confidence,
            "planning_benefit_with_confidence": planning_benefit_with_confidence,
            "goal_coverage_complete": coverage_complete,
            "repeated_full64_same_scope_success": repeated_same_scope_success,
            "calibration_surface_audited": calibration_surface_audited,
            "unsupported_evidence_abstention_exercised": unsupported_evidence_abstention_exercised,
            "same_scope_joint_success": same_scope_joint_success,
            "full_hard_success_criteria_met": full_hard_success_criteria_met,
        },
        "errors": errors,
        "claims": {
            "proves": [
                "current evidence has confidence-bound prediction benefit in deterministic sealed64 scoring",
                "current evidence has confidence-bound live Tau planning benefit on the balanced held-out slice",
                "current repeated full64 evidence has same-scope confidence-bound prediction and planning benefit when repeated_full64_same_scope_success is true",
                "current calibration/abstention evidence has a full64 Gate 5 calibration and risk-coverage metric surface when calibration_surface_audited is true",
                "current unsupported-abstention evidence exercises unsupported factual ToM hypotheses through Gate 2 and Gate 5 when unsupported_evidence_abstention_exercised is true",
                "current evidence has mapped reliability and fail-closed coverage through the goal coverage receipt",
            ],
            "does_not_prove": (
                []
                if unsupported_evidence_abstention_exercised
                else ["unsupported-evidence abstention behavior"]
            )
            + [
                "paid provider execution",
                "semantic dream quality",
                "complete Phase 01-16 media runtime execution",
            ],
        },
        "elapsed_s": round(time.monotonic() - started, 6),
    }
    receipt["receipt_sha256"] = _stable_json_sha256({k: v for k, v in receipt.items() if k != "receipt_sha256"})
    receipt_out.parent.mkdir(parents=True, exist_ok=True)
    receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prediction-receipt", required=True)
    parser.add_argument("--planning-receipt", required=True)
    parser.add_argument("--goal-coverage-receipt", required=True)
    parser.add_argument("--repeated-full64-receipt")
    parser.add_argument("--calibration-abstention-receipt")
    parser.add_argument("--unsupported-abstention-receipt")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--receipt-out", required=True)
    parser.add_argument("--fixture-backed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run(
        prediction_receipt_path=Path(args.prediction_receipt),
        planning_receipt_path=Path(args.planning_receipt),
        goal_coverage_receipt_path=Path(args.goal_coverage_receipt),
        repeated_full64_receipt_path=Path(args.repeated_full64_receipt) if args.repeated_full64_receipt else None,
        calibration_abstention_receipt_path=Path(args.calibration_abstention_receipt)
        if args.calibration_abstention_receipt
        else None,
        unsupported_abstention_receipt_path=Path(args.unsupported_abstention_receipt)
        if args.unsupported_abstention_receipt
        else None,
        output_root=Path(args.output_root),
        receipt_out=Path(args.receipt_out),
        fixture_backed=args.fixture_backed,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(f"{receipt['status']} {receipt['receipt_path']}")
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
