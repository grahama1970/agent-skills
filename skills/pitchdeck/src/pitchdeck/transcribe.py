"""Record-and-transcribe speaker narration into slide notes (RealtimeSTT + faster-whisper).

The mic capture and transcription run in the RealtimeSTT project's own venv
(REALSTT_PYTHON overrides the interpreter) via a small runner: RealtimeSTT's
AudioToTextRecorder captures until silence, faster-whisper transcribes. The
transcript is APPENDED to the slide's notes through apply_slide_edit — the
validated path — so required qualifiers living in notes are never clobbered.
No API keys; local models only. Failure modes: missing interpreter/deps or
empty transcript report NEEDS_ATTENTION with the exact remedy; nothing is
written on failure.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from loguru import logger

REALSTT_ROOT = Path.home() / "workspace" / "experiments" / "RealtimeSTT"

_RUNNER = r"""
import sys
sys.path.insert(0, {realstt_root!r})  # RealtimeSTT is used from its checkout
from RealtimeSTT import AudioToTextRecorder

recorder = AudioToTextRecorder(model="base.en", spinner=False, use_microphone=True)
print("SPEAK NOW (stops on silence)", file=sys.stderr)
text = recorder.text()
recorder.shutdown()
print(text)
"""


def _interpreter() -> Path | None:
    override = os.getenv("REALSTT_PYTHON")
    candidates = [Path(override)] if override else []
    candidates.append(REALSTT_ROOT / ".venv" / "bin" / "python")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def record_transcript(timeout_seconds: int = 120) -> dict:
    """Capture one utterance from the microphone and return its transcript."""
    python = _interpreter()
    if python is None:
        return {
            "status": "NEEDS_ATTENTION",
            "reason": f"no RealtimeSTT interpreter; create {REALSTT_ROOT}/.venv or set REALSTT_PYTHON",
        }
    result = subprocess.run(
        [str(python), "-c", _RUNNER.format(realstt_root=str(REALSTT_ROOT))],
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    transcript = result.stdout.strip()
    if result.returncode != 0 or not transcript:
        return {
            "status": "NEEDS_ATTENTION",
            "reason": f"recorder exit {result.returncode}: {result.stderr.strip()[-200:] or 'empty transcript'}",
        }
    return {"status": "PASS", "transcript": transcript}


def record_note(
    bundle_dir: Path,
    output_dir: Path,
    *,
    slide_id: str,
    deck_name: str = "deck.public.yaml",
    timeout_seconds: int = 120,
) -> dict:
    """Record narration and append it to the slide's speaker notes (validated write)."""
    captured = record_transcript(timeout_seconds)
    if captured["status"] != "PASS":
        return captured
    from .io import load_yaml
    from .models import DeckManifest
    from .slide_edit import apply_slide_edit

    deck = load_yaml(bundle_dir / deck_name, DeckManifest)
    slide = next((s for s in deck.slides if s.id == slide_id), None)
    if slide is None:
        raise ValueError(f"no slide '{slide_id}'")
    existing = slide.notes.strip()
    merged = f"{existing}\n\n[narration] {captured['transcript']}" if existing else captured["transcript"]
    apply_slide_edit(bundle_dir, output_dir, slide_id=slide_id, field="notes", value=merged, deck_name=deck_name)
    logger.info("narration appended to {} notes ({} chars)", slide_id, len(captured["transcript"]))
    return {"status": "PASS", "transcript": captured["transcript"], "slide_id": slide_id}
