"""Bridge to import content from ingest-movie."""

import json
import sys
from pathlib import Path
from typing import Optional
from rich.console import Console
import typer

# ── TaskClient integration ──────────────────────────────────────────────────
try:
    sys.path.insert(0, str(Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

console = Console()


def sync_from_ingest(ingest_path: Optional[Path] = None, registry_path: Optional[Path] = None) -> int:
    """Import movies from ingest-movie to consume-movie registry.

    Args:
        ingest_path: Path to ingest-movie transcripts directory
        registry_path: Override registry path

    Returns:
        Number of movies imported
    """
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent.parent / "consume-common"))
        from consume_common.registry import ContentRegistry
    except ImportError as e:
        print(f"SKIP: ContentRegistry not importable: {e}")
        return 0

    if not ingest_path:
        ingest_path = Path(__file__).parent.parent.parent / "ingest-movie" / "transcripts"

    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-movie" / "registry.json"

    if not ingest_path.exists():
        console.print(f"[red]Ingest path not found: {ingest_path}[/red]")
        return 0

    registry = ContentRegistry(registry_path)
    imported = 0

    # Find all transcript JSON files
    transcript_files = list(ingest_path.glob("*.json"))
    console.print(f"[cyan]Found {len(transcript_files)} transcript files[/cyan]")

    monitor = TaskClient("consume-movie-sync", total=len(transcript_files)) if TaskClient else None

    for transcript_file in transcript_files:
        try:
            # Load transcript data
            with open(transcript_file, "r", encoding="utf-8") as f:
                transcript_data = json.load(f)

            # Extract metadata from meta if available
            meta = transcript_data.get("meta", {})
            title = transcript_data.get("title") or meta.get("movie_title") or transcript_file.stem
            duration = transcript_data.get("duration") or meta.get("duration_sec") or 0
            segments = transcript_data.get("segments") or transcript_data.get("transcript", [])
            
            # Resolve path via Jellyfin if needed
            source_path = str(transcript_file)
            from jellyfin_client import JellyfinClient
            jellyfin = JellyfinClient()
            try:
                remote_path = jellyfin.get_item_path(title)
                if remote_path:
                    console.print(f"[dim]Jellyfin resolved '{title}' to: {remote_path}[/dim]")
                    # We store the local transcript path as primary, but could store remote path in meta
            except Exception as e:
                console.print(f"[dim]Jellyfin resolution skip: {e}[/dim]")

            # Look for emotion tags in transcript
            emotion_tags = set()
            for segment in segments:
                tags = segment.get("tags", [])
                for tag in tags:
                    if tag in ["rage", "anger", "confrontation", "manipulation"]:
                        emotion_tags.add(tag)

            # Create content entry
            content_data = {
                "type": "movie",
                "title": title,
                "source_path": str(transcript_file),
                "metadata": {
                    "duration": duration,
                    "segment_count": len(segments),
                    "emotion_tags": list(emotion_tags),
                    "transcript_file": str(transcript_file.name)
                }
            }

            # Check if already exists
            existing = None
            for content in registry.list_content("movie"):
                if content.get("source_path") == str(transcript_file):
                    existing = content
                    break

            if existing:
                console.print(f"[yellow]Skipping existing: {title}[/yellow]")
                continue

            # Add to registry
            content_id = registry.add_content(content_data)
            imported += 1
            console.print(f"[green]Imported: {title} (ID: {content_id[:8]}...)[/green]")

        except Exception as e:
            console.print(f"[red]Error importing {transcript_file}: {e}[/red]")
            continue
        if monitor:
            monitor.update(item=transcript_file.name)

    if monitor:
        monitor.finish()
    console.print(f"[green]Total imported: {imported} movies[/green]")
    return imported


def main(
    ingest: Optional[str] = typer.Option(None, help="Path to ingest-movie transcripts directory"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """CLI entry point for sync."""

    ingest_path = Path(ingest) if ingest else None
    count = sync_from_ingest(ingest_path=ingest_path)

    if json:
        print(json.dumps({"imported": count}))
    else:
        console.print(f"[green]Imported {count} movies[/green]")


if __name__ == "__main__":
    main()