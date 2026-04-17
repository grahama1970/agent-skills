"""Ingest bridge for consume-music.

Imports music entries from ingest-yt-history/history.jsonl into the
consume-music registry. Filters for YouTube Music URLs and extracts
artist/track from title. Applies basic HMT bridge classification.
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from consume_common.registry import ContentRegistry
import typer

# ── TaskClient integration ──────────────────────────────────────────────────
try:
    sys.path.insert(0, str(Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

console = Console()

# Basic HMT bridge classification heuristics based on artist/genre keywords
# These are intentionally broad — the real classification happens in /memory
BRIDGE_HEURISTICS: dict[str, list[str]] = {
    "Fragility": [
        "chelsea wolfe", "daughter", "phoebe bridgers", "mazzy star",
        "cocteau twins", "this mortal coil", "dead can dance",
        "acoustic", "folk", "ethereal", "shoegaze",
    ],
    "Resilience": [
        "sabaton", "two steps from hell", "powerwolf", "amon amarth",
        "manowar", "dragonforce", "blind guardian",
        "epic", "triumph", "power metal", "orchestral",
    ],
    "Corruption": [
        "nine inch nails", "ministry", "godflesh", "author & punisher",
        "industrial", "noise", "harsh", "distorted",
    ],
    "Stealth": [
        "brian eno", "aphex twin", "boards of canada", "tim hecker",
        "grouper", "stars of the lid",
        "ambient", "drone", "minimalist",
    ],
    "Transcendence": [
        "mogwai", "explosions in the sky", "godspeed you", "sigur ros",
        "mono ", "russian circles",
        "post-rock", "post rock", "crescendo",
    ],
    "Precision": [
        "meshuggah", "animals as leaders", "periphery", "tool",
        "dream theater", "between the buried",
        "progressive", "prog", "djent", "technical", "math rock",
    ],
    "Defiance": [
        "bell witch", "pallbearer", "yob", "neurosis",
        "converge", "code orange",
        "doom", "sludge", "hardcore",
    ],
    "Loyalty": [
        "wardruna", "heilung", "enya",
        "choral", "gregorian", "ceremonial", "sacred",
    ],
}

# Domain classification
DOMAIN_HEURISTICS: dict[str, list[str]] = {
    "Dark_Folk": ["folk", "neofolk", "acoustic", "chelsea wolfe", "wardruna"],
    "Doom_Metal": ["doom", "sludge", "bell witch", "pallbearer", "yob", "funeral"],
    "Epic_Metal": ["sabaton", "powerwolf", "amon amarth", "dragonforce", "blind guardian", "manowar"],
    "Epic_Orchestral": ["two steps from hell", "hans zimmer", "soundtrack", "score", "orchestral"],
    "Post_Rock": ["mogwai", "explosions in the sky", "godspeed", "sigur ros", "mono ", "russian circles"],
    "Atmospheric_Ambient": ["brian eno", "aphex twin", "boards of canada", "tim hecker", "ambient", "drone"],
    "Progressive_Metal": ["tool", "dream theater", "meshuggah", "periphery", "animals as leaders"],
    "Pop": ["pop", "indie pop", "synth pop"],
}


def classify_bridges(title: str, artist: str) -> list[str]:
    """Classify a track's HMT bridge attributes from title/artist."""
    combined = f"{title} {artist}".lower()
    bridges = []
    for bridge, keywords in BRIDGE_HEURISTICS.items():
        if any(kw in combined for kw in keywords):
            bridges.append(bridge)
    return bridges


def classify_domain(title: str, artist: str) -> str:
    """Classify a track's genre domain from title/artist."""
    combined = f"{title} {artist}".lower()
    for domain, keywords in DOMAIN_HEURISTICS.items():
        if any(kw in combined for kw in keywords):
            return domain
    return ""


