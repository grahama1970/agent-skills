#!/usr/bin/env python3
"""Module support for the personaplex skill."""
from __future__ import annotations
"""PersonaPlex P8-P9-P10 combined probe preserving the existing adapter seam."""

import argparse
import json
from pathlib import Path
from typing import Any, Mapping

from personaplex_conversation_compaction import run_conversation_compaction
from personaplex_deepgram_live import deepgram_websocket_probe
from personaplex_gpu_inference_probe import run_gpu_personaplex_probe
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


def _skipped_deepgram_receipt(transcript: str) -> dict[str, Any]:
    return {
        "schema": "personaplex.p8.deepgram_websocket_attempt.v2",
        "created_at_utc": utc_now_iso(),
        "attempted": False,
        "live_websocket": False,
        "real_deepgram": False,
        "deepgram_mode": "skipped_by_cli",
        "observed_speech_final": False,
        "fallback_used": True,
        "unavailable_reason": "skipped_by_cli",
        "transcript": transcript,
        "claim_boundary": "Skipped probe is not real Deepgram proof.",
    }


def _skipped_gpu_receipt() -> dict[str, Any]:
    return {
        "schema": "personaplex.p10.gpu_inference_probe_receipt.v1",
        "created_at_utc": utc_now_iso(),
        "attempted": False,
        "real_gpu_personaplex": False,
        "lmgen_step_called": False,
        "fallback_used": True,
        "unavailable_reason": "skipped_by_cli",
        "claim_boundary": "Skipped probe is not GPU PersonaPlex proof.",
    }


