#!/usr/bin/env python3
"""Tau worker for live $ask roundtable browser handler nodes."""

from __future__ import annotations

import argparse
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
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


load_dotenv()


HANDLER_BACKENDS = {
    "webgpt": "webgpt",
    "webclaude": "webclaude",
    "webkimi": "webkimi",
    "webgemini": "webgemini",
    "webgrok": "webgrok",
}
HANDLER_SUBMIT_COMMANDS = {
    "webgpt": "webgpt.submit",
    "webclaude": "claude.submit",
    "webkimi": "kimi.submit",
    "webgemini": "gemini.submit",
    "webgrok": "grok.submit",
}
ATTACH_FILE_HANDLERS = {"webgpt", "webclaude", "webkimi", "webgemini", "webgrok"}
RECOVERY_PACKET_SCHEMA = "ask.browser_failure_recovery_packet.v1"
HANDLER_RECOVERY_PACKET_SCHEMA = "ask.handler_failure_recovery_packet.v1"
WEBGPT_CONVERSATION_FULL_BLOCKER = "BLOCKED_WEBGPT_CONVERSATION_FULL"
WEBGPT_BINDING_STALE_BLOCKER = "BLOCKED_WEBGPT_BINDING_STALE"
BROWSER_TAB_IDENTITY_MISMATCH = "browser_tab_identity_mismatch"
BROWSER_TAB_READ_TIMEOUT = "browser_tab_read_timeout"
BROWSER_ACCESS_BLOCKED = "browser_access_blocked"
BROWSER_PROVIDER_RATE_LIMITED = "browser_provider_rate_limited"
BROWSER_TOOL_UNSUPPORTED = "browser_tool_unsupported"
SURF_BROWSER_LOCK_TIMEOUT = "surf_browser_lock_timeout"
SURF_BROWSER_CONNECTION_UNAVAILABLE = "surf_browser_connection_unavailable"
BROWSER_TRANSPORT_BLOCKERS = {
    WEBGPT_CONVERSATION_FULL_BLOCKER,
    WEBGPT_BINDING_STALE_BLOCKER,
    BROWSER_TAB_IDENTITY_MISMATCH,
    BROWSER_TAB_READ_TIMEOUT,
    BROWSER_ACCESS_BLOCKED,
    BROWSER_PROVIDER_RATE_LIMITED,
    BROWSER_TOOL_UNSUPPORTED,
    SURF_BROWSER_LOCK_TIMEOUT,
    SURF_BROWSER_CONNECTION_UNAVAILABLE,
    "repo_access_blocked",
    "missing_sentinel",
    "prompt_too_large_or_stalled",
    "stale_raw_capture",
}


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
    parser.add_argument("--stable-polls", type=int, default=2)
    parser.add_argument("--no-activate", action="store_true")
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--codex-workspace", default="")
    parser.add_argument("--browser-model-preference", default="")
    parser.add_argument("--subagent-runner", default="")
    parser.add_argument("--subagent-model", default="")
    parser.add_argument("--subagent-reasoning-effort", default="")
    parser.add_argument("--subagent-requested-model", default="")
    args = parser.parse_args()
    if args.handler in HANDLER_SUBMIT_COMMANDS:
        os.environ.setdefault("SURF_LOCK_TIMEOUT_MS", "1800000")

    start = _read_stdin_handoff()
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    if args.node_id == "join":
        result = _run_join(args, start, artifact_dir)
    else:
        result = _run_handler(args, start, artifact_dir)
    print(json.dumps(result["handoff"], sort_keys=True))
    return int(result["exit_code"])


