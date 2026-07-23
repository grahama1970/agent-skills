"""Attribute transcript segments to anonymous diarization speaker turns.

This module is deliberately model-free. It consumes normalized dictionaries
matching the Watch diarization contract and does not import pyannote types.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any

try:
    from skills.watch.scripts.diarization_contract import (
        DIARIZATION_SCHEMA,
        SPEAKER_ATTRIBUTION_SCHEMA,
    )
except ModuleNotFoundError:
    from diarization_contract import DIARIZATION_SCHEMA, SPEAKER_ATTRIBUTION_SCHEMA


def attribute_speakers(
    transcript: dict[str, Any] | None,
    diarization: dict[str, Any] | None,
    *,
    minimum_dominant_ratio: float = 0.50,
    mixed_speaker_ratio: float = 0.20,
) -> dict[str, Any] | None:
    """Derive anonymous speaker attribution for transcript segments.

    The canonical transcript text is copied unchanged. No character, actor, or
    real-world identity promotion is performed here.
    """
    if not transcript or not diarization:
        return None
    if diarization.get("schema") != DIARIZATION_SCHEMA or diarization.get("status") != "complete":
        return None

    segments = transcript.get("segments") or []
    exclusive_turns = _normalized_turns(diarization.get("exclusive_turns") or [])
    regular_turns = _normalized_turns(diarization.get("turns") or [])

    attributed: list[dict[str, Any]] = []
    counts = {"assigned": 0, "multiple": 0, "unassigned": 0}

    for segment in segments:
        attributed_segment = dict(segment)
        attribution = _attribute_segment(
            segment,
            exclusive_turns,
            regular_turns,
            minimum_dominant_ratio=minimum_dominant_ratio,
            mixed_speaker_ratio=mixed_speaker_ratio,
        )
        attributed_segment.update(attribution)
        counts[attributed_segment["speaker_status"]] += 1
        attributed.append(attributed_segment)

    return {
        "schema": SPEAKER_ATTRIBUTION_SCHEMA,
        "status": "complete",
        "transcript_source": transcript.get("source", "unknown"),
        "diarization_schema": DIARIZATION_SCHEMA,
        "diarization_artifact_path": diarization.get("artifact_path", "diarization.json"),
        "segment_count": len(attributed),
        "assigned_count": counts["assigned"],
        "mixed_count": counts["multiple"],
        "unassigned_count": counts["unassigned"],
        "segments": attributed,
        "identity_boundary": {
            "anonymous_speakers_are_identity": False,
            "promotion_allowed": False,
            "notes": [
                "Anonymous speaker labels are acoustic clusters, not character identity.",
                "Speaker-to-character mapping requires separate evidence and human acceptance.",
            ],
        },
    }


def _attribute_segment(
    segment: dict[str, Any],
    exclusive_turns: list[dict[str, Any]],
    regular_turns: list[dict[str, Any]],
    *,
    minimum_dominant_ratio: float,
    mixed_speaker_ratio: float,
) -> dict[str, Any]:
    start = float(segment.get("start", 0.0) or 0.0)
    duration = max(0.0, float(segment.get("duration", 0.0) or 0.0))
    end = start + duration

    if duration == 0.0:
        overlaps = _point_membership_by_speaker(start, exclusive_turns)
        overlapping_speech = _point_overlapping_speech(start, regular_turns)
    else:
        overlaps = _overlap_by_speaker(start, end, exclusive_turns)
        overlapping_speech = _segment_overlapping_speech(start, end, regular_turns)

    candidates = _candidate_rows(overlaps, duration)
    dominant = candidates[0] if candidates else None
    mixed = sum(1 for candidate in candidates if candidate["overlap_ratio"] >= mixed_speaker_ratio) >= 2

    if not dominant:
        speaker = None
        source = "none"
        status = "unassigned"
        overlap_seconds = 0.0
        overlap_ratio = 0.0
    elif mixed:
        speaker = dominant["speaker"]
        source = "pyannote_exclusive"
        status = "multiple"
        overlap_seconds = dominant["overlap_seconds"]
        overlap_ratio = dominant["overlap_ratio"]
    elif dominant["overlap_ratio"] >= minimum_dominant_ratio:
        speaker = dominant["speaker"]
        source = "pyannote_exclusive"
        status = "assigned"
        overlap_seconds = dominant["overlap_seconds"]
        overlap_ratio = dominant["overlap_ratio"]
    else:
        speaker = None
        source = "none"
        status = "unassigned"
        overlap_seconds = dominant["overlap_seconds"]
        overlap_ratio = dominant["overlap_ratio"]

    return {
        "speaker": speaker,
        "speaker_source": source,
        "speaker_status": status,
        "speaker_overlap_seconds": overlap_seconds,
        "speaker_overlap_ratio": overlap_ratio,
        "speaker_candidates": candidates,
        "overlapping_speech": overlapping_speech,
    }


def _normalized_turns(turns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for turn in turns:
        start = float(turn.get("start", 0.0) or 0.0)
        end = float(turn.get("end", 0.0) or 0.0)
        speaker = str(turn.get("speaker", ""))
        if not speaker or end < start:
            continue
        normalized.append({"start": start, "end": end, "speaker": speaker})
    return normalized


def _overlap_by_speaker(start: float, end: float, turns: list[dict[str, Any]]) -> dict[str, float]:
    overlaps: dict[str, float] = defaultdict(float)
    for turn in turns:
        overlap = min(end, turn["end"]) - max(start, turn["start"])
        if overlap > 0:
            overlaps[turn["speaker"]] += overlap
    return dict(overlaps)


def _point_membership_by_speaker(point: float, turns: list[dict[str, Any]]) -> dict[str, float]:
    overlaps: dict[str, float] = {}
    for turn in turns:
        if turn["start"] <= point <= turn["end"]:
            overlaps[turn["speaker"]] = max(overlaps.get(turn["speaker"], 0.0), 0.0)
    return overlaps


def _candidate_rows(overlaps: dict[str, float], duration: float) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for speaker, overlap_seconds in overlaps.items():
        ratio = 1.0 if duration == 0.0 else overlap_seconds / duration
        candidates.append(
            {
                "speaker": speaker,
                "overlap_seconds": _round_metric(overlap_seconds),
                "overlap_ratio": _round_metric(ratio),
            }
        )
    candidates.sort(key=lambda row: (-row["overlap_seconds"], row["speaker"]))
    return candidates


def _segment_overlapping_speech(start: float, end: float, turns: list[dict[str, Any]]) -> bool:
    active = [
        turn
        for turn in turns
        if min(end, turn["end"]) - max(start, turn["start"]) > 0
    ]
    for index, left in enumerate(active):
        for right in active[index + 1 :]:
            if left["speaker"] == right["speaker"]:
                continue
            if min(left["end"], right["end"], end) - max(left["start"], right["start"], start) > 0:
                return True
    return False


def _point_overlapping_speech(point: float, turns: list[dict[str, Any]]) -> bool:
    active_speakers = {
        turn["speaker"]
        for turn in turns
        if turn["start"] <= point <= turn["end"]
    }
    return len(active_speakers) >= 2


def _round_metric(value: float) -> float:
    return round(float(value), 3)
