"""Watch command for consume-movie.

Primary entry point for "watching" a movie with book context.
Loads related book notes before presenting movie content.
"""

import json
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm

# Handle both direct execution and package import
try:
    from .book_context import (
        get_book_notes,
        get_book_context_for_scene,
        display_book_context,
        find_related_books,
        fetch_book_reviews,
        fetch_movie_reviews,
        fetch_adaptation_comparison,
        display_reviews,
        acquire_missing_books,
        display_missing_books,
    )
    from .search import search_subtitles, find_srt_file
except ImportError:
    from book_context import (
        get_book_notes,
        get_book_context_for_scene,
        display_book_context,
        find_related_books,
        fetch_book_reviews,
        fetch_movie_reviews,
        fetch_adaptation_comparison,
        display_reviews,
        acquire_missing_books,
        display_missing_books,
    )
    from search import search_subtitles, find_srt_file

console = Console()


def watch_movie(
    movie_id: str,
    with_book_context: bool = True,
    with_reviews: bool = False,
    acquire_books: bool = False,
    book_id: Optional[str] = None,
    registry_path: Optional[Path] = None,
    interactive: bool = True,
) -> dict[str, Any]:
    """Watch a movie with optional book context and reviews.

    This is the main entry point for consuming a movie after reading the book.
    It loads book notes and external reviews to provide rich context.

    Args:
        movie_id: Movie ID from registry
        with_book_context: Whether to load book context (default: True)
        with_reviews: Whether to fetch external reviews via dogpile (default: False)
        book_id: Specific book ID to use for context (auto-detect if None)
        registry_path: Override registry path
        interactive: Whether to prompt for user input

    Returns:
        Session info dict
    """
    from consume_common.registry import ContentRegistry

    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-movie" / "registry.json"

    # Load movie from registry
    registry = ContentRegistry(registry_path)
    movie = registry.get_content(movie_id)

    if not movie:
        console.print(f"[red]Movie {movie_id} not found in registry[/red]")
        console.print("Run './run.sh sync' to import from ingest-movie")
        return {"error": "Movie not found"}

    movie_title = movie.get("title", "Unknown Movie")
    source_path = Path(movie.get("source_path", ""))

    console.print(Panel(
        f"[bold]{movie_title}[/bold]\n"
        f"ID: {movie_id[:8]}...\n"
        f"Source: {source_path.name if source_path else 'Unknown'}",
        title="Now Watching",
        border_style="blue"
    ))

    session = {
        "movie_id": movie_id,
        "movie_title": movie_title,
        "book_context_loaded": False,
        "book_notes_count": 0,
        "related_books": [],
        "reviews_loaded": False,
    }

    # Load book context if requested
    book_context = None
    if with_book_context:
        console.print("\n[cyan]Loading book context...[/cyan]")

        book_context = get_book_notes(movie_title)

        if book_context.get("has_context"):
            session["book_context_loaded"] = True
            session["book_notes_count"] = len(book_context.get("book_notes", []))
            session["related_books"] = [b["title"] for b in book_context.get("related_books", [])]

            # Display the book context
            display_book_context(book_context)

            if interactive:
                console.print("\n[dim]Book context loaded. Your reading notes will be shown alongside movie scenes.[/dim]")
        else:
            # No local book context - search Readarr for missing books
            console.print("\n[cyan]Checking Readarr for related books...[/cyan]")
            acquisition = acquire_missing_books(movie_title, auto_acquire=acquire_books)

            if acquisition.get("missing_books"):
                display_missing_books(acquisition, prompt_add=interactive)

                # If books were acquired, reload context
                if acquisition.get("acquired_books"):
                    console.print("\n[green]Reloading book context after acquisition...[/green]")
                    book_context = get_book_notes(movie_title)
                    if book_context.get("has_context"):
                        session["book_context_loaded"] = True
                        session["book_notes_count"] = len(book_context.get("book_notes", []))
                        display_book_context(book_context)

                # Display fallback reviews if books unavailable
                if acquisition.get("fallback_reviews") and acquisition["fallback_reviews"].get("has_reviews"):
                    console.print("\n[cyan]Using movie reviews as fallback context:[/cyan]")
                    display_reviews({}, acquisition["fallback_reviews"], {})
                    session["reviews_loaded"] = True
            else:
                console.print(Panel(
                    "[yellow]No book context found for this movie.[/yellow]\n\n"
                    "To add book context:\n"
                    "1. Acquire the book:\n"
                    "   cd .pi/skills/ingest-book && ./run.sh add \"BOOK_TITLE\"\n\n"
                    "2. Read and take notes:\n"
                    "   cd .pi/skills/consume-book\n"
                    "   ./run.sh sync\n"
                    "   ./run.sh note --book <id> --char-position N --note \"insight\"\n\n"
                    "3. Then watch again with context:\n"
                    "   ./run.sh watch --movie <id> --with-book-context",
                    title="No Book Context",
                    border_style="yellow"
                ))
    else:
        console.print("\n[dim]Watching without book context. Add --with-book-context to include reading notes.[/dim]")

    # Fetch external reviews via dogpile if requested
    if with_reviews:
        console.print("\n[cyan]Fetching external reviews via /dogpile...[/cyan]")

        # Fetch movie reviews
        movie_reviews = fetch_movie_reviews(movie_title)

        # Fetch book reviews if we have related books
        book_reviews = {"has_reviews": False}
        comparison = {"has_comparison": False}

        if session["related_books"]:
            # Use the first related book for reviews
            book_title = session["related_books"][0]
            book_reviews = fetch_book_reviews(book_title)

            # Fetch adaptation comparison
            comparison = fetch_adaptation_comparison(book_title, movie_title)

        # Display the reviews
        display_reviews(book_reviews, movie_reviews, comparison)
        session["reviews_loaded"] = True

    # Show available actions
    console.print("\n[bold]Available Actions:[/bold]")
    console.print("  search <query>  - Search scenes in this movie")
    console.print("  note <text>     - Add a note at current position")
    console.print("  clip <time>     - Extract a video clip")
    console.print("")

    return session


