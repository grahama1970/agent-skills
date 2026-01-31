#!/usr/bin/env python3
"""
CLI for discover-books skill.

Usage:
    python -m src.cli similar "Dune"
    python -m src.cli by-author "Frank Herbert"
    python -m src.cli search-subject "science fiction"
    python -m src.cli bridge Resilience
"""

import json
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import openlibrary_client as ol
from . import taxonomy

app = typer.Typer(help="Book discovery via OpenLibrary with taxonomy integration")
console = Console()


def _output_results(results: list, json_output: bool, title: str, bridge_tags: list = None):
    """Output results as table or JSON with taxonomy."""
    if json_output:
        output = {
            "results": [r.to_dict() for r in results],
            "count": len(results),
            "taxonomy": taxonomy.build_taxonomy_output(
                [r.to_dict() for r in results],
                bridge_tags=bridge_tags
            ),
        }
        print(json.dumps(output, indent=2))
        return

    if not results:
        console.print("[yellow]No books found.[/yellow]")
        return

    table = Table(title=title)
    table.add_column("Title", style="cyan", max_width=40)
    table.add_column("Author", style="dim", max_width=25)
    table.add_column("Year", style="dim")
    table.add_column("Subjects", style="dim", max_width=30)

    for r in results:
        subjects_str = ", ".join(r.subjects[:2]) if r.subjects else "-"
        table.add_row(
            r.title[:40],
            r.authors[:25] if len(r.authors) <= 25 else r.authors[:22] + "...",
            r.year,
            subjects_str[:30]
        )

    console.print(table)

    # Show taxonomy in non-JSON mode too
    if results:
        tax = taxonomy.build_taxonomy_output([r.to_dict() for r in results], bridge_tags)
        if tax["bridge_tags"]:
            console.print(f"\n[dim]Bridge tags: {', '.join(tax['bridge_tags'])}[/dim]")


