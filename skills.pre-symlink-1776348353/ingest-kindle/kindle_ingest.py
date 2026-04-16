"""
Kindle ingestion CLI — main Typer application.

Commands:
    clippings [path]      Parse My Clippings.txt into structured highlights
    ingest <file>         Process single .epub/.mobi/.azw3 to text.md
    ingest-all [dir]      Batch process Kindle export directory
    status [--json]       Show ingestion progress
    health                Verify dependencies
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from clippings import parse_clippings, clippings_to_json, save_highlights_for_book
from formats import extract_book, EXTRACTION_MARKER

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

app = typer.Typer(
    name="ingest-kindle",
    help="Kindle book and highlights ingestion pipeline.",
    no_args_is_help=True,
)
console = Console()

LIBRARY_DIR = Path(os.environ.get("KINDLE_LIBRARY_DIR", Path.home() / "clawd" / "library" / "books"))


def _slug(title: str) -> str:
    """Convert book title to filesystem-safe slug."""
    slug = title.lower()
    for ch in "':;,!?()[]{}\"":
        slug = slug.replace(ch, "")
    slug = slug.replace(" ", "_").replace("--", "-").replace("__", "_")
    return slug[:80]


@app.command()
def clippings(
    path: Path = typer.Argument(
        ...,
        help="Path to My Clippings.txt file",
        exists=True,
    ),
    output: Path | None = typer.Option(None, "--output", "-o", help="Output JSON file"),
    book: str | None = typer.Option(None, "--book", "-b", help="Filter by book title"),
):
    """Parse My Clippings.txt into structured highlights JSON."""
    result = parse_clippings(path)

    console.print(f"[bold]Parsed {result.total} clippings from {len(result.books)} books[/bold]")
    if result.errors:
        console.print(f"[yellow]Skipped {result.errors} malformed entries[/yellow]")

    if book:
        # Filter to specific book and save to library
        book_dir = LIBRARY_DIR / _slug(book)
        saved = save_highlights_for_book(result, book, book_dir)
        if saved:
            console.print(f"[green]Saved highlights to {saved}[/green]")
        else:
            console.print(f"[red]No highlights found for '{book}'[/red]")
            raise typer.Exit(1)
        return

    # Show summary table
    table = Table(title="Books with Clippings")
    table.add_column("Book", style="cyan")
    table.add_column("Highlights", justify="right")
    table.add_column("Notes", justify="right")
    table.add_column("Bookmarks", justify="right")

    for book_key, clips in sorted(result.books.items()):
        highlights = sum(1 for c in clips if c.clip_type == "highlight")
        notes = sum(1 for c in clips if c.clip_type == "note")
        bookmarks = sum(1 for c in clips if c.clip_type == "bookmark")
        table.add_row(book_key, str(highlights), str(notes), str(bookmarks))

    console.print(table)

    if output:
        output.write_text(clippings_to_json(result), encoding="utf-8")
        console.print(f"[green]Saved to {output}[/green]")
    else:
        # Save all highlights to library directories
        saved_count = 0
        for book_key, clips in result.books.items():
            title = clips[0].title
            book_dir = LIBRARY_DIR / _slug(title)
            saved = save_highlights_for_book(result, title, book_dir)
            if saved:
                saved_count += 1

        if saved_count:
            console.print(f"[green]Saved highlights for {saved_count} books to {LIBRARY_DIR}[/green]")


@app.command()
def ingest(
    file: Path = typer.Argument(..., help="Path to .epub/.mobi/.azw3 file", exists=True),
    scope: str = typer.Option("books", "--scope", "-s", help="Memory scope"),
    title_override: str | None = typer.Option(None, "--title", "-t", help="Override book title for directory"),
):
    """Process a single ebook to text.md."""
    title = title_override or file.stem
    book_dir = LIBRARY_DIR / _slug(title)

    # Check if already extracted
    text_path = book_dir / "text.md"
    if text_path.exists() and EXTRACTION_MARKER in text_path.read_text(encoding="utf-8"):
        console.print(f"[yellow]Already extracted: {book_dir}[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]Extracting: {file.name}[/bold]")
    console.print(f"  Output: {book_dir}")

    try:
        result_path = extract_book(file, book_dir)
        console.print(f"[green]Done! Text saved to {result_path}[/green]")

        # Show stats
        text = result_path.read_text(encoding="utf-8")
        lines = text.count("\n")
        words = len(text.split())
        console.print(f"  Lines: {lines:,}  Words: {words:,}")

    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@app.command("ingest-all")
def ingest_all(
    directory: Path = typer.Argument(
        ...,
        help="Directory containing ebook files",
        exists=True,
    ),
    scope: str = typer.Option("books", "--scope", "-s", help="Memory scope"),
):
    """Batch process all ebooks in a directory."""
    extensions = {".epub", ".mobi", ".azw3", ".azw"}
    files = [f for f in directory.iterdir() if f.suffix.lower() in extensions]

    if not files:
        console.print(f"[yellow]No ebook files found in {directory}[/yellow]")
        console.print(f"  Supported: {', '.join(sorted(extensions))}")
        raise typer.Exit(1)

    console.print(f"[bold]Found {len(files)} ebooks to process[/bold]")
    success = 0
    failed = 0
    monitor = TaskClient("ingest-kindle", total=len(files)) if TaskClient else None

    for i, file in enumerate(sorted(files), 1):
        console.print(f"\n[bold][{i}/{len(files)}] {file.name}[/bold]")
        book_dir = LIBRARY_DIR / _slug(file.stem)

        text_path = book_dir / "text.md"
        if text_path.exists() and EXTRACTION_MARKER in text_path.read_text(encoding="utf-8"):
            console.print("  [yellow]Already extracted, skipping[/yellow]")
            success += 1
            continue

        try:
            extract_book(file, book_dir)
            success += 1
            console.print("  [green]Done[/green]")
        except Exception as e:
            failed += 1
            console.print(f"  [red]Failed: {e}[/red]")
        if monitor:
            monitor.update(item=file.name)

    if monitor:
        monitor.finish()
    console.print(f"\n[bold]Summary: {success} succeeded, {failed} failed[/bold]")


@app.command()
def status(
    json_output: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show ingestion progress for all books in the library."""
    if not LIBRARY_DIR.exists():
        console.print(f"[yellow]Library not found at {LIBRARY_DIR}[/yellow]")
        raise typer.Exit(0)

    books = []
    for book_dir in sorted(LIBRARY_DIR.iterdir()):
        if not book_dir.is_dir():
            continue

        entry = {
            "title": book_dir.name,
            "has_text": (book_dir / "text.md").exists(),
            "has_highlights": (book_dir / "highlights.json").exists(),
            "has_metadata": (book_dir / "metadata.json").exists(),
            "complete": False,
        }

        text_path = book_dir / "text.md"
        if text_path.exists():
            text = text_path.read_text(encoding="utf-8")
            entry["complete"] = EXTRACTION_MARKER in text
            entry["words"] = len(text.split())

        if (book_dir / "highlights.json").exists():
            highlights = json.loads((book_dir / "highlights.json").read_text())
            entry["highlight_count"] = len(highlights)

        books.append(entry)

    if json_output:
        typer.echo(json.dumps(books, indent=2))
        return

    table = Table(title=f"Library: {LIBRARY_DIR}")
    table.add_column("Book", style="cyan")
    table.add_column("Text", justify="center")
    table.add_column("Highlights", justify="center")
    table.add_column("Complete", justify="center")
    table.add_column("Words", justify="right")

    for b in books:
        table.add_row(
            b["title"],
            "[green]yes[/green]" if b["has_text"] else "[red]no[/red]",
            str(b.get("highlight_count", "-")),
            "[green]yes[/green]" if b["complete"] else "[yellow]no[/yellow]",
            f"{b.get('words', 0):,}" if b.get("words") else "-",
        )

    console.print(table)
    total = len(books)
    complete = sum(1 for b in books if b["complete"])
    console.print(f"\n[bold]{complete}/{total} books fully extracted[/bold]")


