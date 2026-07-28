#!/usr/bin/env python3
"""Render deterministic session-mood voice_delivery turns through live Chatterbox."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CHATTERBOX = "http://127.0.0.1:8018"

#: Voice the renders are conditioned on, sent explicitly with every request.
#: Verified 2026-07-28 as what the service default already resolved to, so
#: naming it changes nothing about the audio -- only about whether the receipt
#: can prove which voice produced it. Whether this candidate should be the
#: authorized Embry reference is a governance decision, tracked in #1070.
REF_AUDIO = ROOT / "voice_clone_candidates" / "embry_kling_clone_candidate.wav"
CHATTERBOX_OUT_HOST_ROOT = Path(
    os.environ.get("CHATTERBOX_OUT_HOST_ROOT", "/home/graham/workspace/experiments/chatterbox/logs")
)


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


session_mood_binding = _load("session_mood_binding")


def _sha(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _normalize_text(text: str | None) -> str:
    return " ".join("".join(ch.lower() if ch.isalnum() else " " for ch in (text or "")).split())


def post_json(url: str, payload: dict, timeout: float = 240.0) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def snapshot_finished_audio(turn_id: str, response: dict, *, out_dir: Path) -> dict:
    source = response.get("finished_response_audio")
    if not source:
        raise RuntimeError("BLOCKED_CHATTERBOX_AUDIO_ARTIFACT_MISSING:no_finished_response_audio")
    source_path = resolve_audio_path(source)
    if source_path is None:
        raise RuntimeError(f"BLOCKED_CHATTERBOX_AUDIO_ARTIFACT_MISSING:{source}")
    snapshot_path = out_dir / f"{turn_id}_finished_response.wav"
    shutil.copy2(source_path, snapshot_path)
    snapshot_sha = _sha_file(snapshot_path)
    reported_sha = (response.get("finished_wav_sha256")
                    or (response.get("finished_response_metrics") or {}).get("sha256"))
    if reported_sha:
        normalized = str(reported_sha).removeprefix("sha256:")
        if normalized != snapshot_sha:
            raise RuntimeError(
                "BLOCKED_CHATTERBOX_AUDIO_HASH_MISMATCH:"
                f"reported={reported_sha}:snapshot=sha256:{snapshot_sha}"
            )
    return {
        "audio_snapshot_status": "PASS_AUDIO_SNAPSHOT_DURABLE",
        "finished_response_audio_source": source,
        "finished_response_audio_resolved_source": str(source_path),
        "finished_response_audio_snapshot": str(snapshot_path),
        "finished_response_audio_snapshot_sha256": "sha256:" + snapshot_sha,
    }


def resolve_audio_path(source: str) -> Path | None:
    source_path = Path(source)
    if source_path.is_file():
        return source_path
    if source_path.is_absolute() and len(source_path.parts) > 2 and source_path.parts[1] == "out":
        host_path = CHATTERBOX_OUT_HOST_ROOT.joinpath(*source_path.parts[2:])
        if host_path.is_file():
            return host_path
    return None


def render_turn(turn: dict, *, label: str, out_dir: Path) -> dict:
    request = {
        "answer_text": turn["answer_text"],
        "label": label,
        "use_blessed_qra_cache": False,
        "asr_verify": True,
        "asr_cache": False,
        "asr_max_candidates": 3,
        "asr_max_wer": 0.0,
        "voice_delivery": turn["voice_delivery"],
        # Explicit, never the service default. Relying on CHATTERBOX_REF_AUDIO
        # meant the renders were conditioned on a clone candidate with nothing
        # in the request, response, or receipt naming it (#1070). An unrecorded
        # voice cannot be audited, and a default can change under you.
        "ref_audio": str(REF_AUDIO),
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
    if _normalize_text(asr_transcript) != _normalize_text(turn["answer_text"]):
        raise RuntimeError(
            "BLOCKED_CHATTERBOX_ASR_TEXT_DRIFT:"
            f"expected={turn['answer_text']!r}:actual={asr_transcript!r}"
        )
    audio_snapshot = snapshot_finished_audio(turn["turn_id"], response, out_dir=out_dir)
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
        **audio_snapshot,
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
        # Which voice produced this audio, provable after the fact (#1070).
        "conditioning_reference": {
            "path": str(REF_AUDIO),
            "exists": REF_AUDIO.is_file(),
            "sha256": "sha256:" + hashlib.sha256(REF_AUDIO.read_bytes()).hexdigest()
            if REF_AUDIO.is_file() else None,
        },
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
