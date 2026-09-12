#!/usr/bin/env python3
"""Render persona-dream speech through $chatterbox-speak (the one speaking engine).

Operator rule (2026-09-12): persona-dream must not bespoke its own speaking
engine for the conversation. All conversation/journal speech renders route
through chatterbox-speak's `speak` front door, which owns pronunciation
normalization, the render-chunk passthrough, temperature (the audible Turbo
affect knob; tone is request-only), receipts, and fail-closed live validation.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CHATTERBOX_SPEAK_RUN = Path(os.environ.get(
    "CHATTERBOX_SPEAK_RUN", str(ROOT.parent / "chatterbox-speak" / "run.sh")))
CONVERSATION_TEMPERATURE = 0.85  # Turbo expressiveness; tune by ear, receipt-recorded


def render_via_chatterbox_speak(
    *, answer_text: str, render_chunks: list[dict[str, Any]], tone: str,
    run_dir: Path, label: str, ref_audio: str | None = None,
    temperature: float = CONVERSATION_TEMPERATURE, context: str = "",
) -> tuple[Path, dict[str, Any]]:
    """Render caller-owned chunks through the chatterbox-speak front door.

    Returns (wav_path_in_run_dir, service_receipt). Raises SystemExit
    (BLOCKED_RENDER_NOT_SPOKEN) when the engine reports anything other than a
    live, ok render — the engine's own fail-closed validation is authoritative.
    """
    plan_path = run_dir / f"{label}.render_chunks.json"
    plan_path.write_text(json.dumps({
        "schema": "persona_dream.render_chunks_plan.v1",
        "status": "render_planned",
        "answer_text": answer_text, "render_chunks": render_chunks,
    }))
    cmd = ["bash", str(CHATTERBOX_SPEAK_RUN), "speak",
           "--tone", tone or "neutral_warm",
           "--render-chunks-plan", str(plan_path),
           "--temperature", str(temperature),
           "--context", context or f"persona-dream {label}"]
    if ref_audio:
        cmd += ["--ref-audio", ref_audio]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise SystemExit(
            f"BLOCKED_RENDER_NOT_SPOKEN: chatterbox-speak rc={proc.returncode} "
            f"{(proc.stdout or '')[-300:]}{(proc.stderr or '')[-300:]}")
    out = json.loads(proc.stdout or "{}")
    if not out.get("ok"):
        raise SystemExit(f"BLOCKED_RENDER_NOT_SPOKEN: {json.dumps(out)[:300]}")
    receipt = json.loads(Path(out["receipt"]).read_text())
    if not receipt.get("live"):
        raise SystemExit("BLOCKED_RENDER_NOT_SPOKEN: engine reports not-live render")
    dest = run_dir / f"{label}.wav"
    shutil.copyfile(out["wav"], dest)
    service_receipt = receipt.get("service_receipt") or {}
    service_receipt.setdefault("render_path", "chatterbox-speak")
    service_receipt.setdefault("render_source", receipt.get("render_source"))
    service_receipt.setdefault("render_temperature", receipt.get("temperature"))
    service_receipt.setdefault("pronunciation_normalized", receipt.get("pronunciation_normalized"))
    return dest, service_receipt


if __name__ == "__main__":
    dest, resp = render_via_chatterbox_speak(
        answer_text="The Eye of Tzeentch held steady while the relay clicked.",
        render_chunks=[{"text": "The Eye of Tzeentch held steady", "tone": "curious_searching",
                        "pause_after_ms": 400, "role": "persona_affect_beat", "interruptible": True},
                       {"text": "while the relay clicked.", "tone": "curious_searching",
                        "pause_after_ms": 0, "role": "persona_affect_beat", "interruptible": True}],
        tone="curious_searching", run_dir=Path("/tmp"), label="pd_composition_selfcheck")
    print("RENDER_VIA_CHATTERBOX_SPEAK_OK", dest, resp.get("render_path"),
          resp.get("render_temperature"), resp.get("pronunciation_normalized"))
