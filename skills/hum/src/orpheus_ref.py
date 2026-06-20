"""Build a longer multi-clip Orpheus target reference for Seed-VC."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

ORPHEUS_CHECKPOINTS = Path(
    os.environ.get(
        "ORPHEUS_CHECKPOINTS_ROOT",
        "/mnt/storage12tb/skills/voice-segment-selector/checkpoints",
    )
)
DEFAULT_CLIP_DIR = Path(
    os.environ.get(
        "HUM_ORPHEUS_REF_CLIPS_DIR",
        "/mnt/storage12tb/skills/voice-segment-selector/jobs/embry-lawson-orpheus/orpheus-dataset/clips",
    )
)


def _duration(path: Path) -> float:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and proc.stdout.strip():
        return float(proc.stdout.strip())
    return 0.0


def build_multi_clip_ref(
    out_path: Path,
    *,
    persona: str = "embry",
    clip_dir: Path | None = None,
    target_seconds: float = 24.0,
    max_clips: int = 5,
) -> Path | None:
    """Concatenate accepted Orpheus dataset clips into one Seed-VC target."""
    roots = [
        clip_dir or DEFAULT_CLIP_DIR,
        ORPHEUS_CHECKPOINTS / f"{persona}_orpheus_lora",
        Path(f"/mnt/storage12tb/media/personas/{persona}/tts_output"),
    ]

    clips: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for wav in sorted(root.rglob("*.wav")):
            if wav.name.startswith("."):
                continue
            if "smoke" in wav.name and root != (clip_dir or DEFAULT_CLIP_DIR):
                continue
            if _duration(wav) >= 2.0:
                clips.append(wav)
        if clips:
            break

    if not clips:
        return None

    selected: list[Path] = []
    total = 0.0
    for wav in clips:
        if len(selected) >= max_clips:
            break
        selected.append(wav)
        total += _duration(wav)
        if total >= target_seconds:
            break

    if not selected:
        return None

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    list_file = out_path.with_suffix(".concat.txt")
    list_file.write_text("\n".join(f"file '{p}'" for p in selected) + "\n")

    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-ac", "1", "-ar", "24000", str(out_path),
        ],
        capture_output=True,
        text=True,
    )
    list_file.unlink(missing_ok=True)
    if proc.returncode != 0 or not out_path.is_file():
        return None
    return out_path
