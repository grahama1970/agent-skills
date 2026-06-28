"""Deterministic Judge phase for Battle fixture battles.

Inputs are an arena workspace plus explicit exploit-safety and regression
commands from the scenario. Outputs are command logs and a Judge receipt. Command
failures are recorded as verdict evidence; filesystem or subprocess launch
failures are allowed to raise to the caller.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .receipts import CommandResult, JudgeReceipt, write_json


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


def judge_one_round(
    *,
    battle_id: str,
    round_number: int,
    arena_path: Path,
    artifact_dir: Path,
    exploit_confirmed_before_patch: bool,
    expect_safe_command: list[str],
    regression_command: list[str],
) -> JudgeReceipt:
    """Independently judge the arena after Blue has been synced."""

    commands: list[CommandResult] = []

    if not exploit_confirmed_before_patch:
        receipt = JudgeReceipt(
            battle_id=battle_id,
            round_number=round_number,
            status="INSUFFICIENT_EVIDENCE",
            verdict="INSUFFICIENT_EVIDENCE",
            exploit_confirmed_before_patch=False,
            next_agent="human",
        )
        write_json(artifact_dir / "judge-receipt.json", receipt)
        return receipt

    safe_ok, safe_cmd = run_command(
        expect_safe_command,
        cwd=arena_path,
        artifact_dir=artifact_dir,
        name="judge-exploit-safe",
    )
    commands.append(safe_cmd)

    tests_ok, test_cmd = run_command(
        regression_command,
        cwd=arena_path,
        artifact_dir=artifact_dir,
        name="judge-regression",
    )
    commands.append(test_cmd)

    if safe_ok and tests_ok:
        status = "PASS"
        verdict = "BLUE_SUCCESS"
    elif safe_ok and not tests_ok:
        status = "FAIL"
        verdict = "FAKE_DEFENSE"
    else:
        status = "FAIL"
        verdict = "RED_SUCCESS"

    receipt = JudgeReceipt(
        battle_id=battle_id,
        round_number=round_number,
        status=status,
        verdict=verdict,
        exploit_confirmed_before_patch=True,
        exploit_blocked_after_patch=safe_ok,
        regression_tests_pass=tests_ok,
        functionality_preserved=safe_ok and tests_ok,
        commands_run=commands,
        next_agent="human",
    )
    write_json(artifact_dir / "judge-receipt.json", receipt)
    return receipt
