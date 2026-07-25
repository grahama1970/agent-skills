from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "monitor_herdr.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("monitor_herdr", SCRIPT)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
sys.modules["monitor_herdr"] = monitor
SPEC.loader.exec_module(monitor)


class FakeHerdr:
    def __init__(self, text: str, explain: dict | None = None) -> None:
        self.text = text
        self.explain = explain or {"state": "done", "matched_rule": "codex_prompt_done_ready"}

    def call(self, method: str, params: dict) -> dict:
        if method == "pane.read":
            return {"type": "pane_read", "read": {"text": self.text}}
        if method == "agent.explain":
            return {"type": "agent_explain", "explain": self.explain}
        raise AssertionError(method)


class FakeSubmitHerdr:
    def __init__(self) -> None:
        self.trace = []
        self.enter_count = 0
        self.ctrl_j_count = 0
        self.sent_text = False
        self.socket_path = Path("/tmp/fake-herdr.sock")

    def call(self, method: str, params: dict) -> dict:
        response = {"id": method, "result": {"type": "ok"}}
        self.trace.append({"request": {"method": method, "params": params}, "response": response})
        if method == "pane.send_text":
            self.sent_text = True
        if method == "pane.send_keys" and params.get("keys") == ["enter"]:
            self.enter_count += 1
        if method == "pane.send_keys" and params.get("keys") == ["ctrl+j"]:
            self.ctrl_j_count += 1
        if method in {"pane.send_text", "pane.send_keys"}:
            return {"type": "ok"}
        if method == "pane.read":
            if not self.sent_text:
                return {"type": "pane_read", "read": {"text": "Codex composer ready"}}
            if self.enter_count < 2:
                return {
                    "type": "pane_read",
                    "read": {
                        "text": (
                            "RESTART CHECK FROM monitor-herdr\n"
                            "Disposition: <choose exactly one of RESUMING_NOW | CAN_SELF_UNBLOCK_WEBGPT>\n"
                            "If the immutable goal is known and not achieved, keep going.\n"
                        )
                    },
                }
            return {"type": "pane_read", "read": {"text": "Running UserPromptSubmit hook\nWorking (1s * esc to interrupt)"}}
        if method == "agent.explain":
            return {"type": "agent_explain", "explain": {"state": "idle", "matched_rule": "codex_prompt_idle_ready"}}
        raise AssertionError(method)


class FakeRealSubmitHerdr(monitor.HerdrClient):
    def __init__(self) -> None:
        super().__init__(Path("/tmp/fake-herdr.sock"))
        self.sent_text = False
        self.enter_count = 0
        self.read_count = 0

    def call(self, method: str, params: dict) -> dict:
        response = {"id": method, "result": {"type": "ok"}}
        self.trace.append({"request": {"method": method, "params": params}, "response": response})
        if method == "pane.send_text":
            self.sent_text = True
        if method == "pane.send_keys" and params.get("keys") == ["enter"]:
            self.enter_count += 1
        if method == "pane.read":
            self.read_count += 1
            if self.read_count == 1:
                return {"type": "pane_read", "read": {"text": "Codex composer ready"}}
            return {"type": "pane_read", "read": {"text": "UserPromptSubmit hook (completed)\nWorking (1s * esc to interrupt)"}}
        if method == "agent.explain":
            return {"type": "agent_explain", "explain": {"state": "idle", "matched_rule": "codex_prompt_idle_ready"}}
        return {"type": "ok"}


class FakePaneRunStrandsPromptHerdr(monitor.HerdrClient):
    def __init__(self) -> None:
        super().__init__(Path("/tmp/fake-herdr.sock"))
        self.sent_text = False
        self.enter_count = 0
        self.ctrl_j_count = 0
        self.read_count = 0

    def call(self, method: str, params: dict) -> dict:
        response = {"id": method, "result": {"type": "ok"}}
        self.trace.append({"request": {"method": method, "params": params}, "response": response})
        if method == "pane.send_text":
            self.sent_text = True
        if method == "pane.send_keys" and params.get("keys") == ["enter"]:
            self.enter_count += 1
        if method == "pane.send_keys" and params.get("keys") == ["ctrl+j"]:
            self.ctrl_j_count += 1
        if method in {"pane.send_text", "pane.send_keys"}:
            return {"type": "ok"}
        if method == "pane.read":
            self.read_count += 1
            if self.read_count == 1:
                return {"type": "pane_read", "read": {"text": "Codex composer ready"}}
            if self.sent_text and self.enter_count >= 1:
                return {"type": "pane_read", "read": {"text": "Running UserPromptSubmit hook\nWorking (1s * esc to interrupt)"}}
            return {
                "type": "pane_read",
                "read": {
                    "text": (
                        "RESTART CHECK FROM monitor-herdr\n"
                        "Unblock Attempts: brave-search=<USED:path | NOT_APPLICABLE:reason>\n"
                        "Disposition: <choose exactly one of RESUMING_NOW | CAN_SELF_UNBLOCK_WEBGPT>\n"
                        "If the immutable goal is known and not achieved, keep going.\n"
                        "›\n"
                        "gpt-5.5 high · repo"
                    )
                },
            }
        if method == "agent.explain":
            return {"type": "agent_explain", "explain": {"state": "idle", "matched_rule": "codex_prompt_idle_ready"}}
        return {"type": "ok"}


class FakeFallbackIdleHerdr(FakeSubmitHerdr):
    def call(self, method: str, params: dict) -> dict:
        if method == "agent.explain":
            return {
                "type": "agent_explain",
                "explain": {"state": "idle", "fallback_reason": "default_known_agent_idle_fallback"},
            }
        return super().call(method, params)


class FakeFailSendTextHerdr(FakeSubmitHerdr):
    def call(self, method: str, params: dict) -> dict:
        if method == "pane.send_text":
            self.trace.append({"request": {"method": method, "params": params}, "response": {"error": {"code": "fail"}}})
            raise RuntimeError("send failed")
        return super().call(method, params)


