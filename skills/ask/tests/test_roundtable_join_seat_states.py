"""#1257: the roundtable join must surface each seat's terminal state and the
degraded/removed seats at the top level, not only inside node-artifacts."""

from __future__ import annotations

import importlib.util
import json
import sys
from types import SimpleNamespace
from pathlib import Path

WORKER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tau_roundtable_worker.py"
spec = importlib.util.spec_from_file_location("trw_seat_states", WORKER_PATH)
worker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = worker
spec.loader.exec_module(worker)


def _seat(root: Path, node_id: str, handler: str, *, ok: bool, chars: int, failure_code=None) -> None:
    d = root / node_id
    d.mkdir(parents=True)
    resp = d / "response.md"
    resp.write_text("x" * chars, encoding="utf-8")
    (d / "node-receipt.json").write_text(json.dumps({
        "schema": "ask.tau_dag_handler_receipt.v1",
        "node_id": node_id, "handler": handler,
        "status": "PASS" if ok else "NEEDS_ATTENTION",
        "ok": ok, "live": True, "provider_live": ok,
        "failure": None if ok else "reaped", "failure_code": failure_code,
        "response_path": str(resp), "response_chars": chars,
        "submit_meta": {"model": handler},
    }), encoding="utf-8")


def test_join_surfaces_per_seat_terminal_states(tmp_path: Path) -> None:
    _seat(tmp_path, "handler-webclaude", "webclaude", ok=True, chars=15500)
    _seat(tmp_path, "handler-webgpt", "webgpt", ok=False, chars=0, failure_code="waiting_for_acceptance")
    _seat(tmp_path, "handler-webkimi", "webkimi", ok=False, chars=0, failure_code="lane_deadline_reaped")
    join_dir = tmp_path / "join"
    join_dir.mkdir()
    args = SimpleNamespace(
        workflow_mode="roundtable", node_id="join", handler="join", topology="concurrent",
        request="r", immutable_goal="r", next_agent="human",
        evidence=["roundtable_join_receipt", "handler_response_index"], prior_node=[],
    )
    start = {"goal": {"goal_id": "g", "goal_version": 1, "immutable_goal": "r", "goal_hash": "0" * 64},
             "github": {"repo": "grahama1970/agent-skills", "target": "skills/ask"}}
    worker._run_join(args, start, join_dir)
    receipt = json.loads((join_dir / "node-receipt.json").read_text(encoding="utf-8"))

    states = {s["handler"]: s for s in receipt["seat_terminal_states"]}
    assert states["webclaude"]["delivered"] is True
    assert states["webgpt"]["delivered"] is False
    assert states["webgpt"]["failure_code"] == "waiting_for_acceptance"
    assert states["webkimi"]["failure_code"] == "lane_deadline_reaped"
    # removed_seats and degraded_seats are non-null and name the two failures
    assert set(receipt["removed_seats"]) == {"webgpt", "webkimi"}
    assert {d["handler"] for d in receipt["degraded_seats"]} == {"webgpt", "webkimi"}
