"""
Movie Ingest Skill - Agent Module
Agent-friendly commands for collaborative movie selection and extraction.
Designed for easy use by project agents (like Horus).
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console

from config import (
    VALID_EMOTIONS,
    HORUS_ARCHETYPE_MAP,
    DOGPILE_DIR,
)
from inventory import (
    load_inventory,
    save_inventory,
    add_clip_to_inventory,
    get_inventory_stats,
)
from scenes import (
    extract_srt_window,
)
from utils import (
    get_ffmpeg_bin,
    get_whisper_model_chain,
    run_subprocess,
    find_media_file,
    find_subtitle_file,
    format_hms,
    parse_timestamp_to_seconds,
)

console = Console()


# -----------------------------------------------------------------------------
# Dogpile Integration
# -----------------------------------------------------------------------------
def run_dogpile(query: str, preset: str = "movie_scenes", timeout_sec: int = 300) -> Dict[str, Any]:
    """
    Run dogpile search and return results.

    Args:
        query: Search query string
        preset: Dogpile preset to use (default: movie_scenes)
        timeout_sec: Timeout in seconds (default: 300)

    Returns:
        Dict with either results or error information
    """
    dogpile_script = DOGPILE_DIR / "dogpile.py"

    if not dogpile_script.exists():
        return {"error": f"Dogpile not found at {dogpile_script}", "status": "not_found"}

    cmd = [
        sys.executable, str(dogpile_script),
        "search", query,
        "--preset", preset,
        "--json"
    ]

    proc = None
    try:
        # Use Popen for better process control
        # start_new_session=True ensures child process is in its own session
        # so it can be cleanly killed without affecting parent
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(DOGPILE_DIR),
            start_new_session=True,
        )

        try:
            stdout, stderr = proc.communicate(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            # Attempt graceful termination of the process group, then force kill if needed
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    proc.kill()
                proc.wait(timeout=5)
            return {
                "error": f"Dogpile search timed out after {timeout_sec}s",
                "status": "timeout",
                "query": query
            }

        if proc.returncode == 0:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                return {"raw_output": stdout, "status": "success", "query": query}
        else:
            return {
                "error": stderr or "Unknown error",
                "status": "failed",
                "returncode": proc.returncode,
                "query": query
            }
    except FileNotFoundError:
        return {"error": f"Python interpreter not found: {sys.executable}", "status": "exception"}
    except Exception as e:
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except Exception:
                    proc.kill()
                proc.wait(timeout=5)
        return {"error": str(e), "status": "exception", "query": query}


# -----------------------------------------------------------------------------
# Agent Inbox Integration
# -----------------------------------------------------------------------------
def send_to_inbox(
    to_project: str,
    message: str,
    message_type: str = "request",
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """Send a message via agent-inbox."""
    skills_dir = Path(__file__).resolve().parents[1]
    inbox_script = skills_dir / "agent-inbox" / "inbox.py"

    if not inbox_script.exists():
        console.print(f"[yellow]Agent inbox not found at {inbox_script}[/yellow]")
        return False

    full_message = message
    if metadata:
        full_message = f"{message}\n\n---\nMetadata: {json.dumps(metadata)}"

    cmd = [
        sys.executable, str(inbox_script),
        "send",
        "--to", to_project,
        "--type", message_type,
        full_message
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0
    except Exception as e:
        console.print(f"[red]Failed to send to inbox: {e}[/red]")
        return False


# -----------------------------------------------------------------------------
# Agent Commands
# -----------------------------------------------------------------------------
def recommend_movies(
    emotion: str,
    actor_model: Optional[str] = None,
    library_path: Optional[Path] = None,
    exclude_movies: Optional[str] = None,
    output_json: Optional[Path] = None,
    max_results: int = 5,
) -> Dict[str, Any]:
    """
    Research movies with emotional scenes for TTS training.

    Args:
        emotion: Target emotion (rage, anger, sorrow, regret, camaraderie, command)
        actor_model: Actor model override (DDL, Pacino, Crowe, Carlin, Bardem, Butler)
        library_path: Local media library to cross-reference
        exclude_movies: Comma-separated movies to exclude
        output_json: Save recommendations to JSON
        max_results: Maximum movie recommendations

    Returns:
        Recommendations dict with dogpile results and agent instructions
    """
    emotion = emotion.lower()
    if emotion not in VALID_EMOTIONS:
        raise ValueError(f"Unknown emotion '{emotion}'. Allowed: {sorted(VALID_EMOTIONS)}")

    archetype = HORUS_ARCHETYPE_MAP.get(emotion, {})
    default_actor = archetype.get("actor_model", "Unknown")
    voice_tone = archetype.get("voice_tone", "neutral")

    actor_hint = actor_model or default_actor.split("(")[0].strip()
    exclusions = [m.strip() for m in (exclude_movies or "").split(",") if m.strip()]

    query_parts = [
        f"war movies {emotion} scenes",
        f"{actor_hint} intensity performance",
        voice_tone.replace("_", " "),
        "dramatic monologue dialogue"
    ]
    query = " ".join(query_parts)

    console.print(f"[cyan]Researching movies for emotion: {emotion}[/cyan]")
    console.print(f"[dim]Actor model: {default_actor}[/dim]")
    console.print(f"[dim]Voice tone: {voice_tone}[/dim]")

    # Run dogpile search
    console.print("[cyan]Running dogpile search (movie_scenes preset)...[/cyan]")
    dogpile_results = run_dogpile(query, preset="movie_scenes")

    if "error" in dogpile_results:
        console.print(f"[yellow]Dogpile warning: {dogpile_results.get('error')}[/yellow]")

    # Check local library
    local_movies: Dict[str, Path] = {}
    if library_path and library_path.exists():
        console.print(f"[cyan]Scanning local library: {library_path}[/cyan]")
        for item in library_path.iterdir():
            if item.is_dir():
                video = find_media_file(item)
                if video:
                    movie_name = item.name
                    clean_name = re.sub(r'\s*\(\d{4}\)\s*$', '', movie_name)
                    local_movies[clean_name.lower()] = item

    recommendations = {
        "query": query,
        "emotion_target": emotion,
        "actor_model": default_actor,
        "voice_tone": voice_tone,
        "archetype": archetype.get("primary_archetype", "unknown"),
        "bdi_patterns": {
            "belief": archetype.get("belief_pattern", ""),
            "desire": archetype.get("desire_pattern", ""),
            "intention": archetype.get("intention_pattern", ""),
        },
        "dogpile_results": dogpile_results,
        "local_library_count": len(local_movies),
        "exclusions": exclusions,
        "candidates": [],
        "instructions_for_horus": f"""
