"""Deterministic Battle v0 runner for the battle skill.

Inputs are a local fixture directory and output directory. Outputs are
Red/Blue/Judge receipts, a Judge-derived scoreboard, monitor index, and run
receipt. This module intentionally avoids agent/model calls; unexpected setup or
IO failures raise or are logged and converted to explicit BLOCKED receipts.
"""

from __future__ import annotations

import difflib
import json
import subprocess
from pathlib import Path
from typing import Any

from .digital_twin import DigitalTwin
from .judge import judge_one_round
from loguru import logger
from .receipts import BlueReceipt, CommandResult, RedReceipt, write_json
from .state import TwinMode


EXECUTION_SCOPE = {
    "mocked": False,
    "live": "local_deterministic_fixture",
    "agentic": False,
    "models_used": [],
}

NON_CLAIMS = [
    "does_not_prove_real_red_agent_behavior",
    "does_not_prove_real_blue_agent_behavior",
    "does_not_prove_scillm_or_opencode_execution",
    "does_not_prove_anvil_or_code_runner_patch_quality",
    "does_not_prove_multi_round_learning",
    "does_not_prove_docker_or_qemu_modes",
    "does_not_prove_memory_learning",
    "does_not_prove_lean_or_qra_assurance",
]


def run_command(
    command: list[str],
    *,
    cwd: Path,
    artifact_dir: Path,
    name: str,
) -> tuple[bool, CommandResult]:
    artifact_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )

    stdout_path = artifact_dir / f"{name}.stdout.txt"
    stderr_path = artifact_dir / f"{name}.stderr.txt"
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")

    return proc.returncode == 0, CommandResult(
        command=command,
        exit_code=proc.returncode,
        stdout_path=str(stdout_path),
        stderr_path=str(stderr_path),
    )


def status_from_verdict(verdict: str) -> str:
    if verdict == "BLUE_SUCCESS":
        return "PASS"
    if verdict in {"RED_SUCCESS", "FAKE_DEFENSE"}:
        return "FAIL"
    if verdict == "INSUFFICIENT_EVIDENCE":
        return "INSUFFICIENT_EVIDENCE"
    return "BLOCKED"


def score_from_judge(*, red_receipt: RedReceipt, judge_verdict: str) -> dict[str, Any]:
    red_score = 1.5 if red_receipt.exploit_confirmed else 0.0

    if judge_verdict == "BLUE_SUCCESS":
        blue_score = 3.6
        tdsr = 1.0
        fdsr = 0.0
    elif judge_verdict == "FAKE_DEFENSE":
        blue_score = 0.0
        tdsr = 0.0
        fdsr = 1.0
    else:
        blue_score = 0.0
        tdsr = 0.0
        fdsr = 0.0

    return {
        "red_score": red_score,
        "blue_score": blue_score,
        "tdsr": tdsr,
        "fdsr": fdsr,
        "asc": 1 if red_receipt.exploit_confirmed else 0,
    }


