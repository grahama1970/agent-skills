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

# ── TaskClient integration ──────────────────────────────────────────────────
try:
    from pathlib import Path as _TaskPath
    sys.path.insert(0, str(_TaskPath.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

# Memory-first discovery imports (graceful fallback)
from pathlib import Path as _Path

_SKILLS_DIR = str(_Path(__file__).resolve().parent.parent.parent)
if _SKILLS_DIR not in sys.path:
    sys.path.insert(0, _SKILLS_DIR)

try:
    from common.discovery import gather_context, score_results, store_discoveries
    from common.taxonomy import ContentType
    _DISCOVERY_AVAILABLE = True
except ImportError:
    _DISCOVERY_AVAILABLE = False

app = typer.Typer(help="Book discovery via OpenLibrary with taxonomy integration")
console = Console()


def _output_results(results: list, json_output: bool, title: str, bridge_tags: list = None, scored: list = None):
    """Output results as table or JSON with taxonomy and optional scoring."""
    if json_output:
        output = {
            "results": [r.to_dict() for r in results],
            "count": len(results),
            "taxonomy": taxonomy.build_taxonomy_output(
                [r.to_dict() for r in results],
                bridge_tags=bridge_tags
            ),
        }
        if scored:
            output["scoring"] = [
                {
                    "title": s.item.get("title", ""),
                    "final_score": s.final_score,
                    "bridge_alignment": s.bridge_alignment,
                    "episodic_resonance": s.episodic_resonance,
                    "novelty": s.novelty,
                    "bridge_tags": s.bridge_tags,
                    "worth_remembering": s.worth_remembering,
                }
                for s in scored
            ]
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
    # Phase 1: Memory-first context gathering
    ctx = None
    scored = None
    if _DISCOVERY_AVAILABLE:
        ctx = gather_context(f"books similar {book}", ContentType.BOOK)
        if ctx.total_hits:
            console.print(f"[dim]{ctx.memory_summary()}[/dim]")

    console.print(f"[dim]Searching for books similar to '{book}'...[/dim]")

    # Phase 2: External API calls
    search_results = ol.search_books(book, limit=1)
    if not search_results:
        console.print(f"[red]Book '{book}' not found.[/red]")
        raise typer.Exit(1)

    source_book = search_results[0]
    console.print(f"[dim]Found: {source_book.title} by {source_book.authors}[/dim]")

    if source_book.subjects:
        subject = source_book.subjects[0]
        console.print(f"[dim]Searching by subject: {subject}[/dim]")
        results = ol.search_by_subject(subject, limit=limit + 5)
        results = [r for r in results if r.key != source_book.key][:limit]
    else:
        if source_book.author_name:
            results = ol.search_by_author(source_book.author_name[0], limit=limit)
            results = [r for r in results if r.key != source_book.key][:limit]
        else:
            results = []

    # Phase 3: Score + rerank with persona/memory
    if _DISCOVERY_AVAILABLE and ctx and results:
        scored = score_results(
            [r.to_dict() for r in results], ctx, ContentType.BOOK, raw_score_key="edition_count"
        )
        title_map = {r.title.lower(): r for r in results}
        reordered = []
        seen = set()
        for s in scored:
            key = s.item.get("title", "").lower()
            if key in title_map and key not in seen:
                reordered.append(title_map[key])
                seen.add(key)
        for r in results:
            if r.title.lower() not in seen:
                reordered.append(r)
        results = reordered[:limit]

    _output_results(results, json_output, f"Books similar to {source_book.title}", scored=scored)

    # Phase 4: Store interesting discoveries
    if _DISCOVERY_AVAILABLE and scored:
        stored = store_discoveries(scored, ContentType.BOOK)
        if stored:
            console.print(f"[dim]Stored {stored} discoveries to memory[/dim]")


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

    # Phase 1: Memory-first context gathering
    ctx = None
    scored = None
    if _DISCOVERY_AVAILABLE:
        ctx = gather_context(f"books {bridge_attr}", ContentType.BOOK)
        if ctx.total_hits:
            console.print(f"[dim]{ctx.memory_summary()}[/dim]")

    console.print(f"[dim]Searching books for bridge '{bridge_attr}'...[/dim]")
    subjects = taxonomy.get_subjects_for_bridge(bridge_attr)
    console.print(f"[dim]Subjects: {', '.join(subjects[:3])}...[/dim]")

    # Phase 2: External API calls
    all_results = []
    seen_keys = set()

    for subject in subjects[:3]:  # Use first 3 subjects
        results = ol.search_by_subject(subject, limit=limit // 2)
        for r in results:
            if r.key not in seen_keys:
                seen_keys.add(r.key)
                all_results.append(r)

    # Phase 3: Score + rerank with persona/memory
    if _DISCOVERY_AVAILABLE and ctx and all_results:
        scored = score_results(
            [r.to_dict() for r in all_results], ctx, ContentType.BOOK, raw_score_key="edition_count"
        )
        # Reorder results by persona-guided score
        title_map = {r.title.lower(): r for r in all_results}
        reordered = []
        seen = set()
        for s in scored:
            key = s.item.get("title", "").lower()
            if key in title_map and key not in seen:
                reordered.append(title_map[key])
                seen.add(key)
        for r in all_results:
            if r.title.lower() not in seen:
                reordered.append(r)
        all_results = reordered[:limit]
    else:
        all_results = sorted(all_results, key=lambda x: x.edition_count, reverse=True)[:limit]

    _output_results(all_results, json_output, f"Books for Bridge: {bridge_attr}", bridge_tags=[bridge_attr], scored=scored)

    # Phase 4: Store interesting discoveries
    if _DISCOVERY_AVAILABLE and scored:
        stored = store_discoveries(scored, ContentType.BOOK)
        if stored:
            console.print(f"[dim]Stored {stored} discoveries to memory[/dim]")


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

    # Phase 1: Memory-first context gathering
    ctx = None
    scored = None
    if _DISCOVERY_AVAILABLE:
        ctx = gather_context("book recommendations history", ContentType.BOOK)
        if ctx.total_hits:
            console.print(f"[dim]{ctx.memory_summary()}[/dim]")

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

        # Phase 2: External API calls
        recent = sorted(books.values(), key=lambda x: x.get("last_consumed", ""), reverse=True)[:3]
        console.print(f"[dim]Based on: {', '.join(b.get('title', 'Unknown')[:30] for b in recent)}[/dim]")

        all_subjects = []
        for book in recent:
            all_subjects.extend(book.get("subjects", [])[:3])

        if not all_subjects:
            authors = [b.get("author") for b in recent if b.get("author")]
            if authors:
                results = ol.search_by_author(authors[0], limit=limit)
            else:
                results = ol.get_trending(limit=limit)
        else:
            from collections import Counter
            subject_counts = Counter(all_subjects)
            top_subject = subject_counts.most_common(1)[0][0]
            console.print(f"[dim]Top subject: {top_subject}[/dim]")
            results = ol.search_by_subject(top_subject, limit=limit)

        # Phase 3: Score + rerank with persona/memory
        if _DISCOVERY_AVAILABLE and ctx and results:
            scored = score_results(
                [r.to_dict() for r in results], ctx, ContentType.BOOK, raw_score_key="edition_count"
            )
            title_map = {r.title.lower(): r for r in results}
            reordered = []
            seen = set()
            for s in scored:
                key = s.item.get("title", "").lower()
                if key in title_map and key not in seen:
                    reordered.append(title_map[key])
                    seen.add(key)
            for r in results:
                if r.title.lower() not in seen:
                    reordered.append(r)
            results = reordered[:limit]

        _output_results(results, json_output, "Recommendations Based on History", scored=scored)

        # Phase 4: Store interesting discoveries
        if _DISCOVERY_AVAILABLE and scored:
            stored = store_discoveries(scored, ContentType.BOOK)
            if stored:
                console.print(f"[dim]Stored {stored} discoveries to memory[/dim]")

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
    monitor = TaskClient("discover-books", total=1) if TaskClient else None
    try:
        app()
    finally:
        if monitor:
            monitor.update(item="done")
            monitor.finish()


if __name__ == "__main__":
    main()
