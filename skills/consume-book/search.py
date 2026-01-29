"""Search functionality for consume-book."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from rich.console import Console

from consume_common.registry import ContentRegistry
from .epub import extract_text

console = Console()


def _load_text(path: Path, format_hint: str, cache_dir: Path, cache_key: str) -> Optional[str]:
    if format_hint == "epub":
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path = cache_dir / f"{cache_key}.txt"
        if cache_path.exists():
            return cache_path.read_text(encoding="utf-8")

        text = extract_text(path)
        cache_path.write_text(text, encoding="utf-8")
        return text

    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def search_books(
    query: str,
    book_id: Optional[str] = None,
    context_chars: int = 200,
    registry_path: Optional[Path] = None
) -> list[dict[str, object]]:
    """Search for text in books.

    Args:
        query: Search query
        book_id: Optional book id to limit search
        context_chars: Characters of context around match
        registry_path: Override registry path

    Returns:
        List of matches
    """
    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-book" / "registry.json"

    registry = ContentRegistry(registry_path)

    if book_id:
        book = registry.get_content(book_id)
        books = [book] if book else []
        if not books:
            console.print(f"[red]Book {book_id} not found[/red]")
            return []
    else:
        books = registry.list_content("book")

    results: list[dict[str, object]] = []
    query_lower = query.lower()

    cache_dir = Path.home() / ".pi" / "consume-book" / "cache"

    for book in books:
        if not book or not book.get("source_path"):
            continue

        source_path = Path(book["source_path"])
        if not source_path.exists():
            continue

        format_hint = str(book.get("metadata", {}).get("format", "text"))
        text = _load_text(source_path, format_hint, cache_dir, book["content_id"])
        if not text:
            continue

        text_lower = text.lower()
        start = 0
        while True:
            index = text_lower.find(query_lower, start)
            if index == -1:
                break

            before_start = max(0, index - context_chars)
            after_end = min(len(text), index + len(query) + context_chars)

            results.append({
                "book_id": book["content_id"],
                "book_title": book.get("title", "Unknown"),
                "char_position": index,
                "text": text[index:index + len(query)],
                "context_before": text[before_start:index].strip(),
                "context_after": text[index + len(query):after_end].strip(),
            })

            start = index + len(query)

    console.print(f"[green]Found {len(results)} matches for '{query}'[/green]")
    return results


def main() -> None:
    """CLI entry point for search."""
    import argparse

    parser = argparse.ArgumentParser(description="Search book text")
    parser.add_argument("query", help="Text to search for")
    parser.add_argument("--book", help="Specific book ID")
    parser.add_argument("--context", type=int, default=200, help="Context chars (default: 200)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    results = search_books(
        query=args.query,
        book_id=args.book,
        context_chars=args.context
    )

    if args.json:
        print(json.dumps({"results": results}, indent=2))
    else:
        if not results:
            console.print("[yellow]No matches found[/yellow]")
            return

        for result in results:
            console.print(f"\n[bold]{result['book_title']}[/bold]")
            console.print(f"  Position: {result['char_position']}")
            console.print(f"  Text: {result['text']}")
            if result["context_before"]:
                console.print(f"  Before: {result['context_before']}")
            if result["context_after"]:
                console.print(f"  After: {result['context_after']}")


if __name__ == "__main__":
    main()