def run_battle_001(*, fixture_dir: Path, out_dir: Path) -> dict[str, Any]:
    """Run one deterministic Red -> Blue -> Judge fixture battle."""

    scenario_path = fixture_dir / "scenario.json"
    scenario = json.loads(scenario_path.read_text(encoding="utf-8"))

    battle_id = str(scenario.get("battle_id", "battle-001"))
    target = fixture_dir / "target"

    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "battle-plan.json", scenario)

    twin = DigitalTwin(str(target), battle_id, mode=TwinMode.COPY)
    if not twin.setup():
        run_receipt = run_receipt_payload(
            battle_id=battle_id,
            status="BLOCKED",
            verdict="BLOCKED",
            out_dir=out_dir,
            reason="digital_twin_setup_failed",
        )
        write_json(out_dir / "run-receipt.json", run_receipt)
        return run_receipt

    try:
        arena = twin.get_arena()
        blue = twin.get_blue_workspace()

        red_dir = out_dir / "red"
        red_ok, red_cmd = run_command(
            scenario["commands"]["expect_vulnerable"],
            cwd=arena,
            artifact_dir=red_dir,
            name="red-exploit",
        )

        red_receipt = RedReceipt(
            battle_id=battle_id,
            status="PASS" if red_ok else "FAIL",
            finding_id="seeded-vuln-001" if red_ok else None,
            exploit_confirmed=red_ok,
            exploit_artifact=red_cmd.stdout_path,
            commands_run=[red_cmd],
        )
        write_json(out_dir / "red-receipt.json", red_receipt)

        if not red_ok:
            scoreboard = scoreboard_payload(
                battle_id=battle_id,
                status="INSUFFICIENT_EVIDENCE",
                verdict="INSUFFICIENT_EVIDENCE",
                red_score=0.0,
                blue_score=0.0,
                tdsr=0.0,
                fdsr=0.0,
                asc=0,
                reason="red_failed_to_confirm_seeded_exploit",
            )
            return write_terminal_artifacts(
                out_dir=out_dir,
                scenario=scenario,
                scoreboard=scoreboard,
                red_status=red_receipt.status,
                blue_status="BLOCKED",
                judge_status="INSUFFICIENT_EVIDENCE",
            )

        blue_dir = out_dir / "blue"
        blue_dir.mkdir(parents=True, exist_ok=True)

        source_file = blue / "app.py"
        patched_file = fixture_dir / "patches" / "app.py"
        patch_diff_path = blue_dir / "patch.diff"

        try:
            before = source_file.read_text(encoding="utf-8")
            after = patched_file.read_text(encoding="utf-8")
            patch_diff = "".join(
                difflib.unified_diff(
                    before.splitlines(keepends=True),
                    after.splitlines(keepends=True),
                    fromfile="a/app.py",
                    tofile="b/app.py",
                )
            )
            patch_diff_path.write_text(patch_diff, encoding="utf-8")
            source_file.write_text(after, encoding="utf-8")
            patch_ok = True
            patch_cmd = CommandResult(
                command=["python", "copy patched app.py into blue workspace"],
                exit_code=0,
                stdout_path=str(patch_diff_path),
                stderr_path=None,
            )
        except Exception as exc:
            logger.error("Battle deterministic patch application failed: {}", exc)
            patch_ok = False
            error_path = blue_dir / "blue-apply-patch.stderr.txt"
            error_path.write_text(str(exc), encoding="utf-8")
            patch_cmd = CommandResult(
                command=["python", "copy patched app.py into blue workspace"],
                exit_code=1,
                stdout_path=None,
                stderr_path=str(error_path),
            )

        blue_receipt = BlueReceipt(
            battle_id=battle_id,
            status="PASS" if patch_ok else "FAIL",
            patch_artifact=str(patch_diff_path),
            changed_files=list(scenario.get("expected_changed_files", [])),
            commands_run=[patch_cmd],
        )
        write_json(out_dir / "blue-receipt.json", blue_receipt)

        if not patch_ok:
            scoreboard = scoreboard_payload(
                battle_id=battle_id,
                status="BLOCKED",
                verdict="BLOCKED",
                red_score=1.5,
                blue_score=0.0,
                tdsr=0.0,
                fdsr=0.0,
                asc=1,
                reason="blue_patch_failed_to_apply",
            )
            return write_terminal_artifacts(
                out_dir=out_dir,
                scenario=scenario,
                scoreboard=scoreboard,
                red_status=red_receipt.status,
                blue_status=blue_receipt.status,
                judge_status="BLOCKED",
            )

        if not twin.sync_blue_to_arena():
            scoreboard = scoreboard_payload(
                battle_id=battle_id,
                status="BLOCKED",
                verdict="BLOCKED",
                red_score=1.5,
                blue_score=0.0,
                tdsr=0.0,
                fdsr=0.0,
                asc=1,
                reason="blue_sync_to_arena_failed",
            )
            return write_terminal_artifacts(
                out_dir=out_dir,
                scenario=scenario,
                scoreboard=scoreboard,
                red_status=red_receipt.status,
                blue_status=blue_receipt.status,
                judge_status="BLOCKED",
            )

        judge_receipt = judge_one_round(
            battle_id=battle_id,
            round_number=1,
            arena_path=arena,
            artifact_dir=out_dir / "judge",
            exploit_confirmed_before_patch=red_receipt.exploit_confirmed,
            expect_safe_command=scenario["commands"]["expect_safe"],
            regression_command=scenario["commands"]["regression"],
        )

        score = score_from_judge(
            red_receipt=red_receipt,
            judge_verdict=judge_receipt.verdict,
        )
        scoreboard = scoreboard_payload(
            battle_id=battle_id,
            status=status_from_verdict(judge_receipt.verdict),
            verdict=judge_receipt.verdict,
            **score,
        )
        return write_terminal_artifacts(
            out_dir=out_dir,
            scenario=scenario,
            scoreboard=scoreboard,
            red_status=red_receipt.status,
            blue_status=blue_receipt.status,
            judge_status=judge_receipt.status,
        )

    finally:
        twin.cleanup()


