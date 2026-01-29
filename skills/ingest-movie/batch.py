"""
Movie Ingest Skill - Batch Processing Module
Batch discovery, planning, and execution for automated pipelines.
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console
from rich.table import Table

from config import (
    VALID_EMOTIONS,
    EMOTION_MOVIE_MAPPINGS,
    DEFAULT_MOVIE_LIBRARY,
)
from utils import find_media_file, find_subtitle_file

console = Console()


def batch_discover(
    library_path: Optional[Path] = None,
    check_subtitles: bool = True,
) -> Dict[str, Any]:
    """
    Scan media directories to create an inventory of available movies.

    Args:
        library_path: Path to media library (defaults to DEFAULT_MOVIE_LIBRARY)
        check_subtitles: Check for subtitle availability

    Returns:
        Dict with discovered movies and their metadata
    """
    library = library_path or DEFAULT_MOVIE_LIBRARY
    if not library.exists():
        console.print(f"[red]Library path not found: {library}[/red]")
        return {"movies": [], "error": "Library not found"}

    console.print(f"[cyan]Scanning library: {library}[/cyan]")

    movies = []
    for item in sorted(library.iterdir()):
        if not item.is_dir():
            continue

        video = find_media_file(item)
        if not video:
            continue

        movie_info = {
            "name": item.name,
            "path": str(item),
            "video_file": str(video),
            "size_gb": round(video.stat().st_size / (1024**3), 2),
        }

        if check_subtitles:
            srt = find_subtitle_file(item, prefer_sdh=True)
            movie_info["has_subtitle"] = srt is not None
            if srt:
                movie_info["subtitle_file"] = str(srt)
                # Check for SDH
                movie_info["has_sdh"] = any(
                    x in srt.name.lower()
                    for x in ['sdh', 'cc', 'hearing']
                )

        movies.append(movie_info)

    console.print(f"\n[bold]Found {len(movies)} movies[/bold]")

    # Display table
    table = Table(title="Movie Library")
    table.add_column("Title", style="green")
    table.add_column("Size", style="cyan")
    table.add_column("Subs", style="yellow", justify="center")

    for m in movies[:30]:
        subs = "✓ SDH" if m.get("has_sdh") else ("✓" if m.get("has_subtitle") else "✗")
        table.add_row(
            m["name"][:50],
            f"{m['size_gb']:.1f} GB",
            subs
        )

    if len(movies) > 30:
        table.add_row("...", "...", "...")
        table.add_row(f"({len(movies) - 30} more)", "", "")

    console.print(table)

    return {
        "library_path": str(library),
        "total_movies": len(movies),
        "with_subtitles": sum(1 for m in movies if m.get("has_subtitle")),
        "with_sdh": sum(1 for m in movies if m.get("has_sdh")),
        "movies": movies,
    }


def batch_plan(
    emotions: Optional[list[str]] = None,
    library_path: Optional[Path] = None,
    include_unavailable: bool = False,
    output_json: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Create a processing manifest from built-in emotion-movie mappings.

    Args:
        emotions: List of emotions to plan for (default: all)
        library_path: Path to media library
        include_unavailable: Include movies not in local library
        output_json: Save manifest to JSON file

    Returns:
        Processing manifest
    """
    library = library_path or DEFAULT_MOVIE_LIBRARY

    # Get local library inventory
    local_movies = {}
    if library.exists():
        for item in library.iterdir():
            if item.is_dir():
                # Normalize name for matching
                name_lower = item.name.lower()
                # Remove year pattern
                import re
                clean = re.sub(r'\s*\(\d{4}\)\s*$', '', name_lower)
                local_movies[clean] = item

    target_emotions = emotions or list(VALID_EMOTIONS)
    target_emotions = [e.lower() for e in target_emotions]

    console.print(f"[cyan]Planning batch for emotions: {', '.join(target_emotions)}[/cyan]")

    manifest = {
        "emotions": target_emotions,
        "library_path": str(library),
        "tasks": [],
        "summary": {"ready": 0, "needs_subtitle": 0, "not_in_library": 0},
    }

    for emotion in target_emotions:
        mappings = EMOTION_MOVIE_MAPPINGS.get(emotion, [])
        if not mappings:
            console.print(f"[yellow]No mappings for emotion: {emotion}[/yellow]")
            continue

        for mapping in mappings:
            title = mapping["title"]
            year = mapping.get("year", "")
            scenes = mapping.get("scenes", [])

            # Try to find in local library
            title_lower = title.lower()
            local_path = local_movies.get(title_lower)

            if not local_path:
                # Try with year
                for key, path in local_movies.items():
                    if title_lower in key:
                        local_path = path
                        break

            task = {
                "emotion": emotion,
                "movie_title": title,
                "year": year,
                "scenes": scenes,
                "status": "not_in_library",
            }

            if local_path:
                task["local_path"] = str(local_path)
                srt = find_subtitle_file(local_path, prefer_sdh=True)
                if srt:
                    task["subtitle_file"] = str(srt)
                    task["status"] = "ready"
                    manifest["summary"]["ready"] += 1
                else:
                    task["status"] = "needs_subtitle"
                    manifest["summary"]["needs_subtitle"] += 1
            else:
                manifest["summary"]["not_in_library"] += 1
                if not include_unavailable:
                    continue

            manifest["tasks"].append(task)

    # Display summary
    console.print(f"\n[bold]Batch Plan Summary:[/bold]")
    console.print(f"  Ready to process: {manifest['summary']['ready']}")
    console.print(f"  Need subtitles: {manifest['summary']['needs_subtitle']}")
    console.print(f"  Not in library: {manifest['summary']['not_in_library']}")

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        with open(output_json, "w") as f:
            json.dump(manifest, f, indent=2)
        console.print(f"\n[green]Manifest saved to {output_json}[/green]")

    return manifest


