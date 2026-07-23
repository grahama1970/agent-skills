#!/usr/bin/env python3
"""Tau worker for live $ask roundtable browser handler nodes."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


HANDLER_BACKENDS = {
    "webgpt": "webgpt",
    "webclaude": "webclaude",
    "webkimi": "webkimi",
    "webgemini": "webgemini",
}
HANDLER_SUBMIT_COMMANDS = {
    "webgpt": "webgpt.submit",
    "webclaude": "claude.submit",
    "webkimi": "kimi.submit",
    "webgemini": "gemini.submit",
}
ATTACH_FILE_HANDLERS = {"webgpt", "webkimi", "webgemini"}
RECOVERY_PACKET_SCHEMA = "ask.browser_failure_recovery_packet.v1"
WEBGPT_CONVERSATION_FULL_BLOCKER = "BLOCKED_WEBGPT_CONVERSATION_FULL"
WEBGPT_BINDING_STALE_BLOCKER = "BLOCKED_WEBGPT_BINDING_STALE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--handler", required=True)
    parser.add_argument("--topology", required=True)
    parser.add_argument("--request-file", required=True)
    parser.add_argument("--browser-oracle-project", default="")
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
    args = parser.parse_args()

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
    recovery_packet_path = artifact_dir / "browser-recovery-packet.json"
    commands: list[dict[str, Any]] = []
    prior_receipts = _load_prior_receipts(artifact_dir.parent, args.prior_node)
    prompt_path.write_text(
        _handler_prompt(
            request_text,
            handler,
            prior_receipts=prior_receipts,
            requires_verdict=_requires_verdict(request_text, prior_receipts),
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
        if handler == "codex":
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

            submit_cmd = [
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
                "--tab-id",
                tab_id,
                "--timeout",
                str(args.timeout),
                "--stable-polls",
                str(args.stable_polls),
            ]
            if url:
                if handler == "webgpt":
                    submit_cmd.extend(["--expect-url", url])
                else:
                    submit_cmd.extend(["--url", url])
            for prior in prior_receipts:
                prior_response = str(prior.get("response_path") or "")
                if prior_response and Path(prior_response).is_file():
                    submit_cmd.extend(["--attach-file", prior_response])
            if args.no_activate:
                submit_cmd.append("--no-activate")
            submit = _run_cmd(submit_cmd, cwd=Path(args.surf_run).parent, timeout=max(args.timeout + 90, 180))
            commands.append(submit.summary())
            if meta_path.is_file():
                submit_meta = _read_json(meta_path)
            transport_summary_path, transport_summary = _load_webgpt_transport_summary(artifact_dir)
            if submit.returncode != 0:
                raise RuntimeError(submit.stderr or submit.stdout or f"{HANDLER_SUBMIT_COMMANDS[handler]} failed")
            response_text = response_path.read_text(encoding="utf-8")
            binding_refresh = _refresh_webgpt_binding_after_proven_submit(
                args,
                project=project,
                tab_id=tab_id,
                previous_url=url,
                submit_meta=submit_meta,
                commands=commands,
            )
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
                    "command": ["scillm.chat", handler],
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
        if recovery_packet.get("failure_code") in {
            WEBGPT_CONVERSATION_FULL_BLOCKER,
            WEBGPT_BINDING_STALE_BLOCKER,
        }:
            status = "BLOCKED"

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
        "recovery_packet_path": str(recovery_packet_path) if recovery_packet else None,
        "response_chars": len(response_text),
        "browser_oracle": resolve_payload,
        "browser_oracle_binding_refresh": binding_refresh,
        "submit_meta": submit_meta,
        "commands": commands,
        "prior_nodes": list(args.prior_node),
        "prior_handler_receipts": prior_receipts,
        "requires_verdict": _requires_verdict(request_text, prior_receipts),
        "verdict": verdict,
        "failure": failure or None,
        "failure_code": recovery_packet.get("failure_code") if recovery_packet else None,
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
            "provider_transport": "$surf",
            "handler": handler,
            "transport": HANDLER_SUBMIT_COMMANDS.get(handler, f"{handler}.local"),
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
    return {"exit_code": 0 if ok else 1, "handoff": handoff}


def _refresh_webgpt_binding_after_proven_submit(
    args: argparse.Namespace,
    *,
    project: str,
    tab_id: str,
    previous_url: str,
    submit_meta: dict[str, Any],
    commands: list[dict[str, Any]],
) -> dict[str, Any]:
    if str(args.handler) != "webgpt":
        return {"status": "skipped", "reason": "handler_not_webgpt"}
    current_url = _proven_live_webgpt_conversation_url(submit_meta)
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
    bind_cmd = [
        str(args.browser_oracle_run),
        "bind",
        project,
        "--backend",
        "webgpt",
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
            "BLOCKED_WEBGPT_BINDING_REFRESH_FAILED: "
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
        failure_code not in {WEBGPT_CONVERSATION_FULL_BLOCKER, WEBGPT_BINDING_STALE_BLOCKER}
        and bool(bundle_paths)
        and can_attach
    )
    stale_binding = _webgpt_stale_binding_details(submit_meta)
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
        },
        "local_readable_bundle_paths": bundle_paths,
        "requires_local_readable_bundle": True,
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
            prompt_text,
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
    if _looks_repo_access_blocked(haystack):
        return "repo_access_blocked"
    if _looks_stale_raw_capture(haystack, submit_meta):
        return "stale_raw_capture"
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
    bare = re.findall(r"(?<![\w:])(/[^\s`'\"<>]+)", text)
    return [item.rstrip(").,;:]") for item in [*quoted, *bare]]


def _is_bundle_like(path: Path) -> bool:
    name = path.name.lower()
    suffixes = "".join(path.suffixes).lower()
    if any(token in name for token in ("bundle", "review", "target", "evidence", "handoff")):
        return True
    return suffixes in {
        ".md",
        ".txt",
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


def _run_join(args: argparse.Namespace, start: dict[str, Any], artifact_dir: Path) -> dict[str, Any]:
    receipt_path = artifact_dir / "node-receipt.json"
    summary_path = artifact_dir / "roundtable-summary.md"
    node_artifacts_root = artifact_dir.parent
    handler_receipts = []
    failures = []
    for path in sorted(node_artifacts_root.glob("handler-*/node-receipt.json")):
        receipt = _read_json(path)
        if receipt.get("schema") != "ask.tau_dag_handler_receipt.v1":
            continue
        handler_receipts.append({"path": str(path), **receipt})
        if receipt.get("ok") is not True:
            failures.append(f"{receipt.get('node_id')}: {receipt.get('failure') or receipt.get('status')}")
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
    ok = bool(handler_receipts) and not failures
    status = "PASS" if ok else "BLOCKED"
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
            {"kind": "handler_response_index", "count": len(handler_receipts), "failures": failures},
            {"kind": "unresolved_gaps", "items": failures},
        ],
    )
    return {"exit_code": 0 if ok else 1, "handoff": handoff}


def _handler_prompt(
    request_text: str,
    handler: str,
    *,
    prior_receipts: list[dict[str, Any]] | None = None,
    requires_verdict: bool = False,
    inline_full: bool = False,
) -> str:
    prior_receipts = prior_receipts or []
    lines = [
        "You are one participant in a Tau-managed roundtable.",
        f"Handler: {handler}",
        "",
        "Request:",
        request_text,
        "",
    ]
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


def _run_cmd(command: list[str], *, cwd: Path, timeout: int) -> CmdResult:
    started = time.time()
    proc = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return CmdResult(command, proc.returncode, proc.stdout, proc.stderr, time.time() - started)


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
    # Effort-suffix selectors (gpt-5.5-high, ...): the router serves base
    # model names; the suffix becomes reasoning_effort (xhigh -> high).
    model = handler
    reasoning_effort = None
    for effort in ("xhigh", "high", "medium", "low"):
        if handler.lower().endswith(f"-{effort}"):
            model = handler[: -(len(effort) + 1)]
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
        "model": handler,
        "duration_seconds": round(time.time() - started, 3),
        "usage": payload.get("usage"),
    }
    meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return text, meta


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
