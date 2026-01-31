#!/usr/bin/env python3
"""
CLI for discover-music skill.

Usage:
    python -m discover_music.cli similar "Chelsea Wolfe"
    python -m discover_music.cli trending --range week
    python -m discover_music.cli search-tag "doom metal"
    python -m discover_music.cli bridge Corruption
"""

import json
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import listenbrainz_client as lb
from . import musicbrainz_client as mb
from . import taxonomy

app = typer.Typer(help="Music discovery via MusicBrainz + ListenBrainz with taxonomy integration")
console = Console()


def _output_artist_results(
    results: list,
    json_output: bool,
    title: str,
    bridge_tags: list = None
):
    """Output artist results as table or JSON with taxonomy."""
    if json_output:
        output = {
            "results": [
                {"name": r.name, "mbid": r.mbid, "tags": getattr(r, 'tags', []),
                 "similarity": getattr(r, 'similarity', None),
                 "listen_count": getattr(r, 'listen_count', None)}
                for r in results
            ],
            "count": len(results),
            "taxonomy": taxonomy.build_taxonomy_output(
                [{"tags": getattr(r, 'tags', []), "disambiguation": getattr(r, 'disambiguation', '')} for r in results],
                bridge_tags=bridge_tags
            ),
        }
        print(json.dumps(output, indent=2))
        return

    if not results:
        console.print("[yellow]No artists found.[/yellow]")
        return

    table = Table(title=title)
    table.add_column("Artist", style="cyan")
    table.add_column("MBID", style="dim")
    table.add_column("Info", justify="right")

    for r in results:
        info = ""
        if hasattr(r, 'similarity') and r.similarity:
            info = f"{r.similarity:.2f}"
        elif hasattr(r, 'listen_count') and r.listen_count:
            info = f"{r.listen_count:,}"
        elif hasattr(r, 'score') and r.score:
            info = f"{r.score}"
        table.add_row(r.name, r.mbid[:8] + "..." if r.mbid else "-", info or "-")

    console.print(table)

    # Show taxonomy in non-JSON mode too
    if results:
        tax = taxonomy.build_taxonomy_output(
            [{"tags": getattr(r, 'tags', []), "disambiguation": getattr(r, 'disambiguation', '')} for r in results],
            bridge_tags
        )
        if tax["bridge_tags"]:
            console.print(f"\n[dim]Bridge tags: {', '.join(tax['bridge_tags'])}[/dim]")


