#!/usr/bin/env python3
from __future__ import annotations
"""PersonaPlex P6/P7 live-service adapters with deterministic fallback.

This module intentionally extends the P3-P5 adapter seam instead of replacing the
architecture.  Each adapter first attempts the discovered real endpoint and then
falls back to deterministic file-backed receipts when the service is not
available.  The receipt flags are the authority: a deterministic fallback receipt
is never presented as real memory, real evidence-case, or real Deepgram proof.
"""

import dataclasses
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, MutableMapping

DEFAULT_MEMORY_URL = "http://127.0.0.1:8601"
DEFAULT_EVIDENCE_CASE_URL = "http://127.0.0.1:8601"
DEFAULT_TIMEOUT_SECONDS = 2.5
DEFAULT_SANITY_ROOT = Path("/tmp/personaplex-p6-p7-p8-sanity")

INLINE_VECTOR_KEYS = {
    "vector",
    "vectors",
    "embedding",
    "embeddings",
    "dense_vector",
    "sparse_vector",
    "qdrant_vector",
    "semantic_vector",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(value, sort_keys=True) + "\n")


def body_excerpt(value: str, limit: int = 1200) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "...<truncated>"


def _resolve_url(explicit: str | None, env_names: Iterable[str], default: str) -> str:
    if explicit is not None:
        return explicit.strip()
    for name in env_names:
        if name in os.environ:
            return os.environ.get(name, "").strip()
    return default


def _join_endpoint(base_or_endpoint: str, endpoint_name: str) -> str:
    cleaned = (base_or_endpoint or "").strip().rstrip("/")
    if not cleaned:
        return ""
    suffix = "/" + endpoint_name.strip("/")
    if cleaned.endswith(suffix):
        return cleaned
    return cleaned + suffix


def _safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "record"