def scoreboard_payload(
    *,
    battle_id: str,
    status: str,
    verdict: str,
    red_score: float,
    blue_score: float,
    tdsr: float,
    fdsr: float,
    asc: int,
    reason: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "battle.scoreboard.v1",
        "battle_id": battle_id,
        "status": status,
        "verdict": verdict,
        "red_score": red_score,
        "blue_score": blue_score,
        "tdsr": tdsr,
        "fdsr": fdsr,
        "asc": asc,
        "receipts": {
            "red": "red-receipt.json",
            "blue": "blue-receipt.json",
            "judge": "judge/judge-receipt.json",
        },
    }
    if reason:
        payload["reason"] = reason
    return payload


def write_terminal_artifacts(
    *,
    out_dir: Path,
    scenario: dict[str, Any],
    scoreboard: dict[str, Any],
    red_status: str,
    blue_status: str,
    judge_status: str,
) -> dict[str, Any]:
    write_json(out_dir / "scoreboard.json", scoreboard)
    write_monitor_index(
        out_dir=out_dir,
        scenario=scenario,
        scoreboard=scoreboard,
        red_status=red_status,
        blue_status=blue_status,
        judge_status=judge_status,
    )
    run_receipt = run_receipt_payload(
        battle_id=str(scenario.get("battle_id", "battle-001")),
        status=str(scoreboard["status"]),
        verdict=str(scoreboard["verdict"]),
        out_dir=out_dir,
        reason=scoreboard.get("reason"),
    )
    write_json(out_dir / "run-receipt.json", run_receipt)
    write_monitor_index(
        out_dir=out_dir,
        scenario=scenario,
        scoreboard=scoreboard,
        red_status=red_status,
        blue_status=blue_status,
        judge_status=judge_status,
    )
    return run_receipt


def run_receipt_payload(
    *,
    battle_id: str,
    status: str,
    verdict: str,
    out_dir: Path,
    reason: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": "battle.run_receipt.v1",
        "battle_id": battle_id,
        "status": status,
        "verdict": verdict,
        "execution": EXECUTION_SCOPE,
        "claim_scope": "fixture_contract_proof",
        "non_claims": NON_CLAIMS,
        "artifacts": artifact_list(out_dir),
    }
    if reason:
        payload["reason"] = reason
    return payload


def write_monitor_index(
    *,
    out_dir: Path,
    scenario: dict[str, Any],
    scoreboard: dict[str, Any],
    red_status: str,
    blue_status: str,
    judge_status: str,
) -> None:
    battle_id = str(scenario.get("battle_id", "battle-001"))

    monitor_index = {
        "schema": "battle.monitor_index.v1",
        "battle_id": battle_id,
        "campaign": "Battle",
        "scenario": scenario.get("scenario_id", "battle-001"),
        "title": scenario.get("title", "Battle fixture"),
        "status": scoreboard.get("status"),
        "verdict": scoreboard.get("verdict"),
        "players": [
            {
                "team": "red",
                "persona": "Isstvan",
                "role": "exploit-finder",
                "receipt": "red-receipt.json",
            },
            {
                "team": "blue",
                "persona": "Phalanx",
                "role": "patcher",
                "receipt": "blue-receipt.json",
            },
            {
                "team": "judge",
                "persona": "Battle Scorekeeper",
                "role": "verifier",
                "receipt": "judge/judge-receipt.json",
            },
        ],
        "timeline": [
            {"stage": "prepare", "status": "PASS"},
            {"stage": "red", "status": red_status},
            {"stage": "blue", "status": blue_status},
            {"stage": "judge", "status": judge_status},
            {"stage": "score", "status": scoreboard.get("status")},
        ],
        "scoreboard": "scoreboard.json",
        "artifacts": artifact_list(out_dir),
    }
    write_json(out_dir / "monitor-index.json", monitor_index)


def artifact_list(out_dir: Path) -> list[str]:
    artifacts: list[str] = []
    for path in sorted(out_dir.rglob("*")):
        if path.is_file():
            artifacts.append(str(path.relative_to(out_dir)))
    return artifacts
