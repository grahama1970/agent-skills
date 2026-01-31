"""Book context integration for consume-movie.

Queries consume-book for related notes, fetches reviews via dogpile,
and provides context before watching/processing movie content.
"""

import json
import os
import re
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# Paths to related skills
SKILLS_DIR = Path(__file__).resolve().parent.parent
DOGPILE_DIR = SKILLS_DIR / "dogpile"
INGEST_BOOK_DIR = SKILLS_DIR / "ingest-book"

def run_dogpile(query: str, preset: str = "general", timeout_sec: int = 120) -> dict[str, Any]:
    """Run dogpile search for reviews and context.

    Args:
        query: Search query
        preset: Dogpile preset (general, book_reviews, movie_scenes)
        timeout_sec: Timeout in seconds

    Returns:
        Dict with results or error
    """
    # Try multiple possible dogpile locations
    dogpile_candidates = [
        DOGPILE_DIR / "dogpile.py",
        DOGPILE_DIR / "dogpile_monolith.py",
        DOGPILE_DIR / "cli.py",
        SKILLS_DIR.parent / ".agent" / "skills" / "dogpile" / "dogpile_monolith.py",
    ]

    dogpile_script = None
    for candidate in dogpile_candidates:
        if candidate.exists():
            dogpile_script = candidate
            break

    if not dogpile_script:
        return {"error": "Dogpile not found", "status": "not_found"}

    cmd = [
        sys.executable, str(dogpile_script),
        "search", query,
        "--preset", preset,
        "--no-interactive"
    ]

    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(dogpile_script.parent),
            start_new_session=True,
        )

        try:
            stdout, stderr = proc.communicate(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            except Exception:
                proc.terminate()
            proc.wait(timeout=5)
            return {"error": f"Dogpile timed out after {timeout_sec}s", "status": "timeout"}

        if proc.returncode == 0:
            try:
                return json.loads(stdout)
            except json.JSONDecodeError:
                return {"raw_output": stdout, "status": "success"}
        else:
            return {"error": stderr or "Unknown error", "status": "failed"}

    except Exception as e:
        return {"error": str(e), "status": "exception"}


def fetch_book_reviews(book_title: str) -> dict[str, Any]:
    """Fetch reviews for a book via dogpile.

    Args:
        book_title: Book title to search for

    Returns:
        Dict with reviews and summary
    """
    query = f'"{book_title}" book review analysis themes'
    console.print(f"[dim]Fetching book reviews for: {book_title}[/dim]")

    results = run_dogpile(query, preset="general", timeout_sec=60)

    return {
        "book_title": book_title,
        "query": query,
        "results": results,
        "has_reviews": results.get("status") == "success" or "raw_output" in results,
    }


def fetch_movie_reviews(movie_title: str) -> dict[str, Any]:
    """Fetch reviews for a movie via dogpile.

    Args:
        movie_title: Movie title to search for

    Returns:
        Dict with reviews and summary
    """
    query = f'"{movie_title}" movie review analysis adaptation comparison'
    console.print(f"[dim]Fetching movie reviews for: {movie_title}[/dim]")

    results = run_dogpile(query, preset="general", timeout_sec=60)

    return {
        "movie_title": movie_title,
        "query": query,
        "results": results,
        "has_reviews": results.get("status") == "success" or "raw_output" in results,
    }


def fetch_adaptation_comparison(book_title: str, movie_title: str) -> dict[str, Any]:
    """Fetch comparison reviews between book and movie adaptation.

    Args:
        book_title: Book title
        movie_title: Movie title

    Returns:
        Dict with comparison analysis
    """
    query = f'"{book_title}" "{movie_title}" book vs movie adaptation differences comparison'
    console.print(f"[dim]Fetching adaptation comparison...[/dim]")

    results = run_dogpile(query, preset="general", timeout_sec=90)

    return {
        "book_title": book_title,
        "movie_title": movie_title,
        "query": query,
        "results": results,
        "has_comparison": results.get("status") == "success" or "raw_output" in results,
    }


def search_readarr(query: str, timeout_sec: int = 30) -> dict[str, Any]:
    """Search for a book in Readarr.

    Args:
        query: Book title or author to search for
        timeout_sec: Timeout in seconds

    Returns:
        Dict with search results or error
    """
    run_script = INGEST_BOOK_DIR / "run.sh"
    if not run_script.exists():
        return {"error": "ingest-book skill not found", "status": "not_found", "results": []}

    cmd = ["bash", str(run_script), "search", query]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=str(INGEST_BOOK_DIR),
        )

        if result.returncode == 0:
            # Parse output - typically formatted text, extract book info
            return {
                "query": query,
                "raw_output": result.stdout,
                "status": "success",
                "results": _parse_readarr_search(result.stdout),
            }
        else:
            return {
                "error": result.stderr or "Search failed",
                "status": "failed",
                "results": [],
            }

    except subprocess.TimeoutExpired:
        return {"error": f"Readarr search timed out after {timeout_sec}s", "status": "timeout", "results": []}
    except Exception as e:
        return {"error": str(e), "status": "exception", "results": []}


