"""Shared /scillm observability helpers for /ask DAG nodes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx

from .ask_config import SCILLM_API_KEY, SCILLM_BASE_URL


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def build_source_bundle(
    *,
    question: str,
    context_items: list[dict[str, Any]] | None = None,
    target_bundle: str | None = None,
    target_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sources: list[dict[str, Any]] = [{"source_id": "QUESTION", "kind": "question", "content": question}]
    for index, item in enumerate(context_items or [], 1):
        sources.append(
            {
                "source_id": f"MEMORY.{index}",
                "kind": "memory",
                "key": str(item.get("_key") or item.get("key") or ""),
                "content": str(item.get("solution") or item.get("answer") or item.get("problem") or ""),
            }
        )
    if target_bundle:
        sources.append(
            {
                "source_id": "TARGET_BUNDLE",
                "kind": "target_bundle",
                "entries": target_entries or [],
                "content": target_bundle,
            }
        )
    serialized = json.dumps(sources, sort_keys=True, default=str)
    return {
        "source_bundle_id": stable_hash(serialized),
        "sources": sources,
    }


def _truncate_source_text(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n[TRUNCATED]"


def serialize_source_bundle(source_bundle: dict[str, Any] | None) -> str | None:
    if not source_bundle:
        return None
    lines: list[str] = []
    for source in source_bundle.get("sources", []):
        source_id = str(source.get("source_id", "SOURCE"))
        kind = str(source.get("kind", "unknown"))
        content = _truncate_source_text(str(source.get("content", "")))
        lines.extend([
            f"[SOURCE {source_id}]",
            f"kind: {kind}",
            content,
            "",
        ])
    return "\n".join(lines).strip()


def build_scillm_metadata(
    *,
    ask_id: str,
    protocol: str,
    node_id: str,
    node_role: str,
    question: str,
    artifact_dir: Path | str,
    source_bundle_id: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    batch_id = f"ask-{protocol}-{ask_id}"
    payload = {
        "ask_id": ask_id,
        "protocol": protocol,
        "node_id": node_id,
        "node_role": node_role,
        "batch_id": batch_id,
        "item_id": node_id,
        "question_hash": stable_hash(question),
        "source_bundle_id": source_bundle_id,
        "artifact_dir": str(artifact_dir),
    }
    payload.update(extra or {})
    return payload


def extract_scillm_observability(response_payload: dict[str, Any], requested_metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "call_id": str(response_payload.get("id") or response_payload.get("call_id") or ""),
        "model": str(response_payload.get("model") or ""),
        "metadata_requested": requested_metadata,
        "metadata_returned": response_payload.get("scillm_metadata") or response_payload.get("metadata") or {},
        "grounding_score": response_payload.get("grounding_score"),
        "grounding_passed": response_payload.get("grounding_passed"),
        "debug_url": response_payload.get("debug_url") or "",
        "batch_resumed": bool(response_payload.get("batch_resumed") or response_payload.get("resumed")),
    }


def scillm_grounding_degraded(scillm: dict[str, Any] | None) -> bool:
    if not isinstance(scillm, dict):
        return False
    status = str(scillm.get("source_grounding_status") or "")
    return status in {"retry_without_source_after_error", "failed_before_response_with_source"} or scillm.get("grounding_passed") is False


def scillm_metadata_observability_degraded(scillm: dict[str, Any] | None) -> bool:
    if not isinstance(scillm, dict):
        return False
    requested = scillm.get("metadata_requested")
    returned = scillm.get("metadata_returned")
    if not isinstance(requested, dict) or not requested:
        return False
    if not isinstance(returned, dict) or not returned:
        return True
    return bool(scillm_metadata_mismatch_failures("scillm", scillm))


def scillm_metadata_mismatch_failures(label: str, scillm: dict[str, Any] | None) -> list[str]:
    if not isinstance(scillm, dict):
        return []
    requested = scillm.get("metadata_requested")
    returned = scillm.get("metadata_returned")
    if not isinstance(requested, dict) or not requested or not isinstance(returned, dict) or not returned:
        return []
    failures: list[str] = []
    for key in ("ask_id", "protocol", "node_id", "batch_id", "item_id"):
        expected = requested.get(key)
        actual = returned.get(key)
        if expected is not None and actual is not None and actual != expected:
            failures.append(f"{label}: scillm_metadata returned {key} mismatch")
    return failures


def summarize_scillm_observability(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    grounding_degraded = False
    observability_degraded = False
    metadata_failures: list[str] = []
    for node in nodes:
        if not isinstance(node, dict):
            continue
        label = str(node.get("reviewer") or node.get("side") or node.get("judge") or "node")
        scillm = node.get("scillm")
        if scillm_grounding_degraded(scillm):
            grounding_degraded = True
        if scillm_metadata_observability_degraded(scillm):
            observability_degraded = True
        metadata_failures.extend(scillm_metadata_mismatch_failures(label, scillm))
    return {
        "grounding_degraded": grounding_degraded,
        "observability_degraded": observability_degraded,
        "metadata_failures": metadata_failures,
    }


def scillm_error_advice(exc: BaseException) -> dict[str, Any]:
    if not isinstance(exc, httpx.HTTPStatusError):
        return {}
    try:
        payload = exc.response.json()
    except Exception:
        return {"http_status": exc.response.status_code}
    error = payload.get("error") if isinstance(payload, dict) else None
    if not isinstance(error, dict):
        return {"http_status": exc.response.status_code, "response": payload}
    return {
        "http_status": exc.response.status_code,
        "message": error.get("message", ""),
        "type": error.get("type", ""),
        "code": error.get("code", ""),
        "advice": error.get("advice", ""),
        "recommendation": error.get("recommendation", ""),
        "debug_url": error.get("debug_url", ""),
    }


def fetch_recent_scillm_debug(caller: str = "ask", limit: int = 1) -> dict[str, Any]:
    try:
        response = httpx.get(
            f"{SCILLM_BASE_URL.rstrip('/')}/v1/scillm/debug",
            params={"caller": caller, "limit": limit},
            headers={
                "Authorization": f"Bearer {SCILLM_API_KEY}",
                "X-Caller-Skill": "ask",
            },
            timeout=5.0,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        return {"status": "unavailable", "error": str(exc)}
    if isinstance(payload, dict):
        return {"status": "ok", "payload": payload}
    return {"status": "ok", "payload": {"items": payload}}
