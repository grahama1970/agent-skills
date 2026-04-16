#!/usr/bin/env python3
"""
CLI for discover-talent skill.

Usage:
    python -m discover_talent.cli search "Florence Pugh"
    python -m discover_talent.cli filmography "Florence Pugh"
    python -m discover_talent.cli by-movie "Oppenheimer"
    python -m discover_talent.cli bridge Corruption
"""

import json
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import tmdb_client as tmdb
from . import taxonomy

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

app = typer.Typer(help="Actor/talent discovery via TMDB with taxonomy integration")
console = Console()


def _output_people(
    results: list,
    json_output: bool,
    title: str,
    bridge_tags: list = None,
    show_character: bool = False,
    scored: list = None,
):
    """Output people results as table or JSON with taxonomy and optional scoring."""
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
                    "name": s.item.get("name", ""),
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
        console.print("[yellow]No actors found.[/yellow]")
        return

    table = Table(title=title)
    table.add_column("Name", style="cyan")
    if show_character:
        table.add_column("Character", style="dim")
    table.add_column("Department", style="dim")
    table.add_column("Popularity", justify="right")
    table.add_column("Known For", style="dim", max_width=40)

    for r in results:
        known_for_str = ""
        if r.known_for:
            known_for_str = ", ".join(m.title[:20] for m in r.known_for[:2])
        elif show_character and r.character:
            known_for_str = f"as {r.character}"
        
        if show_character:
            table.add_row(
                r.name,
                r.character or "-",
                r.known_for_department,
                f"{r.popularity:.1f}",
                known_for_str
            )
        else:
            table.add_row(
                r.name,
                r.known_for_department,
                f"{r.popularity:.1f}",
                known_for_str
            )

    console.print(table)

    # Show taxonomy in non-JSON mode too
    if results:
        tax = taxonomy.build_taxonomy_output([r.to_dict() for r in results], bridge_tags)
        if tax["bridge_tags"]:
            console.print(f"\n[dim]Bridge tags: {', '.join(tax['bridge_tags'])}[/dim]")


def _output_images(images: list, json_output: bool, name: str):
    """Output image results."""
    if json_output:
        output = {
            "results": [img.to_dict() for img in images],
            "count": len(images),
            "person": name,
        }
        print(json.dumps(output, indent=2))
        return

    if not images:
        console.print("[yellow]No images found.[/yellow]")
        return

    console.print(f"[bold]Profile images for {name}[/bold]\n")
    for i, img in enumerate(images, 1):
        console.print(f"[cyan]{i}.[/cyan] {img.url}")
        console.print(f"   [dim]{img.width}x{img.height}, rating: {img.vote_average:.1f}[/dim]")


def _output_credits(credits: list, json_output: bool, name: str):
    """Output filmography results."""
    if json_output:
        output = {
            "results": [c.to_dict() for c in credits],
            "count": len(credits),
            "person": name,
        }
        print(json.dumps(output, indent=2))
        return

    if not credits:
        console.print("[yellow]No credits found.[/yellow]")
        return

    table = Table(title=f"Filmography: {name}")
    table.add_column("Title", style="cyan")
    table.add_column("Year", style="dim")
    table.add_column("Role", style="dim")
    table.add_column("Genres", style="dim")

    for c in credits:
        genres_str = ", ".join(c.genres[:3]) if c.genres else "-"
        role = c.character or c.job or "-"
        table.add_row(c.title, c.year, role[:30], genres_str)

    console.print(table)