def _parse_readarr_search(output: str) -> list[dict[str, str]]:
    """Parse Readarr search output into structured results.

    Args:
        output: Raw output from readarr search command

    Returns:
        List of book dicts with title, author, id
    """
    results = []
    lines = output.strip().split("\n")

    # Parse table-like output from Readarr
    for line in lines:
        # Skip header/separator lines
        if not line.strip() or line.startswith("─") or line.startswith("│"):
            continue
        if "Title" in line and "Author" in line:
            continue

        # Try to extract book info from formatted output
        parts = [p.strip() for p in line.split("│") if p.strip()]
        if len(parts) >= 2:
            results.append({
                "title": parts[0] if len(parts) > 0 else "",
                "author": parts[1] if len(parts) > 1 else "",
                "id": parts[2] if len(parts) > 2 else "",
            })

    return results


def add_book_to_readarr(query: str, timeout_sec: int = 60) -> dict[str, Any]:
    """Add a book to Readarr library.

    Args:
        query: Book title to search and add
        timeout_sec: Timeout in seconds

    Returns:
        Dict with result status
    """
    run_script = INGEST_BOOK_DIR / "run.sh"
    if not run_script.exists():
        return {"error": "ingest-book skill not found", "status": "not_found"}

    cmd = ["bash", str(run_script), "add", query]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=str(INGEST_BOOK_DIR),
        )

        if result.returncode == 0:
            return {
                "query": query,
                "raw_output": result.stdout,
                "status": "success",
                "added": True,
            }
        else:
            return {
                "error": result.stderr or result.stdout or "Add failed",
                "status": "failed",
                "added": False,
            }

    except subprocess.TimeoutExpired:
        return {"error": f"Readarr add timed out after {timeout_sec}s", "status": "timeout", "added": False}
    except Exception as e:
        return {"error": str(e), "status": "exception", "added": False}


def retrieve_and_extract_book(query: str, timeout_sec: int = 300) -> dict[str, Any]:
    """Retrieve a book from Readarr and extract via /extractor.

    This is the full pipeline: search -> download -> extract content.

    Args:
        query: Book title to retrieve
        timeout_sec: Timeout in seconds (longer for download + extraction)

    Returns:
        Dict with result status and extracted content path
    """
    run_script = INGEST_BOOK_DIR / "run.sh"
    if not run_script.exists():
        return {"error": "ingest-book skill not found", "status": "not_found"}

    cmd = ["bash", str(run_script), "retrieve", query]
    console.print(f"[dim]Retrieving and extracting: {query}[/dim]")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=str(INGEST_BOOK_DIR),
        )

        if result.returncode == 0:
            return {
                "query": query,
                "raw_output": result.stdout,
                "status": "success",
                "retrieved": True,
            }
        else:
            return {
                "error": result.stderr or result.stdout or "Retrieve failed",
                "status": "failed",
                "retrieved": False,
            }

    except subprocess.TimeoutExpired:
        return {"error": f"Retrieve timed out after {timeout_sec}s", "status": "timeout", "retrieved": False}
    except Exception as e:
        return {"error": str(e), "status": "exception", "retrieved": False}


