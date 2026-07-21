from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "monitor_confused_agents.py"
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

    assert monitor.classify_pane(
        FakeHerdr("Nothing else to do."),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"done"},
        only_obvious_early_stops=False,
    ) is None


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
    assert "$brave-search" in text
    assert "$webgpt" in text


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
