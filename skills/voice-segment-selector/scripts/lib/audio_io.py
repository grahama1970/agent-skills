"""Audio normalization and clip extraction."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

from lib.constants import AUDIO_EXTENSIONS, SAMPLE_RATE, VIDEO_EXTENSIONS


def probe_duration_sec(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    return float(payload["format"]["duration"])


def normalize_to_wav(input_path: Path, wav_path: Path) -> Path:
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = input_path.suffix.lower()
    if suffix in VIDEO_EXTENSIONS or suffix in AUDIO_EXTENSIONS:
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(input_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                str(SAMPLE_RATE),
                str(wav_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    else:
        raise ValueError(f"Unsupported input type: {input_path}")
    return wav_path


def load_wav(path: Path) -> tuple[np.ndarray, int]:
    y, sr = librosa.load(str(path), sr=SAMPLE_RATE, mono=True)
    return y, sr


def extract_clip(source_wav: Path, start_sec: float, end_sec: float, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{start_sec:.3f}",
            "-to",
            f"{end_sec:.3f}",
            "-i",
            str(source_wav),
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            str(out_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def write_clip_array(y: np.ndarray, sr: int, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(out_path, y, sr)


def load_chapters(chapters_json: Path) -> list[dict]:
    payload = json.loads(chapters_json.read_text())
    chapters = payload.get("chapters", payload)
    rows: list[dict] = []
    for chapter in chapters:
        rows.append(
            {
                "title": chapter.get("tags", {}).get("title", f"chapter-{len(rows)+1}"),
                "start_sec": float(chapter["start_time"]),
                "end_sec": float(chapter["end_time"]),
            }
        )
    return rows
