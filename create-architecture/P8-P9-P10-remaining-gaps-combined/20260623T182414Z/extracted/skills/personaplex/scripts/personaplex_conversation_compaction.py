#!/usr/bin/env python3
from __future__ import annotations
"""PersonaPlex P9 conversation-compaction persistence adapter.

The persistence ownership model implemented here is intentionally conservative:

- ``conversation_history`` remains the canonical immutable turn ledger.
- ``conversation_history_summaries`` contains immutable rolling summaries whose
  source turn keys are stored explicitly.
- ``personaplex_sessions`` is the mutable session head; the adapter performs a
  client-side generation check before upsert and records that the generic memory
  daemon upsert endpoint is not, by itself, a server-side CAS primitive.
- ``conversation_audio_artifacts`` stores path/hash/format metadata only.
- ``personaplex_turns`` is a derived projection and is marked non-canonical.

The memory daemon endpoint available to this bundle is ``POST /upsert``.  The
receipt therefore reports both the real daemon upsert result and the CAS mode
honestly.  No inline vectors are ever included in payloads.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from personaplex_p3_p5_live_services import (
    DEFAULT_MEMORY_URL,
    DEFAULT_SANITY_ROOT,
    DEFAULT_TIMEOUT_SECONDS,
    find_inline_vector_paths,
    memory_upsert,
    safe_filename,
    sha256_file,
    sha256_json,
    utc_now_iso,
    write_json,
)

FIXTURE_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "p8_p9_p10" / "conversation_turns_fixture.json"


def load_turn_fixture() -> list[dict[str, Any]]:
    if FIXTURE_PATH.exists():
        data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [dict(item) for item in data]
        if isinstance(data, Mapping) and isinstance(data.get("turns"), list):
            return [dict(item) for item in data["turns"]]
    return [
        {
            "_key": "conversation:p9-fixture-session:000001",
            "session_id": "p9-fixture-session",
            "turn_id": 1,
            "persona_id": "embry",
            "transcript": "Focus on the west gateway.",
            "retrieval_text": "PersonaPlex turn 1 for embry: Focus on the west gateway.",
        }
    ]


def _chunks(items: Sequence[Mapping[str, Any]], size: int) -> Iterable[list[Mapping[str, Any]]]:
    safe_size = max(1, int(size))
    for index in range(0, len(items), safe_size):
        yield list(items[index : index + safe_size])


def normalize_turn_documents(
    turns: Sequence[Mapping[str, Any]],
    *,
    session_id: str,
    persona_id: str,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for idx, raw in enumerate(turns, start=1):
        turn_id = int(raw.get("turn_id") or idx)
        transcript = str(raw.get("transcript") or raw.get("text") or "").strip()
        key = str(raw.get("_key") or f"conversation:{session_id}:{turn_id:06d}")
        doc = dict(raw)
        doc.update(
            {
                "_key": key,
                "schema": doc.get("schema") or "personaplex.conversation_history.v1",
                "source": doc.get("source") or "personaplex",
                "session_id": str(doc.get("session_id") or session_id),
                "turn_id": turn_id,
                "persona_id": str(doc.get("persona_id") or persona_id),
                "transcript": transcript,
                "retrieval_text": str(
                    doc.get("retrieval_text")
                    or f"PersonaPlex turn {turn_id} for {doc.get('persona_id') or persona_id}: {transcript}"
                ),
                "immutability": {"canonical_ledger": True, "mutated_in_place": False},
                "vector_lifecycle": {
                    "embedding_owner": "memory_daemon",
                    "embedding_requested": True,
                    "inline_vectors_present": False,
                },
                "updated_by_p9_compaction": True,
            }
        )
        normalized.append(doc)
    return normalized


def build_audio_artifact_document(
    *,
    session_id: str,
    turn_id: int,
    audio: str | Path | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(audio, Mapping):
        meta = dict(audio)
        raw_path = meta.get("path") or meta.get("audio_path") or meta.get("source_path")
        path = Path(str(raw_path)).expanduser() if raw_path else None
    else:
        path = Path(audio).expanduser()
        meta = {"path": str(path)}

    if path is not None:
        meta["path"] = str(path)
        meta["exists"] = path.exists()
        if path.exists() and path.is_file():
            meta.setdefault("size_bytes", path.stat().st_size)
            meta.setdefault("sha256", sha256_file(path))
        else:
            meta.setdefault("size_bytes", None)
    else:
        meta.setdefault("exists", False)

    # Do not store bytes or base64; path/hash/format metadata only.
    for forbidden in ("bytes", "raw", "raw_audio", "base64", "data"):
        meta.pop(forbidden, None)

    identity = meta.get("sha256") or meta.get("path") or sha256_json(meta)
    key = f"audio:{session_id}:{turn_id:06d}:{str(identity)[:24].replace('/', '_')}"
    return {
        "_key": safe_filename(key),
        "schema": "personaplex.conversation_audio_artifact.v1",
        "session_id": session_id,
        "turn_id": turn_id,
        "metadata": meta,
        "created_at_utc": utc_now_iso(),
        "storage_policy": {
            "inline_audio_bytes_present": False,
            "payload_kind": "path_hash_metadata_only",
            "content_addressable": bool(meta.get("sha256")),
        },
        "vector_lifecycle": {
            "embedding_owner": None,
            "embedding_requested": False,
            "inline_vectors_present": False,
        },
    }


def deterministic_summary_text(turns: Sequence[Mapping[str, Any]]) -> str:
    parts: list[str] = []
    for doc in turns:
        turn_id = doc.get("turn_id")
        transcript = str(doc.get("transcript") or "").strip()
        if transcript:
            parts.append(f"Turn {turn_id}: {transcript}")
    return " | ".join(parts) if parts else "No transcript text was available for this compaction window."


def build_summary_document(
    *,
    session_id: str,
    persona_id: str,
    summary_index: int,
    source_turns: Sequence[Mapping[str, Any]],
    previous_summary_key: str | None = None,
    audio_artifact_keys: Sequence[str] | None = None,
) -> dict[str, Any]:
    source_turn_keys = [str(doc["_key"]) for doc in source_turns]
    summary_text = deterministic_summary_text(source_turns)
    identity = sha256_json({"source_turn_keys": source_turn_keys, "summary_text": summary_text, "previous": previous_summary_key})
    key = f"summary:{session_id}:{summary_index:06d}:{identity[:16]}"
    return {
        "_key": safe_filename(key),
        "schema": "personaplex.conversation_history_summary.v1",
        "session_id": session_id,
        "persona_id": persona_id,
        "summary_index": summary_index,
        "summary_text": summary_text,
        "retrieval_text": f"PersonaPlex rolling summary for {persona_id}: {summary_text}",
        "source_turn_keys": source_turn_keys,
        "source_turn_count": len(source_turn_keys),
        "previous_summary_key": previous_summary_key,
        "audio_artifact_keys": list(audio_artifact_keys or []),
        "created_at_utc": utc_now_iso(),
        "immutability": {
            "canonical_source_keys": source_turn_keys,
            "mutated_in_place": False,
            "replacement_policy": "write_new_summary_record",
        },
        "graph_lifecycle": {
            "source_collection": "conversation_history",
            "source_turn_keys": source_turn_keys,
            "derived_edges_owner": "graph_builder_or_memory_daemon",
            "derived_edges_status": "pending_or_external",
        },
        "vector_lifecycle": {
            "embedding_owner": "memory_daemon",
            "embedding_requested": True,
            "inline_vectors_present": False,
        },
    }


def build_projection_document(turn: Mapping[str, Any], latest_summary_key: str | None) -> dict[str, Any]:
    key = f"turn_projection:{turn.get('session_id')}:{int(turn.get('turn_id') or 0):06d}"
    return {
        "_key": safe_filename(key),
        "schema": "personaplex.turn_projection.v1",
        "canonical": False,
        "source_collection": "conversation_history",
        "source_turn_key": turn.get("_key"),
        "session_id": turn.get("session_id"),
        "turn_id": turn.get("turn_id"),
        "persona_id": turn.get("persona_id"),
        "latest_summary_key": latest_summary_key,
        "created_at_utc": utc_now_iso(),
        "projection_policy": "derived_projection_never_canonical",
    }


def build_session_head_document(
    *,
    session_id: str,
    persona_id: str,
    active_turn_key: str | None,
    latest_summary_key: str | None,
    source_turn_keys: Sequence[str],
    source_summary_keys: Sequence[str],
    generation: int,
    expected_previous_generation: int,
    previous_head: Mapping[str, Any] | None,
    audio_artifact_keys: Sequence[str],
) -> dict[str, Any]:
    previous_head_sha256 = sha256_json(previous_head) if previous_head else None
    return {
        "_key": safe_filename(f"session:{session_id}"),
        "schema": "personaplex.session_head.v1",
        "session_id": session_id,
        "persona_id": persona_id,
        "generation": generation,
        "active_turn_key": active_turn_key,
        "latest_summary_key": latest_summary_key,
        "source_turn_keys": list(source_turn_keys),
        "source_summary_keys": list(source_summary_keys),
        "audio_artifact_keys": list(audio_artifact_keys),
        "updated_at_utc": utc_now_iso(),
        "cas": {
            "mode": "client_checked_then_memory_daemon_upsert",
            "expected_previous_generation": expected_previous_generation,
            "new_generation": generation,
            "previous_head_supplied": previous_head is not None,
            "previous_head_sha256": previous_head_sha256,
            "daemon_cas_endpoint_available": False,
            "daemon_enforced": False,
        },
        "vector_lifecycle": {
            "embedding_owner": None,
            "embedding_requested": False,
            "inline_vectors_present": False,
        },
    }


def _preflight_no_inline_vectors(collection_payloads: Sequence[Mapping[str, Any]]) -> list[str]:
    return find_inline_vector_paths({"planned_memory_payloads": list(collection_payloads)})


def run_conversation_compaction(
    *,
    turn_documents: Sequence[Mapping[str, Any]] | None = None,
    session_id: str = "p9-session",
    persona_id: str = "embry",
    memory_url: str | None = None,
    out_dir: str | Path = DEFAULT_SANITY_ROOT,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_turns_per_summary: int = 4,
    audio_artifacts: Sequence[str | Path | Mapping[str, Any]] | None = None,
    previous_head: Mapping[str, Any] | None = None,
    expected_previous_generation: int = 0,
    update_projection: bool = True,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    raw_turns = list(turn_documents or load_turn_fixture())
    turns = normalize_turn_documents(raw_turns, session_id=session_id, persona_id=persona_id)

    previous_generation = int(previous_head.get("generation", 0)) if previous_head else expected_previous_generation
    if previous_head is not None and previous_generation != expected_previous_generation:
        receipt = {
            "schema": "personaplex.p9.conversation_compaction_receipt.v1",
            "created_at_utc": utc_now_iso(),
            "ok": False,
            "real_conversation_compaction": False,
            "fallback_used": False,
            "fail_closed": True,
            "unavailable_reason": "cas_generation_mismatch",
            "cas_update_attempted": False,
            "cas_update_applied": False,
            "expected_previous_generation": expected_previous_generation,
            "observed_previous_generation": previous_generation,
            "claim_boundary": "No memory mutation attempted because the client-side CAS preflight failed.",
        }
        write_json(out / "p9-conversation-compaction-receipt.json", receipt)
        return receipt

    audio_docs: list[dict[str, Any]] = []
    artifacts = list(audio_artifacts or [])
    if not artifacts:
        for turn in turns:
            metadata = turn.get("audio_metadata")
            if isinstance(metadata, Mapping):
                artifacts.append({**metadata, "turn_id": turn.get("turn_id")})
    for index, artifact in enumerate(artifacts):
        turn_id = 0
        if isinstance(artifact, Mapping):
            turn_id = int(artifact.get("turn_id") or artifact.get("source_turn_id") or index + 1)
        else:
            turn_id = index + 1
        audio_docs.append(build_audio_artifact_document(session_id=session_id, turn_id=turn_id, audio=artifact))

    summaries: list[dict[str, Any]] = []
    previous_summary_key: str | None = None
    audio_keys = [doc["_key"] for doc in audio_docs]
    for summary_index, chunk in enumerate(_chunks(turns, max_turns_per_summary), start=1):
        summary = build_summary_document(
            session_id=session_id,
            persona_id=persona_id,
            summary_index=summary_index,
            source_turns=chunk,
            previous_summary_key=previous_summary_key,
            audio_artifact_keys=audio_keys,
        )
        summaries.append(summary)
        previous_summary_key = summary["_key"]

    source_turn_keys = [str(doc["_key"]) for doc in turns]
    source_summary_keys = [str(doc["_key"]) for doc in summaries]
    active_turn_key = source_turn_keys[-1] if source_turn_keys else None
    latest_summary_key = source_summary_keys[-1] if source_summary_keys else None
    session_head = build_session_head_document(
        session_id=session_id,
        persona_id=persona_id,
        active_turn_key=active_turn_key,
        latest_summary_key=latest_summary_key,
        source_turn_keys=source_turn_keys,
        source_summary_keys=source_summary_keys,
        generation=expected_previous_generation + 1,
        expected_previous_generation=expected_previous_generation,
        previous_head=previous_head,
        audio_artifact_keys=audio_keys,
    )
    projections = [build_projection_document(turn, latest_summary_key) for turn in turns] if update_projection else []

    planned_payloads: list[dict[str, Any]] = [
        {"collection": "conversation_history", "documents": turns, "skip_embedding": False},
        {"collection": "conversation_history_summaries", "documents": summaries, "skip_embedding": False},
        {"collection": "personaplex_sessions", "documents": [session_head], "skip_embedding": True},
    ]
    if audio_docs:
        planned_payloads.append({"collection": "conversation_audio_artifacts", "documents": audio_docs, "skip_embedding": True})
    if projections:
        planned_payloads.append({"collection": "personaplex_turns", "documents": projections, "skip_embedding": True})
    vector_paths = _preflight_no_inline_vectors(planned_payloads)
    if vector_paths:
        receipt = {
            "schema": "personaplex.p9.conversation_compaction_receipt.v1",
            "created_at_utc": utc_now_iso(),
            "ok": False,
            "real_conversation_compaction": False,
            "fallback_used": False,
            "fail_closed": True,
            "unavailable_reason": "inline_vectors_rejected",
            "no_inline_vectors": False,
            "inline_vector_paths": vector_paths,
            "claim_boundary": "No memory mutation attempted because explicit vector fields were present.",
        }
        write_json(out / "p9-conversation-compaction-receipt.json", receipt)
        return receipt

    attempts: list[dict[str, Any]] = []
    for payload in planned_payloads:
        attempt = memory_upsert(
            documents=[dict(doc) for doc in payload["documents"]],
            collection=str(payload["collection"]),
            skip_embedding=bool(payload["skip_embedding"]),
            memory_url=memory_url or DEFAULT_MEMORY_URL,
            out_dir=out,
            timeout=timeout,
            receipt_name=f"p9-{safe_filename(str(payload['collection']))}-upsert-receipt.json",
        )
        attempts.append(attempt)

    required_collections = {"conversation_history", "conversation_history_summaries", "personaplex_sessions"}
    if audio_docs:
        required_collections.add("conversation_audio_artifacts")
    real_by_collection = {str(a.get("collection")): bool(a.get("real_memory_upsert")) for a in attempts}
    real_required = all(real_by_collection.get(collection) for collection in required_collections)
    any_fallback = any(bool(a.get("fallback_used")) for a in attempts)
    session_attempt = next((a for a in attempts if a.get("collection") == "personaplex_sessions"), {})

    receipt = {
        "schema": "personaplex.p9.conversation_compaction_receipt.v1",
        "created_at_utc": utc_now_iso(),
        "ok": True,
        "session_id": session_id,
        "persona_id": persona_id,
        "turn_count": len(turns),
        "summary_count": len(summaries),
        "audio_artifact_count": len(audio_docs),
        "projection_count": len(projections),
        "source_turn_keys": source_turn_keys,
        "source_summary_keys": source_summary_keys,
        "audio_artifact_keys": audio_keys,
        "latest_summary_key": latest_summary_key,
        "session_head_key": session_head["_key"],
        "new_generation": session_head["generation"],
        "expected_previous_generation": expected_previous_generation,
        "cas_update_attempted": True,
        "cas_update_applied": bool(session_attempt.get("real_memory_upsert")),
        "cas_mode": session_head["cas"],
        "cas_daemon_enforced": False,
        "real_conversation_compaction": real_required,
        "real_memory_upsert": real_required,
        "real_session_head_update": bool(real_by_collection.get("personaplex_sessions")),
        "real_summary_upsert": bool(real_by_collection.get("conversation_history_summaries")),
        "real_audio_artifact_registration": bool(real_by_collection.get("conversation_audio_artifacts")) if audio_docs else None,
        "fallback_used": any_fallback,
        "no_inline_vectors": True,
        "inline_vector_paths": [],
        "memory_upsert_attempts": attempts,
        "planned_documents": {
            "conversation_history": turns,
            "conversation_history_summaries": summaries,
            "conversation_audio_artifacts": audio_docs,
            "personaplex_turns": projections,
            "personaplex_sessions": [session_head],
        },
        "claim_boundary": "real_conversation_compaction=true only when required memory-daemon upserts return 2xx; generic /upsert does not prove server-side CAS enforcement.",
    }
    write_json(out / "p9-conversation-compaction-receipt.json", receipt)
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PersonaPlex P9 conversation compaction persistence probe")
    parser.add_argument("--out-dir", default=str(DEFAULT_SANITY_ROOT))
    parser.add_argument("--session-id", default="p9-session")
    parser.add_argument("--persona-id", default="embry")
    parser.add_argument("--memory-url", default=None)
    parser.add_argument("--turns-json", default=None, help="JSON file containing a list of turn documents. Defaults to fixture.")
    parser.add_argument("--audio-path", action="append", default=[], help="Audio path metadata to register; repeatable.")
    parser.add_argument("--previous-head-json", default=None)
    parser.add_argument("--expected-previous-generation", type=int, default=0)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--require-real", action="store_true", help="Exit 2 unless real_conversation_compaction=true.")
    args = parser.parse_args(argv)

    turns = None
    if args.turns_json:
        loaded = json.loads(Path(args.turns_json).read_text(encoding="utf-8"))
        turns = loaded if isinstance(loaded, list) else loaded.get("turns")
    previous_head = None
    if args.previous_head_json:
        previous_head = json.loads(Path(args.previous_head_json).read_text(encoding="utf-8"))
    receipt = run_conversation_compaction(
        turn_documents=turns,
        session_id=args.session_id,
        persona_id=args.persona_id,
        memory_url=args.memory_url,
        out_dir=args.out_dir,
        timeout=args.timeout,
        audio_artifacts=args.audio_path,
        previous_head=previous_head,
        expected_previous_generation=args.expected_previous_generation,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if args.require_real and not receipt.get("real_conversation_compaction"):
        return 2
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
