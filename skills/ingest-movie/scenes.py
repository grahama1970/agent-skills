"""
Movie Ingest Skill - Scenes Module
SRT parsing, emotion detection, tag extraction, and scene matching.
"""
import re
from collections import Counter
from pathlib import Path
from typing import Optional

from rich.console import Console

from config import (
    CUE_KEYWORDS,
    EMOTION_TAG_MAP,
    TAG_TO_EMOTION,
    RMS_THRESHOLD,
    RMS_WINDOW_SEC,
    VALID_TAGS,
    VALID_EMOTIONS,
)
from utils import (
    format_seconds,
    format_hms,
    format_srt_timestamp,
    read_file_with_encoding_fallback,
)

console = Console()


# -----------------------------------------------------------------------------
# SRT Parsing
# -----------------------------------------------------------------------------
def parse_timestamp(raw: str) -> Optional[float]:
    """Parse SRT timestamp string to seconds."""
    raw = raw.strip()
    m = re.search(r"(\d{1,2}):(\d{2}):(\d{2})(?:[.,](\d{1,3}))?", raw)
    if not m:
        return None
    hours = int(m.group(1))
    minutes = int(m.group(2))
    seconds = int(m.group(3))
    millis_group = m.group(4)
    millis = int(millis_group) if millis_group is not None else 0
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def extract_subtitle_tags(text: str) -> list[str]:
    """
    Extract emotion/action tags from subtitle text.
    Looks for [bracketed], (parenthesized), {braced} cues,
    and -dashed- stage directions.
    """
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


def parse_subtitle_file(path: Path) -> list[dict]:
    """
    Parse an SRT file into a list of entries with start, end, text, and tags.
    Uses encoding fallback chain for robustness.
    """
    if path.suffix.lower() != ".srt":
        raise ValueError("Only .srt subtitles are supported")

    try:
        content, encoding = read_file_with_encoding_fallback(path)
        console.print(f"[dim]Read subtitle with encoding: {encoding}[/dim]")
    except ValueError as e:
        console.print(f"[red]Failed to read subtitle file: {e}[/red]")
        return []

    # Normalize line endings
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    entries: list[dict] = []
    malformed = inverted = total = 0

    def flush_block(block: list[str]):
        nonlocal malformed, inverted, total
        lines = [line.strip() for line in block if line.strip()]
        if len(lines) < 2:
            return
        time_line_idx = next((i for i, l in enumerate(lines[:3]) if "-->" in l), -1)
        if time_line_idx == -1:
            malformed += 1
            return
        time_line = lines[time_line_idx]
        text_lines = lines[time_line_idx + 1:]
        if not text_lines:
            return
        parts = [part.strip() for part in time_line.split("-->")]
        if len(parts) != 2:
            malformed += 1
            return
        start_str, end_str = parts
        start = parse_timestamp(start_str)
        end = parse_timestamp(end_str)
        total += 1
        if start is None or end is None:
            malformed += 1
            return
        if end < start:
            inverted += 1
            return
        text = " ".join(text_lines)
        tags = extract_subtitle_tags(text)
        entries.append({"start": start, "end": end, "text": text, "tags": tags})

    buffer: list[str] = []
    for line in content.splitlines():
        if line.strip() == "":
            if buffer:
                flush_block(buffer)
                buffer = []
        else:
            buffer.append(line)
    if buffer:
        flush_block(buffer)

    console.print(
        f"[dim]Subtitle parse summary: total={total}, valid={len(entries)}, "
        f"malformed={malformed}, inverted={inverted}[/dim]"
    )
    return entries


# -----------------------------------------------------------------------------
# Tag and Emotion Utilities
# -----------------------------------------------------------------------------
def tags_for_emotion(emotion: Optional[str]) -> set[str]:
    """Get the set of tags that indicate an emotion."""
    if not emotion:
        return set()
    return {tag.lower() for tag in EMOTION_TAG_MAP.get(emotion.lower(), set())}


def infer_emotion_from_tags(tags: list[str], fallback: Optional[str] = None) -> Optional[str]:
    """
    Infer the primary emotion from a list of tags.
    Uses priority ordering if multiple emotions detected.
    """
    if fallback:
        return fallback.lower()
    mapped = [TAG_TO_EMOTION.get(tag.lower()) for tag in tags]
    mapped = [m for m in mapped if m]
    if not mapped:
        return None
    counts = Counter(mapped)
    priority = ["rage", "anger", "sorrow", "regret", "camaraderie"]
    sorted_emotions = sorted(
        counts.keys(),
        key=lambda e: (-counts[e], priority.index(e) if e in priority else len(priority)),
    )
    return sorted_emotions[0]


# -----------------------------------------------------------------------------
# Segment Tag Attachment
# -----------------------------------------------------------------------------
def attach_tags_to_segments(segments: list[dict], entries: list[dict]) -> None:
    """
    Attach subtitle tags to Whisper segments based on time overlap.
    Modifies segments in place.
    """
    if not entries:
        return
    entries_sorted = sorted(entries, key=lambda e: e["start"])
    entry_idx = 0
    for seg in segments:
        seg_start = seg.get("start", 0.0)
        seg_end = seg_start + seg.get("duration", 0.0)
        seg_tags = set()

        while entry_idx < len(entries_sorted) and entries_sorted[entry_idx]["end"] < seg_start:
            entry_idx += 1

        probe = entry_idx
        while probe < len(entries_sorted) and entries_sorted[probe]["start"] <= seg_end:
            seg_tags.update(entries_sorted[probe]["tags"])
            probe += 1

        if seg_tags:
            seg.setdefault("tags", [])
            seg["tags"] = sorted(set(seg["tags"]) | seg_tags)


