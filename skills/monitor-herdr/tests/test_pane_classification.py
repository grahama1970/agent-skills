"""Tests for stopped-pane classification and stall observation.

Split out of test_monitor_herdr.py alongside scripts/pane_classification.py so
both stay under the 800-line repo limit. `monitor` here is the pane_classification
module, so the existing assertions read unchanged.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pane_classification.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("pane_classification", SCRIPT)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
sys.modules["pane_classification"] = monitor
SPEC.loader.exec_module(monitor)

import change_tracking  # noqa: E402


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
def test_goal_file_without_current_restart_signal_does_not_prompt(tmp_path: Path) -> None:
    (tmp_path / "GOAL.md").write_text("Finish the project goal.", encoding="utf-8")
    pane = {
        "agent": "codex",
        "agent_status": "idle",
        "cwd": str(tmp_path),
        "pane_id": "w11:pX",
    }

    candidate = monitor.classify_pane(
        FakeHerdr("Improve documentation in @filename"),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"idle"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "observe_only"
    assert candidate["classification"] == "immutable_goal_present_no_restart_signal"
    assert "no_current_restart_signal" in candidate["selection_reasons"]
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
def test_monitor_prompt_before_done_receipt_does_not_hide_receipt(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    (tmp_path / "GOAL.md").write_text("Finish feature.", encoding="utf-8")
    pane = {
        "agent": "codex",
        "agent_status": "done",
        "cwd": str(tmp_path),
        "pane_id": "w11:pS",
    }
    text = f"""
    RESTART CHECK FROM monitor-herdr
    Status/Phase: <one line>
    Immutable Goal: <known goal, UNKNOWN, or ACHIEVED_WITH_RECEIPT:path>
    Evidence: <latest concrete command/result/artifact path, or NONE>
    Disposition: <choose exactly one of RESUMING_NOW | BLOCKED_NEEDS_HUMAN | DONE_WITH_RECEIPT>

    Status/Phase: Stop-condition proof completed.
    Immutable Goal: ACHIEVED_WITH_RECEIPT:{receipt}
    Evidence: pytest returned 0; receipt {receipt}
    Next: STOP_ALLOWED because the immutable goal has a fresh receipt.
    Disposition: DONE_WITH_RECEIPT
    """

    current = monitor.latest_transcript_region(text)
    candidate = monitor.classify_pane(
        FakeHerdr(text),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"done"},
        only_obvious_early_stops=False,
    )

    assert "Status/Phase: <one line>" not in current
    assert monitor.transcript_goal_claim(current, project_root=tmp_path)["state"] == "achieved"
    assert candidate is not None
    assert candidate["action"] == "observe_only"
    assert candidate["classification"] == "goal_stop_allowed"
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
def test_unproven_completion_claim_without_restart_signal_does_not_prompt(tmp_path: Path) -> None:
    (tmp_path / "GOAL.md").write_text("Finish feature.", encoding="utf-8")
    pane = {
        "agent": "codex",
        "agent_status": "idle",
        "cwd": str(tmp_path),
        "pane_id": "w11:pZ",
    }
    text = """
    Status/Phase: Stop-condition proof completed.
    Immutable Goal: ACHIEVED_WITH_RECEIPT:missing-receipt.json
    Evidence: receipt exists somewhere, but not in this block.
    Next: STOP_ALLOWED because the immutable goal has receipt-backed proof.
    Disposition: DONE_WITH_RECEIPT
    """

    candidate = monitor.classify_pane(
        FakeHerdr(text),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"idle"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "observe_only"
    assert candidate["classification"] == "completion_claim_unproven_no_restart_signal"
def test_closure_claim_blocked_remains_restart_signal(tmp_path: Path) -> None:
    (tmp_path / "GOAL.md").write_text("Finish feature.", encoding="utf-8")
    pane = {
        "agent": "codex",
        "agent_status": "idle",
        "cwd": str(tmp_path),
        "pane_id": "w11:pZ",
    }
    text = """
    Status/Phase: Stop-condition proof completed.
    Immutable Goal: ACHIEVED_WITH_RECEIPT:missing-receipt.json
    Evidence: none
    Disposition: DONE_WITH_RECEIPT
    Closure claim blocked. This is a high-risk or disputed task.
    """

    candidate = monitor.classify_pane(
        FakeHerdr(text),
        pane,
        cwd_prefix=str(tmp_path.parent),
        include_agents={"codex"},
        stopped_statuses={"idle"},
        only_obvious_early_stops=False,
    )

    assert candidate is not None
    assert candidate["action"] == "restart_continue"
    assert candidate["classification"] == "stopped_or_early_stop"
    assert any("closure claim blocked" in item for item in candidate["early_stop_markers"])
def test_no_change_suppression_downgrades_candidate_to_observe_only() -> None:
    candidate = {
        "action": "restart_continue",
        "classification": "stopped_or_early_stop",
        "selection_reasons": ["stopped_status:done"],
        "change_signature": change_tracking.change_signature({"state_change_seq": 7}, "frozen"),
    }
    prior = {
        "state_change_seq_at_prompt": 7,
        "transcript_digest_at_prompt": change_tracking.transcript_digest("frozen"),
        "no_change_strikes": 0,
    }

    monitor.apply_no_change_suppression(candidate, prior)

    assert candidate["action"] == "observe_only"
    assert candidate["classification"] == "no_change_since_last_prompt"
def test_repeated_no_change_marks_nudge_exhausted() -> None:
    candidate = {
        "action": "restart_continue",
        "classification": "stopped_or_early_stop",
        "selection_reasons": [],
        "change_signature": change_tracking.change_signature({"state_change_seq": 7}, "frozen"),
    }
    prior = {
        "state_change_seq_at_prompt": 7,
        "transcript_digest_at_prompt": change_tracking.transcript_digest("frozen"),
        "no_change_strikes": 2,
    }

    monitor.apply_no_change_suppression(candidate, prior)

    assert candidate["classification"] == "nudge_exhausted_no_change"
    assert candidate["action"] == "observe_only"
