"""Memory upsert and artifact persistence for watch skill.

Stores watch results (frames, audio, QRA pairs) to:
  - /mnt/storage12tb/media/watch-frames/<slug>/ for frames + audio
  - watch_content collection via memory daemon /upsert endpoint
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import httpx
from loguru import logger

from config import WATCH_MEDIA_ROOT, MEMORY_DAEMON_URL, WHISPER_API_KEY, WHISPER_API_URL

WATCH_FRAMES_DIR = WATCH_MEDIA_ROOT


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
        dst_name = f.get("persist_name") or src.name
        dst = dest / dst_name
        shutil.copy2(str(src), str(dst))
        row = dict(f)
        row["path"] = str(dst)
        persisted.append(row)
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


def generate_playable_segments(
    video_path: str,
    frames: list[dict],
    duration_seconds: float,
    slug: str,
    max_segment_seconds: float = 60.0,
) -> tuple[list[dict], list[str]]:
    """Create browser-playable MP4, MP3, and WAV clips aligned to scene rows.

    The report cannot rely on AVI/Xvid fragments in browser media elements. This
    exports small H.264/AAC MP4 segments for the movie column plus MP3 and WAV
    clips for the sound column. Failures are returned as gaps instead of
    aborting watch.
    """
    if not frames:
        return frames, []

    dest = WATCH_FRAMES_DIR / slug
    clips_dir = dest / "clips"
    audio_dir = dest / "audio_mp3"
    audio_wav_dir = dest / "audio_wav"
    clips_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    audio_wav_dir.mkdir(parents=True, exist_ok=True)

    timestamps = [float(f.get("timestamp_seconds", 0.0)) for f in frames]
    updated: list[dict] = []
    gaps: list[str] = []
    for idx, frame in enumerate(frames, start=1):
        start = timestamps[idx - 1]
        next_start = timestamps[idx] if idx < len(timestamps) else duration_seconds
        end = max(start, min(next_start, start + max_segment_seconds))
        if end <= start:
            end = start + 1.0

        video_out = clips_dir / f"segment_{idx:04d}.mp4"
        audio_out = audio_dir / f"audio_{idx:04d}.mp3"
        audio_wav_out = audio_wav_dir / f"audio_{idx:04d}.wav"
        row = dict(frame)

        if _run_segment_ffmpeg(video_path, start, end, video_out, media="video"):
            row["video_clip_path"] = str(video_out)
        else:
            gaps.append(f"video_clip_failed:{idx}")

        if _run_segment_ffmpeg(video_path, start, end, audio_out, media="audio"):
            row["audio_clip_path"] = str(audio_out)
        else:
            gaps.append(f"audio_clip_failed:{idx}")

        if _run_segment_ffmpeg(video_path, start, end, audio_wav_out, media="audio_wav"):
            row["audio_wav_clip_path"] = str(audio_wav_out)
        else:
            gaps.append(f"audio_wav_clip_failed:{idx}")

        updated.append(row)

    return updated, gaps


def _run_segment_ffmpeg(video_path: str, start: float, end: float, out_path: Path, media: str) -> bool:
    if out_path.exists() and out_path.stat().st_size > 0:
        return True
    duration = max(0.1, end - start)
    base = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-t",
        f"{duration:.3f}",
        "-i",
        str(Path(video_path).resolve()),
    ]
    if media == "video":
        cmd = base + [
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "28",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-ac",
            "2",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(out_path),
        ]
    elif media == "audio":
        cmd = base + [
            "-vn",
            "-af",
            "volume=12dB",
            "-ac",
            "2",
            "-ar",
            "44100",
            "-c:a",
            "libmp3lame",
            "-b:a",
            "160k",
            str(out_path),
        ]
    else:
        cmd = base + [
            "-vn",
            "-af",
            "volume=12dB",
            "-ac",
            "2",
            "-ar",
            "44100",
            "-c:a",
            "pcm_s16le",
            str(out_path),
        ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    except (OSError, subprocess.TimeoutExpired) as exc:
        logger.error("{} segment export failed at {:.3f}-{:.3f}: {}", media, start, end, exc)
        return False
    if result.returncode != 0 or not out_path.exists() or out_path.stat().st_size == 0:
        logger.error("{} segment export failed at {:.3f}-{:.3f}: {}", media, start, end, result.stderr.strip()[:300])
        return False
    return True


def upsert_qras(
    qra_pairs: list[dict], source: str, title: str,
    duration: float, frame_count: int, sampling_mode: str,
    transcript_source: str | None, slug: str, now: str,
    persisted_frames: list[dict], audio_path: str | None = None,
    visual_descriptions: list[dict] | None = None,
    scene_elements: list[dict] | None = None,
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
            "visual_descriptions": json.dumps(visual_descriptions or []),
            "scene_elements": json.dumps(scene_elements or []),
            "model": pair.get("_model", "unknown"),
            "scope": "watch_history", "tags": ["watch_history", sampling_mode, slug],
        })
    if not docs:
        return 0
    try:
        resp = httpx.post(
            f"{MEMORY_DAEMON_URL}/upsert",
            json={"collection": "watch_content", "documents": docs},
            timeout=15.0,
        )
        if resp.status_code == 200:
            logger.info("upserted {} QRA pairs to watch_content: {}", len(docs), title)
            return len(docs)
        logger.error("memory upsert failed ({}): {}", resp.status_code, resp.text)
    except httpx.ConnectError:
        logger.error("memory daemon not reachable at {}", MEMORY_DAEMON_URL)
    except Exception as exc:
        logger.error("memory upsert error: {}", exc)
    return 0


def upsert_scene_elements(
    scene_elements: list[dict],
    source: str,
    title: str,
    slug: str,
    now: str,
    diff_intelligence: dict | None = None,
    persona: str | None = None,
) -> int:
    """Upsert individual scene rows to watch_content for timecode-level recall."""
    docs = []
    for row in scene_elements:
        timecode = row.get("timecode", "")
        if not timecode:
            continue
        seed = f"{source}:{title}:{slug}:scene:{timecode}"
        doc_key = f"watch-scene-{hashlib.sha256(seed.encode()).hexdigest()[:16]}"
        diff = row.get("diff_info") or {}
        tags = ["watch_history", "watch_scene", slug]
        if persona:
            tags.append(f"persona:{persona}")
        if diff.get("category"):
            tags.append(f"divergence:{diff['category']}")
        if row.get("total_chunks"):
            tags.append(f"chunk:{int(row['chunk_index']) + 1}-of-{row['total_chunks']}")
        srt_text = (row.get("srt_text") or "").strip()
        whisper_text = (row.get("text") or "").strip()
        doc = {
            "_key": doc_key,
            "question": f"What happens in {title} at {timecode}?",
            "answer": f"SRT: {srt_text[:300]}\nWhisper: {whisper_text[:300]}"[:500],
            "title": title[:200],
            "source": source,
            "timecode": timecode,
            "movie_segment": row.get("movie_segment", ""),
            "srt_text": srt_text[:500],
            "whisper_text": whisper_text[:500],
            "visual_description": (row.get("visual_description") or "")[:500],
            "scene_image_path": row.get("scene_marker_image_path", ""),
            "diff_category": diff.get("category", ""),
            "diff_confidence": diff.get("confidence", 0),
            "diff_detail": (diff.get("detail") or "")[:200],
            "watched_at": now,
            "frame_dir": str(WATCH_FRAMES_DIR / slug),
            "scope": "watch_history",
            "tags": tags,
        }
        for chunk_field in ("chunk_index", "total_chunks", "chunk_start_seconds", "chunk_end_seconds"):
            if chunk_field in row:
                doc[chunk_field] = row[chunk_field]
        docs.append(doc)
    if not docs:
        return 0
    keys = [d["_key"] for d in docs]
    try:
        resp = httpx.post(
            f"{MEMORY_DAEMON_URL}/upsert",
            json={"collection": "watch_content", "documents": docs},
            timeout=30.0,
        )
        if resp.status_code == 200:
            logger.info("upserted {} scene elements to watch_content: {}", len(docs), title)
            return keys
        logger.error("scene memory upsert failed ({}): {}", resp.status_code, resp.text)
    except httpx.ConnectError:
        logger.error("memory daemon not reachable at {}", MEMORY_DAEMON_URL)
    except Exception as exc:
        logger.error("scene memory upsert error: {}", exc)
    return []


def upsert_persona_watch_record(
    title: str,
    source: str,
    slug: str,
    now: str,
    duration_seconds: float,
    scene_count: int,
    frame_count: int,
    diff_percentage: int = 0,
    persona: str | None = None,
    scene_keys: list[str] | None = None,
) -> int:
    """Record that a persona watched this film in persona_memory."""
    persona_id = persona or "default"
    seed = f"watch:{persona_id}:{slug}:{now[:10]}"
    doc_key = f"watch-{persona_id}-{slug}-{now[:10]}"
    tags = ["watch_history", f"persona:{persona_id}", "media:movie", slug]
    answer_text = f"{persona_id.capitalize()} watched {title} ({duration_seconds:.0f}s, {scene_count} scenes)"
    retrieval_text = (
        f"{persona_id.capitalize()} watched {title} on {now[:10]}. "
        f"It is {duration_seconds:.0f}s long with {scene_count} scenes and {frame_count} frames extracted."
    )
    doc = {
        "_key": doc_key,
        "persona_id": persona_id,
        "retrieval_text": retrieval_text,
        "question_text": f"What movies has {persona_id.capitalize()} watched?",
        "answer_text": answer_text,
        "title": title[:200],
        "source": source,
        "media_type": "movie",
        "duration_seconds": duration_seconds,
        "scene_count": scene_count,
        "frame_count": frame_count,
        "diff_percentage": diff_percentage,
        "slug": slug,
        "watch_report_path": slug,
        "watched_at": now,
        "watch_content_keys": json.dumps(scene_keys or []),
        "scope": "persona_memory",
        "tags": tags,
    }
    try:
        resp = httpx.post(
            f"{MEMORY_DAEMON_URL}/upsert",
            json={"collection": "persona_memory", "documents": [doc]},
            timeout=15.0,
        )
        if resp.status_code == 200:
            logger.info("stored persona watch record for {}: {}", persona_id, title)
            return 1
        logger.error("persona memory upsert failed ({}): {}", resp.status_code, resp.text[:200])
    except httpx.ConnectError:
        logger.error("memory daemon not reachable at {}", MEMORY_DAEMON_URL)
    except Exception as exc:
        logger.error("persona memory upsert error: {}", exc)
    return 0


def upsert_visual_descriptions(
    visual_descriptions: list[dict],
    source: str,
    title: str,
    slug: str,
    now: str,
) -> int:
    """Upsert frame-level visual evidence to watch_content.

    These records are intentionally separate from transcript QRA records so
    appearance questions can retrieve image-derived evidence instead of
    transcript-only summaries.
    """
    docs = []
    for item in visual_descriptions:
        description = str(item.get("description", "")).strip()
        if not description:
            continue
        index = int(item.get("index", len(docs)))
        timestamp = float(item.get("timestamp", item.get("timestamp_seconds", 0.0)))
        seed = f"{source}:{title}:{slug}:visual:{index}:{timestamp:.3f}"
        doc_key = f"watch-visual-{hashlib.sha256(seed.encode()).hexdigest()[:16]}"
        frame_path = str(item.get("path", ""))
        docs.append({
            "_key": doc_key,
            "question": f"What visual evidence appears in {title} at {timestamp:.0f} seconds?",
            "answer": description[:700],
            "title": title[:200],
            "source": source,
            "timestamp_seconds": timestamp,
            "frame_index": index,
            "frame_path": frame_path,
            "visual_description": description[:1000],
            "visual_description_source": item.get("source", "vlm"),
            "visual_description_status": "described",
            "watched_at": now,
            "frame_dir": str(WATCH_FRAMES_DIR / slug),
            "scope": "watch_history",
            "tags": ["watch_history", "visual_evidence", slug],
        })
    if not docs:
        return 0
    try:
        resp = httpx.post(
            f"{MEMORY_DAEMON_URL}/upsert",
            json={"collection": "watch_content", "documents": docs},
            timeout=15.0,
        )
        if resp.status_code == 200:
            logger.info("upserted {} visual descriptions to watch_content: {}", len(docs), title)
            return len(docs)
        logger.error("visual memory upsert failed ({}): {}", resp.status_code, resp.text)
    except httpx.ConnectError:
        logger.error("memory daemon not reachable at {}", MEMORY_DAEMON_URL)
    except Exception as exc:
        logger.error("visual memory upsert error: {}", exc)
    return 0
