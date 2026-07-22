#!/usr/bin/env python3
"""Audit PCTOM-R2 receipt claim truthfulness within the local archive."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pctom_r2_phase1_lib import ROOT_DEFAULT, SCHEMA_PREFIX, discover_receipts, file_sha256, load_json, now_iso, rel, write_json


PASS_STATUS = "PASS_PCTOM_EVIDENCE_CLAIM_INTEGRITY"
BLOCKED_STATUS = "BLOCKED_PCTOM_EVIDENCE_CLAIM_INTEGRITY"
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


def claim_errors(receipt: dict[str, Any], name: str) -> list[str]:
    errors: list[str] = []
    for counter in FORBIDDEN_COUNTERS:
        value = receipt.get(counter, 0)
        if value not in (0, None):
            errors.append(f"forbidden_counter_nonzero:{name}:{counter}:{value}")
    claims = receipt.get("claims")
    if receipt.get("status", "").startswith("PASS") and not isinstance(claims, dict):
        errors.append(f"pass_receipt_missing_claims:{name}")
        claims = {}
    proves = claims.get("proves") if isinstance(claims, dict) and isinstance(claims.get("proves"), list) else []
    for index, claim in enumerate(proves):
        if not isinstance(claim, str):
            errors.append(f"claim_not_string:{name}:{index}")
            continue
        if receipt.get("fixture_backed") is True:
            lowered = claim.lower()
            for term in FORBIDDEN_FIXTURE_CLAIM_TERMS:
                if term in lowered:
                    errors.append(f"fixture_claim_overreach:{name}:{index}:{term}")
    return errors


def audit_claims(root: Path, receipt_out: Path) -> dict[str, Any]:
    errors: list[str] = []
    audited: list[dict[str, Any]] = []
    for path in discover_receipts(root):
        if path.resolve() == receipt_out.resolve():
            continue
        raw = load_json(path, errors, "receipt")
        if not isinstance(raw, dict):
            continue
        name = rel(root, path)
        receipt_errors = claim_errors(raw, name)
        audited.append({
            "path": name,
            "sha256": file_sha256(path),
            "schema": raw.get("schema"),
            "status": raw.get("status"),
            "mocked": raw.get("mocked"),
            "live": raw.get("live"),
            "fixture_backed": raw.get("fixture_backed"),
            "errors": receipt_errors,
        })
        errors.extend(receipt_errors)

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
    negative_errors = claim_errors(forged, "fixtures/audit-mutations/forged-mocked-false")
    negative_results = [{
        "fixture": "forged-mocked-false",
        "expected_status": "BLOCKED_PCTOM_EVIDENCE_TRUTHFULNESS",
        "observed_status": "BLOCKED_PCTOM_EVIDENCE_TRUTHFULNESS" if negative_errors else PASS_STATUS,
        "blocked_as_expected": bool(negative_errors),
        "errors": negative_errors,
    }]
    if not negative_errors:
        errors.append("negative_fixture_not_blocked:forged-mocked-false")

    status = PASS_STATUS if not errors else BLOCKED_STATUS
    receipt = {
        "schema": f"{SCHEMA_PREFIX}.pctom_evidence_claim_integrity_receipt.v1",
        "created_at": now_iso(),
        "status": status,
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "human_content_judgment_rows": 0,
        "llm_judge_rows": 0,
        "audited_receipts": audited,
        "forbidden_claim_terms": list(FORBIDDEN_FIXTURE_CLAIM_TERMS),
        "negative_fixture_results": negative_results,
        "errors": errors,
        "claims": {
            "proves": [
                "PCTOM-R2 PASS-like receipt claims avoid fixture-backed live efficacy, provider execution, semantic dream quality, and forbidden side-effect overclaims",
                "forged mocked:false fixture-backed live-efficacy claims fail closed",
            ] if status == PASS_STATUS else [
                "PCTOM-R2 evidence claim integrity audit failed closed before acceptance",
            ],
            "does_not_prove": [
                "semantic correctness of the research hypotheses",
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
    parser = argparse.ArgumentParser(description="Audit PCTOM-R2 evidence claim integrity.")
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    receipt = audit_claims(args.root, args.receipt_out)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(args.receipt_out)
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
