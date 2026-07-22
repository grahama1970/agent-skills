#!/usr/bin/env python3
"""Check the frozen PCTOM-R2 goal contract and goal-drift fixtures.

This is a deterministic local Phase 0 checker. It proves only that the
contract boundary is present and that selected drift mutations fail closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any


PASS_STATUS = "PASS_PCTOM_R2_CONTRACT"
BLOCKED_STATUS = "BLOCKED_PCTOM_R2_GOAL_DRIFT"

CANONICAL_GOAL = (
    "Build PCTOM-R2 Experimental Integrity and Replication Readiness: create a durable, "
    "automatically discovered, scope-indexed evidence archive that proves accepted-source "
    "lineage, pre-seal outcome isolation, deterministic proper scoring with explicit "
    "abstention accounting, audit-tamper detection, and crash-safe pipeline transitions; "
    "add independently replayable compute-matched Memory, free-CD, structured-CD, and "
    "functional-ToM deterministic corpora; and seal an endpoint-aligned powered-trial "
    "protocol, without running or claiming the powered live efficacy study, using human "
    "or LLM content judgment, or expanding into provider, video, dream-aesthetic, or "
    "dashboard work."
)

REQUIRED_PREDECESSOR_SHA = "sha256:88e5f6941af8b1ed6336a19ce01c568b8075051b46a5f3df2666ee789edeeb14"

REQUIRED_PHRASES = {
    "canonical_goal_exact": CANONICAL_GOAL,
    "predecessor_status": "predecessor_status: PASS_PCTOM_OBJECTIVE_EVIDENCE_AUDIT",
    "predecessor_sha": f"predecessor_receipt_sha256: {REQUIRED_PREDECESSOR_SHA}",
    "no_live_efficacy": "executing the powered live efficacy study",
    "no_live_efficacy_claim": "claiming that counterfactual dreaming improves prediction or planning",
    "no_provider_video": "paid provider calls, video generation, voice generation, or media-provider",
    "no_human_llm_judge": "human or LLM content judgment",
    "no_dashboard_proof": "dashboards or polished human-facing status surfaces as proof",
    "final_pass_status": "status: PASS_PCTOM_R2_REPLICATION_READINESS",
    "live_efficacy_false": "live_efficacy_claimed: false",
}

FORBIDDEN_CRITICAL_PATH_PHRASES = {
    "provider_video_required": "provider/video work is required",
    "dashboard_required": "dashboard work is required",
    "subjective_quality_required": "subjective dream quality is required",
    "live_efficacy_required": "live efficacy study is required",
}


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(resolved)


def _load_contract(path: Path) -> tuple[str, list[str]]:
    errors: list[str] = []
    if not path.exists():
        return "", [f"missing_contract:{path}"]
    if path.is_symlink():
        return "", [f"symlink_contract:{path}"]
    try:
        return path.read_text(encoding="utf-8"), errors
    except Exception as exc:
        return "", [f"unreadable_contract:{path}:{exc}"]


def _check_contract_text(text: str) -> tuple[list[str], dict[str, bool]]:
    errors: list[str] = []
    checks: dict[str, bool] = {}
    for check_name, phrase in REQUIRED_PHRASES.items():
        ok = phrase in text
        checks[check_name] = ok
        if not ok:
            errors.append(f"missing_required_phrase:{check_name}")
    for check_name, phrase in FORBIDDEN_CRITICAL_PATH_PHRASES.items():
        ok = phrase not in text
        checks[f"forbidden_absent_{check_name}"] = ok
        if not ok:
            errors.append(f"forbidden_critical_path_phrase:{check_name}")
    return errors, checks


def _check_contract_file(contract_path: Path) -> dict[str, Any]:
    text, load_errors = _load_contract(contract_path)
    errors, checks = _check_contract_text(text)
    errors = load_errors + errors
    status = PASS_STATUS if not errors else BLOCKED_STATUS
    return {
        "path": str(contract_path),
        "status": status,
        "errors": errors,
        "checks": checks,
    }


def _check_negative_fixtures(fixture_root: Path | None) -> list[dict[str, Any]]:
    if fixture_root is None:
        return []
    results: list[dict[str, Any]] = []
    for fixture in sorted(fixture_root.glob("*.md")):
        outcome = _check_contract_file(fixture)
        observed_status = outcome["status"]
        results.append(
            {
                "fixture": fixture.name,
                "expected_status": BLOCKED_STATUS,
                "observed_status": observed_status,
                "blocked_as_expected": observed_status == BLOCKED_STATUS,
                "errors": outcome["errors"],
            }
        )
    return results


def build_receipt(contract_path: Path, receipt_out: Path, fixture_root: Path | None) -> dict[str, Any]:
    contract_path = contract_path.resolve()
    receipt_out = receipt_out.resolve()
    contract_outcome = _check_contract_file(contract_path)
    negative_results = _check_negative_fixtures(fixture_root.resolve() if fixture_root else None)
    fixture_errors = [
        f"negative_fixture_not_blocked:{result['fixture']}"
        for result in negative_results
        if not result["blocked_as_expected"]
    ]
    all_errors = list(contract_outcome["errors"]) + fixture_errors
    status = PASS_STATUS if not all_errors else BLOCKED_STATUS
    receipt = {
        "schema": "persona_dream.research.prospective_tom.pctom_r2_contract_receipt.v1",
        "created_at": _now_iso(),
        "status": status,
        "contract_path": _display_path(contract_path),
        "contract_sha256": _sha256_file(contract_path) if contract_path.exists() else "",
        "receipt_path": _display_path(receipt_out),
        "mocked": False,
        "live": False,
        "fixture_backed": True,
        "provider_call_attempts": 0,
        "memory_write_attempts": 0,
        "goal_checks": contract_outcome["checks"],
        "negative_fixture_results": negative_results,
        "counts": {
            "negative_fixtures": len(negative_results),
            "negative_fixtures_blocked": sum(1 for result in negative_results if result["blocked_as_expected"]),
        },
        "errors": all_errors,
        "claims": {
            "proves": [
                "the PCTOM-R2 canonical goal text is present in the Phase 0 contract",
                "the predecessor PCTOM objective receipt hash is recorded as bounded prior evidence",
                "the contract excludes live efficacy, provider/video, dashboard, and subjective dream-quality work from the active critical path",
                "selected goal-drift mutations fail closed",
            ]
            if status == PASS_STATUS
            else [
                "the checker produced a fail-closed receipt for a missing, changed, or drifted PCTOM-R2 contract",
            ],
            "does_not_prove": [
                "scope-indexed evidence archive completion",
                "automatic receipt discovery",
                "accepted-source lineage",
                "pre-seal outcome isolation",
                "proper scoring implementation",
                "abstention accounting",
                "audit-tamper detection beyond the Phase 0 drift fixtures",
                "restart atomicity",
                "deterministic mechanism or functional-ToM corpus readiness",
                "sealed powered-trial protocol readiness",
                "live counterfactual-dream efficacy",
            ],
        },
    }
    _write_json(receipt_out, receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--receipt-out", type=Path, required=True)
    parser.add_argument("--fixture-root", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    receipt = build_receipt(args.contract, args.receipt_out, args.fixture_root)
    if args.json:
        print(json.dumps(receipt, indent=2, sort_keys=True))
    else:
        print(receipt["status"])
        print(receipt["receipt_path"])
    return 0 if receipt["status"] == PASS_STATUS else 1


if __name__ == "__main__":
    raise SystemExit(main())
