"""Clip extraction functionality for consume-movie."""

import json
import subprocess
from pathlib import Path
from typing import Optional
from rich.console import Console

console = Console()


def extract_clip(
    query: str,
    output_dir: Path,
    duration: int = 10,
    registry_path: Optional[Path] = None
) -> Optional[Path]:
    """Extract a video clip matching the search query.

    Args:
        query: Text to search for in subtitles
        output_dir: Directory to save clip
        duration: Clip duration in seconds
        registry_path: Override registry path

    Returns:
        Path to extracted clip or None
    """
    from .search import search_subtitles

    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-movie" / "registry.json"

    # Search for the query
    results = search_subtitles(query, registry_path=registry_path)
    if not results:
        console.print(f"[red]No matches found for '{query}'[/red]")
        return None

    # Use first result
    result = results[0]
    movie_id = result["movie_id"]
    start_time = result["start"]
    movie_title = result["movie_title"]

    # Find video file
    video_path = find_video_file(result["srt_path"])
    if not video_path:
        console.print(f"[red]No video file found for {movie_title}[/red]")
        return None

    # Create output filename
    safe_title = "".join(c for c in movie_title if c.isalnum() or c in " -_").strip()
    safe_query = "".join(c for c in query if c.isalnum() or c in " -_").strip()[:30]
    output_filename = f"{safe_title}_{safe_query}_{int(start_time)}s.mp4"
    output_path = Path(output_dir) / output_filename

    # Extract clip using ffmpeg
    try:
        cmd = [
            "ffmpeg",
            "-ss", str(start_time),
            "-t", str(duration),
            "-i", str(video_path),
            "-c", "copy",  # Copy codec for speed
            "-y",  # Overwrite output
            str(output_path)
        ]

        console.print(f"[cyan]Extracting clip: {movie_title} at {start_time}s[/cyan]")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            console.print(f"[green]Clip saved: {output_path}[/green]")
            return output_path
        else:
            console.print(f"[red]FFmpeg error: {result.stderr}[/red]")
            return None

    except Exception as e:
        console.print(f"[red]Error extracting clip: {e}[/red]")
        return None


def find_video_file(srt_path: Path) -> Optional[Path]:
    """Find video file corresponding to SRT file.

    Args:
        srt_path: Path to SRT file

    Returns:
        Path to video file or None
    """
    parent_dir = srt_path.parent
    base_name = srt_path.stem

    # Common video extensions
    video_extensions = [".mkv", ".mp4", ".avi", ".m4v", ".mov", ".wmv"]

    # Try exact match first
    for ext in video_extensions:
        candidate = parent_dir / f"{base_name}{ext}"
        if candidate.exists():
            return candidate

    # Try removing language codes
    if "_" in base_name:
        base_clean = base_name.split("_")[0]
        for ext in video_extensions:
            candidate = parent_dir / f"{base_clean}{ext}"
            if candidate.exists():
                return candidate

    # Look for any video in same directory
    for ext in video_extensions:
        videos = list(parent_dir.glob(f"*{ext}"))
        if videos:
            return videos[0]

    return None


def main():
    """CLI entry point for clip extraction."""
    import argparse

    parser = argparse.ArgumentParser(description="Extract video clips from movies")
    parser.add_argument("--query", required=True, help="Text to search for")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--duration", type=int, default=10, help="Clip duration in seconds")

    args = parser.parse_args()

    output_path = extract_clip(
        query=args.query,
        output_dir=Path(args.output),
        duration=args.duration
    )

    if output_path:
        print(json.dumps({"clip_path": str(output_path)}))
    else:
        print(json.dumps({"error": "Failed to extract clip"}))
        exit(1)


if __name__ == "__main__":
    main()