@app.command()
def similar(
    artist: str = typer.Argument(..., help="Artist name to find similar artists for"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Find artists similar to the given artist."""
    console.print(f"[dim]Searching for artists similar to '{artist}'...[/dim]")

    # Try ListenBrainz first (better similarity data)
    results = lb.get_similar_artists(artist, limit=limit)

    if not results:
        # Fallback to MusicBrainz tag-based similarity
        console.print("[dim]ListenBrainz: no results, trying MusicBrainz tags...[/dim]")
        mb_artist = mb.search_artists(query=artist, limit=1)
        if mb_artist:
            full_artist = mb.get_artist(mb_artist[0].mbid)
            if full_artist:
                mb_results = mb.get_similar_by_tags(full_artist, limit=limit)
                results = [
                    lb.LBArtist(name=a.name, mbid=a.mbid, similarity=a.score / 100)
                    for a in mb_results
                ]

    _output_artist_results(results, json_output, f"Artists similar to {artist}")


@app.command()
def trending(
    time_range: str = typer.Option("week", "--range", "-r", help="week, month, year, all_time"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get trending artists from ListenBrainz."""
    console.print(f"[dim]Fetching trending artists ({time_range})...[/dim]")

    results = lb.get_trending_artists(time_range=time_range, limit=limit)

    if json_output:
        print(json.dumps([
            {"name": r.name, "mbid": r.mbid, "listen_count": r.listen_count}
            for r in results
        ]))
        return

    if not results:
        console.print("[yellow]No trending data available.[/yellow]")
        return

    table = Table(title=f"Trending Artists ({time_range})")
    table.add_column("Artist", style="cyan")
    table.add_column("Listens", justify="right", style="green")

    for r in results:
        table.add_row(r.name, f"{r.listen_count:,}")

    console.print(table)


@app.command("search-tag")
def search_tag(
    tag: str = typer.Argument(..., help="Genre/style tag to search"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Search artists by genre/style tag via MusicBrainz."""
    console.print(f"[dim]Searching artists tagged '{tag}'...[/dim]")

    results = mb.search_by_tag(tag, limit=limit)

    if json_output:
        print(json.dumps([
            {"name": r.name, "mbid": r.mbid, "tags": r.tags, "country": r.country}
            for r in results
        ]))
        return

    if not results:
        console.print("[yellow]No artists found for this tag.[/yellow]")
        return

    table = Table(title=f"Artists tagged '{tag}'")
    table.add_column("Artist", style="cyan")
    table.add_column("Country", style="dim")
    table.add_column("Tags", style="dim")

    for r in results:
        tags_str = ", ".join(r.tags[:3]) if r.tags else "-"
        table.add_row(r.name, r.country or "-", tags_str)

    console.print(table)


@app.command()
def bridge(
    bridge_attr: str = typer.Argument(..., help="Bridge attribute (Precision, Resilience, Fragility, Corruption, Loyalty, Stealth)"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Search artists by HMT bridge attribute."""
    valid_bridges = list(taxonomy.BRIDGE_TO_TAGS.keys())
    if bridge_attr not in valid_bridges:
        console.print(f"[red]Invalid bridge. Choose from: {', '.join(valid_bridges)}[/red]")
        sys.exit(1)

    console.print(f"[dim]Searching artists for bridge '{bridge_attr}'...[/dim]")
    tags = taxonomy.get_tags_for_bridge(bridge_attr)
    console.print(f"[dim]Tags: {', '.join(tags[:3])}...[/dim]")

    results = mb.search_by_bridge(bridge_attr, limit=limit)

    _output_artist_results(results, json_output, f"Artists for Bridge: {bridge_attr}", bridge_tags=[bridge_attr])


@app.command()
def fresh(
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get fresh/new releases from ListenBrainz."""
    console.print("[dim]Fetching fresh releases...[/dim]")

    results = lb.explore_fresh_releases(limit=limit)

    if json_output:
        print(json.dumps(results))
        return

    if not results:
        console.print("[yellow]No fresh releases found.[/yellow]")
        return

    table = Table(title="Fresh Releases")
    table.add_column("Release", style="cyan")
    table.add_column("Artist", style="dim")

    for r in results:
        table.add_row(
            r.get("release_name", "Unknown"),
            r.get("artist_name", "Unknown"),
        )

    console.print(table)


@app.command()
def user_top(
    username: str = typer.Argument(..., help="ListenBrainz username"),
    time_range: str = typer.Option("all_time", "--range", "-r", help="week, month, year, all_time"),
    limit: int = typer.Option(10, "--limit", "-n", help="Max results"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
):
    """Get a user's top artists from ListenBrainz."""
    console.print(f"[dim]Fetching top artists for {username}...[/dim]")

    results = lb.get_user_artists(username, time_range=time_range, limit=limit)

    if json_output:
        print(json.dumps([
            {"name": r.name, "mbid": r.mbid, "listen_count": r.listen_count}
            for r in results
        ]))
        return

    if not results:
        console.print("[yellow]No data found for this user.[/yellow]")
        return

    table = Table(title=f"Top Artists for {username} ({time_range})")
    table.add_column("Artist", style="cyan")
    table.add_column("Listens", justify="right", style="green")

    for r in results:
        table.add_row(r.name, f"{r.listen_count:,}")

    console.print(table)


@app.command()
def check():
    """Check API connectivity."""
    console.print("[bold]Checking API connectivity...[/bold]\n")

    # MusicBrainz
    console.print("[dim]Testing MusicBrainz...[/dim]")
    try:
        results = mb.search_artists(query="test", limit=1)
        if results:
            console.print("[green]MusicBrainz: OK[/green]")
        else:
            console.print("[yellow]MusicBrainz: OK (no results)[/yellow]")
    except Exception as e:
        console.print(f"[red]MusicBrainz: FAIL - {e}[/red]")

    # ListenBrainz
    console.print("[dim]Testing ListenBrainz...[/dim]")
    try:
        results = lb.get_trending_artists(limit=1)
        if results:
            console.print("[green]ListenBrainz: OK[/green]")
        else:
            console.print("[yellow]ListenBrainz: OK (no results)[/yellow]")
    except Exception as e:
        console.print(f"[red]ListenBrainz: FAIL - {e}[/red]")

    # Token status
    if lb.is_authenticated():
        console.print("[green]ListenBrainz token: Configured[/green]")
    else:
        console.print("[dim]ListenBrainz token: Not set (public API only)[/dim]")


def main():
    app()


if __name__ == "__main__":
    main()
