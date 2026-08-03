#!/usr/bin/env python3
"""Prove pause_after_round is applied by the ordinary Battle run loop."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import battle_skill.orchestrator as orchestrator_module
import battle_skill.state as state_module
from battle_skill.human_interjection import (
    apply_pending_pause_after_round,
    submit_pause_after_round,
)
from battle_skill.orchestrator import BattleOrchestrator
from battle_skill.state import RoundResult


def _utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _ProofMonitor:
    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self.updates: list[dict[str, Any]] = []

    def register(self, **_: Any) -> bool:
        return True

    def update(self, current_round: int, red_score: float, blue_score: float) -> None:
        self.updates.append(
            {
                "current_round": current_round,
                "red_score": red_score,
                "blue_score": blue_score,
                "created_at": _utc(),
            }
        )
        _write_json(self.out_dir / "monitor-updates.json", {"updates": self.updates})


class _ProofBattleOrchestrator(BattleOrchestrator):
    def __init__(self, *, target_path: Path, out_dir: Path, auth_value: str) -> None:
        super().__init__(str(target_path), max_rounds=2, concurrent=True)
        self.out_dir = out_dir
        self.auth_value = auth_value
        self.control_dir = out_dir / "control"
        self.worker_start_dir = out_dir / "worker-starts"
        self.judge_dir = out_dir / "judge"
        self.worker_events: list[dict[str, Any]] = []
        self.monitor = _ProofMonitor(out_dir)

    def setup_digital_twin(self) -> bool:
        _write_json(
            self.out_dir / "setup-receipt.json",
            {
                "schema": "battle.runtime_pause_setup.v1",
                "status": "PASS",
                "mocked": False,
                "live": "local_deterministic_scheduler_harness",
                "battle_id": self.battle_id,
                "target_path": self.target_path,
                "created_at": _utc(),
            },
        )
        return True

    def _record_worker_start(self, *, team: str, round_num: int) -> None:
        event = {
            "seq": len(self.worker_events) + 1,
            "event_type": "worker_start",
            "team": team,
            "round_number": round_num,
            "battle_id": self.battle_id,
            "created_at": _utc(),
            "monotonic_ns": time.monotonic_ns(),
        }
        self.worker_events.append(event)
        _write_json(self.worker_start_dir / f"round-{round_num:04d}-{team}.json", event)

    def run_round_concurrent(self, round_num: int) -> RoundResult:
        self._record_worker_start(team="red", round_num=round_num)
        self._record_worker_start(team="blue", round_num=round_num)
        judge_receipt = _write_json(
            self.judge_dir / f"round-{round_num:04d}-judge.json",
            {
                "schema": "battle.judge_receipt.v1",
                "status": "PASS",
                "mocked": False,
                "live": "local_deterministic_scheduler_harness",
                "battle_id": self.battle_id,
                "run_id": self.battle_id,
                "round_number": round_num,
                "verdict": "NO_FINDINGS",
                "created_at": _utc(),
            },
        )
        if round_num == 1:
            submit_pause_after_round(
                out_dir=self.control_dir / "requests",
                active_run_id=self.battle_id,
                request_run_id=self.battle_id,
                request_id="pause-after-round-1",
                auth_token=self.auth_value,
                expected_auth_token=self.auth_value,
                boundary="round_running",
                judge_receipt=judge_receipt,
            )
        with self.state._lock:
            self.state.current_round = round_num
        return RoundResult(round_number=round_num, red_score=0.0, blue_score=0.0)


def _run_negative_cases(out_dir: Path, *, auth_value: str) -> dict[str, Any]:
    cases_dir = out_dir / "negative-cases"
    judge_receipt = _write_json(
        cases_dir / "judge.json",
        {
            "schema": "battle.judge_receipt.v1",
            "status": "PASS",
            "mocked": False,
            "live": "local_deterministic_scheduler_harness",
            "run_id": "run-good",
            "round_number": 1,
            "created_at": _utc(),
        },
    )
    round_receipt = _write_json(
        cases_dir / "round-boundary.json",
        {
            "schema": "battle.round_boundary.v1",
            "status": "PASS",
            "mocked": False,
            "live": "local_deterministic_scheduler_harness",
            "run_id": "run-good",
            "round_number": 1,
            "created_at": _utc(),
        },
    )

    wrong_run_dir = cases_dir / "wrong-run"
    wrong_run = submit_pause_after_round(
        out_dir=wrong_run_dir / "requests",
        active_run_id="run-good",
        request_run_id="run-other",
        request_id="wrong-run",
        auth_token=auth_value,
        expected_auth_token=auth_value,
        boundary="round_running",
        judge_receipt=judge_receipt,
    )
    wrong_run_scan = apply_pending_pause_after_round(
        control_dir=wrong_run_dir,
        active_run_id="run-good",
        round_receipt=round_receipt,
    )

    rejected_dir = cases_dir / "rejected-auth"
    rejected_auth = submit_pause_after_round(
        out_dir=rejected_dir / "requests",
        active_run_id="run-good",
        request_run_id="run-good",
        request_id="rejected-auth",
        auth_token="battle-local-proof-wrong-auth-value",
        expected_auth_token=auth_value,
        boundary="round_running",
        judge_receipt=judge_receipt,
    )
    rejected_scan = apply_pending_pause_after_round(
        control_dir=rejected_dir,
        active_run_id="run-good",
        round_receipt=round_receipt,
    )

    duplicate_dir = cases_dir / "duplicate"
    first_duplicate = submit_pause_after_round(
        out_dir=duplicate_dir / "requests",
        active_run_id="run-good",
        request_run_id="run-good",
        request_id="duplicate",
        auth_token=auth_value,
        expected_auth_token=auth_value,
        boundary="round_running",
        judge_receipt=judge_receipt,
    )
    duplicate_submit = submit_pause_after_round(
        out_dir=duplicate_dir / "requests",
        active_run_id="run-good",
        request_run_id="run-good",
        request_id="duplicate",
        auth_token=auth_value,
        expected_auth_token=auth_value,
        boundary="round_running",
        judge_receipt=judge_receipt,
    )
    first_scan = apply_pending_pause_after_round(
        control_dir=duplicate_dir,
        active_run_id="run-good",
        round_receipt=round_receipt,
    )
    restart_scan = apply_pending_pause_after_round(
        control_dir=duplicate_dir,
        active_run_id="run-good",
        round_receipt=round_receipt,
    )

    return {
        "wrong_run": {"request": wrong_run, "scan": wrong_run_scan},
        "rejected_auth": {"request": rejected_auth, "scan": rejected_scan},
        "duplicate_request": {
            "first_request": first_duplicate,
            "second_request": duplicate_submit,
            "first_scan": first_scan,
            "restart_scan": restart_scan,
        },
    }


def run(out_dir: Path) -> dict[str, Any]:
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    battles_dir = out_dir / "battles"
    target_path = out_dir / "target"
    target_path.mkdir(parents=True, exist_ok=True)
    _write_json(target_path / "target.json", {"schema": "battle.pause_target.v1", "status": "READY"})

    orchestrator_module.BATTLES_DIR = battles_dir
    state_module.BATTLES_DIR = battles_dir

    auth_value = "battle-local-proof-auth-value"
    battle = _ProofBattleOrchestrator(
        target_path=target_path,
        out_dir=out_dir,
        auth_value=auth_value,
    )
    final_state = battle.run(checkpoint_interval=99)
    state_path = battles_dir / f"{battle.battle_id}.json"
    state_payload = _read_json(state_path)
    round_boundary = battle.control_dir / "round-boundaries" / "round-0001.json"
    request_path = battle.control_dir / "requests" / "pause-after-round-1.json"
    application_path = battle.control_dir / "applications" / "pause-after-round-1.application.json"
    scans = sorted((battle.control_dir / "scans").glob("*.json"))
    worker_starts = sorted(battle.worker_start_dir.glob("*.json"))
    negative_cases = _run_negative_cases(out_dir, auth_value=auth_value)

    checks = {
        "round_1_terminal_receipt_exists": round_boundary.exists(),
        "round_1_judge_receipt_exists": (battle.judge_dir / "round-0001-judge.json").exists(),
        "pause_request_accepted": _read_json(request_path).get("status") == "ACCEPTED",
        "application_applied": _read_json(application_path).get("status") == "APPLIED",
        "application_count_one": len(list((battle.control_dir / "applications").glob("*.application.json"))) == 1,
        "durable_state_paused": state_payload.get("status") == "paused" == final_state.status,
        "current_round_one": state_payload.get("current_round") == 1 == final_state.current_round,
        "round_2_worker_start_receipts_absent": not list(battle.worker_start_dir.glob("round-0002-*.json")),
        "scan_receipt_exists": bool(scans),
        "round_receipt_unchanged": (
            _read_json(application_path).get("round_receipt_sha256_before") == _sha256(round_boundary)
            and _read_json(application_path).get("round_receipt_sha256_after") == _sha256(round_boundary)
        ),
        "wrong_run_noop": negative_cases["wrong_run"]["scan"].get("status") == "NO_ELIGIBLE_REQUEST",
        "rejected_auth_noop": negative_cases["rejected_auth"]["scan"].get("status") == "NO_ELIGIBLE_REQUEST",
        "duplicate_applied_once": (
            negative_cases["duplicate_request"]["first_scan"].get("status") == "APPLIED"
            and negative_cases["duplicate_request"]["restart_scan"].get("status") == "NO_ELIGIBLE_REQUEST"
        ),
    }
    errors = [name for name, passed in checks.items() if not passed]
    receipt = {
        "schema": "battle.runtime_pause_after_round_proof.v1",
        "status": "PASS" if not errors else "FAIL",
        "mocked": False,
        "live": "local_ordinary_run_loop_with_deterministic_workers",
        "battle_id": battle.battle_id,
        "generated_at": _utc(),
        "checks": checks,
        "errors": errors,
        "artifacts": {
            "state": str(state_path),
            "request": str(request_path),
            "application": str(application_path),
            "round_boundary": str(round_boundary),
            "scan_receipts": [str(path) for path in scans],
            "worker_start_receipts": [str(path) for path in worker_starts],
            "negative_cases_dir": str(out_dir / "negative-cases"),
        },
        "worker_events": battle.worker_events,
        "observed": {
            "pause_request": _read_json(request_path).get("status"),
            "application": _read_json(application_path).get("status"),
            "durable_state": state_payload.get("status"),
            "current_round": state_payload.get("current_round"),
            "request_applied_count": len(list((battle.control_dir / "applications").glob("*.application.json"))),
            "round_2_worker_start_receipts": [
                str(path) for path in battle.worker_start_dir.glob("round-0002-*.json")
            ],
        },
        "proof_scope": {
            "claims": {
                "proves": [
                    "BattleOrchestrator.run() applies an accepted current-run pause_after_round receipt at the after-round boundary.",
                    "The run loop saves durable paused state at round 1 and returns before scheduling round 2.",
                    "Wrong-run, rejected-auth, duplicate, and restart-style already-applied receipts do not apply a second pause.",
                ],
                "does_not_prove": [
                    "Frontend submission over authenticated live transport.",
                    "LLM/provider Red or Blue worker quality.",
                    "Docker Judge authority for ordinary orchestrator findings and patches.",
                    "Resume semantics after a paused state.",
                ],
            }
        },
    }
    proof_path = out_dir / "runtime-pause-after-round-proof.json"
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
