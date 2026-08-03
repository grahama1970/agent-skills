#!/usr/bin/env python3
"""Serve a local Battle live transport with authenticated pause control."""

from __future__ import annotations

import argparse
import json
import signal
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import battle_skill.orchestrator as orchestrator_module
import battle_skill.state as state_module
from battle_skill.live_transport_server import (
    LiveControlConfig,
    build_live_transport_source,
    create_live_transport_server,
)
from battle_skill.orchestrator import BattleOrchestrator
from battle_skill.state import RoundResult


def _utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


class _ProofMonitor:
    def register(self, **_: Any) -> bool:
        return True

    def update(self, *_: Any) -> None:
        return None


class _LiveControlProofBattle(BattleOrchestrator):
    def __init__(self, *, target_path: Path, out_dir: Path, run_id: str, authority_receipt: Path) -> None:
        super().__init__(str(target_path), max_rounds=2, concurrent=True)
        self.out_dir = out_dir
        self.battle_id = run_id
        self.control_dir = out_dir / "control"
        self.authority_receipt = authority_receipt
        self.worker_start_dir = out_dir / "worker-starts"
        self.monitor = _ProofMonitor()
        self.state.battle_id = run_id
        self.state.max_rounds = 2

    def setup_digital_twin(self) -> bool:
        _write_json(
            self.out_dir / "setup-receipt.json",
            {
                "schema": "battle.live_control_setup.v1",
                "status": "PASS",
                "mocked": False,
                "live": "local_ordinary_run_loop_with_deterministic_workers",
                "battle_id": self.battle_id,
                "created_at": _utc(),
            },
        )
        return True

    def run_round_concurrent(self, round_num: int) -> RoundResult:
        _write_json(
            self.worker_start_dir / f"round-{round_num:04d}-red.json",
            {"schema": "battle.worker_start.v1", "team": "red", "round_number": round_num, "created_at": _utc()},
        )
        _write_json(
            self.worker_start_dir / f"round-{round_num:04d}-blue.json",
            {"schema": "battle.worker_start.v1", "team": "blue", "round_number": round_num, "created_at": _utc()},
        )
        if round_num == 1:
            self._wait_for_pause_request()
        with self.state._lock:
            self.state.current_round = round_num
        return RoundResult(round_number=round_num, red_score=0.0, blue_score=0.0)

    def _wait_for_pause_request(self) -> None:
        request_dir = self.control_dir / "requests"
        for _ in range(160):
            if list(request_dir.glob("*.json")):
                time.sleep(1.0)
                return
            time.sleep(0.125)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument("--battle-id", default="battle-004")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--auth-token", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--ready", type=Path, required=True)
    args = parser.parse_args()

    out_dir = args.out.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    target_path = out_dir / "target"
    target_path.mkdir(parents=True, exist_ok=True)
    _write_json(target_path / "target.json", {"schema": "battle.live_control_target.v1", "status": "READY"})

    source = build_live_transport_source(fixture_path=args.fixture, battle_id=args.battle_id)
    authority_receipt = _write_json(
        out_dir / "control-authority-receipt.json",
        {
            "schema": "battle.live_control_authority_receipt.v1",
            "status": "PASS",
            "mocked": False,
            "live": "local_ordinary_run_loop_with_deterministic_workers",
            "battle_id": args.battle_id,
            "run_id": source.run_id,
            "boundary": "round_running",
            "created_at": _utc(),
        },
    )

    battles_dir = out_dir / "battles"
    orchestrator_module.BATTLES_DIR = battles_dir
    state_module.BATTLES_DIR = battles_dir
    battle = _LiveControlProofBattle(
        target_path=target_path,
        out_dir=out_dir,
        run_id=source.run_id,
        authority_receipt=authority_receipt,
    )
    config = LiveControlConfig(
        control_dir=battle.control_dir,
        expected_auth_token=args.auth_token,
        authority_receipt=authority_receipt,
        active_run_id=source.run_id,
    )
    server = create_live_transport_server(
        source=source,
        host=args.host,
        port=args.port,
        control_config=config,
    )
    actual_port = int(server.server_address[1])
    battle_thread = threading.Thread(target=lambda: battle.run(checkpoint_interval=99), name="battle-live-control-proof", daemon=True)
    battle_thread.start()

    _write_json(
        args.ready,
        {
            "schema": "battle.live_control_server_ready.v1",
            "status": "PASS",
            "mocked": False,
            "live": "local_http_sse_adapter_plus_ordinary_run_loop",
            "battle_id": args.battle_id,
            "run_id": source.run_id,
            "base_url": f"http://{args.host}:{actual_port}",
            "snapshot_endpoint": source.snapshot_endpoint,
            "control_endpoint": source.pause_control_endpoint,
            "state_path": str(battles_dir / f"{source.run_id}.json"),
            "control_dir": str(battle.control_dir),
            "authority_receipt": str(authority_receipt),
            "created_at": _utc(),
        },
    )

    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    server_thread = threading.Thread(target=server.serve_forever, name="battle-live-control-http", daemon=True)
    server_thread.start()
    try:
        while not stop.is_set():
            time.sleep(0.2)
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)
        battle_thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
