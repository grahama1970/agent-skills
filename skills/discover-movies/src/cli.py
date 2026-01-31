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

app = typer.Typer(help="Movie discovery via TMDB with taxonomy integration")
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
    console.print(f"[dim]Searching for movies similar to '{movie}'...[/dim]")

    # First search for the movie
    search_results = tmdb.search_movies(movie, limit=1)
    if not search_results:
        console.print(f"[red]Movie '{movie}' not found.[/red]")
        raise typer.Exit(1)

    source_movie = search_results[0]
    console.print(f"[dim]Found: {source_movie.title} ({source_movie.year})[/dim]")

    # Get similar movies
    results = tmdb.get_similar_movies(source_movie.id, limit=limit)

    _output_results(results, json_output, f"Movies similar to {source_movie.title}")


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

    console.print(f"[dim]Searching movies for bridge '{bridge_attr}'...[/dim]")
    genre_ids = taxonomy.get_genre_ids_for_bridge(bridge_attr)
    console.print(f"[dim]Genres: {', '.join(taxonomy.BRIDGE_TO_GENRES[bridge_attr][:3])}...[/dim]")

    results = tmdb.discover_by_genre(genre_ids, limit=limit)

    _output_results(results, json_output, f"Movies for Bridge: {bridge_attr}", bridge_tags=[bridge_attr])


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

    # Try to load from consume-movie registry
    import json
    from pathlib import Path

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

        # Get most recently consumed movies
        recent = sorted(movies.values(), key=lambda x: x.get("last_consumed", ""), reverse=True)[:3]
        console.print(f"[dim]Based on: {', '.join(m.get('title', 'Unknown')[:30] for m in recent)}[/dim]")

        # Get recommendations for each
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
        _output_results(all_recs, json_output, "Recommendations Based on History")

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
    app()


if __name__ == "__main__":
    main()