def _run_handler(args: argparse.Namespace, start: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
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
            inline_full=handler not in HANDLER_SUBMIT_COMMANDS and handler != "codex",
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
    binding_refresh: dict[str, Any] | None = None
    submit_prompt_path = prompt_path
    browser_attachment_paths: list[str] = []
    browser_local_path_preflight: dict[str, Any] | None = None
    failure = ""
    recovery_packet: dict[str, Any] | None = None
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
            submit = _run_cmd(
                submit_cmd,
                cwd=Path(args.surf_run).parent,
                timeout=_browser_submit_timeout(handler, args.timeout),
            )
            commands.append(submit.summary())
            if meta_path.is_file():
                submit_meta = _read_json(meta_path)
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
        if recovery_packet.get("failure_code") in BROWSER_TRANSPORT_BLOCKERS:
            status = "BLOCKED"
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
        recovery_packet_path.write_text(
            json.dumps(recovery_packet, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        status = "NEEDS_ATTENTION"

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
        "raw_response_path": str(raw_path),
        "meta_path": str(meta_path),
        "transport_summary_path": str(transport_summary_path) if transport_summary_path else None,
        "webgpt_transport_summary": transport_summary or None,
        "prompt_path": str(prompt_path),
        "browser_prompt_path": str(submit_prompt_path) if submit_prompt_path != prompt_path else None,
        "browser_attachment_paths": browser_attachment_paths,
        "browser_local_path_preflight": browser_local_path_preflight,
        "recovery_packet_path": str(recovery_packet_path) if recovery_packet else None,
        "response_chars": len(response_text),
        "browser_oracle": resolve_payload,
        "browser_oracle_binding_refresh": binding_refresh,
        "browser_model_preference": str(getattr(args, "browser_model_preference", "") or "") or None,
        "submit_meta": submit_meta,
        "commands": commands,
        "prior_nodes": list(args.prior_node),
        "prior_handler_receipts": prior_receipts,
        "requires_verdict": _requires_verdict(request_text, prior_receipts),
        "verdict": verdict,
        "failure": failure or None,
        "failure_code": recovery_packet.get("failure_code") if recovery_packet else None,
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
        },
        {
            "kind": "normalized_handler_receipt",
            "node_id": args.node_id,
            "handler": handler,
            "response_path": str(response_path),
            "response_chars": len(response_text),
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
    artifacts = [receipt_path, prompt_path, response_path, raw_path, meta_path, recovery_packet_path]
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
    ]
    if tab_id:
        command.extend(["--tab-id", tab_id])
    if url:
        if handler == "webgpt":
            command.extend(["--expect-url", url] if tab_id else ["--url", url])
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
    if not local_candidates:
        return (
            prompt_path,
            combined_attachments,
            {
                "schema": "ask.browser_local_path_preflight.v1",
                "status": "PASS",
                "local_path_count": 0,
                "attached_file_count": len(combined_attachments),
                "sanitized_prompt_path": None,
            },
        )

    attached_by_resolved = {str(Path(path).resolve()): index + 1 for index, path in enumerate(combined_attachments)}
    sanitized = prompt_text
    replacements: list[dict[str, Any]] = []
    for candidate in local_candidates:
        path = Path(candidate).expanduser()
        label = "local-only path not attached"
        attachment_index = None
        if path.is_file():
            try:
                attachment_index = attached_by_resolved.get(str(path.resolve()))
            except OSError:
                attachment_index = None
        if attachment_index is not None:
            label = f"attached local evidence file ATTACHMENT_{attachment_index}"
        replacement = f"[{label}: {path.name}]"
        sanitized = sanitized.replace(candidate, replacement)
        replacements.append(
            {
                "path": candidate,
                "file_exists": path.is_file(),
                "attached": attachment_index is not None,
                "attachment_index": attachment_index,
                "replacement": replacement,
            }
        )

    sanitized_prompt_path = prompt_path.with_name("browser-readable-prompt.md")
    attachment_lines = []
    for index, path in enumerate(combined_attachments, start=1):
        attachment_lines.append(f"- ATTACHMENT_{index}: {Path(path).name}")
    if attachment_lines:
        sanitized += "\n\nLocal evidence attachments available to the browser model:\n" + "\n".join(attachment_lines)
        sanitized += "\nUse the attached files as source material; do not rely on local filesystem paths.\n"
    sanitized_prompt_path.write_text(sanitized, encoding="utf-8")
    return (
        sanitized_prompt_path,
        combined_attachments,
        {
            "schema": "ask.browser_local_path_preflight.v1",
            "status": "PASS" if handler in ATTACH_FILE_HANDLERS or not readable_bundle_paths else "NEEDS_ATTENTION",
            "local_path_count": len(local_candidates),
            "attached_file_count": len(combined_attachments),
            "sanitized_prompt_path": str(sanitized_prompt_path),
            "replacements": replacements,
        },
    )


def _local_path_candidates(text: str) -> list[str]:
    candidates: list[str] = []
    for candidate in _extract_path_candidates(text):
        if candidate.startswith("//") or "://" in candidate:
            continue
        path = Path(candidate).expanduser()
        if not path.is_absolute():
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


def _should_retry_browser_stale_binding(
    *,
    handler: str,
    url: str,
    submit_meta: dict[str, Any],
    submit: CmdResult,
) -> bool:
    if handler not in HANDLER_SUBMIT_COMMANDS or not url:
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
            timeout=_browser_submit_timeout(handler, args.timeout),
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
    open_tab = _run_cmd([str(args.surf_run), "tab.new", url], cwd=Path(args.surf_run).parent, timeout=90)
    open_summary = open_tab.summary()
    open_summary["recovery_attempt"] = "webgpt_stale_binding_open_url"
    commands.append(open_summary)
    if open_tab.returncode != 0 and "browser lock" in (open_tab.stderr + open_tab.stdout).lower():
        open_tab = _run_cmd(
            [str(args.surf_run), "tab.new", url, "--no-lock"],
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
        timeout=_browser_submit_timeout(handler, args.timeout),
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
    try:
        payload = json.loads(tab_list.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        payload = payload.get("tabs", [])
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
    if handler != "webclaude":
        return {"status": "skipped", "reason": "handler_not_presubmit_refreshable"}
    live_url = _live_tab_url(args.surf_run, tab_id, commands=commands)
    if not live_url:
        return {"status": "skipped", "reason": "live_tab_url_unavailable"}
    if not _is_claude_new_to_chat_transition(previous_url, live_url):
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
    try:
        payload = json.loads(tab_list.stdout)
    except json.JSONDecodeError:
        return ""
    if isinstance(payload, dict):
        payload = payload.get("tabs", [])
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
        failure=failure,
        response_text=response_text,
        raw_text=raw_text,
        prompt_text=prompt_text,
        submit_meta=submit_meta,
        commands=commands,
    )
    bundle_paths = _local_readable_bundle_paths(prompt_text, request_payload)
    can_attach = handler in ATTACH_FILE_HANDLERS
    auto_retry_allowed = (
        failure_code
        not in {
            WEBGPT_CONVERSATION_FULL_BLOCKER,
            WEBGPT_BINDING_STALE_BLOCKER,
            BROWSER_TAB_IDENTITY_MISMATCH,
            BROWSER_TAB_READ_TIMEOUT,
            BROWSER_ACCESS_BLOCKED,
            BROWSER_PROVIDER_RATE_LIMITED,
            BROWSER_TOOL_UNSUPPORTED,
        }
        and bool(bundle_paths)
        and can_attach
    )
    stale_binding = _webgpt_stale_binding_details(submit_meta)
    surf_lock_blocker = _surf_lock_blocker_details(failure=failure, commands=commands, submit_meta=submit_meta)
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
        prompt_path=prompt_path,
    )
    return {
        "schema": RECOVERY_PACKET_SCHEMA,
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
            "submit_meta_status": submit_meta.get("status") or submit_meta.get("status_code"),
            "last_command": commands[-1] if commands else None,
            "stale_binding": stale_binding,
            "surf_lock_blocker": surf_lock_blocker,
        },
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
    }


def _classify_browser_failure(
    *,
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
            json.dumps(submit_meta, sort_keys=True, default=str),
            json.dumps(commands[-1] if commands else {}, sort_keys=True, default=str),
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
    if _looks_surf_browser_lock_timeout(haystack, commands, submit_meta):
        return SURF_BROWSER_LOCK_TIMEOUT
    if _looks_surf_browser_connection_unavailable(haystack):
        return SURF_BROWSER_CONNECTION_UNAVAILABLE
    if _looks_browser_provider_rate_limited(haystack, submit_meta):
        return BROWSER_PROVIDER_RATE_LIMITED
    if _looks_browser_access_blocked(haystack, submit_meta):
        return BROWSER_ACCESS_BLOCKED
    if _looks_browser_tool_unsupported(haystack):
        return BROWSER_TOOL_UNSUPPORTED
    if _looks_repo_access_blocked(haystack):
        return "repo_access_blocked"
    if _looks_tab_identity_mismatch(haystack, submit_meta):
        return BROWSER_TAB_IDENTITY_MISMATCH
    if _looks_stale_raw_capture(haystack, submit_meta):
        return "stale_raw_capture"
    if _looks_browser_tab_read_timeout(haystack):
        return BROWSER_TAB_READ_TIMEOUT
    if _looks_prompt_too_large_or_stalled(haystack):
        return "prompt_too_large_or_stalled"
    if _looks_missing_sentinel(haystack, submit_meta):
        return "missing_sentinel"
    return "missing_sentinel"


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


def _looks_browser_access_blocked(text: str, meta: dict[str, Any]) -> bool:
    if meta.get("browser_access_blocked") is True or meta.get("cloudflare_challenge_detected") is True:
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
    markers = (
        "too many requests",
        "you've hit your limit",
        "you have hit your limit",
        "please try again later",
        "system is currently busy",
        "capacity is busy",
        "provider_capacity_limited",
        "temporarily limited access",
        "rate_limited",
        "browser_provider_rate_limited",
    )
    return any(marker in text for marker in markers)


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


def _surf_lock_blocker_details(
    *, failure: str, commands: list[dict[str, Any]], submit_meta: dict[str, Any]
) -> dict[str, Any]:
    candidates: list[str] = [failure, json.dumps(submit_meta, sort_keys=True, default=str)]
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
    owner_match = re.search(
        r"owner_pid=(?P<pid>\S+).*?owner_created_at=(?P<created_at>\S+).*?owner_socket=(?P<socket>\S+).*?lock_dir=(?P<lock_dir>\S+)",
        haystack,
        flags=re.IGNORECASE | re.DOTALL,
    )
    owner: dict[str, Any] | None = None
    lock_dir = None
    if owner_match:
        pid_text = owner_match.group("pid")
        owner = {
            "pid": int(pid_text) if pid_text.isdigit() else pid_text,
            "created_at": owner_match.group("created_at"),
            "socket": owner_match.group("socket"),
        }
        lock_dir = owner_match.group("lock_dir")
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


def _looks_prompt_too_large_or_stalled(text: str) -> bool:
    markers = (
        "timed out",
        "timeout",
        "stalled",
        "hang",
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
    if failure_code == WEBGPT_CONVERSATION_FULL_BLOCKER:
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
            "--create-tab",
        ]
        if args.browser_oracle_project:
            command.extend(["--project", str(args.browser_oracle_project)])
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
        ]
        tab_id = str(browser_oracle.get("tab_id") or browser_oracle.get("controlled_tab_id") or "").strip()
        url = str(browser_oracle.get("conversation_url") or "").strip()
        if tab_id:
            command.extend(["--tab-id", tab_id])
        if url:
            command.extend(["--expect-url" if str(args.handler) == "webgpt" else "--url", url])
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
            "--attach-file",
            bundle_path,
        ]
        tab_id = ""
        if isinstance(browser_oracle, dict):
            tab_id = str(browser_oracle.get("tab_id") or browser_oracle.get("controlled_tab_id") or "")
        if not tab_id:
            tab_id = _tab_id_from_commands(args)
        if tab_id:
            command.extend(["--tab-id", tab_id])
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
    if str(args.browser_oracle_project or ""):
        command.extend(["--handler-project", f"{args.handler}={args.browser_oracle_project}"])
    return command