class FakeWorkingAfterEnterHerdr(FakeSubmitHerdr):
    def call(self, method: str, params: dict) -> dict:
        if method == "agent.explain" and self.enter_count >= 1:
            return {"type": "agent_explain", "explain": {"state": "working"}}
        return super().call(method, params)


class FakeWrappedPromptAfterEnterHerdr(FakeSubmitHerdr):
    def call(self, method: str, params: dict) -> dict:
        response = {"id": method, "result": {"type": "ok"}}
        self.trace.append({"request": {"method": method, "params": params}, "response": response})
        if method == "pane.send_keys" and params.get("keys") == ["enter"]:
            self.enter_count += 1
        if method in {"pane.send_text", "pane.send_keys"}:
            if method == "pane.send_text":
                self.sent_text = True
            return {"type": "ok"}
        if method == "pane.read":
            if not self.sent_text:
                return {"type": "pane_read", "read": {"text": "Codex composer ready"}}
            if self.enter_count < 2:
                return {
                    "type": "pane_read",
                    "read": {
                        "text": (
                            "Unblock Attempts: brave-search=<USED:path | NOT_APPLICABLE:reason>; "
                            "browser-oracle=<USED:path | NOT_APPLICABLE:reason>\n"
                            "Disposition: <choose exactly one of RESUMING_NOW | BLOCKED_NEEDS_HUMAN | "
                            "CAN_SELF_UNBLOCK_WEBGPT | DONE_WITH_RECEIPT>\n"
                            "If the immutable goal is known and not achieved, keep going.\n"
                        )
                    },
                }
            return {"type": "pane_read", "read": {"text": "Running UserPromptSubmit hook\nWorking (1s * esc to interrupt)"}}
        if method == "agent.explain":
            return {"type": "agent_explain", "explain": {"state": "idle", "matched_rule": "codex_prompt_idle_ready"}}
        raise AssertionError(method)


class FakeLaggingPromptReadbackHerdr(FakeSubmitHerdr):
    def call(self, method: str, params: dict) -> dict:
        response = {"id": method, "result": {"type": "ok"}}
        self.trace.append({"request": {"method": method, "params": params}, "response": response})
        if method == "pane.send_text":
            self.sent_text = True
            return {"type": "ok"}
        if method == "pane.send_keys" and params.get("keys") == ["enter"]:
            self.enter_count += 1
            return {"type": "ok"}
        if method == "pane.read":
            if not self.sent_text:
                return {"type": "pane_read", "read": {"text": "Codex composer ready"}}
            if self.enter_count < 2:
                return {"type": "pane_read", "read": {"text": "Codex composer ready"}}
            return {"type": "pane_read", "read": {"text": "Running UserPromptSubmit hook\nWorking (1s * esc to interrupt)"}}
        if method == "agent.explain":
            return {"type": "agent_explain", "explain": {"state": "idle", "matched_rule": "codex_prompt_idle_ready"}}
        raise AssertionError(method)


class FakeDelayedWorkingAfterSecondEnterHerdr(FakeSubmitHerdr):
    def call(self, method: str, params: dict) -> dict:
        response = {"id": method, "result": {"type": "ok"}}
        self.trace.append({"request": {"method": method, "params": params}, "response": response})
        if method == "pane.send_text":
            self.sent_text = True
            return {"type": "ok"}
        if method == "pane.send_keys" and params.get("keys") == ["enter"]:
            self.enter_count += 1
            return {"type": "ok"}
        if method == "pane.read":
            return {"type": "pane_read", "read": {"text": "Codex composer ready"}}
        if method == "agent.explain":
            state = "working" if self.enter_count >= 2 else "idle"
            return {"type": "agent_explain", "explain": {"state": state, "matched_rule": "codex_prompt_idle_ready"}}
        raise AssertionError(method)


class FakeCtrlJSubmitHerdr(FakeSubmitHerdr):
    def call(self, method: str, params: dict) -> dict:
        response = {"id": method, "result": {"type": "ok"}}
        self.trace.append({"request": {"method": method, "params": params}, "response": response})
        if method == "pane.send_text":
            self.sent_text = True
            return {"type": "ok"}
        if method == "pane.send_keys" and params.get("keys") == ["enter"]:
            self.enter_count += 1
            return {"type": "ok"}
        if method == "pane.send_keys" and params.get("keys") == ["ctrl+j"]:
            self.ctrl_j_count += 1
            return {"type": "ok"}
        if method == "pane.read":
            if not self.sent_text:
                return {"type": "pane_read", "read": {"text": "Codex composer ready"}}
            if self.ctrl_j_count:
                return {"type": "pane_read", "read": {"text": "UserPromptSubmit hook (completed)\nWorking (1s * esc to interrupt)"}}
            return {"type": "pane_read", "read": {"text": "RESTART CHECK FROM monitor-herdr\nDisposition: <choose exactly one of RESUMING_NOW | DONE_WITH_RECEIPT>"}}
        if method == "agent.explain":
            state = "working" if self.ctrl_j_count else "idle"
            return {"type": "agent_explain", "explain": {"state": state, "matched_rule": "codex_prompt_idle_ready"}}
        raise AssertionError(method)


