#!/usr/bin/env python3
"""
Movie Ingest Skill
Search NZBGeek and transcribe local video files using Whisper for PersonaPlex alignment.
"""
import os
import sys
import json
import time
import re
import subprocess
import requests
import typer
from pathlib import Path
from typing import Optional
from collections import defaultdict
from rich.console import Console
from rich.table import Table
from datetime import datetime, timezone

app = typer.Typer(help="Movie Ingest & Transcription Skill")
scenes_app = typer.Typer(help="Transcript scene utilities")
app.add_typer(scenes_app, name="scenes")
console = Console()

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
NZB_API_KEY = os.environ.get("NZBD_GEEK_API_KEY")
NZB_BASE_URL = os.environ.get("NZBD_GEEK_BASE_URL", "https://api.nzbgeek.info/")
WHISPER_BIN = os.environ.get("WHISPER_BIN", os.path.expanduser("~/.local/bin/whisper"))
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "/usr/bin/ffmpeg")

CUE_KEYWORDS = {
    "laugh": "laugh",
    "chuckle": "laugh",
    "giggle": "laugh",
    "snicker": "laugh",
    "sob": "cry",
    "cry": "cry",
    "scream": "shout",
    "shout": "shout",
    "yell": "shout",
    "shouting": "shout",
    "yelling": "shout",
    "angry": "anger",
    "anger": "anger",
    "rage": "rage",
    "sigh": "sigh",
    "breath": "breath",
    "breathing": "breath",
    "whisper": "whisper",
}

def _validate_env():
    if not NZB_API_KEY:
        console.print("[yellow]Warning: NZBD_GEEK_API_KEY not set. Search will fail.[/yellow]")


@scenes_app.command("find")
def find_scene_windows(
    subtitle_file: Path = typer.Argument(..., exists=True, help="Subtitle .srt to scan"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Case-insensitive text substring to find"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by subtitle cue tag (e.g. laugh, shout)"),
    window: float = typer.Option(15.0, help="Seconds of padding before/after the match for suggested clips"),
    max_matches: int = typer.Option(5, help="Maximum matches to display"),
    offset: float = typer.Option(0.0, help="Seconds to add when referencing the full movie (useful if .srt was trimmed)"),
    video_file: Optional[Path] = typer.Option(None, "--video", help="Optional video file path for ffmpeg command hints"),
):
    """Search subtitle text/tags to locate clip timestamps."""
    if not query and not tag:
        raise typer.BadParameter("Provide at least --query or --tag to locate a scene")

    entries = parse_subtitle_file(subtitle_file)
    if not entries:
        console.print("[red]No subtitle entries found; ensure the .srt has text lines.[/red]")
        raise typer.Exit(code=1)

    query_lower = query.lower() if query else None
    tag_lower = tag.lower() if tag else None
    matches = []
    for entry in entries:
        text = entry.get("text", "")
        text_lower = text.lower()
        if query_lower and query_lower not in text_lower:
            continue
        if tag_lower and tag_lower not in [t.lower() for t in entry.get("tags", [])]:
            continue
        matches.append(entry)
        if len(matches) >= max_matches:
            break

    if not matches:
        console.print("[yellow]No matches found for the given query/tag.[/yellow]")
        raise typer.Exit()

    adjusted_video = str(video_file) if video_file else None
    console.print(f"[green]Found {len(matches)} match(es). Suggested clip windows with ±{window:.1f}s padding:" )
    for idx, entry in enumerate(matches, 1):
        start = entry.get("start", 0.0)
        end = entry.get("end", start)
        clip_start = max(0.0, start - window) + offset
        clip_end = end + window + offset
        console.print(f"\n[bold]Match {idx}[/bold]")
        console.print(f"Subtitle window: {format_seconds(start+offset)} → {format_seconds(end+offset)}")
        console.print(f"Suggested clip: {format_seconds(clip_start)} → {format_seconds(clip_end)}")
        console.print(f"Text: {entry.get('text', '').strip()}")
        entry_tags = entry.get("tags") or []
        if entry_tags:
            console.print(f"Tags: {', '.join(entry_tags)}")
        if adjusted_video:
            console.print(
                "ffmpeg -ss {start} -to {end} -i '{video}' -c copy clip_{idx}.mkv".format(
                    start=format_seconds(clip_start), end=format_seconds(clip_end), video=adjusted_video, idx=idx
                )
            )

