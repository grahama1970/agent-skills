"""Transcript search functionality for consume-youtube."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rich.console import Console

from consume_common.registry import ContentRegistry

console = Console()


def search_transcripts(
    query: str,
    channel: Optional[str] = None,
    video_id: Optional[str] = None,
    context_segments: int = 1,
    registry_path: Optional[Path] = None
) -> list[dict[str, object]]:
    """Search for text in YouTube transcripts."""
    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-youtube" / "registry.json"

    registry = ContentRegistry(registry_path)
    videos = registry.list_content("youtube")

    if channel:
        videos = [v for v in videos if v.get("metadata", {}).get("channel") == channel]
    if video_id:
        videos = [v for v in videos if v.get("metadata", {}).get("video_id") == video_id]

    results: list[dict[str, object]] = []
    query_lower = query.lower()

    for video in videos:
        source_path = video.get("source_path")
        if not source_path:
            continue

        transcript_path = Path(source_path)
        if not transcript_path.exists():
            continue

        try:
            data = json.loads(transcript_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue

        transcript = data.get("transcript", []) if isinstance(data, dict) else []

        for index, segment in enumerate(transcript):
            text = str(segment.get("text", ""))
            if query_lower not in text.lower():
                continue

            start = float(segment.get("start", 0))
            context_before = _collect_context(transcript, index - context_segments, index)
            context_after = _collect_context(transcript, index + 1, index + 1 + context_segments)

            results.append({
                "video_id": video.get("metadata", {}).get("video_id"),
                "video_title": video.get("title", "Unknown"),
                "channel": video.get("metadata", {}).get("channel"),
                "start": start,
                "duration": float(segment.get("duration", 0)),
                "text": text,
                "context_before": context_before,
                "context_after": context_after,
            })

    console.print(f"[green]Found {len(results)} matches for '{query}'[/green]")
    return results


def _collect_context(transcript: list[dict], start: int, end: int) -> str:
    start = max(0, start)
    end = min(len(transcript), end)
    parts: list[str] = []
    for i in range(start, end):
        text = str(transcript[i].get("text", "")).strip()
        if text:
            parts.append(text)
    return " ".join(parts)


def main() -> None:
    """CLI entry point for search."""
    import argparse

    parser = argparse.ArgumentParser(description="Search YouTube transcripts")
    parser.add_argument("query", help="Text to search for")
    parser.add_argument("--channel", help="Channel name")
    parser.add_argument("--video", help="Video ID")
    parser.add_argument("--context", type=int, default=1, help="Context segments (default: 1)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    results = search_transcripts(
        query=args.query,
        channel=args.channel,
        video_id=args.video,
        context_segments=args.context,
    )

    if args.json:
        print(json.dumps({"results": results}, indent=2))
    else:
        if not results:
            console.print("[yellow]No matches found[/yellow]")
            return

        for result in results:
            console.print(f"\n[bold]{result['video_title']}[/bold]")
            console.print(f"  Channel: {result['channel']}")
            console.print(f"  Time: {result['start']:.1f}s")
            console.print(f"  Text: {result['text']}")
            if result["context_before"]:
                console.print(f"  Before: {result['context_before']}")
            if result["context_after"]:
                console.print(f"  After: {result['context_after']}")


if __name__ == "__main__":
    main()
