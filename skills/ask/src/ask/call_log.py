"""Every $ask model call, success or failure, persisted to $memory.

Ask reruns the same browser/API seats daily but each lane's outcome evaporated
with its run directory. Recording one `ask_call_log` document per node receipt
at the single execution choke point means the next run can recall "last
successful webgemini call" and what failed before, instead of rediscovering
rate limits and dead tabs live.

Writes are best-effort: memory being down must never fail an ask run.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import httpx

SCHEMA = "ask.call_log.v1"
COLLECTION = "ask_call_log"
RAW_MEMORY_URL = (os.environ.get("MEMORY_SERVICE_URL") or "http://127.0.0.1:8601").rstrip("/")
# unix:// socket env values are served by the same daemon on loopback HTTP.
MEMORY_URL = "http://127.0.0.1:8601" if RAW_MEMORY_URL.startswith("unix://") else RAW_MEMORY_URL


def _handler_of(item: dict[str, Any]) -> str:
    node_id = str(item.get("node_id") or "")
    if node_id.startswith("handler-"):
        return node_id[len("handler-"):]
    return str(item.get("route") or node_id or "unknown")


def _key_for(run_dir: str, node_id: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", f"{Path(run_dir).name}:{node_id}").strip("-")
    return f"ask:{slug}"


def _read_json_path(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _conversation_fields(item: dict[str, Any]) -> dict[str, Any]:
    response_path = item.get("response_path")
    if not response_path:
        return {}
    meta_path = Path(str(response_path)).with_name("response.meta.json")
    meta = _read_json_path(meta_path)
    if meta is None:
        return {}
    return {
        "controlled_tab_id": meta.get("controlled_tab_id"),
        "conversation_url": meta.get("conversation_url"),
    }


def _method_fields(item: dict[str, Any], run_dir: str) -> dict[str, Any]:
    """Denormalize the exact configuration that produced this call's outcome.

    A web-model call must not be a blind guess: the next run needs the proven
    reasoning selection, tab binding, lifecycle mode, and dispatch command of
    the last successful call without spelunking the run directory.
    """
    method: dict[str, Any] = {}
    response_path = item.get("response_path")
    meta: dict[str, Any] | None = None
    if response_path:
        meta = _read_json_path(Path(str(response_path)).with_name("response.meta.json"))
    if meta:
        for key in (
            "requested_model",
            "requested_reasoning",
            "selected_reasoning",
            "reasoning_selection_status",
            "requested_tab_id",
            "requested_url",
            "roundtrip_preflight_required",
            "roundtrip_preflight_exit_code",
        ):
            if meta.get(key) is not None:
                method[key] = meta.get(key)
    root = Path(run_dir) if run_dir else None
    if root and root.is_dir():
        lifecycle = _read_json_path(root / "browser-tab-lifecycle.json")
        if lifecycle:
            for key in ("mode", "cleanup_policy", "identity_guard"):
                if lifecycle.get(key) is not None:
                    method[f"tab_lifecycle_{key}"] = lifecycle.get(key)
            created = lifecycle.get("created_tabs")
            if isinstance(created, list) and created:
                method["created_tabs"] = created
        node_id = str(item.get("node_id") or "")
        if node_id:
            spec = _read_json_path(root / "command-specs" / node_id / "tau-dispatch-command.json")
            command = spec.get("command") if spec else None
            if isinstance(command, list) and command:
                method["dispatch_command"] = _redact_command(command)
    return method


def _redact_command(command: list[Any]) -> list[Any]:
    """Mask values of secret-bearing flags before they reach $memory."""
    redacted = list(command)
    for i, part in enumerate(redacted[:-1]):
        token = str(part or "").lower()
        if token.endswith("api-key") or token.endswith("token") or token.endswith("secret"):
            redacted[i + 1] = "<redacted>"
    return redacted


def document_for(item: dict[str, Any], *, run_dir: str, target: str = "", status: str = "") -> dict[str, Any]:
    node_id = str(item.get("node_id") or "unknown")
    ok = item.get("ok") is True
    failure_code = item.get("failure_code")
    if not ok and not failure_code:
        failure = item.get("failure")
        failure_code = str(failure.get("failure_code") or failure.get("code") or "") if isinstance(failure, dict) else ""
    doc = {
        "schema": SCHEMA,
        "_key": _key_for(run_dir, node_id),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "run_dir": run_dir,
        "target": target or None,
        "node_id": node_id,
        "handler": _handler_of(item),
        "mode": item.get("mode"),
        "model": item.get("model") or item.get("requested_model"),
        "status": "ok" if ok else "error",
        "ok": ok,
        "failure_code": str(failure_code) if failure_code else None,
        "bundle_status": status or None,
        "provider_live": item.get("provider_live") is True,
        "provider_transport": item.get("provider_transport"),
        "response_path": item.get("response_path"),
        "response_chars": item.get("response_chars"),
        "recovery_packet_path": item.get("recovery_packet_path"),
        "retrieval_text": (
            f"{_handler_of(item)} call {'succeeded' if ok else 'failed'}"
            + (f" with {failure_code}" if failure_code else "")
            + f" in run {Path(run_dir).name}"
        ),
    }
    doc.update(_conversation_fields(item))
    method = _method_fields(item, run_dir)
    if method:
        doc["method"] = method
    return doc


def record_from_execution(execution: Any, *, target: str = "", run_dir: str = "") -> list[dict[str, Any]]:
    """Persist one call-log doc per node receipt in an ask execution result.

    Wired where execution-status.json is written; failures never raise.
    """
    if os.environ.get("ASK_CALL_LOG_DISABLED", "").strip().lower() in {"1", "true", "yes"}:
        return []
    if not isinstance(execution, dict):
        return []
    receipts = execution.get("node_provider_receipts")
    if not isinstance(receipts, list) or not receipts:
        return []
    documents = [
        document_for(item, run_dir=str(run_dir or execution.get("receipt_dir") or ""), target=target,
                     status=str(execution.get("status") or ""))
        for item in receipts
        if isinstance(item, dict)
    ]
    if not documents:
        return []
    try:
        response = httpx.post(
            f"{MEMORY_URL}/upsert",
            json={"collection": COLLECTION, "documents": documents},
            timeout=10.0,
            headers={"x-caller-skill": "ask"},
        )
        response.raise_for_status()
        return documents
    except (httpx.HTTPError, OSError):
        return []


def call_history(handler: str, *, limit: int = 50) -> dict[str, Any]:
    """Last successful call, its method, and recent failures for one handler."""
    response = httpx.post(
        f"{MEMORY_URL}/list",
        json={"collection": COLLECTION, "limit": max(limit, 200), "filters": {"handler": handler}},
        timeout=10.0,
        headers={"x-caller-skill": "ask"},
    )
    response.raise_for_status()
    docs = response.json().get("documents") or []
    docs.sort(key=lambda d: str(d.get("ts") or ""), reverse=True)
    last_success = next((d for d in docs if d.get("ok") is True), None)
    failures = [d for d in docs if d.get("ok") is not True and d.get("status") != "retracted_fixture"][:10]
    return {
        "handler": handler,
        "total": len(docs),
        "last_success": last_success,
        "last_success_method": (last_success or {}).get("method"),
        "recent_failures": failures,
    }


def seat_health(handler: str, *, docs: list[dict[str, Any]] | None = None, threshold: int = 3) -> dict[str, Any]:
    """Consecutive-failure health for one browser seat, from ask_call_log.

    A seat that failed N calls in a row with no success since is a known-bad
    seat: including it in a live run burns timeouts and provider cooldowns on
    a lane we already have evidence against.
    """
    if docs is None:
        try:
            response = httpx.post(
                f"{MEMORY_URL}/list",
                json={"collection": COLLECTION, "limit": 200, "filters": {"handler": handler}},
                timeout=10.0,
                headers={"x-caller-skill": "ask"},
            )
            response.raise_for_status()
            docs = response.json().get("documents") or []
        except (httpx.HTTPError, OSError):
            return {"handler": handler, "consecutive_failures": 0, "known_bad": False, "unavailable": True}
    ordered = sorted(docs, key=lambda d: str(d.get("ts") or ""), reverse=True)
    consecutive = 0
    codes: list[str] = []
    for doc in ordered:
        if doc.get("ok") is True:
            break
        if doc.get("status") == "retracted_fixture":
            continue
        consecutive += 1
        code = str(doc.get("failure_code") or "").strip()
        if code and code not in codes:
            codes.append(code)
    last_success = next((d.get("ts") for d in ordered if d.get("ok") is True), None)
    return {
        "handler": handler,
        "consecutive_failures": consecutive,
        "failure_codes": codes,
        "last_success_ts": last_success,
        "known_bad": consecutive >= threshold,
        "unavailable": False,
    }


def last_success_context(handlers: list[str], *, docs_by_handler: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    """Per-handler last-success context for the project agent, from $memory.

    Returned inside every executed ask result so the agent that just consumed
    a handler call also sees, in the same JSON, what last worked for each seat
    and what to avoid — without running a separate history command.
    Best-effort: memory being down omits the field, never fails the run.
    """
    context: dict[str, Any] = {}
    for handler in dict.fromkeys(h for h in handlers if h):
        if docs_by_handler is not None:
            docs = docs_by_handler.get(handler, [])
        else:
            try:
                response = httpx.post(
                    f"{MEMORY_URL}/list",
                    json={"collection": COLLECTION, "limit": 200, "filters": {"handler": handler}},
                    timeout=10.0,
                    headers={"x-caller-skill": "ask"},
                )
                response.raise_for_status()
                docs = response.json().get("documents") or []
            except (httpx.HTTPError, OSError):
                continue
        health = seat_health(handler, docs=docs)
        ordered = sorted(docs, key=lambda d: str(d.get("ts") or ""), reverse=True)
        last = next((d for d in ordered if d.get("ok") is True), None)
        method = (last or {}).get("method") or {}
        if not last:
            context[handler] = {
                "last_success_ts": None,
                "blind_guess": True,
                "consecutive_failures": health.get("consecutive_failures"),
                "avoid_failure_codes": health.get("failure_codes"),
            }
            continue
        context[handler] = {
            "last_success_ts": last.get("ts"),
            "run_dir": last.get("run_dir"),
            "conversation_url": last.get("conversation_url"),
            "controlled_tab_id": last.get("controlled_tab_id"),
            "method": {
                key: method[key]
                for key in (
                    "requested_url",
                    "requested_reasoning",
                    "selected_reasoning",
                    "tab_lifecycle_mode",
                    "layout",
                    "constraint",
                )
                if method.get(key) is not None
            },
            "consecutive_failures": health.get("consecutive_failures"),
            "avoid_failure_codes": health.get("failure_codes"),
            "blind_guess": False,
        }
    return context


def recommendation(handler: str, *, limit: int = 50) -> dict[str, Any]:
    """Non-blind starting point for the next call to this handler.

    Returns the proven method of the last successful call plus the failure
    codes to avoid repeating. When no success is recorded, says so plainly:
    the next call IS a blind guess and the caller should compile-only or probe
    cheaply first.
    """
    history = call_history(handler, limit=limit)
    method = history.get("last_success_method")
    last = history.get("last_success") or {}
    failure_codes: list[str] = []
    for doc in history.get("recent_failures") or []:
        code = str(doc.get("failure_code") or "").strip()
        if code and code not in failure_codes:
            failure_codes.append(code)
    if not method:
        return {
            "schema": "ask.call_recommendation.v1",
            "handler": handler,
            "blind_guess": True,
            "reason": "no successful call recorded in ask_call_log",
            "avoid_failure_codes": failure_codes,
            "next_command": f"python3 skills/ask/scripts/ask_call_history.py --handler {handler} --json",
        }
    return {
        "schema": "ask.call_recommendation.v1",
        "handler": handler,
        "blind_guess": False,
        "reuse": {
            key: value
            for key, value in {
                **{k: method.get(k) for k in (
                    "requested_reasoning",
                    "selected_reasoning",
                    "requested_tab_id",
                    "requested_url",
                    "tab_lifecycle_mode",
                    "tab_lifecycle_cleanup_policy",
                )},
                "controlled_tab_id": last.get("controlled_tab_id"),
                "conversation_url": last.get("conversation_url"),
            }.items()
            if value is not None
        },
        "full_method": method,
        "last_success_ts": (history.get("last_success") or {}).get("ts"),
        "avoid_failure_codes": failure_codes,
    }