## Movie Selection for {emotion.upper()} Emotion

Review the candidates below. For each movie, consider:
1. Does the actor's performance match the {voice_tone.replace('_', ' ')} tone needed?
2. Are there specific scenes with the right emotional intensity?
3. Is SDH subtitle availability confirmed?
4. Is the movie available locally or via streaming?

After reviewing, respond with your selections in this format:
```
APPROVED: Movie Title (Year) - Scene: "description" @ timestamp
QUEUE: Movie Title (Year) - for {emotion} later
SKIP: Movie Title (Year) - reason
```

Then I'll extract the clips using:
  python movie_ingest.py agent quick --movie "path" --emotion {emotion} --scene "description" --timestamp "HH:MM:SS-HH:MM:SS"
""",
    }

    # Display for agent review
    console.print("\n" + "=" * 70)
    console.print(f"[bold green]MOVIE RECOMMENDATIONS FOR {emotion.upper()}[/bold green]")
    console.print("=" * 70)

    console.print(f"\n[bold]Target Profile:[/bold]")
    console.print(f"  Actor Model: {default_actor}")
    console.print(f"  Voice Tone: {voice_tone}")

    if local_movies:
        console.print(f"\n[bold]Local Library ({len(local_movies)} movies available):[/bold]")
        for name, path in sorted(local_movies.items())[:10]:
            console.print(f"  ✓ {path.name}")

    console.print(f"\n[bold]Research Results:[/bold]")
    if "raw_output" in dogpile_results:
        console.print(dogpile_results["raw_output"][:2000])
    else:
        console.print(json.dumps(dogpile_results, indent=2)[:2000])

    console.print("\n" + "-" * 70)
    console.print(recommendations["instructions_for_horus"])

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w") as f:
            json.dump(recommendations, f, indent=2, default=str)
        console.print(f"\n[green]Recommendations saved to {output_json}[/green]")

    return recommendations


def quick_extract(
    movie: Path,
    emotion: str,
    scene: str,
    timestamp: str,
    output_dir: Optional[Path] = None,
    characters: Optional[str] = None,
    clip_id: Optional[str] = None,
    notify_project: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Single-step clip extraction: download subs → extract clip → create persona JSON.

    Args:
        movie: Path to movie file or directory
        emotion: Target emotion
        scene: Scene description
        timestamp: Timestamp range (HH:MM:SS-HH:MM:SS or SS-SS)
        output_dir: Output directory for persona JSON
        characters: Comma-separated character names
        clip_id: Custom clip ID
        notify_project: Send completion to agent-inbox project

    Returns:
        Dict with status and output paths
    """
    # Import here to avoid circular imports
    from transcribe import create_persona_json, run_whisper
    from extract import extract_audio
    from subs import download_subtitles

    emotion = emotion.lower()
    if emotion not in VALID_EMOTIONS:
        raise ValueError(f"Unknown emotion '{emotion}'. Allowed: {sorted(VALID_EMOTIONS)}")

    # Parse timestamp
    timestamp_pattern = r'^(\d{1,2}:?\d{2}:?\d{2})-(\d{1,2}:?\d{2}:?\d{2})$'
    match = re.match(timestamp_pattern, timestamp.replace(" ", ""))
    if not match:
        sec_pattern = r'^(\d+)-(\d+)$'
        sec_match = re.match(sec_pattern, timestamp.replace(" ", ""))
        if sec_match:
            start_sec = int(sec_match.group(1))
            end_sec = int(sec_match.group(2))
        else:
            raise ValueError(f"Invalid timestamp format: {timestamp}. Use HH:MM:SS-HH:MM:SS or SS-SS")
    else:
        start_str, end_str = match.groups()
        start_sec = parse_timestamp_to_seconds(start_str)
        end_sec = parse_timestamp_to_seconds(end_str)

    if end_sec <= start_sec:
        raise ValueError("End timestamp must be after start timestamp")

    # Resolve movie path
    if movie.is_dir():
        video_file = find_media_file(movie)
        if not video_file:
            raise ValueError(f"No video file found in {movie}")
        movie_dir = movie
    else:
        video_file = movie
        movie_dir = movie.parent

    movie_title = movie_dir.name
    console.print(f"[cyan]Quick extraction: {movie_title}[/cyan]")
    console.print(f"[dim]Emotion: {emotion} | Scene: {scene}[/dim]")
    console.print(f"[dim]Timestamp: {format_hms(start_sec)} - {format_hms(end_sec)}[/dim]")

    # Step 1: Ensure subtitles exist
    console.print("\n[bold]Step 1/4:[/bold] Checking subtitles...")
    subtitle_file = find_subtitle_file(movie_dir, prefer_sdh=True)

    if not subtitle_file:
        console.print("[yellow]No subtitles found. Downloading...[/yellow]")
        subtitle_file = download_subtitles(video_file, prefer_sdh=True)
        if not subtitle_file:
            console.print("[red]Failed to obtain subtitles. Cannot proceed.[/red]")
            raise ValueError("No subtitles available")

    console.print(f"[green]✓ Using subtitles: {subtitle_file.name}[/green]")

    # Step 2: Create clip directory and extract video segment
    console.print("\n[bold]Step 2/4:[/bold] Extracting video clip...")

    clip_name = clip_id or f"clip_{emotion}_{int(start_sec)}"
    emotion_clips_dir = movie_dir / f"{emotion}_clips"
    emotion_clips_dir.mkdir(exist_ok=True)

    clip_video = emotion_clips_dir / f"{clip_name}.mkv"
    clip_srt = emotion_clips_dir / f"{clip_name}.srt"

    # Track created files for cleanup on failure
    created_files: list[Path] = []
    # Initialize persona_json before try block to ensure it's defined for cleanup
    persona_json: Optional[Path] = None

    def _cleanup_on_failure():
        for f in created_files:
            if f.exists():
                try:
                    f.unlink()
                    console.print(f"[dim]Cleaned up: {f.name}[/dim]")
                except Exception as e:
                    console.print(f"[yellow]Warning: Could not clean up {f.name}: {e}[/yellow]")
        if emotion_clips_dir.exists() and not any(emotion_clips_dir.iterdir()):
            try:
                emotion_clips_dir.rmdir()
            except Exception:
                pass

    try:
        # Extract video segment
        ffmpeg_cmd = [
            get_ffmpeg_bin(), "-y",
            "-ss", format_hms(start_sec),
            "-to", format_hms(end_sec),
            "-i", str(video_file),
            "-c", "copy",
            str(clip_video)
        ]
        run_subprocess(ffmpeg_cmd, timeout_sec=120)
        created_files.append(clip_video)
        console.print(f"[green]✓ Extracted clip: {clip_video.name}[/green]")

        # Step 3: Extract subtitle window
        console.print("\n[bold]Step 3/4:[/bold] Extracting subtitle window...")
        has_subtitles = extract_srt_window(subtitle_file, start_sec, end_sec, clip_srt)
        # Only track clip_srt for cleanup if it was actually created
        if has_subtitles and clip_srt.exists():
            created_files.append(clip_srt)

        if not has_subtitles:
            console.print("[yellow]Warning: No subtitles in time window.[/yellow]")

        # Step 4: Run transcription to create persona JSON
        console.print("\n[bold]Step 4/4:[/bold] Creating persona JSON...")

        persona_dir = emotion_clips_dir / "persona"
        persona_dir.mkdir(exist_ok=True)

        # Extract audio
        audio_file = persona_dir / f"{clip_name}.wav"
        extract_audio(clip_video, audio_file)
        created_files.append(audio_file)

        # Run Whisper with fallback chain
        transcript_json = None
        whisper_models = get_whisper_model_chain()
        model_errors: list[str] = []
        for model in whisper_models:
            console.print(f"[dim]Trying Whisper model: {model}[/dim]")
            try:
                transcript_json = run_whisper(audio_file, persona_dir, model=model)
                if transcript_json:
                    console.print(f"[green]✓ Transcription succeeded with model: {model}[/green]")
                    break
            except Exception as e:
                err = f"{model}: {e}"
                model_errors.append(err)
                console.print(f"[yellow]Model {model} failed: {e}[/yellow]")
                continue
        if not transcript_json:
            raise ValueError(f"Whisper transcription failed with all models: {whisper_models}; errors: {model_errors}")

        # Create persona JSON
        persona_json = persona_dir / f"{clip_name}_persona.json"
        create_persona_json(
            transcript_json=transcript_json,
            audio_file=audio_file,
            input_file=clip_video,
            subtitle_path=clip_srt if has_subtitles else subtitle_file,
            output_path=persona_json,
            emotion=emotion,
            movie_title=movie_title,
            scene=scene,
            characters=characters,
            source_id=clip_name,
        )
        created_files.append(persona_json)

        # Clean up intermediate audio
        if audio_file.exists():
            audio_file.unlink()
            try:
                created_files.remove(audio_file)
            except ValueError:
                pass
        # Remove persona dir if it ended up empty (use next() for efficiency)
        if persona_dir.exists():
            try:
                next(persona_dir.iterdir())
            except StopIteration:
                try:
                    persona_dir.rmdir()
                except Exception:
                    pass

    except Exception as e:
        console.print(f"\n[red]Extraction failed: {e}[/red]")
        console.print("[yellow]Cleaning up partial files...[/yellow]")
        _cleanup_on_failure()
        raise

    if persona_json is None or not persona_json.exists():
        console.print(f"[red]Error: Persona JSON not created[/red]")
        _cleanup_on_failure()
        raise ValueError("Persona JSON not created")

    # Copy to output directory if specified
    final_output = persona_json
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        final_output = output_dir / persona_json.name
        shutil.copy(persona_json, final_output)
        console.print(f"[green]✓ Copied to: {final_output}[/green]")

    # Update inventory
    add_clip_to_inventory(
        movie_title=movie_title,
        emotion=emotion,
        clip_path=clip_video,
        persona_path=final_output,
        scene_description=scene,
        timestamp=f"{format_hms(start_sec)}-{format_hms(end_sec)}",
    )

    # Notify via agent-inbox if requested
    if notify_project:
        send_to_inbox(
            to_project=notify_project,
            message=f"Clip extraction complete: {clip_name}",
            message_type="completion",
            metadata={
                "clip_id": clip_name,
                "movie": movie_title,
                "emotion": emotion,
                "scene": scene,
                "persona_json": str(final_output),
            }
        )
        console.print(f"[green]✓ Notified project: {notify_project}[/green]")

    console.print(f"\n[bold green]✓ Quick extraction complete![/bold green]")
    console.print(f"Persona JSON: {final_output}")

    return {"status": "success", "persona_json": str(final_output), "clip_id": clip_name}