def _tab_id_from_commands(args: argparse.Namespace) -> str:
    # The primary receipt keeps browser-oracle resolution separately; tests and
    # recovery packets still need a deterministic fallback when only args exist.
    return ""


def _recovery_reason(failure_code: str) -> str:
    return {
        WEBGPT_CONVERSATION_FULL_BLOCKER: "The controlled ChatGPT conversation is at its maximum length and cannot accept the WebGPT round.",
        WEBGPT_BINDING_STALE_BLOCKER: "The browser-oracle binding points at a stale ChatGPT URL; the controlled tab is open at a different live URL.",
        BROWSER_TAB_IDENTITY_MISMATCH: "The browser-oracle binding or requested tab does not match the live browser tab URL.",
        BROWSER_TAB_READ_TIMEOUT: "The bound browser tab was reachable by identity but did not respond to Surf page reads.",
        BROWSER_ACCESS_BLOCKED: "The browser provider presented an access challenge before the request could be submitted.",
        BROWSER_PROVIDER_RATE_LIMITED: "The browser provider accepted routing but reported a provider-side request limit.",
        BROWSER_TOOL_UNSUPPORTED: "The Surf wrapper called a browser tool name that the installed surf-cli runtime does not support.",
        SURF_BROWSER_LOCK_TIMEOUT: "The Surf browser lock is held by another live command; the browser lane was not submitted.",
        SURF_BROWSER_CONNECTION_UNAVAILABLE: "The Surf native host or socket disconnected before the browser lane completed.",
        "repo_access_blocked": "The browser reviewer appears unable to read the referenced repository or local path.",
        "missing_sentinel": "The browser transport did not produce the expected completion sentinel.",
        "prompt_too_large_or_stalled": "The browser submit appears to have timed out, stalled, or exceeded prompt size limits.",
        "stale_raw_capture": "The raw browser capture appears to be from the wrong or stale assistant turn.",
    }[failure_code]


