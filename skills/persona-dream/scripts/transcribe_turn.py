#!/usr/bin/env python3
"""Turn a recorded utterance into the text of a conversation turn.

Voice mode needs both directions. Chatterbox already owns the outbound half and
owns it well -- fifteen calibrated tones, per-render receipts. The inbound half
had nothing, so talking to her meant typing at her.

This uses local Whisper. That is a deliberate choice over the browser's
SpeechRecognition API, which ships the audio to a third party: every other part
of this loop -- the memories, the journal, the voice -- runs on this machine,
and routing only the human's half of the conversation off-box would be a strange
place to make an exception.

`embry-voice-control` declares the endpoint contract this would eventually
belong behind (`POST /listen/start`, `POST /turn`, with listener evidence and
speaker identity). That control plane is not implemented yet -- the running
service exposes only the listener event bus -- so this is a local stand-in
scoped to one thing: bytes in, text out. When the control plane lands, this
should be replaced by it rather than grown.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

#: Small is enough for close-mic conversational speech and keeps a turn
#: responsive; the model is a knob because a slower one is sometimes worth it.
WHISPER_MODEL = os.environ.get("PERSONA_DREAM_WHISPER_MODEL", "small.en")
WHISPER_BIN = os.environ.get("PERSONA_DREAM_WHISPER_BIN", "whisper")


def stt_health() -> dict[str, Any]:
    """Say plainly whether dictation can work, so the UI can disable the mic."""
    binary = shutil.which(WHISPER_BIN)
    return {
        "available": bool(binary),
        "engine": "whisper",
        "model": WHISPER_MODEL,
        "binary": binary,
        "local": True,
        "reason": None if binary else f"{WHISPER_BIN!r} not found on PATH",
        "control_plane": (
            "embry-voice-control declares POST /listen/start and POST /turn for "
            "this, including speaker identity and listener evidence. Only its "
            "listener event bus is implemented today, so this is a local "
            "stand-in and should be replaced by that contract, not extended."
        ),
    }


def transcribe(audio: bytes, suffix: str = ".webm") -> dict[str, Any]:
    """Transcribe one utterance. Returns a receipt, never raises on bad audio."""
    health = stt_health()
    if not health["available"]:
        return {
            "schema": "persona_dream.transcript_receipt.v1",
            "status": "BLOCKED_STT_UNAVAILABLE",
            "failed_gates": [health["reason"]],
            "text": "",
        }
    if not audio:
        return {
            "schema": "persona_dream.transcript_receipt.v1",
            "status": "BLOCKED_NO_AUDIO",
            "failed_gates": ["empty_audio"],
            "text": "",
        }

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        src = tmp_dir / f"utterance{suffix}"
        src.write_bytes(audio)
        proc = subprocess.run(
            [WHISPER_BIN, str(src), "--model", WHISPER_MODEL,
             "--output_format", "json", "--output_dir", str(tmp_dir),
             "--fp16", "False"],
            capture_output=True, text=True, timeout=300,
        )
        out = src.with_suffix(".json")
        if proc.returncode != 0 or not out.is_file():
            return {
                "schema": "persona_dream.transcript_receipt.v1",
                "status": "BLOCKED_TRANSCRIPTION_FAILED",
                "failed_gates": [f"whisper_exit_{proc.returncode}"],
                "stderr_tail": proc.stderr[-600:],
                "text": "",
            }
        payload = json.loads(out.read_text(encoding="utf-8"))

    text = str(payload.get("text") or "").strip()
    return {
        "schema": "persona_dream.transcript_receipt.v1",
        "status": "PASS_TRANSCRIBED" if text else "BLOCKED_EMPTY_TRANSCRIPT",
        "mocked": False,
        "live": True,
        "engine": "whisper",
        "model": WHISPER_MODEL,
        "local": True,
        "text": text,
        "language": payload.get("language"),
        "failed_gates": [] if text else ["transcript_was_empty"],
        "boundary": (
            "This is what the recogniser heard, not a verified quotation. "
            "No speaker identity is established; $memory owns that."
        ),
    }


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("audio", type=Path, nargs="?", help="audio file to transcribe")
    ap.add_argument("--health", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if args.health or not args.audio:
        print(json.dumps(stt_health(), indent=2, sort_keys=True))
        return 0

    result = transcribe(args.audio.read_bytes(), suffix=args.audio.suffix)
    print(json.dumps(result, indent=2, sort_keys=True) if args.json
          else f"{result['status']}  {result.get('text','')}")
    return 0 if result["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
