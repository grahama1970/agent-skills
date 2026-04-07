#!/usr/bin/env python3
"""
Movie Ingest CLI - Main Entry Point
Thin wrapper that imports from modular components.

This file is kept for backwards compatibility with run.sh.
The actual implementation is in the following modules:
- config.py: Constants, emotion mappings, paths
- utils.py: Subprocess helpers, encoding detection
- inventory.py: Clip registry with file locking
- scenes.py: SRT parsing, emotion detection
- search.py: NZBGeek search
- extract.py: FFmpeg video/audio extraction
- transcribe.py: Whisper, persona JSON generation
- agent.py: Agent-friendly commands
- batch.py: Batch processing commands
- subs.py: Subtitle management
- radarr.py: Radarr integration
"""
import sys
from pathlib import Path

# Add this directory to path for imports
SKILL_DIR = Path(__file__).parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

import json
from typing import Optional

import typer
from rich.console import Console

# Import from modules (now works since we added SKILL_DIR to sys.path)
from config import VALID_EMOTIONS, VALID_TAGS, validate_env
from search import search_nzb, display_search_results
from scenes import parse_subtitle_file, collect_matches, infer_emotion_from_tags
from extract import extract_audio
from transcribe import (
    run_whisper,
    create_persona_json,
    resolve_subtitle_file,
)
from inventory import load_inventory, get_inventory_stats
from subs import download_subtitles, batch_download_subtitles
from batch import batch_discover, batch_plan, batch_run, batch_status
from radarr import acquire_movies, show_preset_info, check_radarr_connection
from agent import (
    recommend_movies,
    recommend_books,
    quick_extract,
    discover_scenes,
    show_inventory,
    request_extraction,
)
from utils import (
    format_seconds,
    format_hms,
    get_ffmpeg_bin,
    find_media_file,
    find_subtitle_file,
)

# Create Typer apps
app = typer.Typer(help="Movie Ingest & Transcription Skill")
scenes_app = typer.Typer(help="Transcript scene utilities")
batch_app = typer.Typer(help="Batch processing for automated pipelines")
subs_app = typer.Typer(help="Subtitle download and management")
agent_app = typer.Typer(help="Agent-friendly commands for project integration")
acquire_app = typer.Typer(help="Movie acquisition via Radarr")

app.add_typer(scenes_app, name="scenes")
app.add_typer(batch_app, name="batch")
app.add_typer(subs_app, name="subs")
app.add_typer(agent_app, name="agent")
app.add_typer(acquire_app, name="acquire")

console = Console()


# -----------------------------------------------------------------------------
# Search Command
# -----------------------------------------------------------------------------
@app.command("search")
def search_cmd(
    term: str = typer.Argument(..., help="Movie title to search"),
    cat: str = typer.Option("2000", help="Category (2000=Movies, 5000=TV)"),
    limit: int = typer.Option(10, help="Max results to display"),
):
    """Search NZBGeek for movie releases."""
    validate_env(console)
    results = search_nzb(term, cat, limit)
    display_search_results(results, term)


# -----------------------------------------------------------------------------
# Transcribe Command
# -----------------------------------------------------------------------------
@app.command("transcribe")
def transcribe_cmd(
    input_file: Path = typer.Argument(..., exists=True, help="Video file path"),
    output_dir: Path = typer.Option(Path("./transcripts"), help="Directory for output"),
    model: str = typer.Option("medium", help="Whisper model"),
    emotion: Optional[str] = typer.Option(None, help="Tag with emotion"),
    movie_title: Optional[str] = typer.Option(None, help="Movie title"),
    scene: Optional[str] = typer.Option(None, help="Scene description"),
    characters: Optional[str] = typer.Option(None, help="Comma-separated character list"),
    source_id: Optional[str] = typer.Option(None, help="Stable clip ID"),
    subtitle_file: Optional[Path] = typer.Option(None, help="Path to subtitle .srt"),
    output_json: Optional[Path] = typer.Option(None, help="Override output path"),
):
    """Transcribe video using Whisper and create PersonaPlex JSON."""
    if emotion and emotion.lower() not in VALID_EMOTIONS:
        raise typer.BadParameter(f"Unknown emotion. Allowed: {sorted(VALID_EMOTIONS)}")

    output_dir.mkdir(parents=True, exist_ok=True)
    stem = input_file.stem
    audio_file = output_dir / f"{stem}.wav"

    # Resolve subtitle
    subtitle_path = resolve_subtitle_file(input_file, subtitle_file)

    # Extract audio
    console.print(f"[cyan]Extracting audio...[/cyan]")
    extract_audio(input_file, audio_file)

    # Run Whisper
    transcript_json = run_whisper(audio_file, output_dir, model)
    if not transcript_json:
        raise typer.Exit(code=1)

    # Create persona JSON
    persona_file = output_json or (output_dir / f"{stem}_persona.json")
    create_persona_json(
        transcript_json=transcript_json,
        audio_file=audio_file,
        input_file=input_file,
        subtitle_path=subtitle_path,
        output_path=persona_file,
        emotion=emotion,
        movie_title=movie_title,
        scene=scene,
        characters=characters,
        source_id=source_id,
    )