def attach_audio_intensity_tags(audio_file: Path, segments: list[dict]) -> set[str]:
    """
    Analyze audio RMS levels and tag segments with intensity markers.
    Requires soundfile and numpy.
    """
    try:
        import soundfile as sf
        import numpy as np
    except ImportError:
        console.print("[yellow]soundfile or numpy not installed; skipping audio intensity tagging.[/yellow]")
        return set()

    if not audio_file.exists():
        return set()

    intensity_tags = set()
    try:
        data, sr = sf.read(audio_file)
    except Exception as e:
        console.print(f"[yellow]Failed to read audio for intensity tagging: {e}[/yellow]")
        return set()

    if getattr(data, "ndim", 1) > 1:
        data = data.mean(axis=1)

    window_size = int(sr * RMS_WINDOW_SEC)

    for seg in segments:
        start = seg.get("start", 0.0)
        end = start + seg.get("duration", 0.0)
        start_idx = max(0, int(start * sr))
        end_idx = min(len(data), int(end * sr))
        if end_idx <= start_idx:
            continue
        segment_audio = data[start_idx:end_idx]
        if len(segment_audio) <= window_size:
            rms = float(np.sqrt(np.mean(segment_audio ** 2))) if len(segment_audio) else 0.0
            rms_max = rms
        else:
            windows = [segment_audio[i:i+window_size] for i in range(0, len(segment_audio), window_size)]
            rms_max = max(float(np.sqrt(np.mean(w ** 2))) for w in windows if len(w))

        segment_tags = set()
        if rms_max > RMS_THRESHOLD * 2:
            segment_tags.add("rage_candidate")
        elif rms_max > RMS_THRESHOLD:
            segment_tags.add("anger_candidate")
        elif rms_max < 0.05:
            segment_tags.add("whisper_candidate")

        if segment_tags:
            intensity_tags.update(segment_tags)
            seg.setdefault("tags", [])
            seg["tags"] = sorted(set(seg["tags"]) | segment_tags)

    return intensity_tags


# -----------------------------------------------------------------------------
# Match Collection
# -----------------------------------------------------------------------------
def collect_matches(
    entries: list[dict],
    query: Optional[str],
    tag: Optional[str],
    emotion: Optional[str],
    max_matches: int,
    merge_adjacent: bool = True,
) -> list[dict]:
    """
    Collect subtitle entries matching query, tag, or emotion criteria.
    Optionally merges adjacent entries for continuous scenes.
    """
    query_lower = query.lower() if query else None
    tag_filters = set()
    if tag:
        tag_filters.add(tag.lower())
    tag_filters |= tags_for_emotion(emotion)

    raw_matches: list[dict] = []
    prefetch = max_matches * (10 if merge_adjacent else 1)
    for entry in entries:
        text = entry.get("text", "")
        entry_tags = {t.lower() for t in entry.get("tags", [])}
        if query_lower and query_lower not in text.lower():
            continue
        if tag_filters and not (tag_filters & entry_tags):
            continue
        raw_matches.append(entry)
        if query_lower is None and tag_filters:
            if len(raw_matches) >= prefetch:
                break
        elif len(raw_matches) >= prefetch:
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
            merged.append(entry.copy())
        if len(merged) >= max_matches:
            break
    return merged


# -----------------------------------------------------------------------------
# SRT Window Extraction
# -----------------------------------------------------------------------------
def extract_srt_window(
    srt_path: Path,
    start_sec: float,
    end_sec: float,
    output_path: Path,
) -> bool:
    """
    Extract a time window from an SRT file to a new SRT.
    Uses encoding fallback and validates output.
    Returns True if subtitles were found, False if empty.
    """
    try:
        content, encoding = read_file_with_encoding_fallback(srt_path)
    except ValueError as e:
        raise ValueError(f"Could not decode SRT file: {e}")

    # Normalize line endings
    content = content.replace('\r\n', '\n').replace('\r', '\n')

    # More flexible regex for subtitle blocks
    pattern = r'(\d+)\s*\n\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[,\.]\d{3})\s*\n((?:(?!\n\s*\n|\n\d+\s*\n).)*)'
    blocks = re.findall(pattern, content, re.DOTALL)

    output_blocks = []
    new_index = 1

    for num, start_ts, end_ts, text in blocks:
        start = parse_timestamp(start_ts)
        end = parse_timestamp(end_ts)
        if start is None or end is None:
            continue

        # Check for overlap with time window
        if end < start_sec or start > end_sec:
            continue

        # Adjust timestamps relative to clip start
        new_start = max(0, start - start_sec)
        new_end = end - start_sec

        output_blocks.append(
            f"{new_index}\n"
            f"{format_srt_timestamp(new_start)} --> {format_srt_timestamp(new_end)}\n"
            f"{text.strip()}\n"
        )
        new_index += 1

    if not output_blocks:
        console.print(f"[yellow]Warning: No subtitles found in time window {start_sec:.1f}-{end_sec:.1f}[/yellow]")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(output_blocks), encoding='utf-8')
    console.print(f"[green]Extracted {len(output_blocks)} subtitle entries to {output_path}[/green]")
    return True


def write_subtitle_snippet(
    entries: list[dict],
    output_path: Path,
    start_offset: float = 0.0,
) -> None:
    """
    Write subtitle entries to an SRT file with optional time offset.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []
    for idx, entry in enumerate(entries, 1):
        start = entry["start"] - start_offset
        end = entry["end"] - start_offset
        if start < 0:
            start = 0
        if end < 0:
            continue
        lines.append(f"{idx}")
        lines.append(f"{format_srt_timestamp(start)} --> {format_srt_timestamp(end)}")
        lines.append(entry.get("text", ""))
        lines.append("")

    output_path.write_text("\n".join(lines), encoding='utf-8')
