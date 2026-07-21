#!/usr/bin/env python3
"""Audit class-separated cooperation exposure from a live Tau exposure/contrast slice."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_COOPERATION_CLASS_SEPARATED_EXPOSURE_AUDIT"
BLOCKED_STATUS = "BLOCKED_PCTOM_COOPERATION_CLASS_SEPARATED_EXPOSURE_AUDIT"
LIVE_SLICE_PASS_STATUS = "PASS_LIVE_TAU_PCTOM_COOPERATION_EXPOSURE_CONTRAST_SLICE"
KEEP_CLASS = "KEEP_COOPERATION_POSITIVE"
AVOID_CLASS = "AVOID_OR_UNSAFE_COOPERATION_CONTRAST"
OFFER_ACTION = "OFFER_COOPERATION"
COUNTERPART_OFFER = "KAI_OFFERS_COOPERATION"
ZERO_WRITE_KEYS = (
    "memory_write_attempts",
    "provider_call_attempts",
    "canonical_memory_write_attempts",
    "identity_write_attempts",
    "source_memory_write_attempts",
)


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


def _pre_outcome_leaks(value: Any) -> bool:
    allowed_keys = {"uses_outcome_or_oracle"}
    forbidden_key_tokens = ("actual_next_action", "oracle_action", "outcome_visible", "observed_outcome")
    if isinstance(value, dict):
        for key, child in value.items():
            key_text = str(key)
            if key_text not in allowed_keys and any(token in key_text.lower() for token in forbidden_key_tokens):
                return True
            if key_text == "uses_outcome_or_oracle" and child is not False:
                return True
            if _pre_outcome_leaks(child):
                return True
    if isinstance(value, list):
        return any(_pre_outcome_leaks(item) for item in value)
    return False


def _rows_by_class(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets = {KEEP_CLASS: [], AVOID_CLASS: [], "UNKNOWN": []}
    for row in rows:
        contrast_class = row.get("contrast_class")
        if contrast_class in buckets:
            buckets[str(contrast_class)].append(row)
        else:
            buckets["UNKNOWN"].append(row)
    return buckets


def _count_actions(rows: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        action = row.get(field)
        if isinstance(action, str):
            counts[action] = counts.get(action, 0) + 1
    return counts


def _validate_inputs(
    *,
    live_slice_receipt: dict[str, Any],
    rows_doc: dict[str, Any],
    summary_doc: dict[str, Any],
    require_hashes: bool,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    errors: list[str] = []
    if live_slice_receipt.get("status") != LIVE_SLICE_PASS_STATUS:
        errors.append(f"live_slice_status_not_pass:{live_slice_receipt.get('status')}")
    if live_slice_receipt.get("mocked") is not False:
        errors.append("live_slice_mocked_not_false")
    if live_slice_receipt.get("live") is not True:
        errors.append("live_slice_live_not_true")
    if live_slice_receipt.get("fixture_backed") is not False:
        errors.append("live_slice_fixture_backed_not_false")
    if live_slice_receipt.get("planning_benefit_with_confidence") is not False:
        errors.append("planning_benefit_with_confidence_claimed")
    if live_slice_receipt.get("llm_judge_used") is not False:
        errors.append("llm_judge_used")
    if live_slice_receipt.get("human_content_judgment_required") is not False:
        errors.append("human_content_judgment_required")
    for key in ZERO_WRITE_KEYS:
        if live_slice_receipt.get(key) != 0:
            errors.append(f"{key}_not_zero:{live_slice_receipt.get(key)}")

    rows = rows_doc.get("rows") if isinstance(rows_doc.get("rows"), list) else []
    if not isinstance(rows_doc.get("rows"), list):
        errors.append("rows_doc_rows_not_list")
    if not rows:
        errors.append("rows_empty")
    summary_counts = {
        "rows": summary_doc.get("rows"),
        "keep_cooperation_positive_rows": summary_doc.get("keep_cooperation_positive_rows"),
        "avoid_or_unsafe_cooperation_contrast_rows": summary_doc.get("avoid_or_unsafe_cooperation_contrast_rows"),
        "offer_cooperation_affordance_rows": summary_doc.get("offer_cooperation_affordance_rows"),
        "cd_action_change_count": summary_doc.get("cd_action_change_count"),
        "cd_offer_cooperation_candidates": summary_doc.get("cd_offer_cooperation_candidates"),
    }
    receipt_counts = live_slice_receipt.get("counts") if isinstance(live_slice_receipt.get("counts"), dict) else {}
    for key, summary_value in summary_counts.items():
        if receipt_counts.get(key) != summary_value and key != "rows":
            errors.append(f"summary_receipt_count_mismatch:{key}:{summary_value}:{receipt_counts.get(key)}")
    if receipt_counts.get("rows") != len(rows) or summary_doc.get("rows") != len(rows):
        errors.append(f"row_count_mismatch:{len(rows)}:{receipt_counts.get('rows')}:{summary_doc.get('rows')}")

    buckets = _rows_by_class(rows)
    keep_rows = buckets[KEEP_CLASS]
    avoid_rows = buckets[AVOID_CLASS]
    unknown_rows = buckets["UNKNOWN"]
    if unknown_rows:
        errors.append(f"unknown_contrast_class_rows:{len(unknown_rows)}")
    if not keep_rows:
        errors.append("missing_keep_rows")
    if not avoid_rows:
        errors.append("missing_avoid_rows")

    keep_offer_rows = [row for row in keep_rows if row.get("cd_original_action") == OFFER_ACTION]
    avoid_offer_rows = [row for row in avoid_rows if row.get("cd_original_action") == OFFER_ACTION]
    keep_counterpart_offer_rows = [
        row
        for row in keep_rows
        if isinstance(row.get("cd_pre_outcome_rule_inputs"), dict)
        and row["cd_pre_outcome_rule_inputs"].get("selected_from_predicted_counterpart_action") == COUNTERPART_OFFER
    ]
    avoid_counterpart_offer_rows = [
        row
        for row in avoid_rows
        if isinstance(row.get("cd_pre_outcome_rule_inputs"), dict)
        and row["cd_pre_outcome_rule_inputs"].get("selected_from_predicted_counterpart_action") == COUNTERPART_OFFER
    ]
    changed_rows = [row for row in rows if row.get("cd_action_changed_by_rule") is True]
    pre_outcome_leak_rows = [
        row.get("episode_id")
        for row in rows
        if _pre_outcome_leaks(row.get("cd_pre_outcome_rule_inputs"))
    ]
    if len(keep_offer_rows) != len(keep_rows):
        errors.append(f"keep_rows_not_all_offer_cooperation:{len(keep_offer_rows)}:{len(keep_rows)}")
    if avoid_offer_rows:
        errors.append(f"avoid_rows_offer_cooperation:{len(avoid_offer_rows)}")
    if len(keep_counterpart_offer_rows) != len(keep_rows):
        errors.append(f"keep_rows_not_all_counterpart_offer:{len(keep_counterpart_offer_rows)}:{len(keep_rows)}")
    if avoid_counterpart_offer_rows:
        errors.append(f"avoid_rows_select_counterpart_offer:{len(avoid_counterpart_offer_rows)}")
    if changed_rows:
        errors.append(f"threshold_rule_changed_actions:{len(changed_rows)}")
    if pre_outcome_leak_rows:
        errors.append(f"pre_outcome_rule_inputs_leak:{pre_outcome_leak_rows}")

    class_separated_cd_discrimination_observed = bool(keep_rows and avoid_rows) and (
        len(keep_offer_rows) == len(keep_rows)
        and not avoid_offer_rows
        and len(keep_counterpart_offer_rows) == len(keep_rows)
        and not avoid_counterpart_offer_rows
        and not pre_outcome_leak_rows
    )
    unsafe_offer_suppression_exercised = bool(avoid_offer_rows and changed_rows)
    feature_split_acceptance_allowed = bool(class_separated_cd_discrimination_observed and unsafe_offer_suppression_exercised)
    if feature_split_acceptance_allowed:
        conclusion = "FEATURE_SPLIT_PREREQUISITES_MET"
        missing_prerequisites: list[str] = []
    elif class_separated_cd_discrimination_observed:
        conclusion = "CD_CLASS_SEPARATED_COOPERATION_OBSERVED_FEATURE_SPLIT_STILL_BLOCKED"
        missing_prerequisites = ["missing_unsafe_offer_suppression_candidate"]
    else:
        conclusion = "CLASS_SEPARATED_COOPERATION_EXPOSURE_NOT_ESTABLISHED"
        missing_prerequisites = ["missing_class_separated_cd_discrimination"]

    audit = {
        "schema": "persona_dream.research.prospective_tom.cooperation_class_separated_exposure_audit.v1",
        "conclusion": conclusion,
        "class_separated_cd_discrimination_observed": class_separated_cd_discrimination_observed,
        "unsafe_offer_suppression_exercised": unsafe_offer_suppression_exercised,
        "feature_split_acceptance_allowed": feature_split_acceptance_allowed,
        "missing_prerequisites": missing_prerequisites,
        "observed": {
            "rows": len(rows),
            "keep_rows": len(keep_rows),
            "avoid_or_unsafe_rows": len(avoid_rows),
            "keep_offer_rows": len(keep_offer_rows),
            "avoid_offer_rows": len(avoid_offer_rows),
            "keep_counterpart_offer_rows": len(keep_counterpart_offer_rows),
            "avoid_counterpart_offer_rows": len(avoid_counterpart_offer_rows),
            "threshold_action_change_rows": len(changed_rows),
            "cd_original_actions_by_class": {
                KEEP_CLASS: _count_actions(keep_rows, "cd_original_action"),
                AVOID_CLASS: _count_actions(avoid_rows, "cd_original_action"),
            },
            "cd_intervened_actions_by_class": {
                KEEP_CLASS: _count_actions(keep_rows, "cd_intervened_action"),
                AVOID_CLASS: _count_actions(avoid_rows, "cd_intervened_action"),
            },
        },
        "claims": {
            "proves": [
                "the live Tau exposure/contrast slice contains class-separated CD cooperation behavior",
                "CD selected OFFER_COOPERATION on keep-cooperation rows and avoided OFFER_COOPERATION on avoid/unsafe rows",
                "the audit used sealed pre-outcome rule inputs and detected no oracle/outcome input leakage",
                "replacement feature-split acceptance remains blocked because no unsafe OFFER_COOPERATION suppression candidate was exercised",
            ],
            "does_not_prove": [
                "a replacement cooperation feature split is valid",
                "confidence-bounded CD planning benefit",
                "broad held-out planning benefit",
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    checks = {
        "live_slice_receipt_passed": live_slice_receipt.get("status") == LIVE_SLICE_PASS_STATUS,
        "live_not_mocked": live_slice_receipt.get("live") is True and live_slice_receipt.get("mocked") is False,
        "zero_unsupported_writes": all(live_slice_receipt.get(key) == 0 for key in ZERO_WRITE_KEYS),
        "no_judgment_used": live_slice_receipt.get("llm_judge_used") is False
        and live_slice_receipt.get("human_content_judgment_required") is False,
        "row_counts_match_receipt_and_summary": "row_count_mismatch" not in " ".join(errors),
        "keep_rows_all_offer_cooperation": len(keep_offer_rows) == len(keep_rows) and bool(keep_rows),
        "avoid_rows_no_offer_cooperation": not avoid_offer_rows and bool(avoid_rows),
        "keep_rows_all_selected_counterpart_offer": len(keep_counterpart_offer_rows) == len(keep_rows) and bool(keep_rows),
        "avoid_rows_no_selected_counterpart_offer": not avoid_counterpart_offer_rows and bool(avoid_rows),
        "threshold_rule_made_no_action_changes": not changed_rows,
        "pre_outcome_inputs_exclude_oracle_or_outcome": not pre_outcome_leak_rows,
        "class_separated_cd_discrimination_observed": class_separated_cd_discrimination_observed,
        "feature_split_acceptance_allowed": feature_split_acceptance_allowed,
        "feature_split_blocked_without_unsafe_offer_suppression": not feature_split_acceptance_allowed
        and "missing_unsafe_offer_suppression_candidate" in missing_prerequisites,
    }

    if require_hashes:
        rows_path = Path(str(live_slice_receipt.get("rows_path", "")))
        summary_path = Path(str(live_slice_receipt.get("summary_path", "")))
        if not rows_path.exists():
            errors.append(f"rows_path_missing:{rows_path}")
        elif live_slice_receipt.get("rows_sha256") != _file_sha256(rows_path):
            errors.append("rows_sha256_mismatch")
        if not summary_path.exists():
            errors.append(f"summary_path_missing:{summary_path}")
        elif live_slice_receipt.get("summary_sha256") != _file_sha256(summary_path):
            errors.append("summary_sha256_mismatch")
        expected_receipt_sha = live_slice_receipt.get("receipt_sha256")
        actual_receipt_sha = _stable_json_sha256(
            {key: value for key, value in live_slice_receipt.items() if key != "receipt_sha256"}
        )
        if expected_receipt_sha != actual_receipt_sha:
            errors.append("live_slice_receipt_sha256_mismatch")

    return errors, checks, audit


def _negative_checks(
    *,
    live_slice_receipt: dict[str, Any],
    rows_doc: dict[str, Any],
    summary_doc: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}

    bad_receipt = copy.deepcopy(live_slice_receipt)
    bad_receipt["status"] = "BLOCKED_LIVE_TAU_PCTOM_COOPERATION_EXPOSURE_CONTRAST_SLICE"
    errors, checks, _audit = _validate_inputs(
        live_slice_receipt=bad_receipt,
        rows_doc=rows_doc,
        summary_doc=summary_doc,
        require_hashes=False,
    )
    results["live_slice_status_not_pass"] = {
        "failed_closed": any(error.startswith("live_slice_status_not_pass") for error in errors),
        "errors": errors,
        "checks": checks,
    }

    no_keep_offer = copy.deepcopy(rows_doc)
    for row in no_keep_offer.get("rows", []):
        if row.get("contrast_class") == KEEP_CLASS:
            row["cd_original_action"] = "WAIT"
            break
    errors, checks, _audit = _validate_inputs(
        live_slice_receipt=live_slice_receipt,
        rows_doc=no_keep_offer,
        summary_doc=summary_doc,
        require_hashes=False,
    )
    results["missing_keep_offer_cooperation"] = {
        "failed_closed": any(error.startswith("keep_rows_not_all_offer_cooperation") for error in errors),
        "errors": errors,
        "checks": checks,
    }

    avoid_offer = copy.deepcopy(rows_doc)
    for row in avoid_offer.get("rows", []):
        if row.get("contrast_class") == AVOID_CLASS:
            row["cd_original_action"] = OFFER_ACTION
            break
    errors, checks, _audit = _validate_inputs(
        live_slice_receipt=live_slice_receipt,
        rows_doc=avoid_offer,
        summary_doc=summary_doc,
        require_hashes=False,
    )
    results["avoid_row_offer_cooperation"] = {
        "failed_closed": any(error.startswith("avoid_rows_offer_cooperation") for error in errors),
        "errors": errors,
        "checks": checks,
    }

    leak = copy.deepcopy(rows_doc)
    for row in leak.get("rows", []):
        if isinstance(row.get("cd_pre_outcome_rule_inputs"), dict):
            row["cd_pre_outcome_rule_inputs"]["oracle_action"] = OFFER_ACTION
            break
    errors, checks, _audit = _validate_inputs(
        live_slice_receipt=live_slice_receipt,
        rows_doc=leak,
        summary_doc=summary_doc,
        require_hashes=False,
    )
    results["pre_outcome_oracle_leak"] = {
        "failed_closed": any(error.startswith("pre_outcome_rule_inputs_leak") for error in errors),
        "errors": errors,
        "checks": checks,
    }

    broad_claim = copy.deepcopy(live_slice_receipt)
    broad_claim["planning_benefit_with_confidence"] = True
    errors, checks, _audit = _validate_inputs(
        live_slice_receipt=broad_claim,
        rows_doc=rows_doc,
        summary_doc=summary_doc,
        require_hashes=False,
    )
    results["planning_benefit_claim_injected"] = {
        "failed_closed": "planning_benefit_with_confidence_claimed" in errors,
        "errors": errors,
        "checks": checks,
    }
    return results


def run_audit(
    *,
    live_slice_receipt_path: Path,
    output_root: Path,
    receipt_out: Path,
    run_negative_checks: bool = True,
) -> dict[str, Any]:
    started = time.monotonic()
    live_slice_receipt_path = live_slice_receipt_path.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts_root = output_root / "artifacts"
    audit_path = artifacts_root / "cooperation_class_separated_exposure_audit.json"
    negative_path = artifacts_root / "cooperation_class_separated_exposure_negative_checks.json"
    errors: list[str] = []

    live_slice_receipt = _load_json(live_slice_receipt_path, errors, "live_slice_receipt")
    live_slice_receipt = live_slice_receipt if isinstance(live_slice_receipt, dict) else {}
    rows_path = Path(str(live_slice_receipt.get("rows_path", "")))
    summary_path = Path(str(live_slice_receipt.get("summary_path", "")))
    rows_doc = _load_json(rows_path, errors, "rows_doc") if str(rows_path) else None
    rows_doc = rows_doc if isinstance(rows_doc, dict) else {}
    summary_doc = _load_json(summary_path, errors, "summary_doc") if str(summary_path) else None
    summary_doc = summary_doc if isinstance(summary_doc, dict) else {}

    audit_errors, checks, audit = _validate_inputs(
        live_slice_receipt=live_slice_receipt,
        rows_doc=rows_doc,
        summary_doc=summary_doc,
        require_hashes=True,
    )
    errors.extend(audit_errors)
    negative_results = (
        _negative_checks(
            live_slice_receipt=live_slice_receipt,
            rows_doc=rows_doc,
            summary_doc=summary_doc,
        )
        if run_negative_checks
        else {}
    )
    negative_checks_failed_closed = all(result.get("failed_closed") is True for result in negative_results.values())
    if run_negative_checks and not negative_checks_failed_closed:
        errors.append("negative_checks_did_not_fail_closed")

    _write_json(audit_path, audit)
    if run_negative_checks:
        _write_json(
            negative_path,
            {
                "schema": "persona_dream.research.prospective_tom.cooperation_class_separated_exposure_negative_checks.v1",
                "results": negative_results,
            },
        )

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.cooperation_class_separated_exposure_audit_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "input_live_slice_receipt": str(live_slice_receipt_path),
        "input_live_slice_receipt_sha256": _file_sha256(live_slice_receipt_path)
        if live_slice_receipt_path.exists()
        else None,
        "audit_path": str(audit_path),
        "audit_sha256": _file_sha256(audit_path) if audit_path.exists() else None,
        "negative_checks_path": str(negative_path) if run_negative_checks else None,
        "negative_checks_sha256": _file_sha256(negative_path) if run_negative_checks and negative_path.exists() else None,
        "conclusion": audit.get("conclusion"),
        "class_separated_cd_discrimination_observed": audit.get("class_separated_cd_discrimination_observed"),
        "unsafe_offer_suppression_exercised": audit.get("unsafe_offer_suppression_exercised"),
        "feature_split_acceptance_allowed": audit.get("feature_split_acceptance_allowed"),
        "missing_prerequisites": audit.get("missing_prerequisites"),
        "observed": audit.get("observed"),
        "mocked": False,
        "live": live_slice_receipt.get("live") is True,
        "fixture_backed": False,
        "deterministic_simulator_corpus": live_slice_receipt.get("deterministic_simulator_corpus") is True,
        "live_tau_originated_artifacts_consumed": live_slice_receipt.get("live_tau_originated_artifacts_consumed") is True,
        "live_tau_reexecuted_by_this_command": False,
        "tau_call_attempts": 0,
        "tau_live_call_performed": 0,
        "human_content_judgment_required": False,
        "llm_judge_used": False,
        "memory_write_attempts": 0,
        "provider_call_attempts": 0,
        "canonical_memory_write_attempts": 0,
        "identity_write_attempts": 0,
        "source_memory_write_attempts": 0,
        "replacement_policy_claimed": False,
        "broad_planning_benefit_claimed": False,
        "checks": {
            **checks,
            "negative_checks_failed_closed": negative_checks_failed_closed if run_negative_checks else None,
        },
        "negative_results": negative_results,
        "errors": errors,
        "claims": audit.get("claims")
        if status == PASS_STATUS
        else {
            "proves": ["the cooperation class-separated exposure audit failed closed"],
            "does_not_prove": [
                "class-separated CD cooperation behavior",
                "a replacement cooperation feature split is valid",
                "confidence-bounded CD planning benefit",
                "broad held-out planning benefit",
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    _write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live-slice-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--skip-negative-checks", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "cooperation_class_separated_exposure_audit_receipt.v1.json")
    receipt = run_audit(
        live_slice_receipt_path=args.live_slice_receipt,
        output_root=args.output_root,
        receipt_out=receipt_out,
        run_negative_checks=not args.skip_negative_checks,
    )
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
