#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import receipt_gate


VERIFIER_SCHEMA = "monitor_sparta.verifier_receipt.v1"
REVIEWER_SCHEMA = "monitor_sparta.reviewer_receipt.v1"


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def _non_empty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_verifier(receipt: Mapping[str, Any], *, closure_receipt_path: Path) -> list[str]:
    errors: list[str] = []
    if receipt.get("schema") != VERIFIER_SCHEMA:
        errors.append(f"verifier_schema_not_{VERIFIER_SCHEMA}")
    if receipt.get("decision") != "pass":
        errors.append("verifier_decision_not_pass")
    if not bool(receipt.get("independent")):
        errors.append("verifier_not_independent")
    checked = str(receipt.get("checked_receipt_path") or "")
    if checked and Path(checked) != closure_receipt_path:
        errors.append("verifier_checked_different_receipt")
    if not checked:
        errors.append("verifier_checked_receipt_path_missing")
    checks = receipt.get("checks")
    if not isinstance(checks, list) or not checks:
        errors.append("verifier_checks_missing")
    else:
        for index, check in enumerate(checks):
            if not isinstance(check, Mapping):
                errors.append(f"verifier_check_{index}_not_object")
                continue
            if check.get("exit_code") != 0:
                errors.append(f"verifier_check_{index}_exit_nonzero")
            if not _non_empty_string(check.get("command")):
                errors.append(f"verifier_check_{index}_command_missing")
            if not _non_empty_string(check.get("artifact")):
                errors.append(f"verifier_check_{index}_artifact_missing")
    return errors


def validate_reviewer(
    receipt: Mapping[str, Any],
    *,
    closure_receipt_path: Path,
    verifier_receipt_path: Path,
) -> list[str]:
    errors: list[str] = []
    if receipt.get("schema") != REVIEWER_SCHEMA:
        errors.append(f"reviewer_schema_not_{REVIEWER_SCHEMA}")
    if receipt.get("decision") != "pass":
        errors.append("reviewer_decision_not_pass")
    if not bool(receipt.get("independent")):
        errors.append("reviewer_not_independent")
    checked = str(receipt.get("checked_receipt_path") or "")
    if checked and Path(checked) != closure_receipt_path:
        errors.append("reviewer_checked_different_receipt")
    if not checked:
        errors.append("reviewer_checked_receipt_path_missing")
    verifier_path = str(receipt.get("verifier_receipt_path") or "")
    if verifier_path and Path(verifier_path) != verifier_receipt_path:
        errors.append("reviewer_checked_different_verifier_receipt")
    if not verifier_path:
        errors.append("reviewer_verifier_receipt_path_missing")
    blocking = receipt.get("blocking_findings")
    if not isinstance(blocking, list):
        errors.append("reviewer_blocking_findings_not_list")
    elif blocking:
        errors.append("reviewer_blocking_findings_present")
    reviewed = receipt.get("reviewed_evidence")
    if not isinstance(reviewed, list) or not reviewed:
        errors.append("reviewer_reviewed_evidence_missing")
    return errors


def gate_bundle(
    *,
    closure_receipt_path: Path,
    verifier_receipt_path: Path,
    reviewer_receipt_path: Path,
) -> dict[str, Any]:
    closure_receipt = load_json(closure_receipt_path)
    verifier_receipt = load_json(verifier_receipt_path)
    reviewer_receipt = load_json(reviewer_receipt_path)
    closure_gate = receipt_gate.gate_receipt(closure_receipt, require_closure=True)
    verifier_errors = validate_verifier(verifier_receipt, closure_receipt_path=closure_receipt_path)
    reviewer_errors = validate_reviewer(
        reviewer_receipt,
        closure_receipt_path=closure_receipt_path,
        verifier_receipt_path=verifier_receipt_path,
    )
    errors = []
    if not closure_gate.get("ok"):
        errors.extend(f"closure:{item}" for item in closure_gate.get("errors", []))
    errors.extend(f"verifier:{item}" for item in verifier_errors)
    errors.extend(f"reviewer:{item}" for item in reviewer_errors)
    return {
        "schema": "monitor_sparta.closure_bundle_gate.v1",
        "ok": not errors,
        "errors": errors,
        "closure_receipt_path": str(closure_receipt_path),
        "verifier_receipt_path": str(verifier_receipt_path),
        "reviewer_receipt_path": str(reviewer_receipt_path),
        "closure_gate": closure_gate,
        "verifier_decision": verifier_receipt.get("decision"),
        "reviewer_decision": reviewer_receipt.get("decision"),
        "mocked": False,
        "live": False,
        "proves": [
            "closure receipt has Tau handoff proof",
            "separate verifier receipt passed deterministic checks",
            "separate reviewer receipt passed with no blocking findings",
        ],
        "does_not_prove": [
            "all monitor-sparta issues are resolved",
            "semantic correctness beyond named verifier/reviewer evidence",
            "freshness of artifacts outside the checked receipt paths",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Gate monitor-sparta closure bundles.")
    parser.add_argument("--closure-receipt", type=Path, required=True)
    parser.add_argument("--verifier-receipt", type=Path, required=True)
    parser.add_argument("--reviewer-receipt", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = gate_bundle(
            closure_receipt_path=args.closure_receipt,
            verifier_receipt_path=args.verifier_receipt,
            reviewer_receipt_path=args.reviewer_receipt,
        )
    except Exception as exc:  # noqa: BLE001
        result = {
            "schema": "monitor_sparta.closure_bundle_gate.v1",
            "ok": False,
            "errors": [f"gate_error:{type(exc).__name__}:{exc}"],
            "mocked": False,
            "live": False,
        }
    if args.json or not result.get("ok"):
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"PASS: {args.closure_receipt}")
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