def watch_with_search(
    movie_id: str,
    query: str,
    with_book_context: bool = True,
    registry_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Search movie scenes with book context annotations.

    Args:
        movie_id: Movie ID from registry
        query: Search query
        with_book_context: Whether to annotate with book notes
        registry_path: Override registry path

    Returns:
        Search results with book annotations
    """
    from consume_common.registry import ContentRegistry

    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-movie" / "registry.json"

    # Get movie title for book context
    registry = ContentRegistry(registry_path)
    movie = registry.get_content(movie_id)

    if not movie:
        console.print(f"[red]Movie {movie_id} not found[/red]")
        return []

    movie_title = movie.get("title", "Unknown")

    # Load book context
    book_context = None
    if with_book_context:
        console.print(f"[cyan]Loading book context for: {movie_title}[/cyan]")
        book_context = get_book_notes(movie_title)

        if book_context.get("has_context"):
            console.print(f"[green]Found {len(book_context.get('book_notes', []))} book notes[/green]")
        else:
            console.print("[yellow]No book context available[/yellow]")

    # Search subtitles
    results = search_subtitles(
        query=query,
        movie_id=movie_id,
        with_book_context=with_book_context,
        registry_path=registry_path
    )

    return results


def main():
    """CLI entry point for watch command."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Watch a movie with book context",
        epilog="""
Examples:
  ./run.sh watch --movie abc123 --with-book-context
  ./run.sh watch --movie abc123 --search "fear"
  ./run.sh watch --list
"""
    )

    parser.add_argument("--movie", "-m", help="Movie ID to watch")
    parser.add_argument("--with-book-context", action="store_true", default=True,
                       help="Load notes from related book (default: on)")
    parser.add_argument("--no-book-context", action="store_true",
                       help="Watch without book context")
    parser.add_argument("--with-reviews", action="store_true",
                       help="Fetch external reviews via /dogpile")
    parser.add_argument("--acquire-books", action="store_true",
                       help="Auto-add missing books to Readarr")
    parser.add_argument("--book", "-b", help="Specific book ID for context")
    parser.add_argument("--search", "-s", help="Search for scenes matching query")
    parser.add_argument("--list", "-l", action="store_true", help="List available movies")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    # Handle --list
    if args.list:
        from consume_common.registry import ContentRegistry
        registry_path = Path.home() / ".pi" / "consume-movie" / "registry.json"
        registry = ContentRegistry(registry_path)
        movies = registry.list_content("movie")

        if args.json:
            print(json.dumps({"movies": movies}, indent=2))
        else:
            if not movies:
                console.print("[yellow]No movies in registry. Run './run.sh sync' first.[/yellow]")
                return

            table = Table(title="Available Movies")
            table.add_column("ID", style="cyan", no_wrap=True)
            table.add_column("Title", style="green")
            table.add_column("Book Context?", justify="center")

            for movie in movies:
                movie_title = movie.get("title", "Unknown")
                related_books = find_related_books(movie_title)
                has_books = "Yes" if related_books else "-"
                table.add_row(
                    movie["content_id"][:8] + "...",
                    movie_title,
                    has_books
                )

            console.print(table)
        return

    # Require movie ID for other operations
    if not args.movie:
        console.print("[red]Please specify --movie <id>[/red]")
        console.print("Use --list to see available movies")
        return

    with_book_context = args.with_book_context and not args.no_book_context

    # Handle search
    if args.search:
        results = watch_with_search(
            movie_id=args.movie,
            query=args.search,
            with_book_context=with_book_context,
        )

        if args.json:
            print(json.dumps({"results": results}, indent=2))
        return

    # Default: watch session
    session = watch_movie(
        movie_id=args.movie,
        with_book_context=with_book_context,
        with_reviews=args.with_reviews,
        acquire_books=args.acquire_books,
        book_id=args.book,
        interactive=not args.json,
    )

    if args.json:
        print(json.dumps(session, indent=2))


if __name__ == "__main__":
    main()