def _auto_retry_blocked_reason(
    *, failure_code: str, bundle_paths: list[str], can_attach: bool
) -> str:
    if failure_code == WEBGPT_CONVERSATION_FULL_BLOCKER:
        return "conversation_full_requires_fresh_chatgpt_conversation"
    if failure_code == WEBGPT_BINDING_STALE_BLOCKER:
        return "browser_oracle_binding_stale_rebind_required"
    if failure_code == BROWSER_TAB_IDENTITY_MISMATCH:
        return "browser_tab_identity_rebind_required"
    if failure_code == BROWSER_TAB_READ_TIMEOUT:
        return "browser_tab_read_timeout_rebind_required"
    if failure_code == BROWSER_ACCESS_BLOCKED:
        return "browser_access_challenge_requires_human_browser_recovery"
    if failure_code == BROWSER_PROVIDER_RATE_LIMITED:
        return "browser_provider_rate_limit_requires_backoff"
    if failure_code == BROWSER_TOOL_UNSUPPORTED:
        return "surf_runtime_command_mismatch_requires_repair"
    if failure_code == SURF_BROWSER_LOCK_TIMEOUT:
        return "surf_browser_lock_owner_still_running"
    if failure_code == SURF_BROWSER_CONNECTION_UNAVAILABLE:
        return "surf_browser_connection_must_recover"
    if not bundle_paths:
        return "missing_local_readable_bundle"
    if not can_attach:
        return "handler_transport_does_not_support_attach_file"
    return "unknown"


