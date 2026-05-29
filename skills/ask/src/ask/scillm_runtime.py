"""Shared /scillm observability helpers for /ask DAG nodes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import httpx

from .ask_config import SCILLM_API_KEY, SCILLM_BASE_URL


CITATION_SCHEMA_VERSION = "ask.citations.v1"
SOURCE_CHUNK_CHARS = 4000
SOURCE_CHUNK_OVERLAP = 200
KNOWLEDGE_CITATION_KINDS = frozenset({"memory", "question", "runtime_health", "dogpile", "fetcher"})
CODE_REVIEW_CITATION_KINDS = frozenset({"target_bundle", "file", "diff", "runtime_artifact", "command_output"})


def stable_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _chunk_source(
    *,
    source_id: str,
    kind: str,
    content: str,
    base_fields: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    fields = dict(base_fields or {})
    if len(content) <= SOURCE_CHUNK_CHARS:
        return [{
            **fields,
            "source_id": source_id,
            "kind": kind,
            "content": content,
            "chunked": False,
        }]
    chunks: list[dict[str, Any]] = []
    start = 0
    index = 1
    step = max(1, SOURCE_CHUNK_CHARS - SOURCE_CHUNK_OVERLAP)
    while start < len(content):
        end = min(len(content), start + SOURCE_CHUNK_CHARS)
        chunks.append({
            **fields,
            "source_id": f"{source_id}.{index}",
            "kind": kind,
            "parent_source_id": source_id,
            "chunk_index": index,
            "chunk_start": start,
            "chunk_end": end,
            "chunked": True,
            "content": content[start:end],
        })
        if end >= len(content):
            break
        start += step
        index += 1
    return chunks


def build_source_bundle(
    *,
    question: str,
    context_items: list[dict[str, Any]] | None = None,
    target_bundle: str | None = None,
    target_entries: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    sources: list[dict[str, Any]] = _chunk_source(source_id="QUESTION", kind="question", content=question)
    for index, item in enumerate(context_items or [], 1):
        sources.extend(
            _chunk_source(
                source_id=f"MEMORY.{index}",
                kind="memory",
                content=str(item.get("solution") or item.get("answer") or item.get("problem") or ""),
                base_fields={"key": str(item.get("_key") or item.get("key") or "")},
            )
        )
    if target_bundle:
        sources.extend(
            _chunk_source(
                source_id="TARGET_BUNDLE",
                kind="target_bundle",
                content=target_bundle,
                base_fields={"entries": target_entries or []},
            )
        )
    serialized = json.dumps(sources, sort_keys=True, default=str)
    return {
        "citation_schema_version": CITATION_SCHEMA_VERSION,
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
        parent_source_id = str(source.get("parent_source_id") or "")
        content = _truncate_source_text(str(source.get("content", "")))
        lines.append(f"[SOURCE {source_id}]")
        if parent_source_id:
            lines.append(f"parent_source_id: {parent_source_id}")
        lines.extend([f"kind: {kind}", content, ""])
    return "\n".join(lines).strip()


def source_ids_from_bundle(source_bundle: dict[str, Any] | None) -> set[str]:
    if not isinstance(source_bundle, dict):
        return set()
    ids: set[str] = set()
    for source in source_bundle.get("sources", []):
        if source.get("source_id"):
            ids.add(str(source["source_id"]))
        if source.get("parent_source_id"):
            ids.add(str(source["parent_source_id"]))
    return ids


def source_kind_by_id(source_bundle: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(source_bundle, dict):
        return {}
    kinds: dict[str, str] = {}
    for source in source_bundle.get("sources", []):
        kind = str(source.get("kind") or "unknown")
        if source.get("source_id"):
            kinds[str(source["source_id"])] = kind
        if source.get("parent_source_id"):
            kinds[str(source["parent_source_id"])] = kind
    return kinds


def normalize_citation(
    value: Any,
    *,
    default_source_kind: str = "",
    supports: str = "",
) -> dict[str, str] | None:
    if isinstance(value, dict):
        source_id = str(value.get("source_id") or "").strip()
        source_kind = str(value.get("source_kind") or value.get("kind") or default_source_kind).strip()
        quote_or_summary = str(value.get("quote_or_summary") or value.get("quote") or value.get("summary") or "").strip()
        citation_supports = str(value.get("supports") or supports).strip()
        if not source_id and _looks_like_source_id(quote_or_summary):
            source_id = quote_or_summary
        if not source_kind and source_id:
            source_kind = _source_kind_for_id(source_id, default_source_kind)
    elif isinstance(value, str):
        quote_or_summary = value.strip()
        source_id = quote_or_summary if _looks_like_source_id(quote_or_summary) else ""
        source_kind = _source_kind_for_id(source_id, default_source_kind) if source_id else default_source_kind
        citation_supports = supports
    else:
        return None
    if not source_id and not quote_or_summary:
        return None
    return {
        "source_id": source_id,
        "source_kind": source_kind,
        "quote_or_summary": quote_or_summary,
        "supports": citation_supports,
    }


def _looks_like_source_id(value: str) -> bool:
    if not value:
        return False
    prefixes = (
        "TARGET.",
        "TARGET_BUNDLE",
        "MEMORY.",
        "QUESTION",
        "DOGPILE.",
        "FETCHER.",
        "COMMAND.",
        "ARTIFACT.",
        "DIFF.",
    )
    return value == "QUESTION" or any(value.startswith(prefix) for prefix in prefixes)


def _source_kind_for_id(source_id: str, default_source_kind: str = "") -> str:
    if source_id.startswith("TARGET.") or source_id.startswith("TARGET_BUNDLE"):
        return "target_bundle"
    if source_id.startswith("MEMORY."):
        return "memory"
    if source_id == "QUESTION":
        return "question"
    if source_id.startswith("DOGPILE."):
        return "dogpile"
    if source_id.startswith("FETCHER."):
        return "fetcher"
    if source_id.startswith("COMMAND."):
        return "command_output"
    if source_id.startswith("ARTIFACT."):
        return "runtime_artifact"
    if source_id.startswith("DIFF."):
        return "diff"
    return default_source_kind


def normalize_citations(
    value: Any,
    *,
    default_source_kind: str = "",
    supports: str = "",
) -> list[dict[str, str]]:
    raw_values = value if isinstance(value, list) else ([] if value is None else [value])
    citations: list[dict[str, str]] = []
    for raw_value in raw_values:
        citation = normalize_citation(raw_value, default_source_kind=default_source_kind, supports=supports)
        if citation:
            citations.append(citation)
    return citations


def memory_citations_from_items(
    items: list[dict[str, Any]],
    *,
    limit: int = 5,
    supports: str = "answer",
) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    for index, item in enumerate(items[:limit], 1):
        text = str(item.get("solution") or item.get("answer") or item.get("text") or item.get("problem") or "").strip()
        if not text:
            continue
        citations.append({
            "source_id": f"MEMORY.{index}",
            "source_kind": "memory",
            "quote_or_summary": text[:280],
            "supports": supports,
        })
    return citations


def target_bundle_citations(
    source_bundle: dict[str, Any] | None,
    *,
    supports: str = "target_review",
    limit: int = 3,
) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    for source in (source_bundle or {}).get("sources", []):
        if source.get("kind") != "target_bundle":
            continue
        content = str(source.get("content") or "").strip()
        citations.append({
            "source_id": str(source.get("source_id")),
            "source_kind": "target_bundle",
            "quote_or_summary": content[:280],
            "supports": supports,
        })
        if len(citations) >= limit:
            break
    return citations


def validate_citations(
    label: str,
    citations: list[dict[str, Any]],
    *,
    source_bundle: dict[str, Any] | None = None,
    allowed_source_kinds: set[str] | frozenset[str] | None = None,
    require_quote: bool = True,
    require_any: bool = False,
) -> list[str]:
    failures: list[str] = []
    allowed_ids = source_ids_from_bundle(source_bundle)
    bundle_kinds = source_kind_by_id(source_bundle)
    if require_any and not citations:
        failures.append(f"{label}: requires at least one structured citation")
    for index, raw_citation in enumerate(citations, 1):
        citation = normalize_citation(raw_citation)
        if not citation:
            failures.append(f"{label}: citation {index} is not a structured citation")
            continue
        source_id = citation["source_id"]
        source_kind = citation["source_kind"]
        if not source_id:
            failures.append(f"{label}: citation {index} missing source_id")
            continue
        if allowed_ids and source_id not in allowed_ids:
            failures.append(f"{label}: citation {source_id} is not in source bundle")
        expected_kind = bundle_kinds.get(source_id)
        if expected_kind and source_kind and source_kind != expected_kind:
            failures.append(f"{label}: citation {source_id} source_kind mismatch")
        effective_kind = expected_kind or source_kind
        if allowed_source_kinds is not None and effective_kind not in allowed_source_kinds:
            failures.append(f"{label}: citation {source_id} has inadmissible source_kind {effective_kind}")
        if require_quote and not citation["quote_or_summary"]:
            failures.append(f"{label}: citation {source_id} missing quote_or_summary")
    return failures


def has_admissible_citation(
    citations: list[dict[str, Any]],
    *,
    source_bundle: dict[str, Any] | None = None,
    allowed_source_kinds: set[str] | frozenset[str],
) -> bool:
    if not citations:
        return False
    return not validate_citations(
        "citation",
        citations,
        source_bundle=source_bundle,
        allowed_source_kinds=allowed_source_kinds,
        require_any=True,
    )


def render_citations_markdown(citations: list[dict[str, Any]]) -> str:
    normalized = normalize_citations(citations)
    if not normalized:
        return "- none"
    return "\n".join(
        f"- [{citation['source_id']}] {citation['quote_or_summary']} ({citation['supports'] or 'support'})"
        for citation in normalized
    )


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
    extra_payload = extra or {}
    identity = source_bundle_id or stable_hash(question)
    cache_key = extra_payload.get("cache_key") or extra_payload.get("prompt_version")
    if cache_key:
        identity = f"{identity}-{stable_hash(str(cache_key))}"
    batch_id = f"ask-{protocol}-{ask_id}-{identity}"
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
    payload.update(extra_payload)
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
