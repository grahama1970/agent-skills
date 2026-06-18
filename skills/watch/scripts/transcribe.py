"""Transcript utilities: SRT caption parsing, local faster-whisper, and segment filtering.

Whisper transcription for URLs is delegated to ingest-youtube (3-tier fallback).
Local faster-whisper handles arbitrary local files (free, GPU-accelerated, no API key).
"""
from __future__ import annotations

import difflib
import re
import statistics
import subprocess
from pathlib import Path


def transcribe_video(video_path: str, work_dir: Path, language: str = "en") -> dict:
    audio_file = work_dir / "audio.wav"
    _extract_audio(video_path, str(audio_file))
    return _transcribe_local(str(audio_file), language)


def _extract_audio(video_path: str, output_path: str) -> None:
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", video_path, "-vn", "-acodec", "pcm_s16le",
         "-ar", "16000", "-ac", "1", output_path],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Audio extraction failed: {result.stderr.strip()}")


def _transcribe_local(audio_path: str, language: str = "en") -> dict:
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        raise RuntimeError("faster-whisper not installed. Run: uv pip install faster-whisper")

    try:
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        device = "cpu"
    compute_type = "float16" if device == "cuda" else "int8"
    model = WhisperModel("base", device=device, compute_type=compute_type)

    segments_gen, info = model.transcribe(audio_path, language=language, vad_filter=True)
    segments = []
    full_text_parts = []
    for seg in segments_gen:
        segments.append({
            "text": seg.text.strip(),
            "start": round(seg.start, 3),
            "duration": round(seg.end - seg.start, 3),
        })
        full_text_parts.append(seg.text.strip())

    return {
        "source": f"whisper-local ({device})",
        "segments": segments,
        "full_text": " ".join(full_text_parts),
        "language": info.language if info else language,
    }


def parse_captions(subtitle_path: str) -> dict:
    path = Path(subtitle_path)
    if not path.exists():
        raise RuntimeError(f"Subtitle file not found: {subtitle_path}")

    segments = []
    content = path.read_text(encoding="utf-8", errors="replace")
    content = content.replace("\r\n", "\n")

    for block in content.strip().split("\n\n"):
        lines = [l.strip() for l in block.split("\n") if l.strip()]
        if len(lines) < 3:
            continue
        time_line = next((l for l in lines[:3] if "-->" in l), None)
        if not time_line:
            continue
        text = " ".join(lines[lines.index(time_line) + 1:])
        parts = [p.strip() for p in time_line.split("-->")]
        if len(parts) != 2:
            continue
        start = _parse_srt_time(parts[0])
        end = _parse_srt_time(parts[1])
        if start is None or end is None:
            continue
        segments.append({"text": text, "start": start, "duration": end - start})

    return {
        "source": "captions",
        "segments": segments,
        "full_text": " ".join(s["text"] for s in segments),
    }


def _parse_srt_time(raw: str) -> float | None:
    import re
    m = re.search(r"(\d{1,2}):(\d{2}):(\d{2})(?:[.,](\d{1,3}))?", raw.strip())
    if not m:
        return None
    hours = int(m.group(1))
    minutes = int(m.group(2))
    seconds = int(m.group(3))
    millis = int(m.group(4)) if m.group(4) else 0
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def filter_segments(segments: list[dict], start: float | None, end: float | None) -> list[dict]:
    if start is None and end is None:
        return segments
    filtered = []
    for seg in segments:
        seg_end = seg["start"] + seg["duration"]
        if start is not None and seg_end < start:
            continue
        if end is not None and seg["start"] > end:
            continue
        filtered.append(seg)
    return filtered


def align_segments_to_reference(
    target: dict | None,
    reference: dict | None,
    *,
    min_offset_seconds: float = 2.0,
    min_matches: int = 5,
    max_spread_seconds: float = 1.5,
    min_ratio: float = 0.65,
) -> tuple[dict | None, dict | None]:
    """Shift target segment starts when text-matched timing is stably offset.

    Returns ``(aligned_target, alignment)``. ``alignment`` is None when there is
    not enough evidence to alter timestamps. The original segment start is kept
    as ``original_start`` for auditability.
    """
    if not target or not reference:
        return target, None
    target_segments = list(target.get("segments") or [])
    reference_segments = list(reference.get("segments") or [])
    if not target_segments or not reference_segments:
        return target, None

    pairs = _matched_offsets(target_segments, reference_segments, min_ratio)
    if len(pairs) < min_matches:
        return target, {
            "status": "insufficient_matches",
            "match_count": len(pairs),
            "offset_seconds": 0.0,
        }

    offsets = sorted(p["offset_seconds"] for p in pairs)
    median = statistics.median(offsets)
    deviations = sorted(abs(offset - median) for offset in offsets)
    median_deviation = statistics.median(deviations)
    if abs(median) < min_offset_seconds or median_deviation > max_spread_seconds:
        return target, {
            "status": "already_aligned" if abs(median) < min_offset_seconds else "unstable_offset",
            "match_count": len(pairs),
            "offset_seconds": round(median, 3),
            "median_deviation_seconds": round(median_deviation, 3),
        }

    aligned_segments = []
    for segment in target_segments:
        row = dict(segment)
        row["original_start"] = row.get("start", 0.0)
        row["start"] = round(max(0.0, float(row.get("start", 0.0)) + median), 3)
        aligned_segments.append(row)

    aligned = dict(target)
    aligned["segments"] = aligned_segments
    aligned["alignment"] = {
        "status": "shifted",
        "reference_source": reference.get("source", "reference"),
        "offset_seconds": round(median, 3),
        "match_count": len(pairs),
        "median_deviation_seconds": round(median_deviation, 3),
        "examples": pairs[:5],
    }
    return aligned, aligned["alignment"]


def _matched_offsets(target_segments: list[dict], reference_segments: list[dict], min_ratio: float) -> list[dict]:
    pairs: list[dict] = []
    normalized_targets = [(_normalize_text(seg.get("text", "")), seg) for seg in target_segments]
    for ref in reference_segments[:80]:
        ref_text = _normalize_text(ref.get("text", ""))
        if len(ref_text) < 8:
            continue
        best_ratio = 0.0
        best_target = None
        for target_text, target in normalized_targets:
            if len(target_text) < 8:
                continue
            ratio = difflib.SequenceMatcher(None, ref_text, target_text).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_target = target
        if best_target and best_ratio >= min_ratio:
            offset = float(ref.get("start", 0.0)) - float(best_target.get("start", 0.0))
            pairs.append({
                "offset_seconds": round(offset, 3),
                "ratio": round(best_ratio, 3),
                "reference_start": round(float(ref.get("start", 0.0)), 3),
                "target_start": round(float(best_target.get("start", 0.0)), 3),
                "reference_text": str(ref.get("text", ""))[:120],
                "target_text": str(best_target.get("text", ""))[:120],
            })
    return pairs


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", value.lower()).strip()
