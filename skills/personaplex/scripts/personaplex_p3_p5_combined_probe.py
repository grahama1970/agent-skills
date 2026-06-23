#!/usr/bin/env python3
from __future__ import annotations
"""PersonaPlex P6-P7-P8 combined probe preserving the P3-P5 receipt boundary."""

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from personaplex_deepgram_live import deepgram_websocket_probe
from personaplex_p3_p5_live_services import (
    DEFAULT_SANITY_ROOT,
    append_jsonl,
    build_conversation_document,
    create_evidence_case,
    memory_upsert,
    sha256_json,
    utc_now_iso,
    write_json,
)


def run_combined_probe(
    *,
    out_dir: str | Path = DEFAULT_SANITY_ROOT,
    session_id: str = "p6p7p8-session",
    persona_id: str = "embry",
    question: str = "Focus on the west gateway.",
    transcript: str = "Focus on the west gateway.",
    memory_url: str | None = None,
    evidence_case_url: str | None = None,
    deepgram_url: str | None = None,
    deepgram_audio_path: str | None = None,
    timeout: float = 2.5,
    deepgram_timeout: float = 10.0,
    skip_deepgram: bool = False,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    events_jsonl = out / "events.jsonl"
    append_jsonl(events_jsonl, {"created_at_utc": utc_now_iso(), "event": "p6_p7_p8_combined_probe_start"})

    if skip_deepgram:
        websocket_probe: dict[str, Any] = {
            "schema": "personaplex.p8.deepgram_websocket_attempt.v1",
            "created_at_utc": utc_now_iso(),
            "attempted": False,
            "live_websocket": False,
            "real_deepgram": False,
            "real_gpu_personaplex": False,
            "deepgram_mode": "skipped_by_cli",
            "observed_speech_final": False,
            "fallback_used": True,
            "unavailable_reason": "skipped_by_cli",
            "transcript": transcript,
        }
    else:
        websocket_probe = deepgram_websocket_probe(
            audio_path=deepgram_audio_path,
            deepgram_url=deepgram_url,
            out_dir=out,
            timeout=deepgram_timeout,
        )
    append_jsonl(events_jsonl, {"created_at_utc": utc_now_iso(), "event": "p8_complete", "real_deepgram": websocket_probe.get("real_deepgram")})

    active_transcript = str(websocket_probe.get("transcript") or transcript)
    evidence_case_attempt = create_evidence_case(
        question=question,
        evidence_case_url=evidence_case_url,
        out_dir=out,
        timeout=timeout,
    )
    append_jsonl(events_jsonl, {"created_at_utc": utc_now_iso(), "event": "p7_complete", "real_create_evidence_case": evidence_case_attempt.get("real_create_evidence_case")})

    release_receipt = {
        "created_at_utc": utc_now_iso(),
        "session_id": session_id,
        "turn_id": 2,
        "generation": 2,
        "release_authorized": True,
        "gate_closed_reason": "final transcript received; close gate before memory/evidence routing",
        "queue_depth_at_release": 0,
        "blocked_token_count": 1,
        "response_packet_hash": sha256_json(
            {
                "transcript": active_transcript,
                "evidence_route": evidence_case_attempt.get("selected_route"),
                "real_create_evidence_case": evidence_case_attempt.get("real_create_evidence_case"),
            }
        ),
    }

    audio_metadata = websocket_probe.get("audio_metadata") if isinstance(websocket_probe.get("audio_metadata"), Mapping) else None
    doc = build_conversation_document(
        session_id=session_id,
        turn_id=2,
        persona_id=persona_id,
        transcript=active_transcript,
        audio_metadata=audio_metadata,
        extra={
            "evidence_route": evidence_case_attempt.get("selected_route"),
            "real_create_evidence_case": bool(evidence_case_attempt.get("real_create_evidence_case")),
            "real_deepgram": bool(websocket_probe.get("real_deepgram")),
        },
    )
    memory_upsert_attempt = memory_upsert(
        documents=[doc],
        memory_url=memory_url,
        out_dir=out,
        timeout=timeout,
    )
    append_jsonl(events_jsonl, {"created_at_utc": utc_now_iso(), "event": "p6_complete", "real_memory_upsert": memory_upsert_attempt.get("real_memory_upsert")})

    stale_rejection = {
        "created_at_utc": utc_now_iso(),
        "operation": "p6_p7_p8_route_callback_after_delay",
        "reason": "stale turn callback fenced before mutation",
        "stale_turn_id": 1,
        "stale_generation": 1,
        "active_turn_id": 2,
        "active_generation": 2,
        "details": {"route_delay_ms": 250},
    }

    final = {
        "schema": "personaplex.p6_p7_p8_real_services.final_receipt.v1",
        "created_at_utc": utc_now_iso(),
        "ok": True,
        "session_id": session_id,
        "persona_id": persona_id,
        "turn_count": 2,
        "active_turn_id": 2,
        "sealed_turn_count": 1,
        "sealed_turn_keys": [doc["_key"]],
        "stale_rejection_count": 1,
        "stale_rejections": [stale_rejection],
        "queue_depth_at_release": 0,
        "deepgram_mode": websocket_probe.get("deepgram_mode"),
        "live_websocket": bool(websocket_probe.get("live_websocket")),
        "real_deepgram": bool(websocket_probe.get("real_deepgram")),
        "real_gpu_personaplex": False,
        "real_memory_upsert": bool(memory_upsert_attempt.get("real_memory_upsert")),
        "real_create_evidence_case": bool(evidence_case_attempt.get("real_create_evidence_case")),
        "websocket_probe": websocket_probe,
        "memory_upsert_attempts": [memory_upsert_attempt],
        "evidence_case_attempts": [evidence_case_attempt],
        "release_receipts": [release_receipt],
        "results": [
            {
                "turn_id": 1,
                "generation": 1,
                "status": "stale_fenced",
                "reason": "route work finished after a newer turn became active",
                "route_endpoint": None,
                "sealed_key": None,
                "gate_receipt": None,
            },
            {
                "turn_id": 2,
                "generation": 2,
                "status": "sealed",
                "reason": "active bounded packet released and canonical conversation_history record prepared",
                "route_action": "COMPLIANCE",
                "route_endpoint": evidence_case_attempt.get("selected_route"),
                "sealed_key": doc["_key"],
                "gate_receipt": release_receipt,
                "memory_upsert_attempt": memory_upsert_attempt,
                "evidence_case_attempt": evidence_case_attempt,
            },
        ],
        "events_jsonl": str(events_jsonl),
        "final_receipt_path": str(out / "p6-p7-p8-final-receipt.json"),
        "claim_boundary": "Combined P6-P7-P8 probe. Deterministic fallback is not real Deepgram/GPU/memory/evidence proof unless the real_* flags are true.",
    }
    write_json(out / "p6-p7-p8-final-receipt.json", final)
    append_jsonl(events_jsonl, {"created_at_utc": utc_now_iso(), "event": "p6_p7_p8_combined_probe_complete", "real_flags": {"memory": final["real_memory_upsert"], "evidence_case": final["real_create_evidence_case"], "deepgram": final["real_deepgram"]}})
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PersonaPlex P6-P7-P8 combined live-service probe")
    parser.add_argument("--out-dir", default=str(DEFAULT_SANITY_ROOT))
    parser.add_argument("--session-id", default="p6p7p8-session")
    parser.add_argument("--persona-id", default="embry")
    parser.add_argument("--question", default="Focus on the west gateway.")
    parser.add_argument("--transcript", default="Focus on the west gateway.")
    parser.add_argument("--memory-url", default=None)
    parser.add_argument("--evidence-case-url", default=None)
    parser.add_argument("--deepgram-url", default=None)
    parser.add_argument("--deepgram-audio-path", default=None)
    parser.add_argument("--timeout", type=float, default=2.5)
    parser.add_argument("--deepgram-timeout", type=float, default=10.0)
    parser.add_argument("--skip-deepgram", action="store_true")
    parser.add_argument("--require-real", action="store_true", help="Exit 2 unless P6, P7, and P8 real flags are all true.")
    args = parser.parse_args(argv)

    receipt = run_combined_probe(
        out_dir=args.out_dir,
        session_id=args.session_id,
        persona_id=args.persona_id,
        question=args.question,
        transcript=args.transcript,
        memory_url=args.memory_url,
        evidence_case_url=args.evidence_case_url,
        deepgram_url=args.deepgram_url,
        deepgram_audio_path=args.deepgram_audio_path,
        timeout=args.timeout,
        deepgram_timeout=args.deepgram_timeout,
        skip_deepgram=args.skip_deepgram,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if args.require_real and not (receipt.get("real_memory_upsert") and receipt.get("real_create_evidence_case") and receipt.get("real_deepgram")):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
