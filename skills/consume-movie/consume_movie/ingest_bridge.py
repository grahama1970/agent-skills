"""Bridge to import content from ingest-movie."""

import json
from pathlib import Path
from typing import Optional
from rich.console import Console

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

    for transcript_file in transcript_files:
        try:
            # Load transcript data
            with open(transcript_file, "r", encoding="utf-8") as f:
                transcript_data = json.load(f)

            # Extract metadata
            title = transcript_data.get("title", transcript_file.stem)
            duration = transcript_data.get("duration", 0)
            segments = transcript_data.get("segments", [])

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

    console.print(f"[green]Total imported: {imported} movies[/green]")
    return imported


def main():
    """CLI entry point for sync."""
    import argparse

    parser = argparse.ArgumentParser(description="Sync movies from ingest-movie")
    parser.add_argument("--ingest", help="Path to ingest-movie transcripts directory")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    ingest_path = Path(args.ingest) if args.ingest else None
    count = sync_from_ingest(ingest_path=ingest_path)

    if args.json:
        print(json.dumps({"imported": count}))
    else:
        console.print(f"[green]Imported {count} movies[/green]")


if __name__ == "__main__":
    main()