# -----------------------------------------------------------------------------
# NZB Search Logic
# -----------------------------------------------------------------------------
@app.command("search")
def search_nzb(
    term: str = typer.Argument(..., help="Movie title to search"),
    cat: str = typer.Option("2000", help="Category (2000=Movies, 5000=TV)"),
    limit: int = typer.Option(10, help="Max results to display")
):
    """Search NZBGeek for movie releases."""
    _validate_env()
    
    params = {
        "t": "search",
        "q": term,
        "cat": cat,
        "apikey": NZB_API_KEY,
        "o": "json"
    }
    
    url = f"{NZB_BASE_URL.rstrip('/')}/api"
    try:
        console.print(f"[cyan]Searching NZBGeek for '{term}'...[/cyan]")
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        
        data = resp.json()
        items = []
        
        # Handle XML-to-JSON quirks (single item vs list)
        if "channel" in data and "item" in data["channel"]:
            items = data["channel"]["item"]
            if isinstance(items, dict):
                items = [items]
        elif "item" in data:
            items = data["item"]
            
        if not items:
            console.print("[yellow]No results found.[/yellow]")
            return

        table = Table(title=f"Results for '{term}'")
        table.add_column("Title", style="green")
        table.add_column("Size", style="cyan")
        table.add_column("PubDate", style="dim")
        table.add_column("Link", style="blue")

        for item in items[:limit]:
            size = item.get("size", "0")
            try:
                size_mb = int(size) / (1024 * 1024)
                size_str = f"{size_mb:.1f} MB"
            except:
                size_str = size
                
            table.add_row(
                item.get("title", "Unknown")[:60],
                size_str,
                item.get("pubDate", "")[:16],
                item.get("link", "")[:40] + "..."
            )
        console.print(table)

    except Exception as e:
        console.print(f"[red]Search failed: {e}[/red]")

