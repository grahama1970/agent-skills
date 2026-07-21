from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "monitor_confused_agents.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("monitor_confused_agents", SCRIPT)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
sys.modules["monitor_confused_agents"] = monitor
SPEC.loader.exec_module(monitor)


class FakeHerdr:
    def __init__(self, text: str) -> None:
        self.text = text

    def call(self, method: str, params: dict) -> dict:
        if method == "pane.read":
            return {"type": "pane_read", "read": {"text": self.text}}
        if method == "agent.explain":
            return {"type": "agent_explain", "explain": {"state": "done"}}
        raise AssertionError(method)


class FakeSubmitHerdr:
    def __init__(self) -> None:
        self.trace = []
        self.enter_count = 0

    def call(self, method: str, params: dict) -> dict:
        response = {"id": method, "result": {"type": "ok"}}
        self.trace.append({"request": {"method": method, "params": params}, "response": response})
        if method == "pane.send_keys" and params.get("keys") == ["enter"]:
            self.enter_count += 1
        if method in {"pane.send_text", "pane.send_keys"}:
            return {"type": "ok"}
        if method == "pane.read":
            if self.enter_count < 2:
                return {"type": "pane_read", "read": {"text": "RESTART CHECK FROM monitor-confused-agents\n  gpt-5.5 high"}}
            return {"type": "pane_read", "read": {"text": "Running UserPromptSubmit hook\nWorking (1s * esc to interrupt)"}}
        if method == "agent.explain":
            return {"type": "agent_explain", "explain": {"state": "idle"}}
        raise AssertionError(method)


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


def test_done_agent_without_goal_can_stop_despite_early_marker(tmp_path: Path) -> None:
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
    assert candidate["action"] == "observe_only"
    assert candidate["classification"] == "no_immutable_goal"


def test_latest_goal_achieved_allows_stop_despite_old_early_marker(tmp_path: Path) -> None:
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
    pane = {
        "agent": "codex",
        "agent_status": "done",
        "cwd": str(tmp_path),
        "pane_id": "w11:pS",
    }
    text = """
    RESTART CHECK FROM monitor-confused-agents
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
    assert candidate["action"] == "needs_human"
    assert candidate["classification"] == "legitimate_human_blocker"


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
    Unblock Attempts: brave-search=NOT_APPLICABLE:credential is private; webgpt=NOT_APPLICABLE:credential is private
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
    assert candidate["classification"] == "goal_stop_allowed"


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
    assert "$brave-search" in text
    assert "$webgpt" in text


def test_send_prompt_uses_second_enter_until_submission_is_visible() -> None:
    client = FakeSubmitHerdr()
    original = monitor.terminal_control_submit
    original_wait = monitor.wait_for_agent_idle
    monitor.terminal_control_submit = lambda pane_id, prompt: {"attempted": True, "ok": False, "exit_code": 2}
    monitor.wait_for_agent_idle = lambda pane_id: {"ok": True, "exit_code": 0}
    try:
        result = monitor.send_prompt(client, "w11:p8", "RESTART CHECK FROM monitor-confused-agents")
    finally:
        monitor.terminal_control_submit = original
        monitor.wait_for_agent_idle = original_wait

    assert result["api_sent"] is True
    assert result["submit_confirmed"] is True
    assert result["second_enter_sent"] is True
    assert result["terminal_control"]["ok"] is False
    assert client.enter_count == 2
    assert "Running UserPromptSubmit hook" in result["post_submit_excerpt"]


def test_prompt_boilerplate_is_not_submission_evidence() -> None:
    text = """
    RESTART CHECK FROM monitor-confused-agents
    Disposition: <choose exactly one of RESUMING_NOW | BLOCKED_NEEDS_HUMAN | DONE_WITH_RECEIPT>
      gpt-5.5 high · ~/workspace/experiments/agent-skills
    """

    assert monitor.prompt_submitted(text) is False


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
    assert "tick --apply" in payload["cron_line"]
    assert "--space 'codex'" in payload["cron_line"]
    assert monitor.CRON_MARKER in payload["cron_line"]
