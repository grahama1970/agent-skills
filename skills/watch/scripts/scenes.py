"""SRT parsing and emotion/scene analysis, adapted from ingest-movie/scenes.py.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Optional


CUE_KEYWORDS = {
    "rage": "rage", "raving": "rage", "furious": "rage",
    "shout": "shout", "yelling": "shout", "yells": "shout", "screaming": "shout", "scream": "shout",
    "laugh": "laugh", "laughing": "laugh", "laughter": "laugh",
    "whisper": "whisper_candidate", "whispers": "whisper_candidate",
    "anger": "anger_candidate", "angry": "anger_candidate",
    "cry": "sorrow", "crying": "sorrow", "cries": "sorrow", "sob": "sorrow",
    "sigh": "sigh", "sighs": "sigh",
    "applause": "applause", "cheering": "applause",
}

EMOTION_TAG_MAP = {
    "rage": {"rage", "shout", "rage_candidate"},
    "anger": {"anger_candidate", "shout"},
    "sorrow": {"sorrow", "cry", "whisper_candidate"},
    "regret": {"sigh", "whisper_candidate"},
    "camaraderie": {"laugh", "applause"},
}

TAG_TO_EMOTION = {}
for emotion, tags in EMOTION_TAG_MAP.items():
    for tag in tags:
        TAG_TO_EMOTION[tag] = emotion

VALID_TAGS = set(CUE_KEYWORDS.values())
VALID_EMOTIONS = set(EMOTION_TAG_MAP.keys())


def parse_srt(path: Path) -> list[dict]:
    if path.suffix.lower() != ".srt":
        raise ValueError("Only .srt subtitles are supported")

    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        raise RuntimeError(f"Failed to read {path}: {exc}") from exc

    content = content.replace("\r\n", "\n")
    entries: list[dict] = []

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
        start = _parse_timestamp(parts[0])
        end = _parse_timestamp(parts[1])
        if start is None or end is None or end < start:
            continue
        tags = _extract_tags(text)
        entries.append({"start": start, "end": end, "text": text, "tags": tags})

    return entries


def _parse_timestamp(raw: str) -> Optional[float]:
    m = re.search(r"(\d{1,2}):(\d{2}):(\d{2})(?:[.,](\d{1,3}))?", raw.strip())
    if not m:
        return None
    hours = int(m.group(1))
    minutes = int(m.group(2))
    seconds = int(m.group(3))
    millis = int(m.group(4)) if m.group(4) else 0
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def _extract_tags(text: str) -> list[str]:
    lowered = text.lower()
    raw_cues = (
        re.findall(r"\[(.*?)\]", lowered)
        + re.findall(r"\((.*?)\)", lowered)
        + re.findall(r"\{(.*?)\}", lowered)
    )
    dash_cues = re.findall(r"-\s*([a-z\s]+?)\s*-", lowered)
    caps_cues = [lowered] if text.isupper() and 1 <= len(text.split()) <= 3 else []
    tags = set()
    for cue in raw_cues + dash_cues + caps_cues:
        for keyword, tag in CUE_KEYWORDS.items():
            if keyword in cue:
                tags.add(tag)
    return sorted(tags)


def find_scenes(
    entries: list[dict],
    query: Optional[str] = None,
    tag: Optional[str] = None,
    emotion: Optional[str] = None,
    max_matches: int = 20,
    merge_adjacent: bool = True,
) -> list[dict]:
    query_lower = query.lower() if query else None
    tag_filters = set()
    if tag:
        tag_filters.add(tag.lower())
    if emotion:
        tag_filters |= EMOTION_TAG_MAP.get(emotion.lower(), set())

    raw_matches: list[dict] = []
    prefetch = max_matches * (10 if merge_adjacent else 1)
    for entry in entries:
        entry_text = entry.get("text", "")
        entry_tags = {t.lower() for t in entry.get("tags", [])}
        if query_lower and query_lower not in entry_text.lower():
            continue
        if tag_filters and not (tag_filters & entry_tags):
            continue
        raw_matches.append(entry)
        if len(raw_matches) >= prefetch:
            break

    if not merge_adjacent:
        return raw_matches[:max_matches]

    merged: list[dict] = []
    for entry in raw_matches:
        if merged and entry["start"] - merged[-1]["end"] <= 2.0:
            merged[-1]["end"] = max(merged[-1]["end"], entry["end"])
            merged[-1]["text"] = (merged[-1].get("text", "") + " " + entry.get("text", "")).strip()
            merged[-1]["tags"] = sorted(set(merged[-1].get("tags", [])) | set(entry.get("tags", [])))
        else:
            merged.append(dict(entry))
        if len(merged) >= max_matches:
            break
    return merged


def analyze_emotions(entries: list[dict]) -> dict:
    tag_counts: dict[str, int] = {}
    for entry in entries:
        for tag in entry.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    emotion_counts: dict[str, int] = {}
    for tag, count in tag_counts.items():
        emotion = TAG_TO_EMOTION.get(tag)
        if emotion:
            emotion_counts[emotion] = emotion_counts.get(emotion, 0) + count

    return {
        "total_entries": len(entries),
        "tag_counts": dict(sorted(tag_counts.items(), key=lambda x: -x[1])),
        "emotion_counts": dict(sorted(emotion_counts.items(), key=lambda x: -x[1])),
    }
