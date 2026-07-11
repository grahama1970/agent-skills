from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import httpx


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, out_dir: str | Path, filename: str | None = None) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    if filename is None:
        parsed = urlparse(url)
        filename = Path(parsed.path).name or "download.bin"

    target = out / filename
    with httpx.stream("GET", url, timeout=180.0, follow_redirects=True) as r:
        r.raise_for_status()
        with target.open("wb") as f:
            for chunk in r.iter_bytes(chunk_size=1024 * 1024):
                if chunk:
                    f.write(chunk)
    return target


def have_ffprobe() -> bool:
    return shutil.which("ffprobe") is not None


def have_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


def ffprobe_duration_seconds(path: str | Path) -> float | None:
    if not have_ffprobe():
        return None
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(cmd, check=True, capture_output=True, text=True)
    payload = json.loads(completed.stdout)
    return float(payload["format"]["duration"])


def convert_audio_for_fal_if_needed(path: str | Path, out_dir: str | Path, *, max_bytes: int = 5_000_000) -> Path:
    """Kling LipSync currently limits audio file size, so compress if necessary."""
    src = Path(path)
    if src.stat().st_size <= max_bytes:
        return src

    if not have_ffmpeg():
        raise RuntimeError(
            f"{src} is larger than {max_bytes} bytes and ffmpeg is not available to compress it."
        )

    out = Path(out_dir) / (src.stem + "_fal_128k.mp3")
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-b:a",
        "128k",
        str(out),
    ]
    subprocess.run(cmd, check=True)
    if out.stat().st_size > max_bytes:
        raise RuntimeError(f"Compressed file still exceeds {max_bytes} bytes: {out}")
    return out


def newest_wav_after(roots: list[Path], started_at: float) -> Path | None:
    candidates: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*.wav"):
            try:
                if p.stat().st_mtime >= started_at:
                    candidates.append(p)
            except FileNotFoundError:
                continue
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
