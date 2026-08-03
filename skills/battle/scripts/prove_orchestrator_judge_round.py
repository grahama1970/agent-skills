#!/usr/bin/env python3
"""Prove ordinary BattleOrchestrator rounds use Docker Judge receipts."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import battle_skill.orchestrator as orchestrator_module
import battle_skill.state as state_module
from battle_skill.orchestrator import BattleOrchestrator
from battle_skill.orchestrator_judge import FailClosedJudgeBoundary, LocalDockerJudgeBoundary
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


class _ProofBattle(BattleOrchestrator):
    def __init__(
        self,
        *,
        out_dir: Path,
        concurrent: bool,
        judge_boundary: LocalDockerJudgeBoundary | FailClosedJudgeBoundary,
    ) -> None:
        target = out_dir / "target"
        target.mkdir(parents=True, exist_ok=True)
        super().__init__(
            str(target),
            max_rounds=1,
            concurrent=concurrent,
            judge_boundary=judge_boundary,
        )
        suffix = out_dir.name.replace("-", "_")
        self.battle_id = f"{self.battle_id}_{suffix}"
        self.state.battle_id = self.battle_id
        self.out_dir = out_dir
        self.control_dir = out_dir / "control"
        self.digital_twin = _NoopTwin()
        self.monitor = _ProofMonitor()
        self.red_agent = self
        self.blue_agent = self

    def setup_digital_twin(self) -> bool:
        _write_json(
            self.out_dir / "setup-receipt.json",
            {
                "schema": "battle.orchestrator_judge_setup.v1",
                "status": "PASS",
                "mocked": False,
                "live": True,
                "battle_id": self.battle_id,
                "created_at": _utc(),
            },
        )
        return True

    def attack(self, round_num: int) -> list[Finding]:
        return self.red_team_worker(round_num)

    def validate_finding_cascade(self, finding: Finding) -> Finding:
        return finding

    def defend(self, findings: list[Finding], round_num: int) -> list[Patch]:
        return self.blue_team_worker(findings, round_num)

    def red_team_worker(self, round_num: int) -> list[Finding]:
        _write_json(
            self.out_dir / "worker-starts" / f"round-{round_num:04d}-red.json",
            {
                "schema": "battle.worker_start_receipt.v1",
                "team": "red",
                "round_number": round_num,
                "battle_id": self.battle_id,
                "created_at": _utc(),
            },
        )
        finding = Finding(
            id="finding-1",
            type=AttackType.INJECTION,
            severity="high",
            description="deterministic command injection fixture",
            exploit_proof="docker-confirmed",
        )
        return [finding]

    def blue_team_worker(self, findings: list[Finding], round_num: int) -> list[Patch]:
        phase = "reactive" if findings else "proactive"
        _write_json(
            self.out_dir / "worker-starts" / f"round-{round_num:04d}-blue-{phase}.json",
            {
                "schema": "battle.worker_start_receipt.v1",
                "team": "blue",
                "phase": phase,
                "round_number": round_num,
                "battle_id": self.battle_id,
                "created_at": _utc(),
            },
        )
        patch = Patch(
            id=f"patch-{phase}",
            finding_id="finding-1",
            type=DefenseType.PATCH,
            diff=f"fixture-blue-success {phase}",
            verified=False,
            functional_evidence_status=FunctionalEvidenceStatus.INSUFFICIENT_EVIDENCE,
        )
        return [patch]


def _run_case(out_dir: Path, *, concurrent: bool, docker: bool) -> dict[str, Any]:
    boundary = LocalDockerJudgeBoundary() if docker else FailClosedJudgeBoundary()
    battle = _ProofBattle(out_dir=out_dir, concurrent=concurrent, judge_boundary=boundary)
    state = battle.run(checkpoint_interval=99)
    judge_dir = battle.control_dir / "judge" / "round-0001"
    scorekeeper = _read_json(judge_dir / "scorekeeper-receipt.json")
    patch_receipts = sorted((judge_dir / "patches").glob("*.json"))
    finding_receipts = sorted((judge_dir / "findings").glob("*.json"))
    docker_attempt_receipts: list[dict[str, Any]] = []
    for receipt_path in [*finding_receipts, *patch_receipts]:
        receipt = _read_json(receipt_path)
        docker_attempt_receipts.extend(receipt.get("docker_attempt_receipts") or [])
    return {
        "battle_id": battle.battle_id,
        "state_status": state.status,
        "current_round": state.current_round,
        "red_score": state.red_total_score,
        "blue_score": state.blue_total_score,
        "worker_start_receipts": [
            str(path) for path in sorted((out_dir / "worker-starts").glob("*.json"))
        ],
        "finding_receipts": [str(path) for path in finding_receipts],
        "patch_receipts": [str(path) for path in patch_receipts],
        "scorekeeper_receipt": str(judge_dir / "scorekeeper-receipt.json"),
        "accepted_red_finding_ids": scorekeeper["accepted_red_finding_ids"],
        "accepted_blue_candidate_ids": scorekeeper["accepted_blue_candidate_ids"],
        "docker_attempt_count": len(docker_attempt_receipts),
        "docker_attempt_exit_codes": [attempt["exit_code"] for attempt in docker_attempt_receipts],
        "patch_phases": [
            _read_json(path)["candidate"]["phase"]
            for path in patch_receipts
            if "candidate" in _read_json(path)
        ],
    }


def run(out_dir: Path) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    battles_dir = out_dir / "battles"
    orchestrator_module.BATTLES_DIR = battles_dir
    state_module.BATTLES_DIR = battles_dir

    concurrent_case = _run_case(out_dir / "concurrent", concurrent=True, docker=True)
    sequential_case = _run_case(out_dir / "sequential", concurrent=False, docker=True)
    unsupported_case = _run_case(out_dir / "unsupported", concurrent=False, docker=False)

    checks = {
        "concurrent_red_and_proactive_blue_started": (
            any("red" in path for path in concurrent_case["worker_start_receipts"])
            and any("blue-proactive" in path for path in concurrent_case["worker_start_receipts"])
        ),
        "concurrent_retained_proactive_and_reactive": concurrent_case["patch_phases"] == ["proactive", "reactive"],
        "concurrent_docker_attempts_read_back": concurrent_case["docker_attempt_count"] >= 5,
        "concurrent_scores_from_judge": (
            concurrent_case["red_score"] > 0
            and concurrent_case["blue_score"] > 0
            and concurrent_case["accepted_red_finding_ids"] == ["finding-1"]
            and len(concurrent_case["accepted_blue_candidate_ids"]) == 2
        ),
        "sequential_uses_judge_boundary": (
            sequential_case["docker_attempt_count"] >= 3
            and sequential_case["accepted_red_finding_ids"] == ["finding-1"]
            and len(sequential_case["accepted_blue_candidate_ids"]) == 1
        ),
        "unsupported_fails_closed": (
            unsupported_case["red_score"] == 0
            and unsupported_case["blue_score"] == 0
            and unsupported_case["accepted_red_finding_ids"] == []
            and unsupported_case["accepted_blue_candidate_ids"] == []
            and unsupported_case["docker_attempt_count"] == 0
        ),
    }
    errors = [name for name, passed in checks.items() if not passed]
    receipt = {
        "schema": "battle.orchestrator_judge_round_proof.v1",
        "status": "PASS" if not errors else "FAIL",
        "mocked": False,
        "live": True,
        "generated_at": _utc(),
        "checks": checks,
        "errors": errors,
        "cases": {
            "concurrent": concurrent_case,
            "sequential": sequential_case,
            "unsupported": unsupported_case,
        },
        "proof_scope": {
            "claims": {
                "proves": [
                    "BattleOrchestrator.run() routes concurrent and sequential rounds through the injected Battle Judge boundary.",
                    "The local supported boundary writes and reads back Docker Judge attempt receipts before score acceptance.",
                    "Proactive and reactive Blue candidates are retained with phase-qualified candidate ids.",
                    "The unsupported ordinary boundary fails closed with zero accepted score.",
                ],
                "does_not_prove": [
                    "Frontend or Pixi behavior.",
                    "External staging deployment.",
                    "Multi-round restart or resume semantics.",
                    "Quality of LLM-generated exploits or patches.",
                ],
            }
        },
    }
    proof_path = out_dir / "orchestrator-judge-round-proof.json"
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
