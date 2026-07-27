"""Browser failure recovery packet tests for Tau roundtable workers."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path


WORKER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "tau_roundtable_worker.py"
SPEC = importlib.util.spec_from_file_location("tau_roundtable_worker", WORKER_PATH)
assert SPEC and SPEC.loader
tau_roundtable_worker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tau_roundtable_worker
SPEC.loader.exec_module(tau_roundtable_worker)


def _args(tmp_path: Path, *, handler: str = "webkimi") -> argparse.Namespace:
    return argparse.Namespace(
        node_id=f"handler-{handler}",
        handler=handler,
        topology="sequential",
        browser_oracle_project=handler,
        surf_run=str(tmp_path / "skills" / "surf" / "run.sh"),
        browser_oracle_run=str(tmp_path / "skills" / "browser-oracle" / "run.sh"),
        timeout=300,
        stable_polls=2,
        no_activate=True,
    )


def _packet(
    tmp_path: Path,
    *,
    handler: str = "webkimi",
    failure: str = "",
    response_text: str = "",
    raw_text: str = "",
    prompt_text: str = "",
    submit_meta: dict | None = None,
    browser_oracle: dict | None = None,
) -> dict:
    artifact_dir = tmp_path / "artifacts"
    artifact_dir.mkdir()
    prompt_path = artifact_dir / "prompt.md"
    prompt_path.write_text(prompt_text, encoding="utf-8")
    return tau_roundtable_worker._browser_failure_recovery_packet(
        _args(tmp_path, handler=handler),
        request_payload={
            "request": prompt_text,
            "repo": "local/agent-skills",
            "target": "browser-recovery",
        },
        failure=failure,
        response_text=response_text,
        raw_text=raw_text,
        prompt_text=prompt_text,
        submit_meta=submit_meta or {},
        commands=[
            {
                "command": ["surf", f"{handler}.submit"],
                "returncode": 1,
                "stdout_excerpt": "",
                "stderr_excerpt": failure,
            }
        ],
        browser_oracle=browser_oracle or {"tab_id": "837359704"},
        response_path=artifact_dir / "response.md",
        raw_path=artifact_dir / "response.raw.md",
        meta_path=artifact_dir / "response.meta.json",
        prompt_path=prompt_path,
    )


def test_repo_access_blocked_fails_closed_without_local_readable_bundle(tmp_path: Path) -> None:
    packet = _packet(
        tmp_path,
        handler="webclaude",
        failure="Claude cannot access this private GitHub repository until GitHub App access is granted.",
        prompt_text="Review https://github.com/private-owner/private-repo for correctness.",
    )

    assert packet["schema"] == "ask.browser_failure_recovery_packet.v1"
    assert packet["failure_code"] == "repo_access_blocked"
    assert packet["local_readable_bundle_paths"] == []
    assert packet["auto_retry_allowed"] is False
    assert packet["auto_retry_blocked_reason"] == "missing_local_readable_bundle"
    assert packet["next_command"][:2][-1] == "tau-dag"
    assert "--execute" in packet["next_command"]
    assert "local readable review bundle" in packet["fallback_instruction"]


def test_prompt_too_large_or_stalled_allows_retry_only_with_attachable_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "review-bundle.md"
    bundle.write_text("# Bundle\n\nReadable local target.", encoding="utf-8")
    packet = _packet(
        tmp_path,
        handler="webkimi",
        failure="surf kimi.submit timed out after 300s; prompt too large or stalled",
        prompt_text=f"Review local bundle {bundle}",
    )

    assert packet["failure_code"] == "prompt_too_large_or_stalled"
    assert packet["local_readable_bundle_paths"] == [str(bundle)]
    assert packet["attach_file_supported"] is True
    assert packet["auto_retry_allowed"] is True
    assert "--attach-file" in packet["next_command"]
    assert packet["next_command"][packet["next_command"].index("--attach-file") + 1] == str(bundle)
    assert "--tab-id" in packet["next_command"]
    assert packet["next_command"][packet["next_command"].index("--tab-id") + 1] == "837359704"
    assert (tmp_path / "artifacts" / "retry-with-local-bundle.md").is_file()


def test_browser_tab_read_timeout_rebinds_instead_of_bundle_retry(tmp_path: Path) -> None:
    packet = _packet(
        tmp_path,
        handler="webclaude",
        failure=(
            "Command '['/home/graham/workspace/experiments/agent-skills/skills/surf/run.sh', "
            "'read', '--tab-id', '837360921']' timed out after 60 seconds"
        ),
        prompt_text="What is 2+2? Answer in one short sentence.",
        submit_meta={
            "status": "failed",
            "requested_tab_id": "837360921",
            "requested_url": "https://claude.ai/chat/9909bd8e-145d-4be5-8a21-2d3b69152e53",
        },
        browser_oracle={
            "project": "webclaude",
            "tab_id": "837360921",
            "conversation_url": "https://claude.ai/chat/9909bd8e-145d-4be5-8a21-2d3b69152e53",
        },
    )

    assert packet["failure_code"] == tau_roundtable_worker.BROWSER_TAB_READ_TIMEOUT
    assert packet["requires_local_readable_bundle"] is False
    assert packet["auto_retry_allowed"] is False
    assert packet["auto_retry_blocked_reason"] == "browser_tab_read_timeout_rebind_required"
    assert packet["next_command"] == [
        str(tmp_path / "skills" / "browser-oracle" / "run.sh"),
        "open-bind",
        "webclaude",
        "--backend",
        "webclaude",
        "--url",
        "https://claude.ai/chat/9909bd8e-145d-4be5-8a21-2d3b69152e53",
        "--manual",
        "--json",
    ]
    assert "prompt-size bundle retry" in packet["fallback_instruction"]
    assert not (tmp_path / "artifacts" / "retry-with-local-bundle.md").exists()


def test_missing_sentinel_classification_uses_submit_metadata(tmp_path: Path) -> None:
    packet = _packet(
        tmp_path,
        handler="webgemini",
        failure="",
        prompt_text="Answer with the sentinel at the end.",
        submit_meta={"raw_contains_sentinel": False, "clean_contains_sentinel": False},
    )

    assert packet["failure_code"] == "missing_sentinel"
    assert packet["auto_retry_allowed"] is False
    assert packet["auto_retry_blocked_reason"] == "missing_local_readable_bundle"
    assert "completion sentinel" in packet["reason"]


def test_stale_webgpt_binding_classification_returns_rebind_command(tmp_path: Path) -> None:
    packet = _packet(
        tmp_path,
        handler="webgpt",
        failure="webgpt.submit tab identity preflight failed for tab 837360696.\nexpected_url_mismatch",
        submit_meta={
            "failure": "tab_identity_preflight_failed",
            "requested_tab_id": "837360696",
            "requested_url": "https://chatgpt.com/c/old",
            "tab_identity_preflight": {
                "error": "expected_url_mismatch",
                "expected_tab_id": "837360696",
                "expected_url": "https://chatgpt.com/c/old",
                "tab": {
                    "id": 837360696,
                    "title": "Sparta Explorer",
                    "url": "https://chatgpt.com/c/new",
                },
            },
        },
    )

    assert packet["failure_code"] == "BLOCKED_WEBGPT_BINDING_STALE"
    assert packet["auto_retry_allowed"] is False
    assert packet["auto_retry_blocked_reason"] == "browser_oracle_binding_stale_rebind_required"
    assert packet["evidence"]["stale_binding"]["live_url"] == "https://chatgpt.com/c/new"
    assert packet["next_command"] == [
        str(tmp_path / "skills" / "browser-oracle" / "run.sh"),
        "bind",
        "webgpt",
        "--backend",
        "webgpt",
        "--tab-id",
        "837360696",
        "--url",
        "https://chatgpt.com/c/new",
        "--manual",
        "--json",
    ]

def test_webgpt_conversation_full_blocks_same_conversation_retry(tmp_path: Path) -> None:
    packet = _packet(
        tmp_path,
        handler="webgpt",
        failure=(
            "BLOCKED_WEBGPT_CONVERSATION_FULL: You have reached the maximum length "
            "for this conversation, but you can keep talking by starting a new chat."
        ),
        prompt_text="Ask webgpt to review this Tau DAG bundle.",
        submit_meta={
            "failure": "BLOCKED_WEBGPT_CONVERSATION_FULL",
            "blocker": "BLOCKED_WEBGPT_CONVERSATION_FULL",
            "recommended_action": "rebind_handler_project_to_fresh_chatgpt_conversation",
        },
    )

    assert packet["failure_code"] == "BLOCKED_WEBGPT_CONVERSATION_FULL"
    assert packet["auto_retry_allowed"] is False
    assert packet["auto_retry_blocked_reason"] == "conversation_full_requires_fresh_chatgpt_conversation"
    assert "--create-tab" in packet["next_command"]
    assert "--project" in packet["next_command"]
    assert "fresh ChatGPT conversation" in packet["fallback_instruction"]


def test_stale_raw_capture_takes_precedence_over_missing_sentinel(tmp_path: Path) -> None:
    packet = _packet(
        tmp_path,
        handler="webgpt",
        failure="missing sentinel",
        raw_text="Found previous response with old sentinel from an earlier assistant turn.",
        prompt_text="Ask webgpt for a current answer.",
        submit_meta={"raw_contains_sentinel": False, "stale_raw_capture": True},
    )

    assert packet["failure_code"] == "stale_raw_capture"
    assert "stale" in packet["fallback_instruction"]


def test_webclaude_auto_retry_uses_readable_bundle_when_transport_supports_attach_file(
    tmp_path: Path,
) -> None:
    bundle = tmp_path / "review-bundle.md"
    bundle.write_text("# Bundle\n\nReadable local target.", encoding="utf-8")
    packet = _packet(
        tmp_path,
        handler="webclaude",
        failure="Claude cannot access this private GitHub repository.",
        prompt_text=f"Review {bundle}",
    )

    assert packet["failure_code"] == "repo_access_blocked"
    assert packet["local_readable_bundle_paths"] == [str(bundle)]
    assert packet["attach_file_supported"] is True
    assert packet["auto_retry_allowed"] is True
    assert packet["auto_retry_blocked_reason"] is None
    assert "--attach-file" in packet["next_command"]
    assert packet["next_command"][packet["next_command"].index("--attach-file") + 1] == str(bundle)
    assert "attached" in packet["fallback_instruction"]


def test_attachment_unavailable_fails_closed_without_unchanged_retry(tmp_path: Path) -> None:
    bundle = tmp_path / "visual-evidence.png"
    bundle.write_bytes(b"\x89PNG\r\n\x1a\n")
    packet = _packet(
        tmp_path,
        handler="webgrok",
        failure="browser_attachment_unavailable: provider response denied attachment access",
        response_text=(
            "TESTER_STATUS: UNKNOWN\n"
            "The attachment is inaccessible and is not mounted in my accessible filesystem."
        ),
        prompt_text=f"Inspect {bundle} and report the visible labels.",
    )

    assert packet["failure_code"] == tau_roundtable_worker.BROWSER_ATTACHMENT_UNAVAILABLE
    assert packet["local_readable_bundle_paths"] == [str(bundle)]
    assert packet["attach_file_supported"] is True
    assert packet["auto_retry_allowed"] is False
    assert packet["auto_retry_blocked_reason"] == "attachment_transport_must_be_repaired"
    assert packet["next_command"] == []
    assert "Do not retry the same attachment submission unchanged" in packet["fallback_instruction"]


def test_surf_browser_lock_timeout_is_transport_blocker_with_owner_metadata(tmp_path: Path) -> None:
    blocker = {
        "schema": "surf.browser_lock_blocker.v1",
        "status": "BLOCKED",
        "blocker": "surf_browser_lock_timeout",
        "owner": {
            "pid": 1838917,
            "created_at": "2026-07-25T14:00:07.031Z",
            "socket": "unix:/tmp/surf.sock",
        },
        "lock_dir": "/tmp/surf-lock-199a427adfd8d6cd",
        "recovery": {
            "do_not_use_no_lock_for_browser_handlers": True,
            "next_command": "wait for the owner process to finish or run this lane through a separate Surf socket/profile",
        },
    }
    packet = _packet(
        tmp_path,
        handler="webgpt",
        failure=(
            "SURF_BROWSER_LOCK_BLOCKED "
            + json.dumps(blocker)
            + "\nError: Timed out waiting for browser lock after 60s."
        ),
        browser_oracle={
            "project": "tau",
            "tab_id": "837359291",
            "conversation_url": "https://chatgpt.com/c/example",
        },
    )

    assert packet["failure_code"] == tau_roundtable_worker.SURF_BROWSER_LOCK_TIMEOUT
    assert packet["requires_local_readable_bundle"] is False
    assert packet["auto_retry_allowed"] is False
    assert packet["auto_retry_blocked_reason"] == "surf_browser_lock_owner_still_running"
    assert packet["evidence"]["surf_lock_blocker"]["owner"]["pid"] == 1838917
    assert "--no-lock" not in packet["next_command"]
    assert packet["next_command"][:2] == [str(tmp_path / "skills" / "surf" / "run.sh"), "webgpt.submit"]
    assert "--expect-url" in packet["next_command"]


def test_surf_browser_lock_timeout_from_meta_is_not_repo_access_blocked(tmp_path: Path) -> None:
    packet = _packet(
        tmp_path,
        handler="webgpt",
        failure="prompt references unreadable local filesystem paths",
        submit_meta={
            "status": "failed",
            "submitted_to_chatgpt": False,
            "proof_status": "submit_not_attempted",
            "requested_tab_id": "837362411",
            "controlled_tab_id": "837362411",
            "tab_identity_preflight": {
                "ok": True,
                "expected_tab_id": "837362411",
                "expected_url": "https://chatgpt.com/",
                "tab": {"id": 837362411, "url": "https://chatgpt.com/"},
            },
            "cdp_probe_stderr": (
                "Timed out waiting for browser lock after 60s "
                "owner_pid=721016 owner_created_at=2026-07-27T14:00:00Z "
                "owner_socket=unix:/tmp/surf.sock lock_dir=/tmp/surf-lock-199a427adfd8d6cd"
            ),
            "stderr_log": "Timed out waiting for browser lock after 60s",
        },
        browser_oracle={
            "project": "tau",
            "tab_id": "837362411",
            "conversation_url": "https://chatgpt.com/",
        },
    )

    assert packet["failure_code"] == tau_roundtable_worker.SURF_BROWSER_LOCK_TIMEOUT
    summary = packet["transport_failure_summary"]
    assert summary["transport_failure_kind"] == "browser_cdp_lock_timeout"
    assert summary["submitted_to_chatgpt"] is False
    assert summary["proof_status"] == "submit_not_attempted"
    assert summary["requested_tab_id"] == "837362411"
    assert summary["controlled_tab_id"] == "837362411"
    assert summary["tab_identity_preflight"]["ok"] is True
    assert "Timed out waiting for browser lock" in summary["cdp_probe_stderr"]
    assert summary["surf_lock_blocker"]["owner"]["pid"] == 721016
    assert summary["surf_lock_blocker"]["owner"]["socket"] == "unix:/tmp/surf.sock"
    assert summary["surf_lock_blocker"]["lock_dir"] == "/tmp/surf-lock-199a427adfd8d6cd"


def test_browser_tab_read_timeout_wins_over_repo_access_markers(tmp_path: Path) -> None:
    packet = _packet(
        tmp_path,
        handler="webclaude",
        failure=(
            "prompt references unreadable local filesystem paths\n"
            "Command '['/home/graham/workspace/experiments/agent-skills/skills/surf/run.sh', "
            "'read', '--tab-id', '837362434']' timed out after 60 seconds"
        ),
        submit_meta={
            "status": "failed",
            "requested_tab_id": "837362434",
            "controlled_tab_id": "837362434",
            "requested_url": "https://claude.ai/chat/example",
            "tab_identity_preflight": {
                "ok": True,
                "expected_tab_id": "837362434",
                "expected_url": "https://claude.ai/chat/example",
                "tab": {"id": 837362434, "url": "https://claude.ai/chat/example"},
            },
            "stderr_log": "surf/run.sh read --tab-id 837362434 timed out after 60 seconds",
        },
        browser_oracle={
            "project": "webclaude",
            "tab_id": "837362434",
            "conversation_url": "https://claude.ai/chat/example",
        },
    )

    assert packet["failure_code"] == tau_roundtable_worker.BROWSER_TAB_READ_TIMEOUT
    summary = packet["transport_failure_summary"]
    assert summary["transport_failure_kind"] == "browser_tab_read_timeout"
    assert summary["requested_tab_id"] == "837362434"
    assert summary["controlled_tab_id"] == "837362434"
    assert summary["tab_identity_preflight"]["ok"] is True
    assert "read --tab-id 837362434 timed out" in summary["stderr_log"]


def test_roundtable_degradation_promotes_transport_failure_summary(tmp_path: Path) -> None:
    recovery_packet_path = tmp_path / "browser-recovery-packet.json"
    recovery_packet_path.write_text(
        json.dumps(
            {
                "auto_retry_allowed": False,
                "auto_retry_blocked_reason": "surf_browser_lock_owner_still_running",
                "next_command": ["skills/surf/run.sh", "webgpt.submit"],
                "transport_failure_summary": {
                    "failure_code": tau_roundtable_worker.SURF_BROWSER_LOCK_TIMEOUT,
                    "transport_failure_kind": "browser_cdp_lock_timeout",
                    "requested_tab_id": "837362411",
                },
                "evidence": {
                    "surf_lock_blocker": {
                        "owner": {"pid": 721016, "socket": "unix:/tmp/surf.sock"},
                        "lock_dir": "/tmp/surf-lock-199a427adfd8d6cd",
                    }
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    analysis = tau_roundtable_worker._roundtable_degradation_analysis(
        status="NEEDS_ATTENTION",
        handler_receipts=[{"node_id": "handler-webgpt"}],
        usable_responses=[],
        failures=[
            {
                "node_id": "handler-webgpt",
                "handler": "webgpt",
                "status": "NEEDS_ATTENTION",
                "failure": "Timed out waiting for browser lock after 60s",
                "failure_code": tau_roundtable_worker.SURF_BROWSER_LOCK_TIMEOUT,
                "recovery_packet_path": str(recovery_packet_path),
            }
        ],
    )

    failed = analysis["failed_seats"][0]
    assert failed["transport_failure_summary"]["transport_failure_kind"] == "browser_cdp_lock_timeout"
    assert failed["transport_failure_summary"]["requested_tab_id"] == "837362411"
    assert failed["evidence"]["surf_lock_blocker"]["owner"]["pid"] == 721016


def test_webgpt_unverified_clean_output_is_quarantined_not_tab_identity_retry(tmp_path: Path) -> None:
    sentinel = "<<<ASK_DONE:20260727T1151Z:WEBGPT>>>"
    packet = _packet(
        tmp_path,
        handler="webgpt",
        failure="Terminated\n",
        response_text="A plausible clean answer without the marker.",
        raw_text=f"A plausible clean answer without the marker.\n{sentinel}\n",
        prompt_text="Answer with the sentinel on the final line.",
        submit_meta={
            "status": "failed",
            "failure": "missing_controlled_tab_id_or_contaminated_clean_output",
            "requested_tab_id": "837362426",
            "controlled_tab_id": None,
            "submitted_to_chatgpt": True,
            "raw_contains_sentinel": True,
            "clean_contains_sentinel": False,
            "response_proof_status": "response_unproven",
            "tab_identity_preflight": {
                "ok": True,
                "tab_id": "837362426",
                "tab": {"id": "837362426", "url": "https://chatgpt.com/c/example"},
            },
        },
        browser_oracle={
            "project": "pdf-oxide-mvp-webgpt-fresh",
            "tab_id": "837362426",
            "conversation_url": "https://chatgpt.com/c/example",
        },
    )

    assert packet["failure_code"] == tau_roundtable_worker.WEBGPT_UNVERIFIED_CLEAN_OUTPUT
    assert packet["requires_local_readable_bundle"] is False
    assert packet["auto_retry_allowed"] is False
    assert packet["auto_retry_blocked_reason"] == "webgpt_controlled_tab_or_clean_output_unproven"
    assert packet["next_command"] == []
    assert "Quarantine the WebGPT response" in packet["fallback_instruction"]

    artifact_dir = tmp_path / "artifacts"
    response_path = artifact_dir / "response.md"
    response_path.write_text("A plausible clean answer without the marker.", encoding="utf-8")
    quarantine = tau_roundtable_worker._quarantine_failed_browser_response(
        response_path=response_path,
        recovery_packet=packet,
        response_text="A plausible clean answer without the marker.",
    )

    assert quarantine["status"] == "QUARANTINED"
    assert quarantine["failure_code"] == tau_roundtable_worker.WEBGPT_UNVERIFIED_CLEAN_OUTPUT
    assert not response_path.exists()
    assert Path(quarantine["quarantine_path"]).name == "response.contaminated.md"


def test_gemini_terminal_sentinel_trailing_content_precedes_prompt_stalled(tmp_path: Path) -> None:
    packet = _packet(
        tmp_path,
        handler="webgemini",
        failure="assistant response contains text after terminal sentinel",
        raw_text="ANSWER\n<<<ASK_DONE:20260727T1151Z:GEMINI>>>\nUnrelated older Gemini text after the marker",
        prompt_text="Answer in one line and end with the sentinel.",
        submit_meta={},
    )

    assert packet["failure_code"] == tau_roundtable_worker.BROWSER_SENTINEL_TRAILING_CONTENT
    assert packet["auto_retry_allowed"] is False
    assert packet["auto_retry_blocked_reason"] == "browser_terminal_sentinel_parser_requires_repair_or_fresh_tab"
    assert packet["next_command"] == []
    assert "Quarantine" in packet["fallback_instruction"]


def test_kimi_composer_draft_is_submit_not_accepted_not_provider_rate_limited(tmp_path: Path) -> None:
    packet = _packet(
        tmp_path,
        handler="webkimi",
        failure="Kimi prompt submission was not accepted: composer still contains draft",
        prompt_text="Answer PING_RESULT: 4",
        submit_meta={
            "status": "failed",
            "requested_tab_id": "837362335",
            "current_url": "https://www.kimi.com/chat/example",
            "kimi_provider_capacity_busy": False,
            "submitted_to_kimi": False,
        },
        browser_oracle={
            "project": "pdf-oxide-mvp-webkimi",
            "tab_id": "837362335",
            "conversation_url": "https://www.kimi.com/chat/example",
        },
    )

    assert packet["failure_code"] == tau_roundtable_worker.BROWSER_SUBMIT_NOT_ACCEPTED
    assert packet["requires_local_readable_bundle"] is False
    assert packet["auto_retry_allowed"] is False
    assert packet["auto_retry_blocked_reason"] == "browser_submit_not_accepted_requires_composer_recovery_or_fresh_tab"
    assert packet["next_command"] == [
        str(tmp_path / "skills" / "browser-oracle" / "run.sh"),
        "open-bind",
        "webkimi",
        "--backend",
        "webkimi",
        "--url",
        "https://www.kimi.com/chat/example",
        "--manual",
        "--json",
    ]
    assert "clean provider tab" in packet["fallback_instruction"]


def test_kimi_system_busy_still_classifies_as_provider_rate_limited(tmp_path: Path) -> None:
    packet = _packet(
        tmp_path,
        handler="webkimi",
        failure="System is currently busy. Please try again later. Composer still contains draft.",
        prompt_text="Answer PING_RESULT: 4",
        submit_meta={
            "status": "failed",
            "kimi_provider_capacity_busy": True,
            "submitted_to_kimi": False,
        },
    )

    assert packet["failure_code"] == tau_roundtable_worker.BROWSER_PROVIDER_RATE_LIMITED
    assert packet["auto_retry_allowed"] is False
    assert packet["auto_retry_blocked_reason"] == "browser_provider_rate_limit_requires_backoff"


def test_timeout_diagnostics_rate_limit_reclassifies_handler_timeout(tmp_path: Path) -> None:
    packet = _packet(
        tmp_path,
        handler="webgrok",
        failure="[tau-worker] command timed out after 300s; killed process group rooted at pid 123",
        prompt_text="Answer PING_RESULT: 4",
        submit_meta={
            "status": "timeout",
            "ask_timeout_diagnostics": {
                "schema": "ask.browser_timeout_diagnostics.v1",
                "status": "CAPTURED",
                "handler": "webgrok",
                "tab_id": "837361333",
                "markers": {
                    "provider_rate_limited": True,
                    "provider_busy": False,
                    "access_blocked": False,
                    "prompt_still_in_composer": False,
                },
                "body_excerpt": "17 hours 40 minutes before limit is gone. Upgrade to SuperGrok.",
            },
        },
    )

    assert packet["failure_code"] == tau_roundtable_worker.BROWSER_PROVIDER_RATE_LIMITED
    assert packet["auto_retry_allowed"] is False
    assert packet["auto_retry_blocked_reason"] == "browser_provider_rate_limit_requires_backoff"
    assert packet["evidence"]["timeout_diagnostics"]["markers"]["provider_rate_limited"] is True


def test_timeout_diagnostics_stuck_composer_reclassifies_submit_not_accepted(tmp_path: Path) -> None:
    packet = _packet(
        tmp_path,
        handler="webkimi",
        failure="[tau-worker] command timed out after 300s; killed process group rooted at pid 456",
        prompt_text="Answer PING_RESULT: 4",
        submit_meta={
            "status": "timeout",
            "ask_timeout_diagnostics": {
                "schema": "ask.browser_timeout_diagnostics.v1",
                "status": "CAPTURED",
                "handler": "webkimi",
                "tab_id": "837362419",
                "markers": {
                    "provider_rate_limited": False,
                    "provider_busy": False,
                    "access_blocked": False,
                    "prompt_still_in_composer": True,
                },
                "composer_excerpt": "Answer PING_RESULT: 4",
            },
        },
    )

    assert packet["failure_code"] == tau_roundtable_worker.BROWSER_SUBMIT_NOT_ACCEPTED
    assert packet["auto_retry_allowed"] is False
    assert packet["auto_retry_blocked_reason"] == "browser_submit_not_accepted_requires_composer_recovery_or_fresh_tab"
    assert packet["evidence"]["timeout_diagnostics"]["markers"]["prompt_still_in_composer"] is True


def test_webgpt_submit_command_expects_home_url_when_tab_id_is_bound(tmp_path: Path) -> None:
    args = _args(tmp_path, handler="webgpt")
    command = tau_roundtable_worker._browser_submit_command(
        args,
        handler="webgpt",
        prompt_path=tmp_path / "prompt.md",
        response_path=tmp_path / "response.md",
        raw_path=tmp_path / "response.raw.md",
        meta_path=tmp_path / "response.meta.json",
        tab_id="837362426",
        url="https://chatgpt.com/",
        attachment_paths=[],
    )

    assert "--tab-id" in command
    assert command[command.index("--tab-id") + 1] == "837362426"
    assert "--expect-url" in command
    assert command[command.index("--expect-url") + 1] == "https://chatgpt.com/"
    assert "--url" not in command


def test_webgpt_submit_command_still_expects_specific_conversation_url(tmp_path: Path) -> None:
    args = _args(tmp_path, handler="webgpt")
    command = tau_roundtable_worker._browser_submit_command(
        args,
        handler="webgpt",
        prompt_path=tmp_path / "prompt.md",
        response_path=tmp_path / "response.md",
        raw_path=tmp_path / "response.raw.md",
        meta_path=tmp_path / "response.meta.json",
        tab_id="837362426",
        url="https://chatgpt.com/c/6a6749ed-7924-83ea-abda-93d6e2570b04",
        attachment_paths=[],
    )

    assert "--expect-url" in command
    assert command[command.index("--expect-url") + 1] == "https://chatgpt.com/c/6a6749ed-7924-83ea-abda-93d6e2570b04"


def test_worker_parses_mixed_stdout_large_tab_list_for_live_url() -> None:
    tabs = [{"id": index, "url": "https://example.com/" + ("x" * 220)} for index in range(40)]
    tabs.append({"id": 837362426, "url": "https://chatgpt.com/c/live", "title": "ChatGPT"})
    text = "Building vendored surf-cli...\n" + json.dumps(tabs)

    parsed = tau_roundtable_worker._parse_json_array_or_tabs(text)

    assert parsed is not None
    assert parsed[-1]["id"] == 837362426


def test_webgpt_home_to_conversation_transition_is_safe_refresh() -> None:
    assert tau_roundtable_worker._is_chatgpt_home_to_chat_transition(
        "https://chatgpt.com/",
        "https://chatgpt.com/c/6a6749ed-7924-83ea-abda-93d6e2570b04",
    )
    assert not tau_roundtable_worker._is_chatgpt_home_to_chat_transition(
        "https://chatgpt.com/c/old",
        "https://chatgpt.com/c/new",
    )


def test_webgpt_home_url_identity_mismatch_does_not_scan_unrelated_tabs() -> None:
    retry = tau_roundtable_worker._should_retry_browser_stale_binding(
        handler="webgpt",
        url="https://chatgpt.com/",
        submit_meta={
            "failure": "tab_identity_preflight_failed",
            "tab_identity_preflight": {"error": "expected_url_mismatch"},
        },
        submit=tau_roundtable_worker.CmdResult(
            command=["surf", "webgpt.submit"],
            returncode=1,
            stdout="",
            stderr="expected_url_mismatch",
            duration=0.1,
        ),
    )

    assert retry is False