@app.command()
def health():
    """Verify all dependencies are available."""
    import importlib
    import shutil

    checks = []

    # Python deps
    for mod_name, label in [
        ("ebooklib", "ebooklib (EPUB)"),
        ("typer", "typer (CLI)"),
        ("rich", "rich (terminal)"),
    ]:
        try:
            importlib.import_module(mod_name)
            checks.append((label, True, "installed"))
        except ImportError:
            checks.append((label, False, "missing — run: uv sync"))

    # Optional: calibre
    if shutil.which("ebook-convert"):
        checks.append(("calibre ebook-convert", True, "available"))
    else:
        checks.append(("calibre ebook-convert", None, "not found (optional — needed for .mobi/.azw3)"))

    # Library dir
    if LIBRARY_DIR.exists():
        checks.append(("Library directory", True, str(LIBRARY_DIR)))
    else:
        checks.append(("Library directory", None, f"will be created at {LIBRARY_DIR}"))

    for label, ok, msg in checks:
        if ok is True:
            console.print(f"  [green]✓[/green] {label}: {msg}")
        elif ok is False:
            console.print(f"  [red]✗[/red] {label}: {msg}")
        else:
            console.print(f"  [yellow]⚠[/yellow] {label}: {msg}")

    if any(ok is False for _, ok, _ in checks):
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
