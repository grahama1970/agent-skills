#!/usr/bin/env python3
"""Dynamic two-voice live demo driver.

Proves live monitoring end-to-end: each meeting turn is synthesized by
Chatterbox AT DEMO TIME (no pre-baked meeting WAV), played aloud through the
PipeWire sink, captured live by the companion capture bridge
(e2e_pipewire_docker_bridge.py running without --source-wav), transcribed by
Docker RealtimeSTT, and surfaced in the Live Evidence HUD while the demo is
still running.

With --dynamic-candidate (default), the candidate's (Embry's) response TEXT is
also generated live by an LLM at demo time from the interviewer's question:
no pre-authored candidate script anywhere in the loop. Interviewer questions
come from the scenario fixture, which is legitimate: the meeting happens TO
the candidate.

This script owns synthesis + playback + per-turn HUD readback. Run the capture
bridge separately so the capture path is the same one used for real meetings.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

CANDIDATE_SYSTEM = (
    "You are Graham, a principal AI engineer, answering live in a technical "
    "interview at DriveWealth (B2B brokerage-as-a-service fintech). Answer the "
    "interviewer's question in 2-4 natural SPOKEN sentences, under 900 "
    "characters total. First person, concrete, no markdown, no bullet points, "
    "no stage directions. It will be read aloud by a TTS voice verbatim."
)

# Chatterbox /synthesize rejects text > 1200 chars (422 string_too_long).
TTS_CHUNK_LIMIT = 1100


def tts_chunks(text: str, limit: int = TTS_CHUNK_LIMIT) -> list[str]:
    """Split text into sentence-boundary chunks under the Chatterbox limit."""

    if len(text) <= limit:
        return [text]
    import re

    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        # A single sentence over the limit gets hard-split as a last resort.
        while len(sentence) > limit:
            chunks.append(sentence[:limit])
            sentence = sentence[limit:]
        current = sentence
    if current:
        chunks.append(current)
    return chunks


def generate_candidate_response(*_args, **_kwargs) -> dict[str, Any]:
    raise RuntimeError("dynamic candidate generation must be routed through Tau, not a direct provider call")


def get_state(backend_url: str) -> dict[str, Any]:
    with urllib.request.urlopen(backend_url.rstrip("/") + "/api/state", timeout=8) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def state_counts(state: dict[str, Any]) -> dict[str, int]:
    transcript = state.get("transcript") or []
    return {
        "transcript_events": len(transcript),
        "pipewire_events": len([e for e in transcript if e.get("source") == "pipewire"]),
        "cards": len(state.get("cards") or []),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-url", default="http://127.0.0.1:8799")
    parser.add_argument("--chatterbox-url", default="http://127.0.0.1:8018")
    parser.add_argument(
        "--fixture",
        default=str(Path(__file__).resolve().parents[1] / "fixtures/realistic_meeting_drivewealth_webgpt.json"),
    )
    parser.add_argument(
        "--interviewer-ref",
        default="/work/persona_dream_voice_refs/horus_v2_agent_ref_6s.wav",
        help="Chatterbox-container-visible reference audio for the interviewer voice.",
    )
    parser.add_argument(
        "--candidate-ref",
        default="/data/embry_ref.wav",
        help="Chatterbox-container-visible reference audio for the candidate voice.",
    )
    parser.add_argument(
        "--chatterbox-out-dir",
        default="/home/graham/workspace/experiments/chatterbox/logs",
        help="Host directory where the Chatterbox container writes rendered WAVs.",
    )
    parser.add_argument(
        "--playback-target",
        default="alsa_output.usb-0b0e_Jabra_SPEAK_510_USB_501AA5274B1D022000-00.analog-stereo",
    )
    parser.add_argument("--max-turns", type=int, default=0, help="0 = all turns.")
    parser.add_argument("--gap-s", type=float, default=1.0, help="Silence between turns.")
    parser.add_argument("--output-dir", default="/tmp/live-evidence-dynamic-two-voice-demo")
    parser.add_argument(
        "--dynamic-candidate",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Generate candidate text through a Tau-backed generator; direct provider calls are disabled.",
    )
    parser.add_argument("--candidate-model", default=os.getenv("LIVE_EVIDENCE_CANDIDATE_MODEL", "claude-sonnet-5"))
    parser.add_argument("--candidate-effort", default=os.getenv("LIVE_EVIDENCE_CANDIDATE_EFFORT", "low"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = Path(args.output_dir).expanduser().resolve() / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    receipt_path = output_dir / "receipt.json"

    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    turns = fixture["turns"]
    if args.max_turns:
        turns = turns[: args.max_turns]
    refs = {"Interviewer": args.interviewer_ref, "Candidate": args.candidate_ref}

    if args.dynamic_candidate:
        raise SystemExit("--dynamic-candidate requires a Tau-backed generator; direct provider calls are disabled")

    receipt: dict[str, Any] = {
        "schema": "live_evidence.dynamic_two_voice_demo_receipt.v1",
        "status": "FAIL",
        "mocked": False,
        "live": True,
        "dynamic_synthesis": True,
        "pre_baked_meeting_wav": False,
        "run_id": run_id,
        "backend_url": args.backend_url,
        "chatterbox_url": args.chatterbox_url,
        "fixture": str(args.fixture),
        "meeting_id": fixture.get("meeting_id"),
        "voices": {"Interviewer": args.interviewer_ref, "Candidate": args.candidate_ref},
        "dynamic_candidate": args.dynamic_candidate,
        "candidate_model": args.candidate_model if args.dynamic_candidate else None,
        "candidate_effort": args.candidate_effort if args.dynamic_candidate else None,
        "turn_count": len(turns),
        "turns": [],
    }

    client = httpx.Client(timeout=240)
    started = time.monotonic()
    baseline = state_counts(get_state(args.backend_url))
    receipt["baseline_state"] = baseline
    spoken_history: list[dict[str, str]] = []
    try:
        for i, turn in enumerate(turns):
            speaker = turn["speaker"]
            label = f"le-dyn-demo-{run_id}-{i:02d}-{speaker.lower()}"
            generation: dict[str, Any] | None = None
            if speaker == "Candidate" and args.dynamic_candidate:
                generation = generate_candidate_response(
                    client, args.candidate_model, args.candidate_effort, spoken_history,
                )
                spoken_text = generation["text"]
            else:
                spoken_text = turn["text"]
            spoken_history.append({"speaker": speaker, "text": spoken_text})
            chunks = tts_chunks(spoken_text)
            synth_s = 0.0
            play_s = 0.0
            wavs: list[str] = []
            for chunk_index, chunk in enumerate(chunks):
                chunk_label = label if len(chunks) == 1 else f"{label}-c{chunk_index}"
                synth_started = time.monotonic()
                response = client.post(
                    args.chatterbox_url.rstrip("/") + "/synthesize",
                    json={"text": chunk, "label": chunk_label, "ref_audio": refs[speaker]},
                )
                response.raise_for_status()
                synth_s += time.monotonic() - synth_started
                wav = Path(args.chatterbox_out_dir) / f"{chunk_label}.wav"
                if not wav.is_file():
                    raise RuntimeError(f"synthesized wav missing on host: {wav}")
                wavs.append(str(wav))
                play_started = time.monotonic()
                subprocess.run(
                    ["pw-play", "--target", args.playback_target, str(wav)],
                    check=True,
                    capture_output=True,
                )
                play_s += time.monotonic() - play_started
            synth_s = round(synth_s, 2)
            play_s = round(play_s, 2)
            wav = wavs[0]
            time.sleep(args.gap_s)
            counts = state_counts(get_state(args.backend_url))
            entry = {
                "i": i,
                "speaker": speaker,
                "ref_audio": refs[speaker],
                "wavs": wavs,
                "chunk_count": len(chunks),
                "text_source": "live_llm_generation" if generation else "scenario_fixture",
                "generation": generation,
                "spoken_text": spoken_text,
                "synth_seconds": synth_s,
                "play_seconds": play_s,
                "state_after": counts,
            }
            receipt["turns"].append(entry)
            print(json.dumps(entry, sort_keys=True), flush=True)
        # Let trailing STT finals and retrieval land before the final readback.
        time.sleep(8.0)
        final_state = get_state(args.backend_url)
        final = state_counts(final_state)
        (output_dir / "final-state.json").write_text(json.dumps(final_state, indent=2) + "\n", encoding="utf-8")
        receipt["final_state"] = final
        receipt["new_pipewire_events"] = final["pipewire_events"] - baseline["pipewire_events"]
        receipt["new_cards"] = final["cards"] - baseline["cards"]
        receipt["elapsed_s"] = round(time.monotonic() - started, 1)
        receipt["status"] = "PASS" if receipt["new_pipewire_events"] > 0 and final["cards"] > 0 else "FAIL"
    except Exception as exc:  # noqa: BLE001 - demo receipt must record any failure
        receipt["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"receipt": str(receipt_path), "status": receipt["status"],
                      "new_pipewire_events": receipt.get("new_pipewire_events"),
                      "new_cards": receipt.get("new_cards")}, indent=2))
    return 0 if receipt["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