def acquire_missing_books(
    movie_title: str,
    auto_acquire: bool = False,
    book_registry_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Check for missing books and optionally acquire them via Readarr.

    If books cannot be found in Readarr, falls back to dogpile movie reviews.

    Args:
        movie_title: Movie title to find related books for
        auto_acquire: If True, automatically retrieve and extract missing books
        book_registry_path: Path to consume-book registry

    Returns:
        Dict with missing books, acquisition status, and fallback reviews
    """
    if not book_registry_path:
        book_registry_path = Path.home() / ".pi" / "consume-book" / "registry.json"

    result = {
        "movie_title": movie_title,
        "suggested_books": [],
        "local_books": [],
        "missing_books": [],
        "readarr_results": [],
        "acquired_books": [],
        "unavailable_books": [],
        "fallback_reviews": None,
    }

    # Get suggested books for this movie
    related_patterns = find_related_books(movie_title)
    result["suggested_books"] = related_patterns

    # Check what's already local
    local_titles = set()
    if book_registry_path.exists():
        try:
            from consume_common.registry import ContentRegistry
            registry = ContentRegistry(book_registry_path)
            books = registry.list_content("book")
            for book in books:
                local_titles.add(book.get("title", "").lower())
                result["local_books"].append(book.get("title"))
        except Exception:
            pass

    # Find missing books
    for pattern in related_patterns:
        is_local = any(pattern in title or title in pattern for title in local_titles)
        if not is_local:
            result["missing_books"].append(pattern)

    # Search/acquire missing books via Readarr
    if result["missing_books"]:
        console.print(f"\n[cyan]Searching Readarr for {len(result['missing_books'])} missing book(s)...[/cyan]")

        for book_pattern in result["missing_books"]:
            console.print(f"  Searching: {book_pattern}")
            search_result = search_readarr(book_pattern)
            found = len(search_result.get("results", [])) > 0

            result["readarr_results"].append({
                "query": book_pattern,
                "found": found,
                "results": search_result.get("results", [])[:3],
                "status": search_result.get("status"),
            })

            if found and auto_acquire:
                # Use retrieve which handles download + extraction
                console.print(f"    [green]Retrieving and extracting via /ingest-book...[/green]")
                retrieve_result = retrieve_and_extract_book(book_pattern)
                if retrieve_result.get("retrieved"):
                    result["acquired_books"].append(book_pattern)
                    console.print(f"    [green]✓ Acquired: {book_pattern}[/green]")
                else:
                    result["unavailable_books"].append(book_pattern)
                    console.print(f"    [yellow]Failed: {retrieve_result.get('error')}[/yellow]")
            elif not found:
                result["unavailable_books"].append(book_pattern)

    # Fallback: if books unavailable, fetch movie reviews via dogpile
    if result["unavailable_books"]:
        console.print(f"\n[yellow]Some books unavailable. Falling back to movie reviews...[/yellow]")
        result["fallback_reviews"] = fetch_movie_reviews(movie_title)

    return result


def display_missing_books(acquisition_result: dict[str, Any], prompt_add: bool = True) -> None:
    """Display missing books and optionally prompt to add them.

    Args:
        acquisition_result: Result from acquire_missing_books()
        prompt_add: Whether to prompt user to add books
    """
    if not acquisition_result.get("missing_books"):
        return

    lines = []
    lines.append("[bold yellow]Missing Books for Context:[/bold yellow]")
    lines.append("")

    for i, book in enumerate(acquisition_result["missing_books"], 1):
        readarr_info = next(
            (r for r in acquisition_result.get("readarr_results", []) if r["query"] == book),
            None
        )

        if readarr_info and readarr_info.get("found"):
            lines.append(f"  {i}. {book.title()} [green](available in Readarr)[/green]")
            for result in readarr_info.get("results", [])[:2]:
                lines.append(f"      → {result.get('title', 'Unknown')} by {result.get('author', 'Unknown')}")
        else:
            lines.append(f"  {i}. {book.title()} [dim](not found in Readarr)[/dim]")

    lines.append("")
    lines.append("[dim]To acquire these books:[/dim]")
    lines.append("  cd .pi/skills/ingest-book && ./run.sh add \"BOOK_TITLE\"")

    console.print(Panel(
        "\n".join(lines),
        title="Suggested Reading Before Watching",
        border_style="yellow"
    ))


def display_reviews(book_reviews: dict, movie_reviews: dict, comparison: dict) -> None:
    """Display fetched reviews in formatted panels.

    Args:
        book_reviews: Book review results
        movie_reviews: Movie review results
        comparison: Adaptation comparison results
    """
    lines = []

    # Book reviews
    if book_reviews.get("has_reviews"):
        lines.append("[bold cyan]Book Reviews:[/bold cyan]")
        raw = book_reviews.get("results", {}).get("raw_output", "")
        if raw:
            # Truncate and format
            lines.append(f"  {raw[:500]}...")
        lines.append("")

    # Movie reviews
    if movie_reviews.get("has_reviews"):
        lines.append("[bold cyan]Movie Reviews:[/bold cyan]")
        raw = movie_reviews.get("results", {}).get("raw_output", "")
        if raw:
            lines.append(f"  {raw[:500]}...")
        lines.append("")

    # Adaptation comparison
    if comparison.get("has_comparison"):
        lines.append("[bold cyan]Book vs Movie Comparison:[/bold cyan]")
        raw = comparison.get("results", {}).get("raw_output", "")
        if raw:
            lines.append(f"  {raw[:500]}...")

    if lines:
        console.print(Panel(
            "\n".join(lines),
            title="External Reviews (via /dogpile)",
            border_style="magenta"
        ))
    else:
        console.print("[dim]No external reviews found[/dim]")


# Known book-to-movie mappings for automatic matching
BOOK_MOVIE_MAP = {
    # Movie title patterns -> Book titles
    "dune": ["dune", "dune messiah"],
    "godfather": ["the godfather"],
    "there will be blood": ["oil!"],
    "apocalypse now": ["heart of darkness"],
    "blade runner": ["do androids dream of electric sheep"],
    "no country for old men": ["no country for old men", "blood meridian"],
    "the road": ["the road"],
    "gladiator": ["those about to die"],
    "fury": ["death traps", "with the old breed"],
    "saving private ryan": ["citizen soldiers", "band of brothers"],
    "band of brothers": ["band of brothers"],
    "the last samurai": ["shogun"],
    "game of thrones": ["a game of thrones", "a song of ice and fire"],
    "lord of the rings": ["the lord of the rings", "the fellowship of the ring"],
    "harry potter": ["harry potter"],
    "fight club": ["fight club"],
    "shawshank": ["rita hayworth and shawshank redemption"],
    "silence of the lambs": ["the silence of the lambs"],
    "jurassic park": ["jurassic park"],
    "the shining": ["the shining"],
    "misery": ["misery"],
    "it": ["it"],
    "stand by me": ["the body"],
    "children of dune": ["children of dune"],
    "foundation": ["foundation"],
    "ender": ["ender's game"],
    "starship troopers": ["starship troopers"],
    "the expanse": ["leviathan wakes", "the expanse"],
    # Warhammer 40k
    "horus": ["horus rising", "horus heresy"],
    "eisenhorn": ["eisenhorn", "xenos"],
    "gaunt": ["gaunt's ghosts", "first and only"],
}


def find_related_books(movie_title: str) -> list[str]:
    """Find book titles that might be related to a movie.

    Args:
        movie_title: Movie title to search for

    Returns:
        List of potentially related book title patterns
    """
    movie_lower = movie_title.lower()
    related = []

    for pattern, books in BOOK_MOVIE_MAP.items():
        if pattern in movie_lower or movie_lower in pattern:
            related.extend(books)

    # Also add the movie title itself as a potential book match
    # (many books share titles with their adaptations)
    related.append(movie_lower)

    return list(set(related))


def get_book_notes(
    movie_title: str,
    book_registry_path: Optional[Path] = None,
    book_notes_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Get notes from related books for a movie.

    Args:
        movie_title: Movie title to find book context for
        book_registry_path: Path to consume-book registry
        book_notes_dir: Path to consume-book notes directory

    Returns:
        Dict with book context including notes, characters, themes
    """
    if not book_registry_path:
        book_registry_path = Path.home() / ".pi" / "consume-book" / "registry.json"
    if not book_notes_dir:
        book_notes_dir = Path.home() / ".pi" / "consume-book" / "notes"

    context = {
        "movie_title": movie_title,
        "related_books": [],
        "book_notes": [],
        "characters": [],
        "themes": [],
        "key_quotes": [],
        "has_context": False,
    }

    # Find related book patterns
    related_patterns = find_related_books(movie_title)

    if not book_registry_path.exists():
        console.print("[yellow]No consume-book registry found[/yellow]")
        return context

    # Load book registry
    try:
        from consume_common.registry import ContentRegistry
        registry = ContentRegistry(book_registry_path)
        books = registry.list_content("book")
    except Exception as e:
        console.print(f"[yellow]Could not load book registry: {e}[/yellow]")
        return context

    # Find matching books
    matched_books = []
    for book in books:
        book_title = book.get("title", "").lower()
        for pattern in related_patterns:
            if pattern in book_title or book_title in pattern:
                matched_books.append(book)
                context["related_books"].append({
                    "book_id": book["content_id"],
                    "title": book.get("title"),
                    "source_path": book.get("source_path"),
                })
                break

    if not matched_books:
        return context

    # Load notes for matched books
    try:
        from consume_common.notes import HorusNotesManager
        notes_manager = HorusNotesManager(book_notes_dir)

        for book in matched_books:
            book_notes = notes_manager.list_notes(content_id=book["content_id"])
            for note in book_notes:
                context["book_notes"].append({
                    "book_title": book.get("title"),
                    "book_id": book["content_id"],
                    "note": note.get("note", ""),
                    "position": note.get("position", {}),
                    "agent_id": note.get("agent_id"),
                    "timestamp": note.get("timestamp"),
                })

                # Extract characters and themes from notes
                note_text = note.get("note", "").lower()

                # Simple heuristic: capitalized words might be character names
                words = note.get("note", "").split()
                for word in words:
                    if word[0].isupper() and len(word) > 2 and word not in ["The", "And", "But", "For"]:
                        clean = re.sub(r'[^\w]', '', word)
                        if clean and clean not in context["characters"]:
                            context["characters"].append(clean)

                # Look for theme keywords
                theme_keywords = ["loyalty", "betrayal", "power", "fear", "love", "death",
                                 "honor", "revenge", "family", "duty", "sacrifice", "ambition"]
                for keyword in theme_keywords:
                    if keyword in note_text and keyword not in context["themes"]:
                        context["themes"].append(keyword)

    except Exception as e:
        console.print(f"[yellow]Could not load book notes: {e}[/yellow]")

    context["has_context"] = len(context["book_notes"]) > 0
    return context


def display_book_context(context: dict[str, Any]) -> None:
    """Display book context in a formatted panel.

    Args:
        context: Book context dict from get_book_notes()
    """
    if not context.get("has_context"):
        console.print(Panel(
            "[yellow]No book context available.[/yellow]\n"
            "Consider reading the source material first:\n"
            "  cd .pi/skills/consume-book\n"
            "  ./run.sh sync\n"
            "  ./run.sh search \"<character>\"",
            title="Book Context",
            border_style="yellow"
        ))
        return

    # Build context display
    lines = []

    # Related books
    if context["related_books"]:
        lines.append("[bold cyan]Related Books:[/bold cyan]")
        for book in context["related_books"]:
            lines.append(f"  - {book['title']}")
        lines.append("")

    # Characters mentioned
    if context["characters"]:
        lines.append("[bold cyan]Characters from Reading:[/bold cyan]")
        lines.append(f"  {', '.join(context['characters'][:15])}")
        lines.append("")

    # Themes identified
    if context["themes"]:
        lines.append("[bold cyan]Themes Identified:[/bold cyan]")
        lines.append(f"  {', '.join(context['themes'])}")
        lines.append("")

    # Book notes
    if context["book_notes"]:
        lines.append(f"[bold cyan]Reading Notes ({len(context['book_notes'])} total):[/bold cyan]")
        for note in context["book_notes"][:5]:  # Show first 5
            lines.append(f"  [{note['book_title']}]")
            lines.append(f"    {note['note'][:100]}{'...' if len(note['note']) > 100 else ''}")

        if len(context["book_notes"]) > 5:
            lines.append(f"  ... and {len(context['book_notes']) - 5} more notes")

    console.print(Panel(
        "\n".join(lines),
        title=f"Book Context for: {context['movie_title']}",
        border_style="green"
    ))


def get_book_context_for_scene(
    movie_title: str,
    scene_text: str,
    context: Optional[dict[str, Any]] = None
) -> dict[str, Any]:
    """Find book notes relevant to a specific scene.

    Args:
        movie_title: Movie title
        scene_text: Text from the scene (dialogue, description)
        context: Pre-loaded book context (or None to load)

    Returns:
        Dict with relevant book notes for this scene
    """
    if context is None:
        context = get_book_notes(movie_title)

    if not context.get("has_context"):
        return {"relevant_notes": [], "characters_in_scene": []}

    scene_lower = scene_text.lower()
    result = {
        "relevant_notes": [],
        "characters_in_scene": [],
    }

    # Find characters mentioned in scene
    for character in context.get("characters", []):
        if character.lower() in scene_lower:
            result["characters_in_scene"].append(character)

    # Find notes mentioning scene content or characters
    for note in context.get("book_notes", []):
        note_text = note.get("note", "").lower()

        # Check if note mentions any character in the scene
        for char in result["characters_in_scene"]:
            if char.lower() in note_text:
                result["relevant_notes"].append(note)
                break

        # Check for keyword overlap
        scene_words = set(scene_lower.split())
        note_words = set(note_text.split())
        overlap = scene_words & note_words

        # If significant overlap, include the note
        meaningful_overlap = overlap - {"the", "a", "an", "is", "was", "are", "were", "to", "of", "and", "in", "on"}
        if len(meaningful_overlap) >= 3 and note not in result["relevant_notes"]:
            result["relevant_notes"].append(note)

    return result


def format_scene_with_book_context(
    scene_text: str,
    book_context: dict[str, Any],
    movie_title: str
) -> str:
    """Format a scene with relevant book context as annotations.

    Args:
        scene_text: The scene dialogue/text
        book_context: Context from get_book_context_for_scene()
        movie_title: Movie title

    Returns:
        Formatted string with scene and book annotations
    """
    lines = []

    # Scene header
    lines.append(f"=== SCENE: {movie_title} ===")
    lines.append("")
    lines.append(scene_text)
    lines.append("")

    # Book context annotations
    if book_context.get("characters_in_scene"):
        lines.append(f"[Characters from book: {', '.join(book_context['characters_in_scene'])}]")

    if book_context.get("relevant_notes"):
        lines.append("")
        lines.append("--- Book Context ---")
        for note in book_context["relevant_notes"][:3]:
            lines.append(f"  > {note['note'][:150]}...")

    return "\n".join(lines)


# CLI entry point
def main():
    """CLI for testing book context."""
    import argparse

    parser = argparse.ArgumentParser(description="Get book context for a movie")
    parser.add_argument("movie", help="Movie title")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--scene", help="Scene text to find relevant notes for")

    args = parser.parse_args()

    context = get_book_notes(args.movie)

    if args.scene:
        scene_context = get_book_context_for_scene(args.movie, args.scene, context)
        if args.json:
            print(json.dumps(scene_context, indent=2, default=str))
        else:
            console.print(f"\n[bold]Scene:[/bold] {args.scene[:100]}...")
            console.print(f"\n[bold]Characters in scene:[/bold] {', '.join(scene_context['characters_in_scene']) or 'None identified'}")
            console.print(f"\n[bold]Relevant book notes:[/bold] {len(scene_context['relevant_notes'])}")
            for note in scene_context["relevant_notes"]:
                console.print(f"  - {note['note'][:100]}...")
    else:
        if args.json:
            print(json.dumps(context, indent=2, default=str))
        else:
            display_book_context(context)


if __name__ == "__main__":
    main()
