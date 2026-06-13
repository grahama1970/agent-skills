"""Voice activity detection and clip sizing."""

from __future__ import annotations

import librosa

from lib.constants import DEFAULT_MAX_CLIP_SEC, DEFAULT_MIN_CLIP_SEC, MERGE_GAP_SEC, VAD_TOP_DB


def merge_intervals(raw: list[tuple[float, float]], merge_gap_sec: float) -> list[tuple[float, float]]:
    if not raw:
        return []
    merged: list[tuple[float, float]] = [raw[0]]
    for start_sec, end_sec in raw[1:]:
        prev_start, prev_end = merged[-1]
        if start_sec - prev_end <= merge_gap_sec:
            merged[-1] = (prev_start, end_sec)
        else:
            merged.append((start_sec, end_sec))
    return merged


def split_long_span(start_sec: float, end_sec: float, max_clip_sec: float) -> list[tuple[float, float]]:
    duration = end_sec - start_sec
    if duration <= max_clip_sec:
        return [(start_sec, end_sec)]
    out: list[tuple[float, float]] = []
    cursor = start_sec
    while cursor < end_sec:
        chunk_end = min(cursor + max_clip_sec, end_sec)
        if chunk_end - cursor >= DEFAULT_MIN_CLIP_SEC:
            out.append((cursor, chunk_end))
        cursor = chunk_end
    return out


def detect_speech_spans(
    y,
    sr: int,
    *,
    min_clip_sec: float = DEFAULT_MIN_CLIP_SEC,
    max_clip_sec: float = DEFAULT_MAX_CLIP_SEC,
    merge_gap_sec: float = MERGE_GAP_SEC,
    top_db: float = VAD_TOP_DB,
) -> list[tuple[float, float]]:
    import librosa

    intervals = librosa.effects.split(y, top_db=top_db, frame_length=2048, hop_length=512)
    raw = [(start / sr, end / sr) for start, end in intervals]
    merged = merge_intervals(raw, merge_gap_sec)
    spans: list[tuple[float, float]] = []
    for start_sec, end_sec in merged:
        if end_sec - start_sec < min_clip_sec:
            continue
        spans.extend(split_long_span(start_sec, end_sec, max_clip_sec))
    return spans
