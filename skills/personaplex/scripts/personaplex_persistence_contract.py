#!/usr/bin/env python3
"""Module support for the personaplex skill."""
from __future__ import annotations
"""Canonical conversation-history and audio-artifact persistence contract.

This P0 persistence layer writes deterministic local JSON artifacts that mirror
what the live wrapper must send through ``/memory /upsert``.  It deliberately
keeps ``conversation_history`` canonical, keeps summaries immutable, treats
``personaplex_sessions`` as a CAS-protected mutable head, and records audio by
path/hash metadata instead of inline vectors.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from personaplex_turn_state import GateReceipt, ResponsePacket, TurnToken, sha256_json, stable_json, utc_now


VECTOR_KEYS = {"vector", "vectors", "embedding", "embeddings", "dense_vector", "audio_vector"}


class PersistenceContractError(RuntimeError):
    pass


class ImmutableLedgerConflict(PersistenceContractError):
    pass


class SessionHeadConflict(PersistenceContractError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_no_inline_vectors(data: Any, path: str = "$") -> None:
    if isinstance(data, dict):
        for key, value in data.items():
            key_l = str(key).lower()
            if key_l in VECTOR_KEYS and isinstance(value, list):
                raise PersistenceContractError(f"inline vector-like array is not allowed at {path}.{key}")
            validate_no_inline_vectors(value, f"{path}.{key}")
    elif isinstance(data, list):
        if len(data) >= 8 and all(isinstance(item, float) for item in data):
            raise PersistenceContractError(f"inline float vector is not allowed at {path}")
        for idx, value in enumerate(data):
            validate_no_inline_vectors(value, f"{path}[{idx}]")


@dataclass
class AudioArtifactRef:
    artifact_id: str
    role: str
    uri: str
    path: str
    sha256: str
    codec: str
    duration_ms: int | None
    retention_class: str
    deletion_state: str
    qdrant_audio_embedding: dict[str, Any]
    created_at_utc: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "role": self.role,
            "uri": self.uri,
            "path": self.path,
            "sha256": self.sha256,
            "codec": self.codec,
            "duration_ms": self.duration_ms,
            "retention_class": self.retention_class,
            "deletion_state": self.deletion_state,
            "qdrant_audio_embedding": self.qdrant_audio_embedding,
            "created_at_utc": self.created_at_utc,
        }


class LocalMemoryUpsertStore:
    """Local deterministic stand-in for the live ``/memory /upsert`` surface."""

    def __init__(self, run_root: Path | str) -> None:
        self.run_root = Path(run_root)
        self.conversation_history = self.run_root / "conversation_history"
        self.conversation_history_summaries = self.run_root / "conversation_history_summaries"
        self.personaplex_sessions = self.run_root / "personaplex_sessions"
        self.personaplex_turns = self.run_root / "personaplex_turns_derived"
        self.conversation_audio_artifacts = self.run_root / "conversation_audio_artifacts"
        self.events_jsonl = self.run_root / "events.jsonl"
        self.stale_callbacks_jsonl = self.run_root / "stale_callbacks.jsonl"
        for path in (
            self.conversation_history,
            self.conversation_history_summaries,
            self.personaplex_sessions,
            self.personaplex_turns,
            self.conversation_audio_artifacts,
        ):
            path.mkdir(parents=True, exist_ok=True)
        self.events_jsonl.parent.mkdir(parents=True, exist_ok=True)

    def append_event(self, event: dict[str, Any]) -> None:
        event = dict(event)
        event.setdefault("created_at_utc", utc_now())
        with self.events_jsonl.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")

    def append_stale_callback(self, receipt: dict[str, Any]) -> None:
        with self.stale_callbacks_jsonl.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(receipt, sort_keys=True, ensure_ascii=False) + "\n")
        self.append_event({"event": "stale_callback_receipt", **receipt})

    def record_audio_bytes(
        self,
        *,
        session_id: str,
        turn_id: int,
        role: str,
        data: bytes,
        codec: str,
        duration_ms: int | None = None,
        retention_class: str = "p0_harness_sanity",
    ) -> AudioArtifactRef:
        digest = sha256_bytes(data)
        safe_codec = codec.replace("/", "_").replace(".", "_")
        artifact_rel = Path("conversation_audio_artifacts") / f"{session_id}-{turn_id:06d}-{role}-{digest[:16]}.{safe_codec}.bin"
        artifact_path = self.run_root / artifact_rel
        artifact_path.write_bytes(data)
        ref = AudioArtifactRef(
            artifact_id=f"audio:{digest}",
            role=role,
            uri=f"file://{artifact_path}",
            path=str(artifact_rel),
            sha256=digest,
            codec=codec,
            duration_ms=duration_ms,
            retention_class=retention_class,
            deletion_state="active",
            qdrant_audio_embedding={
                "available": False,
                "qdrant_collection": None,
                "qdrant_point_id": None,
                "embedding_model": None,
                "embedding_version": None,
                "text_hash": None,
                "semantic_sync_state": "not_synced",
                "deletion_propagation_required": False,
            },
            created_at_utc=utc_now(),
        )
        meta_path = self.conversation_audio_artifacts / f"{digest}.json"
        _write_json(meta_path, ref.to_dict())
        return ref

    def upsert_conversation_history(self, record: dict[str, Any]) -> dict[str, Any]:
        validate_no_inline_vectors(record)
        if record.get("collection") != "conversation_history":
            raise PersistenceContractError("canonical turn record must target conversation_history")
        key = record.get("_key")
        if not key:
            raise PersistenceContractError("conversation_history record missing _key")
        path = self.conversation_history / f"{_safe_key(key)}.json"
        payload = dict(record)
        payload_hash = sha256_json(payload)
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            existing_hash = sha256_json(existing)
            if existing_hash != payload_hash:
                raise ImmutableLedgerConflict(f"immutable conversation_history conflict for {key}")
            status = "idempotent_existing"
        else:
            _write_json(path, payload)
            status = "created"
        receipt = {
            "ok": True,
            "collection": "conversation_history",
            "key": key,
            "path": str(path),
            "status": status,
            "sha256": payload_hash,
            "created_at_utc": utc_now(),
        }
        self.append_event({"event": "memory_upsert_conversation_history", **receipt})
        return receipt

    def write_derived_personaplex_turn_projection(self, canonical_record: dict[str, Any]) -> dict[str, Any]:
        projection = {
            "collection": "personaplex_turns",
            "derived_only": True,
            "source_conversation_key": canonical_record["_key"],
            "session_id": canonical_record["session_id"],
            "turn_id": canonical_record["turn_id"],
            "persona_id": canonical_record["persona_id"],
            "route_action": canonical_record["route_action"],
            "response_packet_hash": canonical_record["response_packet"]["packet_hash"],
            "note": "rebuildable voice/debug projection; not a canonical ledger",
            "created_at_utc": utc_now(),
        }
        validate_no_inline_vectors(projection)
        path = self.personaplex_turns / f"{_safe_key(projection['source_conversation_key'])}.json"
        _write_json(path, projection)
        receipt = {"ok": True, "collection": "personaplex_turns", "derived_only": True, "path": str(path), "source_conversation_key": projection["source_conversation_key"]}
        self.append_event({"event": "memory_upsert_personaplex_turn_projection", **receipt})
        return receipt

    def read_session_head(self, session_id: str) -> dict[str, Any] | None:
        path = self.personaplex_sessions / f"personaplex_session_{_safe_key(session_id)}.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def session_generation(self, session_id: str) -> int:
        head = self.read_session_head(session_id)
        if not head:
            return 0
        return int(head.get("generation") or 0)

    def update_session_head_cas(self, *, session_id: str, expected_generation: int, update: dict[str, Any]) -> dict[str, Any]:
        path = self.personaplex_sessions / f"personaplex_session_{_safe_key(session_id)}.json"
        existing = self.read_session_head(session_id) or {
            "_key": f"personaplex_session:{session_id}",
            "collection": "personaplex_sessions",
            "session_id": session_id,
            "generation": 0,
            "turn_count": 0,
            "current_context_window": [],
            "created_at_utc": utc_now(),
        }
        current_generation = int(existing.get("generation") or 0)
        if current_generation != expected_generation:
            raise SessionHeadConflict(
                f"session head generation mismatch for {session_id}: expected {expected_generation}, found {current_generation}"
            )
        merged = dict(existing)
        merged.update(update)
        merged["generation"] = current_generation + 1
        merged["updated_at_utc"] = utc_now()
        validate_no_inline_vectors(merged)
        _write_json(path, merged)
        receipt = {
            "ok": True,
            "collection": "personaplex_sessions",
            "key": merged["_key"],
            "path": str(path),
            "previous_generation": current_generation,
            "new_generation": merged["generation"],
            "created_at_utc": utc_now(),
        }
        self.append_event({"event": "memory_upsert_personaplex_session_head", **receipt})
        return receipt

    def maybe_write_summary(self, *, session_id: str, start_turn_id: int, end_turn_id: int, policy_version: str, summary_text: str) -> dict[str, Any]:
        key = f"conversation_summary:{session_id}:{start_turn_id:06d}:{end_turn_id:06d}:{policy_version}"
        record = {
            "_key": key,
            "collection": "conversation_history_summaries",
            "session_id": session_id,
            "start_turn_id": start_turn_id,
            "end_turn_id": end_turn_id,
            "policy_version": policy_version,
            "summary_text": summary_text,
            "retrieval_text": f"PersonaPlex summary for session {session_id}, turns {start_turn_id} through {end_turn_id}: {summary_text}",
            "created_at_utc": utc_now(),
        }
        validate_no_inline_vectors(record)
        path = self.conversation_history_summaries / f"{_safe_key(key)}.json"
        if not path.exists():
            _write_json(path, record)
        receipt = {"ok": True, "collection": "conversation_history_summaries", "key": key, "path": str(path), "sha256": sha256_json(record)}
        self.append_event({"event": "memory_upsert_conversation_history_summary", **receipt})
        return receipt

    def list_conversation_history_records(self) -> list[dict[str, Any]]:
        return [json.loads(path.read_text(encoding="utf-8")) for path in sorted(self.conversation_history.glob("*.json"))]


def build_conversation_history_record(
    *,
    token: TurnToken,
    transcript: str,
    route_action: str,
    intent_product: dict[str, Any],
    tool_plan_validation: dict[str, Any],
    route_products: list[dict[str, Any]],
    recall_snapshot: dict[str, Any] | None,
    evidence_packet: dict[str, Any] | None,
    response_packet: ResponsePacket,
    gate_receipt: GateReceipt,
    user_audio: AudioArtifactRef,
    assistant_audio: AudioArtifactRef,
    historical_tool_recommendations: list[dict[str, Any]],
    preintent_context_hash: str,
    safety_outcome: str,
) -> dict[str, Any]:
    intent_json = intent_product.get("json") or {}
    source_hashes = []
    if recall_snapshot:
        source_hashes.extend(str(item.get("source_hash")) for item in recall_snapshot.get("items", []) if item.get("source_hash"))
    if evidence_packet and evidence_packet.get("receipt_hash"):
        source_hashes.append(str(evidence_packet["receipt_hash"]))
    record = {
        "_key": token.turn_key,
        "collection": "conversation_history",
        "schema_version": "personaplex.conversation_history.v1",
        "policy_version": token.policy_version,
        "session_id": token.session_id,
        "persona_id": token.persona_id,
        "turn_id": token.turn_id,
        "generation": token.generation,
        "transcript": transcript,
        "transcript_hash": token.transcript_hash,
        "route_action": route_action,
        "current_intent_authority": {
            "authoritative": True,
            "turn_id": token.turn_id,
            "generation": token.generation,
            "authority_key": token.authority_key,
            "intent_hash": intent_product.get("receipt_hash"),
            "allowed_tools": intent_json.get("allowed_tools") or [],
            "tool_calls": intent_json.get("tool_calls") or [],
            "query_plan": intent_json.get("query_plan") or {},
            "note": "only this current-turn intent product authorized route/tool execution",
        },
        "historical_tool_recommendations": [
            {**item, "authoritative": False, "non_authoritative": True}
            for item in historical_tool_recommendations
        ],
        "tool_plan_validation": tool_plan_validation,
        "selected_tools": tool_plan_validation.get("requested_tools") or [],
        "extracted_entities": intent_json.get("extracted_entities") or [],
        "recall_snapshot": recall_snapshot,
        "evidence_packet": evidence_packet,
        "route_product_receipts": route_products,
        "response_packet": response_packet.to_dict(),
        "gate_receipt": gate_receipt.to_dict(),
        "audio_artifacts": {
            "user": user_audio.to_dict(),
            "assistant": assistant_audio.to_dict(),
        },
        "qdrant_pointer_metadata": {
            "semantic_text_available": True,
            "qdrant_collection": None,
            "qdrant_point_id": None,
            "embedding_model": None,
            "embedding_version": None,
            "text_hash": sha256_json({"transcript": transcript, "response": response_packet.text}),
            "semantic_sync_state": "pending",
        },
        "source_hashes": sorted(set(source_hashes)),
        "preintent_context_hash": preintent_context_hash,
        "safety_outcome": safety_outcome,
        "retrieval_text": _retrieval_text(token, transcript, route_action, intent_json, response_packet.text),
        "sealed_at_utc": utc_now(),
        "created_at_utc": utc_now(),
    }
    validate_no_inline_vectors(record)
    return record


def _retrieval_text(token: TurnToken, transcript: str, route_action: str, intent_json: dict[str, Any], response_text: str) -> str:
    entity_bits: list[str] = []
    for item in intent_json.get("extracted_entities") or []:
        if isinstance(item, str) and item.strip():
            entity_bits.append(item.strip())
        elif isinstance(item, dict):
            label = item.get("text") or item.get("entity") or item.get("id")
            if label:
                entity_bits.append(str(label))
    entities = ", ".join(entity_bits)
    return (
        f"PersonaPlex session {token.session_id} turn {token.turn_id} for persona {token.persona_id}. "
        f"User asked: {transcript}. Route action: {route_action}. Entities: {entities or 'none'}. "
        f"Bounded response: {response_text}"
    )


def _safe_key(key: str) -> str:
    return key.replace(":", "_").replace("/", "_")


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)
