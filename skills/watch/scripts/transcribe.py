"""Transcript utilities: SRT caption parsing, local faster-whisper, and segment filtering.

Whisper transcription for URLs is delegated to ingest-youtube (3-tier fallback).
Local faster-whisper handles arbitrary local files (free, GPU-accelerated, no API key).
"""
from __future__ import annotations

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
