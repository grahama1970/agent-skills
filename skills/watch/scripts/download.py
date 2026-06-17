"""yt-dlp video download wrapper."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


def is_url(value: str) -> bool:
    return value.startswith(("http://", "https://", "www."))


def is_youtube_url(value: str) -> bool:
    return bool(re.search(r"(youtube\.com|youtu\.be)", value))


def download(source: str, out_dir: Path) -> dict:
    if not is_url(source):
        video_path = Path(source).resolve()
        if not video_path.exists():
            raise RuntimeError(f"Local file not found: {video_path}")
        meta = _probe_local(video_path)
        return {"video_path": str(video_path), "subtitle_path": None, "info": meta}

    return _download_url(source, out_dir)


def _probe_local(video_path: Path) -> dict:
    if shutil.which("ffprobe") is None:
        return {"title": video_path.stem, "source": "local"}
    result = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(video_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return {"title": video_path.stem, "source": "local"}
    data = json.loads(result.stdout or "{}")
    fmt = data.get("format", {})
    return {
        "title": fmt.get("tags", {}).get("title", video_path.stem),
        "source": "local",
        "duration": float(fmt.get("duration", 0)),
    }


def _download_url(source: str, out_dir: Path) -> dict:
    if shutil.which("yt-dlp") is None:
        raise RuntimeError("yt-dlp not found on PATH. Install: pip install yt-dlp")

    out_dir.mkdir(parents=True, exist_ok=True)

    dl_result = subprocess.run(
        ["yt-dlp", "--print", "after_move:filepath", "--print", "after_move:title",
         "--print", "after_move:uploader", "--write-subs", "--write-auto-subs",
         "--sub-langs", "en", "--convert-subs", "srt", "--sub-format", "srt",
         "-o", str(out_dir / "%(title)s.%(ext)s"),
         "--no-playlist", source],
        capture_output=True, text=True,
    )
    if dl_result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed for {source}: {dl_result.stderr.strip()}")

    lines = [l.strip() for l in dl_result.stdout.splitlines() if l.strip()]
    video_path = lines[0] if lines else None
    title = lines[1] if len(lines) > 1 else None
    uploader = lines[2] if len(lines) > 2 else None

    if not video_path or not Path(video_path).exists():
        candidates = list(out_dir.iterdir())
        video_exts = {".mp4", ".mkv", ".webm", ".mov", ".avi"}
        video_files = [c for c in candidates if c.suffix.lower() in video_exts and c.is_file()]
        if not video_files:
            raise RuntimeError(f"yt-dlp downloaded but no video file found in {out_dir}")
        video_path = str(video_files[0])

    subtitle_path = None
    srt_candidates = list(Path(video_path).parent.glob(f"{Path(video_path).stem}*.srt"))
    if srt_candidates:
        subtitle_path = str(sorted(srt_candidates, key=lambda p: len(p.name))[0])

    return {
        "video_path": str(Path(video_path).resolve()),
        "subtitle_path": subtitle_path,
        "info": {"title": title or Path(video_path).stem, "uploader": uploader},
    }
