#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Mapping

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import closure_bundle_gate
import receipt_gate


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dict(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run_receipt_gate(closure_receipt: Path, *, artifact_dir: Path) -> dict[str, Any]:
    output = artifact_dir / "receipt_gate.json"
    cmd = [
        sys.executable,
        str(SCRIPT_DIR / "receipt_gate.py"),
        str(closure_receipt),
        "--require-closure",
        "--json",
    ]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    output.write_text(proc.stdout or "", encoding="utf-8")
    parsed: dict[str, Any]
    try:
        parsed = json.loads(proc.stdout or "{}")
        if not isinstance(parsed, dict):
            parsed = {}
    except json.JSONDecodeError:
        parsed = {}
    return {
        "command": " ".join(cmd),
        "exit_code": proc.returncode,
        "artifact": str(output),
        "stdout_tail": (proc.stdout or "")[-4000:],
        "stderr_tail": (proc.stderr or "")[-4000:],
        "parsed": parsed,
    }


def verifier_receipt(closure_receipt: Path, *, artifact_dir: Path, verifier_id: str) -> dict[str, Any]:
    check = run_receipt_gate(closure_receipt, artifact_dir=artifact_dir)
    parsed = check.get("parsed") if isinstance(check.get("parsed"), Mapping) else {}
    passed = check["exit_code"] == 0 and bool(parsed.get("ok"))
    blocking_findings: list[str] = []
    if check["exit_code"] != 0:
        blocking_findings.append("receipt_gate_exit_nonzero")
    for error in parsed.get("errors", []) if isinstance(parsed.get("errors"), list) else []:
        blocking_findings.append(f"receipt_gate:{error}")
    return {
        "schema": closure_bundle_gate.VERIFIER_SCHEMA,
        "created_at": utc_now(),
        "verifier_id": verifier_id,
        "decision": "pass" if passed else "fail",
        "independent": True,
        "checked_receipt_path": str(closure_receipt),
        "checks": [
            {
                "command": check["command"],
                "exit_code": check["exit_code"],
                "artifact": check["artifact"],
            }
        ],
        "blocking_findings": blocking_findings,
        "mocked": False,
        "live": False,
        "proves": [
            "closure receipt passed monitor-sparta receipt-gate",
        ],
        "does_not_prove": [
            "semantic correctness of SPARTA data mutation",
            "independent human acceptance",
        ],
    }


def reviewer_receipt(
    closure_receipt: Path,
    verifier_receipt_path: Path,
    *,
    reviewer_id: str,
) -> dict[str, Any]:
    verifier = load_json(verifier_receipt_path)
    verifier_errors = closure_bundle_gate.validate_verifier(
        verifier,
        closure_receipt_path=closure_receipt,
    )
    blocking = [f"verifier:{error}" for error in verifier_errors]
    verifier_blocking = verifier.get("blocking_findings")
    if isinstance(verifier_blocking, list):
        blocking.extend(f"verifier_blocking:{item}" for item in verifier_blocking)
    elif verifier_blocking is not None:
        blocking.append("verifier_blocking_findings_not_list")
    return {
        "schema": closure_bundle_gate.REVIEWER_SCHEMA,
        "created_at": utc_now(),
        "reviewer_id": reviewer_id,
        "decision": "pass" if not blocking else "fail",
        "independent": True,
        "checked_receipt_path": str(closure_receipt),
        "verifier_receipt_path": str(verifier_receipt_path),
        "blocking_findings": blocking,
        "reviewed_evidence": [str(closure_receipt), str(verifier_receipt_path)],
        "mocked": False,
        "live": False,
        "proves": [
            "verifier receipt schema and deterministic check outputs were reviewed",
            "reviewer found no blocking findings" if not blocking else "reviewer recorded blocking findings",
        ],
        "does_not_prove": [
            "semantic correctness beyond verifier evidence",
            "that all monitor-sparta issues are resolved",
        ],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create monitor-sparta verifier/reviewer receipts.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    verify = sub.add_parser("verify", help="Run deterministic receipt-gate and write verifier receipt")
    verify.add_argument("--closure-receipt", type=Path, required=True)
    verify.add_argument("--output", type=Path, required=True)
    verify.add_argument("--artifact-dir", type=Path)
    verify.add_argument("--verifier-id", default="monitor-sparta-verifier")
    verify.add_argument("--json", action="store_true")

    review = sub.add_parser("review", help="Review verifier receipt and write reviewer receipt")
    review.add_argument("--closure-receipt", type=Path, required=True)
    review.add_argument("--verifier-receipt", type=Path, required=True)
    review.add_argument("--output", type=Path, required=True)
    review.add_argument("--reviewer-id", default="monitor-sparta-reviewer")
    review.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "verify":
            artifact_dir = args.artifact_dir or args.output.parent
            receipt = verifier_receipt(
                args.closure_receipt,
                artifact_dir=artifact_dir,
                verifier_id=args.verifier_id,
            )
            write_json(args.output, receipt)
            rc = 0 if receipt["decision"] == "pass" else 2
        elif args.cmd == "review":
            receipt = reviewer_receipt(
                args.closure_receipt,
                args.verifier_receipt,
                reviewer_id=args.reviewer_id,
            )
            write_json(args.output, receipt)
            rc = 0 if receipt["decision"] == "pass" else 2
        else:
            raise ValueError(f"unknown command: {args.cmd}")
    except Exception as exc:  # noqa: BLE001
        receipt = {
            "schema": "monitor_sparta.closure_review_error.v1",
            "created_at": utc_now(),
            "decision": "fail",
            "blocking_findings": [f"{type(exc).__name__}:{exc}"],
            "mocked": False,
            "live": False,
        }
        if getattr(args, "output", None):
            write_json(args.output, receipt)
        rc = 2
    if getattr(args, "json", False):
        print(json.dumps(receipt, indent=2, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
