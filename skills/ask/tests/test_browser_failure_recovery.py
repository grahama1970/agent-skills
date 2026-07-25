"""Browser failure recovery packet tests for Tau roundtable workers."""

from __future__ import annotations

import argparse
import importlib.util
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


def test_webclaude_does_not_auto_retry_even_with_readable_bundle_until_transport_supports_attach_file(
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
    assert packet["attach_file_supported"] is False
    assert packet["auto_retry_allowed"] is False
    assert packet["auto_retry_blocked_reason"] == "handler_transport_does_not_support_attach_file"
    assert "does not expose --attach-file" in packet["fallback_instruction"]