@app.command()
def search(
    name: str = typer.Argument(..., help="Actor name to search"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Search for actors by name."""
    console.print(f"[dim]Searching for '{name}'...[/dim]")

    results = tmdb.search_people(name, limit=limit)
    # Filter to primarily actors
    actors = [p for p in results if p.known_for_department == "Acting"]
    if not actors:
        actors = results  # Fall back to all results

    _output_people(actors, json_output, f"Search: {name}")


@app.command()
def filmography(
    name: str = typer.Argument(..., help="Actor name"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    department: str = typer.Option("Acting", "--department", "-d", help="Acting or Directing"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get an actor's filmography."""
    console.print(f"[dim]Searching for '{name}'...[/dim]")

    # First find the person
    results = tmdb.search_people(name, limit=1)
    if not results:
        console.print(f"[red]Actor '{name}' not found.[/red]")
        raise typer.Exit(1)

    person = results[0]
    console.print(f"[dim]Found: {person.name}[/dim]")

    # Get their credits
    credits = tmdb.get_person_movie_credits(person.id, limit=limit, department=department)
    
    _output_credits(credits, json_output, person.name)


@app.command("by-movie")
def by_movie(
    movie: str = typer.Argument(..., help="Movie title"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max cast members"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get the cast of a movie."""
    console.print(f"[dim]Searching for movie '{movie}'...[/dim]")

    movie_id = tmdb.search_movie(movie)
    if not movie_id:
        console.print(f"[red]Movie '{movie}' not found.[/red]")
        raise typer.Exit(1)

    cast = tmdb.get_movie_cast(movie_id, limit=limit)
    
    _output_people(cast, json_output, f"Cast: {movie}", show_character=True)


@app.command()
def bridge(
    bridge_attr: str = typer.Argument(..., help="Bridge attribute (Precision, Resilience, etc.)"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Search actors by HMT bridge attribute."""
    valid_bridges = list(taxonomy.BRIDGE_TO_GENRE_IDS.keys())
    if bridge_attr not in valid_bridges:
        console.print(f"[red]Invalid bridge. Choose from: {', '.join(valid_bridges)}[/red]")
        raise typer.Exit(1)

    # Phase 1: Memory-first context gathering
    ctx = None
    scored = None
    if _DISCOVERY_AVAILABLE:
        ctx = gather_context(f"talent actors {bridge_attr}", ContentType.MOVIE)
        if ctx.total_hits:
            console.print(f"[dim]{ctx.memory_summary()}[/dim]")

    console.print(f"[dim]Finding actors for bridge '{bridge_attr}'...[/dim]")

    # Show what we're looking for
    actor_types = taxonomy.get_actor_types_for_bridge(bridge_attr)
    console.print(f"[dim]Actor types: {', '.join(actor_types[:3])}...[/dim]")

    # Phase 2: External API calls
    genre_ids = taxonomy.get_genre_ids_for_bridge(bridge_attr)
    results = tmdb.discover_people_by_genre(genre_ids, limit=limit)

    # Phase 3: Score + rerank with persona/memory
    if _DISCOVERY_AVAILABLE and ctx and results:
        scored = score_results(
            [r.to_dict() for r in results], ctx, ContentType.MOVIE, raw_score_key="popularity"
        )
        name_map = {r.name.lower(): r for r in results}
        reordered = []
        seen = set()
        for s in scored:
            key = s.item.get("name", "").lower()
            if key in name_map and key not in seen:
                reordered.append(name_map[key])
                seen.add(key)
        for r in results:
            if r.name.lower() not in seen:
                reordered.append(r)
        results = reordered[:limit]

    _output_people(results, json_output, f"Actors for Bridge: {bridge_attr}", bridge_tags=[bridge_attr], scored=scored)

    # Phase 4: Store interesting discoveries
    if _DISCOVERY_AVAILABLE and scored:
        stored = store_discoveries(scored, ContentType.MOVIE)
        if stored:
            console.print(f"[dim]Stored {stored} discoveries to memory[/dim]")


@app.command()
def similar(
    name: str = typer.Argument(..., help="Actor name to find similar actors for"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Find actors similar to the given actor."""
    # Phase 1: Memory-first context gathering
    ctx = None
    scored = None
    if _DISCOVERY_AVAILABLE:
        ctx = gather_context(f"talent similar {name}", ContentType.MOVIE)
        if ctx.total_hits:
            console.print(f"[dim]{ctx.memory_summary()}[/dim]")

    console.print(f"[dim]Searching for '{name}'...[/dim]")

    # Phase 2: External API calls
    results = tmdb.search_people(name, limit=1)
    if not results:
        console.print(f"[red]Actor '{name}' not found.[/red]")
        raise typer.Exit(1)

    person = results[0]
    console.print(f"[dim]Found: {person.name}[/dim]")

    credits = tmdb.get_person_movie_credits(person.id, limit=10)

    all_genre_ids = []
    for credit in credits:
        all_genre_ids.extend(credit.genre_ids)

    from collections import Counter
    genre_counts = Counter(all_genre_ids)
    top_genres = [g for g, _ in genre_counts.most_common(3)]

    if not top_genres:
        console.print("[yellow]Cannot determine actor's genre profile.[/yellow]")
        raise typer.Exit(1)

    console.print(f"[dim]Genre profile: {', '.join(tmdb.GENRE_CACHE.get(g, '?') for g in top_genres)}[/dim]")

    similar_actors = tmdb.discover_people_by_genre(top_genres, limit=limit + 5)
    similar_actors = [a for a in similar_actors if a.id != person.id][:limit]

    # Phase 3: Score + rerank with persona/memory
    if _DISCOVERY_AVAILABLE and ctx and similar_actors:
        scored = score_results(
            [a.to_dict() for a in similar_actors], ctx, ContentType.MOVIE, raw_score_key="popularity"
        )
        name_map = {a.name.lower(): a for a in similar_actors}
        reordered = []
        seen = set()
        for s in scored:
            key = s.item.get("name", "").lower()
            if key in name_map and key not in seen:
                reordered.append(name_map[key])
                seen.add(key)
        for a in similar_actors:
            if a.name.lower() not in seen:
                reordered.append(a)
        similar_actors = reordered[:limit]

    _output_people(similar_actors, json_output, f"Actors similar to {person.name}", scored=scored)

    # Phase 4: Store interesting discoveries
    if _DISCOVERY_AVAILABLE and scored:
        stored = store_discoveries(scored, ContentType.MOVIE)
        if stored:
            console.print(f"[dim]Stored {stored} discoveries to memory[/dim]")


@app.command()
def images(
    name: str = typer.Argument(..., help="Actor name"),
    limit: int = typer.Option(5, "--limit", "-n", help="Max images"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get profile images for an actor."""
    console.print(f"[dim]Searching for '{name}'...[/dim]")

    # Find the person
    results = tmdb.search_people(name, limit=1)
    if not results:
        console.print(f"[red]Actor '{name}' not found.[/red]")
        raise typer.Exit(1)

    person = results[0]
    console.print(f"[dim]Found: {person.name}[/dim]")

    # Get images
    images_list = tmdb.get_person_images(person.id, limit=limit)
    
    _output_images(images_list, json_output, person.name)


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
        results = tmdb.search_people("Tom Hanks", limit=1)
        if results:
            console.print(f"[green]Search test: Found '{results[0].name}'[/green]")
        else:
            console.print("[yellow]Search test: No results[/yellow]")
    else:
        console.print("[red]TMDB API: FAILED[/red]")
        raise typer.Exit(1)


def main():
    app()


if __name__ == "__main__":
    main()
