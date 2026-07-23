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
import math
import os
import re
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
from qra import generate_qras, describe_scene_images, describe_scene_images_with_receipt, describe_audio_tracks
from report import build_scene_elements, write_report, write_html_report, write_markdown_report, write_frames_manifest
from scenes import parse_srt, find_scenes, analyze_emotions
from storage import (
    persist_frames,
    extract_and_persist_audio,
    generate_playable_segments,
    upsert_qras,
    upsert_scene_elements,
    upsert_visual_descriptions,
    upsert_persona_watch_record,
    _slugify,
    WATCH_FRAMES_DIR,
)
from transcribe import transcribe_video, parse_captions, filter_segments, align_segments_to_reference, extract_subtitles, has_text_subtitles
from diff_intelligence import build_diff_intelligence
from diarization import diarize_audio, failure_receipt
from speaker_attribution import attribute_speakers
from config import MOVIE_LIBRARY

_CAST_CACHE: dict[str, dict[str, str]] = {}

_COMMON_ALIASES = {
    "grandma": "Granny",
    "granny": "Granny",
    "kid": "Thurman Merman",
    "santa": "Willie T. Soke",
}

def _wikipedia_parse_url(title: str) -> str:
    import urllib.parse

    movie_name = title.split("(")[0].strip().replace(" ", "_")
    page = urllib.parse.quote(movie_name)
    return f"https://en.wikipedia.org/w/api.php?action=parse&page={page}&prop=text&section=2&format=json"


def _word_in(phrase: str, word: str) -> bool:
    return word in phrase.split()

