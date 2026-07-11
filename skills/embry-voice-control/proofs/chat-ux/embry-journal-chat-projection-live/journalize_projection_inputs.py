#!/usr/bin/env python3
"""Journal entity receipts and an already accepted causal render for Round 1."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import wave
from typing import Any

SKILL_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(SKILL_ROOT / "src"))

from embry_voice_control.event_journal import append_event, session_snapshot  # noqa: E402


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def event_id(prefix: str, seed: dict[str, Any]) -> str:
    return prefix + "." + hashlib.sha256(canonical(seed)).hexdigest()[:16]


def extract(text: str, output: Path) -> dict[str, Any]:
    run = Path("/home/graham/workspace/experiments/agent-skills/skills/extract-entities/run.sh")
    result = subprocess.run([str(run), "extract", "--json", "--verbose", text], check=True, capture_output=True, text=True)
    parsed = json.loads(result.stdout)
    output.write_text(json.dumps(parsed, indent=2, sort_keys=True) + "\n")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--journal", type=Path, required=True)
    parser.add_argument("--render-receipt", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    render_receipt = json.loads(args.render_receipt.read_text())
    source_lineage = render_receipt["source_event"]
    session_id = source_lineage["session_id"]
    turn_id = source_lineage["turn_id"]
    events = [event for event in session_snapshot(args.journal, session_id)["events"] if event["turn_id"] == turn_id]
    source = next(event for event in events if event["event_id"] == source_lineage["event_id"])
    plan_path = Path(render_receipt["tau"]["turn_plan_path"])
    plan = json.loads(plan_path.read_text())
    tau = next(
        event for event in events
        if event["type"] == "tau.turn_plan.completed"
        and event["payload"].get("turn_plan_sha256") == render_receipt["tau"]["turn_plan_sha256"]
    )
    targets = (("user", source["event_id"], source["payload"]["text"]), ("assistant", tau["event_id"], plan["display_text"]))

    stored: list[dict[str, Any]] = []
    for role, target_event_id, text in targets:
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        existing = next((
            event for event in events
            if event["type"] == "entities.extraction.completed"
            and event["payload"].get("target_role") == role
            and event["payload"].get("target_event_id") == target_event_id
            and event["payload"].get("target_text_sha256") == "sha256:" + text_hash
        ), None)
        if existing is not None:
            stored.append(existing)
            continue
        result_path = args.output_dir / f"{role}-entities.json"
        result = extract(text, result_path)
        result_hash = sha(result_path)
        span_count = len(result.get("entity_nodes", []))
        seed = {"target_event_id": target_event_id, "target_text_sha256": text_hash, "result_sha256": result_hash}
        payload = {
            "schema": "embry.entity_annotation_event_payload.v1",
            "target_role": role,
            "target_event_id": target_event_id,
            "target_text_sha256": "sha256:" + text_hash,
            "extractor": "$extract-entities",
            "extractor_result_schema": "EntityExtractionResult",
            "result_path": str(result_path),
            "result_sha256": "sha256:" + result_hash,
            "span_count": span_count,
            "input_normalization": "none",
        }
        identifier = event_id("entities.extraction.completed", seed)
        stored.append(append_event(args.journal, {
            "schema": "embry.voice_event.v1", "event_id": identifier, "session_id": session_id,
            "turn_id": turn_id, "type": "entities.extraction.completed",
            "created_at": datetime.now(timezone.utc).isoformat(), "causation_id": target_event_id,
            "correlation_id": source["event_id"], "producer": "embry-voice-control.extract-entities-journalizer",
            "live": True, "mocked": False,
            "artifact_hashes": {"entity_result_sha256": "sha256:" + result_hash, "target_text_sha256": "sha256:" + text_hash},
            "receipt_hash": "sha256:" + hashlib.sha256(canonical(payload)).hexdigest(), "payload": payload,
        }))

    audio_path = Path(render_receipt["chatterbox"]["audio_path"])
    audio_hash = sha(audio_path)
    if audio_hash != render_receipt["chatterbox"]["audio_sha256"]:
        raise RuntimeError("accepted_audio_hash_mismatch")
    render_hash = sha(args.render_receipt)
    with wave.open(str(audio_path), "rb") as audio:
        channels = audio.getnchannels()
        sample_rate_hz = audio.getframerate()
        duration_ms = round(audio.getnframes() / sample_rate_hz * 1000)
    acceptance_count = len(render_receipt["acceptance"])
    acceptance_true_count = sum(value is True for value in render_receipt["acceptance"].values())
    render_payload = {
        "schema": "embry.chatterbox_voice_render_event_payload.v1",
        "journalization_mode": "backfill_from_accepted_live_receipt",
        "tau_turn_plan": {"path": str(plan_path), "sha256": render_receipt["tau"]["turn_plan_sha256"]},
        "tts_render_text_sha256": render_receipt["tau"]["tts_render_text_sha256"],
        "render_receipt": {"path": str(args.render_receipt), "sha256": "sha256:" + render_hash, "acceptance_field_count": acceptance_count, "acceptance_true_count": acceptance_true_count, "acceptance_all_true": all(render_receipt["acceptance"].values())},
        "audio": {
            "artifact_id": "audio:" + audio_hash, "path": str(audio_path), "sha256": audio_hash,
            "bytes": audio_path.stat().st_size, "content_type": "audio/wav", "channels": channels,
            "sample_rate_hz": sample_rate_hz, "duration_ms": duration_ms,
        },
    }
    render_seed = {"tau_turn_plan_sha256": render_receipt["tau"]["turn_plan_sha256"], "audio_sha256": audio_hash, "render_receipt_sha256": render_hash}
    stored.append(append_event(args.journal, {
        "schema": "embry.voice_event.v1", "event_id": event_id("chatterbox.voice_render.completed", render_seed),
        "session_id": session_id, "turn_id": turn_id, "type": "chatterbox.voice_render.completed",
        "created_at": datetime.fromtimestamp(args.render_receipt.stat().st_mtime, timezone.utc).isoformat(),
        "causation_id": tau["event_id"], "correlation_id": source["event_id"],
        "producer": "embry-voice-control.render-receipt-journalizer", "live": True, "mocked": False,
        "artifact_hashes": {"tau_turn_plan_sha256": render_receipt["tau"]["turn_plan_sha256"], "tts_render_text_sha256": render_receipt["tau"]["tts_render_text_sha256"], "audio_sha256": audio_hash},
        "receipt_hash": "sha256:" + hashlib.sha256(canonical(render_payload)).hexdigest(), "payload": render_payload,
    }))
    receipt = {"schema": "embry.chat_projection_inputs_journalized.v1", "ok": True, "live": True, "mocked": False, "journal": str(args.journal), "session_id": session_id, "turn_id": turn_id, "events": stored}
    (args.output_dir / "receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