def find_inline_vector_paths(value: Any, path: str = "$") -> list[str]:
    """Return JSON paths that look like inline vector payloads.

    The adapters reject explicit vector/embedding keys.  They do not ban every
    numeric list because telemetry can legitimately contain scalar arrays; the
    contract here is that named vector fields are not sent to memory.
    """
    findings: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_str = str(key)
            child_path = f"{path}.{key_str}"
            if key_str.lower() in INLINE_VECTOR_KEYS:
                findings.append(child_path)
            findings.extend(find_inline_vector_paths(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            findings.extend(find_inline_vector_paths(child, f"{path}[{index}]"))
    return findings


@dataclasses.dataclass(frozen=True)
class HttpJsonResult:
    ok: bool
    status: int | None
    body_text: str
    body_json: Any | None
    error: str | None = None


def post_json(url: str, payload: Mapping[str, Any], timeout: float = DEFAULT_TIMEOUT_SECONDS) -> HttpJsonResult:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "personaplex-p6-p7-p8-sanity/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - local configured endpoints only.
            raw = resp.read(65536)
            text = raw.decode("utf-8", errors="replace")
            parsed: Any | None
            try:
                parsed = json.loads(text) if text else None
            except json.JSONDecodeError:
                parsed = None
            status = int(getattr(resp, "status", resp.getcode()))
            return HttpJsonResult(ok=200 <= status < 300, status=status, body_text=text, body_json=parsed)
    except urllib.error.HTTPError as exc:
        raw = exc.read(65536)
        text = raw.decode("utf-8", errors="replace")
        parsed = None
        try:
            parsed = json.loads(text) if text else None
        except json.JSONDecodeError:
            pass
        return HttpJsonResult(ok=False, status=exc.code, body_text=text, body_json=parsed, error=f"http_error:{exc.code}")
    except Exception as exc:  # network, timeout, refused, invalid URL
        return HttpJsonResult(ok=False, status=None, body_text="", body_json=None, error=f"{type(exc).__name__}:{exc}")


def build_conversation_document(
    *,
    session_id: str,
    turn_id: int,
    transcript: str,
    persona_id: str = "embry",
    route_action: str = "COMPLIANCE",
    source: str = "personaplex",
    audio_metadata: Mapping[str, Any] | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    key = f"conversation:{session_id}:{turn_id:06d}"
    retrieval_text = f"PersonaPlex turn {turn_id} for {persona_id}: {transcript}".strip()
    doc: dict[str, Any] = {
        "_key": key,
        "schema": "personaplex.conversation_history.v1",
        "source": source,
        "session_id": session_id,
        "turn_id": turn_id,
        "persona_id": persona_id,
        "route_action": route_action,
        "transcript": transcript,
        "retrieval_text": retrieval_text,
        "created_at_utc": utc_now_iso(),
    }
    if audio_metadata:
        # Audio is represented only by path/hash metadata.  Raw bytes are never
        # embedded in the memory payload.
        doc["audio_metadata"] = dict(audio_metadata)
    if extra:
        doc.update(dict(extra))
    return doc


def _write_memory_fallback(out_dir: Path, collection: str, documents: list[Mapping[str, Any]]) -> list[str]:
    paths: list[str] = []
    for doc in documents:
        key = str(doc.get("_key") or sha256_json(doc))
        path = out_dir / collection / f"{_safe_filename(key)}.json"
        write_json(path, doc)
        paths.append(str(path))
    return paths


def memory_upsert(
    *,
    documents: list[Mapping[str, Any]],
    collection: str = "conversation_history",
    skip_embedding: bool = False,
    memory_url: str | None = None,
    out_dir: str | Path = DEFAULT_SANITY_ROOT,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    """Attempt real memory daemon upsert, falling back to deterministic files.

    The returned receipt is intentionally useful even when the daemon is down:
    `real_memory_upsert` is true only after a 2xx daemon response.
    """
    out = Path(out_dir)
    resolved_url = _resolve_url(memory_url, ("PERSONAPLEX_MEMORY_URL", "MEMORY_URL"), DEFAULT_MEMORY_URL)
    endpoint = _join_endpoint(resolved_url, "upsert")
    payload: dict[str, Any] = {
        "collection": collection,
        "documents": [dict(doc) for doc in documents],
        "skip_embedding": bool(skip_embedding),
    }
    vector_paths = find_inline_vector_paths(payload)
    receipt: dict[str, Any] = {
        "schema": "personaplex.p6.memory_upsert_attempt.v1",
        "created_at_utc": utc_now_iso(),
        "collection": collection,
        "document_count": len(documents),
        "skip_embedding": bool(skip_embedding),
        "endpoint": endpoint or None,
        "attempted": False,
        "real_memory_upsert": False,
        "fallback_used": False,
        "no_inline_vectors": not vector_paths,
        "inline_vector_paths": vector_paths,
        "request_payload_sha256": sha256_json(payload),
    }

    if vector_paths:
        receipt.update(
            {
                "fail_closed": True,
                "unavailable_reason": "inline_vectors_rejected",
                "local_fallback_paths": [],
            }
        )
        write_json(out / "p6-memory-upsert-receipt.json", receipt)
        return receipt

    if not endpoint:
        receipt.update({"unavailable_reason": "memory_url_not_configured"})
    else:
        receipt["attempted"] = True
        started = time.monotonic()
        result = post_json(endpoint, payload, timeout=timeout)
        receipt["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
        receipt["response_status"] = result.status
        receipt["response_body_excerpt"] = body_excerpt(result.body_text)
        if result.ok:
            receipt.update(
                {
                    "real_memory_upsert": True,
                    "fallback_used": False,
                    "response_json": result.body_json if isinstance(result.body_json, Mapping) else None,
                }
            )
            write_json(out / "p6-memory-upsert-receipt.json", receipt)
            return receipt
        receipt["unavailable_reason"] = result.error or "memory_http_non_2xx"

    fallback_paths = _write_memory_fallback(out, collection, [dict(doc) for doc in documents])
    receipt.update(
        {
            "fallback_used": True,
            "local_fallback_paths": fallback_paths,
            "deterministic_key": str(documents[0].get("_key")) if documents else None,
        }
    )
    write_json(out / "p6-memory-upsert-receipt.json", receipt)
    return receipt


def _fallback_evidence_packet(question: str) -> dict[str, Any]:
    return {
        "schema": "personaplex.p7.evidence_case_fallback.v1",
        "selected_route": "/memory /clarify",
        "can_answer": False,
        "question": question,
        "clarify_packet": {
            "reason": "evidence_case_service_unavailable",
            "message": "Create a SPARTA evidence case before releasing a substantive compliance claim.",
        },
    }


def create_evidence_case(
    *,
    question: str,
    evidence_case_url: str | None = None,
    context_framework: str = "SPARTA",
    enable_llm: bool = False,
    include_cae_tree: bool = False,
    fail_on_degraded_evidence: bool = False,
    out_dir: str | Path = DEFAULT_SANITY_ROOT,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> dict[str, Any]:
    out = Path(out_dir)
    resolved_url = _resolve_url(
        evidence_case_url,
        ("PERSONAPLEX_EVIDENCE_CASE_URL", "EVIDENCE_CASE_URL", "PERSONAPLEX_MEMORY_URL", "MEMORY_URL"),
        DEFAULT_EVIDENCE_CASE_URL,
    )
    endpoint = _join_endpoint(resolved_url, "create-evidence-case")
    payload: dict[str, Any] = {
        "question": question,
        "context_framework": context_framework,
        "enable_llm": bool(enable_llm),
        "include_cae_tree": bool(include_cae_tree),
        "fail_on_degraded_evidence": bool(fail_on_degraded_evidence),
    }
    vector_paths = find_inline_vector_paths(payload)
    receipt: dict[str, Any] = {
        "schema": "personaplex.p7.evidence_case_attempt.v1",
        "created_at_utc": utc_now_iso(),
        "route_endpoint": "create-evidence-case",
        "endpoint": endpoint or None,
        "question": question,
        "attempted": False,
        "real_create_evidence_case": False,
        "fallback_used": False,
        "selected_route": "/memory /clarify",
        "can_answer": False,
        "substantive_compliance_claim_released": False,
        "no_inline_vectors": not vector_paths,
        "inline_vector_paths": vector_paths,
        "request_payload_sha256": sha256_json(payload),
    }

    if vector_paths:
        receipt.update({"fail_closed": True, "unavailable_reason": "inline_vectors_rejected"})
        write_json(out / "p7-evidence-case-receipt.json", receipt)
        return receipt

    if not endpoint:
        receipt["unavailable_reason"] = "evidence_case_url_not_configured"
    else:
        receipt["attempted"] = True
        started = time.monotonic()
        result = post_json(endpoint, payload, timeout=timeout)
        receipt["duration_ms"] = round((time.monotonic() - started) * 1000, 3)
        receipt["response_status"] = result.status
        receipt["response_body_excerpt"] = body_excerpt(result.body_text)
        if result.ok:
            receipt.update(
                {
                    "real_create_evidence_case": True,
                    "fallback_used": False,
                    "selected_route": "create-evidence-case",
                    "evidence_case_response_json": result.body_json if isinstance(result.body_json, Mapping) else None,
                    "receipt_hash": sha256_json({"endpoint": endpoint, "payload": payload, "response": result.body_text}),
                }
            )
            write_json(out / "p7-evidence-case-receipt.json", receipt)
            return receipt
        receipt["unavailable_reason"] = result.error or "evidence_case_http_non_2xx"

    fallback = _fallback_evidence_packet(question)
    fallback_path = out / "p7-evidence-case-fallback.json"
    write_json(fallback_path, fallback)
    receipt.update(
        {
            "fallback_used": True,
            "fail_closed": True,
            "local_fallback_path": str(fallback_path),
            "receipt_hash": sha256_json(fallback),
        }
    )
    write_json(out / "p7-evidence-case-receipt.json", receipt)
    return receipt


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="PersonaPlex P6/P7 adapter smoke probe")
    parser.add_argument("--out-dir", default=str(DEFAULT_SANITY_ROOT))
    parser.add_argument("--memory-url", default=None)
    parser.add_argument("--evidence-case-url", default=None)
    parser.add_argument("--question", default="Focus on the west gateway.")
    parser.add_argument("--transcript", default="Focus on the west gateway.")
    parser.add_argument("--session-id", default="p6p7-session")
    parser.add_argument("--turn-id", type=int, default=1)
    parser.add_argument("--persona-id", default="embry")
    parser.add_argument("--require-real", action="store_true", help="Exit 2 unless both real P6 and P7 endpoints succeed.")
    args = parser.parse_args(argv)

    doc = build_conversation_document(
        session_id=args.session_id,
        turn_id=args.turn_id,
        persona_id=args.persona_id,
        transcript=args.transcript,
    )
    memory = memory_upsert(documents=[doc], memory_url=args.memory_url, out_dir=args.out_dir)
    evidence = create_evidence_case(question=args.question, evidence_case_url=args.evidence_case_url, out_dir=args.out_dir)
    combined = {
        "schema": "personaplex.p6_p7.adapter_smoke_receipt.v1",
        "created_at_utc": utc_now_iso(),
        "ok": True,
        "real_memory_upsert": bool(memory.get("real_memory_upsert")),
        "real_create_evidence_case": bool(evidence.get("real_create_evidence_case")),
        "memory_upsert_attempt": memory,
        "evidence_case_attempt": evidence,
        "claim_boundary": "Adapter smoke. Deterministic fallback is not real memory/evidence proof unless real_* flags are true.",
    }
    receipt_path = write_json(Path(args.out_dir) / "p6-p7-adapter-smoke-receipt.json", combined)
    print(json.dumps({"receipt_path": str(receipt_path), **combined}, indent=2, sort_keys=True, default=_json_default))
    if args.require_real and not (combined["real_memory_upsert"] and combined["real_create_evidence_case"]):
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