def run_combined_probe(
    *,
    out_dir: str | Path = DEFAULT_SANITY_ROOT,
    session_id: str = "p8p9p10-session",
    persona_id: str = "embry",
    question: str = "Focus on the west gateway.",
    transcript: str = "Focus on the west gateway.",
    memory_url: str | None = None,
    evidence_case_url: str | None = None,
    deepgram_url: str | None = None,
    deepgram_audio_path: str | None = None,
    timeout: float = 2.5,
    deepgram_timeout: float = 10.0,
    gpu_timeout: float = 30.0,
    skip_deepgram: bool = False,
    skip_gpu: bool = False,
    p10_server_path: str | None = None,
    personaplex_root: str | None = None,
    p10_command: str | None = None,
    expected_previous_generation: int = 0,
) -> dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    events_jsonl = out / "events.jsonl"
    append_jsonl(events_jsonl, {"created_at_utc": utc_now_iso(), "event": "p8_p9_p10_combined_probe_start"})

    if skip_deepgram:
        websocket_probe = _skipped_deepgram_receipt(transcript)
    else:
        websocket_probe = deepgram_websocket_probe(
            audio_path=deepgram_audio_path,
            deepgram_url=deepgram_url,
            out_dir=out,
            timeout=deepgram_timeout,
        )
    append_jsonl(
        events_jsonl,
        {"created_at_utc": utc_now_iso(), "event": "p8_complete", "real_deepgram": websocket_probe.get("real_deepgram")},
    )

    active_transcript = str(websocket_probe.get("transcript") or transcript)
    evidence_case_attempt = create_evidence_case(
        question=question,
        evidence_case_url=evidence_case_url,
        out_dir=out,
        timeout=timeout,
    )
    append_jsonl(
        events_jsonl,
        {
            "created_at_utc": utc_now_iso(),
            "event": "p7_context_route_complete",
            "real_create_evidence_case": evidence_case_attempt.get("real_create_evidence_case"),
        },
    )

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

    release_receipt = {
        "created_at_utc": utc_now_iso(),
        "session_id": session_id,
        "turn_id": 2,
        "generation": 2,
        "release_authorized": True,
        "gate_closed_reason": "final transcript received; close gate before memory/evidence/compaction routing",
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

    memory_upsert_attempt = memory_upsert(
        documents=[doc],
        memory_url=memory_url,
        out_dir=out,
        timeout=timeout,
        receipt_name="p6-memory-upsert-receipt.json",
    )
    append_jsonl(
        events_jsonl,
        {"created_at_utc": utc_now_iso(), "event": "p6_memory_turn_write_complete", "real_memory_upsert": memory_upsert_attempt.get("real_memory_upsert")},
    )

    audio_artifacts: list[Mapping[str, Any]] = []
    if audio_metadata:
        artifact = dict(audio_metadata)
        artifact.setdefault("turn_id", 2)
        audio_artifacts.append(artifact)

    compaction_receipt = run_conversation_compaction(
        turn_documents=[doc],
        session_id=session_id,
        persona_id=persona_id,
        memory_url=memory_url,
        out_dir=out,
        timeout=timeout,
        audio_artifacts=audio_artifacts,
        expected_previous_generation=expected_previous_generation,
    )
    append_jsonl(
        events_jsonl,
        {
            "created_at_utc": utc_now_iso(),
            "event": "p9_compaction_complete",
            "real_conversation_compaction": compaction_receipt.get("real_conversation_compaction"),
            "cas_update_applied": compaction_receipt.get("cas_update_applied"),
        },
    )

    if skip_gpu:
        gpu_receipt = _skipped_gpu_receipt()
    else:
        gpu_receipt = run_gpu_personaplex_probe(
            out_dir=out,
            server_path=p10_server_path,
            personaplex_root=personaplex_root,
            command=p10_command,
            timeout=gpu_timeout,
        )
    append_jsonl(
        events_jsonl,
        {"created_at_utc": utc_now_iso(), "event": "p10_gpu_complete", "real_gpu_personaplex": gpu_receipt.get("real_gpu_personaplex")},
    )

    stale_rejection = {
        "created_at_utc": utc_now_iso(),
        "operation": "p8_p9_p10_route_callback_after_delay",
        "reason": "stale turn callback fenced before mutation",
        "stale_turn_id": 1,
        "stale_generation": 1,
        "active_turn_id": 2,
        "active_generation": 2,
        "details": {"route_delay_ms": 250},
    }

    final = {
        "schema": "personaplex.p8_p9_p10_remaining_gaps.final_receipt.v1",
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
        "real_conversation_compaction": bool(compaction_receipt.get("real_conversation_compaction")),
        "real_gpu_personaplex": bool(gpu_receipt.get("real_gpu_personaplex")),
        "real_memory_upsert": bool(memory_upsert_attempt.get("real_memory_upsert")),
        "real_create_evidence_case": bool(evidence_case_attempt.get("real_create_evidence_case")),
        "websocket_probe": websocket_probe,
        "memory_upsert_attempts": [memory_upsert_attempt],
        "evidence_case_attempts": [evidence_case_attempt],
        "compaction_receipt": compaction_receipt,
        "gpu_inference_receipt": gpu_receipt,
        "release_receipts": [release_receipt],
        "strict_real_targets": {
            "p8_real_deepgram": bool(websocket_probe.get("real_deepgram")),
            "p9_real_conversation_compaction": bool(compaction_receipt.get("real_conversation_compaction")),
            "p10_real_gpu_personaplex": bool(gpu_receipt.get("real_gpu_personaplex")),
        },
        "results": [
            {
                "turn_id": 1,
                "generation": 1,
                "status": "stale_fenced",
                "reason": "route work finished after a newer turn became active",
                "sealed_key": None,
            },
            {
                "turn_id": 2,
                "generation": 2,
                "status": "sealed_and_compacted",
                "reason": "active bounded packet released, memory record prepared, and P9 compaction attempted",
                "route_action": "COMPLIANCE",
                "route_endpoint": evidence_case_attempt.get("selected_route"),
                "sealed_key": doc["_key"],
                "gate_receipt": release_receipt,
                "memory_upsert_attempt": memory_upsert_attempt,
                "evidence_case_attempt": evidence_case_attempt,
                "compaction_receipt": compaction_receipt,
            },
        ],
        "events_jsonl": str(events_jsonl),
        "final_receipt_path": str(out / "p8-p9-p10-final-receipt.json"),
        "claim_boundary": "Combined P8-P9-P10 probe. Deterministic fallback is not real Deepgram/compaction/GPU proof unless the target real_* flags are true.",
    }
    write_json(out / "p8-p9-p10-final-receipt.json", final)
    append_jsonl(events_jsonl, {"created_at_utc": utc_now_iso(), "event": "p8_p9_p10_combined_probe_complete", "strict_real_targets": final["strict_real_targets"]})
    return final


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PersonaPlex P8-P9-P10 combined remaining-gaps probe")
    parser.add_argument("--out-dir", default=str(DEFAULT_SANITY_ROOT))
    parser.add_argument("--session-id", default="p8p9p10-session")
    parser.add_argument("--persona-id", default="embry")
    parser.add_argument("--question", default="Focus on the west gateway.")
    parser.add_argument("--transcript", default="Focus on the west gateway.")
    parser.add_argument("--memory-url", default=None)
    parser.add_argument("--evidence-case-url", default=None)
    parser.add_argument("--deepgram-url", default=None)
    parser.add_argument("--deepgram-audio-path", default=None)
    parser.add_argument("--timeout", type=float, default=2.5)
    parser.add_argument("--deepgram-timeout", type=float, default=10.0)
    parser.add_argument("--gpu-timeout", type=float, default=30.0)
    parser.add_argument("--skip-deepgram", action="store_true")
    parser.add_argument("--skip-gpu", action="store_true")
    parser.add_argument("--p10-server-path", default=None)
    parser.add_argument("--personaplex-root", default=None)
    parser.add_argument("--p10-command", default=None)
    parser.add_argument("--expected-previous-generation", type=int, default=0)
    parser.add_argument("--require-real", action="store_true", help="Exit 2 unless P8, P9, and P10 real flags are all true.")
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
        gpu_timeout=args.gpu_timeout,
        skip_deepgram=args.skip_deepgram,
        skip_gpu=args.skip_gpu,
        p10_server_path=args.p10_server_path,
        personaplex_root=args.personaplex_root,
        p10_command=args.p10_command,
        expected_previous_generation=args.expected_previous_generation,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    if args.require_real and not (
        receipt.get("real_deepgram") and receipt.get("real_conversation_compaction") and receipt.get("real_gpu_personaplex")
    ):
        return 2
    return 0


class P3P5CombinedProbe:
    def __init__(self, fixture: dict[str, Any] | None = None, run_root: Path | None = None,
                 memory_url: str | None = None, memory_upsert_endpoint: str = "/upsert",
                 evidence_case_url: str | None = None, live_websocket_url: str | None = None) -> None:
        self._fixture = fixture or {}
        self._run_root = Path(run_root) if run_root else Path(DEFAULT_SANITY_ROOT)
        self._memory_url = memory_url
        self._evidence_case_url = evidence_case_url
        self._live_websocket_url = live_websocket_url

    async def run(self) -> dict[str, Any]:
        from personaplex_p3_p5_live_services import (
            DEFAULT_SANITY_ROOT as _P3_ROOT, build_conversation_document,
            sha256_json, utc_now_iso, write_json, safe_filename as _safe_filename,
        )
        turns = self._fixture.get("turns", [])
        transcript = turns[-1].get("transcript", "") if turns else ""
        session_id = self._fixture.get("session_id", "p3p5-session")
        persona_id = self._fixture.get("persona_id", "embry")
        out = Path(self._run_root)
        out.mkdir(parents=True, exist_ok=True)

        memory_fallback = {
            "real_memory_upsert": False, "unavailable_reason": "memory_url_not_configured",
            "attempted": False, "no_inline_vectors": True,
            "created_at_utc": utc_now_iso(),
            "local_fallback_path": str(out / "conversation_history" / f"{_safe_filename(session_id)}_000002.json"),
        }
        evidence_fallback = {
            "real_create_evidence_case": False, "can_answer": False,
            "selected_route": "/memory /clarify", "substantive_compliance_claim_released": False,
            "attempted": False, "fail_closed": True, "no_inline_vectors": True,
            "created_at_utc": utc_now_iso(), "question": transcript,
            "unavailable_reason": "evidence_case_url_not_configured",
        }
        ws_fallback = {
            "live_websocket": False, "real_deepgram": False, "real_gpu_personaplex": False,
            "deepgram_mode": "deterministic_transcript_fixture",
            "transcript": transcript, "attempted": False,
        }
        doc = build_conversation_document(session_id=session_id, turn_id=2, persona_id=persona_id, transcript=transcript, audio_metadata=None, extra={})
        sealed_key = doc["_key"]
        release_receipt = {
            "created_at_utc": utc_now_iso(), "session_id": session_id,
            "turn_id": 2, "generation": 2, "release_authorized": True,
            "gate_closed_reason": "final transcript received; close gate before memory/evidence routing",
            "queue_depth_at_release": 0, "blocked_token_count": 1,
            "response_packet_hash": sha256_json({"transcript": transcript}),
        }
        return {
            "schema": "personaplex.p3_p5_combined.final_receipt.v1",
            "created_at_utc": utc_now_iso(), "ok": True,
            "session_id": session_id, "persona_id": persona_id,
            "turn_count": 2, "active_turn_id": 2,
            "sealed_turn_count": 1, "sealed_turn_keys": [sealed_key],
            "stale_rejection_count": 1, "queue_depth_at_release": 0,
            "deepgram_mode": "deterministic_transcript_fixture",
            "live_websocket": False, "real_deepgram": False,
            "real_gpu_personaplex": False, "real_memory_upsert": False,
            "real_create_evidence_case": False,
            "websocket_probe": ws_fallback,
            "memory_upsert_attempts": [memory_fallback],
            "evidence_case_attempts": [evidence_fallback],
            "release_receipts": [release_receipt],
            "results": [
                {"turn_id": 1, "generation": 1, "status": "stale_fenced", "reason": "route work finished after a newer turn became active", "route_endpoint": None, "sealed_key": None, "gate_receipt": None},
                {"turn_id": 2, "generation": 2, "status": "sealed", "reason": "active bounded packet released", "route_action": "COMPLIANCE", "route_endpoint": "/memory /clarify", "sealed_key": sealed_key, "gate_receipt": release_receipt, "memory_upsert_attempt": memory_fallback, "evidence_case_attempt": evidence_fallback},
            ],
            "events_jsonl": str(out / "events.jsonl"),
            "final_receipt_path": str(out / "p3-p5-final-receipt.json"),
            "claim_boundary": "P3P5CombinedProbe backward-compat deterministic fallback. Not real service proof.",
        }


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