def _fetch_cast_map(title: str) -> dict[str, str]:
    """Query Wikipedia API for cast list and return {Character: Actor} map."""
    import json
    import urllib.request
    cache_key = title.lower().strip()
    if cache_key in _CAST_CACHE:
        return _CAST_CACHE[cache_key]
    api_url = _wikipedia_parse_url(title)
    cast_map: dict[str, str] = {}
    try:
        req = urllib.request.Request(api_url, headers={"User-Agent": "WatchSkill/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        html = data.get("parse", {}).get("text", {}).get("*", "")
        for actor, char in re.findall(r'<li><a[^>]*>([^<]+)</a>\s+as\s+([^<]+)</li>', html):
            actor = actor.strip()
            char = char.strip()
            if char and actor and len(char) > 1 and len(actor) > 1:
                cast_map[char] = actor
        _CAST_CACHE[cache_key] = cast_map
        return cast_map
    except Exception as exc:
        logger.debug("cast lookup failed for {}: {}", title, exc)
        return {}


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
    if MOVIE_LIBRARY is None:
        return None
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
    """Deprecated compatibility shim.

    Watch may inspect the local movie library, but acquisition and Radarr state
    belong to ingest-movie. Keep this function as a no-op for older sanity
    checks/imports while preventing direct Radarr API access from Watch.
    """
    logger.debug(
        "movie acquisition for '{}' is delegated to ingest-movie; Watch does not query Radarr directly",
        title,
    )
    return None


def _resolve_movie_source(source: str) -> str | None:
    if is_url(source) or Path(source).exists():
        return source
    movie_dir = _find_movie_in_library(source)
    if movie_dir:
        video = _find_video_in_dir(movie_dir) if movie_dir.is_dir() else movie_dir
        if video and video.exists():
            return str(video)
    _check_radarr_library(source)
    logger.info(
        "not found in local movie library. Delegate acquisition to ingest-movie: cd {} && ./run.sh acquire radarr --preset horus_standard --execute",
        SKILLS_DIR / "ingest-movie",
    )
    return None


ROLLING_WINDOW_SECONDS = 300.0
ROLLING_WINDOW_OVERLAP_SECONDS = 3.0
ROLLING_MIN_DURATION_SECONDS = 600.0


def _should_use_rolling_window(
    effective_duration: float,
    focused: bool,
    fps: float | None,
    scene_change: bool,
) -> bool:
    return (
        effective_duration > ROLLING_MIN_DURATION_SECONDS
        and not focused
        and fps is None
        and scene_change
    )


def _plan_rolling_windows(
    effective_start: float,
    effective_end: float,
    window_seconds: float = ROLLING_WINDOW_SECONDS,
    overlap_seconds: float = ROLLING_WINDOW_OVERLAP_SECONDS,
) -> list[dict]:
    windows: list[dict] = []
    total_duration = max(0.0, effective_end - effective_start)
    total_chunks = max(1, int(math.ceil(total_duration / window_seconds)))

    for idx in range(total_chunks):
        canonical_start = effective_start + idx * window_seconds
        canonical_end = min(effective_end, canonical_start + window_seconds)
        extract_start = max(effective_start, canonical_start - overlap_seconds)
        extract_end = min(effective_end, canonical_end + overlap_seconds)
        windows.append({
            "chunk_index": idx,
            "total_chunks": total_chunks,
            "chunk_start_seconds": canonical_start,
            "chunk_end_seconds": canonical_end,
            "extract_start_seconds": extract_start,
            "extract_end_seconds": extract_end,
        })
    return windows


def _merge_rolling_frames(all_chunk_frames: list[list[dict]], tolerance_seconds: float = 0.5) -> list[dict]:
    merged: list[dict] = []
    seen: list[float] = []
    for frame in sorted(
        (f for chunk in all_chunk_frames for f in chunk),
        key=lambda f: float(f["timestamp_seconds"]),
    ):
        ts = float(frame["timestamp_seconds"])
        if any(abs(ts - existing) <= tolerance_seconds for existing in seen):
            continue
        row = dict(frame)
        row["index"] = len(merged)
        row["persist_name"] = f"frame_{len(merged) + 1:05d}.jpg"
        merged.append(row)
        seen.append(ts)
    return merged


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
    diarization: str = "auto",
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
    require_diarization: bool = False,
    doc2qra: bool = False,
    persona: str | None = None,
    out_dir: str | None = None,
    json_output: bool = False,
    visual_model: str | None = None,
    visual_fallback_models: str | None = None,
    require_visual_descriptions: bool = False,
) -> int:
    """Main watch pipeline: resolve source, extract frames, transcribe, generate QRA, store to memory."""
    max_frames_capped = min(max_frames, 500)

    # Rolling window: if video exceeds frame budget, split into chunks
    # This ensures long videos get full coverage without hitting the frame cap
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

    frames: list[dict] = []
    sampling_mode = ""

    if _should_use_rolling_window(effective_duration, focused, use_fps, scene_change):
        windows = _plan_rolling_windows(effective_start, effective_end)
        logger.info("rolling window: {} chunks of {:.0f}s for {:.0f}s video",
                     len(windows), ROLLING_WINDOW_SECONDS, effective_duration)
        all_chunk_frames: list[list[dict]] = []
        for w in windows:
            ci = w["chunk_index"]
            try:
                cf, cs = extract_frames(
                    video_path, work / "frames" / f"chunk_{ci:04d}",
                    use_scene_change=True, fps=None, resolution=resolution,
                    max_frames=max_frames_capped,
                    start_seconds=w["extract_start_seconds"],
                    end_seconds=w["extract_end_seconds"],
                )
            except Exception as exc:
                logger.error("chunk {} frame extraction failed: {}", ci, exc)
                continue
            # Keep only frames in canonical chunk range (no overlap)
            owned = [
                dict(f, chunk_index=ci, total_chunks=len(windows),
                     chunk_start_seconds=w["chunk_start_seconds"],
                     chunk_end_seconds=w["chunk_end_seconds"])
                for f in cf
                if w["chunk_start_seconds"] <= f["timestamp_seconds"] < w["chunk_end_seconds"]
            ]
            if owned:
                all_chunk_frames.append(owned)
            logger.info("  chunk {}/{}: {} frames ({:.0f}s-{:.0f}s)",
                        ci + 1, len(windows), len(owned),
                        w["chunk_start_seconds"], w["chunk_end_seconds"])

        if all_chunk_frames:
            frames = _merge_rolling_frames(all_chunk_frames)
            sampling_mode = "rolling-window"
        else:
            logger.error("rolling window produced no frames — falling back to single-pass")
            try:
                frames, sampling_mode = extract_frames(
                    video_path, work / "frames",
                    use_scene_change=use_scene, fps=use_fps, resolution=resolution,
                    max_frames=max_frames_capped, start_seconds=start_sec, end_seconds=end_sec,
                )
            except Exception as exc:
                logger.error("frame extraction failed: {}", exc)
                return 1
    else:
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
    if sub_path is None and video_path:
        extracted = extract_subtitles(video_path)
        if extracted:
            sub_path = extracted
            logger.info("auto-extracted subtitles from video: {}", sub_path)

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
            w_result = transcribe_video(video_path, work, start_seconds=start_sec, end_seconds=end_sec)
            transcript = _filter_transcript(w_result, None, None)
            if transcript and start_sec is not None:
                for seg in transcript.get("segments", []):
                    seg["original_start"] = seg.get("start", 0.0)
                    seg["start"] = round(seg["start"] + start_sec, 3)
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

    title = transcript.get("video_title") if transcript and transcript.get("video_title") else dl.get("info", {}).get("title") or Path(source).stem

    qra_result = None
    if transcript and transcript.get("full_text") and doc2qra:
        logger.warning("--doc2qra is disabled in Watch: optional scene-level doc2qra integration is not implemented")
        gaps.append("doc2qra_disabled")

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
    visual_description_receipt = None
    try:
        visual_descriptions, visual_description_receipt = describe_scene_images_with_receipt(
            persisted_frames or frames,
            title,
            model=visual_model,
            fallback_models=visual_fallback_models,
        )
        (work / "visual_description_receipt.json").write_text(json.dumps(visual_description_receipt, indent=2))
    except Exception as exc:
        logger.error("image description failed: {}", exc)
        visual_description_receipt = {
            "schema": "watch.visual_description_receipt.v1",
            "status": "exception",
            "mocked": False,
            "live": True,
            "requested_model": visual_model,
            "fallback_models": [],
            "frame_count": len(persisted_frames or frames),
            "described_count": 0,
            "gate": {"status": "failed", "reason": "exception"},
            "error_type": exc.__class__.__name__,
            "error": str(exc),
        }
        (work / "visual_description_receipt.json").write_text(json.dumps(visual_description_receipt, indent=2))
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
    diarization_receipt = None
    if diarization != "none" and audio_path:
        diarization_receipt = diarize_audio(
            audio_path,
            mode=diarization,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
            duration_seconds=full_duration,
        )
        (work / "diarization.json").write_text(json.dumps(diarization_receipt, indent=2))
        if diarization_receipt.get("status") == "complete":
            transcript = _apply_speaker_attribution(transcript, diarization_receipt)
            captions = _apply_speaker_attribution(captions, diarization_receipt)
            if transcript:
                (work / "transcript.json").write_text(json.dumps(transcript, indent=2))
        else:
            code = str(diarization_receipt.get("error_code", "DIARIZATION_INFERENCE_FAILED")).lower()
            if diarization == "pyannote" or require_diarization:
                gaps.append(code)
    elif diarization != "none" and require_diarization:
        diarization_receipt = failure_receipt("failed", "DIARIZATION_AUDIO_INVALID", "no audio artifact available for diarization")
        (work / "diarization.json").write_text(json.dumps(diarization_receipt, indent=2))
        gaps.append("diarization_audio_invalid")

    scene_elements = build_scene_elements(playable_frames, full_duration, transcript, visual_descriptions, audio_path, captions)
    diff_intel = build_diff_intelligence(scene_elements)
    cast_map = _fetch_cast_map(title)
    if cast_map and diff_intel.get("character_intel"):
        name_lower = {k.lower(): (k, v) for k, v in cast_map.items()}
        for ci in diff_intel["character_intel"]:
            cn = ci["name"].lower()
            actor = cast_map.get(ci["name"])
            if not actor:
                alias_target = _COMMON_ALIASES.get(cn)
                if alias_target:
                    actor = cast_map.get(alias_target)
            if not actor:
                for wiki_name, (orig_name, act) in name_lower.items():
                    wl = wiki_name.lower()
                    if cn == wl or (wl.startswith(cn) and len(cn) >= 4) or _word_in(wl, cn) or _word_in(cn, wl):
                        actor = act
                        break
            if actor:
                ci["actor"] = actor
                ci["insight"] = f"{ci['name']} ({actor}) — {ci['insight'].split('—', 1)[-1].strip()}"

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
        diff_intelligence=diff_intel,
    )

    json_report_path = work / "report.json"
    write_report(
        json_report_path, source, title, full_duration, sampling_mode, playable_frames,
        transcript, scenes_analysis, emotion_analysis,
        metadata={"width": meta.get("width"), "height": meta.get("height"), "codec": meta.get("codec")},
        gaps=gaps, visual_descriptions=visual_descriptions, audio_path=audio_path, captions=captions,
        diff_intelligence=diff_intel, visual_description_receipt=visual_description_receipt,
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
                diff_intelligence=diff_intel,
            )
            write_report(
                json_report_path, source, title, full_duration, sampling_mode, playable_frames,
                transcript, scenes_analysis, emotion_analysis,
                metadata={"width": meta.get("width"), "height": meta.get("height"), "codec": meta.get("codec")},
                gaps=gaps, visual_descriptions=visual_descriptions, audio_path=audio_path, captions=captions,
                diff_intelligence=diff_intel, visual_description_receipt=visual_description_receipt,
            )

    if visual_descriptions:
        upsert_visual_descriptions(visual_descriptions, source, title, slug, now)

    scene_keys: list[str] = []
    if scene_elements:
        scene_keys = upsert_scene_elements(scene_elements, source, title, slug, now, diff_intel, persona=persona)
        logger.info("scene_keys count={}, persona={}", len(scene_keys), persona)
        if scene_keys and persona:
            logger.info("calling upsert_persona_watch_record for persona={}", persona)
            upsert_persona_watch_record(
                title, source, slug, now, full_duration,
                scene_count=len(scene_elements),
                frame_count=len(frames),
                diff_percentage=diff_intel.get("overall_diff_percentage", 0) if diff_intel else 0,
                persona=persona,
                scene_keys=scene_keys,
            )
    else:
        logger.warning("no scene elements to store in memory")

    visual_gate_failed = bool(
        visual_description_receipt
        and visual_description_receipt.get("gate", {}).get("status") == "failed"
    )

    if json_output:
        print(json_report_path.read_text())
    else:
        _print_summary(source, title, full_duration, meta, frames, sampling_mode, transcript, scenes_analysis, emotion_analysis, qra_result, work)
    if require_visual_descriptions and visual_gate_failed:
        logger.error("visual description gate failed; see {}", work / "visual_description_receipt.json")
        return 1
    if require_diarization and diarization_receipt and diarization_receipt.get("status") != "complete":
        logger.error("diarization gate failed; see {}", work / "diarization.json")
        return 1
    return 0


def _apply_speaker_attribution(source_doc: dict | None, diarization_receipt: dict | None) -> dict | None:
    attribution = attribute_speakers(source_doc, diarization_receipt)
    if not attribution or not source_doc:
        return source_doc
    enriched = dict(source_doc)
    enriched["segments"] = attribution["segments"]
    enriched["speaker_attribution"] = {
        "schema": attribution["schema"],
        "status": attribution["status"],
        "segment_count": attribution["segment_count"],
        "assigned_count": attribution["assigned_count"],
        "mixed_count": attribution["mixed_count"],
        "unassigned_count": attribution["unassigned_count"],
        "identity_boundary": attribution["identity_boundary"],
    }
    enriched["diarization_source"] = diarization_receipt.get("model", "pyannote")
    enriched["diarization_artifact_path"] = "diarization.json"
    return enriched

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
