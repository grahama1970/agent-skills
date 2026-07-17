#!/usr/bin/env python3
"""Verify rendered dialogue text and timing with local Whisper word timestamps."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def normalize_transcript(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", value.lower()))


def assess_alignment(
    *,
    canonical_text: str,
    whisper_payload: dict[str, Any],
    timeline_offset_seconds: float,
    expected_start_seconds: float,
    expected_end_seconds: float,
    tolerance_seconds: float = 0.5,
) -> dict[str, Any]:
    words = [
        word
        for segment in whisper_payload.get("segments", [])
        for word in segment.get("words", [])
        if word.get("start") is not None and word.get("end") is not None
    ]
    recognized_text = str(whisper_payload.get("text") or "").strip()
    relative_start = min((float(word["start"]) for word in words), default=None)
    relative_end = max((float(word["end"]) for word in words), default=None)
    absolute_start = timeline_offset_seconds + relative_start if relative_start is not None else None
    absolute_end = timeline_offset_seconds + relative_end if relative_end is not None else None
    checks = {
        "words_detected": bool(words),
        "canonical_text_exact_after_normalization": (
            normalize_transcript(recognized_text) == normalize_transcript(canonical_text)
        ),
        "spoken_onset_within_tolerance": (
            absolute_start is not None
            and abs(absolute_start - expected_start_seconds) <= tolerance_seconds
        ),
        "spoken_end_within_tolerance": (
            absolute_end is not None
            and abs(absolute_end - expected_end_seconds) <= tolerance_seconds
        ),
    }
    return {
        "status": "PASS_FORCED_DIALOGUE_ALIGNMENT" if all(checks.values()) else "FAIL_FORCED_DIALOGUE_ALIGNMENT",
        "recognized_text": recognized_text,
        "relative_spoken_interval_seconds": {"start": relative_start, "end": relative_end},
        "absolute_spoken_interval_seconds": {"start": absolute_start, "end": absolute_end},
        "checks": checks,
    }


def verify_with_whisper(
    *,
    dialogue_path: Path,
    canonical_text: str,
    timeline_offset_seconds: float,
    expected_start_seconds: float,
    expected_end_seconds: float,
    output_dir: Path,
    model: str = "large-v3-turbo",
    model_dir: Path = Path.home() / ".cache/whisper",
) -> dict[str, Any]:
    whisper = shutil.which("whisper")
    if not whisper:
        raise RuntimeError("Whisper CLI is not installed")
    model_path = model_dir / f"{model}.pt"
    if not model_path.is_file():
        raise RuntimeError(f"Whisper model is not cached: {model_path}")
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        whisper,
        str(dialogue_path),
        "--model", model,
        "--model_dir", str(model_dir),
        "--device", "cuda",
        "--language", "en",
        "--task", "transcribe",
        "--word_timestamps", "True",
        "--output_format", "json",
        "--output_dir", str(output_dir),
        "--verbose", "False",
        "--fp16", "True",
    ]
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    raw_path = output_dir / f"{dialogue_path.stem}.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    assessment = assess_alignment(
        canonical_text=canonical_text,
        whisper_payload=raw,
        timeline_offset_seconds=timeline_offset_seconds,
        expected_start_seconds=expected_start_seconds,
        expected_end_seconds=expected_end_seconds,
    )
    return {
        "schema": "persona_dream.dialogue_forced_alignment_receipt.v1",
        **assessment,
        "canonical_text": canonical_text,
        "timeline_offset_seconds": timeline_offset_seconds,
        "expected_spoken_interval_seconds": {
            "start": expected_start_seconds,
            "end": expected_end_seconds,
        },
        "rendered_audio_path": str(dialogue_path),
        "rendered_audio_sha256": sha256_file(dialogue_path),
        "whisper": {
            "executable": whisper,
            "model": model,
            "model_sha256": sha256_file(model_path),
            "raw_result_path": str(raw_path),
            "raw_result_sha256": sha256_file(raw_path),
            "command": command,
            "returncode": completed.returncode,
        },
        "mocked": False,
        "live": True,
        "claims": {
            "proves": ["local Whisper recognized the canonical line and measured its spoken interval inside the declared transcript timing tolerance"],
            "does_not_prove": ["visible mouth motion matches the measured speech", "subjective voice quality"],
        },
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
