"""Search functionality for consume-music.

Searches ingested music by title, artist, domain, or bridge attribute.
Used by the dream pipeline to find soundtrack anchors from Horus's listening history.
"""

import json
import re
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from consume_common.registry import ContentRegistry
import typer
from loguru import logger

console = Console()

# HMT bridge keywords for fuzzy matching
BRIDGE_KEYWORDS: dict[str, list[str]] = {
    "Precision": ["technical", "polyrhythm", "algorithmic", "math", "prog", "complex"],
    "Resilience": ["triumphant", "epic", "enduring", "powerful", "anthem", "march"],
    "Fragility": ["delicate", "acoustic", "breaking", "soft", "ethereal", "tender"],
    "Corruption": ["distorted", "industrial", "harsh", "noise", "chaos", "heavy"],
    "Loyalty": ["ceremonial", "choral", "sacred", "devotion", "oath"],
    "Stealth": ["ambient", "drone", "minimalist", "atmospheric", "dark", "subtle"],
    "Transcendence": ["post-rock", "shoegaze", "expansive", "reverb", "layered"],
    "Defiance": ["aggressive", "rebellion", "punk", "thrash", "protest", "rage"],
}

# Domain keywords
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "Dark_Folk": ["folk", "acoustic", "dark", "neofolk"],
    "Doom_Metal": ["doom", "sludge", "slow", "heavy", "funeral"],
    "Epic_Metal": ["metal", "power", "symphonic", "epic"],
    "Epic_Orchestral": ["orchestral", "cinematic", "score", "soundtrack", "classical"],
    "Post_Rock": ["post-rock", "postrock", "crescendo", "instrumental"],
    "Atmospheric_Ambient": ["ambient", "atmospheric", "drone", "electronic", "synth"],
    "Progressive_Metal": ["progressive", "prog", "djent", "technical"],
    "Pop": ["pop", "indie", "alternative"],
}


def search_music(
    query: str,
    artist: Optional[str] = None,
    bridge: Optional[str] = None,
    domain: Optional[str] = None,
    limit: int = 10,
    registry_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Search music registry by title, artist, bridge, or domain.

    Args:
        query: Search query (matches title, artist, metadata)
        artist: Filter by artist name
        bridge: Filter by HMT bridge attribute
        domain: Filter by genre/domain
        limit: Maximum results
        registry_path: Override registry path

    Returns:
        List of matching music entries
    """
    # Pre-hook: Recall prior annotations from memory
    try:
        from memory_integration import recall_prior_annotations
        prior = recall_prior_annotations(query, k=5)
        if prior:
            console.print("[dim]  Recalled prior annotations from memory[/dim]")
    except ImportError:
        pass
    except Exception as e:
        logger.debug("value lookup failed: {}", e)

    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-music" / "registry.json"

    if not registry_path.exists():
        console.print("[yellow]Music registry not found. Run './run.sh sync' first.[/yellow]")
        return []

    registry = ContentRegistry(registry_path)
    all_music = registry.list_content("music")

    if not all_music:
        console.print("[yellow]No music in registry. Run './run.sh sync' first.[/yellow]")
        return []

    query_lower = query.lower()
    results = []

    for entry in all_music:
        title = entry.get("title", "").lower()
        entry_artist = entry.get("metadata", {}).get("artist", "").lower()
        entry_bridges = entry.get("metadata", {}).get("bridge_attributes", [])
        entry_domain = entry.get("metadata", {}).get("domain", "").lower()

        # Filter by artist
        if artist and artist.lower() not in entry_artist:
            continue

        # Filter by bridge
        if bridge and bridge not in entry_bridges:
            continue

        # Filter by domain
        if domain and domain.lower() not in entry_domain:
            continue

        # Score relevance
        score = 0.0
        if query_lower in title:
            score += 2.0
        if query_lower in entry_artist:
            score += 1.5

        # Check bridge keyword match
        for bridge_name, keywords in BRIDGE_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                if bridge_name in entry_bridges:
                    score += 1.0

        # Check domain keyword match
        for domain_name, keywords in DOMAIN_KEYWORDS.items():
            if any(kw in query_lower for kw in keywords):
                if domain_name.lower() in entry_domain:
                    score += 0.8

        # Partial word match in title
        query_words = query_lower.split()
        for word in query_words:
            if len(word) > 2 and word in title:
                score += 0.5

        if score > 0:
            results.append({
                "content_id": entry["content_id"],
                "title": entry.get("title", "Unknown"),
                "artist": entry.get("metadata", {}).get("artist", "Unknown"),
                "domain": entry.get("metadata", {}).get("domain", ""),
                "bridge_attributes": entry_bridges,
                "url": entry.get("metadata", {}).get("url", ""),
                "score": round(score, 2),
            })

    # Sort by score descending
    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:limit]

    console.print(f"[green]Found {len(results)} matches for '{query}'[/green]")
    return results


def main(
    query: str = typer.Argument(..., help="Search query"),
    artist: Optional[str] = typer.Option(None, help="Filter by artist"),
    bridge: Optional[str] = typer.Option(None, help="Filter by HMT bridge attribute"),
    domain: Optional[str] = typer.Option(None, help="Filter by genre/domain"),
    limit: int = typer.Option(10, help="Max results (default: 10)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """CLI entry point for search."""

    results = search_music(
        query=query,
        artist=artist,
        bridge=bridge,
        domain=domain,
        limit=limit,
    )

    if json:
        print(json.dumps({"results": results}, indent=2))
    else:
        if not results:
            console.print("[yellow]No matches found[/yellow]")
            return

        for r in results:
            bridges = ", ".join(r["bridge_attributes"]) if r["bridge_attributes"] else "untagged"
            console.print(
                f"  [bold]{r['artist']}[/bold] - {r['title']}"
                f"  [dim]({r['domain'] or 'unknown'}, {bridges})[/dim]"
            )


if __name__ == "__main__":
    main()
