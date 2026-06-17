"""Memory upsert and artifact persistence for watch skill.

Stores watch results (frames, audio, QRA pairs) to:
  - /mnt/storage12tb/media/watch-frames/<slug>/ for frames + audio
  - watch_content collection via memory daemon /upsert endpoint
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from pathlib import Path

import httpx
from loguru import logger

WATCH_FRAMES_DIR = Path("/mnt/storage12tb/media/watch-frames")


def _slugify(title: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\s-]", "", title).strip().lower()
    s = re.sub(r"[\s]+", "-", s)
    return s[:80] or "untitled"


def persist_frames(frames: list[dict], slug: str) -> list[dict]:
    """Copy frames to persistent storage on 12TB drive."""
    import re
    dest = WATCH_FRAMES_DIR / slug
    dest.mkdir(parents=True, exist_ok=True)
    import shutil
    persisted = []
    for f in frames:
        src = Path(f["path"])
        if not src.exists():
            continue
        dst = dest / src.name
        shutil.copy2(str(src), str(dst))
        persisted.append({"index": f["index"], "timestamp_seconds": f["timestamp_seconds"], "path": str(dst)})
    return persisted


def extract_and_persist_audio(video_path: str, work_dir: Path, slug: str) -> str | None:
    """Extract audio from video via ffmpeg and persist to 12TB."""
    audio_src = work_dir / "audio.wav"
    if not audio_src.exists():
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(audio_src)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0 or not audio_src.exists():
            logger.error("audio extraction failed: {}", result.stderr.strip()[:200])
            return None
    import shutil
    dest = WATCH_FRAMES_DIR / slug
    dest.mkdir(parents=True, exist_ok=True)
    audio_dst = dest / "audio.wav"
    shutil.copy2(str(audio_src), str(audio_dst))
    return str(audio_dst)


def upsert_qras(
    qra_pairs: list[dict], source: str, title: str,
    duration: float, frame_count: int, sampling_mode: str,
    transcript_source: str | None, slug: str, now: str,
    persisted_frames: list[dict], audio_path: str | None = None,
) -> int:
    """Upsert QRA documents to watch_content collection via memory daemon."""
    base_seed = f"{source}:{title}:{now[:10]}"
    docs = []
    for i, pair in enumerate(qra_pairs):
        q = pair.get("question", f"what did I watch about {title[:120]}")
        a = pair.get("answer", title[:200])
        doc_key = f"watch-{hashlib.sha256(f'{base_seed}:q{i}'.encode()).hexdigest()[:16]}"
        docs.append({
            "_key": doc_key,
            "question": q[:300],
            "reasoning": json.dumps({
                "source": source, "duration_seconds": duration,
                "frame_count": frame_count, "sampling_mode": sampling_mode,
                "transcript_source": transcript_source, "watched_at": now,
                "frame_dir": str(WATCH_FRAMES_DIR / slug),
            }),
            "answer": a[:500],
            "title": title[:200], "source": source,
            "duration_seconds": duration, "frame_count": frame_count,
            "sampling_mode": sampling_mode, "transcript_source": transcript_source,
            "watched_at": now, "frame_dir": str(WATCH_FRAMES_DIR / slug),
            "frames": json.dumps(persisted_frames),
            "audio_path": audio_path or "",
            "scope": "watch_history", "tags": ["watch_history", sampling_mode, slug],
        })
    if not docs:
        return 0
    try:
        resp = httpx.post(
            "http://127.0.0.1:8601/upsert",
            json={"collection": "watch_content", "documents": docs},
            timeout=15.0,
        )
        if resp.status_code == 200:
            logger.info("upserted {} QRA pairs to watch_content: {}", len(docs), title)
            return len(docs)
        logger.error("memory upsert failed ({}): {}", resp.status_code, resp.text)
    except httpx.ConnectError:
        logger.error("memory daemon not reachable at 127.0.0.1:8601")
    except Exception as exc:
        logger.error("memory upsert error: {}", exc)
    return 0
