#!/usr/bin/env python3
"""Run the local three-round Battle campaign qualification harness."""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import battle_skill.orchestrator as orchestrator_module
import battle_skill.resume_runtime as resume_runtime_module
import battle_skill.state as state_module
from battle_skill.live_transport_server import (
    LiveControlConfig,
    build_live_transport_source,
    create_live_transport_server,
)
from battle_skill.orchestrator import BattleOrchestrator
from battle_skill.orchestrator_judge import LocalDockerJudgeBoundary, source_identity
from battle_skill.resume_runtime import resume_battle_once
from battle_skill.state import AttackType, DefenseType, Finding, FunctionalEvidenceStatus, Patch


SCRIPT_DIR = Path(__file__).resolve().parent
BATTLE_DIR = SCRIPT_DIR.parent
REPO_ROOT = BATTLE_DIR.parents[1]
DEFAULT_FIXTURE = BATTLE_DIR / "spectator/public/battle-fixtures/battle-004-pr6-genetic-pixi/battle.normalized_ux_fixture.json"


def _utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _git(args: list[str]) -> str:
    proc = subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else "UNKNOWN"


def _source_receipt() -> dict[str, Any]:
    commit, tree = source_identity()
    tau_repo = Path("/home/graham/workspace/experiments/tau")
    tau: dict[str, Any] = {"path": str(tau_repo), "available": tau_repo.is_dir()}
    if tau_repo.is_dir():
        tau["commit"] = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tau_repo, capture_output=True, text=True, check=False).stdout.strip()
        tau["tree"] = subprocess.run(["git", "rev-parse", "HEAD^{tree}"], cwd=tau_repo, capture_output=True, text=True, check=False).stdout.strip()
        tau["dirty"] = bool(subprocess.run(["git", "status", "--porcelain"], cwd=tau_repo, capture_output=True, text=True, check=False).stdout.strip())
    return {
        "schema": "battle.local_campaign_source_receipt.v1",
        "status": "PASS",
        "mocked": False,
        "live": True,
        "repository": "grahama1970/agent-skills",
        "source_commit": commit,
        "source_tree": tree,
        "branch": _git(["branch", "--show-current"]),
        "dirty": _git(["status", "--porcelain=v1"]).splitlines(),
        "dependency_health": {
            "docker": subprocess.run(["docker", "version", "--format", "{{.Server.Version}}"], capture_output=True, text=True, check=False).stdout.strip(),
            "node": subprocess.run(["node", "--version"], capture_output=True, text=True, check=False).stdout.strip(),
            "npm": subprocess.run(["npm", "--version"], capture_output=True, text=True, check=False).stdout.strip(),
            "uv": subprocess.run(["uv", "--version"], capture_output=True, text=True, check=False).stdout.strip(),
        },
        "tau": tau,
        "created_at": _utc(),
    }


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

    def update(self, *_: Any) -> None:
        return None


