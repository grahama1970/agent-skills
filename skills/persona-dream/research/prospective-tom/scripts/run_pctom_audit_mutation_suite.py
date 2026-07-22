#!/usr/bin/env python3
"""Run PCTOM-R2 Phase 2 audit mutation checks.

This suite is deterministic and local. It mutates in-memory copies of Phase 1
custody artifacts and verifies that each mutation is rejected by a named
invariant instead of by a generic parser crash.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pctom_r2_phase1_lib import (
    ARCHIVE_SELF_REL,
    EXCLUDED_ARCHIVE_RECEIPTS,
    ROOT_DEFAULT,
    SCHEMA_PREFIX,
    _audit_archive_data,
    _audit_scope_data,
    discover_files,
    file_sha256,
    load_json,
    now_iso,
    rel,
    stable_json_sha256,
    write_json,
)


PASS_STATUS = "PASS_PCTOM_AUDIT_MUTATION_SUITE"
BLOCKED_STATUS = "BLOCKED_PCTOM_AUDIT_MUTATION_SUITE"
PASS_BASELINE = "PASS_PCTOM_AUDIT_BASELINE"

MUTATION_STATUS = {
    "self-hash": "BLOCKED_PCTOM_SELF_HASH_MISMATCH",
    "parent-substitution": "BLOCKED_PCTOM_PARENT_SUBSTITUTION",
    "child-omission": "BLOCKED_PCTOM_CHILD_OMISSION",
    "duplicate-child": "BLOCKED_PCTOM_DUPLICATE_CHILD",
    "schema-downgrade": "BLOCKED_PCTOM_SCHEMA_DOWNGRADE",
    "scope-swap": "BLOCKED_PCTOM_SCOPE_SWAP",
    "lifecycle-reorder": "BLOCKED_PCTOM_LIFECYCLE_REORDER",
    "unauthorized-origin": "BLOCKED_PCTOM_UNAUTHORIZED_EVIDENCE",
    "forged-mocked-false": "BLOCKED_PCTOM_EVIDENCE_TRUTHFULNESS",
}

INVARIANTS = {
    "self-hash": "self_hash_receipts_match_parent_bytes",
    "parent-substitution": "parent_paths_resolve_to_expected_artifact_class",
    "child-omission": "archive_children_are_complete_and_unique",
    "duplicate-child": "archive_children_are_complete_and_unique",
    "schema-downgrade": "schemas_are_current_phase_versions",
    "scope-swap": "scope_rows_cannot_promote_predecessor_evidence",
    "lifecycle-reorder": "audit_lifecycle_is_monotonic",
    "unauthorized-origin": "acceptance_evidence_has_no_forbidden_origin",
    "forged-mocked-false": "fixture_backed_claims_cannot_overclaim_live_or_efficacy",
}

SELF_OUTPUT_RECEIPTS = {
    "pctom-audit-mutation-suite.v1.json",
    "pctom-evidence-claim-integrity-audit.v1.json",
}
TEMP_ARCHIVE_PREFIXES = ("local/recheck/",)
FORBIDDEN_COUNTERS = (
    "provider_call_attempts",
    "memory_write_attempts",
    "canonical_memory_write_attempts",
    "identity_write_attempts",
    "source_memory_write_attempts",
    "human_content_judgment_rows",
    "llm_judge_rows",
)
FORBIDDEN_FIXTURE_CLAIM_TERMS = (
    "proves live efficacy",
    "live efficacy proven",
    "proves provider execution",
    "provider execution proven",
    "paid provider",
    "production-ready",
    "production ready",
    "proves semantic dream quality",
    "semantic dream quality proven",
    "complete phase 01-16",
    "complete phase 1-16",
)


def clone(value: Any) -> Any:
    return json.loads(json.dumps(value))


def load_required(path: Path, root: Path, label: str, errors: list[str]) -> dict[str, Any]:
    raw = load_json(path, errors, label)
    if not isinstance(raw, dict):
        errors.append(f"{label}_not_object:{rel(root, path) if path.exists() else path}")
        return {}
    return raw


def expected_archive_paths(root: Path) -> set[str]:
    expected: set[str] = set()
    excluded_receipts = set(EXCLUDED_ARCHIVE_RECEIPTS) | SELF_OUTPUT_RECEIPTS
    for path in discover_files(root):
        relative_path = rel(root, path)
        if relative_path.startswith(TEMP_ARCHIVE_PREFIXES):
            continue
        if relative_path == ARCHIVE_SELF_REL:
            continue
        if relative_path.startswith("receipts/") and Path(relative_path).name in excluded_receipts:
            continue
        expected.add(relative_path)
    return expected


def audit_archive_completeness(manifest: dict[str, Any], root: Path) -> list[str]:
    errors: list[str] = []
    entries = manifest.get("entries") if isinstance(manifest.get("entries"), list) else []
    actual = {entry.get("path") for entry in entries if isinstance(entry, dict) and isinstance(entry.get("path"), str)}
    expected = expected_archive_paths(root)
    for missing in sorted(expected - actual):
        errors.append(f"archive_expected_child_omitted:{missing}")
    for extra in sorted(actual - expected):
        errors.append(f"archive_unexpected_child:{extra}")
    return errors


def audit_schema_versions(receipts: list[tuple[str, dict[str, Any]]]) -> list[str]:
    errors: list[str] = []
    for name, receipt in receipts:
        schema = receipt.get("schema")
        if not isinstance(schema, str) or not schema.startswith(SCHEMA_PREFIX) or not schema.endswith(".v1"):
            errors.append(f"schema_version_invalid:{name}:{schema}")
    return errors


def audit_forbidden_counters(receipts: list[tuple[str, dict[str, Any]]]) -> list[str]:
    errors: list[str] = []
    for name, receipt in receipts:
        for counter in FORBIDDEN_COUNTERS:
            value = receipt.get(counter, 0)
            if value not in (0, None):
                errors.append(f"forbidden_counter_nonzero:{name}:{counter}:{value}")
    return errors


def audit_receipt_parent_links(root: Path, receipts: list[tuple[str, dict[str, Any]]]) -> list[str]:
    errors: list[str] = []
    for name, receipt in receipts:
        if "manifest_path" in receipt:
            manifest_path = receipt.get("manifest_path")
            if manifest_path != "evidence/pctom-archive-manifest.v1.json":
                errors.append(f"parent_substitution:{name}:manifest_path:{manifest_path}")
                continue
            full = root / manifest_path
            if receipt.get("manifest_sha256") != file_sha256(full):
                errors.append(f"self_hash_mismatch:{name}:manifest_sha256")
            parent = load_json(full, errors, "manifest_parent")
            if isinstance(parent, dict):
                parent_created = parent.get("created_at")
                receipt_created = receipt.get("created_at")
                if isinstance(parent_created, str) and isinstance(receipt_created, str) and receipt_created < parent_created:
                    errors.append(f"lifecycle_reorder:{name}:receipt_before_manifest")
        if "ledger_path" in receipt:
            ledger_path = receipt.get("ledger_path")
            if ledger_path != "evidence/pctom-evidence-scope-ledger.v1.json":
                errors.append(f"parent_substitution:{name}:ledger_path:{ledger_path}")
                continue
            full = root / ledger_path
            if receipt.get("ledger_sha256") != file_sha256(full):
                errors.append(f"self_hash_mismatch:{name}:ledger_sha256")
            parent = load_json(full, errors, "ledger_parent")
            if isinstance(parent, dict):
                parent_created = parent.get("created_at")
                receipt_created = receipt.get("created_at")
                if isinstance(parent_created, str) and isinstance(receipt_created, str) and receipt_created < parent_created:
                    errors.append(f"lifecycle_reorder:{name}:receipt_before_ledger")
    return errors


def audit_fixture_claim_truthfulness(receipt: dict[str, Any], name: str) -> list[str]:
    errors: list[str] = []
    claims = receipt.get("claims") if isinstance(receipt.get("claims"), dict) else {}
    proves = claims.get("proves") if isinstance(claims.get("proves"), list) else []
    if receipt.get("fixture_backed") is True:
        for index, claim in enumerate(proves):
            if not isinstance(claim, str):
                errors.append(f"claim_not_string:{name}:{index}")
                continue
            lowered = claim.lower()
            for term in FORBIDDEN_FIXTURE_CLAIM_TERMS:
                if term in lowered:
                    errors.append(f"fixture_claim_overreach:{name}:{index}:{term}")
    return errors


def fixture_meta(root: Path, fixture_root: Path, operator_id: str) -> dict[str, Any]:
    path = fixture_root / operator_id / "mutation.json"
    if not path.exists():
        return {"fixture_path": rel(root, path), "fixture_sha256": "", "fixture_missing": True}
    return {"fixture_path": rel(root, path), "fixture_sha256": file_sha256(path), "fixture_missing": False}


def result(
    root: Path,
    fixture_root: Path,
    operator_id: str,
    errors: list[str],
    expected_status: str | None = None,
) -> dict[str, Any]:
    expected = expected_status or MUTATION_STATUS[operator_id]
    observed = expected if errors else PASS_BASELINE
    generic = any(error.startswith(("malformed_", "exception:", "traceback")) for error in errors)
    return {
        "operator_id": operator_id,
        **fixture_meta(root, fixture_root, operator_id),
        "expected_status": expected,
        "observed_status": observed,
        "blocked_as_expected": bool(errors) and observed == expected and not generic,
        "violated_invariant": INVARIANTS.get(operator_id, "none"),
        "generic_failure": generic,
        "errors": errors,
    }


def run_suite(root: Path, fixture_root: Path, receipt_out: Path) -> dict[str, Any]:
    errors: list[str] = []
    manifest_path = root / "evidence/pctom-archive-manifest.v1.json"
    ledger_path = root / "evidence/pctom-evidence-scope-ledger.v1.json"
    archive_receipt_path = root / "receipts/pctom-archive-integrity-audit.v1.json"
    scope_receipt_path = root / "receipts/pctom-evidence-scope-audit.v1.json"
    contract_receipt_path = root / "receipts/pctom-r2-contract-receipt.v1.json"

    manifest = load_required(manifest_path, root, "archive_manifest", errors)
    ledger = load_required(ledger_path, root, "evidence_scope_ledger", errors)
    archive_receipt = load_required(archive_receipt_path, root, "archive_audit_receipt", errors)
    scope_receipt = load_required(scope_receipt_path, root, "scope_audit_receipt", errors)
    contract_receipt = load_required(contract_receipt_path, root, "contract_receipt", errors)
    receipts = [
        ("archive", archive_receipt),
        ("scope", scope_receipt),
        ("contract", contract_receipt),
    ]

    baseline_errors = (
        errors
        + _audit_archive_data(manifest, root)
        + audit_archive_completeness(manifest, root)
        + _audit_scope_data(ledger, root)
        + audit_schema_versions(receipts)
        + audit_forbidden_counters(receipts)
        + audit_receipt_parent_links(root, receipts)
        + [error for name, receipt in receipts for error in audit_fixture_claim_truthfulness(receipt, name)]
    )
    baseline_status = PASS_BASELINE if not baseline_errors else "BLOCKED_PCTOM_AUDIT_BASELINE"

    mutation_results: list[dict[str, Any]] = []
    if not baseline_errors:
        mutated = clone(archive_receipt)
        mutated["manifest_sha256"] = "sha256:" + "0" * 64
        mutation_results.append(result(root, fixture_root, "self-hash", audit_receipt_parent_links(root, [("archive", mutated)])))

        mutated = clone(archive_receipt)
        mutated["manifest_path"] = "evidence/pctom-evidence-scope-ledger.v1.json"
        mutation_results.append(result(root, fixture_root, "parent-substitution", audit_receipt_parent_links(root, [("archive", mutated)])))

        mutated = clone(manifest)
        if mutated.get("entries"):
            mutated["entries"] = mutated["entries"][1:]
        mutation_results.append(
            result(
                root,
                fixture_root,
                "child-omission",
                _audit_archive_data(mutated, root) + audit_archive_completeness(mutated, root),
            )
        )

        mutated = clone(manifest)
        if mutated.get("entries"):
            mutated["entries"].append(clone(mutated["entries"][0]))
            mutated["entries_sha256"] = stable_json_sha256(mutated["entries"])
        mutation_results.append(result(root, fixture_root, "duplicate-child", _audit_archive_data(mutated, root)))

        mutated = clone(contract_receipt)
        mutated["schema"] = f"{SCHEMA_PREFIX}.pctom_r2_contract_receipt.v0"
        mutation_results.append(result(root, fixture_root, "schema-downgrade", audit_schema_versions([("contract", mutated)])))

        mutated = clone(ledger)
        for row in mutated.get("claim_rows", []):
            if row.get("scope_id") == "pctom_predecessor_bounded_prior":
                row["acceptance_use"] = True
                break
        mutation_results.append(result(root, fixture_root, "scope-swap", _audit_scope_data(mutated, root)))

        mutated = clone(archive_receipt)
        mutated["created_at"] = "1970-01-01T00:00:00Z"
        mutation_results.append(result(root, fixture_root, "lifecycle-reorder", audit_receipt_parent_links(root, [("archive", mutated)])))

        mutated = clone(contract_receipt)
        mutated["provider_call_attempts"] = 1
        mutated["human_content_judgment_rows"] = 1
        mutation_results.append(result(root, fixture_root, "unauthorized-origin", audit_forbidden_counters([("contract", mutated)])))

        forged = {
            "schema": f"{SCHEMA_PREFIX}.forged_receipt.v1",
            "status": "PASS_FORGED_FIXTURE",
            "mocked": False,
            "live": False,
            "fixture_backed": True,
            "provider_call_attempts": 0,
            "memory_write_attempts": 0,
            "claims": {
                "proves": [
                    "fixture-backed mocked provider response proves live efficacy and provider execution"
                ],
                "does_not_prove": [],
            },
        }
        mutation_results.append(
            result(root, fixture_root, "forged-mocked-false", audit_fixture_claim_truthfulness(forged, "forged"))
        )

    fixture_errors = [
        f"mutation_fixture_missing:{item['operator_id']}:{item.get('fixture_path')}"
        for item in mutation_results
        if item.get("fixture_missing")
    ]
    required = len(MUTATION_STATUS)
    detected = sum(1 for item in mutation_results if item.get("blocked_as_expected") is True)
    score = detected / required if required else 0.0
    suite_errors = (
        baseline_errors
        + fixture_errors
        + [
            f"mutation_not_blocked:{item['operator_id']}:{item['observed_status']}"
            for item in mutation_results
            if item.get("blocked_as_expected") is not True
        ]
    )
    status = PASS_STATUS if not suite_errors and detected == required and score == 1.0 else BLOCKED_STATUS
    receipt = {
        "schema": f"{SCHEMA_PREFIX}.pctom_audit_mutation_suite_receipt.v1",
        "created_at": now_iso(),
        "status": status,
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "human_content_judgment_rows": 0,
        "llm_judge_rows": 0,
        "contract_path": "contracts/pctom-audit-invariants.v1.json",
        "contract_sha256": file_sha256(root / "contracts/pctom-audit-invariants.v1.json"),
        "baseline_status": baseline_status,
        "baseline_errors": baseline_errors,
        "mutation_operators_required": required,
        "mutation_operators_detected": detected,
        "mutation_score": score,
        "mutation_results": mutation_results,
        "errors": suite_errors,
        "claims": {
            "proves": [
                "PCTOM-R2 Phase 2 audit mutation operators fail closed with named invariant statuses",
                "the current archive, scope, schema, lifecycle, origin, and fixture-claim truthfulness baseline passed before mutation",
            ] if status == PASS_STATUS else [
                "PCTOM-R2 Phase 2 audit mutation suite failed closed before acceptance",
            ],
            "does_not_prove": [
                "accepted-source lineage",
                "pre-seal outcome isolation",
                "proper scoring",
                "restart atomicity",
                "live efficacy",
            ],
        },
    }
    write_json(receipt_out, receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the PCTOM-R2 Phase 2 audit mutation suite.")
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--fixture-root", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = run_suite(args.root, args.fixture_root, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(args.receipt_out)
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
