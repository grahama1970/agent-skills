#!/usr/bin/env python3
"""Submit a recovery prompt to a stopped Herdr pane and prove it was submitted.

Inputs: a live Herdr client, a target pane, and the prompt text.
Outputs: a record carrying the transport used and whether submission was
confirmed by reading the pane back.
Failure modes: fails closed -- an unconfirmed submission is reported as
unconfirmed rather than assumed delivered.

Split out of monitor_herdr.py to keep every module under the 800-line repo limit.
A prompt that is pasted into a composer but never executed looks identical to a
delivered one, which is why every path here re-reads the pane instead of trusting
the transport's own exit status.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from loguru import logger

from herdr_socket import HerdrClient, explain_agent, find_patterns, read_pane_text
from herdr_terminal_control import pane_run_submit, wait_for_agent_idle
from monitor_common import EARLY_STOP_PATTERNS
from transcript_classifier import goal_allows_stop, latest_transcript_region


def send_prompt(client: HerdrClient, pane_id: str, prompt: str, *, project_root: str | Path | None = None) -> dict[str, Any]:
    socket_path = getattr(client, "socket_path", None)
    wait_result = wait_for_agent_idle(pane_id, socket_path=socket_path)
    pre_read = read_pane_text(client, pane_id)
    if not pre_read:
        return skipped_send("pre_read_failed", wait_result=wait_result, send_failed=True)
    pre_region = latest_transcript_region(pre_read)
    root_path = Path(project_root).expanduser() if project_root else None
    if goal_allows_stop(
        pre_region,
        goal_found=True,
        has_early_markers=bool(find_patterns(pre_region, EARLY_STOP_PATTERNS)),
        project_root=root_path,
    ):
        return skipped_send("pre_submit_stop_allowed", wait_result=wait_result, pre_read=pre_read)
    explain = explain_agent(client, pane_id)
    if not wait_result.get("ok") and explain.get("state") not in {"idle", "done"}:
        return skipped_send("idle_wait_failed", wait_result=wait_result, pre_submit_state=explain.get("state"), pre_read=pre_read, send_failed=True)
    if not explain_allows_input(explain):
        return skipped_send("unsafe_pre_submit_state", wait_result=wait_result, pre_submit_state=explain.get("state"), pre_read=pre_read)
    records: list[dict[str, Any]] = []
    terminal_result: dict[str, Any] = {"attempted": False, "reason": "not_real_herdr_client"}
    first_read = ""
    submit_confirmed = False
    pane_run_prompt_visible = False
    if isinstance(client, HerdrClient):
        terminal_result = pane_run_submit(pane_id, prompt, socket_path=socket_path)
        if terminal_result.get("ok"):
            for _ in range(5):
                time.sleep(0.4)
                first_read = read_pane_text(client, pane_id)
                submit_confirmed = prompt_submitted(first_read, baseline=pre_read)
                if submit_confirmed:
                    break
                current = explain_agent(client, pane_id)
                if current.get("state") == "working":
                    submit_confirmed = True
                    break
            pane_run_prompt_visible = prompt_visible_after_send(first_read, baseline=pre_read, prompt=prompt)
        else:
            logger.error("Herdr pane.run submit failed for pane {}", pane_id)
    before = len(client.trace)
    needs_socket_text_fallback = not submit_confirmed and (
        not (isinstance(client, HerdrClient) and terminal_result.get("ok"))
        or pane_run_prompt_visible
    )
    socket_text_fallback_sent = False
    if needs_socket_text_fallback:
        try:
            client.call("pane.send_text", {"pane_id": pane_id, "text": prompt})
        except RuntimeError:
            logger.error("Herdr pane.send_text failed for pane {}", pane_id)
            records.extend(client.trace[before:])
            return skipped_send("send_text_failed", wait_result=wait_result, pre_submit_state=explain.get("state"), pre_read=pre_read, terminal_result=terminal_result, records=records, send_failed=True)
        records.extend(client.trace[before:])
        socket_text_fallback_sent = True
        before = len(client.trace)
        try:
            client.call("pane.send_keys", {"pane_id": pane_id, "keys": ["enter"]})
        except RuntimeError:
            logger.error("Herdr pane.send_keys enter failed for pane {}", pane_id)
            records.extend(client.trace[before:])
            return skipped_send("send_enter_failed", wait_result=wait_result, pre_submit_state=explain.get("state"), pre_read=pre_read, terminal_result=terminal_result, records=records, input_modified=True, send_failed=True)
        records.extend(client.trace[before:])
        for _ in range(5):
            time.sleep(0.4)
            first_read = read_pane_text(client, pane_id)
            submit_confirmed = prompt_submitted(first_read, baseline=pre_read)
            if submit_confirmed:
                break
            current = explain_agent(client, pane_id)
            if current.get("state") == "working":
                submit_confirmed = True
                break
    second_enter_sent = False
    second_read = ""
    ctrl_j_sent = False
    ctrl_j_read = ""
    final_read = ""
    final_grace_poll_used = False
    if not submit_confirmed:
        current = explain_agent(client, pane_id)
        if not explain_allows_input(current):
            return skipped_send(
                "post_enter_uncertain",
                wait_result=wait_result,
                pre_submit_state=explain.get("state"),
                pre_read=pre_read,
                terminal_result=terminal_result,
                records=records,
                input_modified=True,
                send_failed=True,
            )
        before = len(client.trace)
        try:
            client.call("pane.send_keys", {"pane_id": pane_id, "keys": ["enter"]})
        except RuntimeError:
            logger.error("Herdr second pane.send_keys enter failed for pane {}", pane_id)
        records.extend(client.trace[before:])
        second_enter_sent = True
        for _ in range(5):
            time.sleep(0.4)
            second_read = read_pane_text(client, pane_id)
            submit_confirmed = prompt_submitted(second_read, baseline=pre_read)
            if submit_confirmed:
                break
            current = explain_agent(client, pane_id)
            if current.get("state") == "working":
                submit_confirmed = True
                break
    if not submit_confirmed:
        current = explain_agent(client, pane_id)
        if explain_allows_input(current):
            before = len(client.trace)
            try:
                client.call("pane.send_keys", {"pane_id": pane_id, "keys": ["ctrl+j"]})
            except RuntimeError:
                logger.error("Herdr pane.send_keys ctrl+j failed for pane {}", pane_id)
            records.extend(client.trace[before:])
            ctrl_j_sent = True
            for _ in range(5):
                time.sleep(0.4)
                ctrl_j_read = read_pane_text(client, pane_id)
                submit_confirmed = prompt_submitted(ctrl_j_read, baseline=pre_read)
                if submit_confirmed:
                    break
                current = explain_agent(client, pane_id)
                if current.get("state") == "working":
                    submit_confirmed = True
                    break
    if not submit_confirmed and (bool(terminal_result.get("ok")) or records):
        final_grace_poll_used = True
        for _ in range(10):
            time.sleep(0.75)
            final_read = read_pane_text(client, pane_id)
            submit_confirmed = prompt_submitted(final_read, baseline=pre_read)
            if submit_confirmed:
                break
            current = explain_agent(client, pane_id)
            if current.get("state") == "working":
                submit_confirmed = True
                break
    api_sent = all("error" not in item.get("response", {}) for item in records)
    transport_sent = bool(terminal_result.get("ok")) or api_sent
    return {
        "send_api": records,
        "terminal_control": terminal_result,
        "idle_wait": wait_result,
        "pre_submit_state": explain.get("state"),
        "api_sent": transport_sent,
        "submit_confirmed": submit_confirmed,
        "input_modified": transport_sent,
        "pane_run_prompt_visible": pane_run_prompt_visible,
        "socket_text_fallback_sent": socket_text_fallback_sent,
        "second_enter_sent": second_enter_sent,
        "ctrl_j_sent": ctrl_j_sent,
        "final_grace_poll_used": final_grace_poll_used,
        "post_submit_excerpt": (final_read or ctrl_j_read or second_read or first_read)[-1200:],
    }
def explain_allows_input(explain: dict[str, Any]) -> bool:
    if explain.get("error") or explain.get("state") not in {"idle", "done"}:
        return False
    if any(explain.get(key) for key in ("fallback_reason", "skip_reason", "screen_detection_skip_reason", "warning", "warnings")):
        return False
    matched_rule = str(explain.get("matched_rule") or explain.get("rule") or "")
    if not matched_rule:
        return False
    lowered = matched_rule.lower()
    if any(token in lowered for token in ["approval", "permission", "question", "blocked", "fallback", "skip"]):
        return False
    return any(token in lowered for token in ["prompt", "idle", "done", "stopped", "ready"])
def prompt_submitted(text: str, *, baseline: str = "") -> bool:
    return prompt_submission_marker(text, baseline=baseline) != ""
def prompt_submission_marker(text: str, *, baseline: str = "") -> str:
    if not text:
        return ""
    for marker in ["Running UserPromptSubmit hook", "UserPromptSubmit hook (completed)", "Working (", "Booting MCP server"]:
        if text.count(marker) > baseline.count(marker):
            return marker
    return ""
def prompt_visible_after_send(text: str, *, baseline: str, prompt: str) -> bool:
    if not text:
        return False
    if prompt in text and prompt not in baseline:
        return True
    signatures = [
        "Unblock Attempts:",
        "Disposition:",
        "CAN_SELF_UNBLOCK_WEBGPT",
        "If the immutable goal is known and not achieved",
    ]
    new_hits = sum(1 for item in signatures if text.count(item) > baseline.count(item))
    if new_hits >= 2:
        return True
    strong_visible_hits = sum(1 for item in signatures if item in text)
    return strong_visible_hits >= 3 and len(text) > len(baseline) + 200
def prompt_send_failed(prompt_record: dict[str, Any]) -> bool:
    if prompt_record.get("sent"):
        return False
    if prompt_record.get("send_failed") or prompt_record.get("input_modified"):
        return True
    return False
def skipped_send(
    reason: str,
    *,
    wait_result: dict[str, Any] | None = None,
    pre_submit_state: str | None = None,
    pre_read: str = "",
    terminal_result: dict[str, Any] | None = None,
    records: list[dict[str, Any]] | None = None,
    input_modified: bool = False,
    send_failed: bool = False,
) -> dict[str, Any]:
    return {
        "send_api": records or [],
        "terminal_control": terminal_result or {"attempted": False, "reason": reason},
        "idle_wait": wait_result or {},
        "pre_submit_state": pre_submit_state,
        "api_sent": False,
        "submit_confirmed": False,
        "input_modified": input_modified,
        "send_failed": send_failed,
        "second_enter_sent": False,
        "post_submit_excerpt": "",
        "pre_submit_excerpt": pre_read[-1200:],
        "skipped": True,
        "skip_reason": reason,
    }
def candidate_without_text(candidate: dict[str, Any]) -> dict[str, Any]:
    clean = dict(candidate)
    if "recent_excerpt" in clean and len(str(clean["recent_excerpt"])) > 400:
        clean["recent_excerpt"] = str(clean["recent_excerpt"])[-400:]
    return clean