class FakeDelayedWorkingAfterCtrlJHerdr(FakeSubmitHerdr):
    def __init__(self) -> None:
        super().__init__()
        self.post_ctrl_j_explain_count = 0

    def call(self, method: str, params: dict) -> dict:
        response = {"id": method, "result": {"type": "ok"}}
        self.trace.append({"request": {"method": method, "params": params}, "response": response})
        if method == "pane.send_text":
            self.sent_text = True
            return {"type": "ok"}
        if method == "pane.send_keys" and params.get("keys") == ["enter"]:
            self.enter_count += 1
            return {"type": "ok"}
        if method == "pane.send_keys" and params.get("keys") == ["ctrl+j"]:
            self.ctrl_j_count += 1
            return {"type": "ok"}
        if method == "pane.read":
            return {"type": "pane_read", "read": {"text": "RESTART CHECK FROM monitor-herdr\n›\n\ngpt-5.5 high · repo"}}
        if method == "agent.explain":
            if self.ctrl_j_count:
                self.post_ctrl_j_explain_count += 1
            state = "working" if self.post_ctrl_j_explain_count >= 7 else "idle"
            return {"type": "agent_explain", "explain": {"state": state, "matched_rule": "codex_prompt_idle_ready"}}
        raise AssertionError(method)


class FakeCompletionBeforeSendHerdr(FakeSubmitHerdr):
    def __init__(self, text: str = "Immutable Goal: ACHIEVED_WITH_RECEIPT:receipt.json\n") -> None:
        super().__init__()
        self.completion_text = text

    def call(self, method: str, params: dict) -> dict:
        if method == "pane.read":
            return {
                "type": "pane_read",
                "read": {"text": self.completion_text},
            }
        return super().call(method, params)


