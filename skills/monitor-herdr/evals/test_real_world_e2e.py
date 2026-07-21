from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "monitor_herdr.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("monitor_herdr", SCRIPT)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
sys.modules["monitor_herdr"] = monitor
SPEC.loader.exec_module(monitor)


class EvalHerdrClient:
    def __init__(
        self,
        *,
        panes: list[dict[str, Any]],
        text_by_pane: dict[str, str],
        after_first_read_by_pane: dict[str, str] | None = None,
        explain_by_pane: dict[str, dict[str, Any]] | None = None,
        fail_send_text: bool = False,
        confirm_submission: bool = True,
    ) -> None:
        self.panes = panes
        self.text_by_pane = dict(text_by_pane)
        self.after_first_read_by_pane = after_first_read_by_pane or {}
        self.explain_by_pane = explain_by_pane or {}
        self.fail_send_text = fail_send_text
        self.confirm_submission = confirm_submission
        self.trace: list[dict[str, Any]] = []
        self.socket_path = Path("/tmp/monitor-confused-eval-herdr.sock")
        self.enter_count = 0
        self.sent_text_count = 0
        self.read_count_by_pane: dict[str, int] = {}

    def call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            result = self._call(method, params)
        except RuntimeError:
            raise
        response = {"id": method, "result": result}
        self.trace.append({"request": {"method": method, "params": params}, "response": response})
        return result

    def _call(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "workspace.list":
            return {"workspaces": [{"workspace_id": "w1", "label": "codex", "number": 1}]}
        if method == "pane.list":
            return {"panes": self.panes}
        if method == "pane.read":
            pane_id = str(params["pane_id"])
            self.read_count_by_pane[pane_id] = self.read_count_by_pane.get(pane_id, 0) + 1
            if self.read_count_by_pane[pane_id] > 1 and pane_id in self.after_first_read_by_pane:
                self.text_by_pane[pane_id] = self.after_first_read_by_pane[pane_id]
                del self.after_first_read_by_pane[pane_id]
            return {"type": "pane_read", "read": {"text": self.text_by_pane[pane_id]}}
        if method == "agent.explain":
            pane_id = str(params["target"])
            explain = self.explain_by_pane.get(pane_id, {"state": "idle", "matched_rule": "codex_prompt_idle_ready"})
            return {"type": "agent_explain", "explain": explain}
        if method == "pane.send_text":
            pane_id = str(params["pane_id"])
            if self.fail_send_text:
                self.trace.append({
                    "request": {"method": method, "params": params},
                    "response": {"error": {"code": "eval_send_text_failed"}},
                })
                raise RuntimeError("eval send_text failed")
            self.sent_text_count += 1
            self.text_by_pane[pane_id] += "\n" + str(params["text"])
            return {"type": "ok"}
        if method == "pane.send_keys":
            pane_id = str(params["pane_id"])
            if params.get("keys") == ["enter"]:
                self.enter_count += 1
                if self.confirm_submission:
                    self.text_by_pane[pane_id] += "\nRunning UserPromptSubmit hook\nWorking (1s * esc to interrupt)"
            return {"type": "ok"}
        raise AssertionError(method)


def receipt(tmp_path: Path) -> dict[str, Any]:
    receipt_dir = tmp_path / "receipt"
    receipt_dir.mkdir()
    return {
        "schema": "agent_skills.monitor_herdr.tick_receipt.v1",
        "run_id": "eval",
        "mocked": False,
        "live": False,
        "api": "eval_herdr_socket_fixture",
        "apply": True,
        "receipt_dir": str(receipt_dir),
        "events_path": str(receipt_dir / "events.jsonl"),
        "log_file": str(tmp_path / "log.jsonl"),
        "state_path": str(tmp_path / "state.json"),
        "selection": {},
        "workspace": None,
        "api_trace": [],
        "observed_panes": 0,
        "stopped_panes": [],
        "selected_panes": [],
        "prompts": [],
        "errors": [],
    }


def run_eval_tick(tmp_path: Path, client: EvalHerdrClient) -> tuple[int, dict[str, Any]]:
    original_state = monitor.STATE_PATH
    original_wait = monitor.wait_for_agent_idle
    try:
        monitor.STATE_PATH = tmp_path / "state.json"
        monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
        return monitor.tick_locked(
            client=client,
            receipt=receipt(tmp_path),
            events_path=tmp_path / "receipt" / "events.jsonl",
            apply=True,
            space="codex",
            cwd_prefix=str(tmp_path),
            include_agents={"codex"},
            stopped_statuses={"done", "idle", "blocked", "unknown"},
            cooldown_seconds=0,
            unconfirmed_cooldown_seconds=600,
            max_prompts=20,
            only_obvious_early_stops=False,
        )
    finally:
        monitor.STATE_PATH = original_state
        monitor.wait_for_agent_idle = original_wait


def test_eval_plain_no_immutable_goal_never_enters_prompt(tmp_path: Path) -> None:
    project = tmp_path / "nogal"
    project.mkdir()
    client = EvalHerdrClient(
        panes=[{"workspace_id": "w1", "pane_id": "w1:p1", "agent": "codex", "agent_status": "done", "cwd": str(project)}],
        text_by_pane={"w1:p1": "Idle composer with no explicit hook failure."},
    )

    exit_code, result = run_eval_tick(tmp_path, client)

    assert exit_code == 0
    assert result["ok"] is True
    assert result["stopped_panes"][0]["classification"] == "no_immutable_goal"
    assert result["selected_panes"] == []
    assert client.sent_text_count == 0
    assert client.enter_count == 0


def test_eval_no_immutable_goal_with_explicit_early_stop_enters_prompt(tmp_path: Path) -> None:
    project = tmp_path / "nogal_early"
    project.mkdir()
    client = EvalHerdrClient(
        panes=[{"workspace_id": "w1", "pane_id": "w1:p1", "agent": "codex", "agent_status": "done", "cwd": str(project)}],
        text_by_pane={"w1:p1": "Stop hook (stopped)\nWhat remains is a broader route audit."},
    )

    exit_code, result = run_eval_tick(tmp_path, client)

    assert exit_code == 0
    assert result["ok"] is True
    assert result["stopped_panes"][0]["classification"] == "stopped_or_early_stop"
    assert result["selected_panes"][0]["selection_reasons"][-1] == "immutable_goal_unknown_but_early_stop_marker"
    assert result["prompts"][0]["sent"] is True
    assert client.sent_text_count == 1
    assert client.enter_count == 1


def test_eval_goal_achieved_line_never_enters_prompt(tmp_path: Path) -> None:
    project = tmp_path / "done"
    project.mkdir()
    (project / "GOAL.md").write_text("Finish the receipt-backed change.", encoding="utf-8")
    client = EvalHerdrClient(
        panes=[{"workspace_id": "w1", "pane_id": "w1:p2", "agent": "codex", "agent_status": "done", "cwd": str(project)}],
        text_by_pane={"w1:p2": "gpt-5.5 high · repo      Goal achieved (4m 12s)"},
    )

    exit_code, result = run_eval_tick(tmp_path, client)

    assert exit_code == 0
    assert result["ok"] is True
    assert result["stopped_panes"][0]["classification"] == "goal_stop_allowed"
    assert result["selected_panes"] == []
    assert client.sent_text_count == 0
    assert client.enter_count == 0


def test_eval_fallback_idle_never_enters_prompt(tmp_path: Path) -> None:
    project = tmp_path / "fallback"
    project.mkdir()
    (project / "GOAL.md").write_text("Finish the route audit.", encoding="utf-8")
    client = EvalHerdrClient(
        panes=[{"workspace_id": "w1", "pane_id": "w1:p3", "agent": "codex", "agent_status": "idle", "cwd": str(project)}],
        text_by_pane={"w1:p3": "What remains is implementation."},
        explain_by_pane={"w1:p3": {"state": "idle", "fallback_reason": "default_known_agent_idle_fallback"}},
    )

    exit_code, result = run_eval_tick(tmp_path, client)

    assert exit_code == 0
    assert result["ok"] is True
    assert result["stopped_panes"][0]["classification"] == "blocked_or_unknown_observe_only"
    assert result["selected_panes"] == []
    assert client.sent_text_count == 0
    assert client.enter_count == 0


def test_eval_send_text_failure_tick_returns_nonzero_and_needs_attention(tmp_path: Path) -> None:
    project = tmp_path / "sendfail"
    project.mkdir()
    (project / "GOAL.md").write_text("Finish the route audit.", encoding="utf-8")
    client = EvalHerdrClient(
        panes=[{"workspace_id": "w1", "pane_id": "w1:p4", "agent": "codex", "agent_status": "done", "cwd": str(project)}],
        text_by_pane={"w1:p4": "What remains is the mobile viewport pass."},
        fail_send_text=True,
    )

    exit_code, result = run_eval_tick(tmp_path, client)

    assert exit_code == 1
    assert result["ok"] is False
    assert result["status"] == "NEEDS_ATTENTION"
    assert result["prompts"][0]["skip_reason"] == "send_text_failed"
    assert result["prompts"][0]["send_failed"] is True
    assert client.enter_count == 0


def test_eval_no_submission_marker_after_enter_returns_nonzero(tmp_path: Path) -> None:
    project = tmp_path / "notentered"
    project.mkdir()
    (project / "GOAL.md").write_text("Finish the route audit.", encoding="utf-8")
    client = EvalHerdrClient(
        panes=[{"workspace_id": "w1", "pane_id": "w1:p5", "agent": "codex", "agent_status": "done", "cwd": str(project)}],
        text_by_pane={"w1:p5": "What remains is the receipt deep link."},
        confirm_submission=False,
    )

    exit_code, result = run_eval_tick(tmp_path, client)

    assert exit_code == 1
    assert result["ok"] is False
    assert result["status"] == "NEEDS_ATTENTION"
    assert result["prompts"][0]["api_sent"] is True
    assert result["prompts"][0]["submit_confirmed"] is False
    assert result["prompts"][0]["input_modified"] is True
    assert client.enter_count == 2


def test_eval_invalid_receipt_appearing_before_send_does_not_suppress_prompt(tmp_path: Path) -> None:
    project = tmp_path / "stale"
    project.mkdir()
    (project / "GOAL.md").write_text("Finish the route audit.", encoding="utf-8")
    client = EvalHerdrClient(
        panes=[{"workspace_id": "w1", "pane_id": "w1:p6", "agent": "codex", "agent_status": "done", "cwd": str(project)}],
        text_by_pane={"w1:p6": "What remains is the receipt deep link."},
        after_first_read_by_pane={"w1:p6": "Immutable Goal: ACHIEVED_WITH_RECEIPT:missing.json\n"},
    )

    exit_code, result = run_eval_tick(tmp_path, client)

    assert exit_code == 0
    assert result["ok"] is True
    assert result["prompts"][0]["sent"] is True
    assert result["prompts"][0].get("skip_reason") != "pre_submit_stop_allowed"
    assert client.sent_text_count == 1
    assert client.enter_count == 1