def _fallback_instruction(failure_code: str, *, has_bundle: bool, can_attach: bool, handler: str) -> str:
    if failure_code == WEBGPT_CONVERSATION_FULL_BLOCKER:
        return (
            "Do not wait or retry in the same conversation. Rebind browser-oracle to a fresh ChatGPT "
            "conversation, then rerun the Tau DAG node."
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
    if failure_code == BROWSER_TOOL_UNSUPPORTED:
        return "Repair the Surf wrapper/provider adapter command mapping, then rerun the Tau DAG node. Do not retry the same browser call unchanged."
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
    if has_bundle and not can_attach:
        return (
            f"Do not auto-retry {handler}: the current Surf transport does not expose --attach-file for this handler. "
            "Use a handler with attachment support or add attachment support before retrying."
        )
    if has_bundle and can_attach:
        return "Run the next_command; it resubmits a concise prompt with the readable local bundle attached."
    if failure_code == "repo_access_blocked":
        return (
            "Create a local readable review bundle, or grant/add the repository through the browser provider's GitHub integration, "
            "then rerun the next_command with the bundle path in the request."
        )
    if failure_code == "prompt_too_large_or_stalled":
        return "Write the target material to a local readable bundle and rerun with that bundle instead of inlining a large prompt."
    if failure_code == "stale_raw_capture":
        return "Refresh or rebind the browser-oracle tab, then rerun the next_command; do not reuse the stale raw capture."
    return "Rerun only after the browser tab is responsive or a local readable bundle is available."


def _requires_local_readable_bundle(failure_code: str) -> bool:
    return failure_code not in {
        WEBGPT_CONVERSATION_FULL_BLOCKER,
        WEBGPT_BINDING_STALE_BLOCKER,
        BROWSER_TAB_IDENTITY_MISMATCH,
        BROWSER_TAB_READ_TIMEOUT,
        BROWSER_ACCESS_BLOCKED,
        BROWSER_PROVIDER_RATE_LIMITED,
        BROWSER_TOOL_UNSUPPORTED,
        SURF_BROWSER_LOCK_TIMEOUT,
        SURF_BROWSER_CONNECTION_UNAVAILABLE,
        "stale_raw_capture",
    }


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
    }