# -----------------------------------------------------------------------------
# Transcription Logic
# -----------------------------------------------------------------------------
@app.command("transcribe")
def transcribe_video(
    input_file: Path = typer.Argument(..., exists=True, help="Video file path"),
    output_dir: Path = typer.Option(Path("./transcripts"), help="Directory for Whisper + persona JSON"),
    model: str = typer.Option("medium", help="Whisper model (base, small, medium, large)"),
    emotion: str = typer.Option(None, help="Tag with emotion (e.g. rage, sorrow)"),
    movie_title: Optional[str] = typer.Option(None, help="Movie or benchmark title"),
    scene: Optional[str] = typer.Option(None, help="Scene description (e.g. 'Pacino warns Fredo')"),
    characters: Optional[str] = typer.Option(None, help="Comma-separated character list"),
    source_id: Optional[str] = typer.Option(None, help="Stable clip ID (defaults to filename stem)"),
    subtitle_file: Optional[Path] = typer.Option(None, help="Path to subtitle .srt with emotion cues"),
    output_json: Optional[Path] = typer.Option(None, help="Override for ingestion-ready JSON path"),
):
    """
    Transcribe a video file using local Whisper.
    Extracts audio -> Transcribes -> Calculates Rhythm.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_file.stem
    audio_file = output_dir / f"{stem}.wav"

    subtitle_path = resolve_subtitle_file(input_file, subtitle_file)
    subtitle_entries = parse_subtitle_file(subtitle_path)
    if not subtitle_entries:
        raise typer.BadParameter(
            f"No usable cues found in subtitle file {subtitle_path}. Provide a high-quality subtitle track with emotion annotations."
        )
    
    # 1. Extract Audio
    console.print(f"[cyan]Extracting audio to {audio_file}...[/cyan]")
    cmd_ffmpeg = [
        FFMPEG_BIN, "-y",
        "-i", str(input_file),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(audio_file)
    ]
    subprocess.run(cmd_ffmpeg, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # 2. Run Whisper
    console.print(f"[cyan]Running Whisper ({model})...[/cyan]")
    # whisper command output formats: txt, vtt, srt, tsv, json
    cmd_whisper = [
        WHISPER_BIN,
        str(audio_file),
        "--model", model,
        "--output_dir", str(output_dir),
        "--output_format", "json"
    ]
    
    try:
        subprocess.run(cmd_whisper, check=True)
    except FileNotFoundError:
        console.print(f"[red]Whisper binary not found at {WHISPER_BIN}[/red]")
        return

    # 3. Process JSON for PersonaPlex
    json_file = output_dir / f"{stem}.json"
    if not json_file.exists():
        console.print(f"[red]Whisper JSON not found at {json_file}[/red]")
        return

    with open(json_file) as f:
        transcript = json.load(f)

    segments = transcript.get("segments", []) or []
    formatted_segments = []
    full_text_parts = []
    last_end = 0.0
    pauses = 0
    for seg in segments:
        start = float(seg.get("start", 0))
        end = float(seg.get("end", start))
        duration = max(0.0, end - start)
        text = (seg.get("text") or "").strip()
        if start - last_end > 0.5:
            pauses += 1
        last_end = end
        formatted_segments.append({
            "text": text,
            "start": round(start, 3),
            "duration": round(duration, 3),
        })
        if text:
            full_text_parts.append(text)

    total_duration = float(transcript.get("duration", last_end))
    total_words = len((" ".join(full_text_parts)).split())
    wpm = (total_words / total_duration) * 60 if total_duration > 0 else 0.0

    clip_id = source_id or stem
    character_list = [c.strip() for c in (characters.split(",") if characters else []) if c.strip()]

    attach_tags_to_segments(formatted_segments, subtitle_entries)
    subtitle_tag_set = {tag for entry in subtitle_entries for tag in entry["tags"]}
    audio_tag_set = attach_audio_intensity_tags(audio_file, formatted_segments)
    aggregate_tags = sorted(subtitle_tag_set | audio_tag_set)
    meta = {
        "video_id": clip_id,
        "source": "movie",
        "movie_title": movie_title or stem,
        "scene": scene,
        "characters": character_list,
        "emotion_tag": emotion,
        "language": transcript.get("language"),
        "duration_sec": round(total_duration, 3),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_file": str(input_file),
        "subtitle_file": str(subtitle_path),
        "subtitle_tags": sorted(subtitle_tag_set),
        "audio_tags": sorted(audio_tag_set),
        "rhythm_metrics": {
            "wpm": round(wpm, 1),
            "pause_count": pauses,
            "duration_sec": round(total_duration, 2)
        }
    }

    persona_payload = {
        "meta": meta,
        "full_text": " ".join(full_text_parts),
        "transcript": formatted_segments,
    }

    enriched_file = output_json or (output_dir / f"{stem}_persona.json")
    with open(enriched_file, "w") as f:
        json.dump(persona_payload, f, indent=2)

    console.print(f"[green]Success! Persona JSON saved to {enriched_file}[/green]")
    console.print(f"Rhythm: {wpm:.1f} WPM, {pauses} significant pauses")
    if aggregate_tags:
        console.print(f"Detected cue tags: {', '.join(aggregate_tags)}")
    console.print("Next: `python horus_lore_ingest.py emotion --input {dir} --emotion <tag>` to ingest.")


def resolve_subtitle_file(input_file: Path, explicit: Optional[Path]) -> Path:
    if explicit:
        if not explicit.exists():
            raise typer.BadParameter(f"Subtitle file {explicit} does not exist")
        return explicit

    candidates = []
    for candidate in input_file.parent.glob(f"{input_file.stem}*.srt"):
        candidates.append(candidate)

    if not candidates:
        raise typer.BadParameter(
            "Subtitle .srt file not found. Provide --subtitle pointing to a release with emotion cues before ingesting."
        )

    return sorted(candidates, key=lambda p: len(p.name))[0]


def parse_subtitle_file(path: Path) -> list[dict]:
    if path.suffix.lower() != ".srt":
        raise typer.BadParameter("Only .srt subtitles are supported right now")

    content = path.read_text(encoding="utf-8", errors="ignore")
    blocks = re.split(r"\r?\n\s*\r?\n", content)
    entries: list[dict] = []

    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        if len(lines) < 2:
            continue
        time_line_idx = 0
        if "-->" not in lines[0] and len(lines) >= 2:
            time_line_idx = 1
        time_line = lines[time_line_idx]
        if "-->" not in time_line:
            continue
        text_lines = lines[time_line_idx + 1 :]
        if not text_lines:
            continue
        start_str, end_str = [part.strip() for part in time_line.split("-->")]
        start = parse_timestamp(start_str)
        end = parse_timestamp(end_str)
        if start is None or end is None:
            continue
        text = " ".join(text_lines)
        tags = extract_subtitle_tags(text)
        entries.append({
            "start": start,
            "end": end,
            "text": text,
            "tags": tags,
        })

    return entries


def parse_timestamp(raw: str) -> Optional[float]:
    raw = raw.strip().replace(".", ",")
    match = re.match(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", raw)
    if not match:
        return None
    hours, minutes, seconds, millis = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds + millis / 1000.0


def extract_subtitle_tags(text: str) -> list[str]:
    lowered = text.lower()
    raw_cues = re.findall(r"\[(.*?)\]", lowered) + re.findall(r"\((.*?)\)", lowered)
    tags = set()
    for cue in raw_cues:
        for keyword, tag in CUE_KEYWORDS.items():
            if keyword in cue:
                tags.add(tag)
    return sorted(tags)


def attach_tags_to_segments(segments: list[dict], entries: list[dict]) -> None:
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
    try:
        import soundfile as sf
        import numpy as np
    except ImportError:
        console.print("[yellow]soundfile or numpy not installed; skipping audio intensity tagging.[/yellow]")
        return set()

    if not audio_file.exists():
        return set()

    data, sr = sf.read(audio_file)
    if data.ndim > 1:
        data = data.mean(axis=1)

    rms_threshold = 0.2
    intensity_tags = set()
    window_size = int(sr * 0.5)

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
        if rms_max > rms_threshold * 2:
            segment_tags.add("rage_candidate")
        elif rms_max > rms_threshold:
            segment_tags.add("anger_candidate")
        elif rms_max < 0.05:
            segment_tags.add("whisper_candidate")

        if segment_tags:
            intensity_tags.update(segment_tags)
            seg.setdefault("tags", [])
            seg["tags"] = sorted(set(seg["tags"]) | segment_tags)

    return intensity_tags


def format_seconds(value: float) -> str:
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    seconds = value % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"
    return f"{minutes:02d}:{seconds:05.2f}"

if __name__ == "__main__":
    app()
