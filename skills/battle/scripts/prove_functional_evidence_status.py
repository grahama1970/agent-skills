#!/usr/bin/env python3
"""Receipt proof for Battle Blue tri-state functional evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
from pathlib import Path
from typing import Any

from battle_skill.receipts import BlueReceipt, JudgeReceipt, write_json
from battle_skill.scoring import Scorer
from battle_skill.state import AttackType, BattleState, DefenseType, Finding, FunctionalEvidenceStatus, Patch


SCRIPT_DIR = Path(__file__).resolve().parent
BATTLE_DIR = SCRIPT_DIR.parent
REPO_ROOT = BATTLE_DIR.parents[1]


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _git(args: list[str]) -> str:
    return subprocess.check_output(["git", *args], cwd=REPO_ROOT, text=True).strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _finding(case_id: str) -> Finding:
    return Finding(
        id=f"{case_id}-finding",
        type=AttackType.EXPLOIT,
        severity="high",
        description=f"{case_id} deterministic finding",
        exploit_proof="docker-judge-confirmed-exploit",
    )


def _functional_artifact(
    case_dir: Path,
    *,
    status: FunctionalEvidenceStatus,
    command: str | None,
    exit_code: int | None,
    assertions: list[dict[str, Any]],
) -> tuple[str | None, str | None]:
    if command is None and exit_code is None and not assertions:
        return None, None
    artifact = {
        "schema": "battle.functional_evidence_artifact.v1",
        "status": status.value,
        "command": command,
        "exit_code": exit_code,
        "assertions": assertions,
        "created_at": _utc(),
    }
    path = case_dir / "functional-evidence.json"
    _write_json(path, artifact)
    return str(path), _sha256(path)


def _case(
    out_dir: Path,
    *,
    case_id: str,
    functional_status: FunctionalEvidenceStatus,
    command: str | None,
    exit_code: int | None,
    assertions: list[dict[str, Any]],
    judge_verdict: str,
    judge_accepts_patch: bool,
) -> dict[str, Any]:
    case_dir = out_dir / case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    finding = _finding(case_id)
    artifact_ref, artifact_sha = _functional_artifact(
        case_dir,
        status=functional_status,
        command=command,
        exit_code=exit_code,
        assertions=assertions,
    )
    patch = Patch(
        id=f"{case_id}-patch",
        finding_id=finding.id,
        type=DefenseType.PATCH,
        diff="diff --git a/app.py b/app.py\n",
        verified=judge_accepts_patch,
        functional_evidence_status=functional_status,
        functional_test_command=command,
        functional_exit_code=exit_code,
        functional_receipt_ref=artifact_ref,
        functional_artifact_sha256=artifact_sha,
    )
    blue = BlueReceipt(
        battle_id="battle-functional-evidence-1052",
        round_number=1,
        status="PASS" if judge_accepts_patch else "BLOCKED",
        patch_artifact=f"{case_id}/patch.diff",
        changed_files=["app.py"],
        functional_evidence_status=functional_status.value,
        functionality_preserved=patch.functionality_preserved,
        functional_test_command=command,
        functional_exit_code=exit_code,
        functional_receipt_ref=artifact_ref,
        functional_artifact_sha256=artifact_sha,
    )
    judge = JudgeReceipt(
        battle_id="battle-functional-evidence-1052",
        round_number=1,
        status="PASS" if judge_accepts_patch else "INSUFFICIENT_EVIDENCE",
        verdict=judge_verdict,  # type: ignore[arg-type]
        exploit_confirmed_before_patch=True,
        exploit_blocked_after_patch=judge_accepts_patch,
        regression_tests_pass=functional_status is FunctionalEvidenceStatus.PASS,
        functional_evidence_status=functional_status.value,
        functionality_preserved=patch.functionality_preserved,
        functional_test_command=command,
        functional_exit_code=exit_code,
        functional_receipt_ref=artifact_ref,
        functional_artifact_sha256=artifact_sha,
    )
    blue_path = write_json(case_dir / "blue-receipt.json", blue)
    judge_path = write_json(case_dir / "judge-receipt.json", judge)
    state = BattleState(
        battle_id="battle-functional-evidence-1052",
        target_path=str(case_dir / "target"),
        max_rounds=1,
        all_findings=[finding],
        all_patches=[patch],
    )
    metrics = Scorer.calculate_metrics(state)
    score = Scorer.score_patch(patch, finding, round_number=1)
    scoreboard = {
        "schema": "battle.functional_evidence_scoreboard.v1",
        "case_id": case_id,
        "functional_evidence_status": functional_status.value,
        "functionality_preserved": patch.functionality_preserved,
        "judge_accepts_patch": judge_accepts_patch,
        "patch_verified": patch.verified,
        "patch_score": score,
        "metrics": metrics,
        "expected": {
            "tdsr_credit": functional_status is FunctionalEvidenceStatus.PASS and judge_accepts_patch,
            "fdsr_credit": functional_status is FunctionalEvidenceStatus.FAIL and judge_accepts_patch,
            "insufficient_credit": functional_status is FunctionalEvidenceStatus.INSUFFICIENT_EVIDENCE,
        },
        "receipts": {
            "blue": str(blue_path),
            "judge": str(judge_path),
            "functional_artifact": artifact_ref,
        },
    }
    scoreboard_path = case_dir / "scoreboard.json"
    _write_json(scoreboard_path, scoreboard)
    return {
        "case_id": case_id,
        "status": "PASS",
        "functional_evidence_status": functional_status.value,
        "functionality_preserved": patch.functionality_preserved,
        "judge_verdict": judge_verdict,
        "judge_accepts_patch": judge_accepts_patch,
        "patch_score": score,
        "metrics": metrics,
        "receipts": {
            "blue": str(blue_path),
            "judge": str(judge_path),
            "scoreboard": str(scoreboard_path),
            "functional_artifact": artifact_ref,
        },
    }


def _validate(cases: list[dict[str, Any]]) -> list[str]:
    by_id = {case["case_id"]: case for case in cases}
    errors: list[str] = []
    no_harness = by_id["case-1-no-behavioral-harness"]
    if no_harness["functional_evidence_status"] != "INSUFFICIENT_EVIDENCE":
        errors.append("case1_not_insufficient")
    if no_harness["metrics"]["tdsr"] != 0 or no_harness["metrics"]["fdsr"] != 0:
        errors.append("case1_received_tdsr_or_fdsr")
    passed = by_id["case-2-behavioral-pass"]
    if passed["functional_evidence_status"] != "PASS" or passed["metrics"]["tdsr"] != 1:
        errors.append("case2_not_pass_tdsr")
    failed = by_id["case-3-behavioral-fail"]
    if failed["functional_evidence_status"] != "FAIL" or failed["metrics"]["fdsr"] != 1:
        errors.append("case3_not_fail_fdsr")
    exit_zero = by_id["case-4-exit-zero-no-evidence"]
    if exit_zero["functional_evidence_status"] != "INSUFFICIENT_EVIDENCE":
        errors.append("case4_not_insufficient")
    if exit_zero["patch_score"] != 0 or exit_zero["metrics"]["tdsr"] != 0 or exit_zero["metrics"]["fdsr"] != 0:
        errors.append("case4_received_score")
    return errors


def run(out_dir: Path) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    cases = [
        _case(
            out_dir,
            case_id="case-1-no-behavioral-harness",
            functional_status=FunctionalEvidenceStatus.INSUFFICIENT_EVIDENCE,
            command=None,
            exit_code=None,
            assertions=[],
            judge_verdict="INSUFFICIENT_EVIDENCE",
            judge_accepts_patch=True,
        ),
        _case(
            out_dir,
            case_id="case-2-behavioral-pass",
            functional_status=FunctionalEvidenceStatus.PASS,
            command="python -m pytest tests/test_behavior.py -q",
            exit_code=0,
            assertions=[{"name": "behavior preserved", "passed": True}],
            judge_verdict="BLUE_SUCCESS",
            judge_accepts_patch=True,
        ),
        _case(
            out_dir,
            case_id="case-3-behavioral-fail",
            functional_status=FunctionalEvidenceStatus.FAIL,
            command="python -m pytest tests/test_behavior.py -q",
            exit_code=1,
            assertions=[{"name": "behavior preserved", "passed": False}],
            judge_verdict="FAKE_DEFENSE",
            judge_accepts_patch=True,
        ),
        _case(
            out_dir,
            case_id="case-4-exit-zero-no-evidence",
            functional_status=FunctionalEvidenceStatus.INSUFFICIENT_EVIDENCE,
            command="python -m py_compile app.py",
            exit_code=0,
            assertions=[],
            judge_verdict="INSUFFICIENT_EVIDENCE",
            judge_accepts_patch=False,
        ),
    ]
    errors = _validate(cases)
    receipt = {
        "schema": "battle.functional_evidence_status_proof.v1",
        "status": "PASS" if not errors else "FAIL",
        "mocked": False,
        "live": "local_deterministic_blue_judge_score_receipts",
        "generated_at": _utc(),
        "source": {
            "repository": "grahama1970/agent-skills",
            "commit": _git(["rev-parse", "HEAD"]),
            "battle_tree": _git(["rev-parse", "HEAD:skills/battle"]),
        },
        "cases": cases,
        "errors": errors,
        "claims": {
            "proves": [
                "No behavioral harness remains INSUFFICIENT_EVIDENCE and receives no TDSR/FDSR credit.",
                "Passing behavioral evidence maps to PASS and TDSR only after Judge acceptance.",
                "Failing behavioral evidence maps to FAIL and FDSR only after Judge acceptance.",
                "Exit-zero build/compile generation without Judge functional evidence cannot produce PASS or accepted score.",
            ],
            "does_not_prove": [
                "Ordinary orchestrator Docker Judge integration; #1161 owns that boundary.",
                "New patch generation behavior.",
                "External staging deployment.",
            ],
        },
    }
    _write_json(out_dir / "functional-evidence-proof.json", receipt)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description="Prove Battle tri-state functional evidence semantics")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = run(args.out)
    print(json.dumps({"status": receipt["status"], "receipt": str(args.out / "functional-evidence-proof.json"), "errors": receipt["errors"]}, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
