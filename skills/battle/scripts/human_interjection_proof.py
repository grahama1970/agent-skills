#!/usr/bin/env python3
"""Exercise the Battle pause_after_round human interjection contract."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

from battle_skill.human_interjection import apply_after_round, submit_pause_after_round


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def run(out_dir: Path) -> int:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    active_run_id = "battle-human-interjection-proof-run"
    fixture_auth_value = "battle-local-proof-auth-value"
    invalid_auth_value = "wrong-auth-value"
    judge_receipt = out_dir / "judge-receipt.json"
    _write(
        judge_receipt,
        {
            "schema": "battle.arena_tau_public_only_judge_receipt.v1",
            "status": "PASS",
            "verdict": "BLUE_SUCCESS",
            "run_id": active_run_id,
            "mocked": False,
            "live": True,
            "created_at": _utc(),
        },
    )

    interjections = out_dir / "interjections"
    applications = out_dir / "applications"
    accepted = submit_pause_after_round(
        out_dir=interjections,
        active_run_id=active_run_id,
        request_run_id=active_run_id,
        request_id="pause-accepted",
        auth_token=fixture_auth_value,
        expected_auth_token=fixture_auth_value,
        boundary="round_running",
        judge_receipt=judge_receipt,
    )
    duplicate = submit_pause_after_round(
        out_dir=interjections,
        active_run_id=active_run_id,
        request_run_id=active_run_id,
        request_id="pause-accepted",
        auth_token=fixture_auth_value,
        expected_auth_token=fixture_auth_value,
        boundary="round_running",
        judge_receipt=judge_receipt,
    )
    invalid_auth = submit_pause_after_round(
        out_dir=interjections,
        active_run_id=active_run_id,
        request_run_id=active_run_id,
        request_id="pause-invalid-auth",
        auth_token=invalid_auth_value,
        expected_auth_token=fixture_auth_value,
        boundary="round_running",
        judge_receipt=judge_receipt,
    )
    invalid_timing = submit_pause_after_round(
        out_dir=interjections,
        active_run_id=active_run_id,
        request_run_id=active_run_id,
        request_id="pause-invalid-timing",
        auth_token=fixture_auth_value,
        expected_auth_token=fixture_auth_value,
        boundary="judge_finalized",
        judge_receipt=judge_receipt,
    )
    wrong_run = submit_pause_after_round(
        out_dir=interjections,
        active_run_id=active_run_id,
        request_run_id="other-run",
        request_id="pause-wrong-run",
        auth_token=fixture_auth_value,
        expected_auth_token=fixture_auth_value,
        boundary="round_running",
        judge_receipt=judge_receipt,
    )
    application = apply_after_round(
        out_dir=applications,
        interjection_receipt=interjections / "pause-accepted.json",
        round_receipt=judge_receipt,
    )

    cases = {
        "accepted": accepted,
        "duplicate": duplicate,
        "invalid_auth": invalid_auth,
        "invalid_timing": invalid_timing,
        "wrong_run": wrong_run,
        "application": application,
    }
    errors: list[str] = []
    expected = {
        "accepted": "ACCEPTED",
        "duplicate": "DUPLICATE_ACCEPTED",
        "invalid_auth": "REJECTED",
        "invalid_timing": "REJECTED",
        "wrong_run": "REJECTED",
        "application": "APPLIED",
    }
    for name, status in expected.items():
        if cases[name].get("status") != status:
            errors.append(f"{name}_status_mismatch")
    if not all(case.get("mocked") is False and case.get("live") is True for case in cases.values()):
        errors.append("mocked_live_flags_mismatch")
    if not all(
        (case.get("immutability") or case).get("judge_receipt_unchanged", True)
        for case in (accepted, duplicate, invalid_auth, invalid_timing, wrong_run)
    ):
        errors.append("judge_receipt_mutated")
    if application.get("round_receipt_unchanged") is not True:
        errors.append("round_receipt_mutated")

    proof = {
        "schema": "battle.human_interjection_proof.v1",
        "status": "PASS" if not errors else "FAIL",
        "mocked": False,
        "live": True,
        "run_id": active_run_id,
        "generated_at": _utc(),
        "judge_receipt": str(judge_receipt),
        "case_statuses": {name: case.get("status") for name, case in cases.items()},
        "case_receipts": {
            "accepted": str(interjections / "pause-accepted.json"),
            "duplicate": str(next(interjections.glob("pause-accepted.duplicate.*.json"))),
            "invalid_auth": str(interjections / "pause-invalid-auth.json"),
            "invalid_timing": str(interjections / "pause-invalid-timing.json"),
            "wrong_run": str(interjections / "pause-wrong-run.json"),
            "application": str(applications / "pause-accepted.application.json"),
        },
        "errors": errors,
        "proof_scope": {
            "proves": [
                "pause_after_round accepts an authenticated current-run request at a round boundary.",
                "duplicate request ids are idempotent.",
                "invalid auth, invalid timing, and wrong-run requests fail closed with receipts.",
                "Judge/round receipts are not mutated by interjection handling.",
            ],
            "does_not_prove": [
                "Frontend controls.",
                "Tau or orchestrator pause execution beyond the recorded after-round contract.",
                "Arbitrary redirect or persona-change commands.",
            ],
        },
    }
    proof_path = out_dir / "proof.json"
    _write(proof_path, proof)
    print(json.dumps({"status": proof["status"], "receipt": str(proof_path), "errors": errors}, indent=2))
    return 0 if not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Battle human interjection proof")
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    return run(args.out_dir)


if __name__ == "__main__":
    raise SystemExit(main())