# -----------------------------------------------------------------------------
# Scenes Commands
# -----------------------------------------------------------------------------
@scenes_app.command("find")
def scenes_find_cmd(
    subtitle_file: Path = typer.Option(..., "--subtitle", "-s", exists=True),
    query: Optional[str] = typer.Option(None, "--query", "-q"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t"),
    emotion: Optional[str] = typer.Option(None, "--emotion", "-e"),
    window: float = typer.Option(15.0, help="Padding seconds"),
    max_matches: int = typer.Option(5),
    offset: float = typer.Option(0.0),
    video_file: Optional[Path] = typer.Option(None, "--video"),
):
    """Search subtitle text/tags to locate clip timestamps."""
    if not query and not tag and not emotion:
        raise typer.BadParameter("Provide --query, --tag, or --emotion")

    if tag and tag.lower() not in VALID_TAGS:
        raise typer.BadParameter(f"Unknown tag. Allowed: {sorted(VALID_TAGS)}")
    if emotion and emotion.lower() not in VALID_EMOTIONS:
        raise typer.BadParameter(f"Unknown emotion. Allowed: {sorted(VALID_EMOTIONS)}")

    entries = parse_subtitle_file(subtitle_file)
    if not entries:
        console.print("[red]No subtitle entries found[/red]")
        raise typer.Exit(code=1)

    matches = collect_matches(entries, query, tag, emotion, max_matches, merge_adjacent=True)
    if not matches:
        console.print("[yellow]No matches found[/yellow]")
        return

    console.print(f"[green]Found {len(matches)} match(es)[/green]")
    for idx, entry in enumerate(matches, 1):
        start = entry.get("start", 0.0)
        end = entry.get("end", start)
        clip_start = max(0.0, start - window) + offset
        clip_end = end + window + offset

        console.print(f"\n[bold]Match {idx}[/bold]")
        console.print(f"Window: {format_seconds(start+offset)} → {format_seconds(end+offset)}")
        console.print(f"Clip: {format_seconds(clip_start)} → {format_seconds(clip_end)}")
        console.print(f"Text: {entry.get('text', '').strip()[:100]}")

        if video_file:
            console.print(f"ffmpeg -ss {format_hms(clip_start)} -to {format_hms(clip_end)} -i '{video_file}' -c copy clip_{idx}.mkv")


@scenes_app.command("analyze")
def scenes_analyze_cmd(
    subtitle_file: Path = typer.Option(..., "--subtitle", "-s", exists=True),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    output_json: Optional[Path] = typer.Option(None, "--output-json", "-o"),
):
    """Analyze subtitle file for emotion cues."""
    entries = parse_subtitle_file(subtitle_file)
    if not entries:
        console.print("[red]No entries found[/red]")
        raise typer.Exit(code=1)

    # Count tags
    tag_counts = {}
    for entry in entries:
        for tag in entry.get("tags", []):
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    console.print(f"[bold]Emotion Cue Analysis[/bold]")
    console.print(f"Total entries: {len(entries)}")
    console.print(f"\n[bold]Tags found:[/bold]")
    for tag, count in sorted(tag_counts.items(), key=lambda x: -x[1]):
        emotion = infer_emotion_from_tags([tag])
        console.print(f"  {tag}: {count} occurrences → {emotion or 'unknown'}")

    if output_json:
        result = {"file": str(subtitle_file), "entries": len(entries), "tags": tag_counts}
        output_json.write_text(json.dumps(result, indent=2))
        console.print(f"\n[green]Saved to {output_json}[/green]")


@scenes_app.command("quality")
def scenes_quality_cmd(
    subtitle_file: Path = typer.Option(..., "--subtitle", "-s", exists=True),
    strict: bool = typer.Option(False, "--strict"),
):
    """Validate subtitle quality for PersonaPlex ingestion."""
    entries = parse_subtitle_file(subtitle_file)

    issues = []

    # Check encoding (already handled by parse_subtitle_file with fallback)
    if not entries:
        issues.append(("error", "No valid subtitle entries found"))

    # Check entry count
    if len(entries) < 10:
        issues.append(("warning", f"Low entry count: {len(entries)} entries"))

    # Check for emotion cues
    total_tags = sum(len(e.get("tags", [])) for e in entries)
    if total_tags == 0:
        issues.append(("warning", "No emotion cues found in subtitles"))

    # Check timing consistency
    prev_end = 0.0
    overlaps = 0
    for entry in entries:
        if entry.get("start", 0) < prev_end:
            overlaps += 1
        prev_end = entry.get("end", 0)

    if overlaps > 0:
        issues.append(("warning", f"{overlaps} overlapping subtitle entries"))

    # Report
    console.print(f"[bold]Subtitle Quality Report[/bold]")
    console.print(f"File: {subtitle_file.name}")
    console.print(f"Entries: {len(entries)}")
    console.print(f"Emotion cues: {total_tags}")

    if issues:
        console.print("\n[bold]Issues:[/bold]")
        for level, msg in issues:
            color = "red" if level == "error" else "yellow"
            console.print(f"  [{color}]{level.upper()}[/{color}]: {msg}")

        if strict and any(level == "error" for level, _ in issues):
            raise typer.Exit(code=1)
    else:
        console.print("\n[green]✓ No issues found[/green]")


@scenes_app.command("extract")
def scenes_extract_cmd(
    subtitle_file: Path = typer.Option(..., "--subtitle", "-s", exists=True),
    tag: str = typer.Option(..., "--tag", "-t", help="Tag to extract (e.g. rage, shout)"),
    video_file: Optional[Path] = typer.Option(None, "--video", "-v", exists=True),
    clip_dir: Optional[Path] = typer.Option(None, "--clip-dir"),
    output_json: Optional[Path] = typer.Option(None, "--output-json", "-o"),
    subtitle_only: bool = typer.Option(False, "--subtitle-only"),
):
    """Extract scenes matching a tag from subtitles."""
    from scenes import extract_srt_window

    entries = parse_subtitle_file(subtitle_file)
    if not entries:
        console.print("[red]No subtitle entries found[/red]")
        raise typer.Exit(code=1)

    matches = collect_matches(entries, None, tag, None, max_matches=50, merge_adjacent=True)
    if not matches:
        console.print(f"[yellow]No matches found for tag: {tag}[/yellow]")
        return

    console.print(f"[green]Found {len(matches)} scenes with tag '{tag}'[/green]")

    manifest = {"tag": tag, "subtitle_file": str(subtitle_file), "scenes": []}

    for idx, entry in enumerate(matches, 1):
        start = entry.get("start", 0.0)
        end = entry.get("end", start)

        scene = {
            "index": idx,
            "start": start,
            "end": end,
            "text": entry.get("text", "")[:200],
            "tags": entry.get("tags", []),
        }

        # Extract clips if requested
        if clip_dir and video_file and not subtitle_only:
            clip_dir.mkdir(parents=True, exist_ok=True)
            clip_path = clip_dir / f"clip_{idx:02d}.mkv"
            srt_path = clip_dir / f"clip_{idx:02d}.srt"

            # Extract video clip
            from extract import extract_video_clip
            extract_video_clip(video_file, clip_path, start - 2, end + 2)
            scene["clip_path"] = str(clip_path)

            # Extract subtitle window
            extract_srt_window(subtitle_file, start - 2, end + 2, srt_path)
            scene["srt_path"] = str(srt_path)

        manifest["scenes"].append(scene)
        console.print(f"  {idx}. [{format_hms(start)} - {format_hms(end)}] {entry.get('text', '')[:50]}...")

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(manifest, indent=2))
        console.print(f"\n[green]Manifest saved to {output_json}[/green]")


