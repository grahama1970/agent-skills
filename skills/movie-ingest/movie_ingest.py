#!/usr/bin/env python3
"""
Movie Ingest Skill
Search NZBGeek and transcribe local video files using Whisper for PersonaPlex alignment.
"""
import os
import sys
import json
import re
import shutil
import subprocess
import requests
import typer
from pathlib import Path
from typing import Optional
from collections import Counter
from functools import lru_cache
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
NZB_API_KEY = os.environ.get("NZBD_GEEK_API_KEY") or os.environ.get("NZB_GEEK_API_KEY")
NZB_BASE_URL = (
    os.environ.get("NZBD_GEEK_BASE_URL")
    or os.environ.get("NZB_GEEK_BASE_URL")
    or "https://api.nzbgeek.info/"
)
WHISPER_BIN = os.environ.get("WHISPER_BIN", os.path.expanduser("~/.local/bin/whisper"))
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "/usr/bin/ffmpeg")

@lru_cache(maxsize=1)
def get_ffmpeg_bin() -> str:
    """Return ffmpeg path preferring env override but falling back to PATH."""
    configured = FFMPEG_BIN
    if configured and Path(configured).exists():
        return configured
    discovered = shutil.which("ffmpeg")
    return discovered or configured

# Audio intensity tagging thresholds (override via env)
RMS_THRESHOLD = float(os.environ.get("AUDIO_RMS_THRESHOLD", "0.2"))
RMS_WINDOW_SEC = float(os.environ.get("AUDIO_RMS_WINDOW_SEC", "0.5"))

CUE_KEYWORDS = {
    "laugh": "laugh",
    "laughs": "laugh",
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
    "snarl": "rage",
    "growl": "rage",
}

EMOTION_TAG_MAP = {
    "rage": {"rage", "rage_candidate", "anger_candidate", "shout"},
    "anger": {"anger", "anger_candidate", "shout"},
    "humor": {"laugh"},
    "regret": {"cry", "sob", "sigh"},
    "respect": {"whisper", "whisper_candidate", "breath"},
}

TAG_TO_EMOTION = {
    "rage": "rage",
    "rage_candidate": "rage",
    "anger": "anger",
    "anger_candidate": "anger",
    "shout": "anger",
    "laugh": "humor",
    "cry": "regret",
    "sob": "regret",
    "sigh": "regret",
    "whisper": "respect",
    "whisper_candidate": "respect",
    "breath": "respect",
}

SUBTITLE_HINT_KEYWORDS = (" subs", "subbed", "subtitle", "subtitles", ".srt", "cc", "sdh", "caption")
def _validate_env():
    if os.environ.get("NZBD_GEEK_API_KEY") and not os.environ.get("NZB_GEEK_API_KEY"):
        console.print("[yellow]Note: prefer NZB_GEEK_API_KEY (without the extra 'D').[/yellow]")
    if not NZB_API_KEY:
        console.print(
            "[yellow]Warning: NZB_GEEK_API_KEY not set. NZB search will fail.[/yellow]"
        )


def release_has_subtitle_hint(item: dict) -> bool:
    haystack = " ".join(
        [
            str(item.get("title", "")),
            str(item.get("description", "")),
            str(item.get("attr", "")),
        ]
    ).lower()
    return any(keyword in haystack for keyword in SUBTITLE_HINT_KEYWORDS)


@scenes_app.command("find")
def find_scene_windows(
    subtitle_file: Path = typer.Option(..., "--subtitle", "-s", exists=True, help="Subtitle .srt to scan"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Case-insensitive text substring to find"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by subtitle cue tag (e.g. laugh, shout)"),
    emotion: Optional[str] = typer.Option(None, "--emotion", "-e", help="Filter by canonical emotion (rage, anger, humor, respect, regret)"),
    window: float = typer.Option(15.0, help="Seconds of padding before/after the match for suggested clips"),
    max_matches: int = typer.Option(5, help="Maximum matches to display"),
    offset: float = typer.Option(0.0, help="Seconds to add when referencing the full movie (useful if .srt was trimmed)"),
    video_file: Optional[Path] = typer.Option(None, "--video", help="Optional video file path for ffmpeg command hints"),
):
    """Search subtitle text/tags to locate clip timestamps."""
    if not query and not tag and not emotion:
        raise typer.BadParameter("Provide at least --query, --tag, or --emotion to locate a scene")

    entries = parse_subtitle_file(subtitle_file)
    if not entries:
        console.print("[red]No subtitle entries found; ensure the .srt has text lines.[/red]")
        raise typer.Exit(code=1)

    matches = collect_matches(entries, query, tag, emotion, max_matches, merge_adjacent=True)
    if not matches:
        console.print("[yellow]No matches found for the given query/tag.[/yellow]")
        raise typer.Exit()

    adjusted_video = str(video_file) if video_file else None
    console.print(f"[green]Found {len(matches)} match(es). Suggested clip windows with ±{window:.1f}s padding:[/green]")
    for idx, entry in enumerate(matches, 1):
        start = entry.get("start", 0.0)
        end = entry.get("end", start)
        clip_start = max(0.0, start - window) + offset
        clip_end = end + window + offset
        inferred = infer_emotion_from_tags(entry.get("tags", []), emotion)
        console.print(f"\n[bold]Match {idx}[/bold]")
        console.print(f"Subtitle window: {format_seconds(start+offset)} → {format_seconds(end+offset)}")
        console.print(f"Suggested clip: {format_seconds(clip_start)} → {format_seconds(clip_end)}")
        console.print(f"Text: {entry.get('text', '').strip()}")
        entry_tags = entry.get("tags") or []
        if entry_tags:
            console.print(f"Tags: {', '.join(entry_tags)}")
        if inferred:
            console.print(f"Inferred emotion: {inferred}")
        if adjusted_video:
            console.print(
                "{bin} -ss {start} -to {end} -i '{video}' -c copy clip_{idx}.mkv".format(
                    bin=get_ffmpeg_bin(),
                    start=format_hms(clip_start),
                    end=format_hms(clip_end),
                    video=adjusted_video,
                    idx=idx,
                )
            )


