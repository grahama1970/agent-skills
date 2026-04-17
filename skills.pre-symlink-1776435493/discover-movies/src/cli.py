#!/usr/bin/env python3
"""
CLI for discover-movies skill.

Usage:
    python -m src.cli similar "There Will Be Blood"
    python -m src.cli trending --range week
    python -m src.cli search-genre "thriller"
    python -m src.cli bridge Corruption
"""

import json
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import tmdb_client as tmdb
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

app = typer.Typer(help="Movie discovery via TMDB with taxonomy integration")
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
        console.print("[yellow]No movies found.[/yellow]")
        return

    table = Table(title=title)
    table.add_column("Title", style="cyan")
    table.add_column("Year", style="dim")
    table.add_column("Rating", justify="right")
    table.add_column("Genres", style="dim")

    for r in results:
        genres_str = ", ".join(r.genres[:3]) if r.genres else "-"
        table.add_row(r.title, r.year, f"{r.vote_average:.1f}", genres_str)

    console.print(table)

    # Show taxonomy in non-JSON mode too
    if results:
        tax = taxonomy.build_taxonomy_output([r.to_dict() for r in results], bridge_tags)
        if tax["bridge_tags"]:
            console.print(f"\n[dim]Bridge tags: {', '.join(tax['bridge_tags'])}[/dim]")