def _classify_handler_failure(*, handler: str, failure: str, submit_meta: dict[str, Any]) -> str:
    haystack = "\n".join([handler, failure, json.dumps(submit_meta, sort_keys=True, default=str)]).lower()
    if "prior_handler_receipts_not_ready" in haystack:
        return "prior_handler_receipts_not_ready"
    if (
        "http 401" in haystack
        or "invalid api key" in haystack
        or "authentication_error" in haystack
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
            "failure_code": receipt.get("failure_code") or _classify_handler_failure(
                handler=str(receipt.get("handler") or ""),
                failure=str(receipt.get("failure") or ""),
                submit_meta=receipt.get("submit_meta") if isinstance(receipt.get("submit_meta"), dict) else {},
            ),
            "recovery_packet_path": receipt.get("recovery_packet_path"),
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
        if response_path.is_file():
            text = response_path.read_text(encoding="utf-8").strip()
            lines.append(text[:2000])
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
            lines.extend(
                [
                    f"- `{item.get('node_id')}` / `{item.get('handler')}`: `{item.get('failure_code')}`",
                    f"  recovery: `{item.get('recovery_packet_path') or 'missing'}`",
                ]
            )
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
            "next_command": next_command or None,
            "auto_retry_allowed": recovery_packet.get("auto_retry_allowed"),
            "auto_retry_blocked_reason": recovery_packet.get("auto_retry_blocked_reason"),
        }
        failed_seats.append(failed)
        if next_command:
            recovery_commands.append(
                {
                    "node_id": failure.get("node_id"),
                    "handler": failure.get("handler"),
                    "failure_code": code,
                    "next_command": next_command,
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
    revision_path = artifact_dir / "winner-revision-request.md"
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
    if tied:
        blockers.append("winner_tie_requires_project_agent_review")
    if not candidate_winner_handler:
        blockers.append("no_clear_winner_from_receipts")
    if not all_verified_features:
        blockers.append("no_explicit_verified_features_to_promote")
    if transport_blockers:
        blockers.append("competition_transport_blocked")
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

    revision_lines = [
        "# Winner Revision Request",
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
        revision_lines.extend(f"- {feature}" for feature in all_verified_features)
    else:
        revision_lines.append("- NEEDS_ATTENTION: no candidate emitted explicit VERIFIED_FEATURE lines.")
    revision_lines.extend(
        [
            "",
            "Instructions to the winner:",
            "- Keep the winning implementation as the base.",
            "- Add only the listed verified features that still pass local deterministic checks.",
            "- Do not import unverified candidate claims.",
            "- Return changed files, commands run, proof artifacts, and unresolved blockers.",
        ]
    )
    revision_path.write_text("\n".join(str(line) for line in revision_lines).rstrip() + "\n", encoding="utf-8")

    scorecard = {
        "schema": "ask.tau_dag_compete_scorecard.v1",
        "created_at": _now(),
        "status": status,
        "ok": ok,
        "mocked": False,
        "live": any(item["live"] for item in handler_receipts),
        "provider_live": ok and all(item["provider_live"] for item in handler_receipts),
        "winner_handler": winner_handler,
        "winner_node_id": winner.get("node_id") if winner and winner_handler else "",
        "selection_basis": "deterministic_receipts_and_explicit_verified_feature_markers",
        "failure_kind": "transport" if transport_blockers else ("semantic_or_evidence" if blockers else "none"),
        "candidates": handler_receipts,
        "transport_blockers": transport_blockers,
        "verified_features": all_verified_features,
        "blockers": blockers,
        "degradation_analysis": degradation_analysis,
        "revision_request_path": str(revision_path),
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
        "revision_request_path": str(revision_path),
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
        artifacts=[receipt_path, scorecard_path, revision_path, summary_path],
        evidence=[
            {"kind": "compete_scorecard", "path": str(scorecard_path), "status": status},
            {"kind": "degradation_analysis", **degradation_analysis},
            {"kind": "verified_feature_packet", "count": len(all_verified_features), "items": all_verified_features},
            {"kind": "winner_revision_request", "path": str(revision_path), "winner_handler": winner_handler},
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
            }
        )
        if next_command:
            recovery_commands.append(
                {
                    "node_id": candidate.get("node_id"),
                    "handler": candidate.get("handler"),
                    "failure_code": code,
                    "next_command": next_command,
                }
            )
    if status == "PASS":
        why = f"Winner `{winner_handler}` selected from receipt-backed verified features."
    elif not candidates:
        why = "No candidate receipts were available, so the competition cannot be scored."
    elif failed_candidates:
        why = (
            f"{len(failed_candidates)} of {len(candidates)} candidate lane(s) failed or need attention; "
            f"{len(verified_features)} explicit VERIFIED_FEATURE item(s) were available."
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
            lines.extend(
                [
                    f"- `{item.get('node_id')}` / `{item.get('handler')}`: `{item.get('failure_code')}`",
                    f"  recovery: `{item.get('recovery_packet_path') or 'missing'}`",
                ]
            )
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
) -> str:
    prior_receipts = prior_receipts or []
    lines = [
        (
            "You are one isolated competitor in a Tau-managed implementation competition."
            if workflow_mode == "compete"
            else "You are one participant in a Tau-managed roundtable."
        ),
        f"Handler: {handler}",
        "",
        "Request:",
        request_text,
        "",
    ]
    if model_preference:
        lines.extend(["Browser model preference:", model_preference, ""])
    if workflow_mode == "compete":
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
    if requires_verdict:
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
    return {
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


def _browser_submit_timeout(handler: str, provider_timeout: int) -> int:
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
    if handler == "webgpt":
        # webgpt-submit permits three default 300-second rate-limit cooldowns
        # before the final provider observation.
        return max(provider_timeout + (3 * 300) + lock_wait_seconds + 150, 180)
    if handler == "webgemini":
        # gemini-submit permits two provider observations separated by its
        # default 120-second stalled-response cooldown.
        return max((2 * (provider_timeout + 60)) + 120 + lock_wait_seconds + 30, 180)
    return max(provider_timeout + lock_wait_seconds + 90, 180)


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


def _terminate_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    except PermissionError:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return


def _kill_process_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except ProcessLookupError:
        return
    except PermissionError:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            return


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
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
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


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