@scenes_app.command("extract")
def extract_scene_manifest(
    subtitle_file: Path = typer.Option(..., "--subtitle", "-s", exists=True, help="Subtitle .srt to scan"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Case-insensitive text substring to find"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by subtitle cue tag (e.g. laugh, shout)"),
    emotion: Optional[str] = typer.Option(None, "--emotion", "-e", help="Filter by canonical emotion (rage, anger, humor, respect, regret)"),
    window: float = typer.Option(12.0, help="Seconds of padding before/after matches when clipping"),
    max_matches: int = typer.Option(10, help="Maximum matches to process"),
    offset: float = typer.Option(0.0, help="Seconds to align subtitles with full movie timing"),
    video_file: Optional[Path] = typer.Option(None, "--video", help="Optional video file to auto-clip via ffmpeg"),
    clip_dir: Optional[Path] = typer.Option(None, "--clip-dir", help="Directory to write extracted clips (.mkv/.srt)"),
    output_json: Optional[Path] = typer.Option(None, "--output-json", help="Manifest path (defaults to <subtitle>.scenes.json)"),
    subtitle_only: bool = typer.Option(False, "--subtitle-only", help="Skip ffmpeg work and just emit manifest data"),
):
    """Generate a JSON manifest (and optional clips) for PersonaPlex ingestion."""
    if not query and not tag and not emotion:
        raise typer.BadParameter("Provide at least --query, --tag, or --emotion to extract scenes")
    if subtitle_only and clip_dir:
        raise typer.BadParameter("--subtitle-only cannot be combined with --clip-dir")
    if clip_dir and not video_file:
        raise typer.BadParameter("--clip-dir requires --video to read from")

    entries = parse_subtitle_file(subtitle_file)
    matches = collect_matches(entries, query, tag, emotion, max_matches, merge_adjacent=True)
    if not matches:
        console.print("[yellow]No matches found; nothing to extract.[/yellow]")
        raise typer.Exit()

    manifest_path = output_json or subtitle_file.with_suffix(".scenes.json")
    manifest: list[dict] = []
    clip_dir_path = Path(clip_dir) if clip_dir else None
    if clip_dir_path:
        clip_dir_path.mkdir(parents=True, exist_ok=True)

    console.print(f"[cyan]Processing {len(matches)} match(es) from {subtitle_file}[/cyan]")
    for idx, entry in enumerate(matches, 1):
        start = entry.get("start", 0.0)
        end = entry.get("end", start)
        clip_start = max(0.0, start - window) + offset
        clip_end = end + window + offset
        inferred = infer_emotion_from_tags(entry.get("tags", []), emotion)
        record = {
            "index": idx,
            "text": entry.get("text", "").strip(),
            "tags": entry.get("tags", []),
            "emotion": inferred,
            "subtitle_window": {
                "start_sec": round(start, 3),
                "end_sec": round(end, 3),
            },
            "movie_window": {
                "start_sec": round(clip_start, 3),
                "end_sec": round(clip_end, 3),
                "duration_sec": round(max(0.0, clip_end - clip_start), 3),
            },
        }
        if video_file:
            record["movie_window"]["ffmpeg_hint"] = (
                "{bin} -ss {start} -to {end} -i '{video}' -c copy clip_{idx:02d}.mkv".format(
                    bin=get_ffmpeg_bin(),
                    start=format_hms(clip_start),
                    end=format_hms(clip_end),
                    video=str(video_file),
                    idx=idx,
                )
            )

        clip_metadata = {}
        if clip_dir_path and not subtitle_only:
            clip_name = f"clip_{idx:02d}"
            clip_video_path = clip_dir_path / f"{clip_name}.mkv"
            cmd = [
                get_ffmpeg_bin(),
                "-y",
                "-ss",
                f"{clip_start:.3f}",
                "-to",
                f"{clip_end:.3f}",
                "-i",
                str(video_file),
                "-c",
                "copy",
                str(clip_video_path),
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                clip_metadata["video"] = str(clip_video_path)
                console.print(f"[green]Saved {clip_video_path}[/green]")
            except subprocess.CalledProcessError as exc:
                console.print(f"[red]ffmpeg failed for {clip_name}: {exc}[/red]")

            snippet_path = clip_dir_path / f"{clip_name}.srt"
            snippet = write_subtitle_snippet(entries, clip_start, clip_end, snippet_path, offset)
            if snippet:
                clip_metadata["subtitle"] = str(snippet)
            if inferred:
                clip_metadata["emotion"] = inferred
            if clip_metadata:
                record["clip_artifacts"] = clip_metadata

        manifest.append(record)

    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump({"scenes": manifest, "source_subtitle": str(subtitle_file)}, fh, indent=2)

    console.print(f"[green]Scene manifest saved to {manifest_path}[/green]")
    if clip_dir_path and not subtitle_only:
        console.print(f"[green]Clips available under {clip_dir_path}[/green]")
    console.print("Next: feed manifest rows into horus_lore_ingest emotion ingest.")

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
        table.add_column("Subs?", style="yellow", justify="center")
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
            subs_flag = "✅" if release_has_subtitle_hint(item) else ""
            table.add_row(
                item.get("title", "Unknown")[:60],
                subs_flag,
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
    emotion: Optional[str] = typer.Option(None, help="Tag with emotion (e.g. rage, sorrow)"),
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
        get_ffmpeg_bin(), "-y",
        "-i", str(input_file),
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        str(audio_file)
    ]
    try:
        subprocess.run(cmd_ffmpeg, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except FileNotFoundError:
        console.print(f"[red]ffmpeg not found at {get_ffmpeg_bin()}[/red]")
        return
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]ffmpeg failed to extract audio: {exc}[/red]")
        return
    
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
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]Whisper failed: {exc}[/red]")
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
    ingest_hint = emotion or "<emotion>"
    console.print(f"Next: `python horus_lore_ingest.py emotion --input {output_dir} --emotion {ingest_hint}` to ingest.")


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
        text_lines = lines[time_line_idx + 1 :]
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
        f"[dim]Subtitle parse summary: total={total}, valid={len(entries)}, malformed={malformed}, inverted={inverted}[/dim]"
    )
    return entries


