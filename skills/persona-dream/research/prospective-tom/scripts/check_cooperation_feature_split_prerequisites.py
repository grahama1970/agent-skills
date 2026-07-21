#!/usr/bin/env python3
"""Audit whether cooperation evidence can support a replacement feature split."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_COOPERATION_FEATURE_SPLIT_PREREQUISITE_AUDIT"
BLOCKED_STATUS = "BLOCKED_PCTOM_COOPERATION_FEATURE_SPLIT_PREREQUISITE_AUDIT"
ACCEPTANCE_PASS_STATUS = "PASS_PCTOM_COOPERATION_NO_INTERVENTION_POLICY_ACCEPTANCE"
DIAGNOSTIC_PASS_STATUS = "PASS_PCTOM_COOPERATION_POLICY_DIAGNOSTIC"
REJECT_CONCLUSION = "REJECT_SINGLE_PROBABILITY_COOPERATION_FALLBACK"
KEEP_COOPERATION_LABEL = "LOW_CONFIDENCE_TOP_ACTION_CORRECT_RULE_REGRESSION"
AVOID_COOPERATION_LABELS = {
    "UNSAFE_COOPERATION_RULE_HELPED",
    "UNSAFE_COOPERATION_NOT_HELPED",
}
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


def _contains_forbidden_pre_outcome_key(value: Any) -> bool:
    forbidden = ("oracle", "outcome", "actual_next_action", "observed")
    if isinstance(value, dict):
        for key, child in value.items():
            if any(token in str(key).lower() for token in forbidden):
                return True
            if _contains_forbidden_pre_outcome_key(child):
                return True
    if isinstance(value, list):
        return any(_contains_forbidden_pre_outcome_key(item) for item in value)
    return False


def _validate_receipt_sha256(receipt: dict[str, Any], errors: list[str], label: str) -> None:
    expected = receipt.get("receipt_sha256")
    actual = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    if expected != actual:
        errors.append(f"{label}_receipt_sha256_mismatch")


def _validate_inputs(
    *,
    acceptance_receipt: dict[str, Any],
    acceptance_doc: dict[str, Any],
    diagnostic_receipt: dict[str, Any],
    diagnostic_doc: dict[str, Any],
    require_hashes: bool,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    errors: list[str] = []

    if acceptance_receipt.get("status") != ACCEPTANCE_PASS_STATUS:
        errors.append(f"acceptance_status_not_pass:{acceptance_receipt.get('status')}")
    if acceptance_receipt.get("broad_planning_benefit_claimed") is not False:
        errors.append("acceptance_broad_planning_benefit_claimed")
    if acceptance_receipt.get("replacement_policy_claimed") is not False:
        errors.append("acceptance_replacement_policy_claimed")
    if acceptance_receipt.get("mocked") is not False or acceptance_receipt.get("live") is not True:
        errors.append("acceptance_live_mocked_flags_mismatch")
    if acceptance_receipt.get("tau_call_attempts") != 0 or acceptance_receipt.get("tau_live_call_performed") != 0:
        errors.append("acceptance_tau_calls_not_zero")
    if acceptance_receipt.get("llm_judge_used") is not False or acceptance_receipt.get("human_content_judgment_required") is not False:
        errors.append("acceptance_judgment_flags_not_false")
    for key in ZERO_WRITE_KEYS:
        if acceptance_receipt.get(key) != 0:
            errors.append(f"acceptance_{key}_not_zero:{acceptance_receipt.get(key)}")

    if diagnostic_receipt.get("status") != DIAGNOSTIC_PASS_STATUS:
        errors.append(f"diagnostic_status_not_pass:{diagnostic_receipt.get('status')}")
    if diagnostic_receipt.get("diagnostic_conclusion") != REJECT_CONCLUSION:
        errors.append(f"diagnostic_conclusion_not_reject:{diagnostic_receipt.get('diagnostic_conclusion')}")
    if diagnostic_doc.get("conclusion") != REJECT_CONCLUSION:
        errors.append(f"diagnostic_artifact_conclusion_not_reject:{diagnostic_doc.get('conclusion')}")
    if diagnostic_receipt.get("mocked") is not False or diagnostic_receipt.get("live") is not True:
        errors.append("diagnostic_live_mocked_flags_mismatch")
    if diagnostic_receipt.get("tau_call_attempts") != 0 or diagnostic_receipt.get("tau_live_call_performed") != 0:
        errors.append("diagnostic_tau_calls_not_zero")
    for key in ZERO_WRITE_KEYS:
        if diagnostic_receipt.get(key) != 0:
            errors.append(f"diagnostic_{key}_not_zero:{diagnostic_receipt.get(key)}")

    accepted_rows = acceptance_doc.get("accepted_rows") if isinstance(acceptance_doc, dict) else None
    if not isinstance(accepted_rows, list):
        errors.append("accepted_rows_not_list")
        accepted_rows = []
    diagnostic_candidates = diagnostic_doc.get("candidates") if isinstance(diagnostic_doc, dict) else None
    if not isinstance(diagnostic_candidates, list):
        errors.append("diagnostic_candidates_not_list")
        diagnostic_candidates = []

    keep_candidates: list[dict[str, Any]] = []
    for idx, row in enumerate(accepted_rows):
        if not isinstance(row, dict):
            errors.append(f"accepted_row_{idx}_not_object")
            continue
        pre = row.get("pre_outcome_basis")
        post = row.get("post_outcome_evaluation_only")
        if not isinstance(pre, dict):
            errors.append(f"accepted_row_{idx}_pre_outcome_basis_not_object")
            continue
        if _contains_forbidden_pre_outcome_key(pre):
            errors.append(f"accepted_row_{idx}_pre_outcome_basis_leaks_oracle_or_outcome")
        if row.get("accepted_action") != "OFFER_COOPERATION":
            errors.append(f"accepted_row_{idx}_accepted_action_not_offer_cooperation:{row.get('accepted_action')}")
        if not isinstance(post, dict):
            errors.append(f"accepted_row_{idx}_post_outcome_not_object")
            continue
        delta = post.get("regret_delta_avoided")
        if not isinstance(delta, (int, float)) or isinstance(delta, bool) or float(delta) <= 0:
            errors.append(f"accepted_row_{idx}_regret_delta_avoided_not_positive:{delta}")
        else:
            keep_candidates.append(row)

    avoid_candidates: list[dict[str, Any]] = []
    for idx, candidate in enumerate(diagnostic_candidates):
        if not isinstance(candidate, dict):
            errors.append(f"diagnostic_candidate_{idx}_not_object")
            continue
        pre = candidate.get("pre_outcome_features")
        if not isinstance(pre, dict):
            errors.append(f"diagnostic_candidate_{idx}_pre_outcome_features_not_object")
            continue
        if _contains_forbidden_pre_outcome_key(pre):
            errors.append(f"diagnostic_candidate_{idx}_pre_outcome_features_leaks_oracle_or_outcome")
        if candidate.get("label") in AVOID_COOPERATION_LABELS:
            avoid_candidates.append(candidate)

    label_counts = diagnostic_doc.get("label_counts") if isinstance(diagnostic_doc.get("label_counts"), dict) else {}
    keep_label_count = int(label_counts.get(KEEP_COOPERATION_LABEL, 0) or 0)
    avoid_label_count = sum(int(label_counts.get(label, 0) or 0) for label in AVOID_COOPERATION_LABELS)
    feature_split_acceptance_allowed = bool(keep_candidates and avoid_candidates)
    if feature_split_acceptance_allowed:
        conclusion = "FEATURE_SPLIT_PREREQUISITES_MET"
        missing_prerequisites: list[str] = []
    else:
        conclusion = "FEATURE_SPLIT_BLOCKED_INSUFFICIENT_CONTRAST"
        missing_prerequisites = []
        if not keep_candidates:
            missing_prerequisites.append("missing_keep_cooperation_positive_candidate")
        if not avoid_candidates:
            missing_prerequisites.append("missing_unsafe_or_avoid_cooperation_contrast_candidate")

    audit = {
        "schema": "persona_dream.research.prospective_tom.cooperation_feature_split_prerequisite_audit.v1",
        "conclusion": conclusion,
        "feature_split_acceptance_allowed": feature_split_acceptance_allowed,
        "missing_prerequisites": missing_prerequisites,
        "minimum_required_contrast": {
            "keep_cooperation_positive_candidates": 1,
            "avoid_or_unsafe_cooperation_candidates": 1,
        },
        "observed_contrast": {
            "accepted_keep_cooperation_positive_candidates": len(keep_candidates),
            "diagnostic_keep_cooperation_label_count": keep_label_count,
            "diagnostic_avoid_or_unsafe_cooperation_candidates": len(avoid_candidates),
            "diagnostic_avoid_or_unsafe_label_count": avoid_label_count,
            "diagnostic_candidate_count": len(diagnostic_candidates),
        },
        "accepted_keep_cooperation_candidates": [
            {
                "episode_id": row.get("episode_id"),
                "variant": row.get("variant"),
                "accepted_action": row.get("accepted_action"),
                "pre_outcome_basis": row.get("pre_outcome_basis"),
            }
            for row in keep_candidates
        ],
        "avoid_or_unsafe_cooperation_candidates": [
            {
                "episode_id": candidate.get("episode_id"),
                "variant": candidate.get("variant"),
                "label": candidate.get("label"),
                "pre_outcome_features": candidate.get("pre_outcome_features"),
            }
            for candidate in avoid_candidates
        ],
        "claims": {
            "proves": [
                "current live-originated cooperation evidence is one-sided for replacement feature-split learning",
                "the accepted keep-cooperation row has pre-outcome basis that excludes oracle/outcome fields",
                "no replacement cooperation policy or broad planning-benefit claim is accepted by this audit",
            ],
            "does_not_prove": [
                "a replacement cooperation feature split is valid",
                "broad held-out planning benefit",
                "confidence-bounded CD planning benefit",
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    checks = {
        "acceptance_receipt_passed": acceptance_receipt.get("status") == ACCEPTANCE_PASS_STATUS,
        "diagnostic_receipt_passed": diagnostic_receipt.get("status") == DIAGNOSTIC_PASS_STATUS,
        "pre_outcome_fields_exclude_oracle_or_outcome": not any(
            "leaks_oracle_or_outcome" in error for error in errors
        ),
        "unsupported_writes_absent": all(
            receipt.get(key) == 0 for receipt in (acceptance_receipt, diagnostic_receipt) for key in ZERO_WRITE_KEYS
        ),
        "no_new_tau_calls": acceptance_receipt.get("tau_call_attempts") == 0
        and acceptance_receipt.get("tau_live_call_performed") == 0
        and diagnostic_receipt.get("tau_call_attempts") == 0
        and diagnostic_receipt.get("tau_live_call_performed") == 0,
        "no_judgment_used": acceptance_receipt.get("llm_judge_used") is False
        and acceptance_receipt.get("human_content_judgment_required") is False
        and diagnostic_receipt.get("llm_judge_used") is False
        and diagnostic_receipt.get("human_content_judgment_required") is False,
        "feature_split_acceptance_allowed": feature_split_acceptance_allowed,
        "missing_contrast_blocks_replacement_policy": not feature_split_acceptance_allowed
        and "missing_unsafe_or_avoid_cooperation_contrast_candidate" in missing_prerequisites,
    }

    if require_hashes:
        acceptance_path_value = acceptance_receipt.get("acceptance_path")
        if not isinstance(acceptance_path_value, str):
            errors.append("acceptance_path_missing_from_receipt")
        else:
            acceptance_path = Path(acceptance_path_value)
            if not acceptance_path.exists():
                errors.append(f"acceptance_path_missing:{acceptance_path}")
            elif acceptance_receipt.get("acceptance_sha256") != _file_sha256(acceptance_path):
                errors.append("acceptance_sha256_mismatch")
        diagnostic_path_value = diagnostic_receipt.get("diagnostic_path")
        if not isinstance(diagnostic_path_value, str):
            errors.append("diagnostic_path_missing_from_receipt")
        else:
            diagnostic_path = Path(diagnostic_path_value)
            if not diagnostic_path.exists():
                errors.append(f"diagnostic_path_missing:{diagnostic_path}")
            elif diagnostic_receipt.get("diagnostic_sha256") != _file_sha256(diagnostic_path):
                errors.append("diagnostic_sha256_mismatch")
        _validate_receipt_sha256(acceptance_receipt, errors, "acceptance")
        _validate_receipt_sha256(diagnostic_receipt, errors, "diagnostic")

    return errors, checks, audit


def _negative_checks(
    *,
    acceptance_receipt: dict[str, Any],
    acceptance_doc: dict[str, Any],
    diagnostic_receipt: dict[str, Any],
    diagnostic_doc: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}

    bad_acceptance = copy.deepcopy(acceptance_receipt)
    bad_acceptance["status"] = "BLOCKED_PCTOM_COOPERATION_NO_INTERVENTION_POLICY_ACCEPTANCE"
    errors, checks, _audit = _validate_inputs(
        acceptance_receipt=bad_acceptance,
        acceptance_doc=acceptance_doc,
        diagnostic_receipt=diagnostic_receipt,
        diagnostic_doc=diagnostic_doc,
        require_hashes=False,
    )
    results["acceptance_status_not_pass"] = {
        "failed_closed": any(error.startswith("acceptance_status_not_pass") for error in errors),
        "errors": errors,
        "checks": checks,
    }

    broad_claim = copy.deepcopy(acceptance_receipt)
    broad_claim["broad_planning_benefit_claimed"] = True
    errors, checks, _audit = _validate_inputs(
        acceptance_receipt=broad_claim,
        acceptance_doc=acceptance_doc,
        diagnostic_receipt=diagnostic_receipt,
        diagnostic_doc=diagnostic_doc,
        require_hashes=False,
    )
    results["broad_planning_benefit_claim_injected"] = {
        "failed_closed": "acceptance_broad_planning_benefit_claimed" in errors,
        "errors": errors,
        "checks": checks,
    }

    leak_acceptance_doc = copy.deepcopy(acceptance_doc)
    rows = leak_acceptance_doc.get("accepted_rows") if isinstance(leak_acceptance_doc, dict) else None
    if isinstance(rows, list) and rows:
        row = rows[0]
        if isinstance(row, dict) and isinstance(row.get("pre_outcome_basis"), dict):
            row["pre_outcome_basis"]["oracle_action"] = "OFFER_COOPERATION"
    errors, checks, _audit = _validate_inputs(
        acceptance_receipt=acceptance_receipt,
        acceptance_doc=leak_acceptance_doc,
        diagnostic_receipt=diagnostic_receipt,
        diagnostic_doc=diagnostic_doc,
        require_hashes=False,
    )
    results["accepted_pre_outcome_oracle_leak"] = {
        "failed_closed": any("accepted_row_0_pre_outcome_basis_leaks_oracle_or_outcome" in error for error in errors),
        "errors": errors,
        "checks": checks,
    }

    no_keep_doc = copy.deepcopy(acceptance_doc)
    rows = no_keep_doc.get("accepted_rows") if isinstance(no_keep_doc, dict) else None
    if isinstance(rows, list):
        rows.clear()
    errors, checks, _audit = _validate_inputs(
        acceptance_receipt=acceptance_receipt,
        acceptance_doc=no_keep_doc,
        diagnostic_receipt=diagnostic_receipt,
        diagnostic_doc=diagnostic_doc,
        require_hashes=False,
    )
    results["missing_keep_cooperation_candidate"] = {
        "failed_closed": _audit.get("feature_split_acceptance_allowed") is False
        and "missing_keep_cooperation_positive_candidate" in _audit.get("missing_prerequisites", []),
        "errors": errors,
        "checks": checks,
    }

    return results


def run_audit(
    *,
    no_intervention_acceptance_receipt: Path,
    output_root: Path,
    receipt_out: Path,
    run_negative_checks: bool = True,
) -> dict[str, Any]:
    started = time.monotonic()
    no_intervention_acceptance_receipt = no_intervention_acceptance_receipt.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    artifacts_root = output_root / "artifacts"
    audit_path = artifacts_root / "cooperation_feature_split_prerequisite_audit.json"
    negative_path = artifacts_root / "cooperation_feature_split_prerequisite_negative_checks.json"
    errors: list[str] = []

    acceptance_receipt = _load_json(no_intervention_acceptance_receipt, errors, "no_intervention_acceptance_receipt")
    acceptance_receipt = acceptance_receipt if isinstance(acceptance_receipt, dict) else {}
    acceptance_path = Path(str(acceptance_receipt.get("acceptance_path", "")))
    acceptance_doc = _load_json(acceptance_path, errors, "no_intervention_acceptance") if str(acceptance_path) else None
    acceptance_doc = acceptance_doc if isinstance(acceptance_doc, dict) else {}

    diagnostic_receipt_path = Path(str(acceptance_receipt.get("input_policy_diagnostic_receipt", "")))
    diagnostic_receipt = (
        _load_json(diagnostic_receipt_path, errors, "policy_diagnostic_receipt")
        if str(diagnostic_receipt_path)
        else None
    )
    diagnostic_receipt = diagnostic_receipt if isinstance(diagnostic_receipt, dict) else {}
    diagnostic_path = Path(str(diagnostic_receipt.get("diagnostic_path", "")))
    diagnostic_doc = _load_json(diagnostic_path, errors, "policy_diagnostic") if str(diagnostic_path) else None
    diagnostic_doc = diagnostic_doc if isinstance(diagnostic_doc, dict) else {}

    audit_errors, checks, audit = _validate_inputs(
        acceptance_receipt=acceptance_receipt,
        acceptance_doc=acceptance_doc,
        diagnostic_receipt=diagnostic_receipt,
        diagnostic_doc=diagnostic_doc,
        require_hashes=True,
    )
    errors.extend(audit_errors)
    negative_results = (
        _negative_checks(
            acceptance_receipt=acceptance_receipt,
            acceptance_doc=acceptance_doc,
            diagnostic_receipt=diagnostic_receipt,
            diagnostic_doc=diagnostic_doc,
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
                "schema": "persona_dream.research.prospective_tom.cooperation_feature_split_prerequisite_negative_checks.v1",
                "results": negative_results,
            },
        )

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    final_checks = {
        **checks,
        "negative_checks_failed_closed": negative_checks_failed_closed if run_negative_checks else None,
    }
    receipt_payload = {
        "schema": "persona_dream.research.prospective_tom.cooperation_feature_split_prerequisite_audit_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "processing_time_s": round(time.monotonic() - started, 3),
        "input_no_intervention_acceptance_receipt": str(no_intervention_acceptance_receipt),
        "input_no_intervention_acceptance_receipt_sha256": _file_sha256(no_intervention_acceptance_receipt)
        if no_intervention_acceptance_receipt.exists()
        else None,
        "audit_path": str(audit_path),
        "audit_sha256": _file_sha256(audit_path) if audit_path.exists() else None,
        "negative_checks_path": str(negative_path) if run_negative_checks else None,
        "negative_checks_sha256": _file_sha256(negative_path) if run_negative_checks and negative_path.exists() else None,
        "conclusion": audit.get("conclusion"),
        "feature_split_acceptance_allowed": audit.get("feature_split_acceptance_allowed"),
        "missing_prerequisites": audit.get("missing_prerequisites"),
        "observed_contrast": audit.get("observed_contrast"),
        "mocked": False,
        "live": acceptance_receipt.get("live") is True and diagnostic_receipt.get("live") is True,
        "live_tau_originated_artifacts_consumed": acceptance_receipt.get("live_tau_originated_artifacts_consumed") is True
        and diagnostic_receipt.get("live_tau_originated_artifacts_consumed") is True,
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
        "checks": final_checks,
        "negative_results": negative_results,
        "errors": errors,
        "claims": audit.get("claims")
        if status == PASS_STATUS
        else {
            "proves": ["the cooperation feature-split prerequisite audit failed closed"],
            "does_not_prove": [
                "a replacement cooperation feature split is valid",
                "broad held-out planning benefit",
                "confidence-bounded CD planning benefit",
                "semantic dream quality",
                "paid provider execution",
                "complete live Phase 01-16 runtime execution",
            ],
        },
    }
    receipt_payload["receipt_sha256"] = _stable_json_sha256(
        {key: value for key, value in receipt_payload.items() if key != "receipt_sha256"}
    )
    _write_json(receipt_out, receipt_payload)
    return receipt_payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-intervention-acceptance-receipt", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, default=None)
    parser.add_argument("--skip-negative-checks", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    receipt_out = args.receipt_out or (args.output_root / "cooperation_feature_split_prerequisite_audit_receipt.v1.json")
    receipt = run_audit(
        no_intervention_acceptance_receipt=args.no_intervention_acceptance_receipt,
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