@app.command()
def similar(
    movie: str = typer.Argument(..., help="Movie title to find similar movies for"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Find movies similar to the given movie."""
    # Phase 1: Memory-first context gathering
    ctx = None
    scored = None
    if _DISCOVERY_AVAILABLE:
        ctx = gather_context(f"movies similar {movie}", ContentType.MOVIE)
        if ctx.total_hits:
            console.print(f"[dim]{ctx.memory_summary()}[/dim]")

    console.print(f"[dim]Searching for movies similar to '{movie}'...[/dim]")

    # Phase 2: External API calls
    search_results = tmdb.search_movies(movie, limit=1)
    if not search_results:
        console.print(f"[red]Movie '{movie}' not found.[/red]")
        raise typer.Exit(1)

    source_movie = search_results[0]
    console.print(f"[dim]Found: {source_movie.title} ({source_movie.year})[/dim]")

    results = tmdb.get_similar_movies(source_movie.id, limit=limit)

    # Phase 3: Score + rerank with persona/memory
    if _DISCOVERY_AVAILABLE and ctx and results:
        scored = score_results(
            [r.to_dict() for r in results], ctx, ContentType.MOVIE, raw_score_key="popularity"
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

    _output_results(results, json_output, f"Movies similar to {source_movie.title}", scored=scored)

    # Phase 4: Store interesting discoveries
    if _DISCOVERY_AVAILABLE and scored:
        stored = store_discoveries(scored, ContentType.MOVIE)
        if stored:
            console.print(f"[dim]Stored {stored} discoveries to memory[/dim]")


@app.command()
def trending(
    time_range: str = typer.Option("week", "--range", "-r", help="day or week"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get trending movies."""
    console.print(f"[dim]Fetching trending movies ({time_range})...[/dim]")

    results = tmdb.get_trending(time_window=time_range, limit=limit)

    _output_results(results, json_output, f"Trending Movies ({time_range})")


@app.command("search-genre")
def search_genre(
    genre: str = typer.Argument(..., help="Genre to search for"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Search movies by genre."""
    console.print(f"[dim]Searching movies in genre '{genre}'...[/dim]")

    # Map genre name to IDs
    genre_lower = genre.lower()
    genre_ids = []

    for gid, name in tmdb._GENRE_CACHE.items():
        if genre_lower in name.lower():
            genre_ids.append(gid)

    if not genre_ids:
        console.print(f"[red]Genre '{genre}' not found. Try: Action, Drama, Horror, Thriller, etc.[/red]")
        raise typer.Exit(1)

    results = tmdb.discover_by_genre(genre_ids, limit=limit)

    _output_results(results, json_output, f"Movies in '{genre}'")


@app.command("by-director")
def by_director(
    name: str = typer.Argument(..., help="Director name"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get movies by a director."""
    console.print(f"[dim]Searching for director '{name}'...[/dim]")

    person_id = tmdb.search_person(name)
    if not person_id:
        console.print(f"[red]Director '{name}' not found.[/red]")
        raise typer.Exit(1)

    results = tmdb.get_person_movies(person_id, limit=limit, department="Directing")

    _output_results(results, json_output, f"Movies by {name}")


@app.command()
def bridge(
    bridge_attr: str = typer.Argument(..., help="Bridge attribute (Precision, Resilience, Fragility, Corruption, Loyalty, Stealth)"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Search movies by HMT bridge attribute."""
    valid_bridges = list(taxonomy.BRIDGE_TO_GENRE_IDS.keys())
    if bridge_attr not in valid_bridges:
        console.print(f"[red]Invalid bridge. Choose from: {', '.join(valid_bridges)}[/red]")
        raise typer.Exit(1)

    # Phase 1: Memory-first context gathering
    ctx = None
    scored = None
    if _DISCOVERY_AVAILABLE:
        ctx = gather_context(f"movies {bridge_attr}", ContentType.MOVIE)
        if ctx.total_hits:
            console.print(f"[dim]{ctx.memory_summary()}[/dim]")

    console.print(f"[dim]Searching movies for bridge '{bridge_attr}'...[/dim]")
    genre_ids = taxonomy.get_genre_ids_for_bridge(bridge_attr)
    console.print(f"[dim]Genres: {', '.join(taxonomy.BRIDGE_TO_GENRES[bridge_attr][:3])}...[/dim]")

    # Phase 2: External API calls
    results = tmdb.discover_by_genre(genre_ids, limit=limit)

    # Phase 3: Score + rerank with persona/memory
    if _DISCOVERY_AVAILABLE and ctx and results:
        scored = score_results(
            [r.to_dict() for r in results], ctx, ContentType.MOVIE, raw_score_key="popularity"
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

    _output_results(results, json_output, f"Movies for Bridge: {bridge_attr}", bridge_tags=[bridge_attr], scored=scored)

    # Phase 4: Store interesting discoveries
    if _DISCOVERY_AVAILABLE and scored:
        stored = store_discoveries(scored, ContentType.MOVIE)
        if stored:
            console.print(f"[dim]Stored {stored} discoveries to memory[/dim]")


@app.command()
def fresh(
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get fresh/new releases (now playing)."""
    console.print("[dim]Fetching new releases...[/dim]")

    results = tmdb.get_now_playing(limit=limit)

    _output_results(results, json_output, "Fresh Releases (Now Playing)")


@app.command()
def recommendations(
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get recommendations based on consume-movie history."""
    console.print("[dim]Loading consume-movie history...[/dim]")

    import json
    from pathlib import Path

    # Phase 1: Memory-first context gathering
    ctx = None
    scored = None
    if _DISCOVERY_AVAILABLE:
        ctx = gather_context("movie recommendations history", ContentType.MOVIE)
        if ctx.total_hits:
            console.print(f"[dim]{ctx.memory_summary()}[/dim]")

    registry_path = Path.home() / ".pi" / "consume-movie" / "registry.json"
    if not registry_path.exists():
        registry_path = Path(__file__).parent.parent.parent / "consume-movie" / "registry.json"

    if not registry_path.exists():
        console.print("[yellow]No consume-movie history found. Watch some movies first![/yellow]")
        raise typer.Exit(1)

    try:
        with open(registry_path) as f:
            registry = json.load(f)

        movies = registry.get("movies", {})
        if not movies:
            console.print("[yellow]No movies in history. Watch some movies first![/yellow]")
            raise typer.Exit(1)

        # Phase 2: External API calls
        recent = sorted(movies.values(), key=lambda x: x.get("last_consumed", ""), reverse=True)[:3]
        console.print(f"[dim]Based on: {', '.join(m.get('title', 'Unknown')[:30] for m in recent)}[/dim]")

        all_recs = []
        seen_ids = set()

        for movie in recent:
            if "tmdb_id" in movie:
                recs = tmdb.get_recommendations(movie["tmdb_id"], limit=limit // 2)
                for r in recs:
                    if r.id not in seen_ids:
                        seen_ids.add(r.id)
                        all_recs.append(r)

        all_recs = all_recs[:limit]

        # Phase 3: Score + rerank with persona/memory
        if _DISCOVERY_AVAILABLE and ctx and all_recs:
            scored = score_results(
                [r.to_dict() for r in all_recs], ctx, ContentType.MOVIE, raw_score_key="popularity"
            )
            title_map = {r.title.lower(): r for r in all_recs}
            reordered = []
            seen = set()
            for s in scored:
                key = s.item.get("title", "").lower()
                if key in title_map and key not in seen:
                    reordered.append(title_map[key])
                    seen.add(key)
            for r in all_recs:
                if r.title.lower() not in seen:
                    reordered.append(r)
            all_recs = reordered[:limit]

        _output_results(all_recs, json_output, "Recommendations Based on History", scored=scored)

        # Phase 4: Store interesting discoveries
        if _DISCOVERY_AVAILABLE and scored:
            stored = store_discoveries(scored, ContentType.MOVIE)
            if stored:
                console.print(f"[dim]Stored {stored} discoveries to memory[/dim]")

    except Exception as e:
        console.print(f"[red]Error loading history: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def check():
    """Check TMDB API connectivity."""
    console.print("[bold]Checking TMDB API connectivity...[/bold]\n")

    import os
    api_key = os.environ.get("TMDB_API_KEY", "")

    if not api_key:
        console.print("[red]TMDB_API_KEY not set.[/red]")
        console.print("[dim]Set it with: export TMDB_API_KEY=your_key[/dim]")
        raise typer.Exit(1)

    console.print(f"[dim]API key: {api_key[:8]}...{api_key[-4:]}[/dim]")

    if tmdb.check_api():
        console.print("[green]TMDB API: OK[/green]")

        # Test a quick search
        results = tmdb.search_movies("The Godfather", limit=1)
        if results:
            console.print(f"[green]Search test: Found '{results[0].title}' ({results[0].year})[/green]")
        else:
            console.print("[yellow]Search test: No results[/yellow]")
    else:
        console.print("[red]TMDB API: FAILED[/red]")
        raise typer.Exit(1)


def main():
    monitor = TaskClient("discover-movies", total=1) if TaskClient else None
    try:
        app()
    finally:
        if monitor:
            monitor.update(item="done")
            monitor.finish()


if __name__ == "__main__":
    main()