def parse_timestamp(raw: str) -> Optional[float]:
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


def tags_for_emotion(emotion: Optional[str]) -> set[str]:
    if not emotion:
        return set()
    return {tag.lower() for tag in EMOTION_TAG_MAP.get(emotion.lower(), set())}


def infer_emotion_from_tags(tags: list[str], fallback: Optional[str] = None) -> Optional[str]:
    if fallback:
        return fallback.lower()
    mapped = [TAG_TO_EMOTION.get(tag.lower()) for tag in tags]
    mapped = [m for m in mapped if m]
    if not mapped:
        return None
    counts = Counter(mapped)
    priority = ["rage", "anger", "humor", "regret", "respect"]
    sorted_emotions = sorted(
        counts.keys(),
        key=lambda e: (-counts[e], priority.index(e) if e in priority else len(priority)),
    )
    return sorted_emotions[0]


def collect_matches(
    entries: list[dict],
    query: Optional[str],
    tag: Optional[str],
    emotion: Optional[str],
    max_matches: int,
    merge_adjacent: bool = True,
) -> list[dict]:
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
            # prefer cue-driven matches by not over-collecting
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


def write_subtitle_snippet(
    entries: list[dict],
    clip_start_global: float,
    clip_end_global: float,
    output_path: Path,
    offset: float,
) -> Optional[Path]:
    output_lines = []
    index = 1
    for entry in entries:
        entry_start_global = entry["start"] + offset
        entry_end_global = entry["end"] + offset
        if entry_end_global < clip_start_global or entry_start_global > clip_end_global:
            continue
        local_start = max(0.0, entry_start_global - clip_start_global)
        clip_duration_local = max(0.0, clip_end_global - clip_start_global)
        local_end = min(max(local_start, entry_end_global - clip_start_global), clip_duration_local)
        output_lines.append(
            f"{index}\n"
            f"{format_srt_timestamp(local_start)} --> {format_srt_timestamp(local_end)}\n"
            f"{entry.get('text', '').strip()}\n"
        )
        index += 1

    if not output_lines:
        return None

    output_path.write_text("\n".join(output_lines), encoding="utf-8")
    return output_path


def format_seconds(value: float) -> str:
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    seconds = value % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"
    return f"{minutes:02d}:{seconds:05.2f}"

def format_hms(value: float) -> str:
    value = max(0.0, value)
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    seconds = value % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"


def format_srt_timestamp(value: float) -> str:
    value = max(0.0, value)
    total_ms = int(round(value * 1000))
    hours = total_ms // 3_600_000
    rem = total_ms % 3_600_000
    minutes = rem // 60_000
    rem %= 60_000
    seconds = rem // 1000
    millis = rem % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"

if __name__ == "__main__":
    app()
