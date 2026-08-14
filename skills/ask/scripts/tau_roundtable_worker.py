#!/usr/bin/env python3
"""Tau worker for live $ask roundtable browser handler nodes."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import signal
import shlex
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from ask.seam_models import enforce  # noqa: E402


load_dotenv()


HANDLER_BACKENDS = {
    "webgpt": "webgpt",
    "webclaude": "webclaude",
    "webkimi": "webkimi",
    "webgemini": "webgemini",
    "webgrok": "webgrok",
    "webdeepseek": "webdeepseek",
}
HANDLER_SUBMIT_COMMANDS = {
    "webgpt": "webgpt.submit",
    "webclaude": "claude.submit",
    "webkimi": "kimi.submit",
    "webgemini": "gemini.submit",
    "webgrok": "grok.submit",
    "webdeepseek": "deepseek.submit",
}
SURF_PROVIDER_RESULT_PROVIDERS = {
    "webgpt": "webgpt",
    "webclaude": "claude",
    "webkimi": "kimi",
    "webgemini": "gemini",
    "webgrok": "grok",
    "webdeepseek": "unknown",
}
HANDLER_EXTRACT_COMMANDS = {
    "webgpt": "webgpt.extract",
    # gemini.extract routes to scripts/gemini-extract.sh (run.sh route added
    # 2026-08-02 after the packet runnability gate exposed the missing route).
    "webgemini": "gemini.extract",
    "webgrok": "grok.extract",
}
HANDLER_EXTRACT_WAIT_SUPPORTED = {"webgpt", "webgrok"}


@dataclass(frozen=True)
class ProviderPayloadPolicy:
    handler: str
    submit_command: str
    can_attach: bool
    max_attachments: int
    zip_allowed: bool
    preferred_bundle: str
    gotcha: str
    inline_text_attachments: bool = False


@dataclass(frozen=True)
class BrowserFailureCode:
    code: str
    reason: str
    transport_blocker: bool = True
    requires_local_readable_bundle: bool = False
    bundle_retry_candidate: bool = False
    auto_retry_blocked_reason: str = ""
    quarantine_label: str = "unverified"
    transport_failure_kind: str = ""


PROVIDER_PAYLOAD_POLICIES: dict[str, ProviderPayloadPolicy] = {
    "webgpt": ProviderPayloadPolicy(
        handler="webgpt",
        submit_command="webgpt.submit",
        can_attach=True,
        max_attachments=1,
        zip_allowed=True,
        preferred_bundle="inline small Markdown/text bundles; use one attachment or zip only when an archive is required",
        gotcha="attachments can stall at ChatGPT acceptance; inline small readable bundles and reserve upload for large/archive payloads",
        inline_text_attachments=True,
    ),
    "webclaude": ProviderPayloadPolicy(
        handler="webclaude",
        submit_command="claude.submit",
        can_attach=True,
        max_attachments=99,
        zip_allowed=True,
        preferred_bundle="readable files; multiple attachments supported",
        gotcha="staged prompt or prompt echo is not submit proof",
    ),
    "webkimi": ProviderPayloadPolicy(
        handler="webkimi",
        submit_command="kimi.submit",
        can_attach=True,
        max_attachments=1,
        zip_allowed=False,
        preferred_bundle="one plain Markdown or text bundle attached with --attach-file",
        gotcha="do not use zip; send a short prompt plus one readable Markdown/text attachment, not a large inline composer payload",
    ),
    "webgemini": ProviderPayloadPolicy(
        handler="webgemini",
        submit_command="gemini.submit",
        can_attach=True,
        max_attachments=1,
        zip_allowed=False,
        preferred_bundle="one readable Markdown/text bundle inlined when upload input is unavailable",
        gotcha="current Gemini tab UI may not expose a file input; inline Markdown/text bundles instead of assuming upload",
        inline_text_attachments=True,
    ),
    "webgrok": ProviderPayloadPolicy(
        handler="webgrok",
        submit_command="grok.submit",
        can_attach=True,
        max_attachments=1,
        zip_allowed=False,
        preferred_bundle="one readable bundle when upload input and preview exist",
        gotcha="upload support is visible-input dependent",
    ),
    "webdeepseek": ProviderPayloadPolicy(
        handler="webdeepseek",
        submit_command="deepseek.submit",
        can_attach=False,
        max_attachments=0,
        zip_allowed=False,
        preferred_bundle="bounded inline text only",
        gotcha="attachments and zip files are unsupported",
    ),
    "deepseek": ProviderPayloadPolicy(
        handler="deepseek",
        submit_command="deepseek.submit",
        can_attach=False,
        max_attachments=0,
        zip_allowed=False,
        preferred_bundle="bounded inline text only",
        gotcha="attachments and zip files are unsupported",
    ),
}


def _payload_policy(handler: str) -> ProviderPayloadPolicy:
    return PROVIDER_PAYLOAD_POLICIES.get(
        handler,
        ProviderPayloadPolicy(
            handler=handler,
            submit_command=HANDLER_SUBMIT_COMMANDS.get(handler, ""),
            can_attach=False,
            max_attachments=0,
            zip_allowed=False,
            preferred_bundle="inline text only unless a provider policy is added",
            gotcha="unknown provider payload contract",
        ),
    )


ATTACH_FILE_HANDLERS = {
    handler for handler, policy in PROVIDER_PAYLOAD_POLICIES.items() if policy.can_attach
}
RECOVERY_PACKET_SCHEMA = "ask.browser_failure_recovery_packet.v1"
HANDLER_RECOVERY_PACKET_SCHEMA = "ask.handler_failure_recovery_packet.v1"
ASK_TICKET_TARGET = "$ask at agent-skills@main"
WEBGPT_CONVERSATION_FULL_BLOCKER = "BLOCKED_WEBGPT_CONVERSATION_FULL"
WEBGPT_BINDING_STALE_BLOCKER = "BLOCKED_WEBGPT_BINDING_STALE"
BROWSER_TAB_IDENTITY_MISMATCH = "browser_tab_identity_mismatch"
BROWSER_TAB_UNVERIFIED_MULTIPLE = "browser_tab_unverified_with_multiple_provider_tabs"
BROWSER_TAB_NOT_OPEN = "browser_tab_not_open"
BROWSER_TAB_READ_TIMEOUT = "browser_tab_read_timeout"
BROWSER_ACCESS_BLOCKED = "browser_access_blocked"
BROWSER_PROVIDER_RATE_LIMITED = "browser_provider_rate_limited"
BROWSER_PROVIDER_SETUP_FAILED = "browser_provider_setup_failed"
BROWSER_SUBMIT_NOT_ACCEPTED = "browser_submit_not_accepted"
BROWSER_TOOL_UNSUPPORTED = "browser_tool_unsupported"
BROWSER_ATTACHMENT_UI_MISSING = "attachment_ui_missing"
KIMI_CONVERSATION_TOO_LONG_BLOCKER = "BLOCKED_KIMI_CONVERSATION_TOO_LONG"
BROWSER_ATTACHMENT_UNAVAILABLE = "browser_attachment_unavailable"
BROWSER_CLEAN_OUTPUT_CONTAMINATED = "browser_clean_output_contaminated"
BROWSER_SENTINEL_TRAILING_CONTENT = "browser_sentinel_trailing_content"
WEBGPT_UNVERIFIED_CLEAN_OUTPUT = "missing_controlled_tab_id_or_contaminated_clean_output"
BROWSER_HANDLER_TIMEOUT = "browser_handler_timeout"
BROWSER_HANDLER_INTERRUPTED = "browser_handler_interrupted"
BROWSER_EXTENSION_COMMAND_TIMEOUT = "browser_extension_command_timeout"
BROWSER_COMPOSER_INTERACTION_FAILED = "browser_composer_interaction_failed"
ENVIRONMENT_DEPENDENCY_INSTALL_FAILED = "environment_dependency_install_failed"
BROWSER_ATTACHMENT_ARGUMENT_CONTRACT_FAILED = "browser_attachment_argument_contract_failed"
SURF_BROWSER_LOCK_TIMEOUT = "surf_browser_lock_timeout"
SURF_BROWSER_CONNECTION_UNAVAILABLE = "surf_browser_connection_unavailable"
REPO_ACCESS_BLOCKED = "repo_access_blocked"
MISSING_SENTINEL = "missing_sentinel"
PROMPT_TOO_LARGE_OR_STALLED = "prompt_too_large_or_stalled"
STALE_RAW_CAPTURE = "stale_raw_capture"
BROWSER_FAILURE_CODES: dict[str, BrowserFailureCode] = {
    WEBGPT_CONVERSATION_FULL_BLOCKER: BrowserFailureCode(
        WEBGPT_CONVERSATION_FULL_BLOCKER,
        "The controlled ChatGPT conversation is at its maximum length and cannot accept the WebGPT round.",
        auto_retry_blocked_reason="conversation_full_requires_fresh_chatgpt_conversation",
    ),
    WEBGPT_BINDING_STALE_BLOCKER: BrowserFailureCode(
        WEBGPT_BINDING_STALE_BLOCKER,
        "The browser-oracle binding points at a stale ChatGPT URL; the controlled tab is open at a different live URL.",
        auto_retry_blocked_reason="browser_oracle_binding_stale_rebind_required",
        transport_failure_kind="browser_oracle_binding_stale",
    ),
    BROWSER_TAB_IDENTITY_MISMATCH: BrowserFailureCode(
        BROWSER_TAB_IDENTITY_MISMATCH,
        "The browser-oracle binding or requested tab does not match the live browser tab URL.",
        auto_retry_blocked_reason="browser_tab_identity_rebind_required",
    ),
    BROWSER_TAB_UNVERIFIED_MULTIPLE: BrowserFailureCode(
        BROWSER_TAB_UNVERIFIED_MULTIPLE,
        "The explicit tab id could not be verified because many provider tabs are open; "
        "pass --expect-url for the seat's tab or close excess provider tabs (not a rebind).",
        auto_retry_blocked_reason="browser_tab_needs_expect_url_or_fewer_tabs",
    ),
    BROWSER_TAB_NOT_OPEN: BrowserFailureCode(
        BROWSER_TAB_NOT_OPEN,
        "The requested provider tab is no longer open; reprovision the seat tab (not a rebind).",
        auto_retry_blocked_reason="browser_tab_reprovision_required",
    ),
    BROWSER_TAB_READ_TIMEOUT: BrowserFailureCode(
        BROWSER_TAB_READ_TIMEOUT,
        "The bound browser tab was reachable by identity but did not respond to Surf page reads.",
        auto_retry_blocked_reason="browser_tab_read_timeout_rebind_required",
    ),
    BROWSER_ACCESS_BLOCKED: BrowserFailureCode(
        BROWSER_ACCESS_BLOCKED,
        "The browser provider presented an access challenge before the request could be submitted.",
        auto_retry_blocked_reason="browser_access_challenge_requires_human_browser_recovery",
    ),
    BROWSER_PROVIDER_RATE_LIMITED: BrowserFailureCode(
        BROWSER_PROVIDER_RATE_LIMITED,
        "The browser provider accepted routing but reported a provider-side request limit.",
        auto_retry_blocked_reason="browser_provider_rate_limit_requires_backoff",
    ),
    BROWSER_PROVIDER_SETUP_FAILED: BrowserFailureCode(
        BROWSER_PROVIDER_SETUP_FAILED,
        "Surf reached the browser provider, but a provider UI setup step such as model or reasoning selection failed before prompt delivery.",
        auto_retry_blocked_reason="browser_provider_setup_requires_transport_repair_or_fresh_tab",
    ),
    BROWSER_SUBMIT_NOT_ACCEPTED: BrowserFailureCode(
        BROWSER_SUBMIT_NOT_ACCEPTED,
        "Surf reached the browser composer, but the prompt was not accepted as a submitted message.",
        auto_retry_blocked_reason="browser_submit_not_accepted_requires_composer_recovery_or_fresh_tab",
    ),
    BROWSER_TOOL_UNSUPPORTED: BrowserFailureCode(
        BROWSER_TOOL_UNSUPPORTED,
        "The Surf wrapper called a browser tool name that the installed surf-cli runtime does not support.",
        auto_retry_blocked_reason="surf_runtime_command_mismatch_requires_repair",
    ),
    BROWSER_ATTACHMENT_UI_MISSING: BrowserFailureCode(
        BROWSER_ATTACHMENT_UI_MISSING,
        "The provider attachment UI or file input was not available before prompt submission.",
        auto_retry_blocked_reason="attachment_ui_missing_requires_transport_repair",
    ),
    KIMI_CONVERSATION_TOO_LONG_BLOCKER: BrowserFailureCode(
        KIMI_CONVERSATION_TOO_LONG_BLOCKER,
        "Kimi ended the controlled thread for context length and asked for a new session; "
        "surf already rotated the tab into a fresh chat once and Kimi refused again.",
        auto_retry_blocked_reason="conversation_too_long_requires_fresh_kimi_chat",
    ),
    BROWSER_ATTACHMENT_UNAVAILABLE: BrowserFailureCode(
        BROWSER_ATTACHMENT_UNAVAILABLE,
        "The browser provider returned text but explicitly reported that the attached evidence was unavailable.",
        auto_retry_blocked_reason="attachment_transport_must_be_repaired",
    ),
    BROWSER_CLEAN_OUTPUT_CONTAMINATED: BrowserFailureCode(
        BROWSER_CLEAN_OUTPUT_CONTAMINATED,
        "The browser provider returned text, but Surf could not produce a clean response because the terminal sentinel remained in the cleaned output.",
        auto_retry_blocked_reason="browser_clean_output_contains_terminal_sentinel",
        quarantine_label="contaminated",
    ),
    BROWSER_SENTINEL_TRAILING_CONTENT: BrowserFailureCode(
        BROWSER_SENTINEL_TRAILING_CONTENT,
        "The browser provider output included text after the terminal sentinel, so the clean assistant turn is not attributable.",
        auto_retry_blocked_reason="browser_terminal_sentinel_parser_requires_repair_or_fresh_tab",
        quarantine_label="contaminated",
    ),
    WEBGPT_UNVERIFIED_CLEAN_OUTPUT: BrowserFailureCode(
        WEBGPT_UNVERIFIED_CLEAN_OUTPUT,
        "WebGPT returned plausible text, but Surf could not prove the controlled tab or clean output attribution.",
        auto_retry_blocked_reason="webgpt_controlled_tab_or_clean_output_unproven",
        quarantine_label="contaminated",
    ),
    BROWSER_HANDLER_TIMEOUT: BrowserFailureCode(
        BROWSER_HANDLER_TIMEOUT,
        "The browser handler did not produce a usable, receipt-backed response before the declared worker timeout.",
        auto_retry_blocked_reason="browser_handler_timeout_expired",
    ),
    BROWSER_HANDLER_INTERRUPTED: BrowserFailureCode(
        BROWSER_HANDLER_INTERRUPTED,
        "The browser handler was interrupted by its parent or operator before a terminal response receipt was written.",
        auto_retry_blocked_reason="browser_handler_interrupted_no_automatic_recovery",
    ),
    BROWSER_EXTENSION_COMMAND_TIMEOUT: BrowserFailureCode(
        BROWSER_EXTENSION_COMMAND_TIMEOUT,
        "Surf's native host timed out waiting for the Chrome extension to answer a browser command, so the prompt was never delivered; the provider itself did not block the request.",
        auto_retry_blocked_reason="surf_extension_command_timeout_retry_same_binding_after_extension_reload",
    ),
    BROWSER_COMPOSER_INTERACTION_FAILED: BrowserFailureCode(
        BROWSER_COMPOSER_INTERACTION_FAILED,
        "The provider composer refused focus or typing on the controlled tab, so the prompt was never entered. Prompt size is not implicated.",
        auto_retry_blocked_reason="browser_composer_requires_fresh_tab_or_composer_recovery",
    ),
    ENVIRONMENT_DEPENDENCY_INSTALL_FAILED: BrowserFailureCode(
        ENVIRONMENT_DEPENDENCY_INSTALL_FAILED,
        "The lane died installing local Python dependencies, so no browser or provider work was attempted.",
        auto_retry_blocked_reason="local_python_environment_requires_repair",
    ),
    BROWSER_ATTACHMENT_ARGUMENT_CONTRACT_FAILED: BrowserFailureCode(
        BROWSER_ATTACHMENT_ARGUMENT_CONTRACT_FAILED,
        "Surf refused the submit's attachment arguments before opening a browser: this transport sends one attachment per submit.",
        auto_retry_blocked_reason="browser_attachment_contract_requires_single_bundle",
    ),
    SURF_BROWSER_LOCK_TIMEOUT: BrowserFailureCode(
        SURF_BROWSER_LOCK_TIMEOUT,
        "The Surf browser lock is held by another live command; the browser lane was not submitted.",
        auto_retry_blocked_reason="surf_browser_lock_owner_still_running",
        transport_failure_kind="browser_cdp_lock_timeout",
    ),
    SURF_BROWSER_CONNECTION_UNAVAILABLE: BrowserFailureCode(
        SURF_BROWSER_CONNECTION_UNAVAILABLE,
        "The Surf native host or socket disconnected before the browser lane completed.",
        auto_retry_blocked_reason="surf_browser_connection_must_recover",
    ),
    REPO_ACCESS_BLOCKED: BrowserFailureCode(
        REPO_ACCESS_BLOCKED,
        "The browser reviewer appears unable to read the referenced repository or local path.",
        requires_local_readable_bundle=True,
        bundle_retry_candidate=True,
    ),
    MISSING_SENTINEL: BrowserFailureCode(
        MISSING_SENTINEL,
        "The browser transport did not produce the expected completion sentinel.",
        requires_local_readable_bundle=True,
        bundle_retry_candidate=True,
    ),
    PROMPT_TOO_LARGE_OR_STALLED: BrowserFailureCode(
        PROMPT_TOO_LARGE_OR_STALLED,
        "The browser submit reported explicit size or stall wording from the provider.",
        requires_local_readable_bundle=True,
        bundle_retry_candidate=True,
    ),
    STALE_RAW_CAPTURE: BrowserFailureCode(
        STALE_RAW_CAPTURE,
        "The raw browser capture appears to be from the wrong or stale assistant turn.",
        auto_retry_blocked_reason="browser_raw_capture_stale_rebind_required",
        quarantine_label="contaminated",
    ),
}
BROWSER_TRANSPORT_BLOCKERS = {
    code for code, failure_code in BROWSER_FAILURE_CODES.items() if failure_code.transport_blocker
}


def _ask_ticket_instruction(*, failure_code: str, packet_kind: str) -> str:
    return (
        f"If failure_code={failure_code} in this {packet_kind} is misclassified, missing an actionable next_command, "
        f"or still blocks the project after following the recovery instruction, file a $ticket to "
        f"{ASK_TICKET_TARGET}. Include the Ask run directory, dag.json, node-receipt.json, "
        f"{packet_kind}.json, response.meta.json, response.raw.md, and the exact command stderr."
    )


def _browser_failure_code(code: str) -> BrowserFailureCode:
    return BROWSER_FAILURE_CODES.get(
        code,
        BrowserFailureCode(
            code=code,
            reason="The browser handler failed with an unregistered failure code.",
            transport_blocker=True,
            auto_retry_blocked_reason="unregistered_browser_failure_code_requires_ask_ticket",
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--handler", required=True)
    parser.add_argument("--topology", required=True)
    parser.add_argument("--workflow-mode", default="roundtable", choices=["roundtable", "compete"])
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--browser-oracle-project", default="")
    parser.add_argument("--provider-hint", default="")
    parser.add_argument("--next-agent", default="human")
    parser.add_argument("--artifact-dir", required=True)
    parser.add_argument("--surf-run", required=True)
    parser.add_argument("--browser-oracle-run", required=True)
    parser.add_argument("--scillm-base-url", default="http://127.0.0.1:4001")
    parser.add_argument("--scillm-api-key", default="")
    parser.add_argument("--prior-node", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--command-timeout-budget", type=int, default=0)
    parser.add_argument("--browser-lock-timeout", type=int, default=0)
    parser.add_argument("--stable-polls", type=int, default=2)
    parser.add_argument("--no-activate", action="store_true")
    parser.add_argument("--evidence", action="append", default=[])
    # Caller-supplied local evidence forwarded to the provider as --attach-file
    # (agent-skills#1062).
    parser.add_argument("--attach-file", action="append", default=[], dest="attach_files")
    parser.add_argument("--codex-workspace", default="")
    parser.add_argument("--browser-model-preference", default="")
    parser.add_argument("--subagent-runner", default="")
    parser.add_argument("--subagent-model", default="")
    parser.add_argument("--subagent-reasoning-effort", default="")
    parser.add_argument("--subagent-requested-model", default="")
    args = parser.parse_args()
    _configure_browser_runtime_environment(args)

    start = _read_stdin_handoff()
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if args.node_id == "join":
        result = _run_join(args, start, artifact_dir)
    else:
        result = _run_handler(args, start, artifact_dir)
    print(json.dumps(result["handoff"], sort_keys=True))
    return int(result["exit_code"])


def _configure_browser_runtime_environment(args: argparse.Namespace) -> None:
    if args.handler in HANDLER_SUBMIT_COMMANDS:
        browser_lock_timeout = int(getattr(args, "browser_lock_timeout", 0) or 0)
        if browser_lock_timeout > 0:
            os.environ["SURF_LOCK_TIMEOUT_MS"] = str(browser_lock_timeout * 1000)
        else:
            os.environ.setdefault("SURF_LOCK_TIMEOUT_MS", "1800000")
    if args.handler == "webgpt":
        os.environ.setdefault("SURF_WEBGPT_RATE_LIMIT_WAIT_SECONDS", "300")
        os.environ.setdefault("SURF_WEBGPT_RATE_LIMIT_RETRY_ATTEMPTS", "1")


def _run_handler(args: argparse.Namespace, start: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    # Recovery gets a slice of wall clock that is genuinely its own. Anchoring
    # it at lane start meant the submit consumed the entire budget and the
    # ladder was skipped before trying a single rung (observed 2026-08-03:
    # webkimi, recovery_budget_exhausted with zero attempts made).
    lane_recovery_budget = max(240, int(getattr(args, "timeout", 900) or 900) // 2)
    request_payload = _read_json(Path(args.request_file))
    request_text = str(request_payload.get("request") or "")
    handler = args.handler
    response_path = artifact_dir / "response.md"
    raw_path = artifact_dir / "response.raw.md"
    meta_path = artifact_dir / "response.meta.json"
    prompt_path = artifact_dir / "prompt.md"
    receipt_path = artifact_dir / "node-receipt.json"
    recovery_packet_path = artifact_dir / (
        "browser-recovery-packet.json" if handler in HANDLER_SUBMIT_COMMANDS else "handler-recovery-packet.json"
    )
    commands: list[dict[str, Any]] = []
    prior_receipts = _load_prior_receipts(artifact_dir.parent, args.prior_node)
    prompt_path.write_text(
        _handler_prompt(
            request_text,
            handler,
            prior_receipts=prior_receipts,
            requires_verdict=_requires_verdict(request_text, prior_receipts),
            workflow_mode=getattr(args, "workflow_mode", "roundtable"),
            model_preference=getattr(args, "browser_model_preference", ""),
            # API (scillm) handlers have no attachment channel and no path
            # preflight: give them the full prior response including the diff.
            # The judge must see full competitor bodies regardless.
            inline_full=(handler not in HANDLER_SUBMIT_COMMANDS and handler != "codex")
            or args.node_id in ("judge", "report"),
            node_id=str(args.node_id),
            criteria=[str(c) for c in (request_payload.get("criteria") or [])],
        ),
        encoding="utf-8",
    )

    status = "ERROR"
    ok = False
    provider_live = False
    response_text = ""
    resolve_payload: dict[str, Any] = {}
    submit_meta: dict[str, Any] = {}
    transport_summary: dict[str, Any] = {}
    transport_summary_path: Path | None = None
    surf_provider_result: dict[str, Any] = {}
    surf_provider_result_path: Path | None = None
    binding_refresh: dict[str, Any] | None = None
    browser_transport_queue_path = artifact_dir / "browser-transport-queue.json"
    submit_prompt_path = prompt_path
    browser_attachment_paths: list[str] = []
    browser_local_path_preflight: dict[str, Any] | None = None
    failure = ""
    recovery_packet: dict[str, Any] | None = None
    response_quarantine: dict[str, Any] | None = None
    started = _now()
    try:
        prior_failures = [
            f"{item.get('node_id')}: {item.get('failure') or item.get('status')}"
            for item in prior_receipts
            if item.get("ok") is not True
        ]
        if prior_failures:
            raise RuntimeError("prior_handler_receipts_not_ready: " + "; ".join(prior_failures))
        if _is_subagent_handler_args(args):
            response_text, submit_meta, subagent_commands = _run_subagent_handler(
                args,
                prompt_path=prompt_path,
                response_path=response_path,
                raw_path=raw_path,
                meta_path=meta_path,
                artifact_dir=artifact_dir,
            )
            commands.extend(subagent_commands)
        elif handler == "codex":
            response_text, submit_meta, codex_commands = _run_codex_handler(
                args,
                prompt_path=prompt_path,
                response_path=response_path,
                raw_path=raw_path,
                meta_path=meta_path,
            )
            commands.extend(codex_commands)
        elif handler in HANDLER_SUBMIT_COMMANDS:
            project = args.browser_oracle_project or handler
            resolve = _run_cmd(
                [
                    str(args.browser_oracle_run),
                    "resolve",
                    "--backend",
                    HANDLER_BACKENDS[handler],
                    "--project",
                    project,
                    "--json",
                ],
                cwd=Path(args.browser_oracle_run).parent,
                timeout=60,
            )
            commands.append(resolve.summary())
            if resolve.returncode != 0:
                raise RuntimeError(resolve.stderr or resolve.stdout)
            resolve_payload = _parse_json_object(resolve.stdout)
            tab_id = str(resolve_payload.get("tab_id") or "")
            url = str(resolve_payload.get("conversation_url") or "")
            if handler == "webgpt" and tab_id:
                # webgpt --expect-url must equal the tab's LIVE url: the guard
                # checks the live tab, and a fresh chatgpt tab navigates to
                # /c/<id> after any activity, so a stored root url goes stale
                # and mismatches on later rounds (#1252, found via live eval).
                # Always reconcile against the current tab url for webgpt.
                live_url = _current_tab_url(args, tab_id)
                if live_url:
                    url = live_url
            if not url and tab_id:
                # Ask provisions webgpt seats at a bare provider root (no
                # conversation id), so conversation_url is empty and no
                # --expect-url gets passed. With many provider tabs open the
                # identity guard then fails unverified_tab_id_with_multiple_
                # chatgpt_tabs and the seat never submits (#1252). Resolve the
                # tab's live URL so --expect-url is always asserted.
                url = _current_tab_url(args, tab_id) or url
            if not tab_id:
                raise RuntimeError(f"browser-oracle project {project!r} resolved without tab_id")
            binding_refresh = _refresh_browser_binding_before_submit(
                args,
                project=project,
                tab_id=tab_id,
                previous_url=url,
                commands=commands,
            )
            if binding_refresh.get("status") == "updated" and binding_refresh.get("current_url"):
                url = str(binding_refresh["current_url"])

            attachment_paths: list[str] = []
            attachment_paths.extend(
                resolve_requested_attachments(
                    [str(item) for item in (getattr(args, "attach_files", None) or [])],
                    handler=handler,
                )
            )
            for prior in prior_receipts:
                prior_response = str(prior.get("response_path") or "")
                if prior_response and Path(prior_response).is_file():
                    attachment_paths.append(prior_response)
            (
                submit_prompt_path,
                browser_attachment_paths,
                browser_local_path_preflight,
            ) = _prepare_browser_submit_payload(
                handler=handler,
                prompt_path=prompt_path,
                request_payload=request_payload,
                attachment_paths=attachment_paths,
            )
            submit_cmd = _browser_submit_command(
                args,
                handler=handler,
                prompt_path=submit_prompt_path,
                response_path=response_path,
                raw_path=raw_path,
                meta_path=meta_path,
                tab_id=tab_id,
                url=url,
                attachment_paths=browser_attachment_paths,
            )
            submit = _run_browser_transport_cmd(
                submit_cmd,
                cwd=Path(args.surf_run).parent,
                timeout=_browser_submit_timeout(
                    handler,
                    args.timeout,
                    command_timeout_budget=int(getattr(args, "command_timeout_budget", 0) or 0),
                ),
                handler=handler,
                artifact_dir=artifact_dir,
                queue_path=browser_transport_queue_path,
                browser_lock_timeout=int(getattr(args, "browser_lock_timeout", 0) or 0),
            )
            commands.append(submit.summary())
            if meta_path.is_file():
                submit_meta = _read_json(meta_path)
            if submit.returncode == 124 and handler in HANDLER_SUBMIT_COMMANDS:
                timeout_diagnostics = _browser_timeout_diagnostics(
                    surf_run=Path(args.surf_run),
                    handler=handler,
                    tab_id=tab_id,
                    url=url,
                    prompt_path=submit_prompt_path,
                    artifact_dir=artifact_dir,
                )
                if timeout_diagnostics:
                    submit_meta = {
                        **submit_meta,
                        "status": submit_meta.get("status") or "timeout",
                        "ask_timeout_diagnostics": timeout_diagnostics,
                    }
                    meta_path.write_text(
                        json.dumps(submit_meta, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8",
                    )
            degraded_response_recovered = _normalize_degraded_webgpt_response(
                handler=handler,
                meta_path=meta_path,
                response_path=response_path,
                raw_path=raw_path,
            )
            if degraded_response_recovered:
                submit_meta = _read_json(meta_path)
            transport_summary_path, transport_summary = _load_webgpt_transport_summary(artifact_dir)
            if submit.returncode != 0 and _should_retry_browser_stale_binding(
                handler=handler,
                url=url,
                submit_meta=submit_meta,
                submit=submit,
            ):
                retry = _retry_browser_stale_binding(
                    args,
                    handler=handler,
                    project=project,
                    url=url,
                    current_tab_id=tab_id,
                    prompt_path=prompt_path,
                    response_path=response_path,
                    raw_path=raw_path,
                    meta_path=meta_path,
                    attachment_paths=browser_attachment_paths,
                    commands=commands,
                )
                if retry:
                    submit = retry["submit"]
                    submit_meta = retry["submit_meta"]
                    tab_id = retry["tab_id"]
                    binding_refresh = retry["binding_refresh"]
                    if isinstance(resolve_payload, dict):
                        resolve_payload["tab_id"] = tab_id
                        if binding_refresh and binding_refresh.get("current_url"):
                            resolve_payload["conversation_url"] = binding_refresh["current_url"]
                    degraded_response_recovered = _normalize_degraded_webgpt_response(
                        handler=handler,
                        meta_path=meta_path,
                        response_path=response_path,
                        raw_path=raw_path,
                    )
                    if degraded_response_recovered:
                        submit_meta = _read_json(meta_path)
                    transport_summary_path, transport_summary = _load_webgpt_transport_summary(artifact_dir)
            surf_provider_result_path, surf_provider_result = _write_surf_provider_result(
                args,
                handler=handler,
                meta_path=meta_path,
                submit=submit,
                artifact_dir=artifact_dir,
                commands=commands,
            )
            if submit.returncode != 0 and not degraded_response_recovered:
                raise RuntimeError(submit.stderr or submit.stdout or f"{HANDLER_SUBMIT_COMMANDS[handler]} failed")
            response_text = response_path.read_text(encoding="utf-8")
            post_submit_refresh = _refresh_browser_binding_after_proven_submit(
                args,
                project=project,
                tab_id=tab_id,
                previous_url=url,
                submit_meta=submit_meta,
                commands=commands,
            )
            if post_submit_refresh.get("status") == "updated" or (
                not binding_refresh or binding_refresh.get("status") != "updated"
            ):
                binding_refresh = post_submit_refresh
        else:
            response_text, submit_meta = _run_scillm_handler(
                args,
                handler=handler,
                prompt_path=prompt_path,
                response_path=response_path,
                raw_path=raw_path,
                meta_path=meta_path,
            )
            commands.append(
                {
                    "command": ["scillm.chat", submit_meta.get("model") or handler],
                    "returncode": 0,
                    "duration_seconds": submit_meta.get("duration_seconds"),
                    "stdout_excerpt": response_text[:1000],
                    "stderr_excerpt": "",
                }
            )
        ok = bool(response_text.strip())
        if ok and browser_attachment_paths and _response_denies_attachment_access(response_text):
            failure = (
                f"{BROWSER_ATTACHMENT_UNAVAILABLE}: provider response explicitly denied access "
                "to the attached evidence"
            )
            ok = False
        if ok and _requires_verdict(request_text, prior_receipts):
            ok = _has_verdict(response_text)
            if not ok:
                failure = "review_verdict_missing: expected PASS, FAIL, or NEEDS_ATTENTION"
        status = "PASS" if ok else "ERROR"
        provider_live = ok
    except Exception as exc:
        failure = str(exc)
        status = "ERROR"
        ok = False
        provider_live = False
        if response_path.is_file():
            response_text = response_path.read_text(encoding="utf-8")
    if handler in HANDLER_SUBMIT_COMMANDS and not ok:
        raw_text = raw_path.read_text(encoding="utf-8", errors="replace") if raw_path.is_file() else ""
        prompt_text = prompt_path.read_text(encoding="utf-8", errors="replace") if prompt_path.is_file() else ""
        recovery_packet = _browser_failure_recovery_packet(
            args,
            request_payload=request_payload,
            failure=failure,
            response_text=response_text,
            raw_text=raw_text,
            prompt_text=prompt_text,
            submit_meta=submit_meta,
            commands=commands,
            browser_oracle=resolve_payload,
            response_path=response_path,
            raw_path=raw_path,
            meta_path=meta_path,
            prompt_path=prompt_path,
        )
        recovery_packet_path.write_text(
            json.dumps(recovery_packet, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        # Look before theorising. The fixed diagnostic series runs on every
        # browser lane failure -- including the ones the ladder will refuse to
        # retry -- so the failure always carries live tab state rather than an
        # agent's guess about it.
        lane_diagnostics = _lane_diagnostics(
            args,
            failure_code=str(recovery_packet.get("failure_code") or ""),
            submit_meta=submit_meta,
            browser_oracle=resolve_payload,
            sentinel=str(submit_meta.get("sentinel") or ""),
        )
        lane_diagnostics = enforce("ask.lane_diagnostics.v1", lane_diagnostics)
        (artifact_dir / "lane-diagnostics.json").write_text(
            json.dumps(lane_diagnostics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        recovery_packet["lane_diagnostics"] = lane_diagnostics
        # Assume the first attempt fails: something upstream has probably
        # changed. Work the lane's own recovery ladder here, in-run, instead
        # of emitting advice nobody executes (observed 2026-08-03: nine failed
        # lanes, five with a concrete next_command, zero recovery artifacts).
        lane_recovery = _attempt_lane_recovery(
            args,
            recovery_packet=recovery_packet,
            browser_oracle=resolve_payload,
            submit_meta=submit_meta,
            response_path=response_path,
            raw_path=raw_path,
            meta_path=meta_path,
            artifact_dir=artifact_dir,
            deadline=time.time() + lane_recovery_budget,
        )
        (artifact_dir / "lane-recovery.json").write_text(
            json.dumps(lane_recovery, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        recovery_packet["lane_recovery"] = lane_recovery
        recovery_packet_path.write_text(
            json.dumps(recovery_packet, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if lane_recovery.get("recovered"):
            recovered_path = Path(str(lane_recovery.get("response_path") or ""))
            if recovered_path.is_file():
                response_text = recovered_path.read_text(encoding="utf-8", errors="replace")
                response_path.write_text(response_text, encoding="utf-8")
                ok = True
                status = "PASS"
                provider_live = True
                failure = ""
        if not ok and recovery_packet.get("failure_code") in BROWSER_TRANSPORT_BLOCKERS:
            status = "BLOCKED"
        if not ok:
            # Quarantine only unrecovered output. A lane that healed itself has
            # sentinel-verified provider text at response_path; moving it aside
            # would hand the join an empty seat that actually succeeded.
            response_quarantine = _quarantine_failed_browser_response(
                response_path=response_path,
                recovery_packet=recovery_packet,
                response_text=response_text,
            )
            if response_quarantine.get("quarantine_path"):
                response_path = Path(str(response_quarantine["quarantine_path"]))
    crosstalk = crosstalk_tab_mismatch(str(resolve_payload.get("tab_id") or ""), submit_meta)
    if crosstalk:
        # Never let a cross-tab capture be read as this seat's answer.
        ok = False
        status = "BLOCKED"
        failure = failure or (
            f"browser_tab_crosstalk: bound tab {crosstalk['bound_tab_id']} but captured from "
            f"{crosstalk['controlled_tab_id']}"
        )
        if response_path.is_file():
            crosstalk_path = _unique_quarantine_path(response_path.with_name("response.crosstalk.md"))
            response_path.rename(crosstalk_path)
            crosstalk["quarantine_path"] = str(crosstalk_path)
            response_path = crosstalk_path
        response_quarantine = {**(response_quarantine or {}), "crosstalk": crosstalk}

    if not ok and recovery_packet is None:
        recovery_packet = _handler_failure_recovery_packet(
            args,
            request_payload=request_payload,
            failure=failure,
            response_text=response_text,
            submit_meta=submit_meta,
            commands=commands,
            response_path=response_path,
            raw_path=raw_path,
            meta_path=meta_path,
            prompt_path=prompt_path,
        )
        # A browser lane can reach this fallback without passing the main
        # browser branch (observed 2026-08-03: the webgemini timeout produced a
        # packet here and therefore no recovery at all). Recovery attaches
        # wherever a browser lane concludes unhealthy, not in one branch only.
        if handler in HANDLER_SUBMIT_COMMANDS:
            lane_recovery = _attempt_lane_recovery(
                args,
                recovery_packet=recovery_packet,
                browser_oracle=resolve_payload if isinstance(resolve_payload, dict) else {},
                submit_meta=submit_meta if isinstance(submit_meta, dict) else {},
                response_path=response_path,
                raw_path=raw_path,
                meta_path=meta_path,
                artifact_dir=artifact_dir,
                deadline=time.time() + lane_recovery_budget,
            )
            (artifact_dir / "lane-recovery.json").write_text(
                json.dumps(lane_recovery, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            recovery_packet["lane_recovery"] = lane_recovery
            if lane_recovery.get("recovered"):
                recovered_path = Path(str(lane_recovery.get("response_path") or ""))
                if recovered_path.is_file():
                    response_text = recovered_path.read_text(encoding="utf-8", errors="replace")
                    response_path.write_text(response_text, encoding="utf-8")
                    ok = True
                    provider_live = True
                    failure = ""
        recovery_packet_path.write_text(
            json.dumps(recovery_packet, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        status = "PASS" if ok else "NEEDS_ATTENTION"

    lane_exit_ok = ok
    workflow_mode = getattr(args, "workflow_mode", "roundtable")
    if workflow_mode in {"roundtable", "compete"} and not ok:
        # Seats can be unavailable, rate-limited, auth-blocked, or provider-
        # blocked without invalidating the artifact set. Preserve the lane as a
        # terminal outcome and let the join node index every peer receipt.
        status = "NEEDS_ATTENTION"
        lane_exit_ok = True
        if not failure:
            failure = f"{workflow_mode}_lane_needs_attention"

    verdict = _extract_verdict(response_text)
    if verdict is None and recovery_packet is not None:
        verdict = str(recovery_packet.get("failure_code") or "") or None
    receipt = {
        "schema": "ask.tau_dag_handler_receipt.v1",
        "created_at": _now(),
        "started_at": started,
        "node_id": args.node_id,
        "handler": handler,
        "topology": args.topology,
        "status": status,
        "ok": ok,
        "mocked": False,
        "live": bool(commands),
        "provider_live": provider_live,
        "response_path": str(response_path),
        "response_quarantine": response_quarantine,
        "raw_response_path": str(raw_path),
        "meta_path": str(meta_path),
        "transport_summary_path": str(transport_summary_path) if transport_summary_path else None,
        "browser_transport_queue_path": str(browser_transport_queue_path) if browser_transport_queue_path.is_file() else None,
        "webgpt_transport_summary": transport_summary or None,
        "prompt_path": str(prompt_path),
        "browser_prompt_path": str(submit_prompt_path) if submit_prompt_path != prompt_path else None,
        "browser_attachment_paths": browser_attachment_paths,
        "requested_attachment_paths": [str(item) for item in (getattr(args, "attach_files", None) or [])],
        "browser_local_path_preflight": browser_local_path_preflight,
        "recovery_packet_path": str(recovery_packet_path) if recovery_packet else None,
        "response_chars": len(response_text),
        "browser_oracle": resolve_payload,
        "browser_oracle_binding_refresh": binding_refresh,
        "browser_model_preference": str(getattr(args, "browser_model_preference", "") or "") or None,
        "submit_meta": submit_meta,
        "surf_provider_result_path": str(surf_provider_result_path) if surf_provider_result_path else None,
        "surf_provider_result": surf_provider_result or None,
        "commands": commands,
        "prior_nodes": list(args.prior_node),
        "prior_handler_receipts": prior_receipts,
        "requires_verdict": _requires_verdict(request_text, prior_receipts),
        "verdict": verdict,
        "failure": failure or None,
        "failure_code": recovery_packet.get("failure_code") if recovery_packet else None,
        "browser_transport_failure_summary": recovery_packet.get("transport_failure_summary") if recovery_packet else None,
        "competition_lane_exit_ok": lane_exit_ok,
        "recovery_packet": recovery_packet,
        "provider_receipt": {
            "schema": "ask.tau_dag_provider_route_receipt.v1",
            "status": status,
            "ok": ok,
            "mocked": False,
            "live": bool(commands),
            "provider_live": provider_live,
            "route": "tau_roundtable_handler_adapter",
            "execution_owner": "$tau",
            "provider_transport": _provider_transport_for_args(args, handler),
            "handler": handler,
            "provider_hint": str(getattr(args, "provider_hint", "") or "") or None,
            "transport": _transport_for_args(args, handler),
            "model": submit_meta.get("model") if handler not in HANDLER_SUBMIT_COMMANDS else None,
            "requested_model": submit_meta.get("requested_handler") if handler not in HANDLER_SUBMIT_COMMANDS else None,
            "browser_model_preference": str(getattr(args, "browser_model_preference", "") or "") or None,
            "transport_summary_path": str(transport_summary_path) if transport_summary_path else None,
            "surf_provider_result_path": str(surf_provider_result_path) if surf_provider_result_path else None,
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    evidence = [
        {
            "kind": "handler_response_receipt",
            "node_id": args.node_id,
            "handler": handler,
            "path": str(receipt_path),
            "status": status,
            "verdict": verdict,
            "failure_code": recovery_packet.get("failure_code") if recovery_packet else None,
            "mocked": False,
            "live": bool(commands),
            "provider_live": provider_live,
            "provider_receipt": receipt["provider_receipt"],
        },
        {
            "kind": "normalized_handler_receipt",
            "node_id": args.node_id,
            "handler": handler,
            "response_path": str(response_path),
            "response_chars": len(response_text),
            "response_quarantine": response_quarantine,
        },
        {
            "kind": "transport_metadata",
            "node_id": args.node_id,
            "handler": handler,
            "meta_path": str(meta_path),
        },
    ]
    if transport_summary_path:
        evidence.append(
            {
                "kind": "webgpt_transport_summary",
                "node_id": args.node_id,
                "handler": handler,
                "path": str(transport_summary_path),
                "final_transport_state": transport_summary.get("final_transport_state"),
                "next_command": transport_summary.get("next_command"),
            }
        )
    if surf_provider_result_path:
        evidence.append(
            {
                "kind": "surf_provider_result",
                "node_id": args.node_id,
                "handler": handler,
                "path": str(surf_provider_result_path),
                "schema": surf_provider_result.get("schema") if isinstance(surf_provider_result, dict) else None,
                "status": surf_provider_result.get("status") if isinstance(surf_provider_result, dict) else None,
                "proof_status": surf_provider_result.get("proof_status") if isinstance(surf_provider_result, dict) else None,
                "success": surf_provider_result.get("success") if isinstance(surf_provider_result, dict) else None,
            }
        )
    if browser_transport_queue_path.is_file():
        evidence.append(
            {
                "kind": "browser_transport_queue",
                "node_id": args.node_id,
                "handler": handler,
                "path": str(browser_transport_queue_path),
            }
        )
    if prior_receipts:
        evidence.append(
            {
                "kind": "prior_handler_receipts",
                "node_id": args.node_id,
                "prior_nodes": [
                    {
                        "node_id": item.get("node_id"),
                        "status": item.get("status"),
                        "path": item.get("path"),
                    }
                    for item in prior_receipts
                ],
            }
        )
    if recovery_packet:
        evidence.append(
            {
                "kind": "browser_failure_recovery_packet",
                "node_id": args.node_id,
                "handler": handler,
                "path": str(recovery_packet_path),
                "failure_code": recovery_packet["failure_code"],
                "auto_retry_allowed": recovery_packet["auto_retry_allowed"],
                "next_command": recovery_packet["next_command"],
            }
        )
    if binding_refresh and binding_refresh.get("status") == "updated":
        evidence.append(
            {
                "kind": "browser_oracle_binding_refresh",
                "node_id": args.node_id,
                "handler": handler,
                "project": binding_refresh.get("project"),
                "previous_url": binding_refresh.get("previous_url"),
                "current_url": binding_refresh.get("current_url"),
                "binding_path": binding_refresh.get("binding_path"),
            }
        )
    artifacts = [receipt_path, prompt_path, response_path, raw_path, meta_path, recovery_packet_path, browser_transport_queue_path]
    if transport_summary_path:
        artifacts.append(transport_summary_path)
    handoff = _handoff(
        args,
        start,
        status=status,
        summary=f"{args.node_id} {status.lower()} via {HANDLER_SUBMIT_COMMANDS.get(handler, handler)}.",
        artifacts=artifacts,
        evidence=evidence,
    )
    return {"exit_code": 0 if lane_exit_ok else 1, "handoff": handoff}


def _current_tab_url(args: argparse.Namespace, tab_id: str) -> str:
    """Best-effort live URL for an explicit tab id via surf tab.list (#1252).

    Used to supply --expect-url when the binding has no conversation_url yet,
    so the webgpt identity guard can verify the tab even amid many open
    provider tabs. Never raises; returns "" on any failure.
    """
    try:
        res = _run_cmd([str(args.surf_run), "tab.list", "--json"], cwd=Path(args.surf_run).parent, timeout=30)
        if res.returncode != 0:
            return ""
        parsed = json.loads(res.stdout.strip())
        rows = parsed.get("tabs") if isinstance(parsed, dict) else parsed
        if not isinstance(rows, list):
            return ""
        for row in rows:
            if isinstance(row, dict) and str(row.get("id")) == str(tab_id):
                return str(row.get("url") or "")
    except Exception:
        return ""
    return ""


def _browser_submit_command(
    args: argparse.Namespace,
    *,
    handler: str,
    prompt_path: Path,
    response_path: Path,
    raw_path: Path,
    meta_path: Path,
    tab_id: str,
    url: str,
    attachment_paths: list[str],
) -> list[str]:
    command = [
        str(args.surf_run),
        HANDLER_SUBMIT_COMMANDS[handler],
        "--input",
        str(prompt_path),
        "--output",
        str(response_path),
        "--raw-output",
        str(raw_path),
        "--meta-output",
        str(meta_path),
        "--timeout",
        str(args.timeout),
        "--stable-polls",
        str(args.stable_polls),
        "--stable-stall-ms",
        _browser_stable_stall_ms(),
    ]
    # Reasoning models go quiet for minutes: the assistant text stops changing
    # while the model thinks, which surf's default 30s stall heuristic reads as
    # "finished, no sentinel" and returns empty. On 2026-08-13 this discarded a
    # complete 15k-character ChatGPT Pro answer TWICE (lane-diagnostics:
    # response_rendered_capture_missed / missing_sentinel) — the sentinel was
    # present in the tab both times. The run --timeout is the real bound, so
    # wait for the sentinel until it expires. Override with ASK_STABLE_STALL_MS.
    _append_browser_lock_timeout(command, args)
    if tab_id:
        command.extend(["--tab-id", tab_id])
    if url:
        if handler == "webgpt":
            if tab_id:
                command.extend(["--expect-url", url])
            elif not tab_id:
                command.extend(["--url", url])
        else:
            command.extend(["--url", url])
    browser_model_preference = str(getattr(args, "browser_model_preference", "") or "").strip()
    if handler == "webclaude" and browser_model_preference:
        command.extend(["--model", browser_model_preference])
    for attachment_path in attachment_paths:
        command.extend(["--attach-file", attachment_path])
    if args.no_activate:
        command.append("--no-activate")
    return command


def _browser_stable_stall_ms() -> str:
    """Milliseconds of unchanged assistant text before surf gives up waiting.

    "0" means wait until --timeout. That is the correct default here: a quiet
    reasoning model is not a stalled one, and the run timeout already bounds
    the wait. Env override exists for lanes that would rather fail fast.
    """
    raw = os.environ.get("ASK_STABLE_STALL_MS", "0").strip()
    try:
        return str(max(0, int(raw)))
    except ValueError:
        return "0"


def _append_browser_lock_timeout(command: list[str], args: argparse.Namespace) -> None:
    browser_lock_timeout = int(getattr(args, "browser_lock_timeout", 0) or 0)
    if browser_lock_timeout > 0:
        command.extend(["--lock-timeout", str(browser_lock_timeout)])


def _prepare_browser_submit_payload(
    *,
    handler: str,
    prompt_path: Path,
    request_payload: dict[str, Any],
    attachment_paths: list[str],
) -> tuple[Path, list[str], dict[str, Any]]:
    prompt_text = prompt_path.read_text(encoding="utf-8", errors="replace")
    local_candidates = _local_path_candidates(prompt_text)
    readable_bundle_paths = _local_readable_bundle_paths(prompt_text, request_payload)
    combined_attachments = _unique_existing_files([*attachment_paths, *readable_bundle_paths])
    policy = _payload_policy(handler)
    inline_candidates = combined_attachments
    if handler == "webgpt":
        inline_candidates = _unique_existing_files(attachment_paths)
    inline_paths = _inline_text_bundle_paths(inline_candidates) if policy.inline_text_attachments else []
    inline_by_resolved = {str(Path(path).resolve()): index + 1 for index, path in enumerate(inline_paths)}
    submit_attachments = [path for path in combined_attachments if str(Path(path).resolve()) not in inline_by_resolved]
    if not local_candidates and not inline_paths and not submit_attachments:
        return (
            prompt_path,
            submit_attachments,
            {
                "schema": "ask.browser_local_path_preflight.v1",
                "status": "PASS",
                "local_path_count": 0,
                "attached_file_count": len(submit_attachments),
                "inlined_file_count": 0,
                "sanitized_prompt_path": None,
            },
        )

    attached_by_resolved = {str(Path(path).resolve()): index + 1 for index, path in enumerate(submit_attachments)}
    sanitized = prompt_text
    replacements: list[dict[str, Any]] = []
    for candidate in local_candidates:
        path = Path(candidate).expanduser()
        label = "local-only path not attached"
        attachment_index = None
        inline_index = None
        if path.is_file():
            try:
                resolved = str(path.resolve())
                attachment_index = attached_by_resolved.get(resolved)
                inline_index = inline_by_resolved.get(resolved)
            except OSError:
                attachment_index = None
                inline_index = None
        if attachment_index is not None:
            label = f"attached local evidence file ATTACHMENT_{attachment_index}"
        elif inline_index is not None:
            label = f"inlined local evidence file INLINE_{inline_index}"
        replacement = f"[{label}: {path.name}]"
        sanitized = sanitized.replace(candidate, replacement)
        replacements.append(
            {
                "path": candidate,
                "file_exists": path.is_file(),
                "attached": attachment_index is not None,
                "inlined": inline_index is not None,
                "attachment_index": attachment_index,
                "inline_index": inline_index,
                "replacement": replacement,
            }
        )

    sanitized_prompt_path = prompt_path.with_name("browser-readable-prompt.md")
    attachment_lines = []
    for index, path in enumerate(submit_attachments, start=1):
        attachment_lines.append(f"- ATTACHMENT_{index}: {Path(path).name}")
    if attachment_lines:
        sanitized += "\n\nLocal evidence attachments available to the browser model:\n" + "\n".join(attachment_lines)
        sanitized += "\nUse the attached files as source material; do not rely on local filesystem paths.\n"
    if inline_paths:
        sanitized += "\n\nLocal evidence bundles inlined for this provider:\n"
        for index, path in enumerate(inline_paths, start=1):
            path_obj = Path(path)
            text = path_obj.read_text(encoding="utf-8", errors="replace")
            sanitized += f"\n### INLINE_{index}: {path_obj.name}\n\n```text\n{text.rstrip()}\n```\n"
        sanitized += "\nUse the INLINE_* sections as source material; they replace local filesystem attachment paths for this provider.\n"
    sanitized_prompt_path.write_text(sanitized, encoding="utf-8")
    return (
        sanitized_prompt_path,
        submit_attachments,
        {
            "schema": "ask.browser_local_path_preflight.v1",
            "status": "PASS" if policy.can_attach or inline_paths or not readable_bundle_paths else "NEEDS_ATTENTION",
            "local_path_count": len(local_candidates),
            "attached_file_count": len(submit_attachments),
            "inlined_file_count": len(inline_paths),
            "sanitized_prompt_path": str(sanitized_prompt_path),
            "replacements": replacements,
        },
    )


def _local_path_candidates(text: str) -> list[str]:
    """Absolute paths in the prompt that a browser seat could not open.

    A leading slash is not enough to make something a path. This prompt was
    corrupted in a live review because `/project-watchdog`, `/ticket` and
    `/monitor-sparta` are SKILL references and `*/5` is a cron expression --
    all four were rewritten to "[local-only path not attached: ...]", so the
    reviewer never saw the interval it was asked to judge.

    Two rules separate the cases without weakening the guard:

    - a single-segment `/word` that does not exist on disk is a skill
      reference, not a path worth mentioning to a remote model;
    - a candidate immediately preceded by `*` is a cron field.

    A real path that exists is still sanitized, which is the case the guard was
    written for: leaking a local path to a browser seat that cannot read it.
    """
    candidates: list[str] = []
    for candidate in _extract_path_candidates(text):
        if candidate.startswith("//") or "://" in candidate:
            continue
        path = Path(candidate).expanduser()
        if not path.is_absolute():
            continue
        # `*/5`, `*/15` -- a cron minute field, not a directory.
        if re.search(r"\*" + re.escape(candidate) + r"\b", text):
            continue
        # `/skill-name`: one segment, nothing on disk. Rewriting it destroys
        # the reference while protecting nothing.
        if len(path.parts) <= 2 and not path.exists():
            continue
        if candidate not in candidates:
            candidates.append(candidate)
    return candidates


def _unique_existing_files(paths: list[str]) -> list[str]:
    unique: list[str] = []
    for item in paths:
        path = Path(str(item)).expanduser()
        if not path.is_file():
            continue
        try:
            resolved = str(path.resolve())
        except OSError:
            continue
        if resolved not in unique:
            unique.append(resolved)
    return unique


def _inline_text_bundle_paths(paths: list[str], *, max_total_chars: int = 120_000) -> list[str]:
    inlineable_suffixes = {".md", ".markdown", ".txt", ".json", ".yaml", ".yml", ".csv"}
    selected: list[str] = []
    total = 0
    for item in paths:
        path = Path(item)
        if path.suffix.lower() not in inlineable_suffixes:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            resolved = str(path.resolve())
        except OSError:
            continue
        next_total = total + len(text)
        if next_total > max_total_chars:
            continue
        selected.append(resolved)
        total = next_total
    return selected


def _should_retry_browser_stale_binding(
    *,
    handler: str,
    url: str,
    submit_meta: dict[str, Any],
    submit: CmdResult,
) -> bool:
    if handler not in HANDLER_SUBMIT_COMMANDS or not url:
        return False
    if handler == "webgpt" and _is_chatgpt_home_url(url):
        return False
    haystack = "\n".join(
        [
            str(submit_meta.get("failure") or ""),
            str(submit_meta.get("blocker") or ""),
            str(submit_meta.get("proof_status") or ""),
            str(submit_meta.get("agent_diagnosis") or ""),
            submit.stderr,
            submit.stdout,
        ]
    ).lower()
    if _looks_browser_tool_unsupported(haystack) or _looks_browser_provider_rate_limited(haystack, submit_meta):
        return False
    retry_markers = (
        "tab_identity_preflight_failed",
        "browser_tab_identity_mismatch",
        "tab_not_open_chatgpt",
        "tab_not_open_claude",
        "tab_not_open_kimi",
        "tab_not_open_gemini",
        "tab_not_open_grok",
        "not authenticated",
        "login required",
        "log in to x.com",
        "input field: not found",
        "send button: not found",
        "input field not found",
        "send button not found",
        "composer not found",
        "no composer",
    )
    return any(marker in haystack for marker in retry_markers)


def _retry_browser_stale_binding(
    args: argparse.Namespace,
    *,
    handler: str,
    project: str,
    url: str,
    current_tab_id: str,
    prompt_path: Path,
    response_path: Path,
    raw_path: Path,
    meta_path: Path,
    attachment_paths: list[str],
    commands: list[dict[str, Any]],
) -> dict[str, Any] | None:
    candidates = _live_provider_tab_candidates(
        args,
        handler=handler,
        requested_url=url,
        exclude_tab_id=current_tab_id,
        commands=commands,
    )
    for candidate in candidates[:4]:
        tab_id = str(candidate.get("id") or "").strip()
        candidate_url = str(candidate.get("url") or url).strip()
        if not tab_id:
            continue
        retry_cmd = _browser_submit_command(
            args,
            handler=handler,
            prompt_path=prompt_path,
            response_path=response_path,
            raw_path=raw_path,
            meta_path=meta_path,
            tab_id=tab_id,
            url=candidate_url or url,
            attachment_paths=attachment_paths,
        )
        retry = _run_cmd(
            retry_cmd,
            cwd=Path(args.surf_run).parent,
            timeout=_browser_submit_timeout(
                handler,
                args.timeout,
                command_timeout_budget=int(getattr(args, "command_timeout_budget", 0) or 0),
            ),
        )
        retry_summary = retry.summary()
        retry_summary["recovery_attempt"] = f"{handler}_stale_binding_submit_existing_tab"
        retry_summary["candidate_tab_id"] = tab_id
        retry_summary["candidate_url"] = candidate_url or None
        commands.append(retry_summary)
        submit_meta = _read_json(meta_path) if meta_path.is_file() else {}
        if retry.returncode != 0:
            continue
        binding_refresh = _bind_browser_oracle_url(
            args,
            project=project,
            tab_id=tab_id,
            backend=HANDLER_BACKENDS[handler],
            previous_url=url,
            current_url=candidate_url or url,
            commands=commands,
        )
        return {
            "submit": retry,
            "submit_meta": submit_meta,
            "tab_id": tab_id,
            "binding_refresh": binding_refresh,
        }
    if handler != "webgpt":
        return None
    # #1222: recovery must not open tabs in the user's working window —
    # provision an unfocused reviewer window like normal seat provisioning.
    open_tab = _run_cmd([str(args.surf_run), "window.new", url, "--unfocused"], cwd=Path(args.surf_run).parent, timeout=90)
    open_summary = open_tab.summary()
    open_summary["recovery_attempt"] = "webgpt_stale_binding_open_url"
    commands.append(open_summary)
    if open_tab.returncode != 0 and "browser lock" in (open_tab.stderr + open_tab.stdout).lower():
        open_tab = _run_cmd(
            [str(args.surf_run), "window.new", url, "--unfocused", "--no-lock"],
            cwd=Path(args.surf_run).parent,
            timeout=90,
        )
        open_summary = open_tab.summary()
        open_summary["recovery_attempt"] = "webgpt_stale_binding_open_url_no_lock"
        commands.append(open_summary)
    if open_tab.returncode != 0:
        return None
    tab_id = _extract_tab_id(open_tab.stdout)
    if not tab_id:
        return None
    binding_refresh = _bind_browser_oracle_url(
        args,
        project=project,
        tab_id=tab_id,
        backend=HANDLER_BACKENDS[handler],
        previous_url="",
        current_url=url,
        commands=commands,
    )
    retry_cmd = _browser_submit_command(
        args,
        handler=handler,
        prompt_path=prompt_path,
        response_path=response_path,
        raw_path=raw_path,
        meta_path=meta_path,
        tab_id=tab_id,
        url=url,
        attachment_paths=attachment_paths,
    )
    retry = _run_cmd(
        retry_cmd,
        cwd=Path(args.surf_run).parent,
        timeout=_browser_submit_timeout(
            handler,
            args.timeout,
            command_timeout_budget=int(getattr(args, "command_timeout_budget", 0) or 0),
        ),
    )
    retry_summary = retry.summary()
    retry_summary["recovery_attempt"] = f"{handler}_stale_binding_submit_after_new_tab_rebind"
    commands.append(retry_summary)
    submit_meta = _read_json(meta_path) if meta_path.is_file() else {}
    return {
        "submit": retry,
        "submit_meta": submit_meta,
        "tab_id": tab_id,
        "binding_refresh": binding_refresh,
    }


def _live_provider_tab_candidates(
    args: argparse.Namespace,
    *,
    handler: str,
    requested_url: str,
    exclude_tab_id: str,
    commands: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    tab_list = _run_cmd([str(args.surf_run), "tab.list", "--json"], cwd=Path(args.surf_run).parent, timeout=60)
    summary = tab_list.summary()
    summary["recovery_attempt"] = f"{handler}_stale_binding_scan_live_tabs"
    commands.append(summary)
    if tab_list.returncode != 0:
        return []
    payload = _parse_json_array_or_tabs(tab_list.stdout)
    if not isinstance(payload, list):
        return []
    candidates: list[dict[str, Any]] = []
    for tab in payload:
        if not isinstance(tab, dict):
            continue
        tab_id = str(tab.get("id") or "").strip()
        if not tab_id or tab_id == str(exclude_tab_id):
            continue
        tab_url = str(tab.get("url") or "").strip()
        if not _is_provider_url(handler, tab_url, requested_url):
            continue
        candidates.append(tab)
    return sorted(candidates, key=lambda item: (not bool(item.get("active")), str(item.get("id") or "")))


def _is_provider_url(handler: str, tab_url: str, requested_url: str = "") -> bool:
    url = tab_url or requested_url
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if handler == "webgpt":
        return host in {"chatgpt.com", "www.chatgpt.com"}
    if handler == "webclaude":
        return host in {"claude.ai", "www.claude.ai"}
    if handler == "webkimi":
        return host in {"kimi.com", "www.kimi.com"}
    if handler == "webgemini":
        return host in {"gemini.google.com"}
    if handler == "webgrok":
        return host in {"grok.com", "www.grok.com", "x.com", "www.x.com"}
    return False


def _extract_tab_id(text: str) -> str:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        for key in ("tabId", "tab_id", "id"):
            value = payload.get(key)
            if value:
                return str(value)
    match = re.search(r"\btab(?:Id|[_ -]?id)?[\"':=\s]+(\d{3,})\b", text, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _normalize_degraded_webgpt_response(
    *,
    handler: str,
    meta_path: Path,
    response_path: Path,
    raw_path: Path,
) -> bool:
    if handler != "webgpt" or not meta_path.is_file() or not response_path.is_file() or not raw_path.is_file():
        return False
    try:
        meta = _read_json(meta_path)
        raw_text = raw_path.read_text(encoding="utf-8", errors="replace")
        clean_text = response_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, json.JSONDecodeError, RuntimeError):
        return False
    if not _is_degraded_webgpt_response_available(meta, raw_text=raw_text, clean_text=clean_text):
        return False

    requested_tab = str(meta.get("requested_tab_id") or "").strip()
    identity = meta.get("tab_identity_preflight") if isinstance(meta.get("tab_identity_preflight"), dict) else {}
    tab = identity.get("tab") if isinstance(identity.get("tab"), dict) else {}
    tab_url = str(tab.get("url") or "").strip()
    focus_warning = str(meta.get("failure") or "focus_stolen_despite_no_activate")
    meta.update(
        {
            "status": "recovered_focus_changed",
            "failure": focus_warning,
            "focus_drift_warning": focus_warning,
            "proof_status": "response_proven",
            "response_proof_status": "response_proven",
            "controlled_tab_id": str(meta.get("controlled_tab_id") or requested_tab),
            "controlled_tab_id_mismatch": False,
            "transport_degraded": True,
            "recovered_output": True,
            "agent_diagnosis": (
                "ChatGPT returned the current sentinel-bearing assistant response from the verified requested tab; "
                "focus changed during no-activate mode, so background focus proof is degraded."
            ),
            "agent_action": (
                "Use raw_output, output, and meta_output as degraded reviewer response evidence; "
                "preserve focus_drift_warning and do not claim clean background focus invariance."
            ),
        }
    )
    if tab_url:
        if not meta.get("current_url"):
            meta["current_url"] = tab_url
        if not meta.get("tab_url"):
            meta["tab_url"] = tab_url
        if _is_chatgpt_conversation_url(tab_url) and not meta.get("conversation_url"):
            meta["conversation_url"] = tab_url
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def _write_surf_provider_result(
    args: argparse.Namespace,
    *,
    handler: str,
    meta_path: Path,
    submit: CmdResult,
    artifact_dir: Path,
    commands: list[dict[str, Any]],
) -> tuple[Path | None, dict[str, Any]]:
    if handler not in HANDLER_SUBMIT_COMMANDS or not meta_path.is_file():
        return None, {}
    provider = SURF_PROVIDER_RESULT_PROVIDERS.get(handler, "unknown")
    stdout_path = artifact_dir / "submit.stdout.txt"
    stderr_path = artifact_dir / "submit.stderr.txt"
    result_path = artifact_dir / "response.provider_result.json"
    stdout_path.write_text(submit.stdout or "", encoding="utf-8")
    stderr_path.write_text(submit.stderr or "", encoding="utf-8")
    command = [
        str(args.surf_run),
        "meta.normalize",
        "--meta",
        str(meta_path),
        "--provider",
        provider,
        "--json",
        "--return-code",
        str(submit.returncode),
        "--duration-seconds",
        f"{submit.duration:.3f}",
        "--command-stdout-file",
        str(stdout_path),
        "--command-stderr-file",
        str(stderr_path),
    ]
    result = _run_cmd(command, cwd=Path(args.surf_run).parent, timeout=30)
    # The normalizer receipt lives in the payload (normalizer_command); it is
    # intentionally not appended to `commands` so the submit itself stays the
    # terminal command entry (timeout receipts assert commands[-1] is the submit).
    del commands
    if result.returncode != 0:
        payload = {
            "schema": "surf.provider_result.v1",
            "provider": provider,
            "status": "failed",
            "proof_status": "normalization_failed",
            "success": False,
            "normalizer_command": result.summary(),
            "source_meta": str(meta_path),
        }
    else:
        try:
            payload = _parse_json_object(result.stdout)
        except (json.JSONDecodeError, RuntimeError) as exc:
            payload = {
                "schema": "surf.provider_result.v1",
                "provider": provider,
                "status": "failed",
                "proof_status": "normalization_parse_failed",
                "success": False,
                "error": str(exc),
                "normalizer_command": result.summary(),
                "source_meta": str(meta_path),
            }
    result_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result_path, payload


def _is_degraded_webgpt_response_available(meta: dict[str, Any], *, raw_text: str, clean_text: str) -> bool:
    failure = str(meta.get("failure") or "")
    if failure not in {"focus_stolen_mid_submit", "focus_stolen_despite_no_activate"}:
        return False
    if meta.get("focus_invariant_ok") is not False:
        return False
    sentinel = str(meta.get("sentinel") or "")
    if not sentinel or sentinel not in raw_text or sentinel in clean_text:
        return False
    if meta.get("raw_contains_sentinel") is False or meta.get("clean_contains_sentinel") is True:
        return False
    if meta.get("clean_contamination_markers"):
        return False
    requested_tab = str(meta.get("requested_tab_id") or "").strip()
    controlled_tab = str(meta.get("controlled_tab_id") or "").strip()
    if controlled_tab and requested_tab and controlled_tab != requested_tab:
        return False
    identity = meta.get("tab_identity_preflight")
    if not isinstance(identity, dict) or identity.get("ok") is not True:
        return False
    tab = identity.get("tab")
    if not isinstance(tab, dict):
        tab = {}
    identity_tab = str(identity.get("tab_id") or tab.get("id") or "").strip()
    return bool(requested_tab and identity_tab == requested_tab)


def _refresh_browser_binding_after_proven_submit(
    args: argparse.Namespace,
    *,
    project: str,
    tab_id: str,
    previous_url: str,
    submit_meta: dict[str, Any],
    commands: list[dict[str, Any]],
) -> dict[str, Any]:
    handler = str(args.handler)
    if handler not in {"webgpt", "webclaude"}:
        return {"status": "skipped", "reason": "handler_not_refreshable"}
    current_url = _proven_live_browser_conversation_url(handler, submit_meta)
    if not current_url:
        return {"status": "skipped", "reason": "no_proven_live_conversation_url"}
    if _same_url(previous_url, current_url):
        return {
            "status": "not_needed",
            "project": project,
            "tab_id": tab_id,
            "current_url": current_url,
            "previous_url": previous_url or None,
        }
    return _bind_browser_oracle_url(
        args,
        project=project,
        tab_id=tab_id,
        backend=HANDLER_BACKENDS[handler],
        previous_url=previous_url,
        current_url=current_url,
        commands=commands,
    )


def _refresh_browser_binding_before_submit(
    args: argparse.Namespace,
    *,
    project: str,
    tab_id: str,
    previous_url: str,
    commands: list[dict[str, Any]],
) -> dict[str, Any]:
    handler = str(args.handler)
    if handler not in {"webclaude", "webgpt"}:
        return {"status": "skipped", "reason": "handler_not_presubmit_refreshable"}
    live_url = _live_tab_url(args.surf_run, tab_id, commands=commands)
    if not live_url:
        return {"status": "skipped", "reason": "live_tab_url_unavailable"}
    safe_transition = (
        _is_claude_new_to_chat_transition(previous_url, live_url)
        if handler == "webclaude"
        else _is_chatgpt_home_to_chat_transition(previous_url, live_url)
    )
    if not safe_transition:
        return {"status": "skipped", "reason": "not_safe_provider_url_transition", "live_url": live_url}
    return _bind_browser_oracle_url(
        args,
        project=project,
        tab_id=tab_id,
        backend=HANDLER_BACKENDS[handler],
        previous_url=previous_url,
        current_url=live_url,
        commands=commands,
    )


def _bind_browser_oracle_url(
    args: argparse.Namespace,
    *,
    project: str,
    tab_id: str,
    backend: str,
    previous_url: str,
    current_url: str,
    commands: list[dict[str, Any]],
) -> dict[str, Any]:
    bind_cmd = [
        str(args.browser_oracle_run),
        "bind",
        project,
        "--backend",
        backend,
        "--tab-id",
        tab_id,
        "--url",
        current_url,
        "--manual",
        "--json",
    ]
    bind = _run_cmd(bind_cmd, cwd=Path(args.browser_oracle_run).parent, timeout=60)
    commands.append(bind.summary())
    if bind.returncode != 0:
        raise RuntimeError(
            "BLOCKED_BROWSER_BINDING_REFRESH_FAILED: "
            + (bind.stderr.strip() or bind.stdout.strip() or "browser-oracle bind failed")
        )
    payload = _parse_json_object(bind.stdout)
    return {
        "status": "updated",
        "project": project,
        "tab_id": tab_id,
        "previous_url": previous_url or None,
        "current_url": current_url,
        "binding_path": payload.get("state_path"),
        "browser_oracle": payload,
    }


def _live_tab_url(surf_run: str, tab_id: str, *, commands: list[dict[str, Any]]) -> str:
    tab_list = _run_cmd([str(surf_run), "tab.list", "--json"], cwd=Path(surf_run).parent, timeout=60)
    commands.append(tab_list.summary())
    if tab_list.returncode != 0:
        return ""
    payload = _parse_json_array_or_tabs(tab_list.stdout)
    if not isinstance(payload, list):
        return ""
    for tab in payload:
        if not isinstance(tab, dict):
            continue
        if str(tab.get("id") or "") == str(tab_id):
            return str(tab.get("url") or "").strip()
    return ""


def _proven_live_browser_conversation_url(handler: str, meta: dict[str, Any]) -> str:
    if handler == "webgpt":
        return _proven_live_webgpt_conversation_url(meta)
    if handler == "webclaude":
        return _proven_live_claude_conversation_url(meta)
    return ""


def _proven_live_webgpt_conversation_url(meta: dict[str, Any]) -> str:
    if not isinstance(meta, dict):
        return ""
    status = str(meta.get("status") or "")
    proof_status = str(meta.get("response_proof_status") or meta.get("proof_status") or "")
    if status not in {"completed", "recovered_focus_changed"}:
        return ""
    if proof_status != "response_proven":
        return ""
    requested_tab = str(meta.get("requested_tab_id") or "")
    controlled_tab = str(meta.get("controlled_tab_id") or "")
    if requested_tab and controlled_tab and requested_tab != controlled_tab:
        return ""
    for key in ("current_url", "conversation_url", "tab_url", "final_url"):
        url = str(meta.get(key) or "").strip()
        if _is_chatgpt_conversation_url(url):
            return url
    return ""


def _proven_live_claude_conversation_url(meta: dict[str, Any]) -> str:
    if not isinstance(meta, dict):
        return ""
    if str(meta.get("status") or "") != "completed":
        return ""
    requested_tab = str(meta.get("requested_tab_id") or "")
    controlled_tab = str(meta.get("controlled_tab_id") or "")
    if requested_tab and controlled_tab and requested_tab != controlled_tab:
        return ""
    if meta.get("raw_contains_sentinel") is not True:
        return ""
    candidates = [
        str(meta.get("current_url") or "").strip(),
        str(meta.get("conversation_url") or "").strip(),
        str(meta.get("tab_url") or "").strip(),
        str(meta.get("final_url") or "").strip(),
    ]
    identity = meta.get("tab_identity_preflight")
    if isinstance(identity, dict):
        candidates.append(str(identity.get("live_url") or "").strip())
        tab = identity.get("tab")
        if isinstance(tab, dict):
            candidates.append(str(tab.get("url") or "").strip())
    for url in candidates:
        if _is_claude_conversation_url(url):
            return url
    return ""


def _is_chatgpt_conversation_url(url: str) -> bool:
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        return False
    if parsed.netloc not in {"chatgpt.com", "www.chatgpt.com"}:
        return False
    parts = [part for part in parsed.path.split("/") if part]
    return "c" in parts and parts[-1] != "project"


def _is_chatgpt_home_url(url: str) -> bool:
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        return False
    if parsed.netloc not in {"chatgpt.com", "www.chatgpt.com"}:
        return False
    return parsed.path.strip("/") in {"", "new"}


def _is_chatgpt_home_to_chat_transition(expected_url: str, live_url: str) -> bool:
    return _is_chatgpt_home_url(expected_url) and _is_chatgpt_conversation_url(live_url)


def _is_claude_conversation_url(url: str) -> bool:
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        return False
    if parsed.netloc not in {"claude.ai", "www.claude.ai"}:
        return False
    parts = [part for part in parsed.path.split("/") if part]
    return len(parts) >= 2 and parts[0] == "chat" and bool(parts[1])


def _is_claude_new_to_chat_transition(expected_url: str, live_url: str) -> bool:
    expected = urllib.parse.urlparse(str(expected_url or "").strip())
    live = urllib.parse.urlparse(str(live_url or "").strip())
    if expected.netloc not in {"claude.ai", "www.claude.ai"}:
        return False
    if live.netloc not in {"claude.ai", "www.claude.ai"}:
        return False
    expected_path = expected.path.rstrip("/")
    live_path = live.path.rstrip("/")
    return expected_path in {"", "/new"} and live_path.startswith("/chat/")


def _same_url(left: str, right: str) -> bool:
    return left.strip().rstrip("/") == right.strip().rstrip("/")


def _browser_failure_recovery_packet(
    args: argparse.Namespace,
    *,
    request_payload: dict[str, Any],
    failure: str,
    response_text: str,
    raw_text: str,
    prompt_text: str,
    submit_meta: dict[str, Any],
    commands: list[dict[str, Any]],
    browser_oracle: dict[str, Any],
    response_path: Path,
    raw_path: Path,
    meta_path: Path,
    prompt_path: Path,
) -> dict[str, Any]:
    handler = str(args.handler)
    failure_code = _classify_browser_failure(
        handler=handler,
        failure=failure,
        response_text=response_text,
        raw_text=raw_text,
        prompt_text=prompt_text,
        submit_meta=submit_meta,
        commands=commands,
    )
    bundle_paths = _unique_existing_files(
        [
            *[str(item) for item in (getattr(args, "attach_files", None) or [])],
            str(submit_meta.get("attach_file") or ""),
            *_local_readable_bundle_paths(prompt_text, request_payload),
        ]
    )
    payload_policy = _payload_policy(handler)
    can_attach = payload_policy.can_attach
    failure_meta = _browser_failure_code(failure_code)
    auto_retry_allowed = failure_meta.bundle_retry_candidate and bool(bundle_paths) and can_attach
    stale_binding = _webgpt_stale_binding_details(submit_meta)
    surf_lock_blocker = _surf_lock_blocker_details(failure=failure, commands=commands, submit_meta=submit_meta)
    transport_failure_summary = _browser_transport_failure_summary(
        failure_code=failure_code,
        submit_meta=submit_meta,
        commands=commands,
        surf_lock_blocker=surf_lock_blocker,
    )
    recovery_prompt = sanitize_recovery_prompt(prompt_path, bundle_paths)
    recovery_prompt_path = Path(recovery_prompt.get("prompt_path") or prompt_path)
    bound_tab_id = str(browser_oracle.get("tab_id") or "").strip()
    bound_tab_open = tab_still_open(str(getattr(args, "surf_run", "") or ""), bound_tab_id)
    lock_owner = surf_lock_owner()
    lock_snapshot = {
        "owner": lock_owner,
        "observed_after_failure": True,
        "causal_only_when_surf_lock_blocker_present": bool(surf_lock_blocker),
    }
    next_command = _recovery_next_command(
        args,
        request_payload=request_payload,
        failure_code=failure_code,
        bundle_path=bundle_paths[0] if bundle_paths else "",
        can_attach=can_attach,
        browser_oracle=browser_oracle,
        submit_meta=submit_meta,
        response_path=response_path,
        raw_path=raw_path,
        meta_path=meta_path,
        prompt_path=recovery_prompt_path,
    )
    if bound_tab_open is False:
        # The bound tab is gone (fresh-temporary lifecycle already cleaned it up),
        # so a --tab-id retry would target a closed tab (agent-skills#1081).
        next_command = [item for item in next_command if item != bound_tab_id]
        next_command = [
            item for index, item in enumerate(next_command)
            if item != "--tab-id" or index + 1 < len(next_command)
        ]
        next_command = [item for item in next_command if item != "--tab-id"]
    next_command, next_command_rejected = _validate_next_command_runnable(next_command)
    RecoveryPacketContract(
        schema=str(RECOVERY_PACKET_SCHEMA),
        failure_code=str(failure_code),
        next_command=list(next_command),
    ).validate()
    return {
        "schema": RECOVERY_PACKET_SCHEMA,
        **({"next_command_rejected": next_command_rejected} if next_command_rejected else {}),
        "status": "NEEDS_ATTENTION",
        "mocked": False,
        "live": bool(commands),
        "failure_code": failure_code,
        "handler": handler,
        "node_id": args.node_id,
        "reason": _recovery_reason(failure_code),
        "evidence": {
            "failure_excerpt": failure.strip()[:2000],
            "response_chars": len(response_text),
            "raw_response_chars": len(raw_text),
            "prompt_chars": len(prompt_text),
            "measured_prompt_chars": len(prompt_text),
            "provider_prompt_limit_chars": _provider_reported_limit_chars(failure),
            "submit_meta_status": submit_meta.get("status") or submit_meta.get("status_code"),
            "last_command": commands[-1] if commands else None,
            "timeout_diagnostics": submit_meta.get("ask_timeout_diagnostics"),
            "environment_dependency": (
                _environment_dependency_details(failure.lower())
                if failure_code == ENVIRONMENT_DEPENDENCY_INSTALL_FAILED
                else None
            ),
            "stale_binding": stale_binding,
            "surf_lock_blocker": surf_lock_blocker,
            "surf_lock_snapshot": lock_snapshot,
            "surf_lock_owner": lock_owner,
            "bound_tab_open": bound_tab_open,
            "recovery_prompt": recovery_prompt,
            "submit_meta_summary": transport_failure_summary,
        },
        "transport_failure_summary": transport_failure_summary,
        "local_readable_bundle_paths": bundle_paths,
        "requires_local_readable_bundle": _requires_local_readable_bundle(failure_code),
        "attach_file_supported": can_attach,
        "auto_retry_allowed": auto_retry_allowed,
        "auto_retry_blocked_reason": None
        if auto_retry_allowed
        else _auto_retry_blocked_reason(
            failure_code=failure_code,
            bundle_paths=bundle_paths,
            can_attach=can_attach,
        ),
        "next_command": next_command,
        "fallback_instruction": _fallback_instruction(
            failure_code,
            has_bundle=bool(bundle_paths),
            can_attach=can_attach,
            handler=handler,
        ),
        "ticket_target": ASK_TICKET_TARGET,
        "ticket_instruction": _ask_ticket_instruction(
            failure_code=failure_code,
            packet_kind="browser-recovery-packet",
        ),
    }


def _quarantine_failed_browser_response(
    *,
    response_path: Path,
    recovery_packet: dict[str, Any],
    response_text: str,
) -> dict[str, Any]:
    failure_code = str(recovery_packet.get("failure_code") or "browser_handler_failed")
    quarantine_path: Path | None = None
    if response_path.is_file():
        label = _browser_failure_code(failure_code).quarantine_label
        quarantine_path = _unique_quarantine_path(response_path.with_name(f"response.{label}.md"))
        response_path.rename(quarantine_path)
    quarantine = {
        "schema": "ask.browser_failed_response_quarantine.v1",
        "status": "QUARANTINED" if quarantine_path else "NO_RESPONSE_FILE",
        "ok": False,
        "provider_live": False,
        "failure_code": failure_code,
        "original_response_path": str(response_path),
        "quarantine_path": str(quarantine_path) if quarantine_path else None,
        "response_chars": len(response_text),
        "caller_action": (
            "Do not treat this browser prose as a clean seat response unless a later PASS receipt "
            "replaces this quarantine artifact."
        ),
    }
    quarantine_path_for_json = response_path.with_name("response.quarantine.json")
    quarantine["quarantine_receipt_path"] = str(quarantine_path_for_json)
    quarantine_path_for_json.write_text(json.dumps(quarantine, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return quarantine


def _unique_quarantine_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(2, 100):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"unable to allocate quarantine path near {path}")


def _classify_browser_failure(
    *,
    handler: str,
    failure: str,
    response_text: str,
    raw_text: str,
    prompt_text: str,
    submit_meta: dict[str, Any],
    commands: list[dict[str, Any]],
) -> str:
    haystack = "\n".join(
        [
            failure,
            response_text,
            raw_text,
            _match_text(submit_meta),
            _match_text(commands[-1] if commands else {}),
        ]
    ).lower()
    if (
        str(submit_meta.get("failure") or "") == WEBGPT_CONVERSATION_FULL_BLOCKER
        or str(submit_meta.get("blocker") or "") == WEBGPT_CONVERSATION_FULL_BLOCKER
        or WEBGPT_CONVERSATION_FULL_BLOCKER.lower() in haystack
    ):
        return WEBGPT_CONVERSATION_FULL_BLOCKER
    if _webgpt_stale_binding_details(submit_meta):
        return WEBGPT_BINDING_STALE_BLOCKER
    if _looks_browser_attachment_argument_contract_failed(haystack):
        return BROWSER_ATTACHMENT_ARGUMENT_CONTRACT_FAILED
    if _looks_environment_dependency_install_failed(haystack):
        return ENVIRONMENT_DEPENDENCY_INSTALL_FAILED
    if _looks_surf_browser_lock_timeout(haystack, commands, submit_meta):
        return SURF_BROWSER_LOCK_TIMEOUT
    if _looks_surf_browser_connection_unavailable(haystack):
        return SURF_BROWSER_CONNECTION_UNAVAILABLE
    # Kimi's context-limit notice also says "try again", so it must be tested
    # before the rate-limit heuristic or it gets misread as throttling and the
    # lane waits out a cooldown that can never clear it.
    if _looks_kimi_conversation_too_long(haystack, submit_meta):
        return KIMI_CONVERSATION_TOO_LONG_BLOCKER
    if _looks_browser_provider_rate_limited(haystack, submit_meta):
        return BROWSER_PROVIDER_RATE_LIMITED
    if _looks_browser_provider_setup_failed(haystack, submit_meta):
        return BROWSER_PROVIDER_SETUP_FAILED
    # Specific pre-delivery causes must precede submit-not-accepted: that check
    # fires on `submitted_to_chatgpt is False`, which holds for EVERY failure
    # before delivery, so it otherwise masks the real mechanism (a genuine
    # access challenge or a Surf extension stall) behind a composer-recovery
    # instruction (agent-skills#1034).
    if _looks_browser_access_blocked(haystack, submit_meta):
        return BROWSER_ACCESS_BLOCKED
    if _looks_browser_extension_command_timeout(haystack, submit_meta):
        return BROWSER_EXTENSION_COMMAND_TIMEOUT
    if _looks_browser_submit_not_accepted(haystack, submit_meta):
        return BROWSER_SUBMIT_NOT_ACCEPTED
    if _looks_browser_tool_unsupported(haystack):
        return BROWSER_TOOL_UNSUPPORTED
    if (
        _browser_attachment_ui_missing_in_meta(submit_meta)
        or _looks_browser_attachment_ui_missing(haystack)
        or _kimi_attachment_metadata_missing_after_attach(handler, submit_meta)
    ):
        return BROWSER_ATTACHMENT_UI_MISSING
    if (
        BROWSER_ATTACHMENT_UNAVAILABLE in haystack
        or _browser_attachment_missing_in_meta(submit_meta)
        or _response_denies_attachment_access(response_text)
    ):
        return BROWSER_ATTACHMENT_UNAVAILABLE
    if _looks_webgpt_unverified_clean_output(handler, haystack, submit_meta):
        return WEBGPT_UNVERIFIED_CLEAN_OUTPUT
    if _looks_clean_output_contaminated(haystack, submit_meta):
        return BROWSER_CLEAN_OUTPUT_CONTAMINATED
    if _looks_sentinel_trailing_content(haystack, submit_meta):
        return BROWSER_SENTINEL_TRAILING_CONTENT
    if _looks_browser_tab_read_timeout(haystack):
        return BROWSER_TAB_READ_TIMEOUT
    if _looks_browser_handler_interrupted(submit_meta, commands):
        return BROWSER_HANDLER_INTERRUPTED
    if _looks_browser_handler_timeout(haystack, commands):
        return BROWSER_HANDLER_TIMEOUT
    if _looks_repo_access_blocked(haystack):
        return REPO_ACCESS_BLOCKED
    preflight_error = ""
    identity_pf = submit_meta.get("tab_identity_preflight")
    if isinstance(identity_pf, dict):
        preflight_error = str(identity_pf.get("error") or "").strip().lower()
    if preflight_error == "unverified_tab_id_with_multiple_chatgpt_tabs":
        return BROWSER_TAB_UNVERIFIED_MULTIPLE
    if preflight_error in {"tab_not_open_chatgpt", "tab_not_open_claude", "tab_not_open_kimi", "tab_not_open_gemini", "invalid_tab_id"}:
        return BROWSER_TAB_NOT_OPEN
    if _looks_tab_identity_mismatch(haystack, submit_meta):
        return BROWSER_TAB_IDENTITY_MISMATCH
    if _looks_stale_raw_capture(haystack, submit_meta):
        return STALE_RAW_CAPTURE
    if _looks_browser_composer_interaction_failed(haystack):
        return BROWSER_COMPOSER_INTERACTION_FAILED
    if _looks_prompt_too_large_or_stalled(haystack):
        return PROMPT_TOO_LARGE_OR_STALLED
    if _looks_missing_sentinel(haystack, submit_meta):
        return MISSING_SENTINEL
    return MISSING_SENTINEL


def _webgpt_stale_binding_details(meta: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(meta, dict):
        return {}
    identity = meta.get("tab_identity_preflight")
    if not isinstance(identity, dict):
        return {}
    if str(meta.get("failure") or "") != "tab_identity_preflight_failed":
        return {}
    if str(identity.get("error") or "") != "expected_url_mismatch":
        return {}
    tab = identity.get("tab")
    if not isinstance(tab, dict):
        tab = {}
    live_url = str(tab.get("url") or "").strip()
    expected_url = str(identity.get("expected_url") or meta.get("requested_url") or "").strip()
    tab_id = str(identity.get("expected_tab_id") or meta.get("requested_tab_id") or tab.get("id") or "").strip()
    if not live_url:
        return {}
    return {
        "expected_url": expected_url or None,
        "live_url": live_url,
        "tab_id": tab_id or None,
        "tab_title": tab.get("title"),
    }


def _looks_repo_access_blocked(text: str) -> bool:
    markers = (
        "can't access the repository",
        "cannot access the repository",
        "can't access this repository",
        "cannot access this repository",
        "private repository",
        "private github repo",
        "github app access",
        "grant access to repos",
        "repository access",
        "repo access",
        "unauthorized",
        "403",
        "404 not found",
        "prompt references unreadable local filesystem paths",
        "unreadable local filesystem paths",
        "local path",
        "no such file or directory",
    )
    return any(marker in text for marker in markers)


def _response_denies_attachment_access(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower())
    markers = (
        "attachment is inaccessible",
        "attachment is not accessible",
        "attachment is not mounted",
        "attached file is inaccessible",
        "attached file is not accessible",
        "attached image is inaccessible",
        "attached image is not accessible",
        "attached local image cannot be inspected",
        "attached image cannot be inspected",
        "attachment cannot be inspected",
        "attachment is unreachable",
        "attachment was not provided",
        "attachment is missing",
        "local attachment is unreachable",
        "source-of-truth attachment was not provided",
        "source of truth attachment was not provided",
        "designated source-of-truth attachment",
        "designated source of truth attachment",
        "image file was not provided",
        "image file was not attached",
        "attached review bundle was not provided",
        "review bundle was not provided",
        "no attachment or readme text was included",
        "image was not provided",
        "image was not attached",
        "no image content was provided",
        "no image content is available",
        "missing image asset",
        "does not exist on the accessible filesystem",
        "unable to inspect the visual contents",
        "cannot inspect the visual contents",
        "file was not provided or rendered",
    )
    return any(marker in normalized for marker in markers)


def _looks_browser_attachment_ui_missing(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower())
    return (
        "file input" in normalized
        and "not present" in normalized
        and ("kimi" in normalized or "attachment" in normalized or "upload" in normalized)
    )


def _browser_attachment_ui_missing_in_meta(meta: dict[str, Any]) -> bool:
    if not isinstance(meta, dict):
        return False
    failure = str(meta.get("failure") or "").lower()
    blocker = str(meta.get("blocker") or "").lower()
    proof_status = str(meta.get("proof_status") or "").lower()
    return (
        failure == "attachment_ui_missing"
        or blocker == "blocked_attachment_ui_missing"
        or proof_status == "file_upload_unavailable"
    )


def _kimi_attachment_metadata_missing_after_attach(handler: str, meta: dict[str, Any]) -> bool:
    if handler != "webkimi" or not isinstance(meta, dict):
        return False
    failure = str(meta.get("failure") or "").lower()
    return (
        failure == "attachment_metadata_missing"
        and bool(meta.get("attach_file"))
        and meta.get("attachment_missing") is True
    )


def _browser_attachment_missing_in_meta(meta: dict[str, Any]) -> bool:
    if not isinstance(meta, dict):
        return False
    failure = str(meta.get("failure") or "").lower()
    return (
        meta.get("attachment_missing") is True
        or meta.get("attachment_preview_missing") is True
        or failure in {"attachment_metadata_missing", "attachment_preview_missing"}
    )


def _match_text(value: Any) -> str:
    """Flatten a payload to its VALUES for substring classification.

    Field names must never reach the marker haystack: a meta payload always
    carries keys like `browser_access_blocked` and `timeout_error`, so dumping
    the whole JSON made every WebGPT failure match those markers regardless of
    the field values (agent-skills#1034).
    """
    parts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for item in node.values():
                walk(item)
        elif isinstance(node, (list, tuple, set)):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            parts.append(node)
        elif node is not None and not isinstance(node, bool):
            parts.append(str(node))

    walk(value)
    return "\n".join(parts)


def _looks_browser_extension_command_timeout(text: str, meta: dict[str, Any]) -> bool:
    """Surf's native host gave up waiting for the browser extension.

    This is a transport stall inside Surf/Chrome (`Timeout waiting for
    extension: <tool>`), not a provider access challenge. It is lane-local and
    retryable on the same binding.
    """
    if str(meta.get("failure") or "").strip().lower() == "extension_command_timeout":
        return True
    return "timeout waiting for extension" in text


def _looks_browser_access_blocked(text: str, meta: dict[str, Any]) -> bool:
    if meta.get("browser_access_blocked") is True or meta.get("cloudflare_challenge_detected") is True:
        return True
    timeout_markers = _timeout_diagnostic_markers(meta)
    if timeout_markers.get("access_blocked") is True:
        return True
    markers = (
        "cloudflare challenge",
        "blocked_webgpt_cloudflare_challenge",
        "complete in browser",
        "verify you are human",
        "checking if the site connection is secure",
        "browser_access_blocked",
    )
    return any(marker in text for marker in markers)


def _looks_kimi_conversation_too_long(text: str, meta: dict[str, Any]) -> bool:
    """Kimi refused the round because the thread hit its context budget.

    This is not throttling and not an attachment fault: the thread is spent, so
    the round has to go into a new chat. Surf's kimi client rotates once on its
    own, so reaching this code means a fresh chat still could not take the
    payload and the round needs to be split or shortened.
    """
    if meta.get("kimi_conversation_too_long") is True:
        return True
    if str(meta.get("failure") or "") == "kimi_conversation_too_long":
        return True
    if str(meta.get("blocker") or "") == KIMI_CONVERSATION_TOO_LONG_BLOCKER:
        return True
    if str(meta.get("proof_status") or "") == "conversation_length_limited":
        return True
    normalized = re.sub(r"\s+", " ", text.lower())
    if KIMI_CONVERSATION_TOO_LONG_BLOCKER.lower() in normalized:
        return True
    if "kimi conversation too long" in normalized:
        return True
    return (
        ("getting too long" in normalized or "is too long" in normalized)
        and ("new session" in normalized or "new chat" in normalized)
    )


def _looks_browser_provider_rate_limited(text: str, meta: dict[str, Any]) -> bool:
    if meta.get("chatgpt_too_many_requests_detected") is True:
        return True
    if meta.get("kimi_provider_capacity_busy") is True:
        return True
    if meta.get("failure") in {"kimi_provider_capacity_busy", "grok_provider_capacity_busy"}:
        return True
    if meta.get("blocker") in {"BLOCKED_KIMI_PROVIDER_CAPACITY", "BLOCKED_GROK_PROVIDER_CAPACITY"}:
        return True
    rate_limit = meta.get("chatgpt_rate_limit")
    if isinstance(rate_limit, dict) and rate_limit.get("exhausted") is True:
        return True
    timeout_markers = _timeout_diagnostic_markers(meta)
    if timeout_markers.get("provider_rate_limited") is True or timeout_markers.get("provider_busy") is True:
        return True
    markers = (
        "too many requests",
        "you've hit your limit",
        "you have hit your limit",
        "please try again later",
        "system is currently busy",
        "capacity is busy",
        "provider_capacity_limited",
        "temporarily limited access",
        "browser_provider_rate_limited",
        "grok_provider_rate_limited",
        "blocked_grok_provider_rate_limit",
        "limit is gone",
        "upgrade to supergrok",
    )
    return any(marker in text for marker in markers)


def _looks_browser_provider_setup_failed(text: str, meta: dict[str, Any]) -> bool:
    failure = str(meta.get("failure") or "").lower()
    blocker = str(meta.get("blocker") or "").lower()
    if failure == BROWSER_PROVIDER_SETUP_FAILED or blocker == BROWSER_PROVIDER_SETUP_FAILED:
        return True
    markers = (
        "model option not confirmed",
        "reasoning option not confirmed",
        "provider setup failed",
        "provider selector not confirmed",
        "model selector not confirmed",
        "reasoning selector not confirmed",
    )
    return any(marker in text for marker in markers)


def _looks_browser_submit_not_accepted(text: str, meta: dict[str, Any]) -> bool:
    failure = str(meta.get("failure") or "").lower()
    blocker = str(meta.get("blocker") or "").lower()
    if failure == BROWSER_SUBMIT_NOT_ACCEPTED or blocker == BROWSER_SUBMIT_NOT_ACCEPTED:
        return True
    if meta.get("submitted_to_chatgpt") is False or meta.get("submitted_to_kimi") is False:
        return True
    timeout_markers = _timeout_diagnostic_markers(meta)
    if timeout_markers.get("prompt_still_in_composer") is True:
        return True
    markers = (
        "prompt submission was not accepted",
        "composer still contains draft",
        "composer still contains the draft",
        "editor still contains draft",
        "editor still contains the draft",
        "submit click did not fire",
        "submit did not fire",
        "send did not fire",
        "message was not submitted",
        "prompt was not submitted",
        "input was not submitted",
    )
    return any(marker in text for marker in markers)


def _submit_not_accepted_can_retry_same_identity(handler: str, meta: dict[str, Any]) -> bool:
    if handler != "webgpt":
        return False
    if str(meta.get("failure") or "").strip().lower() != "tab_identity_preflight_failed":
        return False
    identity = meta.get("tab_identity_preflight")
    if not isinstance(identity, dict):
        return False
    return str(identity.get("error") or "").strip().lower() == "unverified_tab_id_with_multiple_chatgpt_tabs"


def _timeout_diagnostic_markers(meta: dict[str, Any]) -> dict[str, Any]:
    diagnostics = meta.get("ask_timeout_diagnostics")
    if not isinstance(diagnostics, dict):
        return {}
    markers = diagnostics.get("markers")
    return markers if isinstance(markers, dict) else {}


def _looks_browser_tool_unsupported(text: str) -> bool:
    markers = (
        "unknown tool:",
        "unknown command:",
        "unknown message type:",
        "unsupported tool",
        "unsupported command",
    )
    return any(marker in text for marker in markers)


def _looks_surf_browser_lock_timeout(text: str, commands: list[dict[str, Any]], meta: dict[str, Any]) -> bool:
    if meta.get("blocker") == SURF_BROWSER_LOCK_TIMEOUT or meta.get("failure_code") == SURF_BROWSER_LOCK_TIMEOUT:
        return True
    if "surf_browser_lock_timeout" in text or "surf_browser_lock_blocked" in text:
        return True
    if _surf_lock_blocker_details(failure=text, commands=commands, submit_meta=meta):
        return True
    return any(_surf_lock_blocker_details(failure="", commands=[command], submit_meta={}) for command in commands)


def _looks_surf_browser_connection_unavailable(text: str) -> bool:
    markers = (
        "socket connect failed",
        "socket not found",
        "surf connection closed before response",
        "native messaging host disconnected",
        "failed to connect to surf",
    )
    return any(marker in text for marker in markers)


def _browser_transport_failure_summary(
    *,
    failure_code: str,
    submit_meta: dict[str, Any],
    commands: list[dict[str, Any]],
    surf_lock_blocker: dict[str, Any],
) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "failure_code": failure_code,
        "transport_failure_kind": _transport_failure_kind(failure_code),
    }
    for key in (
        "submitted_to_chatgpt",
        "submitted_to_kimi",
        "submitted_to_claude",
        "submitted_to_gemini",
        "submitted_to_grok",
        "proof_status",
        "response_proof_status",
        "requested_tab_id",
        "controlled_tab_id",
        "controlled_tab_id_mismatch",
        "requested_url",
        "controlled_url",
        "status",
        "failure",
        "blocker",
        "cdp_probe_stderr",
        "cdp_retry_stderr",
        "stderr_log",
        "sentinel",
        "output",
        "raw_output",
        "submitted_output",
        "raw_contains_sentinel",
        "clean_contains_sentinel",
        "clean_contamination_markers",
        "raw_chars",
        "clean_chars",
        "provider_busy_cooldown_count",
        "provider_busy_retry_attempts",
        "provider_busy_cooldown_seconds",
    ):
        if key in submit_meta:
            summary[key] = submit_meta.get(key)
    identity = submit_meta.get("tab_identity_preflight")
    if isinstance(identity, dict):
        summary["tab_identity_preflight"] = identity
    if surf_lock_blocker:
        summary["surf_lock_blocker"] = surf_lock_blocker
    command_stderr = _last_nonempty_command_field(commands, "stderr_excerpt")
    if command_stderr:
        summary["last_command_stderr_excerpt"] = command_stderr
    command_stdout = _last_nonempty_command_field(commands, "stdout_excerpt")
    if command_stdout:
        summary["last_command_stdout_excerpt"] = command_stdout
    return summary


def _transport_failure_kind(failure_code: str) -> str:
    return _browser_failure_code(failure_code).transport_failure_kind or failure_code


def _last_nonempty_command_field(commands: list[dict[str, Any]], key: str) -> str:
    for command in reversed(commands):
        if not isinstance(command, dict):
            continue
        value = str(command.get(key) or "").strip()
        if value:
            return value[:4000]
    return ""


def _surf_lock_blocker_details(
    *, failure: str, commands: list[dict[str, Any]], submit_meta: dict[str, Any]
) -> dict[str, Any]:
    meta_text_fields = [
        "cdp_probe_stderr",
        "cdp_retry_stderr",
        "stderr_log",
        "error",
        "failure",
        "message",
        "blocker",
    ]
    candidates: list[str] = [failure, json.dumps(submit_meta, sort_keys=True, default=str)]
    candidates.extend(str(submit_meta.get(key) or "") for key in meta_text_fields)
    for command in commands:
        if isinstance(command, dict):
            candidates.extend(
                [
                    str(command.get("stderr_excerpt") or ""),
                    str(command.get("stdout_excerpt") or ""),
                ]
            )
    for text in candidates:
        for line in str(text).splitlines():
            if not line.startswith("SURF_BROWSER_LOCK_BLOCKED "):
                continue
            try:
                payload = json.loads(line[len("SURF_BROWSER_LOCK_BLOCKED ") :].strip())
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict) and payload.get("blocker") == SURF_BROWSER_LOCK_TIMEOUT:
                return payload
    haystack = "\n".join(candidates)
    if "timed out waiting for browser lock" not in haystack.lower():
        return {}
    owner = None
    owner_pid = str(submit_meta.get("owner_pid") or "").strip()
    owner_socket = str(submit_meta.get("owner_socket") or "").strip()
    owner_created_at = str(submit_meta.get("owner_created_at") or "").strip()
    lock_dir = str(submit_meta.get("lock_dir") or "").strip() or None
    if owner_pid or owner_socket or owner_created_at:
        owner = {
            "pid": int(owner_pid) if owner_pid.isdigit() else owner_pid or None,
            "created_at": owner_created_at or None,
            "socket": owner_socket or None,
        }
    owner_match = re.search(
        r"owner_pid=(?P<pid>\S+).*?owner_created_at=(?P<created_at>\S+).*?owner_socket=(?P<socket>\S+).*?lock_dir=(?P<lock_dir>\S+)",
        haystack,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if owner_match:
        pid_text = owner_match.group("pid").strip('",')
        owner = {
            "pid": int(pid_text) if pid_text.isdigit() else pid_text,
            "created_at": owner_match.group("created_at").strip('",'),
            "socket": owner_match.group("socket").strip('",'),
        }
        lock_dir = owner_match.group("lock_dir").strip('",')
    return {
        "schema": "surf.browser_lock_blocker.v1",
        "status": "BLOCKED",
        "blocker": SURF_BROWSER_LOCK_TIMEOUT,
        "owner": owner,
        "lock_dir": lock_dir,
        "recovery": {
            "do_not_use_no_lock_for_browser_handlers": True,
            "next_command": "wait for the owner process to finish or use a separate Surf socket/profile",
        },
    }


def _looks_tab_identity_mismatch(text: str, meta: dict[str, Any]) -> bool:
    failure = str(meta.get("failure") or "").lower()
    if "url mismatch" in failure or "tab identity" in failure:
        return True
    markers = (
        "url mismatch: expected",
        "expected_url_mismatch",
        "tab_identity_preflight_failed",
        "controlled_tab_id_mismatch",
        "invalid tab id",
        "tab not found",
        "wrong_tab",
        "requested tab",
    )
    return any(marker in text for marker in markers)


def _looks_stale_raw_capture(text: str, meta: dict[str, Any]) -> bool:
    if meta.get("stale_raw_capture") is True or meta.get("stale_capture") is True:
        return True
    markers = (
        "stale raw",
        "stale capture",
        "stale cdp",
        "old sentinel",
        "previous response",
        "prior response",
        "wrong assistant turn",
        "sentinel from an earlier",
        "current sentinel",
    )
    return any(marker in text for marker in markers)


def _looks_webgpt_unverified_clean_output(handler: str, text: str, meta: dict[str, Any]) -> bool:
    if handler != "webgpt":
        return False
    if WEBGPT_UNVERIFIED_CLEAN_OUTPUT in text:
        return True
    if str(meta.get("failure") or "") == WEBGPT_UNVERIFIED_CLEAN_OUTPUT:
        return True
    if meta.get("response_proof_status") == "response_unproven" and meta.get("raw_contains_sentinel") is True:
        controlled_tab = str(meta.get("controlled_tab_id") or "").strip()
        return not controlled_tab
    return False


def _looks_clean_output_contaminated(text: str, meta: dict[str, Any]) -> bool:
    failure = str(meta.get("failure") or "").lower()
    if BROWSER_CLEAN_OUTPUT_CONTAMINATED in text:
        return True
    if "contaminated_clean_output" in failure:
        return True
    if meta.get("raw_contains_sentinel") is True and meta.get("clean_contains_sentinel") is True:
        return True
    markers = (
        "clean output contains sentinel",
        "clean response contains sentinel",
        "contaminated clean output",
        "sentinel remained in clean output",
        "what can we tackle together?",
        "@keyframes",
        "automation-only instruction:",
        "after your complete answer, append a final line containing only this exact marker:",
        "do not print anything after that marker.",
    )
    return any(marker in text for marker in markers)


def _looks_sentinel_trailing_content(text: str, meta: dict[str, Any]) -> bool:
    if str(meta.get("failure") or "") == BROWSER_SENTINEL_TRAILING_CONTENT:
        return True
    markers = (
        "assistant response contains text after terminal sentinel",
        "text after terminal sentinel",
        "trailing text after terminal sentinel",
        "content after terminal sentinel",
    )
    return any(marker in text for marker in markers)


def _looks_browser_tab_read_timeout(text: str) -> bool:
    if BROWSER_TAB_READ_TIMEOUT in text:
        return True
    if "timed out" not in text and "timeout" not in text:
        return False
    tab_read_markers = (
        "'read', '--tab-id'",
        '"read", "--tab-id"',
        " read --tab-id",
        "run.sh', 'read'",
        "run.sh read",
        "surf read --tab-id",
        "page.text",
        "page text",
    )
    return any(marker in text for marker in tab_read_markers)


def _looks_browser_handler_timeout(text: str, commands: list[dict[str, Any]]) -> bool:
    if "[tau-worker] command timed out after" in text:
        return True
    for command in commands:
        if not isinstance(command, dict):
            continue
        if command.get("returncode") == 124:
            return True
        stderr = str(command.get("stderr_excerpt") or "").lower()
        if "[tau-worker] command timed out after" in stderr:
            return True
    return False


def _looks_browser_handler_interrupted(
    meta: dict[str, Any],
    commands: list[dict[str, Any]],
) -> bool:
    interrupted_codes = {-15, 143}
    for key in ("exit_code", "returncode"):
        try:
            if int(meta.get(key)) in interrupted_codes:
                return True
        except (TypeError, ValueError):
            pass
    for command in commands:
        if not isinstance(command, dict):
            continue
        try:
            if int(command.get("returncode")) in interrupted_codes:
                return True
        except (TypeError, ValueError):
            pass
    return False


def _provider_reported_limit_chars(text: str) -> int | None:
    """Read a size limit only when the provider actually states one.

    A packet that asserts a limit it never saw is worse than one that omits it
    (agent-skills#1077), so this returns None unless the failure text carries a
    number next to limit wording.
    """
    patterns = (
        r"maximum (?:context |prompt )?length[^0-9]{0,20}(\d{3,})",
        r"limit(?:ed)? to[^0-9]{0,20}(\d{3,})\s*(?:characters|chars|tokens)",
        r"(\d{3,})\s*(?:characters|chars|tokens)\s*(?:maximum|max|limit)",
    )
    lowered = (text or "").lower()
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return int(match.group(1))
    return None


def resolve_requested_attachments(requested: list[str], *, handler: str) -> list[str]:
    """Resolve caller-supplied evidence, failing closed on anything unusable.

    A browser lane that silently drops requested evidence still answers, from
    prose alone, and sounds just as confident (agent-skills#1062).
    """
    if not requested:
        return []
    missing = [item for item in requested if not Path(item).expanduser().is_file()]
    if missing:
        raise RuntimeError(
            "browser_attachment_missing: requested attachment(s) not readable: " + ", ".join(missing)
        )
    if handler not in ATTACH_FILE_HANDLERS:
        raise RuntimeError(
            f"browser_attachment_unsupported: handler {handler} cannot receive --attach-file evidence"
        )
    return [str(Path(item).expanduser().resolve()) for item in requested]


def _looks_browser_attachment_argument_contract_failed(text: str) -> bool:
    """Surf rejected the submit's attachment arguments before touching a browser.

    An argument-parsing refusal produces no response file, which used to surface
    as missing_sentinel and hid the real contract (agent-skills#1081).
    """
    markers = (
        "accepts --attach-files for flag parity",
        "this wrapper sends one attachment",
        "pass one local bundle",
        "supports one attachment",
    )
    return any(marker in text for marker in markers)


def _looks_environment_dependency_install_failed(text: str) -> bool:
    """The lane died installing local Python dependencies.

    Nothing about the browser or the prompt is implicated: the run never got
    far enough to drive a provider (agent-skills#1078).
    """
    install_markers = (
        "failed to install:",
        "failed to create virtual environment",
        "failed to create directory",
        "could not install packages",
        "error: externally-managed-environment",
        "no space left on device",
    )
    env_markers = (
        "dist-packages",
        "site-packages",
        "virtual environment already exists",
        "a virtual environment already exists",
        "permission denied (os error 13)",
        "permission denied:",
    )
    return any(marker in text for marker in install_markers) and any(marker in text for marker in env_markers)


def _environment_dependency_details(text: str) -> dict[str, Any]:
    """Name the wheel and the directory the install was denied, for the packet."""
    package = re.search(r"failed to install:\s*([^\s(]+)", text)
    directory = re.search(r"failed to create directory\s+([^\s:]+)", text)
    return {
        "package": package.group(1) if package else None,
        "target_directory": directory.group(1) if directory else None,
    }


def _looks_browser_composer_interaction_failed(text: str) -> bool:
    """The provider composer refused focus/typing.

    This is a UI interaction failure on the controlled tab, independent of how
    large the prompt is (agent-skills#1077: an 8288-char and a 42% smaller
    4782-char prompt failed identically on webkimi).
    """
    markers = (
        "failed to focus/type",
        "failed to focus prompt composer",
        "failed to type into",
        "prompt composer",
        "composer not found",
        "could not focus composer",
    )
    return any(marker in text for marker in markers)


def _looks_prompt_too_large_or_stalled(text: str) -> bool:
    # Bare "timeout"/"timed out" are NOT size evidence: every browser dispatch
    # command carries a --timeout flag, so those markers matched the argv of any
    # failure that reached this check and mislabelled it as a size problem
    # (agent-skills#1077). Only explicit size or stall wording counts now.
    markers = (
        # Precise stall wording only. A bare "timeout" also appears in the
        # --timeout flag of every dispatch command.
        "response timeout",
        "response timed out",
        "timed out waiting",
        "submit timed out",
        "stalled",
        "context length",
        "context_length",
        "maximum context",
        "too large",
        "too long",
        "message is too long",
        "input is too long",
        "prompt too large",
        "payload too large",
        "request entity too large",
        "413",
    )
    return any(marker in text for marker in markers)


def _looks_missing_sentinel(text: str, meta: dict[str, Any]) -> bool:
    if meta.get("raw_contains_sentinel") is False or meta.get("clean_contains_sentinel") is False:
        return True
    markers = (
        "missing sentinel",
        "sentinel missing",
        "sentinel_not_found",
        "did not emit sentinel",
        "completion marker",
        "expected sentinel",
    )
    return any(marker in text for marker in markers)


def _local_readable_bundle_paths(prompt_text: str, request_payload: dict[str, Any]) -> list[str]:
    candidates: list[str] = []
    for value in [prompt_text, str(request_payload.get("request") or "")]:
        candidates.extend(_extract_path_candidates(value))
    bundle_paths: list[str] = []
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if not path.is_absolute():
            continue
        if not path.is_file():
            continue
        if not _is_bundle_like(path):
            continue
        try:
            with path.open("rb") as handle:
                handle.read(1)
        except OSError:
            continue
        resolved = str(path.resolve())
        if resolved not in bundle_paths:
            bundle_paths.append(resolved)
    return bundle_paths


def _extract_path_candidates(text: str) -> list[str]:
    quoted = re.findall(r"['\"](/[^'\"\s]+)['\"]", text)
    bare = re.findall(r"(?<![\w:/])(/[^\s`'\"<>]+)", text)
    return [item.rstrip(").,;:]") for item in [*quoted, *bare]]


def _is_bundle_like(path: Path) -> bool:
    name = path.name.lower()
    suffixes = "".join(path.suffixes).lower()
    if any(token in name for token in ("bundle", "review", "target", "evidence", "handoff")):
        return True
    return suffixes in {
        ".bmp",
        ".gif",
        ".jpeg",
        ".jpg",
        ".md",
        ".pdf",
        ".png",
        ".txt",
        ".webp",
        ".json",
        ".jsonl",
        ".zip",
        ".tar",
        ".tar.gz",
        ".tgz",
    }


def crosstalk_tab_mismatch(bound_tab_id: str, submit_meta: dict[str, Any]) -> dict[str, Any] | None:
    """Detect a seat that captured from a tab it does not own.

    Concurrent seats share one browser; a node whose controlled tab differs from
    its bound tab has captured another seat's conversation, so its response is
    not attributable (agent-skills#1025).
    """
    bound = str(bound_tab_id or "").strip()
    controlled = str(submit_meta.get("controlled_tab_id") or "").strip()
    if not bound or not controlled or bound == controlled:
        return None
    return {
        "schema": "ask.browser_tab_crosstalk.v1",
        "bound_tab_id": bound,
        "controlled_tab_id": controlled,
        "reason": "the seat captured from a tab it does not own; the response is not attributable",
    }


def sanitize_recovery_prompt(prompt_path: Path, attachment_paths: list[str]) -> dict[str, Any]:
    """Strip bare local paths from a retry prompt unless they are attached.

    A recovery packet that echoes the failing prompt verbatim hands the operator
    a command Surf blocks as web_review_bundle_unreadable (agent-skills#1081).
    """
    try:
        text = prompt_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"sanitized": False, "reason": "prompt_unreadable", "prompt_path": str(prompt_path)}
    attached = {str(Path(item).expanduser().resolve()) for item in attachment_paths}
    unattached = [
        candidate
        for candidate in _local_path_candidates(text)
        if str(Path(candidate).expanduser().resolve()) not in attached
    ]
    if not unattached:
        return {"sanitized": False, "reason": "no_unattached_local_paths", "prompt_path": str(prompt_path)}
    sanitized_text = text
    for candidate in unattached:
        sanitized_text = sanitized_text.replace(candidate, "<local path removed: not attached>")
    sanitized_path = prompt_path.with_name("prompt.recovery.md")
    sanitized_path.write_text(sanitized_text, encoding="utf-8")
    return {
        "sanitized": True,
        "prompt_path": str(sanitized_path),
        "original_prompt_path": str(prompt_path),
        "removed_paths": unattached,
    }


def tab_still_open(surf_run: str, tab_id: str) -> bool | None:
    """None when liveness cannot be determined; False only on a proven miss."""
    if not tab_id or not surf_run or not Path(surf_run).is_file():
        return None
    try:
        result = _run_cmd([str(surf_run), "tab.list", "--json"], timeout=60, cwd=Path.cwd())
    except (OSError, RuntimeError):
        return None
    if result.returncode != 0:
        return None
    tabs = _parse_json_array_or_tabs(result.stdout)
    if not isinstance(tabs, list):
        return None
    return any(str(item.get("id")) == str(tab_id) for item in tabs if isinstance(item, dict))


def surf_lock_owner() -> dict[str, Any] | None:
    """Name whoever holds the shared Surf browser lock, for a stalled receipt."""
    for lock_dir in sorted(Path("/tmp").glob("surf-lock-*")):
        owner = lock_dir / "owner.json"
        if not owner.is_file():
            continue
        try:
            payload = json.loads(owner.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pid = payload.get("pid")
        payload["lock_dir"] = str(lock_dir)
        payload["owner_alive"] = Path(f"/proc/{pid}").exists() if pid else None
        return payload
    return None


@dataclass(frozen=True)
class HandoffContract:
    """Deterministic seam contract for tau.agent_handoff.v1 emissions.

    validate() raises SeamContractError on violation: the worker exits
    non-zero and Tau fails the node closed, so a drifting producer cannot
    hand malformed evidence downstream and have it ignored.
    """

    schema: str
    goal: dict
    result: dict

    REQUIRED_RESULT_KEYS = ("status", "summary", "evidence")

    def validate(self) -> None:
        problems: list[str] = []
        if self.schema != "tau.agent_handoff.v1":
            problems.append(f"schema must be tau.agent_handoff.v1, got {self.schema!r}")
        if not isinstance(self.goal, dict) or not self.goal.get("goal_hash"):
            problems.append("goal.goal_hash is required")
        if not isinstance(self.result, dict):
            problems.append("result must be an object")
        else:
            for key in self.REQUIRED_RESULT_KEYS:
                if key not in self.result:
                    problems.append(f"result.{key} is required")
            for index, item in enumerate(self.result.get("evidence") or []):
                if isinstance(item, dict) and not item.get("goal_hash"):
                    problems.append(f"evidence[{index}] missing goal_hash")
        if problems:
            raise SeamContractError("tau.agent_handoff.v1", problems)


@dataclass(frozen=True)
class RecoveryPacketContract:
    """Seam contract for browser recovery packets: no unrunnable guidance."""

    schema: str
    failure_code: str
    next_command: list

    def validate(self) -> None:
        problems: list[str] = []
        if not self.schema:
            problems.append("schema is required")
        if not self.failure_code:
            problems.append("failure_code is required")
        if not isinstance(self.next_command, list):
            problems.append("next_command must be a list")
        if problems:
            raise SeamContractError("ask.browser_recovery_packet", problems)


class SeamContractError(RuntimeError):
    def __init__(self, kind: str, problems: list[str]) -> None:
        self.kind = kind
        self.problems = problems
        super().__init__(f"seam {kind!r} violated: {problems}")


_SURF_CLI_SOURCE_CACHE: dict[str, str] = {}


def _validate_next_command_runnable(
    next_command: list[str],
) -> tuple[list[str], dict[str, Any] | None]:
    """Refuse to emit a next_command the operator cannot actually run.

    Two checks, both derived from live failures: argv[0] must be an existing
    executable (a packet once pointed at a path that was never created), and a
    surf tool name must exist in the installed CLI (a packet once named
    gemini.extract, which the CLI does not implement — the operator burned a
    lane discovering that). A rejected command is preserved with its reason so
    the producer bug is visible instead of laundered into an empty list.
    """
    if not next_command:
        return next_command, None
    argv0 = Path(str(next_command[0]))
    if not argv0.is_file() or not os.access(argv0, os.X_OK):
        return [], {
            "command": next_command,
            "reason": f"argv[0] is not an executable file: {argv0}",
        }
    if argv0.name == "run.sh" and "surf" in str(argv0) and len(next_command) > 1:
        tool = str(next_command[1])
        if "." in tool and (argv0.parent / "vendor" / "surf-cli").is_dir():
            surf_root = argv0.parent
            source = _SURF_CLI_SOURCE_CACHE.get(str(surf_root))
            if source is None:
                source = ""
                candidates = [
                    surf_root / "run.sh",
                    surf_root / "vendor" / "surf-cli" / "native" / "cli.cjs",
                    surf_root / "vendor" / "surf-cli" / "native" / "host-helpers.cjs",
                ]
                candidates.extend(sorted((surf_root / "scripts").glob("*.sh")) if (surf_root / "scripts").is_dir() else [])
                for candidate in candidates:
                    if candidate.is_file():
                        source += candidate.read_text(encoding="utf-8", errors="replace")
                _SURF_CLI_SOURCE_CACHE[str(surf_root)] = source
            if source and tool not in source:
                return [], {
                    "command": next_command,
                    "reason": f"surf tool {tool!r} not found in the installed surf skill",
                }
    return next_command, None


def _recovery_next_command(
    args: argparse.Namespace,
    *,
    request_payload: dict[str, Any],
    failure_code: str,
    bundle_path: str,
    can_attach: bool,
    browser_oracle: dict[str, Any],
    submit_meta: dict[str, Any],
    response_path: Path,
    raw_path: Path,
    meta_path: Path,
    prompt_path: Path,
) -> list[str]:
    def append_browser_identity(command: list[str]) -> None:
        tab_id = ""
        if isinstance(browser_oracle, dict):
            tab_id = str(browser_oracle.get("tab_id") or browser_oracle.get("controlled_tab_id") or "").strip()
        if not tab_id:
            tab_id = _tab_id_from_commands(args)
        url = str(
            browser_oracle.get("conversation_url")
            or submit_meta.get("current_url")
            or submit_meta.get("requested_url")
            or ""
        ).strip()
        if tab_id:
            command.extend(["--tab-id", tab_id])
        if url:
            command.extend(["--expect-url" if str(args.handler) == "webgpt" and tab_id else "--url", url])

    if failure_code in {
        BROWSER_ATTACHMENT_UNAVAILABLE,
        BROWSER_SENTINEL_TRAILING_CONTENT,
        WEBGPT_UNVERIFIED_CLEAN_OUTPUT,
    }:
        return []
    if failure_code == WEBGPT_BINDING_STALE_BLOCKER:
        stale = _webgpt_stale_binding_details(submit_meta)
        project = str(args.browser_oracle_project or browser_oracle.get("project") or args.handler)
        tab_id = str(stale.get("tab_id") or browser_oracle.get("tab_id") or "")
        live_url = str(stale.get("live_url") or "")
        command = [
            str(args.browser_oracle_run),
            "bind",
            project,
            "--backend",
            HANDLER_BACKENDS[str(args.handler)],
        ]
        if tab_id:
            command.extend(["--tab-id", tab_id])
        if live_url:
            command.extend(["--url", live_url])
        command.extend(["--manual", "--json"])
        return command
    # Both providers end a thread the same way — the round has to move into a
    # fresh conversation, so they share one resubmit command.
    if failure_code in {WEBGPT_CONVERSATION_FULL_BLOCKER, KIMI_CONVERSATION_TOO_LONG_BLOCKER}:
        command = [
            str(args.surf_run),
            HANDLER_SUBMIT_COMMANDS[str(args.handler)],
            "--input",
            str(prompt_path),
            "--output",
            str(response_path.with_name("response.fresh-conversation.md")),
            "--raw-output",
            str(raw_path.with_name("response.fresh-conversation.raw.md")),
            "--meta-output",
            str(meta_path.with_name("response.fresh-conversation.meta.json")),
            "--timeout",
            str(args.timeout),
            "--stable-polls",
            str(args.stable_polls),
            "--stable-stall-ms",
            _browser_stable_stall_ms(),
            "--create-tab",
        ]
        # Same reasoning-model stall guard as the primary submit path: a quiet
        # model is not a stalled one, and --timeout already bounds the wait.
        _append_browser_lock_timeout(command, args)
        # kimi.submit takes no --project; passing it fails argument parsing
        # before any browser work, which would hide the real blocker.
        if args.browser_oracle_project and failure_code == WEBGPT_CONVERSATION_FULL_BLOCKER:
            command.extend(["--project", str(args.browser_oracle_project)])
        # The fresh chat has none of the prior thread's context, so the round's
        # own attachment has to be re-sent with it.
        for attachment_path in list(getattr(args, "attach_files", []) or []):
            command.extend(["--attach-file", str(attachment_path)])
        if args.no_activate:
            command.append("--no-activate")
        return command
    if failure_code == BROWSER_TAB_READ_TIMEOUT:
        project = str(args.browser_oracle_project or browser_oracle.get("project") or args.handler)
        url = str(
            browser_oracle.get("conversation_url")
            or submit_meta.get("current_url")
            or submit_meta.get("requested_url")
            or ""
        ).strip()
        command = [
            str(args.browser_oracle_run),
            "open-bind",
            project,
            "--backend",
            HANDLER_BACKENDS[str(args.handler)],
        ]
        if url:
            command.extend(["--url", url])
        command.extend(["--manual", "--json"])
        return command
    if failure_code == BROWSER_SUBMIT_NOT_ACCEPTED:
        url = str(
            browser_oracle.get("conversation_url")
            or submit_meta.get("current_url")
            or submit_meta.get("requested_url")
            or ""
        ).strip()
        if _submit_not_accepted_can_retry_same_identity(str(args.handler), submit_meta):
            command = [
                str(args.surf_run),
                HANDLER_SUBMIT_COMMANDS[str(args.handler)],
                "--input",
                str(prompt_path),
                "--output",
                str(response_path.with_name("response.identity-retry.md")),
                "--raw-output",
                str(raw_path.with_name("response.identity-retry.raw.md")),
                "--meta-output",
                str(meta_path.with_name("response.identity-retry.meta.json")),
                "--timeout",
                str(args.timeout),
                "--stable-polls",
                str(args.stable_polls),
                "--stable-stall-ms",
                _browser_stable_stall_ms(),
            ]
            _append_browser_lock_timeout(command, args)
            append_browser_identity(command)
            if not any(item in {"--tab-id", "--url"} for item in command):
                project = str(args.browser_oracle_project or browser_oracle.get("project") or args.handler)
                command.extend(["--project", project])
            if args.no_activate:
                command.append("--no-activate")
            return command
        command = [
            str(args.browser_oracle_run),
            "open-bind",
            str(args.browser_oracle_project or browser_oracle.get("project") or args.handler),
            "--backend",
            HANDLER_BACKENDS[str(args.handler)],
        ]
        if url:
            command.extend(["--url", url])
        command.extend(["--manual", "--json"])
        return command
    if failure_code == BROWSER_PROVIDER_SETUP_FAILED:
        command = [
            str(args.surf_run),
            HANDLER_SUBMIT_COMMANDS[str(args.handler)],
            "--input",
            str(prompt_path),
            "--output",
            str(response_path.with_name("response.after-provider-setup.md")),
            "--raw-output",
            str(raw_path.with_name("response.after-provider-setup.raw.md")),
            "--meta-output",
            str(meta_path.with_name("response.after-provider-setup.meta.json")),
            "--timeout",
            str(args.timeout),
            "--stable-polls",
            str(args.stable_polls),
            "--stable-stall-ms",
            _browser_stable_stall_ms(),
        ]
        _append_browser_lock_timeout(command, args)
        tab_id = str(browser_oracle.get("tab_id") or browser_oracle.get("controlled_tab_id") or "").strip()
        url = str(browser_oracle.get("conversation_url") or submit_meta.get("requested_url") or "").strip()
        if tab_id:
            command.extend(["--tab-id", tab_id])
        if url:
            command.extend(["--expect-url" if str(args.handler) == "webgpt" else "--url", url])
        if args.no_activate:
            command.append("--no-activate")
        return command
    if failure_code in {SURF_BROWSER_LOCK_TIMEOUT, SURF_BROWSER_CONNECTION_UNAVAILABLE}:
        command = [
            str(args.surf_run),
            HANDLER_SUBMIT_COMMANDS[str(args.handler)],
            "--input",
            str(prompt_path),
            "--output",
            str(response_path.with_name("response.after-lock.md")),
            "--raw-output",
            str(raw_path.with_name("response.after-lock.raw.md")),
            "--meta-output",
            str(meta_path.with_name("response.after-lock.meta.json")),
            "--timeout",
            str(args.timeout),
            "--stable-polls",
            str(args.stable_polls),
            "--stable-stall-ms",
            _browser_stable_stall_ms(),
        ]
        _append_browser_lock_timeout(command, args)
        tab_id = str(browser_oracle.get("tab_id") or browser_oracle.get("controlled_tab_id") or "").strip()
        url = str(browser_oracle.get("conversation_url") or "").strip()
        if tab_id:
            command.extend(["--tab-id", tab_id])
        if url:
            command.extend(["--expect-url" if str(args.handler) == "webgpt" else "--url", url])
        if args.no_activate:
            command.append("--no-activate")
        return command
    extract_command = _browser_provider_extract_command(
        args,
        failure_code=failure_code,
        browser_oracle=browser_oracle,
        submit_meta=submit_meta,
        response_path=response_path,
        raw_path=raw_path,
        meta_path=meta_path,
    )
    if extract_command:
        return extract_command
    policy = _payload_policy(str(args.handler))
    inline_retry_paths = _inline_text_bundle_paths([bundle_path]) if bundle_path and policy.inline_text_attachments else []
    if inline_retry_paths:
        retry_prompt = prompt_path.with_name("retry-with-local-bundle.md")
        bundle = Path(inline_retry_paths[0])
        bundle_text = bundle.read_text(encoding="utf-8", errors="replace")
        retry_prompt.write_text(
            "\n".join(
                [
                    "Use the inlined local bundle as the source of truth.",
                    "Do not rely on bare private GitHub URLs or local paths not present in this prompt.",
                    "Answer the original request using the inlined bundle and state any remaining access gaps.",
                    "",
                    "Original request:",
                    str(request_payload.get("request") or ""),
                    "",
                    f"Browser failure class that triggered this retry packet: {failure_code}",
                    "",
                    f"### INLINE_1: {bundle.name}",
                    "",
                    "```text",
                    bundle_text.rstrip(),
                    "```",
                    "",
                    "Use INLINE_1 as source material; it replaces local filesystem attachment paths for this provider.",
                ]
            ),
            encoding="utf-8",
        )
        command = [
            str(args.surf_run),
            HANDLER_SUBMIT_COMMANDS[str(args.handler)],
            "--input",
            str(retry_prompt),
            "--output",
            str(response_path.with_name("response.retry.md")),
            "--raw-output",
            str(raw_path.with_name("response.retry.raw.md")),
            "--meta-output",
            str(meta_path.with_name("response.retry.meta.json")),
            "--timeout",
            str(args.timeout),
            "--stable-polls",
            str(args.stable_polls),
            "--stable-stall-ms",
            _browser_stable_stall_ms(),
        ]
        _append_browser_lock_timeout(command, args)
        append_browser_identity(command)
        if args.no_activate:
            command.append("--no-activate")
        return command
    if bundle_path and can_attach:
        retry_prompt = prompt_path.with_name("retry-with-local-bundle.md")
        retry_prompt.write_text(
            "\n".join(
                [
                    "Use the attached local bundle as the source of truth.",
                    "Do not rely on bare private GitHub URLs or local paths not present in the attachment.",
                    "Answer the original request using the attached bundle and state any remaining access gaps.",
                    "",
                    "Original request:",
                    str(request_payload.get("request") or ""),
                    "",
                    f"Browser failure class that triggered this retry packet: {failure_code}",
                ]
            ),
            encoding="utf-8",
        )
        command = [
            str(args.surf_run),
            HANDLER_SUBMIT_COMMANDS[str(args.handler)],
            "--input",
            str(retry_prompt),
            "--output",
            str(response_path.with_name("response.retry.md")),
            "--raw-output",
            str(raw_path.with_name("response.retry.raw.md")),
            "--meta-output",
            str(meta_path.with_name("response.retry.meta.json")),
            "--timeout",
            str(args.timeout),
            "--stable-polls",
            str(args.stable_polls),
            "--stable-stall-ms",
            _browser_stable_stall_ms(),
            "--attach-file",
            bundle_path,
        ]
        _append_browser_lock_timeout(command, args)
        append_browser_identity(command)
        if args.no_activate:
            command.append("--no-activate")
        return command
    ask_root = Path(args.surf_run).resolve().parent.parent / "ask"
    command = [
        str(ask_root / "run.sh"),
        "tau-dag",
        str(request_payload.get("request") or ""),
        "--repo",
        str(request_payload.get("repo") or "local/ask"),
        "--target",
        str(request_payload.get("target") or args.node_id),
        "--handler",
        str(args.handler),
        "--topology",
        str(args.topology),
        "--execute",
        "--json",
    ]
    browser_lock_timeout = int(getattr(args, "browser_lock_timeout", 0) or 0)
    if browser_lock_timeout > 0:
        command.extend(["--browser-lock-timeout", str(browser_lock_timeout)])
    if str(args.browser_oracle_project or ""):
        command.extend(["--handler-project", f"{args.handler}={args.browser_oracle_project}"])
    return command


def _tab_id_from_commands(args: argparse.Namespace) -> str:
    # The primary receipt keeps browser-oracle resolution separately; tests and
    # recovery packets still need a deterministic fallback when only args exist.
    return ""


#: Failure classes where retrying inside the lane cannot help: the provider
#: itself refused, so another attempt is spray-and-pray against a wall.
PROVIDER_HOSTS = {
    "webgpt": "chatgpt.com",
    "webclaude": "claude.ai",
    "webkimi": "kimi.com",
    "webgemini": "gemini.google.com",
    "webgrok": "grok.com",
    "webdeepseek": "chat.deepseek.com",
}

# One JS payload, evaluated in the real authenticated tab. Everything the
# ladder needs to pick a rung is read here rather than guessed at: whether the
# page is a live provider surface, whether it is still generating, whether a
# rate-limit or error banner is on screen, and whether the round's sentinel is
# already rendered (the response arrived and only capture missed it).
_LANE_STATE_JS = """
const body = document.body ? document.body.innerText : '';
// Match on LANGUAGE, not on class names: provider markup reuses 'limit'
// and 'Toast' for ordinary chrome, and a class-only match reported the
// reasoning-level label 'High' as an error banner (observed 2026-08-04).
const BLOCKING = /(rate ?limit|too many requests|usage (limit|cap)|try again (in|later)|unavailable|out of capacity|at capacity|upgrade to continue|you've reached|something went wrong|error occurred)/i;
const banner = Array.from(document.querySelectorAll('[role=alert],[class*=error],[class*=limit],[class*=Toast]'))
  .map(e => (e.innerText || '').trim())
  .filter(t => t.length > 8 && BLOCKING.test(t))
  .slice(0, 3);
return JSON.stringify({
  title: document.title,
  url: location.href,
  visibility: document.visibilityState,
  body_chars: body.length,
  body_tail: body.slice(-600),
  composer_present: !!document.querySelector(
    'textarea,[contenteditable=true],div[role=textbox]'),
  generating: /stop (answering|generating|streaming)/i.test(body)
    || !!document.querySelector('[aria-label*="Stop" i],[data-testid*="stop" i]'),
  banners: banner,
});
"""


def _probe_lane_state(
    args: argparse.Namespace,
    *,
    tab_id: str,
    sentinel: str,
) -> list[dict[str, Any]]:
    """Run the fixed provider-failure diagnostic series against the live tab.

    Ordered, deterministic, and identical for every handler and every failure
    code. Each rung records PASS/FAIL/SKIPPED with the evidence that decided
    it, so a lane failure always carries live state instead of an agent's
    theory about live state. Checks are ordered cheapest-and-most-fundamental
    first; a FAIL short-circuits the rungs that depend on it, because "tab is
    gone" makes "composer present" meaningless rather than false.
    """
    surf_run = str(getattr(args, "surf_run", "") or "")
    handler = str(args.handler)
    checks: list[dict[str, Any]] = []

    def record(name: str, status: str, **evidence: Any) -> None:
        checks.append({"check": name, "status": status, **evidence})

    if not surf_run:
        record("surf_transport", "SKIPPED", reason="no surf_run configured")
        return checks

    cwd = Path(surf_run).parent
    listing = _run_cmd([surf_run, "tab.list", "--json"], cwd=cwd, timeout=60)
    if listing.returncode != 0:
        record(
            "surf_transport",
            "FAIL",
            returncode=listing.returncode,
            stderr_excerpt=(listing.stderr or "")[-300:],
        )
        return checks
    record("surf_transport", "PASS")

    tabs = _parse_json_array_or_tabs(listing.stdout)
    tabs = tabs if isinstance(tabs, list) else []
    if not tab_id:
        record("tab_identity", "SKIPPED", reason="lane never recorded a controlled tab id")
        return checks
    tab = next(
        (t for t in tabs if isinstance(t, dict) and str(t.get("id") or "") == str(tab_id)),
        None,
    )
    if tab is None:
        # An EMPTY listing proves nothing: a real browser always has tabs, so
        # an empty result means the listing itself did not answer. Calling
        # that "vanished" would demote provider_extract on no evidence and
        # throw away a free recovery.
        record(
            "tab_identity",
            "FAIL" if tabs else "SKIPPED",
            tab_id=tab_id,
            reason=(
                "controlled tab is no longer open"
                if tabs
                else "tab listing returned no tabs; absence is unproven"
            ),
            open_tab_ids=[str(t.get("id")) for t in tabs if isinstance(t, dict)][:20],
        )
        return checks
    live_url = str(tab.get("url") or "")
    record("tab_identity", "PASS", tab_id=tab_id, url=live_url, title=str(tab.get("title") or ""))

    host = PROVIDER_HOSTS.get(handler, "")
    if not host:
        record("provider_url", "SKIPPED", reason=f"no known host for handler {handler!r}")
    elif host in live_url:
        record("provider_url", "PASS", host=host, url=live_url)
    else:
        record(
            "provider_url",
            "FAIL",
            host=host,
            url=live_url,
            reason="controlled tab drifted off the provider surface",
        )

    state_cmd = [surf_run, "js", _LANE_STATE_JS, "--tab-id", str(tab_id), "--no-activate"]
    state_result = _run_cmd(state_cmd, cwd=cwd, timeout=90)
    if state_result.returncode != 0:
        record(
            "page_state",
            "FAIL",
            returncode=state_result.returncode,
            stderr_excerpt=(state_result.stderr or "")[-300:],
            reason="could not evaluate JS in the controlled tab",
        )
        return checks
    state: dict[str, Any] = {}
    raw = (state_result.stdout or "").strip()
    for candidate in (raw, raw.strip('"').replace('\\"', '"').replace("\\n", "\n")):
        try:
            loaded = json.loads(candidate)
            if isinstance(loaded, str):
                loaded = json.loads(loaded)
            if isinstance(loaded, dict):
                state = loaded
                break
        except (ValueError, TypeError):
            continue
    if not state:
        record("page_state", "FAIL", reason="page state was not decodable JSON", stdout_excerpt=raw[:300])
        return checks
    record(
        "page_state",
        "PASS",
        visibility=state.get("visibility"),
        body_chars=state.get("body_chars"),
        composer_present=state.get("composer_present"),
        generating=state.get("generating"),
    )
    record(
        "composer_present",
        "PASS" if state.get("composer_present") else "FAIL",
        reason="" if state.get("composer_present") else "no composer element; page is not a usable chat surface",
    )
    banners = [b for b in (state.get("banners") or []) if isinstance(b, str)]
    record(
        "provider_banner",
        "FAIL" if banners else "PASS",
        banners=banners[:3],
        reason="provider surfaced an error/limit banner" if banners else "",
    )
    if not sentinel:
        record("sentinel_rendered", "SKIPPED", reason="round has no sentinel to look for")
    else:
        tail = str(state.get("body_tail") or "")
        found = sentinel in tail
        record(
            "sentinel_rendered",
            "PASS" if found else "FAIL",
            sentinel=sentinel,
            reason=(
                "response is already rendered; capture missed its window"
                if found
                else "sentinel absent from the visible page tail"
            ),
            still_generating=state.get("generating"),
        )
    return checks


def _lane_diagnostics(
    args: argparse.Namespace,
    *,
    failure_code: str,
    submit_meta: dict[str, Any],
    browser_oracle: dict[str, Any],
    sentinel: str,
) -> dict[str, Any]:
    """Live-state diagnostics for a failed lane, with a derived diagnosis.

    Runs for EVERY browser lane failure, including the ones the recovery
    ladder refuses to retry. A hopeless failure code still deserves evidence:
    that is precisely the case where the temptation is to theorise about why
    the provider said no.
    """
    tab_id = str(
        submit_meta.get("controlled_tab_id")
        or submit_meta.get("requested_tab_id")
        or browser_oracle.get("controlled_tab_id")
        or browser_oracle.get("tab_id")
        or ""
    ).strip()
    checks = _probe_lane_state(args, tab_id=tab_id, sentinel=sentinel)
    by_name = {str(c.get("check")): c for c in checks}

    def failed(name: str) -> bool:
        return str(by_name.get(name, {}).get("status")) == "FAIL"

    # Deterministic diagnosis: first matching rule wins, most fundamental
    # first. This is a lookup, not a judgement call, so two readers of the
    # same checks always reach the same conclusion.
    if failed("surf_transport"):
        diagnosis = "surf_transport_down"
    elif failed("tab_identity"):
        diagnosis = "controlled_tab_vanished"
    elif failed("provider_url"):
        diagnosis = "tab_drifted_off_provider"
    elif failed("page_state"):
        diagnosis = "tab_unresponsive_to_js"
    elif by_name.get("sentinel_rendered", {}).get("status") == "PASS":
        diagnosis = "response_rendered_capture_missed"
    elif by_name.get("sentinel_rendered", {}).get("still_generating") is True:
        diagnosis = "provider_still_generating_at_timeout"
    elif failed("provider_banner"):
        diagnosis = "provider_banner_blocked"
    elif failed("composer_present"):
        diagnosis = "no_usable_chat_surface"
    else:
        diagnosis = "no_live_defect_observed"
    return {
        "schema": "ask.lane_diagnostics.v1",
        "handler": str(args.handler),
        "node_id": str(args.node_id),
        "failure_code": failure_code,
        "tab_id": tab_id,
        "checks": checks,
        "diagnosis": diagnosis,
    }


LANE_RECOVERY_HOPELESS = frozenset(
    {
        BROWSER_HANDLER_INTERRUPTED,
        BROWSER_PROVIDER_RATE_LIMITED,
        "grok_provider_rate_limited",
        "browser_provider_capacity_busy",
    }
)


def _lane_recovery_actions(
    args: argparse.Namespace,
    *,
    failure_code: str,
    browser_oracle: dict[str, Any],
    submit_meta: dict[str, Any],
    response_path: Path,
    raw_path: Path,
    meta_path: Path,
    packet_next_command: list[str],
) -> list[dict[str, Any]]:
    """Ordered, escalating recovery actions for one failed browser lane.

    Every entry is a DIFFERENT evidence-derived action, never the same command
    twice: repeating an identical attempt is spray-and-pray. The order encodes
    what actually recovered lanes in production:

    1. provider extract - the response is usually already rendered in the tab
       and only the capture missed its window.
    2. foreground the tab, then extract again - Chrome virtualizes background
       tabs, and CDP evaluation against them times out; foregrounding made an
       identical extract succeed in seconds (observed 2026-08-01, webgpt and
       webgemini seats).
    3. the recovery packet's own next_command - resubmit or rebind, already
       computed per failure class.
    """
    actions: list[dict[str, Any]] = []
    extract = _browser_provider_extract_command(
        args,
        failure_code=failure_code,
        browser_oracle=browser_oracle,
        submit_meta=submit_meta,
        response_path=response_path,
        raw_path=raw_path,
        meta_path=meta_path,
    )
    tab_id = str(
        submit_meta.get("controlled_tab_id")
        or submit_meta.get("requested_tab_id")
        or browser_oracle.get("controlled_tab_id")
        or browser_oracle.get("tab_id")
        or ""
    ).strip()
    if extract:
        actions.append({"action": "provider_extract", "command": extract})
        if tab_id:
            actions.append(
                {
                    "action": "foreground_tab_then_extract",
                    "command": extract,
                    "pre_command": [str(args.surf_run), "tab.switch", tab_id],
                }
            )
    if packet_next_command:
        actions.append({"action": "packet_next_command", "command": list(packet_next_command)})
    return actions


def _lane_recovery_succeeded(meta_path: Path, output_path: Path, sentinel: str) -> bool:
    """A recovery counts only when it produced sentinel-bearing provider text."""
    meta = _read_json(meta_path) if meta_path.is_file() else None
    if isinstance(meta, dict) and meta.get("raw_contains_sentinel") is True:
        return True
    if sentinel and output_path.is_file():
        try:
            return sentinel in output_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
    return False


def _ladder_order_for_diagnosis(diagnosis: str) -> list[str]:
    """Rung priority implied by live state, most-likely-to-work first.

    The default order is a prior; a diagnosis is evidence and outranks it.
    Re-submitting to a tab whose response is already rendered wastes the
    provider round that extraction would have recovered for free.
    """
    return {
        "response_rendered_capture_missed": ["provider_extract", "foreground_tab_then_extract"],
        "provider_still_generating_at_timeout": ["foreground_tab_then_extract", "provider_extract"],
        "tab_unresponsive_to_js": ["foreground_tab_then_extract", "provider_extract"],
        "controlled_tab_vanished": ["packet_next_command"],
        "tab_drifted_off_provider": ["packet_next_command"],
        "no_usable_chat_surface": ["packet_next_command"],
    }.get(diagnosis, [])


def _attempt_lane_recovery(
    args: argparse.Namespace,
    *,
    recovery_packet: dict[str, Any],
    browser_oracle: dict[str, Any],
    submit_meta: dict[str, Any],
    response_path: Path,
    raw_path: Path,
    meta_path: Path,
    artifact_dir: Path,
    deadline: float,
) -> dict[str, Any]:
    """Work a failed browser lane until it yields proof or the ladder runs out.

    Assume the first attempt failed for a reason that has probably changed
    under us (provider DOM, tab virtualization, stale binding). Each rung is a
    distinct diagnosis-driven action whose result is verified by the same
    sentinel contract the original attempt had to satisfy.
    """
    failure_code = str(recovery_packet.get("failure_code") or "")
    receipt: dict[str, Any] = {
        "schema": "ask.lane_recovery.v1",
        "handler": str(args.handler),
        "node_id": str(args.node_id),
        "initial_failure_code": failure_code,
        "attempts": [],
        "recovered": False,
    }
    if failure_code in LANE_RECOVERY_HOPELESS:
        reason = (
            "the browser handler was interrupted; in-run recovery would outlive the cancelled Ask run"
            if failure_code == BROWSER_HANDLER_INTERRUPTED
            else f"{failure_code} is provider-side; retrying cannot change it"
        )
        receipt["skipped_reason"] = reason
        return receipt
    heartbeat_path = meta_path.parent / "webgpt_heartbeat.json"
    heartbeat = _read_json(heartbeat_path) if heartbeat_path.is_file() else None
    sentinel = str(
        submit_meta.get("sentinel")
        or (heartbeat.get("sentinel") if isinstance(heartbeat, dict) else "")
        or ""
    ).strip()
    actions = _lane_recovery_actions(
        args,
        failure_code=failure_code,
        browser_oracle=browser_oracle,
        submit_meta=submit_meta,
        response_path=response_path,
        raw_path=raw_path,
        meta_path=meta_path,
        packet_next_command=list(recovery_packet.get("next_command") or []),
    )
    if not actions:
        receipt["skipped_reason"] = "no evidence-derived recovery action available"
        return receipt
    diagnosis = str((recovery_packet.get("lane_diagnostics") or {}).get("diagnosis") or "")
    preferred = _ladder_order_for_diagnosis(diagnosis)
    if preferred:
        rank = {name: i for i, name in enumerate(preferred)}
        actions.sort(key=lambda a: rank.get(str(a.get("action")), len(rank)))
        receipt["ladder_order_source"] = diagnosis
        receipt["ladder_order"] = [str(a.get("action")) for a in actions]
    out_path = response_path.with_name("response.recovered.md")
    out_raw = raw_path.with_name("response.recovered.raw.md")
    out_meta = meta_path.with_name("response.recovered.meta.json")
    for index, action in enumerate(actions, start=1):
        remaining = int(deadline - time.time())
        if remaining < 30:
            receipt["attempts"].append(
                {"attempt": index, "action": action["action"], "skipped": "recovery_budget_exhausted"}
            )
            break
        command = list(action["command"])
        for flag, value in (("--output", out_path), ("--raw-output", out_raw), ("--meta-output", out_meta)):
            if flag in command:
                command[command.index(flag) + 1] = str(value)
        entry: dict[str, Any] = {"attempt": index, "action": action["action"], "command": command}
        pre = action.get("pre_command")
        if pre:
            pre_result = _run_cmd(list(pre), cwd=artifact_dir, timeout=min(120, remaining))
            entry["pre_command"] = list(pre)
            entry["pre_returncode"] = pre_result.returncode
            time.sleep(3)
        result = _run_cmd(command, cwd=artifact_dir, timeout=max(30, min(remaining - 10, 900)))
        entry["returncode"] = result.returncode
        entry["stderr_excerpt"] = (result.stderr or "")[-400:]
        if _lane_recovery_succeeded(out_meta, out_raw, sentinel):
            entry["recovered"] = True
            receipt["attempts"].append(entry)
            receipt["recovered"] = True
            receipt["recovered_by"] = action["action"]
            receipt["response_path"] = str(out_path if out_path.is_file() else out_raw)
            return receipt
        entry["recovered"] = False
        receipt["attempts"].append(entry)
    return receipt


def _browser_provider_extract_command(
    args: argparse.Namespace,
    *,
    failure_code: str,
    browser_oracle: dict[str, Any],
    submit_meta: dict[str, Any],
    response_path: Path,
    raw_path: Path,
    meta_path: Path,
) -> list[str]:
    """Return a provider-owned extraction command, never a generic page read."""
    handler = str(args.handler)
    extract_command = HANDLER_EXTRACT_COMMANDS.get(handler)
    if not extract_command:
        return []
    if failure_code not in {MISSING_SENTINEL, BROWSER_HANDLER_TIMEOUT}:
        return []
    # A submit killed at the worker timeout never writes its final meta; the
    # heartbeat is the durable record of the round's sentinel and acceptance.
    heartbeat_path = meta_path.parent / "webgpt_heartbeat.json"
    heartbeat: dict[str, Any] = {}
    if heartbeat_path.is_file():
        loaded = _read_json(heartbeat_path)
        if isinstance(loaded, dict):
            heartbeat = loaded
    sentinel = str(submit_meta.get("sentinel") or heartbeat.get("sentinel") or "").strip()
    if not sentinel:
        return []
    submitted_field = f"submitted_to_{HANDLER_BACKENDS.get(handler, handler).replace('web', '')}"
    submitted = submit_meta.get(submitted_field) is True
    if handler == "webgpt":
        submitted = submitted or submit_meta.get("submitted_to_chatgpt") is True
    if handler == "webgrok":
        submitted = submitted or submit_meta.get("submitted_to_grok") is True
    if not submitted and heartbeat.get("submitted_at"):
        # A submit killed at the worker timeout leaves meta status "failed"
        # even when the prompt went in; the heartbeat's submitted_at is the
        # durable acceptance proof in that case.
        submitted = True
    if not submitted and str(submit_meta.get("status") or "") != "missing_sentinel":
        return []
    tab_id = str(
        submit_meta.get("controlled_tab_id")
        or submit_meta.get("requested_tab_id")
        or browser_oracle.get("controlled_tab_id")
        or browser_oracle.get("tab_id")
        or ""
    ).strip()
    if not tab_id:
        return []
    command = [
        str(args.surf_run),
        extract_command,
        "--tab-id",
        tab_id,
        "--sentinel",
        sentinel,
        "--output",
        str(response_path.with_name("response.extract.md")),
        "--raw-output",
        str(raw_path.with_name("response.extract.raw.md")),
        "--meta-output",
        str(meta_path.with_name("response.extract.meta.json")),
        "--timeout",
        str(args.timeout),
    ]
    if handler in HANDLER_EXTRACT_WAIT_SUPPORTED:
        command.extend(["--wait", "--stable-polls", str(args.stable_polls)])
    return command


def _recovery_reason(failure_code: str) -> str:
    return _browser_failure_code(failure_code).reason


def _auto_retry_blocked_reason(
    *, failure_code: str, bundle_paths: list[str], can_attach: bool
) -> str:
    failure_meta = _browser_failure_code(failure_code)
    if failure_meta.auto_retry_blocked_reason:
        return failure_meta.auto_retry_blocked_reason
    if not bundle_paths:
        return "missing_local_readable_bundle"
    if not can_attach:
        return "handler_transport_does_not_support_attach_file"
    return "unknown"


def _fallback_instruction(failure_code: str, *, has_bundle: bool, can_attach: bool, handler: str) -> str:
    payload_policy = _payload_policy(handler)
    if failure_code == WEBGPT_CONVERSATION_FULL_BLOCKER:
        return (
            "Do not wait or retry in the same conversation. Rebind browser-oracle to a fresh ChatGPT "
            "conversation, then rerun the Tau DAG node."
        )
    if failure_code == KIMI_CONVERSATION_TOO_LONG_BLOCKER:
        return (
            "Do not resubmit into the same Kimi thread and do not treat this as throttling. The next_command "
            "resubmits this round into a fresh Kimi chat; if Kimi refuses again, split the round payload "
            "(attach the bundle instead of inlining it, or carry less prior-round text) before rerunning."
        )
    if failure_code == WEBGPT_BINDING_STALE_BLOCKER:
        return "Run the next_command to rebind browser-oracle to the live ChatGPT tab URL, then rerun the Tau DAG node."
    if failure_code == BROWSER_TAB_IDENTITY_MISMATCH:
        return "Rebind the browser-oracle project to the live tab URL or choose the correct tab, then rerun the Tau DAG node."
    if failure_code == BROWSER_TAB_READ_TIMEOUT:
        return "Run the next_command to open and bind a fresh provider tab, then rerun the Tau DAG node. Do not convert this to a prompt-size bundle retry."
    if failure_code == BROWSER_ACCESS_BLOCKED:
        return "Complete the provider access challenge in the controlled browser tab, rerun Surf preflight, then rerun the Tau DAG node."
    if failure_code == BROWSER_PROVIDER_RATE_LIMITED:
        return "Back off this browser provider until the limit clears; use a different handler or rerun later with the same verified tab."
    if failure_code == BROWSER_PROVIDER_SETUP_FAILED:
        return (
            "Run the next_command after repairing or updating the provider setup path. "
            "Do not treat model/reasoning selector failure as prompt size, repo access, or a completed response."
        )
    if failure_code == BROWSER_SUBMIT_NOT_ACCEPTED:
        return (
            "Run the next_command to open and bind a clean provider tab, then rerun only this lane. "
            "Do not treat an uncleared composer draft as a provider rate limit or as a completed response."
        )
    if failure_code == BROWSER_EXTENSION_COMMAND_TIMEOUT:
        return (
            "Surf's native host timed out waiting for the Chrome extension, so nothing was submitted. "
            "Reload the Surf extension (surf extension.reload), confirm the tab still answers "
            "surf webgpt.tab-id-background-sanity, then rerun only this lane on the same binding. "
            "Do not treat this as a provider access challenge and do not ask a human to solve a captcha."
        )
    if failure_code == BROWSER_TOOL_UNSUPPORTED:
        return "Repair the Surf wrapper/provider adapter command mapping, then rerun the Tau DAG node. Do not retry the same browser call unchanged."
    if failure_code == BROWSER_ATTACHMENT_UI_MISSING:
        return (
            "Do not submit this lane unchanged. Repair the provider attachment UI path, open the provider's "
            "attachment menu/file input before upload, or switch to a handler with working attachment support. "
            "Then rerun a focused attachment lane and read back response.meta.json before using the reviewer output."
        )
    if failure_code == BROWSER_ATTACHMENT_UNAVAILABLE:
        return (
            "Do not retry the same attachment submission unchanged. Repair or replace this provider's "
            "attachment transport, then rerun a focused attachment check before using the lane."
        )
    if failure_code == BROWSER_CLEAN_OUTPUT_CONTAMINATED:
        return (
            "Quarantine the browser output. The raw response contains the sentinel but the cleaned response still "
            "contains it, so repair the provider clean-output parser or rerun only this lane in a fresh tab."
        )
    if failure_code == BROWSER_SENTINEL_TRAILING_CONTENT:
        return (
            "Quarantine the browser output and rerun this lane in a fresh provider tab, or repair the "
            "provider parser so only pre-sentinel attributable content is accepted."
        )
    if failure_code == WEBGPT_UNVERIFIED_CLEAN_OUTPUT:
        return (
            "Quarantine the WebGPT response. Rebind browser-oracle to a proven controlled ChatGPT tab "
            "or rerun through Surf's controlled-tab recovery; do not import the unverified response.md."
        )
    if failure_code == BROWSER_HANDLER_TIMEOUT:
        return (
            "Treat only this browser lane as timed out. Preserve its submitted prompt and metadata, "
            "let the join index usable peer seats, and rerun this handler later or with a fresh provider tab."
        )
    if failure_code == SURF_BROWSER_LOCK_TIMEOUT:
        return (
            "Do not use --no-lock. Wait for the lock owner named in evidence.surf_lock_blocker, "
            "then run next_command, or move this lane to a separate Surf socket/profile."
        )
    if failure_code == SURF_BROWSER_CONNECTION_UNAVAILABLE:
        return (
            "Confirm the Surf native host and /tmp/surf.sock are available, then run next_command. "
            "Do not treat this local transport failure as provider throttling."
        )
    if failure_code == PROMPT_TOO_LARGE_OR_STALLED:
        if payload_policy.handler == "webkimi":
            return (
                f"Write the target material to {payload_policy.preferred_bundle} and rerun with a short prompt "
                "plus --attach-file <path>. Do not use a zip file for Kimi and do not keep retrying the "
                "large inline composer path. The measured prompt size is in evidence.measured_prompt_chars."
            )
        if not payload_policy.can_attach and "deepseek" in payload_policy.handler:
            return (
                "DeepSeek has no attachment path. Reduce the request to a bounded inline prompt, or choose "
                "a different handler for local evidence review. The measured prompt size is in "
                "evidence.measured_prompt_chars."
            )
        return (
            "Write the target material to a local readable bundle and rerun passing it with "
            "--attach-file <path> on tau-dag run or compete, instead of inlining a large prompt. "
            "The measured prompt size is in evidence.measured_prompt_chars."
        )
    if failure_code == BROWSER_ATTACHMENT_ARGUMENT_CONTRACT_FAILED:
        if payload_policy.handler == "webkimi":
            return (
                f"Combine the evidence into {payload_policy.preferred_bundle} and rerun with a single "
                "--attach-file. Do not zip the Kimi bundle and do not inline a large review packet; "
                "Surf rejected the arguments before any browser work, so the prompt and tab are not implicated."
            )
        if not payload_policy.can_attach and "deepseek" in payload_policy.handler:
            return (
                "DeepSeek does not accept attachments or zip files. Rerun with a short inline prompt only, "
                "or route the evidence bundle to a browser handler that supports attachments."
            )
        return (
            "Combine the evidence into one bundle or zip and rerun with a single --attach-file, "
            "or route it to a handler whose transport accepts several attachments. Surf rejected "
            "the arguments before any browser work, so the prompt and tab are not implicated."
        )
    if has_bundle and not can_attach:
        return (
            f"Do not auto-retry {handler}: the current Surf transport does not expose --attach-file for this handler. "
            "Use a handler with attachment support or add attachment support before retrying."
        )
    if has_bundle and can_attach:
        return "Run the next_command; it resubmits a concise prompt with the readable local bundle attached."
    if failure_code == REPO_ACCESS_BLOCKED:
        return (
            "Create a local readable review bundle, or grant/add the repository through the browser provider's GitHub integration, "
            "then rerun the next_command with the bundle path in the request."
        )
    if failure_code == ENVIRONMENT_DEPENDENCY_INSTALL_FAILED:
        return (
            "Repair the local Python environment before rerunning: install into the project virtualenv "
            "(uv sync / uv run --project <skill>) instead of a system dist-packages directory. No browser "
            "tab, prompt size, or bundle change affects this failure."
        )
    if failure_code == BROWSER_COMPOSER_INTERACTION_FAILED:
        return (
            "Open and bind a fresh provider tab, then rerun only this lane. The composer refused focus or "
            "typing, so shrinking the prompt or moving it into a bundle does not address the failure."
        )
    if failure_code == STALE_RAW_CAPTURE:
        return "Refresh or rebind the browser-oracle tab, then rerun the next_command; do not reuse the stale raw capture."
    return "Rerun only after the browser tab is responsive or a local readable bundle is available."


def _requires_local_readable_bundle(failure_code: str) -> bool:
    return _browser_failure_code(failure_code).requires_local_readable_bundle


def _handler_failure_recovery_packet(
    args: argparse.Namespace,
    *,
    request_payload: dict[str, Any],
    failure: str,
    response_text: str,
    submit_meta: dict[str, Any],
    commands: list[dict[str, Any]],
    response_path: Path,
    raw_path: Path,
    meta_path: Path,
    prompt_path: Path,
) -> dict[str, Any]:
    handler = str(args.handler)
    failure_code = _classify_handler_failure(handler=handler, failure=failure, submit_meta=submit_meta)
    return {
        "schema": HANDLER_RECOVERY_PACKET_SCHEMA,
        "status": "NEEDS_ATTENTION",
        "mocked": False,
        "live": bool(commands),
        "failure_code": failure_code,
        "handler": handler,
        "node_id": args.node_id,
        "reason": _handler_recovery_reason(failure_code),
        "evidence": {
            "failure_excerpt": failure.strip()[:2000],
            "response_chars": len(response_text),
            "submit_meta_status": submit_meta.get("status") or submit_meta.get("status_code"),
            "last_command": commands[-1] if commands else None,
            "scillm_base_url": str(getattr(args, "scillm_base_url", "") or "") or None,
        },
        "provider_diagnosis": _handler_provider_diagnosis(
            handler=handler,
            failure=failure,
            submit_meta=submit_meta,
            failure_code=failure_code,
        ),
        "response_path": str(response_path),
        "raw_response_path": str(raw_path),
        "meta_path": str(meta_path),
        "prompt_path": str(prompt_path),
        "auto_retry_allowed": False,
        "auto_retry_blocked_reason": _handler_auto_retry_blocked_reason(failure_code),
        "next_command": _handler_recovery_next_command(args, request_payload, failure_code),
        "fallback_instruction": _handler_fallback_instruction(failure_code),
        "ticket_target": ASK_TICKET_TARGET,
        "ticket_instruction": _ask_ticket_instruction(
            failure_code=failure_code,
            packet_kind="handler-recovery-packet",
        ),
    }


def _classify_handler_failure(*, handler: str, failure: str, submit_meta: dict[str, Any]) -> str:
    haystack = "\n".join([handler, failure, json.dumps(submit_meta, sort_keys=True, default=str)]).lower()
    if "prior_handler_receipts_not_ready" in haystack:
        return "prior_handler_receipts_not_ready"
    if (
        "http 401" in haystack
        or "invalid api key" in haystack
        or "authentication_error" in haystack
        or "provider_auth_error" in haystack
        or "provider_auth_failed" in haystack
        or "token_revoked" in haystack
        or "invalidated oauth token" in haystack
        or "autherror" in haystack
        or "please pass a valid api key" in haystack
    ):
        return "scillm_auth_invalid_api_key"
    if (
        "unknown model" in haystack
        or "not_found_error" in haystack
        or "model not found" in haystack
        or ("model:" in haystack and "404" in haystack)
    ):
        return "scillm_model_not_found"
    if "http 502" in haystack or "all groups exhausted" in haystack or "router_error" in haystack:
        return "scillm_provider_route_failed"
    if "subagent-runner" in haystack:
        return "subagent_runner_failed"
    if "codex" in haystack:
        return "codex_handler_failed"
    if "timed out" in haystack or "timeout" in haystack:
        return "handler_timeout"
    return "handler_execution_failed"


def _handler_provider_diagnosis(
    *,
    handler: str,
    failure: str,
    submit_meta: dict[str, Any],
    failure_code: str,
) -> dict[str, Any]:
    """Extract actionable provider repair hints from SciLLM-style failures."""
    haystack = "\n".join([failure, json.dumps(submit_meta, sort_keys=True, default=str)])
    suggested_models = _extract_suggested_models(haystack)
    available_models = _extract_available_models(haystack)
    routed_model, provider_chain = _extract_model_route(haystack)
    diagnosis = {
        "schema": "ask.handler_provider_diagnosis.v1",
        "handler": handler,
        "failure_code": failure_code,
        "http_status": _extract_http_status(haystack),
        "routed_model": routed_model,
        "provider_chain": provider_chain,
        "suggested_models": suggested_models,
        "available_models_sample": available_models[:24],
        "available_model_count": len(available_models),
        "health_command": "curl -sS http://127.0.0.1:4001/v1/scillm/health | jq .",
        "models_command": "curl -sS http://127.0.0.1:4001/v1/scillm/models | jq .",
    }
    if failure_code == "scillm_auth_invalid_api_key":
        diagnosis["repair_hint"] = (
            "Configure SCILLM_PROXY_KEY, SCILLM_MASTER_KEY, or LITELLM_MASTER_KEY "
            "for the running proxy before rerunning this handler."
        )
    elif failure_code == "scillm_model_not_found":
        diagnosis["repair_hint"] = (
            "Select one of suggested_models or an available model from available_models_sample, "
            "then rerun the same Ask DAG."
        )
    elif failure_code == "scillm_provider_route_failed":
        diagnosis["repair_hint"] = (
            "Check provider health and capacity before retrying; do not relaunch all healthy seats."
        )
    else:
        diagnosis["repair_hint"] = "Inspect failure_excerpt and rerun only after the named blocker is addressed."
    return diagnosis


def _extract_http_status(text: str) -> int | None:
    match = re.search(r"\bHTTP\s+(\d{3})\b", text, flags=re.IGNORECASE)
    if not match:
        match = re.search(r'"code"\s*:\s*(\d{3})\b', text)
    return int(match.group(1)) if match else None


def _extract_suggested_models(text: str) -> list[str]:
    suggestions = []
    for match in re.finditer(r"Did you mean:\s*([^?\\.\\n]+)", text, flags=re.IGNORECASE):
        candidate = match.group(1).strip(" '\"`.,")
        if candidate and candidate not in suggestions:
            suggestions.append(candidate)
    return suggestions


def _extract_available_models(text: str) -> list[str]:
    match = re.search(r"Available:\s*([^\"\\n]+)", text, flags=re.IGNORECASE)
    if not match:
        return []
    raw = match.group(1).strip().rstrip(".")
    models = []
    for item in raw.split(","):
        model = item.strip(" '\"`.")
        if model and model not in models:
            models.append(model)
    return models


def _extract_model_route(text: str) -> tuple[str | None, list[str]]:
    model_match = re.search(r"model='([^']+)'", text)
    routed_model = model_match.group(1) if model_match else None
    chain_match = re.search(r"chain=\[([^\]]*)\]", text)
    chain: list[str] = []
    if chain_match:
        for item in chain_match.group(1).split(","):
            value = item.strip(" '\"`")
            if value:
                chain.append(value)
    return routed_model, chain


def _handler_recovery_reason(failure_code: str) -> str:
    return {
        "prior_handler_receipts_not_ready": "A sequential lane could not run because an upstream handler receipt was not usable.",
        "scillm_auth_invalid_api_key": "SciLLM rejected the configured bearer token.",
        "scillm_model_not_found": "SciLLM routed the requested model to a provider/model id that is not available.",
        "scillm_provider_route_failed": "SciLLM exhausted provider routes for the requested model.",
        "subagent_runner_failed": "The local subagent-runner handler did not produce a usable answer.",
        "codex_handler_failed": "The local Codex handler did not produce the required workspace evidence.",
        "handler_timeout": "The handler did not produce a usable answer before its timeout.",
        "handler_execution_failed": "The handler exited without a usable response.",
    }.get(failure_code, "The handler exited without a usable response.")


def _handler_auto_retry_blocked_reason(failure_code: str) -> str:
    if failure_code == "scillm_auth_invalid_api_key":
        return "auth_requires_configured_scillm_proxy_key"
    if failure_code in {"scillm_model_not_found", "scillm_provider_route_failed"}:
        return "provider_route_requires_model_or_provider_repair"
    if failure_code == "prior_handler_receipts_not_ready":
        return "upstream_receipt_not_usable"
    return "generic_handler_failure_requires_project_agent_review"


def _handler_recovery_next_command(
    args: argparse.Namespace,
    request_payload: dict[str, Any],
    failure_code: str,
) -> str:
    request_text = str(request_payload.get("request") or "").strip()
    parts = ["cd", "skills/ask", "&&", "./run.sh", "tau-dag", request_text or "repeat the same request"]
    for key, flag in (
        ("repo", "--repo"),
        ("target", "--target"),
        ("immutable_goal", "--immutable-goal"),
    ):
        value = str(request_payload.get(key) or "").strip()
        if value:
            parts.extend([flag, value])
    handlers = request_payload.get("handlers") or [getattr(args, "handler", "")]
    for handler in handlers:
        handler_value = str(handler or "").strip()
        if handler_value:
            parts.extend(["--handler", handler_value])
    for project in request_payload.get("handler_projects") or []:
        project_value = str(project or "").strip()
        if project_value:
            parts.extend(["--handler-project", project_value])
    topology = str(request_payload.get("topology") or getattr(args, "topology", "") or "").strip()
    if topology:
        parts.extend(["--topology", topology])
    workflow_mode = str(request_payload.get("workflow_mode") or getattr(args, "workflow_mode", "") or "").strip()
    if workflow_mode:
        parts.extend(["--workflow-mode", workflow_mode])
    base = " ".join(shlex.quote(part) for part in parts)
    if failure_code == "scillm_auth_invalid_api_key":
        return (
            "export SCILLM_PROXY_KEY=<configured proxy key>; "
            + base
            + " --execute --allow-provider-calls --json"
        )
    if failure_code in {"scillm_model_not_found", "scillm_provider_route_failed"}:
        return base + " --execute --allow-provider-calls --json # after selecting an available SciLLM model route"
    return base + " --execute --json"


def _handler_fallback_instruction(failure_code: str) -> str:
    if failure_code == "scillm_auth_invalid_api_key":
        return "Configure SCILLM_PROXY_KEY, SCILLM_MASTER_KEY, or LITELLM_MASTER_KEY for the running SciLLM proxy before retrying."
    if failure_code == "scillm_model_not_found":
        return "Use an available model id from the SciLLM provider list or repair the provider route."
    if failure_code == "scillm_provider_route_failed":
        return "Check SciLLM provider health and rerun with a route that has capacity."
    if failure_code == "prior_handler_receipts_not_ready":
        return "Inspect the upstream node receipt and recovery packet before rerunning the dependent lane."
    return "Inspect the handler recovery packet, then rerun only after the named blocker is addressed."


def _run_join(args: argparse.Namespace, start: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    if args.workflow_mode == "compete":
        return _run_compete_join(args, start, artifact_dir)
    receipt_path = artifact_dir / "node-receipt.json"
    summary_path = artifact_dir / "roundtable-summary.md"
    node_artifacts_root = artifact_dir.parent
    handler_receipts = []
    failures = []
    usable_responses = []
    for path in sorted(node_artifacts_root.glob("handler-*/node-receipt.json")):
        receipt = _read_json(path)
        if receipt.get("schema") != "ask.tau_dag_handler_receipt.v1":
            continue
        response_path = Path(str(receipt.get("response_path") or ""))
        response_chars = response_path.stat().st_size if response_path.is_file() else int(receipt.get("response_chars") or 0)
        indexed_receipt = {
            "path": str(path),
            **receipt,
            "response_chars": response_chars,
            # A passing seat must keep failure_code=null: the classifier greps
            # the serialized submit_meta, where config fields like
            # "timeout_s": 900 read as a timeout and stamped handler_timeout
            # onto PASS lanes (agent-skills#1217).
            "failure_code": receipt.get("failure_code")
            or (
                _classify_handler_failure(
                    handler=str(receipt.get("handler") or ""),
                    failure=str(receipt.get("failure") or ""),
                    submit_meta=receipt.get("submit_meta") if isinstance(receipt.get("submit_meta"), dict) else {},
                )
                if receipt.get("ok") is not True
                else None
            ),
            "recovery_packet_path": receipt.get("recovery_packet_path"),
            "response_quarantine": receipt.get("response_quarantine"),
            "browser_transport_failure_summary": receipt.get("browser_transport_failure_summary"),
        }
        handler_receipts.append(indexed_receipt)
        if receipt.get("ok") is True and response_chars > 0:
            usable_responses.append(indexed_receipt)
        if receipt.get("ok") is not True:
            failures.append(
                {
                    "node_id": receipt.get("node_id"),
                    "handler": receipt.get("handler"),
                    "status": receipt.get("status"),
                    "failure": receipt.get("failure") or receipt.get("status"),
                    "failure_code": indexed_receipt.get("failure_code"),
                    "recovery_packet_path": indexed_receipt.get("recovery_packet_path"),
                    "response_quarantine": indexed_receipt.get("response_quarantine"),
                    "browser_transport_failure_summary": indexed_receipt.get("browser_transport_failure_summary"),
                }
            )
    lines = [
        "# Tau Roundtable Join",
        "",
        f"- topology: `{args.topology}`",
        f"- handlers: `{len(handler_receipts)}`",
        "",
    ]
    for receipt in handler_receipts:
        lines.extend(
            [
                f"## {receipt.get('handler')}",
                "",
                f"- status: `{receipt.get('status')}`",
                f"- response: `{receipt.get('response_path')}`",
                "",
            ]
        )
        response_path = Path(str(receipt.get("response_path") or ""))
        if receipt.get("ok") is True and response_path.is_file():
            text = response_path.read_text(encoding="utf-8").strip()
            lines.append(text[:2000])
            lines.append("")
        elif receipt.get("ok") is not True:
            quarantine = receipt.get("response_quarantine") if isinstance(receipt.get("response_quarantine"), dict) else {}
            quarantine_path = quarantine.get("quarantine_path") if isinstance(quarantine, dict) else None
            lines.append(f"Failed seat output is not quoted. quarantine: `{quarantine_path or 'none'}`")
            lines.append("")
    summary_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    if handler_receipts and not failures and len(usable_responses) == len(handler_receipts):
        status = "PASS"
    elif usable_responses:
        status = "DEGRADED"
    else:
        status = "NEEDS_ATTENTION"
    ok = status == "PASS"
    degradation_analysis = _roundtable_degradation_analysis(
        status=status,
        handler_receipts=handler_receipts,
        usable_responses=usable_responses,
        failures=failures,
    )
    if degradation_analysis["why"]:
        lines.extend(["## Degradation Analysis", ""])
        lines.append(degradation_analysis["why"])
        lines.append("")
        for item in degradation_analysis["failed_seats"]:
            lines.append(f"- `{item.get('node_id')}` / `{item.get('handler')}`: `{item.get('failure_code')}`")
            lines.append(f"  recovery: `{item.get('recovery_packet_path') or 'missing'}`")
            if item.get("ticket_instruction"):
                lines.append(f"  ticket: {item.get('ticket_instruction')}")
        lines.append("")
        summary_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    receipt = {
        "schema": "ask.tau_dag_roundtable_join_receipt.v1",
        "created_at": _now(),
        "node_id": args.node_id,
        "handler": args.handler,
        "topology": args.topology,
        "status": status,
        "ok": ok,
        "mocked": False,
        "live": any(item.get("live") is True for item in handler_receipts),
        "provider_live": ok and all(item.get("provider_live") is True for item in handler_receipts),
        "handler_response_index": handler_receipts,
        "usable_response_count": len(usable_responses),
        "failed_seat_count": len(failures),
        # #1257: per-seat terminal state at the top level so a DEGRADED result
        # is self-explaining without spelunking node-artifacts dirs.
        "seat_terminal_states": [
            {
                "node_id": item.get("node_id"),
                "handler": item.get("handler"),
                "status": item.get("status"),
                "ok": item.get("ok"),
                "failure_code": item.get("failure_code"),
                "response_chars": item.get("response_chars"),
                "delivered": bool(item.get("ok") is True and int(item.get("response_chars") or 0) > 0),
            }
            for item in handler_receipts
        ],
        "degraded_seats": [
            {
                "node_id": item.get("node_id"),
                "handler": item.get("handler"),
                "failure_code": item.get("failure_code") or item.get("status"),
            }
            for item in handler_receipts
            if not (item.get("ok") is True and int(item.get("response_chars") or 0) > 0)
        ],
        "removed_seats": [
            item.get("handler")
            for item in handler_receipts
            if not (item.get("ok") is True and int(item.get("response_chars") or 0) > 0)
        ]
        or None,
        "degradation_analysis": degradation_analysis,
        "summary_path": str(summary_path),
        "unresolved_gaps": failures,
        "provider_receipt": {
            "schema": "ask.tau_dag_provider_route_receipt.v1",
            "status": status,
            "ok": ok,
            "mocked": False,
            "live": any(item.get("live") is True for item in handler_receipts),
            "provider_live": ok and all(item.get("provider_live") is True for item in handler_receipts),
            "route": "tau_roundtable_join_adapter",
            "execution_owner": "$tau",
            "provider_transport": "$surf",
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    handoff = _handoff(
        args,
        start,
        status=status,
        summary=f"Roundtable join {status.lower()} over {len(handler_receipts)} handler receipts.",
        artifacts=[receipt_path, summary_path],
        evidence=[
            {"kind": "roundtable_join_receipt", "path": str(receipt_path), "status": status},
            {"kind": "degradation_analysis", **degradation_analysis},
            {
                "kind": "handler_response_index",
                "count": len(handler_receipts),
                "usable_response_count": len(usable_responses),
                "failures": failures,
            },
            {"kind": "unresolved_gaps", "items": failures},
        ],
    )
    return {"exit_code": 0, "handoff": handoff}


def _roundtable_degradation_analysis(
    *,
    status: str,
    handler_receipts: list[dict[str, Any]],
    usable_responses: list[dict[str, Any]],
    failures: list[dict[str, Any]],
) -> dict[str, Any]:
    failed_seats = []
    failure_codes: dict[str, int] = {}
    recovery_commands = []
    for failure in failures:
        code = str(failure.get("failure_code") or "handler_execution_failed")
        failure_codes[code] = failure_codes.get(code, 0) + 1
        recovery_packet_path = str(failure.get("recovery_packet_path") or "")
        recovery_packet = _read_optional_json(Path(recovery_packet_path)) if recovery_packet_path else {}
        next_command = str(recovery_packet.get("next_command") or "")
        failed = {
            "node_id": failure.get("node_id"),
            "handler": failure.get("handler"),
            "status": failure.get("status"),
            "failure_code": code,
            "failure": failure.get("failure"),
            "recovery_packet_path": recovery_packet_path or None,
            "response_quarantine": failure.get("response_quarantine"),
            "next_command": next_command or None,
            "auto_retry_allowed": recovery_packet.get("auto_retry_allowed"),
            "auto_retry_blocked_reason": recovery_packet.get("auto_retry_blocked_reason"),
            "transport_failure_summary": recovery_packet.get("transport_failure_summary"),
            "evidence": recovery_packet.get("evidence"),
            "ticket_target": recovery_packet.get("ticket_target"),
            "ticket_instruction": recovery_packet.get("ticket_instruction"),
        }
        failed_seats.append(failed)
        if next_command:
            recovery_commands.append(
                {
                    "node_id": failure.get("node_id"),
                    "handler": failure.get("handler"),
                    "failure_code": code,
                    "next_command": next_command,
                    "ticket_target": recovery_packet.get("ticket_target"),
                }
            )
    if status == "PASS":
        why = "All handler seats produced usable responses; no degradation."
    elif usable_responses:
        why = (
            f"{len(usable_responses)} of {len(handler_receipts)} handler seat(s) produced usable responses; "
            f"{len(failed_seats)} terminal seat(s) need attention."
        )
    else:
        why = (
            f"0 of {len(handler_receipts)} handler seat(s) produced usable responses; "
            "the aggregate has no reviewer evidence to preserve."
        )
    return {
        "schema": "ask.tau_dag_degradation_analysis.v1",
        "status": status,
        "why": why,
        "usable_response_count": len(usable_responses),
        "handler_count": len(handler_receipts),
        "failed_seat_count": len(failed_seats),
        "failure_codes": failure_codes,
        "failed_seats": failed_seats,
        "recovery_commands": recovery_commands,
    }


def _run_compete_join(args: argparse.Namespace, start: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    receipt_path = artifact_dir / "node-receipt.json"
    scorecard_path = artifact_dir / "compete-scorecard.json"
    continuation_path = artifact_dir / "winner-continuation-request.md"
    summary_path = artifact_dir / "compete-summary.md"
    node_artifacts_root = artifact_dir.parent
    handler_receipts = []
    blockers = []
    transport_blockers = []
    for path in sorted(node_artifacts_root.glob("handler-*/node-receipt.json")):
        receipt = _read_json(path)
        if receipt.get("schema") != "ask.tau_dag_handler_receipt.v1":
            continue
        response_path = Path(str(receipt.get("response_path") or ""))
        response_text = response_path.read_text(encoding="utf-8") if response_path.is_file() else ""
        verified_features = _extract_verified_features(response_text)
        candidate = {
            "node_id": receipt.get("node_id"),
            "handler": receipt.get("handler"),
            "status": receipt.get("status"),
            "ok": receipt.get("ok") is True,
            "live": receipt.get("live") is True,
            "provider_live": receipt.get("provider_live") is True,
            "response_path": str(response_path) if response_path else "",
            "verified_features": verified_features,
            "feature_count": len(verified_features),
            "failure": receipt.get("failure") or "",
            "failure_code": receipt.get("failure_code") or "",
            "recovery_packet_path": receipt.get("recovery_packet_path"),
            "failure_kind": "semantic",
        }
        recovery_packet = receipt.get("recovery_packet") if isinstance(receipt.get("recovery_packet"), dict) else {}
        if str(candidate["failure_code"]) in BROWSER_TRANSPORT_BLOCKERS:
            candidate["failure_kind"] = "transport"
            transport_blockers.append(
                {
                    "node_id": candidate["node_id"],
                    "handler": candidate["handler"],
                    "failure_code": candidate["failure_code"],
                    "status": candidate["status"],
                    "recovery_packet_path": receipt.get("recovery_packet_path"),
                    "next_command": recovery_packet.get("next_command"),
                    "auto_retry_blocked_reason": recovery_packet.get("auto_retry_blocked_reason"),
                    "evidence": recovery_packet.get("evidence"),
                }
            )
        handler_receipts.append(candidate)
        if candidate["ok"] is not True:
            if candidate["failure_kind"] == "transport":
                blockers.append(f"{candidate['node_id']}: transport_blocker:{candidate['failure_code']}")
            else:
                blockers.append(f"{candidate['node_id']}: {candidate['failure'] or candidate['status']}")

    all_verified_features: list[str] = []
    for candidate in handler_receipts:
        for feature in candidate["verified_features"]:
            if feature not in all_verified_features:
                all_verified_features.append(feature)

    selectable = [item for item in handler_receipts if item["ok"] is True and item["feature_count"] > 0]
    selectable.sort(key=lambda item: (item["feature_count"], item["provider_live"], item["live"]), reverse=True)
    winner = selectable[0] if selectable else None
    tied = bool(len(selectable) > 1 and selectable[0]["feature_count"] == selectable[1]["feature_count"])
    candidate_winner_handler = str(winner.get("handler") or "") if winner and not tied else ""
    fatal_blockers = []
    # Independent judge verdict (agent-skills#1243): when a judge node ran,
    # its WINNER line is authoritative over the deterministic feature count —
    # provided it names a real, passing competitor. An unparseable or invalid
    # verdict is a blocker, never silently ignored.
    judge_selection = None
    judge_receipt_path = node_artifacts_root / "judge" / "node-receipt.json"
    if judge_receipt_path.is_file():
        judge_receipt = _read_json(judge_receipt_path)
        judge_response = ""
        response_path = Path(str(judge_receipt.get("response_path") or ""))
        if response_path.is_file():
            judge_response = response_path.read_text(encoding="utf-8", errors="replace")
        winner_lines = [
            line.split("WINNER:", 1)[1].strip().strip("`*")
            for line in judge_response.splitlines()
            if "WINNER:" in line
        ]
        named = winner_lines[-1] if winner_lines else ""
        by_node = {str(item.get("node_id")): item for item in handler_receipts}
        if judge_receipt.get("ok") is not True:
            fatal_blockers.append("judge_seat_failed")
        elif named in by_node and by_node[named]["ok"] is True:
            judge_selection = by_node[named]
            winner = judge_selection
            tied = False
            candidate_winner_handler = str(judge_selection.get("handler") or "")
        elif named:
            fatal_blockers.append(f"judge_named_invalid_winner:{named}")
        else:
            fatal_blockers.append("judge_verdict_missing_winner_line")
    if tied:
        fatal_blockers.append("winner_tie_requires_project_agent_review")
    if not candidate_winner_handler:
        fatal_blockers.append("no_clear_winner_from_receipts")
    if not all_verified_features:
        fatal_blockers.append("no_explicit_verified_features_to_promote")
    if transport_blockers:
        blockers.append("competition_transport_degraded")
    if (
        handler_receipts
        and len(transport_blockers) == len(handler_receipts)
        and not any(candidate["ok"] is True for candidate in handler_receipts)
    ):
        blockers.append("competition_transport_blocked")
    blockers.extend(fatal_blockers)
    status = "PASS" if candidate_winner_handler and not blockers else "NEEDS_ATTENTION"
    ok = status == "PASS"
    winner_handler = candidate_winner_handler if ok else ""
    degradation_analysis = _compete_degradation_analysis(
        status=status,
        candidates=handler_receipts,
        blockers=blockers,
        transport_blockers=transport_blockers,
        winner_handler=winner_handler,
        verified_features=all_verified_features,
    )

    continuation_lines = [
        "# Winner Continuation Request",
        "",
        f"Status: {status}",
        f"Winner handler: {winner_handler or 'NEEDS_ATTENTION'}",
        "",
        "Task:",
        _read_json(Path(args.request_file)).get("request", ""),
        "",
        "Verified features to consider:",
    ]
    if all_verified_features:
        continuation_lines.extend(f"- {feature}" for feature in all_verified_features)
    else:
        continuation_lines.append("- NEEDS_ATTENTION: no candidate emitted explicit VERIFIED_FEATURE lines.")
    continuation_lines.extend(
        [
            "",
            "Instructions to the winner:",
            "- Keep the winning implementation as the base.",
            "- Add only the listed verified features that still pass local deterministic checks.",
            "- Do not import unverified candidate claims.",
            "- Return changed files, commands run, proof artifacts, and unresolved blockers.",
        ]
    )
    continuation_path.write_text("\n".join(str(line) for line in continuation_lines).rstrip() + "\n", encoding="utf-8")

    scorecard = {
        "schema": "ask.tau_dag_compete_scorecard.v1",
        "created_at": _now(),
        "status": status,
        "ok": ok,
        "mocked": False,
        "live": any(item["live"] for item in handler_receipts),
        "provider_live": bool(ok and winner and winner.get("provider_live") is True),
        "winner_handler": winner_handler,
        "winner_selected_by": "judge_verdict" if judge_selection is not None else "deterministic_receipts",
        "winner_node_id": winner.get("node_id") if winner and winner_handler else "",
        "selection_basis": "deterministic_receipts_and_explicit_verified_feature_markers",
        "failure_kind": (
            "degraded_transport"
            if transport_blockers and ok
            else ("transport" if transport_blockers else ("semantic_or_evidence" if blockers else "none"))
        ),
        "candidates": handler_receipts,
        "transport_blockers": transport_blockers,
        "verified_features": all_verified_features,
        "blockers": blockers,
        "degradation_analysis": degradation_analysis,
        "winner_continuation_request_path": str(continuation_path),
        "revision_request_path": str(continuation_path),
        "proof_scope": {
            "proves": [
                "Candidate node receipts were collected.",
                "The scorecard fail-closed when no clear receipt-backed winner existed.",
                "Only explicit VERIFIED_FEATURE markers were promoted into the revision packet.",
                "Browser transport blockers were separated from semantic candidate failures.",
            ],
            "does_not_prove": [
                "The winning candidate is semantically best.",
                "The verified feature markers are true without project-agent codebase checks.",
                "The winner revision request has been submitted to a model.",
            ],
        },
    }
    scorecard_path.write_text(json.dumps(scorecard, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary_path.write_text(_compete_summary(scorecard) + "\n", encoding="utf-8")
    receipt = {
        "schema": "ask.tau_dag_compete_join_receipt.v1",
        "created_at": _now(),
        "node_id": args.node_id,
        "handler": args.handler,
        "topology": args.topology,
        "workflow_mode": args.workflow_mode,
        "status": status,
        "ok": ok,
        "mocked": False,
        "live": scorecard["live"],
        "provider_live": scorecard["provider_live"],
        "scorecard_path": str(scorecard_path),
        "winner_continuation_request_path": str(continuation_path),
        "revision_request_path": str(continuation_path),
        "summary_path": str(summary_path),
        "handler_response_index": handler_receipts,
        "unresolved_gaps": blockers,
        "degradation_analysis": degradation_analysis,
        "provider_receipt": {
            "schema": "ask.tau_dag_provider_route_receipt.v1",
            "status": status,
            "ok": ok,
            "mocked": False,
            "live": scorecard["live"],
            "provider_live": scorecard["provider_live"],
            "route": "tau_compete_join_adapter",
            "execution_owner": "$tau",
            "provider_transport": "$surf_or_scillm",
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    handoff = _handoff(
        args,
        start,
        status=status,
        summary=f"Compete join {status.lower()} over {len(handler_receipts)} candidate receipts.",
        artifacts=[receipt_path, scorecard_path, continuation_path, summary_path],
        evidence=[
            {"kind": "compete_scorecard", "path": str(scorecard_path), "status": status},
            {"kind": "degradation_analysis", **degradation_analysis},
            {"kind": "verified_feature_packet", "count": len(all_verified_features), "items": all_verified_features},
            {"kind": "winner_continuation_request", "path": str(continuation_path), "winner_handler": winner_handler},
            {"kind": "unresolved_gaps", "items": blockers},
        ],
    )
    return {"exit_code": 0, "handoff": handoff}


def _compete_degradation_analysis(
    *,
    status: str,
    candidates: list[dict[str, Any]],
    blockers: list[str],
    transport_blockers: list[dict[str, Any]],
    winner_handler: str,
    verified_features: list[str],
) -> dict[str, Any]:
    failed_candidates = []
    failure_codes: dict[str, int] = {}
    recovery_commands = []
    for candidate in candidates:
        if candidate.get("ok") is True:
            continue
        code = str(candidate.get("failure_code") or "candidate_output_not_selectable")
        failure_codes[code] = failure_codes.get(code, 0) + 1
        recovery_packet_path = str(candidate.get("recovery_packet_path") or "")
        recovery_packet = _read_optional_json(Path(recovery_packet_path)) if recovery_packet_path else {}
        next_command = str(recovery_packet.get("next_command") or "")
        failed_candidates.append(
            {
                "node_id": candidate.get("node_id"),
                "handler": candidate.get("handler"),
                "status": candidate.get("status"),
                "failure_kind": candidate.get("failure_kind"),
                "failure_code": code,
                "failure": candidate.get("failure"),
                "recovery_packet_path": recovery_packet_path or None,
                "next_command": next_command or None,
                "auto_retry_allowed": recovery_packet.get("auto_retry_allowed"),
                "auto_retry_blocked_reason": recovery_packet.get("auto_retry_blocked_reason"),
                "transport_failure_summary": recovery_packet.get("transport_failure_summary"),
                "evidence": recovery_packet.get("evidence"),
                "ticket_target": recovery_packet.get("ticket_target"),
                "ticket_instruction": recovery_packet.get("ticket_instruction"),
            }
        )
        if next_command:
            recovery_commands.append(
                {
                    "node_id": candidate.get("node_id"),
                    "handler": candidate.get("handler"),
                    "failure_code": code,
                    "next_command": next_command,
                    "ticket_target": recovery_packet.get("ticket_target"),
                }
            )
    if status == "PASS" and failed_candidates:
        why = (
            f"Winner `{winner_handler}` was selected from available receipt-backed candidates; "
            f"{len(failed_candidates)} of {len(candidates)} candidate lane(s) failed or need attention."
        )
    elif status == "PASS":
        why = f"Winner `{winner_handler}` selected from receipt-backed verified features."
    elif not candidates:
        why = "No candidate receipts were available, so the competition cannot be scored."
    elif failed_candidates:
        why = (
            f"{len(failed_candidates)} of {len(candidates)} candidate lane(s) failed or need attention; "
            f"{len(verified_features)} explicit VERIFIED_FEATURE item(s) were available, but selection failed closed "
            "until failed lanes are resolved or explicitly excluded by the project agent."
        )
    else:
        why = "Candidate receipts were collected, but selection failed closed because scorecard blockers remain."
    return {
        "schema": "ask.tau_dag_degradation_analysis.v1",
        "status": status,
        "why": why,
        "candidate_count": len(candidates),
        "failed_candidate_count": len(failed_candidates),
        "winner_handler": winner_handler or None,
        "verified_feature_count": len(verified_features),
        "failure_codes": failure_codes,
        "blockers": blockers,
        "transport_blocker_count": len(transport_blockers),
        "failed_candidates": failed_candidates,
        "recovery_commands": recovery_commands,
    }


def _extract_verified_features(text: str) -> list[str]:
    features: list[str] = []
    for line in text.splitlines():
        match = re.match(r"\s*(?:[-*]\s*)?VERIFIED_FEATURE\s*:\s*(.+?)\s*$", line, flags=re.IGNORECASE)
        if match:
            feature = match.group(1).strip()
            if feature and feature not in features:
                features.append(feature)
    if features:
        return features

    # Some browser providers expose visually separated Markdown as one long DOM
    # text line. Recover explicit markers without treating prose like
    # "VERIFIED_FEATURE: lines" as a promotable feature.
    marker = re.compile(r"VERIFIED_FEATURE\s*:\s*", flags=re.IGNORECASE)
    section_boundary = re.compile(
        r"\s+(?:Position|Evidence|Uncertainties|Risks|Blockers|Proof Commands|PROOF_COMMANDS)\b",
        flags=re.IGNORECASE,
    )
    matches = list(marker.finditer(text))
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        boundary = section_boundary.search(text, start, end)
        if boundary:
            end = boundary.start()
        feature = " ".join(text[start:end].strip().split())
        if not feature:
            continue
        if re.match(r"^(?:line|lines|marker|markers|occurrence|occurrences)\b", feature, flags=re.IGNORECASE):
            continue
        if re.match(r"^(?:and|or|that|which)\b", feature, flags=re.IGNORECASE):
            continue
        if feature not in features:
            features.append(feature)
    return features


def _compete_summary(scorecard: dict[str, Any]) -> str:
    degradation = scorecard.get("degradation_analysis") if isinstance(scorecard.get("degradation_analysis"), dict) else {}
    lines = [
        "# Tau Compete Join",
        "",
        f"- status: `{scorecard.get('status')}`",
        f"- winner: `{scorecard.get('winner_handler') or 'NEEDS_ATTENTION'}`",
        f"- candidates: `{len(scorecard.get('candidates') or [])}`",
        "",
    ]
    if degradation.get("why"):
        lines.extend(["## Degradation Analysis", "", str(degradation.get("why")), ""])
        for item in degradation.get("failed_candidates") or []:
            lines.append(f"- `{item.get('node_id')}` / `{item.get('handler')}`: `{item.get('failure_code')}`")
            lines.append(f"  recovery: `{item.get('recovery_packet_path') or 'missing'}`")
            if item.get("ticket_instruction"):
                lines.append(f"  ticket: {item.get('ticket_instruction')}")
        lines.append("")
    lines.extend(["## Candidates", ""])
    for candidate in scorecard.get("candidates") or []:
        lines.extend(
            [
                f"### {candidate.get('handler')}",
                "",
                f"- status: `{candidate.get('status')}`",
                f"- features: `{candidate.get('feature_count')}`",
                f"- response: `{candidate.get('response_path')}`",
                "",
            ]
        )
    if scorecard.get("blockers"):
        lines.extend(["## Blockers", ""])
        lines.extend(f"- {item}" for item in scorecard.get("blockers") or [])
    return "\n".join(lines).rstrip()


def _handler_prompt(
    request_text: str,
    handler: str,
    *,
    prior_receipts: list[dict[str, Any]] | None = None,
    requires_verdict: bool = False,
    inline_full: bool = False,
    workflow_mode: str = "roundtable",
    model_preference: str = "",
    node_id: str = "",
    criteria: list[str] | None = None,
) -> str:
    prior_receipts = prior_receipts or []
    if node_id == "judge":
        role_line = (
            "You are the INDEPENDENT JUDGE of a Tau-managed implementation "
            "competition. You did not write any submission. Review every "
            "competitor receipt below strictly against the criteria."
        )
    elif node_id == "report":
        role_line = (
            "You are the REPORT WRITER for a completed Tau-managed "
            "implementation competition. Using the scorecard and judge "
            "verdict below, write a concise Markdown report: the task, each "
            "competitor's approach, why the winner won against the criteria, "
            "and the winning function itself. Under 600 words."
        )
    elif workflow_mode == "compete":
        role_line = "You are one isolated competitor in a Tau-managed implementation competition."
    else:
        role_line = "You are one participant in a Tau-managed roundtable."
    lines = [
        role_line,
        f"Handler: {handler}",
        "",
        "Request:",
        request_text,
        "",
    ]
    if node_id in ("judge", "report") and criteria:
        lines.extend(["Evaluation criteria:", *[f"- {c}" for c in criteria], ""])
    if model_preference:
        lines.extend(["Browser model preference:", model_preference, ""])
    if workflow_mode == "compete" and node_id not in ("judge", "report"):
        lines.extend(
            [
                "Isolation rule: work from the shared task only. Do not assume any other competitor output.",
                "Return any reusable ideas as lines that start exactly with `VERIFIED_FEATURE:` only when the feature is concrete enough for the project agent to verify locally.",
                "",
            ]
        )
    if prior_receipts:
        lines.extend(["Prior handler receipts to use as input:", ""])
        for receipt in prior_receipts:
            lines.extend(
                [
                    # No local filesystem paths in a browser-bound prompt: surf's
                    # prompt preflight fails closed on them (the browser model
                    # cannot read local files). The path stays in the node receipt.
                    f"### {receipt.get('node_id')} / {receipt.get('handler')}",
                    f"- status: {receipt.get('status')}",
                    "",
                    # Inline only the summary portion. Raw git diffs contain
                    # tokens (Rust // comments, /paths) that trip the browser
                    # transport's local-path preflight; the full response is
                    # provided to browser handlers as a file attachment.
                    (
                        str(receipt.get("response_excerpt") or "").strip()
                        if inline_full
                        else _excerpt_before_diff(str(receipt.get("response_excerpt") or ""))
                    ),
                    "",
                ]
            )
    if node_id == "judge":
        lines.extend(
            [
                "Score each competitor against the criteria, name concrete "
                "violations, then end with exactly one line naming the best "
                "submission's node id:",
                "WINNER: <competitor-node-id>",
                "",
            ]
        )
    elif requires_verdict:
        lines.extend(
            [
                "Return a review verdict using exactly one of:",
                "VERDICT: PASS",
                "VERDICT: FAIL",
                "VERDICT: NEEDS_ATTENTION",
                "",
            ]
        )
    lines.extend(
        [
            "Return a concise position with these Markdown headings:",
            "## Position",
            "## Evidence",
            "## Uncertainties",
            "## Blockers",
        ]
    )
    return "\n".join(lines)


def _handoff(
    args: argparse.Namespace,
    start: dict[str, Any],
    *,
    status: str,
    summary: str,
    artifacts: list[Path],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    goal = start.get("goal", {})
    goal_hash = goal.get("goal_hash") if isinstance(goal, dict) else None
    if goal_hash:
        # Tau blocks with evidence_goal_hash_missing unless every evidence
        # item carries the contract's immutable goal hash.
        evidence = [
            {**item, "goal_hash": item.get("goal_hash", goal_hash)}
            if isinstance(item, dict)
            else item
            for item in evidence
        ]
    # Self-check the handoff against the consumer's actual rules before
    # emitting it: Tau rejects path-bearing receipt evidence whose file is
    # absent or empty (evidence_receipt_path_missing). Repair what is
    # repairable (write a minimal receipt stub carrying the failure context so
    # the path is real and truthful) and record every action taken, so a
    # drifting producer is corrected at the seam instead of blocking the DAG.
    self_check: list[dict[str, Any]] = []
    path_required_kinds = {"handler_response_receipt", "roundtable_join_receipt"}
    for item in evidence:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "")
        needs_path = kind in path_required_kinds or (kind.endswith("_receipt") and "path" in item)
        if not needs_path:
            continue
        raw_path = item.get("path")
        path = Path(str(raw_path)) if raw_path else None
        if path is not None and path.is_file() and path.stat().st_size > 0:
            continue
        if path is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(
                    json.dumps(
                        {
                            "schema": "ask.repaired_evidence_receipt_stub.v1",
                            "kind": kind,
                            "node_id": args.node_id,
                            "status": status,
                            "note": (
                                "Producer emitted this receipt path without writing the file; "
                                "the handoff self-check materialized this stub so the seam "
                                "contract holds. Treat as degraded evidence."
                            ),
                        },
                        indent=2,
                    )
                    + "\n",
                    encoding="utf-8",
                )
                self_check.append({"kind": kind, "action": "materialized_missing_receipt_stub", "path": str(path)})
                continue
            except OSError as exc:
                self_check.append({"kind": kind, "action": "repair_failed", "error": str(exc)[:200]})
        else:
            self_check.append({"kind": kind, "action": "missing_path_unrepairable"})
    handoff_payload = {
        "schema": "tau.agent_handoff.v1",
        "github": start.get("github", {"repo": "unknown", "target": "unknown"}),
        "goal": start.get("goal", {}),
        "previous_subagent": args.node_id,
        "context": {
            "summary": summary,
            "artifacts": [str(path) for path in artifacts if path.exists()],
        },
        "result": {
            "status": status,
            "summary": summary,
            "evidence": evidence,
            **({"handoff_self_check": self_check} if self_check else {}),
        },
        "rationale": "The node emitted receipt-backed Tau roundtable evidence.",
        "next_agent": {
            "name": args.next_agent,
            "executor": "human" if args.next_agent == "human" else "local",
            "reason": "Return node evidence to the Tau scheduler.",
        },
        "required_evidence": list(args.evidence),
        "stop_condition": "Stop after emitting a single tau.agent_handoff.v1 response.",
    }
    HandoffContract(
        schema=str(handoff_payload.get("schema")),
        goal=handoff_payload.get("goal") or {},
        result=handoff_payload.get("result") or {},
    ).validate()
    return handoff_payload


class CmdResult:
    def __init__(self, command: list[str], returncode: int, stdout: str, stderr: str, duration: float) -> None:
        self.command = command
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.duration = duration

    def summary(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "duration_seconds": round(self.duration, 3),
            "stdout_excerpt": self.stdout.strip()[:1000],
            "stderr_excerpt": self.stderr.strip()[:1000],
        }


def _browser_submit_timeout(
    handler: str,
    provider_timeout: int,
    *,
    command_timeout_budget: int = 0,
) -> int:
    try:
        lock_wait_ms = (
            os.environ["SURF_LOCK_TIMEOUT_MS"]
            if "SURF_LOCK_TIMEOUT_MS" in os.environ
            else "0"
        )
        lock_wait_seconds = max(
            0,
            int(lock_wait_ms or 0) // 1000,
        )
    except ValueError:
        lock_wait_seconds = 60
    if provider_timeout < 30:
        # Forced-timeout tests and manual probes use tiny provider budgets.
        # Those probes should exercise Ask's timeout receipt path immediately
        # instead of inheriting the long production Surf lock envelope.
        lock_wait_seconds = 0
    if handler == "webgpt":
        # webgpt-submit permits three default 300-second rate-limit cooldowns
        # before the final provider observation.
        timeout = max(provider_timeout + (3 * 300) + lock_wait_seconds + 150, 180)
        return _cap_browser_command_timeout(timeout, command_timeout_budget)
    if handler == "webgemini":
        # gemini-submit permits two provider observations separated by its
        # default 120-second stalled-response cooldown.
        timeout = max((2 * (provider_timeout + 60)) + 120 + lock_wait_seconds + 30, 180)
        return _cap_browser_command_timeout(timeout, command_timeout_budget)
    # Claude, Kimi, and Grok receive the provider timeout as a Surf argument.
    # The worker watchdog must be longer than that provider timeout, otherwise
    # Ask kills Surf at the moment Surf should be writing its provider timeout
    # metadata. Keep the grace proportional so tiny debug timeouts remain fast.
    grace_seconds = min(45, max(2, int(provider_timeout * 0.15)))
    timeout = provider_timeout + lock_wait_seconds + grace_seconds
    return _cap_browser_command_timeout(timeout, command_timeout_budget)


def _cap_browser_command_timeout(timeout: int, command_timeout_budget: int) -> int:
    budget = max(0, int(command_timeout_budget or 0))
    if budget <= 0:
        return timeout
    return max(1, min(timeout, budget))


def _browser_timeout_diagnostics(
    *,
    surf_run: Path,
    handler: str,
    tab_id: str,
    url: str,
    prompt_path: Path,
    artifact_dir: Path,
) -> dict[str, Any]:
    if not tab_id:
        return {}
    prompt_text = prompt_path.read_text(encoding="utf-8", errors="replace") if prompt_path.is_file() else ""
    prompt_probe = prompt_text[:500]
    js = r"""
const editable = Array.from(document.querySelectorAll('textarea,[contenteditable="true"],[role="textbox"]'));
const composer = editable.map((el, index) => ({
  index,
  tag: el.tagName,
  role: el.getAttribute('role') || '',
  aria: el.getAttribute('aria-label') || '',
  text: (el.innerText || el.textContent || el.value || '').slice(0, 1200),
  visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
}));
const buttons = Array.from(document.querySelectorAll('button,[role="button"]')).map((el, index) => ({
  index,
  text: (el.innerText || el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 120),
  disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
  visible: !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length)
})).filter(x => x.text);
return JSON.stringify({
  url: location.href,
  title: document.title,
  visibility_state: document.visibilityState,
  body_text: (document.body && document.body.innerText || '').slice(0, 5000),
  composer,
  buttons
});
"""
    snapshot_path = artifact_dir / "browser-timeout-diagnostics.json"
    js_result = _run_cmd(
        [str(surf_run), "js", js, "--tab-id", str(tab_id)],
        cwd=surf_run.parent,
        timeout=20,
    )
    payload: dict[str, Any] = {}
    if js_result.returncode == 0:
        try:
            payload = _parse_json_object(js_result.stdout)
        except (json.JSONDecodeError, RuntimeError):
            payload = {}
    body_text = str(payload.get("body_text") or "")
    composer_items = payload.get("composer") if isinstance(payload.get("composer"), list) else []
    composer_text = "\n".join(str(item.get("text") or "") for item in composer_items if isinstance(item, dict))
    lower = "\n".join([body_text, composer_text, js_result.stderr, js_result.stdout]).lower()
    prompt_still_in_composer = bool(prompt_probe and prompt_probe[:120] in composer_text)
    markers = {
        "provider_busy": any(
            marker in lower
            for marker in (
                "system is currently busy",
                "currently busy",
                "server is busy",
                "high demand",
                "try again later",
            )
        ),
        "provider_rate_limited": any(
            marker in lower
            for marker in (
                "rate limit",
                "too many requests",
                "usage limit",
                "message limit",
                "limit is gone",
                "upgrade to supergrok",
            )
        ),
        "access_blocked": any(
            marker in lower
            for marker in (
                "log in",
                "sign in",
                "verify you are human",
                "captcha",
                "cloudflare",
                "access denied",
            )
        ),
        "possibly_generating": any(
            marker in lower
            for marker in (
                "stop generating",
                "stop responding",
                "stop answer",
                "stop generation",
            )
        ),
        "prompt_still_in_composer": prompt_still_in_composer,
        "composer_nonempty": bool(composer_text.strip()),
    }
    diagnostic = {
        "schema": "ask.browser_timeout_diagnostics.v1",
        "handler": handler,
        "tab_id": str(tab_id),
        "expected_url": url,
        "status": "CAPTURED" if payload else "CAPTURE_FAILED",
        "snapshot_path": str(snapshot_path),
        "js_command": js_result.summary(),
        "url": payload.get("url"),
        "title": payload.get("title"),
        "visibility_state": payload.get("visibility_state"),
        "markers": markers,
        "body_excerpt": body_text[:2000],
        "composer_excerpt": composer_text[:2000],
    }
    snapshot_path.write_text(json.dumps(diagnostic, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return diagnostic


def _run_cmd(command: list[str], *, cwd: Path, timeout: int) -> CmdResult:
    started = time.time()
    proc = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return CmdResult(command, proc.returncode, stdout, stderr, time.time() - started)
    except subprocess.TimeoutExpired:
        _terminate_process_group(proc.pid)
        try:
            stdout, stderr = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            _kill_process_group(proc.pid)
            stdout, stderr = proc.communicate()
        stderr = (
            (stderr or "")
            + f"\n[tau-worker] command timed out after {timeout}s; killed process group rooted at pid {proc.pid}\n"
        )
        return CmdResult(command, 124, stdout or "", stderr, time.time() - started)


def _run_browser_transport_cmd(
    command: list[str],
    *,
    cwd: Path,
    timeout: int,
    handler: str,
    artifact_dir: Path,
    queue_path: Path,
    browser_lock_timeout: int,
) -> CmdResult:
    """Serialize Surf provider submits across Ask workers.

    Concurrent by default: each roundtable lane submits to its own tab, and
    Surf serializes per tab at both the file-lock and host-lease layers, so
    lanes do not wedge each other. Set ASK_BROWSER_TRANSPORT_SERIAL=1 to
    restore the global one-submit-at-a-time queue (a whole submit-and-capture
    cycle per seat, which turns a concurrent panel into a serial one).
    """
    if os.environ.get("ASK_BROWSER_TRANSPORT_SERIAL", "0").lower() in {"0", "false", "no"}:
        return _run_cmd(command, cwd=cwd, timeout=timeout)

    lock_path = Path(os.environ.get("ASK_BROWSER_TRANSPORT_LOCK_FILE", "/tmp/ask-surf-browser-transport.lock"))
    owner_path = Path(str(lock_path) + ".owner.json")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    wait_limit = _browser_transport_wait_limit(browser_lock_timeout=browser_lock_timeout, timeout=timeout)
    started = time.time()
    pid = os.getpid()
    queue_path.parent.mkdir(parents=True, exist_ok=True)

    with lock_path.open("w", encoding="utf-8") as lock_file:
        while True:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                elapsed = time.time() - started
                owner = _read_json(owner_path)
                _write_browser_queue_state(
                    queue_path,
                    status="WAITING",
                    handler=handler,
                    lock_path=lock_path,
                    owner=owner,
                    wait_seconds=elapsed,
                    wait_limit_seconds=wait_limit,
                    pid=pid,
                    artifact_dir=artifact_dir,
                )
                if elapsed >= wait_limit:
                    stderr = (
                        f"surf_browser_lock_timeout: Ask timed out after {wait_limit}s waiting for "
                        f"browser transport lock at {lock_path}. owner={json.dumps(owner, sort_keys=True)}\n"
                    )
                    _write_browser_queue_state(
                        queue_path,
                        status="TIMEOUT",
                        handler=handler,
                        lock_path=lock_path,
                        owner=owner,
                        wait_seconds=elapsed,
                        wait_limit_seconds=wait_limit,
                        pid=pid,
                        artifact_dir=artifact_dir,
                    )
                    return CmdResult(command, 75, "", stderr, time.time() - started)
                time.sleep(min(0.25, max(0.05, wait_limit - elapsed)))

        acquired_at = time.time()
        owner_payload = {
            "schema": "ask.browser_transport_lock_owner.v1",
            "pid": pid,
            "handler": handler,
            "artifact_dir": str(artifact_dir),
            "lock_path": str(lock_path),
            "acquired_at": _now(),
            "command": command[:8],
        }
        owner_path.write_text(json.dumps(owner_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _write_browser_queue_state(
            queue_path,
            status="ACQUIRED",
            handler=handler,
            lock_path=lock_path,
            owner=owner_payload,
            wait_seconds=acquired_at - started,
            wait_limit_seconds=wait_limit,
            pid=pid,
            artifact_dir=artifact_dir,
        )
        try:
            result = _run_cmd(command, cwd=cwd, timeout=timeout)
        finally:
            try:
                current_owner = _read_json(owner_path)
                if str(current_owner.get("pid") or "") == str(pid):
                    owner_path.unlink(missing_ok=True)
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    waited = acquired_at - started
    stderr = result.stderr
    if waited >= 0.1:
        stderr = (
            stderr
            + f"\n[tau-worker] waited {waited:.3f}s for Ask browser transport lock at {lock_path}\n"
        )
    return CmdResult(result.command, result.returncode, result.stdout, stderr, result.duration + waited)


def _browser_transport_wait_limit(*, browser_lock_timeout: int, timeout: int) -> int:
    env_value = os.environ.get("ASK_BROWSER_TRANSPORT_LOCK_TIMEOUT_SECONDS", "").strip()
    if env_value:
        try:
            return max(1, int(env_value))
        except ValueError:
            return 2400
    if browser_lock_timeout > 0:
        return max(1, browser_lock_timeout)
    return max(60, min(timeout, 2400))


def _write_browser_queue_state(
    path: Path,
    *,
    status: str,
    handler: str,
    lock_path: Path,
    owner: dict[str, Any],
    wait_seconds: float,
    wait_limit_seconds: int,
    pid: int,
    artifact_dir: Path,
) -> None:
    payload = {
        "schema": "ask.browser_transport_queue.v1",
        "updated_at": _now(),
        "status": status,
        "handler": handler,
        "pid": pid,
        "lock_path": str(lock_path),
        "wait_seconds": round(wait_seconds, 3),
        "wait_limit_seconds": wait_limit_seconds,
        "owner": owner or None,
        "artifact_dir": str(artifact_dir),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _descendant_pids(root_pid: int) -> list[int]:
    """All descendants of root_pid, crossing setsid boundaries.

    Surf submit scripts run their provider CLI under `setsid`, which moves it
    out of the shell's process group; a plain killpg leaves that CLI alive and
    holding the lane's tab lock (observed: orphaned `cli.cjs chatgpt`/`grok`
    submits surviving the worker watchdog for 10+ minutes).
    """
    children: dict[int, list[int]] = {}
    try:
        out = subprocess.run(
            ["ps", "-eo", "pid=,ppid="], capture_output=True, text=True, timeout=10
        ).stdout
    except Exception:
        return []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        children.setdefault(ppid, []).append(pid)
    found: list[int] = []
    stack = [root_pid]
    while stack:
        current = stack.pop()
        for child in children.get(current, []):
            found.append(child)
            stack.append(child)
    return found


def _signal_process_tree(pid: int, sig: int) -> None:
    descendants = _descendant_pids(pid)
    try:
        os.killpg(pid, sig)
    except ProcessLookupError:
        pass
    except PermissionError:
        try:
            os.kill(pid, sig)
        except ProcessLookupError:
            pass
    for child in descendants:
        try:
            os.kill(child, sig)
        except (ProcessLookupError, PermissionError):
            continue


def _terminate_process_group(pid: int) -> None:
    _signal_process_tree(pid, signal.SIGTERM)


def _kill_process_group(pid: int) -> None:
    _signal_process_tree(pid, signal.SIGKILL)


def _is_subagent_handler_args(args: argparse.Namespace) -> bool:
    return bool(str(getattr(args, "subagent_model", "") or "").strip())


def _provider_transport_for_args(args: argparse.Namespace, handler: str) -> str:
    if handler in HANDLER_SUBMIT_COMMANDS:
        return "$surf"
    if _is_subagent_handler_args(args):
        return "$subagent-runner"
    return "$scillm"


def _transport_for_args(args: argparse.Namespace, handler: str) -> str:
    if handler in HANDLER_SUBMIT_COMMANDS:
        return HANDLER_SUBMIT_COMMANDS[handler]
    if _is_subagent_handler_args(args):
        return "subagent-runner.codex_exec"
    return "scillm.chat"


def _run_subagent_handler(
    args: argparse.Namespace,
    *,
    prompt_path: Path,
    response_path: Path,
    raw_path: Path,
    meta_path: Path,
    artifact_dir: Path,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    """Run a non-mutating Tau subagent handler through /subagent-runner."""

    runner = Path(str(getattr(args, "subagent_runner", "") or "")).expanduser()
    if not runner.is_file():
        raise RuntimeError(f"subagent-runner not found: {runner}")
    model = str(getattr(args, "subagent_model", "") or args.handler).strip()
    requested_model = str(getattr(args, "subagent_requested_model", "") or args.handler).strip()
    reasoning_effort = str(getattr(args, "subagent_reasoning_effort", "") or "high").strip()
    subagent_root = artifact_dir / "subagent-runner"
    subagent_root.mkdir(parents=True, exist_ok=True)
    answer_file = artifact_dir / "subagent-answer.txt"
    spec_file = artifact_dir / "subagent-spec.json"
    answer_file.write_text("", encoding="utf-8")
    task_id = f"ask-tau-{_safe_fragment(args.node_id)}-{int(time.time())}"
    command = [
        "bash",
        "-lc",
        (
            'codex exec --model "$ASK_TAU_SUBAGENT_MODEL" '
            '-c "model_reasoning_effort=\\"$ASK_TAU_SUBAGENT_REASONING\\"" '
            '--sandbox read-only '
            '--skip-git-repo-check '
            '--cd "$ASK_TAU_SUBAGENT_CWD" '
            '--output-last-message "$ASK_TAU_SUBAGENT_ANSWER_FILE" '
            '--color never '
            '- < "$ASK_TAU_SUBAGENT_PROMPT_FILE"'
        ),
    ]
    spec = {
        "task_id": task_id,
        "title": f"/ask Tau subagent handler {args.node_id}",
        "prompt": " ",
        "backend": "codex",
        "command": command,
        "cwd": str(Path.cwd()),
        "output_dir": str(subagent_root),
        "timeout_seconds": int(args.timeout),
        "idle_timeout_seconds": int(max(30, min(args.timeout, 300))),
        "env": {
            "ASK_TAU_SUBAGENT_MODEL": model,
            "ASK_TAU_SUBAGENT_REQUESTED_MODEL": requested_model,
            "ASK_TAU_SUBAGENT_REASONING": reasoning_effort,
            "ASK_TAU_SUBAGENT_CWD": str(Path.cwd()),
            "ASK_TAU_SUBAGENT_ANSWER_FILE": str(answer_file),
            "ASK_TAU_SUBAGENT_PROMPT_FILE": str(prompt_path),
            "SUBAGENT_RUNNER_FINAL_MESSAGE_FILE": str(answer_file),
            "SUBAGENT_RUNNER_IDLE_MODE": "heartbeat",
            "SUBAGENT_RUNNER_HEARTBEAT_INTERVAL": "30",
        },
        "tags": ["ask", "tau", "roundtable", "subagent-runner", model, reasoning_effort],
    }
    spec_file.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    started = _run_cmd([str(runner), "start", str(spec_file)], cwd=runner.parent, timeout=30)
    commands: list[dict[str, Any]] = [started.summary()]
    if started.returncode != 0:
        raise RuntimeError(f"subagent-runner start failed: {started.stderr or started.stdout}")
    start_payload = _parse_json_object(started.stdout)
    session_dir = Path(str(start_payload.get("artifact_dir") or ""))
    if not session_dir.is_dir():
        raise RuntimeError("subagent-runner did not return a readable artifact_dir")
    state = _wait_for_subagent_session(session_dir, timeout=int(args.timeout))
    result = _read_subagent_result(session_dir)
    if str(state.get("status") or "") != "completed":
        transcript = _read_text(session_dir / "transcript.log")[-2000:]
        raise RuntimeError(
            f"subagent-runner session {state.get('status')}: {state.get('status_reason', '')}\n{transcript}"
        )

    response = str(result.get("final_message") or "").strip()
    if not response:
        response = answer_file.read_text(encoding="utf-8", errors="replace").strip()
    if not response:
        response = _read_text(session_dir / "transcript.log").strip()
    if not response:
        raise RuntimeError("subagent-runner completed without answer output")

    raw_path.write_text(response, encoding="utf-8")
    response_path.write_text(response, encoding="utf-8")
    meta = {
        "schema": "ask.subagent_handler_meta.v1",
        "handler": args.handler,
        "requested_handler": requested_model,
        "requested_model": requested_model,
        "model": model,
        "reasoning_effort": reasoning_effort,
        "requested_reasoning_effort": reasoning_effort,
        "transport": "subagent-runner.codex_exec",
        "provider_transport": "$subagent-runner",
        "subagent_runner": str(runner),
        "session_dir": str(session_dir),
        "spec_path": str(spec_file),
        "answer_file": str(answer_file),
        "status": state.get("status"),
        "duration_seconds": result.get("duration_seconds"),
        "finished_at": _now(),
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return response, meta, commands


def _wait_for_subagent_session(session_dir: Path, *, timeout: int) -> dict[str, Any]:
    status_path = session_dir / "status.json"
    deadline = time.monotonic() + timeout
    last_state: dict[str, Any] = {}
    terminal = {"completed", "failed", "cancelled", "timed_out", "stalled"}
    while time.monotonic() < deadline:
        if status_path.is_file():
            try:
                state = _read_json(status_path)
            except (OSError, json.JSONDecodeError, RuntimeError):
                time.sleep(0.2)
                continue
            last_state = state
            if str(state.get("status") or "") in terminal:
                return state
        time.sleep(0.5)
    raise RuntimeError(f"subagent-runner session timeout after {timeout}s: {last_state}")


def _read_subagent_result(session_dir: Path) -> dict[str, Any]:
    result_path = session_dir / "result.json"
    if not result_path.is_file():
        return {}
    try:
        return _read_json(result_path)
    except (OSError, json.JSONDecodeError, RuntimeError):
        return {}


def _read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def _safe_fragment(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", value.strip()).strip("-")
    return cleaned[:64] or "handler"


def _run_codex_handler(
    args: argparse.Namespace,
    *,
    prompt_path: Path,
    response_path: Path,
    raw_path: Path,
    meta_path: Path,
) -> tuple[str, dict[str, Any], list[dict[str, Any]]]:
    """Run the local codex coder inside its bound workspace.

    The node response is codex's final message PLUS the workspace's actual
    `git diff` so the downstream reviewer judges the real change. A run that
    produces no diff is a node failure, not a soft pass.
    """
    workspace = Path(args.codex_workspace).expanduser()
    if not workspace.is_dir() or not (workspace / ".git").exists():
        raise RuntimeError(f"codex workspace is not a git worktree: {workspace}")
    commands: list[dict[str, Any]] = []
    final_message_path = raw_path
    codex_cmd = [
        "codex",
        "exec",
        "-c",
        'model_reasoning_effort="high"',
        "-c",
        "features.hooks=false",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        # codex's bwrap sandbox cannot initialize in this environment
        # (RTM_NEWADDR loopback failure; workspace-write rejects all writes,
        # verified by direct probe 2026-07-21). Containment comes from the
        # isolated git worktree, the diff-only review, and the downstream
        # gates -- not from codex's own sandbox.
        "--sandbox",
        "danger-full-access",
        "--cd",
        str(workspace),
        "-o",
        str(final_message_path),
        "-",
    ]
    prompt_text = prompt_path.read_text(encoding="utf-8")
    started = time.monotonic()
    proc = subprocess.run(
        codex_cmd,
        input=prompt_text,
        capture_output=True,
        text=True,
        timeout=args.timeout,
        cwd=str(workspace),
    )
    duration = time.monotonic() - started
    commands.append(
        {
            "command": codex_cmd[:12] + ["..."],
            "returncode": proc.returncode,
            "duration_seconds": round(duration, 3),
            "stdout_excerpt": (proc.stdout or "")[-1500:],
            "stderr_excerpt": (proc.stderr or "")[-800:],
        }
    )
    if proc.returncode != 0:
        raise RuntimeError(f"codex exec failed rc={proc.returncode}: {(proc.stderr or proc.stdout)[-500:]}")
    diff = subprocess.run(
        ["git", "-C", str(workspace), "diff"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    status_out = subprocess.run(
        ["git", "-C", str(workspace), "status", "--short"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    commands.append(
        {
            "command": ["git", "-C", str(workspace), "diff"],
            "returncode": diff.returncode,
            "duration_seconds": 0,
            "stdout_excerpt": (diff.stdout or "")[:400],
            "stderr_excerpt": (diff.stderr or "")[:200],
        }
    )
    if not (diff.stdout or "").strip() and not (status_out.stdout or "").strip():
        raise RuntimeError("codex_no_workspace_change: coder ran but produced no diff")
    final_message = ""
    if final_message_path.is_file():
        final_message = final_message_path.read_text(encoding="utf-8")
    response = "\n".join(
        [
            "## Coder summary",
            final_message.strip() or "(codex produced no final message)",
            "",
            "## Workspace status",
            "```",
            (status_out.stdout or "").strip(),
            "```",
            "",
            "## Workspace diff (git diff)",
            "```diff",
            (diff.stdout or "").strip()[:60000],
            "```",
            "",
        ]
    )
    response_path.write_text(response, encoding="utf-8")
    meta = {
        "schema": "ask.codex_handler_meta.v1",
        "workspace": str(workspace),
        "codex_returncode": proc.returncode,
        "duration_seconds": round(duration, 3),
        "diff_bytes": len(diff.stdout or ""),
        "finished_at": _now(),
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return response, meta, commands


def _run_scillm_handler(
    args: argparse.Namespace,
    *,
    handler: str,
    prompt_path: Path,
    response_path: Path,
    raw_path: Path,
    meta_path: Path,
) -> tuple[str, dict[str, Any]]:
    prompt = prompt_path.read_text(encoding="utf-8")
    base_url = str(args.scillm_base_url).rstrip("/")
    canonical_handler, canonicalization = _canonicalize_scillm_handler(
        handler,
        str(getattr(args, "provider_hint", "") or ""),
    )
    # Effort-suffix selectors (gpt-5.5-high, ...): the router serves base
    # model names; the suffix becomes reasoning_effort (xhigh -> high).
    model = canonical_handler
    reasoning_effort = None
    for effort in ("xhigh", "high", "medium", "low"):
        if canonical_handler.lower().endswith(f"-{effort}"):
            model = canonical_handler[: -(len(effort) + 1)]
            reasoning_effort = "high" if effort == "xhigh" else effort
            break
    # multimodal: attached images are SHOWN to the model (#1391) — a vision
    # check seat must never judge blind. Non-image attachments are inlined.
    attach_files = [str(item) for item in (getattr(args, "attach_files", None) or [])]
    image_parts = []
    for attachment in attach_files:
        path = Path(attachment)
        if not path.is_file():
            raise RuntimeError(f"scillm attachment missing: {attachment}")
        suffix = path.suffix.lower()
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".gif"}:
            import base64 as _b64
            mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(suffix[1:], f"image/{suffix[1:]}")
            image_parts.append({"type": "image_url", "image_url": {
                "url": f"data:{mime};base64,{_b64.b64encode(path.read_bytes()).decode()}"}})
        else:
            prompt += f"\n\n--- ATTACHED FILE {path.name} ---\n" + path.read_text(encoding="utf-8", errors="replace")[:20000]
    content = ([{"type": "text", "text": prompt}] + image_parts) if image_parts else prompt
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
    }
    # Anthropic rejects `temperature` on current Claude models
    # ("`temperature` is deprecated for this model", observed live on
    # claude-opus-4-8 2026-07-22); other routes keep deterministic sampling.
    if not model.lower().startswith("claude"):
        payload["temperature"] = 0
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url}/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {args.scillm_api_key}",
            "Content-Type": "application/json",
            "X-Caller-Skill": "ask-tau-roundtable",
        },
        method="POST",
    )
    started = time.time()
    try:
        with urllib.request.urlopen(request, timeout=args.timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status_code = response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"scillm.chat failed HTTP {exc.code}: {raw[:1000]}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"scillm.chat failed: {exc}") from exc
    raw_path.write_text(raw, encoding="utf-8")
    payload = _parse_json_object(raw)
    choices = payload.get("choices") if isinstance(payload.get("choices"), list) else []
    message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    if isinstance(content, list):
        text = "\n".join(str(item.get("text") or item) for item in content)
    else:
        text = str(content or "")
    response_path.write_text(text, encoding="utf-8")
    meta = {
        "schema": "ask.tau_dag_scillm_submit_meta.v1",
        "status_code": status_code,
        "model": model,
        "requested_handler": handler,
        "canonical_handler": canonical_handler,
        "provider_hint": str(getattr(args, "provider_hint", "") or "") or None,
        "canonicalization": canonicalization,
        "duration_seconds": round(time.time() - started, 3),
        "usage": payload.get("usage"),
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return text, meta


def _canonicalize_scillm_handler(handler: str, provider_hint: str) -> tuple[str, dict[str, Any] | None]:
    raw = handler.strip()
    hint = provider_hint.strip().lower()
    if raw.lower().startswith("chutes/"):
        canonical = raw.split("/", 1)[1].strip()
        return canonical, {
            "schema": "ask.scillm_handler_canonicalization.v1",
            "status": "AUTO_CONVERTED",
            "from": raw,
            "to": canonical,
            "provider_hint": hint or "chutes",
            "reason": "SciLLM model ids do not include the chutes/ transport prefix.",
        }
    return raw, None


def _excerpt_before_diff(text: str) -> str:
    """Summary portion of a response: everything before a workspace diff block."""
    for marker in ("## Workspace status", "## Workspace diff", "```diff"):
        idx = text.find(marker)
        if idx != -1:
            return text[:idx].strip() + "\n\n(full response including the git diff is attached as a file)"
    return text.strip()


def _load_prior_receipts(node_artifacts_root: Path, prior_nodes: list[str]) -> list[dict[str, Any]]:
    receipts: list[dict[str, Any]] = []
    for node_id in prior_nodes:
        path = node_artifacts_root / node_id / "node-receipt.json"
        if not path.is_file():
            receipts.append(
                {
                    "node_id": node_id,
                    "status": "MISSING",
                    "ok": False,
                    "failure": f"missing prior receipt: {path}",
                    "path": str(path),
                }
            )
            continue
        receipt = _read_json(path)
        response_path = Path(str(receipt.get("response_path") or ""))
        response_excerpt = ""
        if response_path.is_file():
            response_excerpt = response_path.read_text(encoding="utf-8").strip()[:80000]
        receipts.append({"path": str(path), "response_excerpt": response_excerpt, **receipt})
    return receipts


def _requires_verdict(request_text: str, prior_receipts: list[dict[str, Any]]) -> bool:
    if not prior_receipts:
        return False
    lower = request_text.lower()
    return any(
        marker in lower
        for marker in (
            "pass/fail",
            "pass or fail",
            "pass fail",
            "pass-fail",
            "review for pass",
            "review it for pass",
            "review the work for pass",
        )
    )


def _extract_verdict(text: str) -> str | None:
    upper = text.upper()
    for verdict in ("NEEDS_ATTENTION", "PASS", "FAIL"):
        if f"VERDICT: {verdict}" in upper or f"VERDICT {verdict}" in upper:
            return verdict
    return None


def _has_verdict(text: str) -> bool:
    return _extract_verdict(text) is not None


def _read_stdin_handoff() -> dict[str, Any]:
    text = sys.stdin.read()
    if not text.strip():
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"JSON root is not an object: {path}")
    return payload


def _read_optional_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return _read_json(path)
    except (OSError, json.JSONDecodeError, RuntimeError):
        return {}


def _load_webgpt_transport_summary(artifact_dir: Path) -> tuple[Path | None, dict[str, Any]]:
    summary_path = artifact_dir / "webgpt_transport_summary.json"
    if not summary_path.is_file():
        return None, {}
    try:
        payload = _read_json(summary_path)
    except (OSError, json.JSONDecodeError, RuntimeError):
        return None, {}
    if payload.get("schema") != "surf.webgpt_transport_summary.v1":
        return None, {}
    return summary_path, payload


def _parse_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    start = stripped.find("{")
    if start > 0:
        stripped = stripped[start:]
    payload = json.loads(stripped)
    if not isinstance(payload, dict):
        raise RuntimeError("JSON root is not an object")
    return payload


def _parse_json_array_or_tabs(text: str) -> list[dict[str, Any]] | None:
    stripped = text.strip()
    for index, char in enumerate(stripped):
        if char not in "[{":
            continue
        try:
            payload = json.loads(stripped[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            payload = payload.get("tabs", [])
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
    return None


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