def test_early_stop_transcript_restarts_done_agent(tmp_path: Path) -> None:
    (tmp_path / "IMMUTABLE_GOAL.md").write_text("Finish the full Battle route audit.", encoding="utf-8")
    text = """
    Next/Stop Condition
    No current blocker on this cleanup slice. What remains, if you want a stronger acceptance gate,
    is a broader route audit beyond top-level #battle.
    Stop hook (stopped)
    status response lacks operational detail.
    """
    pane = {
        "agent": "codex",
        "agent_status": "done",
        "cwd": str(tmp_path),
        "pane_id": "w11:pD",
    }
    candidate = monitor.classify_pane(
        FakeHerdr(text),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"done"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "restart_continue"
    assert candidate["immutable_goal"]["found"] is True
    assert any(item.startswith("early_stop:") for item in candidate["selection_reasons"])


def test_done_agent_without_goal_or_early_marker_can_stop(tmp_path: Path) -> None:
    pane = {
        "agent": "codex",
        "agent_status": "done",
        "cwd": str(tmp_path),
        "pane_id": "w11:pD",
    }

    candidate = monitor.classify_pane(
        FakeHerdr("Nothing else to do."),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"done"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "observe_only"
    assert candidate["classification"] == "no_immutable_goal"


def test_done_agent_without_goal_with_early_marker_restarts(tmp_path: Path) -> None:
    pane = {
        "agent": "codex",
        "agent_status": "done",
        "cwd": str(tmp_path),
        "pane_id": "w11:pD",
    }
    text = """
    Stop hook (stopped)
    What remains is a broader route audit.
    """

    candidate = monitor.classify_pane(
        FakeHerdr(text),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"done"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "restart_continue"
    assert candidate["classification"] == "stopped_or_early_stop"
    assert "immutable_goal_unknown_but_early_stop_marker" in candidate["selection_reasons"]


def test_done_agent_without_goal_and_no_early_marker_can_stop(tmp_path: Path) -> None:
    pane = {
        "agent": "codex",
        "agent_status": "done",
        "cwd": str(tmp_path),
        "pane_id": "w11:pD",
    }

    candidate = monitor.classify_pane(
        FakeHerdr("Idle with no explicit hook failure."),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"done"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "observe_only"
    assert candidate["classification"] == "no_immutable_goal"


def test_cwd_prefix_rejects_sibling_path(tmp_path: Path) -> None:
    prefix = tmp_path / "scope"
    sibling = tmp_path / "scope-other"
    prefix.mkdir()
    sibling.mkdir()
    (sibling / "GOAL.md").write_text("Do not monitor this sibling.", encoding="utf-8")
    pane = {
        "agent": "codex",
        "agent_status": "done",
        "cwd": str(sibling),
        "pane_id": "w11:pD",
    }

    assert monitor.classify_pane(
        FakeHerdr("Stop hook (stopped). What remains is work."),
        pane,
        cwd_prefix=str(prefix),
        include_agents={"codex"},
        stopped_statuses={"done"},
        only_obvious_early_stops=False,
    ) is None


def test_goal_discovery_never_crosses_project_boundary(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    subdir = repo / "subdir"
    subdir.mkdir(parents=True)
    (repo / ".git").mkdir()
    (tmp_path / "GOAL.md").write_text("Parent goal must not leak into repo.", encoding="utf-8")

    result = monitor.discover_immutable_goal(str(subdir), boundary=repo)

    assert result["found"] is False


def test_latest_goal_achieved_allows_stop_despite_old_early_marker(tmp_path: Path) -> None:
    (tmp_path / "GOAL.md").write_text("Finish feature.", encoding="utf-8")
    pane = {
        "agent": "codex",
        "agent_status": "done",
        "cwd": str(tmp_path),
        "pane_id": "w11:pS",
    }
    text = """
    Stop hook (blocked)
    Closure claim lacks deterministic proof.

    ─ Worked for 1m 10s ─────────────────────────────────────────────────────────

    › Implement {feature}

      gpt-5.5 high · ~/workspace/experiments/agent-skills      Goal achieved (1h 32m)
    """

    candidate = monitor.classify_pane(
        FakeHerdr(text),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"done"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "observe_only"


def test_monitor_prompt_boilerplate_does_not_override_goal_achieved(tmp_path: Path) -> None:
    (tmp_path / "GOAL.md").write_text("Finish feature.", encoding="utf-8")
    pane = {
        "agent": "codex",
        "agent_status": "done",
        "cwd": str(tmp_path),
        "pane_id": "w11:pS",
    }
    text = """
    RESTART CHECK FROM monitor-herdr
    Ask the human only for a missing decision, credential, authority, acceptance choice, or external state you cannot obtain.
    Disposition: <choose exactly one of RESUMING_NOW | BLOCKED_NEEDS_HUMAN | DONE_WITH_RECEIPT>

      gpt-5.5 high · ~/workspace/experiments/agent-skills      Goal achieved (1h 32m)
    """

    candidate = monitor.classify_pane(
        FakeHerdr(text),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"done"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "observe_only"


def test_human_blocker_is_not_restarted_without_early_marker(tmp_path: Path) -> None:
    (tmp_path / "GOAL.md").write_text("Deploy after approval.", encoding="utf-8")
    pane = {
        "agent": "claude",
        "agent_status": "unknown",
        "cwd": str(tmp_path),
        "pane_id": "w7E:p8",
    }

    candidate = monitor.classify_pane(
        FakeHerdr("Blocked: missing credential and human decision required."),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"claude"},
        stopped_statuses={"unknown"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "observe_only"
    assert candidate["classification"] == "blocked_or_unknown_observe_only"


def test_exhausted_blocker_claim_can_stay_blocked(tmp_path: Path) -> None:
    (tmp_path / "GOAL.md").write_text("Ship only after the production API key is available.", encoding="utf-8")
    pane = {
        "agent": "codex",
        "agent_status": "blocked",
        "cwd": str(tmp_path),
        "pane_id": "w11:pD",
    }
    text = """
    Status/Phase: blocked on missing credential
    Immutable Goal: BLOCKED:need production API key from human
    Unblock Attempts: brave-search=NOT_APPLICABLE:credential is private; browser-oracle=NOT_APPLICABLE:credential is private
    Evidence: NONE
    """

    candidate = monitor.classify_pane(
        FakeHerdr(text),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"blocked"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "observe_only"
    assert candidate["classification"] == "blocked_or_unknown_observe_only"


def test_idle_fallback_is_observe_only(tmp_path: Path) -> None:
    (tmp_path / "GOAL.md").write_text("Finish feature.", encoding="utf-8")
    pane = {
        "agent": "codex",
        "agent_status": "idle",
        "cwd": str(tmp_path),
        "pane_id": "w11:pD",
    }

    candidate = monitor.classify_pane(
        FakeHerdr("What remains is implementation.", explain={"state": "idle", "fallback_reason": "default_known_agent_idle_fallback"}),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"idle"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "observe_only"


def test_idle_without_matched_rule_is_observe_only(tmp_path: Path) -> None:
    (tmp_path / "GOAL.md").write_text("Finish feature.", encoding="utf-8")
    pane = {
        "agent": "codex",
        "agent_status": "idle",
        "cwd": str(tmp_path),
        "pane_id": "w11:pD",
    }

    candidate = monitor.classify_pane(
        FakeHerdr("What remains is implementation.", explain={"state": "idle"}),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"idle"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "observe_only"
    assert candidate["classification"] == "blocked_or_unknown_observe_only"


def test_any_fallback_or_skip_reason_sends_no_input() -> None:
    unsafe_explains = [
        {"state": "idle", "matched_rule": "codex_prompt_idle_ready", "fallback_reason": "any_nonempty_fallback"},
        {"state": "done", "matched_rule": "codex_prompt_done_ready", "skip_reason": "screen too small"},
        {"state": "idle", "matched_rule": "codex_prompt_idle_ready", "screen_detection_skip_reason": "no bottom buffer"},
        {"state": "done", "matched_rule": "codex_prompt_done_ready", "warning": "ambiguous"},
    ]

    for explain in unsafe_explains:
        assert monitor.explain_allows_input(explain) is False


def test_goal_status_line_with_goal_file_allows_stop(tmp_path: Path) -> None:
    (tmp_path / "GOAL.md").write_text("Finish feature.", encoding="utf-8")
    pane = {
        "agent": "codex",
        "agent_status": "done",
        "cwd": str(tmp_path),
        "pane_id": "w11:pD",
    }

    candidate = monitor.classify_pane(
        FakeHerdr("gpt-5.5 high · repo      Goal achieved (1h 32m)"),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"done"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "observe_only"


def test_goal_achieved_status_without_goal_file_allows_stop(tmp_path: Path) -> None:
    pane = {
        "agent": "codex",
        "agent_status": "done",
        "cwd": str(tmp_path),
        "pane_id": "w11:pD",
    }

    candidate = monitor.classify_pane(
        FakeHerdr("gpt-5.5 high · repo      Goal achieved (1h 32m)"),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"done"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "observe_only"
    assert candidate["classification"] == "goal_stop_allowed"


def test_goal_blocked_status_without_goal_file_restarts(tmp_path: Path) -> None:
    pane = {
        "agent": "codex",
        "agent_status": "done",
        "cwd": str(tmp_path),
        "pane_id": "w11:pD",
    }

    candidate = monitor.classify_pane(
        FakeHerdr("gpt-5.5 high · repo      Goal blocked (/goal resume)"),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"done"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "restart_continue"
    assert candidate["classification"] == "stopped_or_early_stop"
    assert "transcript_goal:blocked" in candidate["selection_reasons"]


def test_goal_achieved_instruction_is_not_completion() -> None:
    text = "Do not claim Goal achieved until tests pass."

    assert monitor.transcript_goal_claim(text)["state"] == "none"


def test_goal_blocked_instruction_is_not_status_line() -> None:
    text = "Do not treat the words Goal blocked inside prose as a footer."

    assert monitor.transcript_goal_claim(text)["state"] == "none"


def test_old_attempts_do_not_satisfy_new_blocker(tmp_path: Path) -> None:
    receipt = tmp_path / "review.md"
    receipt.write_text("review", encoding="utf-8")
    text = f"""
    Immutable Goal: BLOCKED:old blocker
    Unblock Attempts: brave-search=USED:{receipt}; browser-oracle=USED:{receipt}

    Status/Phase: new blocker
    Immutable Goal: BLOCKED:new missing credential
    Evidence: none yet
    """

    assert monitor.exhausted_blocker_claim(text, project_root=tmp_path) is False


def test_empty_not_applicable_reason_is_invalid() -> None:
    assert monitor.valid_attempt_value("NOT_APPLICABLE:") is False


def test_webgpt_only_does_not_exhaust_blocker(tmp_path: Path) -> None:
    (tmp_path / "GOAL.md").write_text("Finish feature.", encoding="utf-8")
    pane = {
        "agent": "codex",
        "agent_status": "done",
        "cwd": str(tmp_path),
        "pane_id": "w11:pD",
    }
    text = """
    Immutable Goal: BLOCKED:need human
    Unblock Attempts: brave-search=NOT_APPLICABLE:human; webgpt=NOT_APPLICABLE:human
    """

    candidate = monitor.classify_pane(
        FakeHerdr(text),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"done"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "restart_continue"


def test_goal_file_symlink_escape_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    (outside / "GOAL.md").write_text("outside goal", encoding="utf-8")
    (project / "GOAL.md").symlink_to(outside / "GOAL.md")

    result = monitor.discover_immutable_goal(str(project), boundary=project)

    assert result["found"] is False


def test_probe_text_names_human_brave_and_webgpt_routes() -> None:
    text = monitor.build_prompt({
        "pane_id": "w11:pG",
        "agent": "codex",
        "cwd": "/repo",
        "selection_reasons": ["early_stop"],
        "action": "restart_continue",
        "immutable_goal": {"found": False},
    })

    assert "Immutable Goal:" in text
    assert "RESUMING_NOW" in text
    assert "BLOCKED_NEEDS_HUMAN" in text
    assert "CAN_SELF_UNBLOCK_BRAVE_SEARCH" in text
    assert "CAN_SELF_UNBLOCK_WEBGPT" in text
    assert "Unblock Attempts:" in text
    assert "Are you blocked" in text
    assert "why did you stop early" in text
    assert "have you completed your immutable goal" in text
    assert "$brave-search" in text
    assert "$ask webgpt" in text
    assert "$ask webkimi" in text
    assert "$ticket" in text
    assert "Ticket Check:" in text
    assert "lease/diagnose/fix/prove" in text
    assert "browser-oracle=" in text
    assert "Strict stop rule:" in text
    assert "partial checkpoint" in text
    assert "Immutable Goal: NOT_MET" in text


def test_send_prompt_uses_second_enter_until_submission_is_visible() -> None:
    client = FakeSubmitHerdr()
    original_wait = monitor.wait_for_agent_idle
    monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-herdr")
    finally:
        monitor.wait_for_agent_idle = original_wait

    assert result["api_sent"] is True
    assert result["submit_confirmed"] is True
    assert result["second_enter_sent"] is True
    assert result["terminal_control"]["attempted"] is False
    assert client.enter_count == 2
    assert "Running UserPromptSubmit hook" in result["post_submit_excerpt"]


def test_real_herdr_client_uses_pane_run_submit_without_duplicate_send_text() -> None:
    client = FakeRealSubmitHerdr()
    original_wait = monitor.wait_for_agent_idle
    original_pane_run = monitor.pane_run_submit
    pane_run_calls: list[tuple[str, str]] = []
    monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
    monitor.pane_run_submit = lambda pane_id, prompt, socket_path=None: (
        pane_run_calls.append((pane_id, prompt))
        or {"attempted": True, "ok": True, "transport": "herdr_pane_run", "exit_code": 0}
    )
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-herdr")
    finally:
        monitor.wait_for_agent_idle = original_wait
        monitor.pane_run_submit = original_pane_run

    assert result["api_sent"] is True
    assert result["submit_confirmed"] is True
    assert result["terminal_control"]["transport"] == "herdr_pane_run"
    assert pane_run_calls == [("w11:p8", "RESTART CHECK FROM monitor-herdr")]
    assert client.sent_text is False
    assert client.enter_count == 0


def test_real_herdr_client_retypes_when_pane_run_strands_visible_prompt() -> None:
    client = FakePaneRunStrandsPromptHerdr()
    original_wait = monitor.wait_for_agent_idle
    original_pane_run = monitor.pane_run_submit
    monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
    monitor.pane_run_submit = lambda pane_id, prompt, socket_path=None: {
        "attempted": True,
        "ok": True,
        "transport": "herdr_pane_run",
        "exit_code": 0,
    }
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-herdr")
    finally:
        monitor.wait_for_agent_idle = original_wait
        monitor.pane_run_submit = original_pane_run

    assert result["api_sent"] is True
    assert result["submit_confirmed"] is True
    assert result["pane_run_prompt_visible"] is True
    assert result["socket_text_fallback_sent"] is True
    assert client.sent_text is True
    assert client.enter_count == 1
    assert client.ctrl_j_count == 0


def test_presend_idle_fallback_sends_no_input() -> None:
    client = FakeFallbackIdleHerdr()
    original_wait = monitor.wait_for_agent_idle
    monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-herdr")
    finally:
        monitor.wait_for_agent_idle = original_wait

    assert result["skipped"] is True
    assert result["skip_reason"] == "unsafe_pre_submit_state"
    assert client.enter_count == 0


def test_working_after_first_enter_prevents_second_enter() -> None:
    client = FakeWorkingAfterEnterHerdr()
    original_wait = monitor.wait_for_agent_idle
    monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-herdr")
    finally:
        monitor.wait_for_agent_idle = original_wait

    assert result["submit_confirmed"] is True
    assert result["second_enter_sent"] is False
    assert client.enter_count == 1


def test_prompt_boilerplate_is_not_submission_evidence() -> None:
    text = """
    RESTART CHECK FROM monitor-herdr
    Disposition: <choose exactly one of RESUMING_NOW | BLOCKED_NEEDS_HUMAN | DONE_WITH_RECEIPT>
      gpt-5.5 high · ~/workspace/experiments/agent-skills
    """

    assert monitor.prompt_submitted(text) is False


def test_monitor_prompt_body_does_not_hide_prior_done_receipt() -> None:
    text = """
    Status/Phase: Stop-condition proof completed.
    Immutable Goal: DONE_WITH_RECEIPT
    Next: STOP_ALLOWED because the goal has a fresh receipt.
    Disposition: DONE_WITH_RECEIPT

    ─ Worked for 3m 22s ─────────────────────────────────────────────────────

    › You stopped or went idle while the transcript still shows follow-up work or no real blocker. Resume the task now.
      Ask the human only for a missing decision, credential, authority, acceptance choice, or external state you cannot obtain.
      Status/Phase: <one line>
      Immutable Goal: <known goal, UNKNOWN, or ACHIEVED_WITH_RECEIPT:path>
      Disposition: <choose exactly one of RESUMING_NOW | BLOCKED_NEEDS_HUMAN | DONE_WITH_RECEIPT>

      gpt-5.5 high · ~/workspace/experiments/sparta
    """

    current = monitor.latest_transcript_region(text)

    assert "external state" not in current
    assert monitor.transcript_goal_claim(current)["state"] == "unmet"


def test_wrapped_achieved_receipt_with_done_disposition_does_not_launder_missing_path() -> None:
    text = """
    Status/Phase: Stop-condition proof completed.
    Immutable Goal: ACHIEVED_WITH_RECEIPT:/tmp/codex-ui-verification/sparta/sparta-threat-matrix-goal-stop-
      condition/20260721T1110Z-selected-rd0003.json
    Next: STOP_ALLOWED because the goal has a fresh receipt.
    Disposition: DONE_WITH_RECEIPT
    """

    assert monitor.transcript_goal_claim(text)["state"] == "unmet"


def test_existing_project_receipt_allows_achieved_stop(tmp_path: Path) -> None:
    receipt = tmp_path / ".codex" / "ui-verification" / "latest.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"ok":true}', encoding="utf-8")
    text = f"""
    Status/Phase: Stop-condition proof completed.
    Immutable Goal: ACHIEVED_WITH_RECEIPT:{receipt}
    Evidence: {receipt}; command=verify-ui-cdp
    Next: STOP_ALLOWED because the goal has a fresh receipt.
    Disposition: DONE_WITH_RECEIPT
    """

    assert monitor.transcript_goal_claim(text, project_root=tmp_path)["state"] == "achieved"


def test_achieved_receipt_suppresses_soft_remaining_work_marker(tmp_path: Path) -> None:
    receipt = tmp_path / ".codex" / "ui-verification" / "latest.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"ok":true}', encoding="utf-8")
    (tmp_path / "GOAL.md").write_text("Finish feature.", encoding="utf-8")
    pane = {
        "agent": "codex",
        "agent_status": "done",
        "cwd": str(tmp_path),
        "pane_id": "w11:pS",
    }
    text = f"""
    Status/Phase: Stop-condition proof completed.
    Immutable Goal: ACHIEVED_WITH_RECEIPT:{receipt}
    Evidence: {receipt}; command=verify-ui-cdp
    Next: STOP_ALLOWED because the immutable goal has a fresh receipt.
    What remains outside the immutable goal is a future optional audit.
    Disposition: DONE_WITH_RECEIPT
    """

    candidate = monitor.classify_pane(
        FakeHerdr(text),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"done"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "observe_only"
    assert candidate["classification"] == "goal_stop_allowed"


def test_existing_receipt_without_duplicate_evidence_line_allows_stop(tmp_path: Path) -> None:
    receipt = tmp_path / ".codex" / "ui-verification" / "latest.json"
    receipt.parent.mkdir(parents=True)
    receipt.write_text('{"ok":true}', encoding="utf-8")
    text = f"""
    Status/Phase: Stop-condition proof completed.
    Immutable Goal: ACHIEVED_WITH_RECEIPT:{receipt}
    Next: STOP_ALLOWED because the goal has a fresh receipt.
    Disposition: DONE_WITH_RECEIPT
    """

    assert monitor.transcript_goal_claim(text, project_root=tmp_path)["state"] == "achieved"


def test_out_of_project_receipt_does_not_allow_stop(tmp_path: Path) -> None:
    project = tmp_path / "project"
    outside = tmp_path / "outside"
    project.mkdir()
    outside.mkdir()
    receipt = outside / "receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    text = f"Immutable Goal: ACHIEVED_WITH_RECEIPT:{receipt}\nDisposition: DONE_WITH_RECEIPT\n"

    assert monitor.transcript_goal_claim(text, project_root=project)["state"] == "unmet"


def test_old_submission_marker_cannot_confirm_new_attempt() -> None:
    before = "Running UserPromptSubmit hook\nWorking (1s * esc to interrupt)"
    after = before + "\nRESTART CHECK FROM monitor-herdr"

    assert monitor.prompt_submission_marker(after, baseline=before) == ""


def test_completed_submission_marker_confirms_new_attempt() -> None:
    before = "RESTART CHECK FROM monitor-herdr"
    after = before + "\nUserPromptSubmit hook (completed)"

    assert monitor.prompt_submission_marker(after, baseline=before) == "UserPromptSubmit hook (completed)"


def test_stale_completed_submission_marker_cannot_confirm_new_attempt() -> None:
    before = "UserPromptSubmit hook (completed)\nRESTART CHECK FROM monitor-herdr"
    after = before + "\nRESTART CHECK FROM monitor-herdr"

    assert monitor.prompt_submission_marker(after, baseline=before) == ""


def test_repeated_submission_marker_prevents_second_enter() -> None:
    before = "Running UserPromptSubmit hook\nWorking (1s * esc to interrupt)"
    after = before + "\nRESTART CHECK FROM monitor-herdr"

    assert monitor.prompt_submitted(after, baseline=before) is False


def test_wrapped_prompt_signature_allows_second_enter() -> None:
    baseline = "Codex composer ready"
    wrapped = """
    Unblock Attempts: brave-search=<USED:path | NOT_APPLICABLE:reason>
    Disposition: <choose exactly one of RESUMING_NOW | CAN_SELF_UNBLOCK_WEBGPT>
    If the immutable goal is known and not achieved, keep going.
    """

    assert monitor.prompt_visible_after_send(wrapped, baseline=baseline, prompt="full prompt not visible") is True


def test_stale_wrapped_prompt_signature_does_not_allow_second_enter() -> None:
    baseline = """
    Unblock Attempts: brave-search=<USED:path | NOT_APPLICABLE:reason>
    Disposition: <choose exactly one of RESUMING_NOW | CAN_SELF_UNBLOCK_WEBGPT>
    If the immutable goal is known and not achieved, keep going.
    """

    assert monitor.prompt_visible_after_send(baseline, baseline=baseline, prompt="full prompt not visible") is False


def test_repeated_monitor_prompt_with_longer_composer_allows_second_enter() -> None:
    baseline = """
    Unblock Attempts: brave-search=<USED:path | NOT_APPLICABLE:reason>
    Disposition: <choose exactly one of RESUMING_NOW | CAN_SELF_UNBLOCK_WEBGPT>
    If the immutable goal is known and not achieved, keep going.
    """
    text = baseline + "\n" + ("visible newly pasted prompt body " * 20) + """
    Unblock Attempts: brave-search=<USED:path | NOT_APPLICABLE:reason>
    Disposition: <choose exactly one of RESUMING_NOW | CAN_SELF_UNBLOCK_WEBGPT>
    If the immutable goal is known and not achieved, keep going.
    """

    assert monitor.prompt_visible_after_send(text, baseline=baseline, prompt="full prompt not visible") is True


def test_confirmed_prompt_uses_full_cooldown() -> None:
    prompt_state = {"input_modified": True, "submit_confirmed": True}

    assert monitor.cooldown_for_prompt_state(
        prompt_state,
        cooldown_seconds=3600,
        unconfirmed_cooldown_seconds=600,
    ) == 3600


def test_unconfirmed_prompt_uses_shorter_retry_cooldown() -> None:
    prompt_state = {"input_modified": True, "submit_confirmed": False}

    assert monitor.cooldown_for_prompt_state(
        prompt_state,
        cooldown_seconds=3600,
        unconfirmed_cooldown_seconds=600,
    ) == 600


def test_install_cron_renders_ten_minute_apply_line() -> None:
    exit_code, payload = monitor.install_cron(
        apply=False,
        minute="*/10",
        space="codex",
        apply_prompts=True,
        cwd_prefix="/home/graham/workspace/experiments",
    )

    assert exit_code == 0
    assert payload["status"] == "DRY_RUN"
    assert payload["cron_line"].startswith("*/10 * * * *")
    assert "MONITOR_HERDR_INVOCATION_SOURCE=cron" in payload["cron_line"]
    assert "tick --apply" in payload["cron_line"]
    assert "--space 'codex'" in payload["cron_line"]
    assert "--min-stopped-seconds 600" in payload["cron_line"]
    assert payload["min_stopped_seconds"] == 600
    assert monitor.CRON_MARKER in payload["cron_line"]


def test_send_text_failure_never_sends_enter() -> None:
    client = FakeFailSendTextHerdr()
    original_wait = monitor.wait_for_agent_idle
    monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-herdr")
    finally:
        monitor.wait_for_agent_idle = original_wait

    assert result["skipped"] is True
    assert result["skip_reason"] == "send_text_failed"
    assert result["send_failed"] is True
    assert client.enter_count == 0


def test_send_prompt_uses_second_enter_when_wrapped_prompt_is_visible() -> None:
    client = FakeWrappedPromptAfterEnterHerdr()
    original_wait = monitor.wait_for_agent_idle
    monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-herdr")
    finally:
        monitor.wait_for_agent_idle = original_wait

    assert result["submit_confirmed"] is True
    assert result["second_enter_sent"] is True
    assert client.enter_count == 2


def test_send_prompt_uses_second_enter_when_readback_lags() -> None:
    client = FakeLaggingPromptReadbackHerdr()
    original_wait = monitor.wait_for_agent_idle
    monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-herdr")
    finally:
        monitor.wait_for_agent_idle = original_wait

    assert result["submit_confirmed"] is True
    assert result["second_enter_sent"] is True
    assert result["ctrl_j_sent"] is False
    assert client.enter_count == 2


def test_send_prompt_confirms_working_state_after_second_enter_when_readback_lags() -> None:
    client = FakeDelayedWorkingAfterSecondEnterHerdr()
    original_wait = monitor.wait_for_agent_idle
    monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-herdr")
    finally:
        monitor.wait_for_agent_idle = original_wait

    assert result["submit_confirmed"] is True
    assert result["second_enter_sent"] is True
    assert result["ctrl_j_sent"] is False
    assert client.enter_count == 2


def test_send_prompt_uses_ctrl_j_when_enter_does_not_submit() -> None:
    client = FakeCtrlJSubmitHerdr()
    original_wait = monitor.wait_for_agent_idle
    monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-herdr")
    finally:
        monitor.wait_for_agent_idle = original_wait

    assert result["submit_confirmed"] is True
    assert result["second_enter_sent"] is True
    assert result["ctrl_j_sent"] is True
    assert client.enter_count == 2
    assert client.ctrl_j_count == 1


def test_send_prompt_final_grace_confirms_delayed_working_after_ctrl_j() -> None:
    client = FakeDelayedWorkingAfterCtrlJHerdr()
    original_wait = monitor.wait_for_agent_idle
    monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-herdr")
    finally:
        monitor.wait_for_agent_idle = original_wait

    assert result["submit_confirmed"] is True
    assert result["final_grace_poll_used"] is True
    assert result["ctrl_j_sent"] is True
    assert client.enter_count == 2
    assert client.ctrl_j_count == 1


def test_completion_between_selection_and_send_sends_nothing_with_valid_receipt(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    client = FakeCompletionBeforeSendHerdr(
        f"Immutable Goal: ACHIEVED_WITH_RECEIPT:{receipt}\n"
        f"Evidence: receipt={receipt}; command=verify-ui-cdp\n"
        "Disposition: DONE_WITH_RECEIPT\n"
    )
    original_wait = monitor.wait_for_agent_idle
    monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-herdr", project_root=tmp_path)
    finally:
        monitor.wait_for_agent_idle = original_wait

    assert result["skipped"] is True
    assert result["skip_reason"] == "pre_submit_stop_allowed"
    assert result["input_modified"] is False
    assert client.enter_count == 0


def test_completion_before_send_with_soft_remaining_marker_sends_nothing(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    client = FakeCompletionBeforeSendHerdr(
        f"Immutable Goal: ACHIEVED_WITH_RECEIPT:{receipt}\n"
        f"Evidence: receipt={receipt}; command=verify-ui-cdp\n"
        "Next: STOP_ALLOWED because the immutable goal has a fresh receipt.\n"
        "What remains outside the immutable goal is a future optional audit.\n"
        "Disposition: DONE_WITH_RECEIPT\n"
    )
    original_wait = monitor.wait_for_agent_idle
    monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-herdr", project_root=tmp_path)
    finally:
        monitor.wait_for_agent_idle = original_wait

    assert result["skipped"] is True
    assert result["skip_reason"] == "pre_submit_stop_allowed"
    assert result["input_modified"] is False
    assert client.enter_count == 0


def test_completion_between_selection_and_send_missing_receipt_does_not_suppress_prompt(tmp_path: Path) -> None:
    client = FakeCompletionBeforeSendHerdr()
    original_wait = monitor.wait_for_agent_idle
    monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-herdr", project_root=tmp_path)
    finally:
        monitor.wait_for_agent_idle = original_wait

    assert result.get("skip_reason") != "pre_submit_stop_allowed"
    assert client.enter_count >= 1


def test_send_prompt_never_uses_takeover_controller() -> None:
    client = FakeSubmitHerdr()
    original_wait = monitor.wait_for_agent_idle
    monitor.wait_for_agent_idle = lambda pane_id, socket_path=None: {"ok": True, "exit_code": 0}
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-herdr")
    finally:
        monitor.wait_for_agent_idle = original_wait

    assert result["terminal_control"]["attempted"] is False
    assert result["submit_confirmed"] is True
    assert client.enter_count == 2


def test_invalid_cron_fields_are_rejected() -> None:
    exit_code, payload = monitor.install_cron(
        apply=False,
        minute="*/5",
        space="codex",
        apply_prompts=True,
        cwd_prefix="/home/graham/workspace/experiments",
    )

    assert exit_code == 2
    assert payload["status"] == "BLOCKED"
    assert payload["error"] == "minute_must_be_exactly_every_10"


def test_scheduler_health_reports_not_installed_without_prompting() -> None:
    health = monitor.scheduler_health(
        cron_installed=False,
        latest_receipt={},
        stale_after_seconds=900,
    )

    assert health["status"] == "NOT_INSTALLED"
    assert health["backend"] == "cron"
    assert health["cron_installed"] is False


def test_scheduler_health_reports_stale_latest_receipt() -> None:
    health = monitor.scheduler_health(
        cron_installed=True,
        latest_receipt={"path": "/tmp/receipt.json", "readable": True, "age_seconds": 1200, "ok": True, "status": "OBSERVED"},
        stale_after_seconds=900,
    )

    assert health["status"] == "STALE"
    assert health["latest_receipt_path"] == "/tmp/receipt.json"


def test_latest_receipt_summary_counts_confirmed_prompts(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text(
        """{
          "run_id": "monitor-herdr-test",
          "status": "RESTART_PROMPTS_SUBMITTED",
          "ok": true,
          "invocation_source": "cron",
          "mocked": false,
          "live": true,
          "observed_panes": 2,
          "selected_panes": [{"pane_id": "w1:p1"}],
          "prompts": [{"submit_confirmed": true}]
        }""",
        encoding="utf-8",
    )

    summary = monitor.latest_receipt_summary(receipt)

    assert summary["readable"] is True
    assert summary["status"] == "RESTART_PROMPTS_SUBMITTED"
    assert summary["invocation_source"] == "cron"
    assert summary["selected_panes"] == 1
    assert summary["prompts"] == 1
    assert summary["submit_confirmed"] == [True]


def test_latest_cron_receipt_ignores_newer_manual_receipt(tmp_path: Path) -> None:
    older_cron = tmp_path / "cron" / "receipt.json"
    newer_cli = tmp_path / "cli" / "receipt.json"
    older_cron.parent.mkdir()
    newer_cli.parent.mkdir()
    older_cron.write_text('{"run_id":"cron","invocation_source":"cron","status":"OBSERVED","ok":true}', encoding="utf-8")
    newer_cli.write_text('{"run_id":"cli","invocation_source":"cli","status":"OBSERVED","ok":true}', encoding="utf-8")

    summary = monitor.latest_cron_receipt_summary([newer_cli, older_cron])

    assert summary["run_id"] == "cron"
    assert summary["invocation_source"] == "cron"


def test_corrupt_state_suppresses_input() -> None:
    original = monitor.STATE_PATH
    try:
        monitor.STATE_PATH = Path("/tmp/monitor-confused-corrupt-state-test.json")
        monitor.STATE_PATH.write_text("{not-json", encoding="utf-8")
        state = monitor.load_state()
    finally:
        monitor.STATE_PATH.unlink(missing_ok=True)
        monitor.STATE_PATH = original

    assert state["input_suppressed"] is True
    assert state["state_error"] == "corrupt_json"