def extract_artist_track(title: str) -> tuple[str, str]:
    """Extract artist and track name from YouTube Music title.

    Common formats:
      "Artist - Track Title"
      "Artist - Track Title (Official Video)"
      "Track Title"
    """
    # Remove common suffixes
    clean = re.sub(
        r"\s*\((?:Official\s+)?(?:Music\s+)?(?:Video|Audio|Lyric|Live|Playthrough|MixWave)\).*$",
        "", title, flags=re.IGNORECASE
    )
    clean = re.sub(r"\s*\[.*?\]\s*$", "", clean)

    # Split on " - " (most common YouTube Music format)
    if " - " in clean:
        parts = clean.split(" - ", 1)
        return parts[0].strip(), parts[1].strip()

    # No separator — return title as track, unknown artist
    return "", clean.strip()


def sync_from_ingest(
    ingest_root: Optional[Path] = None,
    registry_path: Optional[Path] = None,
) -> int:
    """Import music entries from ingest-yt-history into registry.

    Args:
        ingest_root: Path to ingest-yt-history data dir
        registry_path: Path to music registry

    Returns:
        Number of entries imported
    """
    if not ingest_root:
        ingest_root = Path.home() / ".pi" / "ingest-yt-history"

    if not registry_path:
        registry_path = Path.home() / ".pi" / "consume-music" / "registry.json"

    history_path = ingest_root / "history.jsonl"
    if not history_path.exists():
        console.print(f"[red]History not found: {history_path}[/red]")
        console.print("[dim]Run /ingest-yt-history first to import YouTube watch history.[/dim]")
        return 0

    registry = ContentRegistry(registry_path)

    # Build set of already-imported video IDs
    existing = registry.list_content("music")
    existing_ids = {e.get("metadata", {}).get("video_id") for e in existing}

    imported = 0
    skipped = 0

    # Count lines for progress tracking
    _total_lines = sum(1 for _ in open(history_path, "r", encoding="utf-8"))
    monitor = TaskClient("consume-music-sync", total=_total_lines) if TaskClient else None

    with open(history_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
            except json.JSONDecodeError:
                continue

            url = entry.get("url", "")
            # Only import YouTube Music entries
            if "music.youtube.com" not in url:
                continue

            video_id = entry.get("video_id", "")
            if video_id in existing_ids:
                skipped += 1
                continue

            title = entry.get("title", "")
            artist, track = extract_artist_track(title)
            bridges = classify_bridges(title, artist)
            domain = classify_domain(title, artist)

            registry.add_content({
                "title": title,
                "type": "music",
                "source_path": str(history_path),
                "metadata": {
                    "video_id": video_id,
                    "artist": artist,
                    "track": track,
                    "url": url,
                    "timestamp": entry.get("ts", ""),
                    "bridge_attributes": bridges,
                    "domain": domain,
                },
            })

            existing_ids.add(video_id)
            imported += 1
            if monitor:
                monitor.update(item=title[:40])

    if monitor:
        monitor.finish()
    console.print(f"[green]Imported {imported} music entries ({skipped} already existed)[/green]")

    # Post-hook: Learn imported tracks to memory with HMT tags
    if imported > 0:
        try:
            from memory_integration import learn_annotation
            learned = 0
            # Re-read latest entries to learn them
            all_music = registry.list_content("music")
            for entry in all_music[-imported:]:
                meta = entry.get("metadata", {})
                learn_annotation(
                    track_title=meta.get("track", entry.get("title", "")),
                    artist=meta.get("artist", ""),
                    annotation=f"Synced from ingest-yt-history. Domain: {meta.get('domain', 'unknown')}",
                    hmt_tags=meta.get("bridge_attributes", []),
                )
                learned += 1
            if learned:
                console.print(f"[dim]  Stored {learned} entries to memory[/dim]")
        except ImportError:
            pass
        except Exception as e:
            console.print(f"[dim]  Memory sync skipped: {e}[/dim]")

    return imported


def main(
    ingest_root: Optional[str] = typer.Option(None, help="Override ingest-yt-history path"),
):
    """CLI entry point for sync."""
    sync_from_ingest(ingest_root=ingest_root)


if __name__ == "__main__":
    main()
