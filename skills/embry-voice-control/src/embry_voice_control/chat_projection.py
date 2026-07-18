"""Fail-closed journal-to-shared-chat projection for one Embry turn."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from embry_voice_control.artifact_authority import resolve_audio_artifact
from embry_voice_control.event_journal import session_snapshot

PROJECTION_SCHEMA = "embry.chat_projection.v1"
TRACE_TYPES = (
    "speaker.verification.completed",
    "memory.speaker_resolved",
    "memory.intent_resolved",
    "memory.answer_resolved",
    "tau.persistent_tick.completed",
    "tau.turn_plan.completed",
)
TRACE_LABELS = {
    "speaker.verification.completed": "Horus verified",
    "memory.speaker_resolved": "Memory speaker resolved",
    "memory.intent_resolved": "Memory intent resolved",
    "memory.answer_resolved": "Memory answer resolved",
    "tau.persistent_tick.completed": "One bounded Tau tick completed",
    "tau.turn_plan.completed": "Tau turn plan completed",
}


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _hex(value: str) -> str:
    return value.removeprefix("sha256:")


def _file_json(path_value: str, expected_hash: str) -> dict[str, Any]:
    path = Path(path_value)
    if not path.is_file():
        raise RuntimeError("referenced_receipt_missing")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != _hex(expected_hash):
        raise RuntimeError("referenced_receipt_hash_mismatch")
    parsed = json.loads(data)
    if not isinstance(parsed, dict):
        raise RuntimeError("referenced_receipt_invalid")
    return parsed


def _one(events: list[dict[str, Any]], event_type: str) -> dict[str, Any]:
    matches = [event for event in events if event["type"] == event_type]
    if len(matches) != 1:
        raise RuntimeError(f"required_event_count_invalid:{event_type}:{len(matches)}")
    return matches[0]


def _annotations(event: dict[str, Any], content: str) -> list[dict[str, Any]]:
    payload = event["payload"]
    result = _file_json(payload["result_path"], payload["result_sha256"])
    annotations: list[dict[str, Any]] = []
    for node in result.get("entity_nodes", []):
        extracted = node.get("extracted", {})
        span = extracted.get("span")
        if not isinstance(span, list) or len(span) != 2:
            continue
        start, end = int(span[0]), int(span[1])
        mention = str(extracted.get("text", ""))
        # Degenerate sentinel span (start >= end, e.g. [0, 0] for a noun phrase the
        # extractor could not locate in the raw text): not a positioned annotation,
        # so ignore it -- mirrors journal_emitters._validate_entity_spans /
        # _select_non_overlapping_nodes so the projection never rejects an event
        # the producer legitimately journaled.
        if start >= end:
            continue
        if not (0 <= start < end <= len(content)) or content[start:end] != mention:
            raise RuntimeError("entity_span_invalid")
        annotations.append({
            "id": str(node.get("id", f"entity-{start}-{end}")),
            "mention": mention,
            "start": start,
            "end": end,
            "kind": str(extracted.get("kind", node.get("node_kind", "entity"))),
            "grounded": bool(node.get("metadata", {}).get("grounded", False)),
            "source": str(extracted.get("source", "extract-entities")),
            "extraction_event_id": event["event_id"],
            "extraction_result_sha256": payload["result_sha256"],
        })
    annotations.sort(key=lambda item: (item["start"], item["end"]))
    for previous, current in zip(annotations, annotations[1:]):
        if previous["end"] > current["start"]:
            raise RuntimeError("entity_spans_overlap")
    return annotations


def build_turn_chat_projection(
    journal_path: Path,
    *,
    session_id: str,
    turn_id: str,
) -> dict[str, Any]:
    """Build one complete projection without invoking any provider."""
    snapshot = session_snapshot(journal_path, session_id)
    if not snapshot["events"]:
        raise LookupError("session_not_found")
    events = [event for event in snapshot["events"] if event["turn_id"] == turn_id]
    if not events:
        raise LookupError("turn_not_found")
    source = _one(events, "listener.final_transcript")
    speaker = _one(events, "speaker.verification.completed")
    tau_plan_event = _one(events, "tau.turn_plan.completed")
    tau_tick = _one(events, "tau.persistent_tick.completed")
    render = _one(events, "chatterbox.voice_render.completed")
    playback_events = [event for event in events if event["type"] in {"playback.requested", "playback.started", "playback.ended"}]
    entity_events = [event for event in events if event["type"] == "entities.extraction.completed"]
    entities_by_role = {event["payload"].get("target_role"): event for event in entity_events}
    if set(entities_by_role) != {"user", "assistant"}:
        raise RuntimeError("entity_events_incomplete")

    events_by_id = {event["event_id"]: event for event in events}
    try:
        memory_answer = events_by_id[tau_plan_event["causation_id"]]
        memory_intent = events_by_id[memory_answer["causation_id"]]
        memory_speaker = events_by_id[memory_intent["causation_id"]]
    except KeyError as exc:
        raise RuntimeError("tau_memory_causation_chain_incomplete") from exc
    expected_chain_types = (
        (memory_speaker, "memory.speaker_resolved"),
        (memory_intent, "memory.intent_resolved"),
        (memory_answer, "memory.answer_resolved"),
    )
    if any(event["type"] != expected for event, expected in expected_chain_types):
        raise RuntimeError("tau_memory_causation_chain_invalid")

    plan = _file_json(tau_plan_event["payload"]["turn_plan_path"], tau_plan_event["payload"]["turn_plan_sha256"])
    if plan.get("session_id") != session_id or plan.get("turn_id") != turn_id:
        raise RuntimeError("tau_plan_lineage_mismatch")
    if plan.get("source_event_id") != source["event_id"]:
        raise RuntimeError("tau_plan_source_mismatch")
    human_text = str(source["payload"].get("text", ""))
    assistant_text = str(plan.get("display_text", ""))
    if not human_text or not assistant_text:
        raise RuntimeError("projection_text_missing")
    display_hash = hashlib.sha256(assistant_text.encode()).hexdigest()
    if display_hash != _hex(str(plan.get("display_text_sha256", ""))):
        raise RuntimeError("display_text_hash_mismatch")
    audio_hash = str(render["payload"]["audio"]["sha256"])
    audio = resolve_audio_artifact(journal_path, session_id=session_id, turn_id=turn_id, audio_sha256=audio_hash)

    required_trace = []
    trace_events = {
        "speaker.verification.completed": speaker,
        "memory.speaker_resolved": memory_speaker,
        "memory.intent_resolved": memory_intent,
        "memory.answer_resolved": memory_answer,
        "tau.persistent_tick.completed": tau_tick,
        "tau.turn_plan.completed": tau_plan_event,
    }
    for event_type in TRACE_TYPES:
        event = trace_events[event_type]
        detail = event["receipt_hash"]
        if event_type == "speaker.verification.completed":
            detail = f"score {event['payload'].get('score', event['payload'].get('confidence', 'unknown'))}"
        required_trace.append({
            "id": event["event_id"],
            "event_id": event["event_id"],
            "sequence": event["sequence"],
            "event_type": event_type,
            "label": TRACE_LABELS[event_type],
            "status": "completed",
            "detail": detail,
            "created_at": event["created_at"],
            "receipt_hash": event["receipt_hash"],
        })
    required_trace.sort(key=lambda step: step["sequence"])

    projection: dict[str, Any] = {
        "schema": PROJECTION_SCHEMA,
        "live": True,
        "mocked": False,
        "projection_only": True,
        "session_id": session_id,
        "turn_id": turn_id,
        "source_event_id": source["event_id"],
        "source_sequence": source["sequence"],
        "journal": {key: snapshot[key] for key in ("through_sequence", "event_count", "sha256")},
        "messages": [
            {
                "id": source["event_id"], "role": "user", "content": human_text,
                "content_sha256": "sha256:" + hashlib.sha256(human_text.encode()).hexdigest(),
                "created_at": source["created_at"],
                "annotations": _annotations(entities_by_role["user"], human_text),
                "provenance": {"event_id": source["event_id"], "sequence": source["sequence"], "receipt_hash": source["receipt_hash"]},
            },
            {
                "id": tau_plan_event["event_id"], "role": "assistant", "content": assistant_text,
                "content_sha256": "sha256:" + display_hash, "created_at": tau_plan_event["created_at"],
                "annotations": _annotations(entities_by_role["assistant"], assistant_text),
                "reasoning_steps": required_trace,
                "audio_artifacts": [{
                    "artifact_id": audio["artifact_id"], "state": "audio_ready",
                    "url": f"/v1/sessions/{session_id}/turns/{turn_id}/artifacts/{audio_hash}",
                    "sha256": audio_hash, "bytes": audio["bytes"], "content_type": audio["content_type"],
                    "channels": audio["channels"], "sample_rate_hz": audio["sample_rate_hz"],
                    "duration_ms": audio["duration_ms"], "playback_enabled": False,
                }],
                "provenance": {
                    "event_id": tau_plan_event["event_id"], "plan_sha256": tau_plan_event["payload"]["turn_plan_sha256"],
                    "tts_render_text_sha256": plan["tts_render_text_sha256"], "render_event_id": render["event_id"],
                },
            },
        ],
        "required_event_ids": [event["event_id"] for event in events if event["type"] in TRACE_TYPES or event["type"] in {"listener.final_transcript", "entities.extraction.completed", "chatterbox.voice_render.completed"}],
        "hashes": {
            "tau_turn_plan_sha256": tau_plan_event["payload"]["turn_plan_sha256"],
            "display_text_sha256": display_hash,
            "tts_render_text_sha256": plan["tts_render_text_sha256"],
            "audio_sha256": audio_hash,
        },
    }
    if playback_events:
        playback_by_type = {event["type"]: event for event in playback_events}
        if set(playback_by_type) != {"playback.requested", "playback.started", "playback.ended"}:
            raise RuntimeError("playback_projection_incomplete")
        requested = playback_by_type["playback.requested"]
        started = playback_by_type["playback.started"]
        ended = playback_by_type["playback.ended"]
        if not (
            requested["causation_id"] == render["event_id"]
            and started["causation_id"] == requested["event_id"]
            and ended["causation_id"] == started["event_id"]
            and requested["sequence"] < started["sequence"] < ended["sequence"]
        ):
            raise RuntimeError("playback_projection_lineage_invalid")
        authority_ids = {
            event["payload"].get("playback_authority_id") or event["payload"].get("authority_id")
            for event in (requested, started, ended)
        }
        if len(authority_ids) != 1 or None in authority_ids:
            raise RuntimeError("playback_projection_authority_mismatch")
        projection["playback"] = {
            "authority_id": authority_ids.pop(),
            "state": "idle",
            "final_state_reason": "playback.ended",
            "events": [
                {"event_id": event["event_id"], "type": event["type"], "sequence": event["sequence"], "created_at": event["created_at"]}
                for event in (requested, started, ended)
            ],
        }
        projection["required_event_ids"].extend(event["event_id"] for event in (requested, started, ended))
    projection["projection_sha256"] = "sha256:" + hashlib.sha256(_canonical(projection)).hexdigest()
    return projection
