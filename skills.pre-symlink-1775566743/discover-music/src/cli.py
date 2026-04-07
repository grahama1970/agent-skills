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

app = typer.Typer(help="Music discovery via MusicBrainz + ListenBrainz with taxonomy integration")
console = Console()


def _output_artist_results(
    results: list,
    json_output: bool,
    title: str,
    bridge_tags: list = None,
    scored: list = None,
):
    """Output artist results as table or JSON with taxonomy and optional scoring."""
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
    # Phase 1: Memory-first context gathering
    ctx = None
    scored = None
    if _DISCOVERY_AVAILABLE:
        ctx = gather_context(f"music similar {artist}", ContentType.MUSIC)
        if ctx.total_hits:
            console.print(f"[dim]{ctx.memory_summary()}[/dim]")

    console.print(f"[dim]Searching for artists similar to '{artist}'...[/dim]")

    # Phase 2: External API calls
    results = lb.get_similar_artists(artist, limit=limit)

    if not results:
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

    # Phase 3: Score + rerank with persona/memory
    if _DISCOVERY_AVAILABLE and ctx and results:
        scored = score_results(
            [{"name": r.name, "mbid": r.mbid, "tags": getattr(r, 'tags', []),
              "description": getattr(r, 'disambiguation', '')} for r in results],
            ctx, ContentType.MUSIC, raw_score_key="similarity"
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

    _output_artist_results(results, json_output, f"Artists similar to {artist}", scored=scored)

    # Phase 4: Store interesting discoveries
    if _DISCOVERY_AVAILABLE and scored:
        stored = store_discoveries(scored, ContentType.MUSIC)
        if stored:
            console.print(f"[dim]Stored {stored} discoveries to memory[/dim]")


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

    # Phase 1: Memory-first context gathering
    ctx = None
    scored = None
    if _DISCOVERY_AVAILABLE:
        ctx = gather_context(f"music {bridge_attr}", ContentType.MUSIC)
        if ctx.total_hits:
            console.print(f"[dim]{ctx.memory_summary()}[/dim]")

    console.print(f"[dim]Searching artists for bridge '{bridge_attr}'...[/dim]")
    tags = taxonomy.get_tags_for_bridge(bridge_attr)
    console.print(f"[dim]Tags: {', '.join(tags[:3])}...[/dim]")

    # Phase 2: External API calls
    results = mb.search_by_bridge(bridge_attr, limit=limit)

    # Phase 3: Score + rerank with persona/memory
    if _DISCOVERY_AVAILABLE and ctx and results:
        scored = score_results(
            [{"name": r.name, "mbid": r.mbid, "tags": getattr(r, 'tags', []),
              "description": getattr(r, 'disambiguation', '')} for r in results],
            ctx, ContentType.MUSIC, raw_score_key="score"
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

    _output_artist_results(results, json_output, f"Artists for Bridge: {bridge_attr}", bridge_tags=[bridge_attr], scored=scored)

    # Phase 4: Store interesting discoveries
    if _DISCOVERY_AVAILABLE and scored:
        stored = store_discoveries(scored, ContentType.MUSIC)
        if stored:
            console.print(f"[dim]Stored {stored} discoveries to memory[/dim]")


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


# Register YouTube commands from separate module
from .cli_youtube import register_youtube_commands
register_youtube_commands(app)


@app.command()
def recommend(
    profile: Optional[str] = typer.Option(None, "--profile", "-p", help="Path to taste profile JSON"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max recommendations"),
    per_artist: int = typer.Option(5, "--per-artist", help="Similar artists per top artist"),
    no_bridges: bool = typer.Option(False, "--no-bridges", help="Skip bridge attribute search"),
    json_output: bool = typer.Option(False, "--json", "-j", help="Output as JSON"),
    queue: bool = typer.Option(False, "--queue", "-q", help="Append recommendations to learn-artist queue"),
    queue_path: Optional[str] = typer.Option(None, "--queue-path", help="Custom queue.txt path"),
):
    """
    Recommend artists based on taste profile from ingest-yt-history.

    Reads the taste profile, finds similar artists via MusicBrainz/ListenBrainz,
    and optionally queues them for learn-artist training.
    """
    from . import recommend as rec

    # Phase 1: Memory-first context gathering
    ctx = None
    scored = None
    if _DISCOVERY_AVAILABLE:
        ctx = gather_context("music recommendations taste profile", ContentType.MUSIC)
        if ctx.total_hits:
            console.print(f"[dim]{ctx.memory_summary()}[/dim]")

    try:
        result = rec.recommend_from_profile(
            profile_path=profile,
            limit=limit,
            per_artist=per_artist,
            use_bridges=not no_bridges,
        )
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(code=1)

    # Phase 3: Score recommendations with persona/memory
    if _DISCOVERY_AVAILABLE and ctx and result.recommendations:
        scored = score_results(
            [{"name": r.name, "tags": r.tags, "description": r.reason} for r in result.recommendations],
            ctx, ContentType.MUSIC, raw_score_key="similarity"
        )
        # Re-weight original recommendations by persona score
        name_to_score = {s.item.get("name", "").lower(): s for s in scored}
        for r in result.recommendations:
            persona_score = name_to_score.get(r.name.lower())
            if persona_score:
                # Blend original similarity with persona-guided score
                r.similarity = 0.6 * r.similarity + 0.4 * persona_score.final_score
                if persona_score.bridge_tags and not r.bridge_tags:
                    r.bridge_tags = persona_score.bridge_tags
        # Re-sort by blended score
        result.recommendations.sort(key=lambda r: r.similarity, reverse=True)

    if json_output:
        output = {
            "recommendations": [
                {
                    "name": r.name,
                    "mbid": r.mbid,
                    "tags": r.tags,
                    "similarity": round(r.similarity, 3),
                    "source_artist": r.source_artist,
                    "bridge_tags": r.bridge_tags,
                    "reason": r.reason,
                }
                for r in result.recommendations
            ],
            "profile_summary": result.profile_summary,
            "count": len(result.recommendations),
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
    else:
        # Print profile summary
        summary = result.profile_summary
        console.print(f"[bold]Recommendations based on taste profile[/bold]")
        console.print(f"[dim]Top artists: {', '.join(summary.get('top_artists', [])[:3])}[/dim]")
        console.print(f"[dim]Top bridges: {', '.join(summary.get('top_bridges', []))}[/dim]")
        console.print(f"[dim]Total tracks in history: {summary.get('total_tracks', '?')}[/dim]\n")

        if not result.recommendations:
            console.print("[yellow]No recommendations found. Try enriching your history first.[/yellow]")
            return

        table = Table(title="Recommended Artists")
        table.add_column("#", style="dim", width=3)
        table.add_column("Artist", style="cyan")
        table.add_column("Score", justify="right", style="green")
        table.add_column("Reason", style="dim")
        table.add_column("Bridges", style="dim")

        for i, r in enumerate(result.recommendations, 1):
            bridges = ", ".join(r.bridge_tags[:2]) if r.bridge_tags else "-"
            table.add_row(
                str(i),
                r.name,
                f"{r.similarity:.2f}",
                r.reason[:40],
                bridges,
            )

        console.print(table)

    # Phase 4: Store interesting discoveries
    if _DISCOVERY_AVAILABLE and scored:
        stored = store_discoveries(scored, ContentType.MUSIC)
        if stored:
            console.print(f"[dim]Stored {stored} discoveries to memory[/dim]")

    # Queue for training if requested
    if queue:
        artists_to_queue = [r.name for r in result.recommendations]
        added = rec.append_to_training_queue(artists_to_queue, queue_path=queue_path)
        console.print(f"\n[green]Queued {added} new artists for learn-artist training[/green]")
        if added < len(artists_to_queue):
            console.print(f"[dim]({len(artists_to_queue) - added} already in queue)[/dim]")


def main():
    monitor = TaskClient("discover-music", total=1) if TaskClient else None
    try:
        app()
    finally:
        if monitor:
            monitor.update(item="done")
            monitor.finish()


if __name__ == "__main__":
    main()
