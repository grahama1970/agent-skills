#!/usr/bin/env python3
"""Render deterministic session-mood voice_delivery turns through live Chatterbox."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CHATTERBOX = "http://127.0.0.1:8018"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


session_mood_binding = _load("session_mood_binding")


def _sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def post_json(url: str, payload: dict, timeout: float = 240.0) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def render_turn(turn: dict, *, label: str, out_dir: Path) -> dict:
    request = {
        "answer_text": turn["answer_text"],
        "label": label,
        "use_blessed_qra_cache": False,
        "asr_verify": True,
        "asr_cache": False,
        "asr_max_candidates": 1,
        "voice_delivery": turn["voice_delivery"],
    }
    request_path = out_dir / f"{turn['turn_id']}_request.json"
    response_path = out_dir / f"{turn['turn_id']}_response.json"
    request_path.write_text(json.dumps(request, indent=2) + "\n")
    started = time.time()
    response = post_json(f"{CHATTERBOX}/synthesize-batch", request)
    elapsed = round(time.time() - started, 3)
    response_path.write_text(json.dumps(response, indent=2) + "\n")
    engine = response.get("engine") or response.get("chunk_engine") or response.get("asr_engine")
    first_chunk = (response.get("chunks") or [{}])[0]
    asr_verification = first_chunk.get("asr_verification") or {}
    first_candidate = ((asr_verification.get("candidates") or [{}])[0])
    asr_gate = (response.get("asr_gate")
                or asr_verification.get("accepted_gate")
                or (first_candidate.get("asr") or {}).get("gate")
                or {})
    asr_transcript = (response.get("asr_transcript")
                      or (first_candidate.get("asr") or {}).get("transcript"))
    finished_metrics = response.get("finished_response_metrics") or {}
    if engine != "chatterbox_base":
        raise RuntimeError(f"BLOCKED_CHATTERBOX_ENGINE_IGNORES_CONTROLS:{engine}")
    if asr_gate.get("ok") is not True:
        raise RuntimeError(f"BLOCKED_CHATTERBOX_ASR_GATE:{asr_gate}")
    return {
        "turn_id": turn["turn_id"],
        "label": label,
        "request_path": str(request_path),
        "request_sha256": "sha256:" + _sha(request),
        "response_path": str(response_path),
        "response_sha256": "sha256:" + _sha(response),
        "elapsed_seconds": elapsed,
        "engine": engine,
        "cache_material_engine": response.get("cache_material_engine"),
        "chunk_engine": response.get("chunk_engine"),
        "asr_engine": response.get("asr_engine"),
        "requested_tone": response.get("requested_tone"),
        "normalized_tone": response.get("normalized_tone"),
        "tone_was_normalized": (response.get("voice_delivery") or {}).get("tone_was_normalized"),
        "emotion_knobs": (response.get("emotion_knobs")
                          or (response.get("cache_material") or {}).get("emotion_knobs")
                          or first_chunk.get("emotion_knobs")),
        "asr_transcript": asr_transcript,
        "asr_gate": asr_gate,
        "finished_response_audio": response.get("finished_response_audio"),
        "finished_wav_sha256": response.get("finished_wav_sha256") or finished_metrics.get("sha256"),
        "finished_wav_duration_seconds": (response.get("finished_wav_duration_seconds")
                                          or finished_metrics.get("duration_seconds")),
    }


def run_live(persona: str, *, session_id: str, out_dir: Path, turns: list[str]) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    binding = session_mood_binding.bind_session(persona, session_id=session_id)
    for idx, text in enumerate(turns, start=1):
        session_mood_binding.add_turn(binding, text, turn_id=f"turn_{idx:03d}")
    session_mood_binding.validate_binding(binding)
    render_results = []
    for turn in binding["turns"]:
        label = f"persona-dream-{session_id}-{turn['turn_id']}"
        render_results.append(render_turn(turn, label=label, out_dir=out_dir))
    receipt = {
        "schema": "persona_dream.session_mood_chatterbox_live_receipt.v1",
        "created_at": "2026-07-27T16:50:00Z",
        "status": "PASS_SESSION_MOOD_CHATTERBOX_LIVE",
        "mocked": False,
        "live": True,
        "endpoint": f"POST {CHATTERBOX}/synthesize-batch",
        "binding": binding,
        "render_results": render_results,
        "claims": {
            "proves": [
                "deterministic session_mood voice_delivery reached live Chatterbox /synthesize-batch",
                "all rendered turns used chatterbox_base",
                "ASR accepted all rendered turns under the Chatterbox gate",
                "answer_text stayed unchanged before render"
            ],
            "does_not_prove": [
                "exact WER 0.0 for every stochastic render",
                "perceived target emotion",
                "speaker similarity",
                "adversarial Embry recognition",
                "live Memory or Watch availability",
                "browser or microphone path"
            ]
        },
    }
    receipt_path = out_dir / "RECEIPT.json"
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--persona", default="embry")
    parser.add_argument("--session-id", default="p2_3_session_mood_chatterbox")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--turn", action="append", default=[])
    args = parser.parse_args()
    turns = args.turn or [
        "I can hold the boundary clearly.",
        "The answer is unchanged.",
        "The boundary remains clear.",
    ]
    receipt = run_live(args.persona, session_id=args.session_id,
                       out_dir=args.out_dir, turns=turns)
    print(json.dumps({
        "status": receipt["status"],
        "session_id": receipt["binding"]["session_id"],
        "mood_label": receipt["binding"]["session_mood"]["mood_label"],
        "turn_count": len(receipt["render_results"]),
        "engines": [r["engine"] for r in receipt["render_results"]],
        "wers": [r["asr_gate"]["wer"] for r in receipt["render_results"]],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
