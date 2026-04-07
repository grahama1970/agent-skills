#!/usr/bin/env python3
"""Tool: audio_processor
Purpose: Add sound effects and music
Uses: FFmpeg, audio mixing
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _validate_path(value: str | None, label: str) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")
    return path


def mix_audio(
    voice: Path | None,
    music: Path | None,
    sfx: Path | None,
    output: Path,
    duration: float | None,
    voice_volume: float,
    music_volume: float,
    sfx_volume: float,
    dry_run: bool = False,
) -> bool:
    inputs: list[str] = []
    filters: list[str] = []
    mix_inputs: list[str] = []
    idx = 0

    def add_input(path: Path, label: str, volume: float) -> None:
        nonlocal idx
        inputs.extend(["-i", str(path)])
        filters.append(f"[{idx}:a]volume={volume}[{label}]")
        mix_inputs.append(f"[{label}]")
        idx += 1

    if voice:
        add_input(voice, "voice", voice_volume)
    if music:
        add_input(music, "music", music_volume)
    if sfx:
        add_input(sfx, "sfx", sfx_volume)

    if not mix_inputs:
        print("No input audio provided. Use --voice, --music, or --sfx.", file=sys.stderr)
        return False

    output.parent.mkdir(parents=True, exist_ok=True)

    if dry_run:
        print(f"DRY RUN: would mix {len(mix_inputs)} tracks -> {output}")
        return True

    filter_complex = ";".join(
        filters + [f"{''.join(mix_inputs)}amix=inputs={len(mix_inputs)}:duration=longest[mix]"]
    )
    cmd = ["ffmpeg", "-y"] + inputs + [
        "-filter_complex", filter_complex,
        "-map", "[mix]",
    ]
    if duration:
        cmd += ["-t", str(duration)]
    cmd += ["-c:a", "aac", "-b:a", "192k", str(output)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err = result.stderr.strip()
        print(err[:500] if err else "FFmpeg failed", file=sys.stderr)
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Mix narration, music, and SFX audio")
    parser.add_argument("--voice", help="Narration/dialogue track")
    parser.add_argument("--music", help="Background music track")
    parser.add_argument("--sfx", help="Sound effects track")
    parser.add_argument("--output", "-o", required=True, help="Output audio path")
    parser.add_argument("--duration", type=float, default=None, help="Trim/pad to duration in seconds")
    parser.add_argument("--voice-volume", type=float, default=1.0)
    parser.add_argument("--music-volume", type=float, default=0.3)
    parser.add_argument("--sfx-volume", type=float, default=0.5)
    parser.add_argument("--dry-run", action="store_true", help="Validate inputs without running FFmpeg")
    args = parser.parse_args()

    try:
        voice = _validate_path(args.voice, "Voice")
        music = _validate_path(args.music, "Music")
        sfx = _validate_path(args.sfx, "SFX")
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    output = Path(args.output)
    success = mix_audio(
        voice=voice,
        music=music,
        sfx=sfx,
        output=output,
        duration=args.duration,
        voice_volume=args.voice_volume,
        music_volume=args.music_volume,
        sfx_volume=args.sfx_volume,
        dry_run=args.dry_run,
    )
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
