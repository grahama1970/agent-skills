#!/usr/bin/env python3
"""Bind the active PCTOM-R objective to current success and coverage receipts."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_OBJECTIVE_EVIDENCE_AUDIT"
BLOCKED_STATUS = "BLOCKED_PCTOM_OBJECTIVE_EVIDENCE_AUDIT"
SCHEMA = "persona_dream.research.prospective_tom.objective_evidence_audit_receipt.v1"

REQUIRED_COVERAGE_IDS = {
    "gate0_provenance_bound_recall_residue",
    "gate1_deterministic_hidden_state_social_episodes",
    "gate2_valid_tom_distributions",
    "gate3_counterfactual_branches_synthetic",
    "gate4_sealed_prediction_commitments",
    "gate5_deterministic_scoring",
    "gate6_action_selection_planning",
    "gate7_non_destructive_belief_revision",
    "gate8_fault_containment",
    "gate9_causal_replay",
    "cross_stage_hash_lineage",
    "autonomous_no_human_judgment",
    "memory_retention_and_recall",
    "unsupported_evidence_abstention",
    "negative_fixtures_fail_closed",
}

FORBIDDEN_SIDE_EFFECT_COUNTERS = {
    "actual_provider_call_attempts",
    "provider_calls",
    "provider_call_count",
    "canonical_memory_writes",
    "identity_writes",
    "source_memory_writes",
    "canonical_write_violations",
    "identity_write_violations",
    "source_memory_write_violations",
}

REQUIRED_PROVIDER_BOUNDARY_CLAIMS = {
    "paid provider execution",
    "complete Phase 01-16 media runtime execution",
}


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


def _receipt_ref(path: Path, receipt: dict[str, Any]) -> dict[str, Any]:
    calculated_receipt_sha256 = _calculated_receipt_sha256(receipt)
    return {
        "path": str(path),
        "status": receipt.get("status"),
        "schema": receipt.get("schema"),
        "mocked": receipt.get("mocked"),
        "live": receipt.get("live"),
        "fixture_backed": receipt.get("fixture_backed"),
        "receipt_sha256": receipt.get("receipt_sha256"),
        "calculated_receipt_sha256": calculated_receipt_sha256,
        "receipt_sha256_matches_content": receipt.get("receipt_sha256") == calculated_receipt_sha256,
        "file_sha256": _file_sha256(path),
    }


def _calculated_receipt_sha256(receipt: dict[str, Any]) -> str:
    return _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})


def _check_receipt_self_hash(receipt: dict[str, Any], label: str, errors: list[str], *, required: bool) -> dict[str, Any]:
    stored = receipt.get("receipt_sha256")
    calculated = _calculated_receipt_sha256(receipt)
    matches = stored == calculated
    if required:
        if not isinstance(stored, str) or not stored.startswith("sha256:"):
            errors.append(f"{label}_receipt_sha256_missing_or_invalid:{stored}")
        elif not matches:
            errors.append(f"{label}_receipt_sha256_self_mismatch:{stored}:{calculated}")
    return {
        "label": label,
        "required": required,
        "stored": stored,
        "calculated": calculated,
        "matches": matches,
    }


def _claims_do_not_prove(receipt: dict[str, Any]) -> set[str]:
    claims = receipt.get("claims") if isinstance(receipt.get("claims"), dict) else {}
    values = claims.get("does_not_prove") if isinstance(claims.get("does_not_prove"), list) else []
    return {value for value in values if isinstance(value, str)}


def _forbidden_side_effects(value: Any, path: str = "$") -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        for key, item in value.items():
            next_path = f"{path}.{key}"
            if key in FORBIDDEN_SIDE_EFFECT_COUNTERS:
                if isinstance(item, bool):
                    numeric = int(item)
                elif isinstance(item, int):
                    numeric = item
                else:
                    numeric = 0
                if numeric:
                    found.append({"path": next_path, "value": item})
            found.extend(_forbidden_side_effects(item, next_path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(_forbidden_side_effects(item, f"{path}[{index}]"))
    return found


def _coverage_map(coverage: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = coverage.get("coverage") if isinstance(coverage.get("coverage"), list) else []
    mapped: dict[str, dict[str, Any]] = {}
    for row in rows:
        if isinstance(row, dict) and isinstance(row.get("coverage_id"), str):
            mapped[row["coverage_id"]] = row
    return mapped


def run(
    *,
    success_receipt_path: Path,
    goal_coverage_receipt_path: Path,
    output_root: Path,
    receipt_out: Path,
    fixture_backed: bool,
) -> dict[str, Any]:
    started = time.monotonic()
    errors: list[str] = []
    success_receipt_path = success_receipt_path.resolve()
    goal_coverage_receipt_path = goal_coverage_receipt_path.resolve()
    output_root = output_root.resolve()
    receipt_out = receipt_out.resolve()
    output_root.mkdir(parents=True, exist_ok=True)

    success = _load_json(success_receipt_path, errors, "success_receipt")
    coverage = _load_json(goal_coverage_receipt_path, errors, "goal_coverage_receipt")
    success = success if isinstance(success, dict) else {}
    coverage = coverage if isinstance(coverage, dict) else {}
    receipt_integrity = [
        _check_receipt_self_hash(success, "success", errors, required=True),
        _check_receipt_self_hash(coverage, "goal_coverage", errors, required=True),
    ]

    if success.get("status") != "PASS_PCTOM_SUCCESS_CRITERIA_AUDIT":
        errors.append(f"success_status_not_expected:{success.get('status')}")
    if success.get("mocked") is not False:
        errors.append(f"success_mocked_not_false:{success.get('mocked')}")
    if success.get("fixture_backed") is True:
        errors.append("success_fixture_backed_true")
    if coverage.get("status") != "PASS_PCTOM_GOAL_COVERAGE":
        errors.append(f"coverage_status_not_expected:{coverage.get('status')}")
    if coverage.get("mocked") is not False:
        errors.append(f"coverage_mocked_not_false:{coverage.get('mocked')}")
    if coverage.get("fixture_backed") is True:
        errors.append("coverage_fixture_backed_true")

    success_coverage_ref = success.get("goal_coverage_receipt")
    success_coverage_ref = success_coverage_ref if isinstance(success_coverage_ref, dict) else {}
    if success_coverage_ref.get("path") != str(goal_coverage_receipt_path):
        errors.append(
            "success_coverage_path_mismatch:"
            f"{success_coverage_ref.get('path')}:{goal_coverage_receipt_path}"
        )
    if success_coverage_ref.get("receipt_sha256") != coverage.get("receipt_sha256"):
        errors.append(
            "success_coverage_receipt_sha256_mismatch:"
            f"{success_coverage_ref.get('receipt_sha256')}:{coverage.get('receipt_sha256')}"
        )

    summary = success.get("summary") if isinstance(success.get("summary"), dict) else {}
    required_success_flags = {
        "prediction_benefit_with_confidence": True,
        "planning_benefit_with_confidence": True,
        "goal_coverage_complete": True,
        "repeated_full64_same_scope_success": True,
        "calibration_surface_audited": True,
        "unsupported_evidence_abstention_exercised": True,
        "same_scope_joint_success": True,
        "full_hard_success_criteria_met": True,
    }
    for key, expected in required_success_flags.items():
        if summary.get(key) is not expected:
            errors.append(f"success_summary_flag_mismatch:{key}:{summary.get(key)}:{expected}")

    counts = coverage.get("counts") if isinstance(coverage.get("counts"), dict) else {}
    if counts.get("required_coverage_ids") != len(REQUIRED_COVERAGE_IDS):
        errors.append(f"coverage_required_ids_mismatch:{counts.get('required_coverage_ids')}:{len(REQUIRED_COVERAGE_IDS)}")
    if counts.get("coverage_ids_seen") != len(REQUIRED_COVERAGE_IDS):
        errors.append(f"coverage_seen_ids_mismatch:{counts.get('coverage_ids_seen')}:{len(REQUIRED_COVERAGE_IDS)}")
    if counts.get("coverage_ids_missing") != 0:
        errors.append(f"coverage_missing_ids_nonzero:{counts.get('coverage_ids_missing')}")
    if counts.get("negative_evidence_receipts", 0) < 10:
        errors.append(f"coverage_negative_receipts_too_low:{counts.get('negative_evidence_receipts')}:10")
    if counts.get("live_positive_evidence_receipts", 0) < 16:
        errors.append(f"coverage_live_positive_receipts_too_low:{counts.get('live_positive_evidence_receipts')}:16")

    mapped = _coverage_map(coverage)
    missing_ids = sorted(REQUIRED_COVERAGE_IDS - set(mapped))
    unexpected_ids = sorted(set(mapped) - REQUIRED_COVERAGE_IDS)
    for coverage_id in missing_ids:
        errors.append(f"missing_required_coverage_id:{coverage_id}")
    for coverage_id in unexpected_ids:
        errors.append(f"unexpected_coverage_id:{coverage_id}")
    missing_positive = []
    missing_negative = []
    for coverage_id in sorted(REQUIRED_COVERAGE_IDS):
        row = mapped.get(coverage_id, {})
        if row.get("positive_evidence", 0) <= 0:
            missing_positive.append(coverage_id)
        if coverage_id in {"negative_fixtures_fail_closed", "unsupported_evidence_abstention"} and row.get("negative_evidence", 0) <= 0:
            missing_negative.append(coverage_id)
    for coverage_id in missing_positive:
        errors.append(f"coverage_missing_positive_evidence:{coverage_id}")
    for coverage_id in missing_negative:
        errors.append(f"coverage_missing_negative_evidence:{coverage_id}")

    success_forbidden_side_effects = _forbidden_side_effects(success, "success_receipt")
    coverage_forbidden_side_effects = _forbidden_side_effects(coverage, "goal_coverage_receipt")
    for item in success_forbidden_side_effects:
        errors.append(f"success_forbidden_side_effect_counter:{item['path']}:{item['value']}")
    for item in coverage_forbidden_side_effects:
        errors.append(f"coverage_forbidden_side_effect_counter:{item['path']}:{item['value']}")

    missing_success_boundary_claims = sorted(REQUIRED_PROVIDER_BOUNDARY_CLAIMS - _claims_do_not_prove(success))
    missing_coverage_boundary_claims = sorted(REQUIRED_PROVIDER_BOUNDARY_CLAIMS - _claims_do_not_prove(coverage))
    for claim in missing_success_boundary_claims:
        errors.append(f"success_missing_does_not_prove_claim:{claim}")
    for claim in missing_coverage_boundary_claims:
        errors.append(f"coverage_missing_does_not_prove_claim:{claim}")

    child_receipt_refs = coverage.get("evidence") if isinstance(coverage.get("evidence"), list) else []
    child_receipts_checked = 0
    child_file_hash_mismatches: list[dict[str, Any]] = []
    child_forbidden_side_effects: list[dict[str, Any]] = []
    for index, row in enumerate(child_receipt_refs):
        if not isinstance(row, dict):
            errors.append(f"coverage_evidence_row_not_object:{index}")
            continue
        raw_path = row.get("path")
        if not isinstance(raw_path, str) or not raw_path:
            errors.append(f"coverage_evidence_row_path_missing:{index}")
            continue
        child_path = Path(raw_path).resolve()
        expected_file_sha256 = row.get("file_sha256")
        actual_file_sha256 = _file_sha256(child_path) if child_path.exists() and child_path.is_file() else None
        if expected_file_sha256 != actual_file_sha256:
            mismatch = {
                "index": index,
                "path": str(child_path),
                "expected_file_sha256": expected_file_sha256,
                "actual_file_sha256": actual_file_sha256,
            }
            child_file_hash_mismatches.append(mismatch)
            errors.append(
                "coverage_child_file_sha256_mismatch:"
                f"{index}:{child_path}:{expected_file_sha256}:{actual_file_sha256}"
            )
        child = _load_json(child_path, errors, f"coverage_evidence_receipt_{index}")
        if not isinstance(child, dict):
            continue
        child_receipts_checked += 1
        receipt_integrity.append(_check_receipt_self_hash(child, f"coverage_evidence_{index}", errors, required=False))
        for item in _forbidden_side_effects(child, f"coverage_evidence[{index}]"):
            item["receipt_path"] = str(child_path)
            child_forbidden_side_effects.append(item)
            errors.append(
                "coverage_child_forbidden_side_effect_counter:"
                f"{child_path}:{item['path']}:{item['value']}"
            )

    objective_clauses = {
        "provenance_bound_recall_residue": "gate0_provenance_bound_recall_residue" in mapped,
        "deterministic_hidden_state_social_episodes": "gate1_deterministic_hidden_state_social_episodes" in mapped,
        "valid_tom_distributions": "gate2_valid_tom_distributions" in mapped,
        "sealed_prediction_commitments": "gate4_sealed_prediction_commitments" in mapped,
        "deterministic_scoring": "gate5_deterministic_scoring" in mapped,
        "non_destructive_belief_revision": "gate7_non_destructive_belief_revision" in mapped,
        "fail_closed_reliability_checks": (
            "gate8_fault_containment" in mapped
            and "gate9_causal_replay" in mapped
            and "negative_fixtures_fail_closed" in mapped
            and counts.get("negative_evidence_receipts", 0) >= 10
        ),
        "autonomous_without_human_content_judgment": "autonomous_no_human_judgment" in mapped,
        "unsupported_evidence_abstention": "unsupported_evidence_abstention" in mapped,
        "provider_video_not_critical_path": (
            not success_forbidden_side_effects
            and not coverage_forbidden_side_effects
            and not child_forbidden_side_effects
            and not missing_success_boundary_claims
            and not missing_coverage_boundary_claims
        ),
    }
    for key, value in objective_clauses.items():
        if value is not True:
            errors.append(f"objective_clause_not_proven:{key}")

    receipt = {
        "schema": SCHEMA,
        "status": PASS_STATUS if not errors else BLOCKED_STATUS,
        "generated_at": _now_iso(),
        "mocked": False,
        "live": False,
        "fixture_backed": fixture_backed,
        "success_receipt": _receipt_ref(success_receipt_path, success),
        "goal_coverage_receipt": _receipt_ref(goal_coverage_receipt_path, coverage),
        "objective": {
            "name": "PCTOM-R text-first prospective Theory-of-Mind reliability lane",
            "provider_video_critical_path": False,
            "clauses": objective_clauses,
        },
        "counts": {
            "required_coverage_ids": len(REQUIRED_COVERAGE_IDS),
            "coverage_ids_seen": counts.get("coverage_ids_seen"),
            "coverage_ids_missing": counts.get("coverage_ids_missing"),
            "evidence_receipts_seen": counts.get("evidence_receipts_seen"),
            "child_evidence_receipts_checked": child_receipts_checked,
            "positive_evidence_receipts": counts.get("positive_evidence_receipts"),
            "negative_evidence_receipts": counts.get("negative_evidence_receipts"),
            "live_positive_evidence_receipts": counts.get("live_positive_evidence_receipts"),
        },
        "receipt_integrity": {
            "receipts_checked": len(receipt_integrity),
            "required_receipts_checked": sum(1 for item in receipt_integrity if item["required"]),
            "required_receipt_sha256_self_mismatches": sum(
                1 for item in receipt_integrity if item["required"] and not item["matches"]
            ),
            "legacy_child_receipt_sha256_self_mismatches_or_missing": sum(
                1 for item in receipt_integrity if not item["required"] and not item["matches"]
            ),
            "child_file_sha256_mismatches": len(child_file_hash_mismatches),
            "child_file_hash_mismatches": child_file_hash_mismatches,
            "items": receipt_integrity,
        },
        "provider_video_boundary": {
            "required_does_not_prove_claims": sorted(REQUIRED_PROVIDER_BOUNDARY_CLAIMS),
            "success_missing_does_not_prove_claims": missing_success_boundary_claims,
            "coverage_missing_does_not_prove_claims": missing_coverage_boundary_claims,
            "success_forbidden_side_effects": success_forbidden_side_effects,
            "coverage_forbidden_side_effects": coverage_forbidden_side_effects,
            "coverage_child_forbidden_side_effects": child_forbidden_side_effects,
        },
        "errors": errors,
        "claims": {
            "proves": [
                "the current top-level PCTOM-R success receipt is bound to the same expanded goal-coverage receipt",
                "all active text-first PCTOM-R objective clauses have named coverage evidence",
                "the objective evidence surface includes fail-closed negative fixtures and unsupported-evidence abstention coverage",
                "the supplied receipt bundle keeps provider/video work outside the current critical path when provider_video_not_critical_path is true",
            ],
            "does_not_prove": [
                "paid provider execution",
                "semantic dream quality",
                "complete Phase 01-16 media runtime execution",
                "future receipts not routed through this objective audit",
            ],
        },
        "output_root": str(output_root),
        "receipt_path": str(receipt_out),
        "elapsed_s": round(time.monotonic() - started, 6),
    }
    receipt["receipt_sha256"] = _stable_json_sha256({key: value for key, value in receipt.items() if key != "receipt_sha256"})
    receipt_out.parent.mkdir(parents=True, exist_ok=True)
    receipt_out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--success-receipt", required=True)
    parser.add_argument("--goal-coverage-receipt", required=True)
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--receipt-out", required=True)
    parser.add_argument("--fixture-backed", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run(
        success_receipt_path=Path(args.success_receipt),
        goal_coverage_receipt_path=Path(args.goal_coverage_receipt),
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