@app.command()
def similar(
    book: str = typer.Argument(..., help="Book title to find similar books for"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Find books similar to the given book."""
    console.print(f"[dim]Searching for books similar to '{book}'...[/dim]")

    # First search for the book to get its subjects
    search_results = ol.search_books(book, limit=1)
    if not search_results:
        console.print(f"[red]Book '{book}' not found.[/red]")
        raise typer.Exit(1)

    source_book = search_results[0]
    console.print(f"[dim]Found: {source_book.title} by {source_book.authors}[/dim]")

    # Get similar books by searching for same subjects
    if source_book.subjects:
        # Use first two subjects for similarity
        subject = source_book.subjects[0]
        console.print(f"[dim]Searching by subject: {subject}[/dim]")
        results = ol.search_by_subject(subject, limit=limit + 5)

        # Filter out the source book
        results = [r for r in results if r.key != source_book.key][:limit]
    else:
        # Fallback: search by author
        if source_book.author_name:
            results = ol.search_by_author(source_book.author_name[0], limit=limit)
            results = [r for r in results if r.key != source_book.key][:limit]
        else:
            results = []

    _output_results(results, json_output, f"Books similar to {source_book.title}")


@app.command("by-author")
def by_author(
    name: str = typer.Argument(..., help="Author name"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get books by a specific author."""
    console.print(f"[dim]Searching for books by '{name}'...[/dim]")

    results = ol.search_by_author(name, limit=limit)

    _output_results(results, json_output, f"Books by {name}")


@app.command("search-subject")
def search_subject(
    subject: str = typer.Argument(..., help="Subject/genre to search for"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Search books by subject/genre."""
    console.print(f"[dim]Searching books in subject '{subject}'...[/dim]")

    results = ol.search_by_subject(subject, limit=limit)

    _output_results(results, json_output, f"Books in '{subject}'")


@app.command()
def bridge(
    bridge_attr: str = typer.Argument(..., help="Bridge attribute (Precision, Resilience, Fragility, Corruption, Loyalty, Stealth)"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Search books by HMT bridge attribute."""
    valid_bridges = list(taxonomy.BRIDGE_TO_SUBJECTS.keys())
    if bridge_attr not in valid_bridges:
        console.print(f"[red]Invalid bridge. Choose from: {', '.join(valid_bridges)}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Searching books for bridge '{bridge_attr}'...[/dim]")
    subjects = taxonomy.get_subjects_for_bridge(bridge_attr)
    console.print(f"[dim]Subjects: {', '.join(subjects[:3])}...[/dim]")

    # Search for each subject and combine results
    all_results = []
    seen_keys = set()

    for subject in subjects[:3]:  # Use first 3 subjects
        results = ol.search_by_subject(subject, limit=limit // 2)
        for r in results:
            if r.key not in seen_keys:
                seen_keys.add(r.key)
                all_results.append(r)

    # Sort by edition count (popularity) and limit
    all_results = sorted(all_results, key=lambda x: x.edition_count, reverse=True)[:limit]

    _output_results(all_results, json_output, f"Books for Bridge: {bridge_attr}", bridge_tags=[bridge_attr])


@app.command()
def trending(
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get trending/popular books."""
    console.print("[dim]Fetching popular books...[/dim]")

    results = ol.get_trending(limit=limit)

    _output_results(results, json_output, "Popular Books")


@app.command()
def fresh(
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get fresh/recent releases."""
    console.print("[dim]Fetching recent releases...[/dim]")

    results = ol.get_new_releases(limit=limit)

    _output_results(results, json_output, "Recent Releases")


@app.command()
def recommendations(
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get recommendations based on consume-book history."""
    console.print("[dim]Loading consume-book history...[/dim]")

    from pathlib import Path

    registry_path = Path.home() / ".pi" / "consume-book" / "registry.json"
    if not registry_path.exists():
        registry_path = Path(__file__).parent.parent.parent / "consume-book" / "registry.json"

    if not registry_path.exists():
        console.print("[yellow]No consume-book history found. Read some books first![/yellow]")
        raise typer.Exit(1)

    try:
        with open(registry_path) as f:
            registry = json.load(f)

        books = registry.get("books", {})
        if not books:
            console.print("[yellow]No books in history. Read some books first![/yellow]")
            raise typer.Exit(1)

        # Get most recently consumed books
        recent = sorted(books.values(), key=lambda x: x.get("last_consumed", ""), reverse=True)[:3]
        console.print(f"[dim]Based on: {', '.join(b.get('title', 'Unknown')[:30] for b in recent)}[/dim]")

        # Get recommendations based on subjects
        all_subjects = []
        for book in recent:
            all_subjects.extend(book.get("subjects", [])[:3])

        if not all_subjects:
            # Fallback to author
            authors = [b.get("author") for b in recent if b.get("author")]
            if authors:
                results = ol.search_by_author(authors[0], limit=limit)
            else:
                results = ol.get_trending(limit=limit)
        else:
            # Search by most common subject
            from collections import Counter
            subject_counts = Counter(all_subjects)
            top_subject = subject_counts.most_common(1)[0][0]
            console.print(f"[dim]Top subject: {top_subject}[/dim]")
            results = ol.search_by_subject(top_subject, limit=limit)

        _output_results(results, json_output, "Recommendations Based on History")

    except Exception as e:
        console.print(f"[red]Error loading history: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def check():
    """Check OpenLibrary API connectivity."""
    console.print("[bold]Checking OpenLibrary API connectivity...[/bold]\n")

    if ol.check_api():
        console.print("[green]OpenLibrary API: OK[/green]")

        # Test a quick search
        results = ol.search_books("Dune", limit=1)
        if results:
            console.print(f"[green]Search test: Found '{results[0].title}' by {results[0].authors}[/green]")
        else:
            console.print("[yellow]Search test: No results[/yellow]")
    else:
        console.print("[red]OpenLibrary API: FAILED[/red]")
        raise typer.Exit(1)


def main():
    app()


if __name__ == "__main__":
    main()
