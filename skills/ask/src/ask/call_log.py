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


def _conversation_fields(item: dict[str, Any]) -> dict[str, Any]:
    response_path = item.get("response_path")
    if not response_path:
        return {}
    meta_path = Path(str(response_path)).with_name("response.meta.json")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        "controlled_tab_id": meta.get("controlled_tab_id"),
        "conversation_url": meta.get("conversation_url"),
    }


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
    """Last successful call and recent failures for one handler, from $memory."""
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
    return {"handler": handler, "total": len(docs), "last_success": last_success, "recent_failures": failures}
