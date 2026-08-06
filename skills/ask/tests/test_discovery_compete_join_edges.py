"""Discovery probes for compete/roundtable join edge cases — hunting for
places /ask fails or degrades incorrectly. Deterministic (no browser)."""

from __future__ import annotations

import importlib.util
import json
import sys
from types import SimpleNamespace
from pathlib import Path

WORKER = Path(__file__).resolve().parents[1] / "scripts" / "tau_roundtable_worker.py"
spec = importlib.util.spec_from_file_location("trw_discovery", WORKER)
w = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = w
spec.loader.exec_module(w)

START = {
    "goal": {"goal_id": "g", "goal_version": 1, "immutable_goal": "r", "goal_hash": "0" * 64},
    "github": {"repo": "grahama1970/agent-skills", "target": "skills/ask"},
}


def _seat(root: Path, node_id: str, handler: str, *, ok: bool, chars: int,
          features: list[str] | None = None, failure_code=None) -> None:
    d = root / node_id
    d.mkdir(parents=True)
    resp = d / "response.md"
    body = "x" * chars
    for f in features or []:
        body += f"\nVERIFIED_FEATURE: {f}"
    resp.write_text(body, encoding="utf-8")
    (d / "node-receipt.json").write_text(json.dumps({
        "schema": "ask.tau_dag_handler_receipt.v1",
        "node_id": node_id, "handler": handler,
        "status": "PASS" if ok else "NEEDS_ATTENTION",
        "ok": ok, "live": True, "provider_live": ok,
        "failure": None if ok else "x", "failure_code": failure_code,
        "response_path": str(resp), "response_chars": len(body),
        "submit_meta": {"model": handler},
    }), encoding="utf-8")


def _judge(root: Path, verdict_line: str, *, ok: bool = True) -> None:
    d = root / "judge"
    d.mkdir(parents=True)
    resp = d / "response.md"
    resp.write_text(f"Scored both.\n{verdict_line}\n", encoding="utf-8")
    (d / "node-receipt.json").write_text(json.dumps({
        "schema": "ask.tau_dag_handler_receipt.v1",
        "node_id": "judge", "handler": "webgpt",
        "status": "PASS" if ok else "NEEDS_ATTENTION", "ok": ok,
        "response_path": str(resp), "response_chars": 40, "failure_code": None,
    }), encoding="utf-8")


def _join_args() -> SimpleNamespace:
    return SimpleNamespace(
        workflow_mode="roundtable", node_id="join", handler="join", topology="concurrent",
        request="r", immutable_goal="r", next_agent="human",
        evidence=["roundtable_join_receipt", "handler_response_index"], prior_node=[],
    )


def _compete_args(tmp_path: Path) -> SimpleNamespace:
    a = _join_args()
    a.workflow_mode = "compete"
    req = tmp_path / "request.json"
    req.write_text(json.dumps({"schema": "ask.tau_dag_request.v1", "request": "Write add_numbers",
                               "criteria": ["best-practices-python compliance"], "immutable_goal": "r"}), encoding="utf-8")
    a.request_file = str(req)
    return a


def _receipt(join_dir: Path) -> dict:
    return json.loads((join_dir / "node-receipt.json").read_text(encoding="utf-8"))


# ---- roundtable join probes ---------------------------------------------

def test_all_seats_fail_is_not_pass(tmp_path: Path) -> None:
    _seat(tmp_path, "handler-webgpt", "webgpt", ok=False, chars=0)
    _seat(tmp_path, "handler-webkimi", "webkimi", ok=False, chars=0)
    jd = tmp_path / "join"; jd.mkdir()
    w._run_join(_join_args(), START, jd)
    assert _receipt(jd)["status"] != "PASS"


def test_mixed_seats_degraded_with_removed(tmp_path: Path) -> None:
    _seat(tmp_path, "handler-webclaude", "webclaude", ok=True, chars=5000)
    _seat(tmp_path, "handler-webgpt", "webgpt", ok=False, chars=0, failure_code="browser_tab_unverified_with_multiple_provider_tabs")
    jd = tmp_path / "join"; jd.mkdir()
    w._run_join(_join_args(), START, jd)
    r = _receipt(jd)
    assert r["status"] == "DEGRADED"
    assert r["removed_seats"] == ["webgpt"]
    assert r["degraded_seats"][0]["failure_code"] == "browser_tab_unverified_with_multiple_provider_tabs"


def test_ok_seat_with_zero_chars_is_not_delivered(tmp_path: Path) -> None:
    # A seat that reports ok=true but returned nothing must not count as delivered.
    _seat(tmp_path, "handler-webgpt", "webgpt", ok=True, chars=0)
    jd = tmp_path / "join"; jd.mkdir()
    w._run_join(_join_args(), START, jd)
    r = _receipt(jd)
    st = r["seat_terminal_states"][0]
    assert st["delivered"] is False


# ---- compete join probes ------------------------------------------------

def test_compete_judge_valid_winner_wins(tmp_path: Path) -> None:
    _seat(tmp_path, "handler-a", "oc-deepseek", ok=True, chars=500, features=["f1"])
    _seat(tmp_path, "handler-b", "gpt-5.5", ok=True, chars=500, features=["f2"])
    _judge(tmp_path, "WINNER: handler-b")
    jd = tmp_path / "join"; jd.mkdir()
    w._run_compete_join(_compete_args(tmp_path), START, jd)
    card = json.loads((jd / "compete-scorecard.json").read_text())
    assert card["winner_handler"] == "gpt-5.5"
    assert card["winner_selected_by"] == "judge_verdict"


def test_compete_judge_invalid_winner_is_blocker(tmp_path: Path) -> None:
    _seat(tmp_path, "handler-a", "oc-deepseek", ok=True, chars=500, features=["f1"])
    _seat(tmp_path, "handler-b", "gpt-5.5", ok=True, chars=500, features=["f2"])
    _judge(tmp_path, "WINNER: handler-ghost")
    jd = tmp_path / "join"; jd.mkdir()
    w._run_compete_join(_compete_args(tmp_path), START, jd)
    card = json.loads((jd / "compete-scorecard.json").read_text())
    assert card["status"] != "PASS"


def test_compete_judge_missing_winner_line_is_blocker(tmp_path: Path) -> None:
    _seat(tmp_path, "handler-a", "oc-deepseek", ok=True, chars=500, features=["f1"])
    _seat(tmp_path, "handler-b", "gpt-5.5", ok=True, chars=500, features=["f2"])
    _judge(tmp_path, "I could not decide.")
    jd = tmp_path / "join"; jd.mkdir()
    w._run_compete_join(_compete_args(tmp_path), START, jd)
    card = json.loads((jd / "compete-scorecard.json").read_text())
    assert card["status"] != "PASS"


def test_compete_failed_judge_seat_is_blocker(tmp_path: Path) -> None:
    _seat(tmp_path, "handler-a", "oc-deepseek", ok=True, chars=500, features=["f1"])
    _seat(tmp_path, "handler-b", "gpt-5.5", ok=True, chars=500, features=["f2"])
    _judge(tmp_path, "WINNER: handler-a", ok=False)
    jd = tmp_path / "join"; jd.mkdir()
    w._run_compete_join(_compete_args(tmp_path), START, jd)
    card = json.loads((jd / "compete-scorecard.json").read_text())
    assert card["status"] != "PASS"