def batch_run(
    manifest_path: Path,
    dry_run: bool = True,
    max_per_emotion: int = 5,
) -> Dict[str, Any]:
    """
    Execute batch processing from a manifest.

    Args:
        manifest_path: Path to batch manifest JSON
        dry_run: Preview without executing
        max_per_emotion: Maximum clips per emotion

    Returns:
        Execution results
    """
    from agent import quick_extract

    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_path) as f:
        manifest = json.load(f)

    tasks = manifest.get("tasks", [])
    ready_tasks = [t for t in tasks if t.get("status") == "ready"]

    console.print(f"[cyan]Batch processing: {len(ready_tasks)} ready tasks[/cyan]")

    if dry_run:
        console.print("[yellow]DRY RUN - no changes will be made[/yellow]\n")

    results = {"processed": [], "skipped": [], "failed": []}
    emotion_counts = {}

    for task in ready_tasks:
        emotion = task["emotion"]
        count = emotion_counts.get(emotion, 0)

        if count >= max_per_emotion:
            console.print(f"[dim]Skipping {task['movie_title']} - emotion {emotion} at max[/dim]")
            results["skipped"].append(task)
            continue

        console.print(f"\n[bold]Processing:[/bold] {task['movie_title']} ({emotion})")

        if dry_run:
            console.print(f"  Would extract scenes: {task.get('scenes', [])}")
            results["processed"].append(task)
            emotion_counts[emotion] = count + 1
            continue

        # Real execution
        try:
            local_path = Path(task["local_path"])
            for scene_desc in task.get("scenes", [])[:1]:  # One scene per movie
                quick_extract(
                    movie=local_path,
                    emotion=emotion,
                    scene=scene_desc,
                    timestamp="00:30:00-00:32:00",  # Placeholder - would need real timestamps
                )
            results["processed"].append(task)
            emotion_counts[emotion] = count + 1
        except Exception as e:
            console.print(f"[red]Failed: {e}[/red]")
            task["error"] = str(e)
            results["failed"].append(task)

    console.print(f"\n[bold]Batch Results:[/bold]")
    console.print(f"  Processed: {len(results['processed'])}")
    console.print(f"  Skipped: {len(results['skipped'])}")
    console.print(f"  Failed: {len(results['failed'])}")

    return results


def batch_status() -> Dict[str, Any]:
    """
    Show status of processed emotion exemplars.

    Returns:
        Status summary
    """
    from inventory import load_inventory, get_inventory_stats

    stats = get_inventory_stats()

    console.print("[bold]Batch Processing Status[/bold]\n")

    table = Table(title="Emotion Coverage")
    table.add_column("Emotion", style="cyan")
    table.add_column("Clips", style="green", justify="right")
    table.add_column("Movies", style="yellow", justify="right")
    table.add_column("Threshold", style="magenta", justify="center")

    for emotion in VALID_EMOTIONS:
        count = stats["clips_by_emotion"].get(emotion, 0)
        threshold = "✓" if count >= 5 else f"Need {5 - count}"
        table.add_row(emotion, str(count), "-", threshold)

    console.print(table)

    console.print(f"\n[bold]Total clips:[/bold] {stats['total_clips']}")
    console.print(f"[bold]Movies processed:[/bold] {stats['movies_processed']}")
    console.print(f"[bold]Last updated:[/bold] {stats.get('last_updated', 'Never')}")

    return stats