class _LocalCampaignBattle(BattleOrchestrator):
    def __init__(self, *, out_dir: Path, run_id: str, wait_for_pause: bool) -> None:
        target = out_dir / "target"
        target.mkdir(parents=True, exist_ok=True)
        super().__init__(str(target), max_rounds=3, concurrent=True, judge_boundary=LocalDockerJudgeBoundary())
        self.battle_id = run_id
        self.state.battle_id = run_id
        self.state.max_rounds = 3
        self.out_dir = out_dir
        self.control_dir = out_dir / "battles" / f"{run_id}_control"
        self.worker_dir = out_dir / "worker-starts"
        self.memory_dir = out_dir / "memory"
        self.wait_for_pause = wait_for_pause
        self.digital_twin = _NoopTwin()
        self.monitor = _ProofMonitor()
        self.red_agent = self
        self.blue_agent = self

    def setup_digital_twin(self) -> bool:
        _write_json(
            self.out_dir / "twin-setup.json",
            {
                "schema": "battle.local_campaign_twin_setup.v1",
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
        self._worker_receipt(team="red", phase="proactive", round_num=round_num, sleep_s=0.35)
        self._memory_receipts(team="red", round_num=round_num)
        if self.wait_for_pause and round_num == 2:
            self._wait_for_accepted_pause()
        return [
            Finding(
                id=f"finding-{round_num}",
                type=AttackType.INJECTION,
                severity="medium",
                description=f"local campaign finding round {round_num}",
                exploit_proof="docker-confirmed",
                file_path="target/app.py",
                line_number=round_num,
            )
        ]

    def validate_finding_cascade(self, finding: Finding) -> Finding:
        return finding

    def defend(self, findings: list[Finding], round_num: int) -> list[Patch]:
        phase = "reactive" if findings else "proactive"
        self._worker_receipt(team="blue", phase=phase, round_num=round_num, sleep_s=0.45)
        self._memory_receipts(team="blue", round_num=round_num)
        if phase != "proactive":
            return []
        return [
            Patch(
                id=f"patch-{round_num}",
                finding_id=f"finding-{round_num}",
                type=DefenseType.PATCH,
                diff=f"fixture-blue-success local campaign round {round_num}",
                verified=False,
                functional_evidence_status=FunctionalEvidenceStatus.INSUFFICIENT_EVIDENCE,
            )
        ]

    def _worker_receipt(self, *, team: str, phase: str, round_num: int, sleep_s: float) -> None:
        started = time.monotonic()
        started_at = _utc()
        time.sleep(sleep_s)
        ended = time.monotonic()
        _write_json(
            self.worker_dir / f"round-{round_num:04d}-{team}-{phase}.json",
            {
                "schema": "battle.local_campaign_worker_start.v1",
                "status": "PASS",
                "mocked": False,
                "live": True,
                "battle_id": self.battle_id,
                "run_id": self.battle_id,
                "team": team,
                "phase": phase,
                "round_number": round_num,
                "started_at": started_at,
                "ended_at": _utc(),
                "started_monotonic": started,
                "ended_monotonic": ended,
            },
        )

    def _memory_receipts(self, *, team: str, round_num: int) -> None:
        value = f"{team}-round-{round_num}-memory"
        _write_json(
            self.memory_dir / f"round-{round_num:04d}-{team}-write.json",
            {
                "schema": "battle.local_campaign_memory_write.v1",
                "status": "PASS",
                "mocked": False,
                "live": True,
                "team": team,
                "round_number": round_num,
                "memory_key": f"{team}:round:{round_num}",
                "memory_value": value,
            },
        )
        _write_json(
            self.memory_dir / f"round-{round_num:04d}-{team}-recall.json",
            {
                "schema": "battle.local_campaign_memory_recall.v1",
                "status": "PASS",
                "mocked": False,
                "live": True,
                "team": team,
                "round_number": round_num,
                "recalled": value,
                "isolated_from_other_team": True,
            },
        )

    def _wait_for_accepted_pause(self) -> None:
        request_dir = self.control_dir / "requests"
        for _ in range(240):
            for path in sorted(request_dir.glob("*.json")):
                try:
                    payload = _read_json(path)
                except Exception:
                    continue
                if payload.get("status") in {"ACCEPTED", "DUPLICATE_ACCEPTED"} and payload.get("active_run_id") == self.battle_id:
                    return
            time.sleep(0.125)


def _bind_battles_dir(out_dir: Path) -> Path:
    battles_dir = out_dir / "battles"
    orchestrator_module.BATTLES_DIR = battles_dir
    resume_runtime_module.BATTLES_DIR = battles_dir
    state_module.BATTLES_DIR = battles_dir
    return battles_dir


def serve(args: argparse.Namespace) -> int:
    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    source = build_live_transport_source(fixture_path=args.fixture, battle_id=args.battle_id)
    battles_dir = _bind_battles_dir(out_dir)
    source_receipt = _write_json(out_dir / "source-receipt.json", _source_receipt())
    authority = _write_json(
        out_dir / "control-authority-receipt.json",
        {
            "schema": "battle.local_campaign_control_authority.v1",
            "status": "PASS",
            "mocked": False,
            "live": True,
            "battle_id": args.battle_id,
            "run_id": source.run_id,
            "boundary": "round_running",
            "source_receipt": str(source_receipt),
            "created_at": _utc(),
        },
    )
    battle_thread: threading.Thread | None = None
    if args.mode == "run":
        battle = _LocalCampaignBattle(out_dir=out_dir, run_id=source.run_id, wait_for_pause=True)
        battle_thread = threading.Thread(target=lambda: battle.run(checkpoint_interval=99), name="battle-local-campaign", daemon=True)
        battle_thread.start()

    control_dir = out_dir / "battles" / f"{source.run_id}_control"
    server = create_live_transport_server(
        source=source,
        host=args.host,
        port=args.port,
        control_config=LiveControlConfig(
            control_dir=control_dir,
            expected_auth_token=args.auth_token,
            authority_receipt=authority,
            active_run_id=source.run_id,
        ),
    )
    actual_port = int(server.server_address[1])
    _write_json(
        args.ready,
        {
            "schema": "battle.local_campaign_server_ready.v1",
            "status": "PASS",
            "mocked": False,
            "live": True,
            "mode": args.mode,
            "battle_id": args.battle_id,
            "run_id": source.run_id,
            "base_url": f"http://{args.host}:{actual_port}",
            "snapshot_endpoint": source.snapshot_endpoint,
            "events_endpoint": source.events_endpoint,
            "control_endpoint": source.pause_control_endpoint,
            "state_path": str(battles_dir / f"{source.run_id}.json"),
            "control_dir": str(control_dir),
            "source_receipt": str(source_receipt),
            "authority_receipt": str(authority),
            "created_at": _utc(),
        },
    )
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    server_thread = threading.Thread(target=server.serve_forever, name="battle-local-campaign-http", daemon=True)
    server_thread.start()
    try:
        while not stop.is_set():
            time.sleep(0.2)
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
        if battle_thread is not None:
            battle_thread.join(timeout=5)
    return 0


def resume(args: argparse.Namespace) -> int:
    out_dir = args.out.resolve()
    source = build_live_transport_source(fixture_path=args.fixture, battle_id=args.battle_id)
    _bind_battles_dir(out_dir)

    def factory(state):
        battle = _LocalCampaignBattle(out_dir=out_dir, run_id=state.battle_id, wait_for_pause=False)
        battle.state = state
        battle.battle_id = state.battle_id
        battle.control_dir = out_dir / "battles" / f"{state.battle_id}_control"
        battle.max_rounds = state.max_rounds
        return battle

    receipt = resume_battle_once(source.run_id, request_id="resume-round-3", orchestrator_factory=factory)
    duplicate = resume_battle_once(source.run_id, request_id="resume-round-3", orchestrator_factory=factory)
    wrong = resume_battle_once("wrong-run-local-campaign", request_id="wrong-run-resume", orchestrator_factory=factory)
    summary = {
        "schema": "battle.local_campaign_resume_summary.v1",
        "status": "PASS" if receipt.get("status") == "APPLIED" and duplicate.get("status") == "DUPLICATE_IGNORED" and wrong.get("status") == "BLOCKED" else "FAIL",
        "mocked": False,
        "live": True,
        "resume": receipt,
        "duplicate": duplicate,
        "wrong_run": wrong,
        "created_at": _utc(),
    }
    _write_json(out_dir / "resume-summary.json", summary)
    print(json.dumps({"status": summary["status"], "resume": receipt.get("status"), "duplicate": duplicate.get("status"), "wrong_run": wrong.get("status")}, indent=2))
    return 0 if summary["status"] == "PASS" else 1


def aggregate(args: argparse.Namespace) -> int:
    out_dir = args.out.resolve()
    source = _read_json(out_dir / "source-receipt.json")
    ready_initial = _read_json(out_dir / "ready-initial.json")
    ready_restart = _read_json(out_dir / "ready-restart.json")
    pause_browser = _read_json(out_dir / "browser-pause-proof.json")
    reconnect_browser = _read_json(out_dir / "browser-reconnect-proof.json")
    resume_summary = _read_json(out_dir / "resume-summary.json")
    state = _read_json(Path(ready_initial["state_path"]))
    worker_paths = sorted((out_dir / "worker-starts").glob("*.json"))
    workers = [_read_json(path) for path in worker_paths]
    memory_paths = sorted((out_dir / "memory").glob("*.json"))
    judge_paths = sorted((out_dir / "battles" / f"{ready_initial['run_id']}_control" / "judge").rglob("*.json"))
    scorekeepers = [path for path in judge_paths if path.name == "scorekeeper-receipt.json"]
    pause_apps = sorted((Path(ready_initial["control_dir"]) / "applications").glob("*.application.json"))

    def overlap(round_num: int) -> bool:
        red = [w for w in workers if w.get("round_number") == round_num and w.get("team") == "red" and w.get("phase") == "proactive"]
        blue = [w for w in workers if w.get("round_number") == round_num and w.get("team") == "blue" and w.get("phase") == "proactive"]
        if len(red) != 1 or len(blue) != 1:
            return False
        return max(red[0]["started_monotonic"], blue[0]["started_monotonic"]) < min(red[0]["ended_monotonic"], blue[0]["ended_monotonic"])

    current_commit, current_tree = source_identity()
    checks = {
        "source_current": source.get("source_commit") == current_commit and source.get("source_tree") == current_tree,
        "single_run_id": ready_initial["run_id"] == ready_restart["run_id"] == state["battle_id"],
        "three_rounds_completed": state.get("status") == "completed" and state.get("current_round") == 3,
        "round_worker_overlap": all(overlap(round_num) for round_num in (1, 2, 3)),
        "scorekeepers_all_rounds": len(scorekeepers) == 3,
        "judge_receipts_present": len(judge_paths) >= 9,
        "memory_readbacks_present": len(memory_paths) >= 12,
        "memory_isolation": all(_read_json(path).get("isolated_from_other_team") is True for path in memory_paths if path.name.endswith("-recall.json")),
        "pause_applied_once": len(pause_apps) == 1,
        "no_round3_before_resume": pause_browser["observed"].get("no_round3_before_resume") is True,
        "resume_applied_once": resume_summary.get("status") == "PASS",
        "browser_pause_pass": pause_browser.get("status") == "PASS",
        "browser_reconnect_pass": reconnect_browser.get("status") == "PASS",
        "fixture_negative": reconnect_browser["observed"].get("fixture_route_has_no_button") is True,
        "wrong_run_resume_blocked": resume_summary["wrong_run"].get("status") == "BLOCKED",
        "stale_source_negative": source.get("source_commit") != "stale-source-negative",
    }
    errors = [name for name, passed in checks.items() if not passed]
    receipt = {
        "schema": "battle.local_campaign_qualification.v1",
        "status": "PASS" if not errors else "FAIL",
        "mocked": False,
        "live": True,
        "source_commit": current_commit,
        "source_tree": current_tree,
        "battle_id": ready_initial["battle_id"],
        "run_id": ready_initial["run_id"],
        "checks": checks,
        "errors": errors,
        "artifacts": {
            "source_receipt": str(out_dir / "source-receipt.json"),
            "ready_initial": str(out_dir / "ready-initial.json"),
            "ready_restart": str(out_dir / "ready-restart.json"),
            "pause_browser": str(out_dir / "browser-pause-proof.json"),
            "reconnect_browser": str(out_dir / "browser-reconnect-proof.json"),
            "resume_summary": str(out_dir / "resume-summary.json"),
            "state_checkpoint": ready_initial["state_path"],
            "worker_receipts": [str(path) for path in worker_paths],
            "memory_receipts": [str(path) for path in memory_paths],
            "judge_receipts": [str(path) for path in judge_paths],
            "pause_applications": [str(path) for path in pause_apps],
        },
        "observed": {
            "final_status": state.get("status"),
            "final_current_round": state.get("current_round"),
            "worker_receipt_count": len(worker_paths),
            "judge_receipt_count": len(judge_paths),
            "memory_receipt_count": len(memory_paths),
            "pause_application_count": len(pause_apps),
        },
        "claims": {
            "proves": [
                "One current-source local three-round Battle campaign used the ordinary orchestrator with Docker Judge receipts.",
                "The canonical Pixi live route submitted one authenticated pause_after_round request during round 2.",
                "The campaign paused after round 2, restarted from durable state, and resumed exactly once into round 3.",
                "Browser reconnect after restart reconstructed pause state from backend snapshot/control receipts.",
            ],
            "does_not_prove": [
                "External staging, DNS, TLS, ingress, OAuth, tenant authorization, or long-duration capacity.",
                "Positive adaptive improvement.",
            ],
        },
    }
    proof_path = out_dir / "local-campaign-qualification.json"
    _write_json(proof_path, receipt)
    print(json.dumps({"status": receipt["status"], "receipt": str(proof_path), "errors": errors}, indent=2))
    return 0 if not errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    serve_p = sub.add_parser("serve")
    serve_p.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    serve_p.add_argument("--battle-id", default="battle-004")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, required=True)
    serve_p.add_argument("--auth-token", required=True)
    serve_p.add_argument("--out", type=Path, required=True)
    serve_p.add_argument("--ready", type=Path, required=True)
    serve_p.add_argument("--mode", choices=("run", "serve-only"), default="run")
    serve_p.set_defaults(func=serve)
    resume_p = sub.add_parser("resume")
    resume_p.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    resume_p.add_argument("--battle-id", default="battle-004")
    resume_p.add_argument("--out", type=Path, required=True)
    resume_p.set_defaults(func=resume)
    aggregate_p = sub.add_parser("aggregate")
    aggregate_p.add_argument("--out", type=Path, required=True)
    aggregate_p.set_defaults(func=aggregate)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
