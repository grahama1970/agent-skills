"""Tests for recovery-prompt submission and its confirmation evidence.

Split out of test_monitor_herdr.py alongside scripts/prompt_submission.py so both
stay under the 800-line repo limit. `monitor` here is the prompt_submission
module, so the existing assertions read unchanged.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "prompt_submission.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("prompt_submission", SCRIPT)
assert SPEC and SPEC.loader
monitor = importlib.util.module_from_spec(SPEC)
sys.modules["prompt_submission"] = monitor
SPEC.loader.exec_module(monitor)


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


def test_any_fallback_or_skip_reason_sends_no_input() -> None:
    unsafe_explains = [
        {"state": "idle", "matched_rule": "codex_prompt_idle_ready", "fallback_reason": "any_nonempty_fallback"},
        {"state": "done", "matched_rule": "codex_prompt_done_ready", "skip_reason": "screen too small"},
        {"state": "idle", "matched_rule": "codex_prompt_idle_ready", "screen_detection_skip_reason": "no bottom buffer"},
        {"state": "done", "matched_rule": "codex_prompt_done_ready", "warning": "ambiguous"},
    ]

    for explain in unsafe_explains:
        assert monitor.explain_allows_input(explain) is False
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
