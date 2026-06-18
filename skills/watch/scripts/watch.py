#!/usr/bin/env python3
"""Watch: download, frame-extract, transcribe, and scene-analyze any video.

Composes with sibling skills:
  - ingest-youtube: transcript for YouTube URLs (3-tier fallback)
  - ingest-movie: SRT scene/emotion analysis for local files
  - doc2qra: QRA extraction from transcripts (optional)

Input: video URL, local file path, or movie title
Output: frames + transcript + 3 QRA pairs + image descriptions + audio descriptions
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from loguru import logger

SCRIPT_DIR = Path(__file__).parent.resolve()
WATCH_DIR = SCRIPT_DIR.parent
SKILLS_DIR = WATCH_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from download import download, is_url, is_youtube_url
from frames import extract_frames, get_metadata, format_time, parse_time, auto_fps, auto_fps_focus
from qra import generate_qras, describe_scene_images, describe_audio_tracks
from report import build_scene_elements, write_report, write_html_report, write_markdown_report, write_frames_manifest
from scenes import parse_srt, find_scenes, analyze_emotions
from storage import (
    persist_frames,
    extract_and_persist_audio,
    generate_playable_segments,
    upsert_qras,
    upsert_visual_descriptions,
    _slugify,
    WATCH_FRAMES_DIR,
)
from transcribe import transcribe_video, parse_captions, filter_segments, align_segments_to_reference

MOVIE_LIBRARY = Path("/mnt/storage12tb/media/movies")


def _env_without_venv() -> dict:
    return {k: v for k, v in os.environ.items() if not k.startswith("VIRTUAL_") and not k.startswith("PYTHON")}


def _call_ingest_youtube(url: str, lang: str = "en", no_whisper: bool = True) -> dict | None:
    ingest_dir = SKILLS_DIR / "ingest-youtube"
    if not ingest_dir.exists():
        return None
    cmd = ["uv", "run", "--directory", str(ingest_dir),
           "python", "youtube_transcript.py", "get", "--url", url, "--lang", lang, "--no-enrich"]
    if no_whisper:
        cmd.append("--no-whisper")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, env=_env_without_venv())
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    if data.get("errors"):
        return None
    segments = [{"text": s.get("text", ""), "start": float(s.get("start", 0)), "duration": float(s.get("duration", 0))} for s in data.get("transcript", [])]
    meta = data.get("meta", {})
    return {"source": f"ingest-youtube ({meta.get('method', 'unknown')})", "segments": segments,
            "full_text": data.get("full_text", ""), "video_title": meta.get("title"), "channel": meta.get("channel")}


def _find_movie_in_library(title: str) -> Path | None:
    if not MOVIE_LIBRARY.exists():
        return None
    import re
    title_lower = title.lower().strip()
    for entry in MOVIE_LIBRARY.iterdir():
        name = entry.name
        name_lower = name.lower()
        if title_lower in name_lower:
            return entry
        name_stripped = re.sub(r"[.\s\-_]+", " ", name_lower).strip()
        title_stripped = re.sub(r"[.\s\-_]+", " ", title_lower).strip()
        if title_stripped in name_stripped or name_stripped in title_stripped:
            return entry
    return None


def _find_video_in_dir(dir_path: Path) -> Path | None:
    video_exts = {".mp4", ".mkv", ".webm", ".mov", ".avi", ".m4v"}
    for f in dir_path.iterdir():
        if f.suffix.lower() in video_exts and f.is_file():
            return f
    for f in dir_path.rglob("*"):
        if f.suffix.lower() in video_exts and f.is_file():
            return f
    return None


def _find_srt_in_dir(dir_path: Path) -> Path | None:
    for f in dir_path.iterdir():
        if f.suffix.lower() == ".srt":
            return f
    for f in dir_path.rglob("*.srt"):
        return f
    return None


def _check_radarr_library(title: str) -> dict | None:
    api_key = os.environ.get("RADARR_API_KEY", "")
    radarr_url = os.environ.get("RADARR_URL", "http://localhost:7878")
    if not api_key:
        return None
    try:
        resp = httpx.get(f"{radarr_url}/api/v3/movie", params={"apikey": api_key}, timeout=15)
        if resp.status_code != 200:
            return None
        title_lower = title.lower().strip()
        for m in resp.json():
            m_title = m.get("title", "").lower()
            if title_lower in m_title or m_title in title_lower:
                return {"in_library": True, "has_file": m.get("hasFile", False), "title": m.get("title"),
                        "year": m.get("year"), "tmdb_id": m.get("tmdbId"), "downloaded": m.get("hasFile", False)}
        return {"in_library": False}
    except Exception as exc:
        logger.debug("Radarr check failed: {}", exc)
        return None


def _resolve_movie_source(source: str) -> str | None:
    if is_url(source) or Path(source).exists():
        return source
    movie_dir = _find_movie_in_library(source)
    if movie_dir:
        video = _find_video_in_dir(movie_dir) if movie_dir.is_dir() else movie_dir
        if video and video.exists():
            return str(video)
    radarr_status = _check_radarr_library(source)
    if radarr_status:
        if radarr_status.get("has_file"):
            pass
        elif radarr_status.get("in_library"):
            logger.info("in Radarr but not downloaded (tmdbId={})", radarr_status.get("tmdb_id"))
        else:
            logger.info("not in Radarr. Add via ingest-movie: cd {} && ./run.sh acquire radarr --preset horus_standard --execute", SKILLS_DIR / "ingest-movie")
    return None


def run_watch(
    source: str,
    scene_change: bool = True,
    fps: float | None = None,
    max_frames: int = 100,
    resolution: int = 512,
    start: str | None = None,
    end: str | None = None,
    subtitle: str | None = None,
    emotion: str | None = None,
    tag: str | None = None,
    query: str | None = None,
    whisper: bool = True,
    doc2qra: bool = False,
    out_dir: str | None = None,
    json_output: bool = False,
) -> int:
    """Main watch pipeline: resolve source, extract frames, transcribe, generate QRA, store to memory."""
    max_frames_capped = min(max_frames, 100)

    raw_source = source
    source_url = raw_source if is_url(raw_source) else None
    resolved_source = raw_source
    resolved_from_library = False

    if not is_url(raw_source) and not Path(raw_source).exists():
        movie_path = _resolve_movie_source(raw_source)
        if movie_path:
            resolved_source = movie_path
            resolved_from_library = True
        else:
            logger.error("cannot resolve '{}' — not a URL, not on disk, not in library", raw_source)
            return 1

    work = Path(out_dir).expanduser().resolve() if out_dir else Path(tempfile.mkdtemp(prefix="watch-"))
    work.mkdir(parents=True, exist_ok=True)
    logger.info("working dir: {}", work)

    try:
        dl = download(resolved_source, work / "download")
    except Exception as exc:
        logger.error("download/source probe failed: {}", exc)
        return 1
    video_path = dl["video_path"]
    logger.info("video: {}", video_path)

    try:
        meta = get_metadata(video_path)
    except Exception as exc:
        logger.error("media metadata probe failed: {}", exc)
        return 1
    full_duration = meta["duration_seconds"]
    gaps: list[str] = []

    start_sec = parse_time(start)
    end_sec = parse_time(end)
    focused = start_sec is not None or end_sec is not None
    effective_start = start_sec if start_sec is not None else 0.0
    effective_end = end_sec if end_sec is not None else full_duration
    effective_duration = max(0.0, effective_end - effective_start)

    calc_fps, target = (auto_fps_focus(effective_duration, max_frames_capped) if focused
                        else auto_fps(effective_duration, max_frames_capped))
    use_fps = fps
    use_scene = scene_change and use_fps is None and not focused
    scope_str = (f"{format_time(effective_start)}-{format_time(effective_end)} ({effective_duration:.1f}s)"
                 if focused else f"full {effective_duration:.1f}s")

    try:
        frames, sampling_mode = extract_frames(
            video_path, work / "frames",
            use_scene_change=use_scene, fps=use_fps, resolution=resolution,
            max_frames=max_frames_capped, start_seconds=start_sec, end_seconds=end_sec,
        )
    except Exception as exc:
        logger.error("frame extraction failed: {}", exc)
        return 1
    logger.info("extracted {} frames ({})", len(frames), sampling_mode)

    transcript = None
    captions = None
    sub_path = subtitle or dl.get("subtitle_path")
    if sub_path is None and resolved_from_library:
        lib_srt = _find_srt_in_dir(Path(resolved_source).parent)
        if lib_srt:
            sub_path = str(lib_srt)

    def _filter_transcript(t: dict | None, st: float | None, en: float | None) -> dict | None:
        if t is None:
            return None
        t["segments"] = filter_segments(t["segments"], st, en)
        t["full_text"] = " ".join(s["text"] for s in t["segments"])
        return t

    if source_url and is_youtube_url(source):
        ingest_result = _call_ingest_youtube(source, no_whisper=True)
        if ingest_result:
            transcript = _filter_transcript(ingest_result, start_sec, end_sec)
        elif whisper:
            ingest_result = _call_ingest_youtube(source, no_whisper=False)
            if ingest_result:
                transcript = _filter_transcript(ingest_result, start_sec, end_sec)

    if sub_path and Path(sub_path).exists():
        try:
            captions = parse_captions(sub_path)
            captions["source"] = f"english-srt:{sub_path}"
            captions = _filter_transcript(captions, start_sec, end_sec)
            if transcript is None and not whisper:
                transcript = captions
        except Exception as exc:
            logger.error("caption parse failed: {}", exc)
            gaps.append("caption_parse_failed")
    else:
        gaps.append("missing_english_srt")

    if whisper and not source_url:
        try:
            w_result = transcribe_video(video_path, work)
            transcript = _filter_transcript(w_result, start_sec, end_sec)
        except RuntimeError as exc:
            logger.error("Whisper failed: {}", exc)
            gaps.append("transcription_failed")
            if transcript is None and captions is not None:
                transcript = captions

    if captions and transcript and captions is not transcript:
        captions, alignment = align_segments_to_reference(captions, transcript)
        if alignment:
            if alignment.get("status") == "shifted":
                gaps.append(f"srt_whisper_alignment_corrected:{alignment.get('offset_seconds')}s")
            elif alignment.get("status") not in {"already_aligned"}:
                gaps.append(f"srt_whisper_alignment_{alignment.get('status')}")

    if transcript is None:
        gaps.append("missing_transcript")

    qra_result = None
    if transcript and transcript.get("full_text") and doc2qra:
        from qra import _build_scene_chunks, _call_doc2qra_scene
        scenes_text = _build_scene_chunks(transcript["segments"], frames, sampling_mode)
        if scenes_text:
            qra_results = []
            for scene in scenes_text:
                r = _call_doc2qra_scene(scene["text"], scene["index"], title, scene["start_seconds"], scene["end_seconds"])
                if r:
                    qra_results.append(r)
            if qra_results:
                qra_result = {"scene_count": len(qra_results), "scenes": qra_results}

    scenes_analysis = None
    emotion_analysis = None
    if sub_path and Path(sub_path).exists() and not source_url:
        try:
            entries = parse_srt(Path(sub_path))
            emotion_analysis = analyze_emotions(entries)
            if emotion or tag or query:
                scenes_analysis = find_scenes(entries, query=query, tag=tag, emotion=emotion)
        except Exception as exc:
            logger.error("SRT analysis failed: {}", exc)

    title = transcript.get("video_title") if transcript and transcript.get("video_title") else dl.get("info", {}).get("title") or Path(source).stem

    manifest_path = work / "frames_manifest.json"
    write_frames_manifest(frames, manifest_path, source=source, sampling_mode=sampling_mode,
                          frame_count=len(frames), max_frames=max_frames_capped,
                          resolution=resolution, duration_seconds=full_duration)

    if transcript:
        (work / "transcript.json").write_text(json.dumps(transcript, indent=2))
    if scenes_analysis:
        (work / "scenes.json").write_text(json.dumps({"matches": scenes_analysis}, indent=2))

    persisted_frames = persist_frames(frames, _slugify(title))
    audio_path = extract_and_persist_audio(video_path, work, _slugify(title)) if video_path else None
    visual_descriptions = []
    try:
        visual_descriptions = describe_scene_images(persisted_frames or frames, title)
    except Exception as exc:
        logger.error("image description failed: {}", exc)
    if frames and not visual_descriptions:
        gaps.append("image_descriptions_missing")
    transcript_source = transcript.get("source") if transcript else None
    uploader = dl.get("info", {}).get("uploader")
    full_text = transcript.get("full_text", "") if transcript else ""
    slug = _slugify(title)
    playable_frames = persisted_frames or frames
    try:
        playable_frames, clip_gaps = generate_playable_segments(video_path, playable_frames, full_duration, slug)
        gaps.extend(clip_gaps)
    except Exception as exc:
        logger.error("browser playable clip generation failed: {}", exc)
        gaps.append("playable_clip_generation_failed")

    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    scene_elements = build_scene_elements(playable_frames, full_duration, transcript, visual_descriptions, audio_path, captions)

    report_path = work / "report.md"
    write_markdown_report(
        report_path, source, title, full_duration, sampling_mode, playable_frames,
        transcript, scenes_analysis, emotion_analysis, focused_range=scope_str if focused else None,
        gaps=gaps, visual_descriptions=visual_descriptions, audio_path=audio_path,
    )
    html_report_path = work / "report.html"
    write_html_report(
        html_report_path, source, title, full_duration, sampling_mode, playable_frames,
        transcript, scenes_analysis, emotion_analysis, captions=captions, focused_range=scope_str if focused else None,
        gaps=gaps, visual_descriptions=visual_descriptions, audio_path=audio_path,
    )

    json_report_path = work / "report.json"
    write_report(
        json_report_path, source, title, full_duration, sampling_mode, playable_frames,
        transcript, scenes_analysis, emotion_analysis,
        metadata={"width": meta.get("width"), "height": meta.get("height"), "codec": meta.get("codec")},
        gaps=gaps, visual_descriptions=visual_descriptions, audio_path=audio_path, captions=captions,
    )

    qra_pairs = generate_qras(full_text, title, uploader) if full_text else None
    if qra_pairs:
        upsert_qras(qra_pairs, source, title, full_duration, len(frames), sampling_mode,
                    transcript_source, slug, now, playable_frames, audio_path, visual_descriptions, scene_elements)
    else:
        logger.warning("no QRA pairs generated — nothing stored to memory")
        if full_text:
            gaps.append("qra_generation_failed")
            write_markdown_report(
                report_path, source, title, full_duration, sampling_mode, playable_frames,
                transcript, scenes_analysis, emotion_analysis, focused_range=scope_str if focused else None,
                gaps=gaps, visual_descriptions=visual_descriptions, audio_path=audio_path,
            )
            write_html_report(
                html_report_path, source, title, full_duration, sampling_mode, playable_frames,
                transcript, scenes_analysis, emotion_analysis, captions=captions, focused_range=scope_str if focused else None,
                gaps=gaps, visual_descriptions=visual_descriptions, audio_path=audio_path,
            )
            write_report(
                json_report_path, source, title, full_duration, sampling_mode, playable_frames,
                transcript, scenes_analysis, emotion_analysis,
                metadata={"width": meta.get("width"), "height": meta.get("height"), "codec": meta.get("codec")},
                gaps=gaps, visual_descriptions=visual_descriptions, audio_path=audio_path, captions=captions,
            )

    if visual_descriptions:
        upsert_visual_descriptions(visual_descriptions, source, title, slug, now)

    if json_output:
        print(json_report_path.read_text())
    else:
        _print_summary(source, title, full_duration, meta, frames, sampling_mode, transcript, scenes_analysis, emotion_analysis, qra_result, work)
    return 0

def _print_summary(source, title, duration, meta, frames, sampling_mode, transcript, scenes, emotion_analysis, qra_result, work):
    m, s = divmod(int(duration), 60)
    dur = f"{m}m {s}s"
    print(f"\n# Watch Report\n")
    print(f"- **Source:** {source}")
    print(f"- **Title:** {title}")
    print(f"- **Duration:** {dur}")
    if meta.get("width") and meta.get("height"):
        print(f"- **Resolution:** {meta['width']}x{meta['height']}")
    print(f"- **Frames:** {len(frames)} ({sampling_mode})")
    if transcript:
        print(f"- **Transcript:** {len(transcript['segments'])} segments ({transcript['source']})")
    else:
        print("- **Transcript:** none available")
    if emotion_analysis:
        print(f"- **Emotion cues:** {len(emotion_analysis.get('emotion_counts', {}))} types")
    if qra_result:
        print(f"- **QRA:** {qra_result['scene_count']} scenes via doc2qra")
    print(f"\n## Frames\n")
    for f in frames[:20]:
        ts = f"{int(f['timestamp_seconds']//60):02d}:{int(f['timestamp_seconds']%60):02d}"
        print(f"- `{f['path']}` (t={ts})")
    if len(frames) > 20:
        print(f"- ... and {len(frames) - 20} more")
    print(f"\n---\nReport: `{work / 'report.md'}`\nHTML report: `{work / 'report.html'}`\nFrames manifest: `{work / 'frames_manifest.json'}`\nWork dir: `{work}`")