# -----------------------------------------------------------------------------
# Batch Commands
# -----------------------------------------------------------------------------
@batch_app.command("discover")
def batch_discover_cmd(
    library: Optional[Path] = typer.Option(None, "--library", "-l"),
    subtitles: bool = typer.Option(True, "--subtitles/--no-subtitles"),
):
    """Scan media directories for available movies."""
    batch_discover(library, subtitles)


@batch_app.command("plan")
def batch_plan_cmd(
    emotion: Optional[str] = typer.Option(None, "--emotion", "-e"),
    include_unavailable: bool = typer.Option(False, "--include-unavailable"),
    output_json: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """Create a processing manifest from emotion mappings."""
    emotions = [emotion] if emotion else None
    batch_plan(emotions, include_unavailable=include_unavailable, output_json=output_json)


@batch_app.command("run")
def batch_run_cmd(
    manifest: Path = typer.Option(..., "--manifest", "-m", exists=True),
    dry_run: bool = typer.Option(True, "--dry-run/--execute"),
):
    """Execute batch processing from manifest."""
    batch_run(manifest, dry_run)


@batch_app.command("status")
def batch_status_cmd():
    """Show status of processed emotion exemplars."""
    batch_status()


# -----------------------------------------------------------------------------
# Subtitle Commands
# -----------------------------------------------------------------------------
@subs_app.command("download")
def subs_download_cmd(
    video: Path = typer.Argument(..., exists=True, help="Video file"),
    language: str = typer.Option("en", "--lang", "-l"),
):
    """Download subtitles for a video file."""
    download_subtitles(video, language)


@subs_app.command("batch")
def subs_batch_cmd(
    directory: Path = typer.Argument(..., exists=True),
    language: str = typer.Option("en", "--lang", "-l"),
    recursive: bool = typer.Option(False, "--recursive", "-r"),
):
    """Download subtitles for all videos in directory."""
    batch_download_subtitles(directory, language, recursive)


# -----------------------------------------------------------------------------
# Agent Commands
# -----------------------------------------------------------------------------
@agent_app.command("recommend")
def agent_recommend_cmd(
    emotion: str = typer.Argument(..., help="Target emotion"),
    actor_model: Optional[str] = typer.Option(None, "--actor", "-a"),
    library_path: Optional[Path] = typer.Option(None, "--library", "-l"),
    exclude_movies: Optional[str] = typer.Option(None, "--exclude", "-x"),
    output_json: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """Research movies with emotional scenes for TTS training."""
    recommend_movies(emotion, actor_model, library_path, exclude_movies, output_json)


@agent_app.command("quick")
def agent_quick_cmd(
    movie: Path = typer.Option(..., "--movie", "-m", exists=True),
    emotion: str = typer.Option(..., "--emotion", "-e"),
    scene: str = typer.Option(..., "--scene", "-s"),
    timestamp: str = typer.Option(..., "--timestamp", "-t"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
    characters: Optional[str] = typer.Option(None, "--characters", "-c"),
    clip_id: Optional[str] = typer.Option(None, "--id"),
    notify_project: Optional[str] = typer.Option(None, "--notify"),
):
    """Single-step clip extraction: subs → clip → persona JSON."""
    quick_extract(movie, emotion, scene, timestamp, output_dir, characters, clip_id, notify_project)


@agent_app.command("discover")
def agent_discover_cmd(
    library_path: Path = typer.Argument(..., exists=True),
    emotion: Optional[str] = typer.Option(None, "--emotion", "-e"),
    query: Optional[str] = typer.Option(None, "--query", "-q"),
    output_json: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """Discover emotion-matching scenes in library."""
    discover_scenes(library_path, emotion, query, output_json=output_json)


@agent_app.command("inventory")
def agent_inventory_cmd(
    emotion: Optional[str] = typer.Option(None, "--emotion", "-e"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Show inventory of processed clips."""
    show_inventory(emotion, as_json)


@agent_app.command("request")
def agent_request_cmd(
    to_project: str = typer.Option("movie-ingest", "--to"),
    emotion: str = typer.Option(..., "--emotion", "-e"),
    description: str = typer.Option(..., "--desc", "-d"),
    count: int = typer.Option(5, "--count", "-n"),
):
    """Send clip extraction request via agent-inbox."""
    request_extraction(to_project, emotion, description, count)


@agent_app.command("recommend-book")
def agent_recommend_book_cmd(
    movie: Optional[str] = typer.Option(None, "--movie", "-m", help="Movie to find source material for"),
    emotion: Optional[str] = typer.Option(None, "--emotion", "-e", help="Emotion for thematic recommendations"),
    library_path: Optional[Path] = typer.Option(None, "--library", "-l", help="Local book library path"),
    output_json: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """Recommend books to read before processing a movie.

    Finds source material, related novels, and thematic companions
    to provide better context for persona training.

    Examples:
        ./run.sh agent recommend-book --movie "Dune"
        ./run.sh agent recommend-book --emotion rage --library ~/library/books
    """
    recommend_books(movie, emotion, library_path, output_json)


# -----------------------------------------------------------------------------
# Acquire Commands
# -----------------------------------------------------------------------------
@acquire_app.command("radarr")
def acquire_radarr_cmd(
    emotion: Optional[str] = typer.Option(None, "--emotion", "-e"),
    preset: str = typer.Option("horus_standard", "--preset"),
    dry_run: bool = typer.Option(True, "--dry-run/--execute"),
):
    """Add missing movies to Radarr from emotion mappings."""
    emotions = [emotion] if emotion else None
    acquire_movies(emotions, preset, dry_run)


@acquire_app.command("preset")
def acquire_preset_cmd():
    """Show the Horus TTS preset configuration."""
    show_preset_info()


@acquire_app.command("check")
def acquire_check_cmd():
    """Check Radarr connection."""
    check_radarr_connection()


# -----------------------------------------------------------------------------
# Main Entry
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app()
