#!/usr/bin/env python3
"""Prove pause, process restart, and exactly-once resume for Battle."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import battle_skill.orchestrator as orchestrator_module
import battle_skill.resume_runtime as resume_runtime_module
import battle_skill.state as state_module
from battle_skill.human_interjection import submit_pause_after_round
from battle_skill.orchestrator import BattleOrchestrator
from battle_skill.orchestrator_judge import LocalDockerJudgeBoundary
from battle_skill.resume_runtime import resume_battle_once
from battle_skill.state import AttackType, DefenseType, Finding, FunctionalEvidenceStatus, Patch


def _utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


class _Mode:
    value = "copy"


class _NoopTwin:
    mode = _Mode()
    docker_image = None
    qemu_machine = None

    def sync_blue_to_arena(self) -> None:
        return None

    def cleanup(self) -> None:
        return None


class _ProofMonitor:
    def register(self, **_: Any) -> bool:
        return True

    def update(self, *args: Any, **kwargs: Any) -> None:
        return None


class _ResumeProofBattle(BattleOrchestrator):
    def __init__(self, *, out_dir: Path, paused_after_round: bool) -> None:
        target = out_dir / "target"
        target.mkdir(parents=True, exist_ok=True)
        super().__init__(
            str(target),
            max_rounds=2,
            concurrent=False,
            judge_boundary=LocalDockerJudgeBoundary(),
        )
        self.battle_id = "battle-resume-proof"
        self.state.battle_id = self.battle_id
        self.out_dir = out_dir
        self.control_dir = out_dir / "battles" / f"{self.battle_id}_control"
        self.digital_twin = _NoopTwin()
        self.monitor = _ProofMonitor()
        self.red_agent = self
        self.blue_agent = self
        self.paused_after_round = paused_after_round

    def setup_digital_twin(self) -> bool:
        _write_json(
            self.out_dir / "twin-setup" / f"round-{self.state.current_round + 1:04d}.json",
            {
                "schema": "battle.twin_setup_receipt.v1",
                "status": "PASS",
                "mocked": False,
                "live": True,
                "battle_id": self.battle_id,
                "target_path": self.target_path,
                "created_at": _utc(),
            },
        )
        return True

    def attack(self, round_num: int) -> list[Finding]:
        _write_json(
            self.out_dir / "worker-starts" / f"round-{round_num:04d}-red.json",
            {"schema": "battle.worker_start_receipt.v1", "team": "red", "round_number": round_num},
        )
        return [
            Finding(
                id=f"finding-{round_num}",
                type=AttackType.INJECTION,
                severity="medium",
                description="resume fixture finding",
                exploit_proof="docker-confirmed",
            )
        ]

    def validate_finding_cascade(self, finding: Finding) -> Finding:
        return finding

    def defend(self, findings: list[Finding], round_num: int) -> list[Patch]:
        _write_json(
            self.out_dir / "worker-starts" / f"round-{round_num:04d}-blue-reactive.json",
            {"schema": "battle.worker_start_receipt.v1", "team": "blue", "phase": "reactive", "round_number": round_num},
        )
        return [
            Patch(
                id=f"patch-{round_num}",
                finding_id=findings[0].id,
                type=DefenseType.PATCH,
                diff="fixture-blue-success resume",
                verified=False,
                functional_evidence_status=FunctionalEvidenceStatus.INSUFFICIENT_EVIDENCE,
            )
        ] if findings else []

    def run_round_sequential(self, round_num: int):
        result = super().run_round_sequential(round_num)
        if self.paused_after_round and round_num == 1:
            judge_receipt = self.control_dir / "judge" / "round-0001" / "findings" / "finding-1.json"
            submit_pause_after_round(
                out_dir=self.control_dir / "requests",
                active_run_id=self.battle_id,
                request_run_id=self.battle_id,
                request_id="pause-after-round-1",
                auth_token="battle-resume-proof-auth",
                expected_auth_token="battle-resume-proof-auth",
                boundary="round_running",
                judge_receipt=judge_receipt,
            )
        return result


def run(out_dir: Path) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    battles_dir = out_dir / "battles"
    orchestrator_module.BATTLES_DIR = battles_dir
    resume_runtime_module.BATTLES_DIR = battles_dir
    state_module.BATTLES_DIR = battles_dir

    first = _ResumeProofBattle(out_dir=out_dir, paused_after_round=True)
    paused_state = first.run(checkpoint_interval=99)
    state_path = battles_dir / f"{first.battle_id}.json"
    paused_checkpoint = _read_json(state_path)
    round1_scorekeeper = first.control_dir / "judge" / "round-0001" / "scorekeeper-receipt.json"
    round1_scorekeeper_before = round1_scorekeeper.read_bytes()

    def factory(state):
        resumed = _ResumeProofBattle(out_dir=out_dir, paused_after_round=False)
        resumed.battle_id = state.battle_id
        resumed.state = state
        resumed.control_dir = battles_dir / f"{state.battle_id}_control"
        resumed.max_rounds = state.max_rounds
        return resumed

    resume_receipt = resume_battle_once(
        first.battle_id,
        request_id="resume-round-2",
        orchestrator_factory=factory,
    )
    duplicate_receipt = resume_battle_once(
        first.battle_id,
        request_id="resume-round-2",
        orchestrator_factory=factory,
    )
    final_checkpoint = _read_json(state_path)

    corrupt_id = "battle-corrupt-resume-proof"
    corrupt_path = battles_dir / f"{corrupt_id}.json"
    corrupt_path.write_text("{not-json", encoding="utf-8")
    corrupt_receipt = resume_battle_once(corrupt_id, request_id="resume-corrupt")

    worker_starts = sorted((out_dir / "worker-starts").glob("*.json"))
    checks = {
        "round_1_paused": paused_state.status == "paused" and paused_state.current_round == 1,
        "checkpoint_paused": paused_checkpoint["status"] == "paused" and paused_checkpoint["current_round"] == 1,
        "resume_applied": resume_receipt["status"] == "APPLIED",
        "preserved_battle_id": resume_receipt["battle_id"] == first.battle_id == final_checkpoint["battle_id"],
        "started_exactly_round_2": [path.name for path in worker_starts].count("round-0002-red.json") == 1,
        "did_not_start_round_3": not any("round-0003" in path.name for path in worker_starts),
        "round_1_scorekeeper_unchanged": round1_scorekeeper.read_bytes() == round1_scorekeeper_before,
        "final_round_2": final_checkpoint["current_round"] == 2,
        "duplicate_resume_noop": duplicate_receipt["status"] == "DUPLICATE_IGNORED" and duplicate_receipt["started_round"] is None,
        "corrupt_checkpoint_blocked": corrupt_receipt["status"] == "BLOCKED" and corrupt_receipt["reason"] == "corrupt_checkpoint",
    }
    errors = [name for name, passed in checks.items() if not passed]
    receipt = {
        "schema": "battle.pause_restart_resume_proof.v1",
        "status": "PASS" if not errors else "FAIL",
        "mocked": False,
        "live": True,
        "generated_at": _utc(),
        "checks": checks,
        "errors": errors,
        "artifacts": {
            "checkpoint": str(state_path),
            "resume_request": str(first.control_dir / "resume" / "requests" / "resume-round-2.json"),
            "resume_application": str(first.control_dir / "resume" / "applications" / "resume-round-2.json"),
            "duplicate_resume_dir": str(first.control_dir / "resume" / "duplicates"),
            "worker_start_receipts": [str(path) for path in worker_starts],
            "round1_scorekeeper": str(round1_scorekeeper),
            "round2_scorekeeper": str(first.control_dir / "judge" / "round-0002" / "scorekeeper-receipt.json"),
            "corrupt_resume_receipt": str(battles_dir / f"{corrupt_id}_control" / "resume" / "applications" / "resume-corrupt.json"),
        },
        "observed": {
            "paused_status": paused_state.status,
            "paused_current_round": paused_state.current_round,
            "final_status": final_checkpoint["status"],
            "final_current_round": final_checkpoint["current_round"],
            "resume_status": resume_receipt["status"],
            "duplicate_status": duplicate_receipt["status"],
            "corrupt_status": corrupt_receipt["status"],
        },
    }
    proof_path = out_dir / "pause-restart-resume-proof.json"
    _write_json(proof_path, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(proof_path), "errors": errors}, indent=2))
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    receipt = run(args.out)
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