def discover_scenes(
    library_path: Path,
    emotion: Optional[str] = None,
    query: Optional[str] = None,
    max_per_movie: int = 5,
    output_json: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Discover emotion-matching scenes in local media library by scanning subtitles.

    Args:
        library_path: Media library directory to scan
        emotion: Filter by emotion
        query: Text search in subtitles
        max_per_movie: Max scenes per movie
        output_json: Save results to JSON

    Returns:
        Discovery results with matching scenes
    """
    if emotion:
        emotion = emotion.lower()
        if emotion not in VALID_EMOTIONS:
            raise ValueError(f"Unknown emotion '{emotion}'. Allowed: {sorted(VALID_EMOTIONS)}")

    emotion_keywords = {
        "rage": ["rage", "fury", "betray", "traitor", "destroy", "kill", "blood", "vengeance", "damn"],
        "anger": ["angry", "hate", "cold", "quiet", "fool", "mistake", "pay", "consequence"],
        "sorrow": ["mourn", "grief", "loss", "death", "gone", "remember", "honor", "fallen", "farewell"],
        "regret": ["mistake", "wrong", "should have", "could have", "fool", "error", "wish", "if only"],
        "camaraderie": ["brother", "together", "fight", "stand", "loyal", "friend", "comrade", "side"],
        "command": ["follow", "lead", "order", "fight", "glory", "victory", "charge", "men", "soldiers"],
    }

    if emotion:
        keywords = emotion_keywords.get(emotion, [])
        if query:
            keywords.append(query.lower())
    elif query:
        keywords = [query.lower()]
    else:
        raise ValueError("Must specify --emotion or --query")

    console.print(f"[cyan]Scanning library: {library_path}[/cyan]")
    console.print(f"[dim]Keywords: {', '.join(keywords)}[/dim]\n")

    results = []
    movies_scanned = 0

    for movie_dir in library_path.iterdir():
        if not movie_dir.is_dir():
            continue

        srt_file = find_subtitle_file(movie_dir, prefer_sdh=True)
        if not srt_file:
            continue

        movies_scanned += 1
        movie_name = movie_dir.name

        try:
            with open(srt_file, 'r', encoding='utf-8-sig', errors='ignore') as f:
                content = f.read()
        except Exception:
            continue

        pattern = r'(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*?)(?=\n\n|\Z)'
        matches = re.findall(pattern, content, re.DOTALL)

        movie_matches = []
        for num, start, end, text in matches:
            text_lower = text.lower()
            matched_keywords = [kw for kw in keywords if kw in text_lower]

            if matched_keywords:
                movie_matches.append({
                    "timestamp": start.split(",")[0],
                    "text": text.strip()[:200],
                    "keywords_matched": matched_keywords,
                })

        if movie_matches:
            movie_matches.sort(key=lambda x: len(x["keywords_matched"]), reverse=True)

            results.append({
                "movie": movie_name,
                "subtitle_file": str(srt_file),
                "video_file": str(find_media_file(movie_dir) or ""),
                "matches": movie_matches[:max_per_movie],
                "total_matches": len(movie_matches),
            })

            console.print(f"[green]✓ {movie_name}[/green]: {len(movie_matches)} scenes found")
            for m in movie_matches[:3]:
                console.print(f"  [{m['timestamp']}] {m['text'][:60]}...")

    console.print(f"\n[bold]Scanned {movies_scanned} movies, found scenes in {len(results)}[/bold]")

    discovery_results = {
        "emotion": emotion,
        "query": query,
        "keywords": keywords,
        "movies_scanned": movies_scanned,
        "movies_with_matches": len(results),
        "results": results,
        "instructions_for_horus": f"""
## Scene Discovery Results

Found {sum(r['total_matches'] for r in results)} potential {emotion or 'matching'} scenes across {len(results)} movies.

To extract a scene, use:
```
python movie_ingest.py agent quick \\
    --movie "MOVIE_PATH" \\
    --emotion {emotion or 'EMOTION'} \\
    --scene "DESCRIPTION" \\
    --timestamp "START-END"
```
""",
    }

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w") as f:
            json.dump(discovery_results, f, indent=2)
        console.print(f"\n[green]Results saved to {output_json}[/green]")

    return discovery_results


def show_inventory(emotion: Optional[str] = None, as_json: bool = False) -> Dict[str, Any]:
    """
    Show inventory of processed clips.

    Args:
        emotion: Filter by emotion
        as_json: Output as JSON

    Returns:
        Inventory stats dict
    """
    inventory = load_inventory()
    clips = inventory.get("clips", [])

    if emotion:
        clips = [c for c in clips if c.get("emotion") == emotion.lower()]

    if as_json:
        print(json.dumps({"clips": clips, "total": len(clips)}, indent=2))
        return {"clips": clips, "total": len(clips)}

    stats = get_inventory_stats()

    console.print("[bold]Clip Inventory[/bold]")
    console.print(f"Total clips: {stats['total_clips']}")
    console.print(f"Movies processed: {stats['movies_processed']}")
    console.print(f"Last updated: {inventory.get('last_updated', 'Never')}\n")

    console.print("[bold]Clips by Emotion:[/bold]")
    for e in VALID_EMOTIONS:
        count = stats['clips_by_emotion'].get(e, 0)
        status = "✓" if count >= 5 else "○"
        console.print(f"  {status} {e}: {count}")

    if clips:
        console.print(f"\n[bold]Recent Clips{' (' + emotion + ')' if emotion else ''}:[/bold]")
        for clip in clips[-10:]:
            console.print(f"  [{clip.get('emotion', '?')}] {clip.get('movie_title', 'Unknown')} - {clip.get('scene_description', '')[:40]}")

    return stats


def request_extraction(
    to_project: str,
    emotion: str,
    description: str,
    count: int = 5,
) -> bool:
    """
    Send a clip extraction request to another project via agent-inbox.

    Args:
        to_project: Target project
        emotion: Target emotion
        description: What kind of scenes are needed
        count: Number of clips needed

    Returns:
        True if request sent successfully
    """
    emotion = emotion.lower()
    if emotion not in VALID_EMOTIONS:
        raise ValueError(f"Unknown emotion '{emotion}'. Allowed: {sorted(VALID_EMOTIONS)}")

    archetype = HORUS_ARCHETYPE_MAP.get(emotion, {})

    request_data = {
        "type": "clip_request",
        "emotion": emotion,
        "description": description,
        "count_needed": count,
        "archetype": archetype.get("primary_archetype"),
        "actor_model": archetype.get("actor_model"),
        "voice_tone": archetype.get("voice_tone"),
        "bdi_patterns": {
            "belief": archetype.get("belief_pattern"),
            "desire": archetype.get("desire_pattern"),
            "intention": archetype.get("intention_pattern"),
        },
    }

    message = f"""Clip Extraction Request

Emotion: {emotion}
Description: {description}
Count needed: {count}

Actor Model: {archetype.get('actor_model', 'Unknown')}
Voice Tone: {archetype.get('voice_tone', 'Unknown')}

Please use `python movie_ingest.py agent recommend {emotion}` to find suitable movies,
then `python movie_ingest.py agent quick` to extract clips."""

    success = send_to_inbox(
        to_project=to_project,
        message=message,
        message_type="request",
        metadata=request_data,
    )

    if success:
        console.print(f"[green]✓ Request sent to {to_project}[/green]")
    else:
        console.print(f"[red]✗ Failed to send request[/red]")

    return success
