"""Subtitle search functionality for consume-movie."""

import json
import srt
from pathlib import Path
from typing import Any, Optional
from rich.console import Console

# Handle both direct execution and package import
try:
    from .book_context import get_book_notes, get_book_context_for_scene, display_book_context
except ImportError:
    from book_context import get_book_notes, get_book_context_for_scene, display_book_context

console = Console()


def search_subtitles(
    query: str,
    movie_id: Optional[str] = None,
    context_seconds: int = 5,
    registry_path: Optional[Path] = None,
    with_book_context: bool = False,
) -> list[dict[str, Any]]:
    """Search for text in movie subtitles.

    Args:
        query: Text to search for
        movie_id: Specific movie ID (None to search all)
        context_seconds: Seconds of context before/after
        registry_path: Override registry path
        with_book_context: Load and display related book notes

    Returns:
        List of search results
    """
    from consume_common.registry import ContentRegistry

    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-movie" / "registry.json"

    registry = ContentRegistry(registry_path)

    # Get movies to search
    if movie_id:
        movies = [registry.get_content(movie_id)]
        if not movies[0]:
            console.print(f"[red]Movie {movie_id} not found[/red]")
            return []
    else:
        movies = registry.list_content("movie")

    results = []
    query_lower = query.lower()
    book_contexts = {}  # Cache book context per movie

    for movie in movies:
        if not movie or not movie.get("source_path"):
            continue

        source_path = Path(movie["source_path"])
        if not source_path.exists():
            console.print(f"[yellow]Source not found: {source_path}[/yellow]")
            continue

        # Find corresponding SRT file
        srt_path = find_srt_file(source_path)
        if not srt_path:
            console.print(f"[yellow]No SRT file found for {movie['title']}[/yellow]")
            continue

        # Search in SRT
        try:
            with open(srt_path, "r", encoding="utf-8") as f:
                srt_content = f.read()

            subtitles = list(srt.parse(srt_content))

            for subtitle in subtitles:
                if query_lower in subtitle.content.lower():
                    # Calculate context
                    context_start = max(0, subtitle.start.total_seconds() - context_seconds)
                    context_end = subtitle.end.total_seconds() + context_seconds

                    # Get context text
                    context_before = ""
                    context_after = ""
                    for sub in subtitles:
                        if sub.end.total_seconds() <= subtitle.start.total_seconds() and sub.end.total_seconds() >= context_start:
                            context_before += sub.content + " "
                        if sub.start.total_seconds() >= subtitle.end.total_seconds() and sub.start.total_seconds() <= context_end:
                            context_after += sub.content + " "

                    result = {
                        "movie_id": movie["content_id"],
                        "movie_title": movie["title"],
                        "start": subtitle.start.total_seconds(),
                        "end": subtitle.end.total_seconds(),
                        "text": subtitle.content,
                        "context_before": context_before.strip(),
                        "context_after": context_after.strip(),
                        "srt_path": str(srt_path)
                    }

                    # Add book context if requested
                    if with_book_context:
                        movie_title = movie["title"]
                        if movie_title not in book_contexts:
                            book_contexts[movie_title] = get_book_notes(movie_title)

                        scene_context = get_book_context_for_scene(
                            movie_title,
                            subtitle.content,
                            book_contexts[movie_title]
                        )
                        result["book_context"] = {
                            "characters_in_scene": scene_context.get("characters_in_scene", []),
                            "relevant_notes": [
                                {"note": n["note"], "book_title": n["book_title"]}
                                for n in scene_context.get("relevant_notes", [])[:3]
                            ],
                        }

                    results.append(result)

        except Exception as e:
            console.print(f"[red]Error processing {srt_path}: {e}[/red]")
            continue

    console.print(f"[green]Found {len(results)} matches for '{query}'[/green]")
    return results


def find_srt_file(source_path: Path) -> Optional[Path]:
    """Find SRT file corresponding to a transcript JSON file.

    Args:
        source_path: Path to transcript JSON file

    Returns:
        Path to SRT file or None
    """
    # Look for SRT files with same base name
    base_name = source_path.stem
    parent_dir = source_path.parent

    # Try various SRT naming patterns
    candidates = [
        parent_dir / f"{base_name}.srt",
        parent_dir / f"{base_name}.en.srt",
        parent_dir / f"{base_name}.english.srt",
        parent_dir / f"{base_name}_en.srt",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    # Look for any SRT in the same directory
    srt_files = list(parent_dir.glob("*.srt"))
    if srt_files:
        return srt_files[0]

    return None


def main():
    """CLI entry point for search."""
    import argparse

    parser = argparse.ArgumentParser(description="Search movie subtitles")
    parser.add_argument("query", help="Text to search for")
    parser.add_argument("--movie", help="Specific movie ID")
    parser.add_argument("--context", type=int, default=5, help="Context seconds (default: 5)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--with-book-context", action="store_true",
                       help="Load notes from related book for context")

    args = parser.parse_args()

    # Display book context header if requested
    if args.with_book_context and not args.json:
        console.print("\n[bold cyan]Loading book context...[/bold cyan]")

    results = search_subtitles(
        query=args.query,
        movie_id=args.movie,
        context_seconds=args.context,
        with_book_context=args.with_book_context
    )

    if args.json:
        print(json.dumps({"results": results}, indent=2))
    else:
        if not results:
            console.print("[yellow]No matches found[/yellow]")
            return

        for result in results:
            console.print(f"\n[bold]{result['movie_title']}[/bold]")
            console.print(f"  Time: {result['start']:.1f}s - {result['end']:.1f}s")
            console.print(f"  Text: {result['text']}")
            if result['context_before']:
                console.print(f"  Before: {result['context_before']}")
            if result['context_after']:
                console.print(f"  After: {result['context_after']}")

            # Display book context if available
            if "book_context" in result:
                book_ctx = result["book_context"]
                if book_ctx.get("characters_in_scene"):
                    console.print(f"  [cyan]Characters (from book):[/cyan] {', '.join(book_ctx['characters_in_scene'])}")
                if book_ctx.get("relevant_notes"):
                    console.print(f"  [cyan]Book notes:[/cyan]")
                    for note in book_ctx["relevant_notes"]:
                        console.print(f"    - [{note['book_title']}] {note['note'][:80]}...")


if __name__ == "__main__":
    main()