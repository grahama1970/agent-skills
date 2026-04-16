"""Bridge to import content from ingest-book or local libraries."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console

from consume_common.registry import ContentRegistry
import typer

# ── TaskClient integration ──────────────────────────────────────────────────
try:
    sys.path.insert(0, str(Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

# Handle both direct execution and package import
try:
    from .epub import extract_title
except ImportError:
    from epub import extract_title

console = Console()

SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt", ".epub"}


def _detect_books_dir(explicit_dir: Optional[Path]) -> Optional[Path]:
    if explicit_dir:
        return explicit_dir

    candidates = [
        Path.home() / "clawd" / "library" / "books",
        Path.home() / "library" / "books",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    return None


def _extract_markdown_title(path: Path) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("# "):
                    return line[2:].strip()
    except OSError:
        return None
    return None


def _build_content_entry(path: Path) -> dict[str, object]:
    title: Optional[str] = None
    format_hint = "text"

    if path.suffix.lower() == ".epub":
        title = extract_title(path)
        format_hint = "epub"
    elif path.suffix.lower() in {".md", ".markdown"}:
        title = _extract_markdown_title(path)
        format_hint = "markdown"

    if not title:
        title = path.stem

    return {
        "type": "book",
        "title": title,
        "source_path": str(path),
        "metadata": {
            "format": format_hint,
            "filename": path.name,
        },
    }


def sync_from_ingest(
    books_dir: Optional[Path] = None,
    registry_path: Optional[Path] = None
) -> int:
    """Import books into consume-book registry.

    Args:
        books_dir: Directory containing book files
        registry_path: Override registry path

    Returns:
        Number of books imported
    """
    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-book" / "registry.json"

    books_dir = _detect_books_dir(books_dir)
    if not books_dir:
        console.print("[red]Books directory not found[/red]")
        return 0

    if not books_dir.exists():
        console.print(f"[red]Books directory does not exist: {books_dir}[/red]")
        return 0

    registry = ContentRegistry(registry_path)
    imported = 0

    book_files = [
        path for path in books_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    ]

    console.print(f"[cyan]Found {len(book_files)} book files[/cyan]")

    existing_sources = {entry.get("source_path") for entry in registry.list_content("book")}
    monitor = TaskClient("consume-book-sync", total=len(book_files)) if TaskClient else None

    for book_path in book_files:
        if str(book_path) in existing_sources:
            continue

        try:
            entry = _build_content_entry(book_path)
            content_id = registry.add_content(entry)
            imported += 1
            console.print(f"[green]Imported: {entry['title']} (ID: {content_id[:8]}...)[/green]")
        except Exception as exc:
            console.print(f"[red]Failed to import {book_path}: {exc}[/red]")
        if monitor:
            monitor.update(item=book_path.name)

    if monitor:
        monitor.finish()
    console.print(f"[green]Total imported: {imported} books[/green]")
    return imported


def main(
    books_dir: Optional[str] = typer.Option(None, help="Directory containing book files"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """CLI entry point for sync."""
    books_dir = Path(books_dir) if books_dir else None
    count = sync_from_ingest(books_dir=books_dir)

    if json:
        print(json.dumps({"imported": count}))


if __name__ == "__main__":
    main()
