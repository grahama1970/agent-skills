#!/usr/bin/env python3
"""
Artist Profile Builder and Memory Exporter.

Builds artist profiles from YouTube music history with instrument classification,
listen counts, and bridge attributes. Exports to /memory for Horus persona recall.

Enables queries like:
    "What is my human's favorite oud player?"
    "Who does my human listen to the most?"
    "What vocalists does my human prefer?"

Usage:
    python -m src.artist_profiles build enriched.jsonl
    python -m src.artist_profiles build enriched.jsonl --export-memory
    python -m src.artist_profiles build enriched.jsonl --export-memory --export-file artists.jsonl
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, TypedDict

from .sync_memory import TaxonomyConfig, extract_taxonomy
import typer


# =============================================================================
# INSTRUMENT CLASSIFICATION (via shared taxonomy)
# =============================================================================

def _get_instrument_classifier():
    """Import the shared instrument taxonomy (lazy load)."""
    try:
        skills_dir = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(skills_dir))
        from common.instrument_taxonomy import classify_artist_instrument, classify_from_subcategory
        return classify_artist_instrument, classify_from_subcategory
    except ImportError:
        return None, None


def _get_learn_artist_db() -> Dict[str, dict]:
    """Load the ARTIST_DB from learn-artist/enrich_taxonomy.py."""
    try:
        learn_artist_dir = Path(__file__).parent.parent.parent / "learn-artist"
        enrich_path = learn_artist_dir / "enrich_taxonomy.py"
        if not enrich_path.exists():
            return {}

        # Import ARTIST_DB from the module
        import importlib.util
        spec = importlib.util.spec_from_file_location("enrich_taxonomy", enrich_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, "ARTIST_DB", {})
    except Exception:
        return {}


def _get_trained_models() -> Dict[str, dict]:
    """Scan trained RVC models for available voice/instrument models."""
    models_root = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "media/music/rvc-models"
    trained = {}

    if not models_root.exists():
        return trained

    for category in ["voice", "instrument"]:
        cat_dir = models_root / category
        if not cat_dir.exists():
            continue
        for model_dir in cat_dir.iterdir():
            if not model_dir.is_dir():
                continue
            meta_path = model_dir / "metadata.json"
            if meta_path.exists():
                try:
                    with open(meta_path) as f:
                        meta = json.load(f)
                    trained[model_dir.name] = {
                        "category": category,
                        "path": str(model_dir),
                        "metadata": meta,
                    }
                except (json.JSONDecodeError, OSError):
                    trained[model_dir.name] = {
                        "category": category,
                        "path": str(model_dir),
                    }

    return trained


# =============================================================================
# ARTIST PROFILE DATA STRUCTURES
# =============================================================================

class ArtistProfileEntry(TypedDict):
    """Rich artist profile for memory export."""
    name: str
    slug: str
    listen_count: int
    instrument: Optional[str]       # e.g., "oud", "vocals", "guitar"
    instrument_family: Optional[str] # e.g., "plucked_strings", "vocals"
    instrument_display: Optional[str]# e.g., "oud player", "vocalist"
    subcategory: Optional[str]       # e.g., "oud-player", "vocalist"
    genres: List[str]
    bridge_attributes: List[str]
    has_trained_model: bool
    model_path: Optional[str]


class InstrumentSummary(TypedDict):
    """Summary of top artists for one instrument type."""
    instrument: str
    instrument_display: str
    family: str
    artists: List[ArtistProfileEntry]


# =============================================================================
# PROFILE BUILDER
# =============================================================================

@dataclass
class ArtistProfileBuilder:
    """Builds rich artist profiles from music history with instrument classification."""

    config: TaxonomyConfig = field(default_factory=TaxonomyConfig)

    # Per-artist aggregation
    artist_counts: Counter = field(default_factory=Counter)
    artist_bridges: Dict[str, set] = field(default_factory=dict)
    artist_genres: Dict[str, Counter] = field(default_factory=dict)
    artist_tags: Dict[str, set] = field(default_factory=dict)

    def process_entry(self, entry: dict) -> None:
        """Process a single music history entry."""
        artist = entry.get("artist") or entry.get("channel") or ""
        if not artist or artist == "Unknown":
            # Fallback: extract from title ("Artist - Song")
            artist = _extract_artist_from_title(entry.get("title", "")) or ""
        if not artist or artist == "Unknown":
            return

        self.artist_counts[artist] += 1

        # Extract taxonomy
        bridges, collection_tags = extract_taxonomy(entry, self.config)

        if artist not in self.artist_bridges:
            self.artist_bridges[artist] = set()
        self.artist_bridges[artist].update(bridges)

        # Collect genres from tags
        if artist not in self.artist_genres:
            self.artist_genres[artist] = Counter()
        for tag in entry.get("tags", []):
            self.artist_genres[artist][tag.lower()] += 1

        # Collect all tags
        if artist not in self.artist_tags:
            self.artist_tags[artist] = set()
        self.artist_tags[artist].update(t.lower() for t in entry.get("tags", []))

    def build(self, top_n: int = 50) -> List[ArtistProfileEntry]:
        """Build artist profiles ranked by listen count."""
        classify_fn, classify_sub_fn = _get_instrument_classifier()
        artist_db = _get_learn_artist_db()
        trained_models = _get_trained_models()

        profiles: List[ArtistProfileEntry] = []

        for artist, count in self.artist_counts.most_common(top_n):
            slug = artist.lower().replace(" ", "-").replace("'", "").replace('"', '')
            bridges = list(self.artist_bridges.get(artist, set()))
            genres = [g for g, _ in self.artist_genres.get(artist, Counter()).most_common(5)]
            tags = list(self.artist_tags.get(artist, set()))

            # Instrument classification
            instrument = None
            instrument_family = None
            instrument_display = None
            subcategory = None

            # Check learn-artist DB first (most reliable)
            db_info = artist_db.get(slug)
            if db_info:
                subcategory = db_info.get("subcategory")
                if not bridges and db_info.get("bridge_tags"):
                    bridges = db_info["bridge_tags"]
                if not genres and db_info.get("genres"):
                    genres = db_info["genres"]

            # Use shared classifier
            if classify_fn:
                info = classify_fn(
                    genres=genres,
                    tags=tags,
                    subcategory=subcategory,
                )
                if info:
                    instrument = info.canonical
                    instrument_family = info.family
                    instrument_display = info.display
                    subcategory = info.subcategory

            # Check for trained model
            has_trained_model = slug in trained_models
            model_path = trained_models.get(slug, {}).get("path")

            profiles.append(ArtistProfileEntry(
                name=artist,
                slug=slug,
                listen_count=count,
                instrument=instrument,
                instrument_family=instrument_family,
                instrument_display=instrument_display,
                subcategory=subcategory,
                genres=genres,
                bridge_attributes=bridges,
                has_trained_model=has_trained_model,
                model_path=model_path,
            ))

        return profiles


def build_instrument_summaries(
    profiles: List[ArtistProfileEntry],
) -> List[InstrumentSummary]:
    """Group profiles by instrument for 'favorite X player' queries."""
    by_instrument: Dict[str, List[ArtistProfileEntry]] = {}

    for p in profiles:
        key = p.get("instrument") or "unknown"
        if key not in by_instrument:
            by_instrument[key] = []
        by_instrument[key].append(p)

    summaries = []
    for instrument, artists in sorted(by_instrument.items()):
        if instrument == "unknown":
            continue
        # Sort by listen count descending
        artists_sorted = sorted(artists, key=lambda a: a["listen_count"], reverse=True)
        if artists_sorted:
            first = artists_sorted[0]
            summaries.append(InstrumentSummary(
                instrument=instrument,
                instrument_display=first.get("instrument_display") or f"{instrument} player",
                family=first.get("instrument_family") or "unknown",
                artists=artists_sorted,
            ))

    return summaries


# =============================================================================
# MEMORY EXPORT
# =============================================================================

def export_artist_to_memory(profile: ArtistProfileEntry) -> dict:
    """
    Format an artist profile as a memory-compatible entry.

    The problem field is structured so semantic search on queries like
    "favorite oud player" or "who does my human listen to" will match.
    """
    name = profile["name"]
    instrument_display = profile.get("instrument_display") or "artist"
    listen_count = profile["listen_count"]
    bridges = profile.get("bridge_attributes", [])
    genres = profile.get("genres", [])
    instrument = profile.get("instrument")

    # Problem: structured for semantic matching
    problem = f"Artist profile: {name} ({instrument_display})"

    # Solution: rich details
    parts = [f"{name} is a {instrument_display}."]
    parts.append(f"Graham listened to {listen_count} of their tracks.")

    if genres:
        parts.append(f"Genres: {', '.join(genres[:4])}.")
    if bridges:
        parts.append(f"Bridge attributes: {', '.join(bridges)}.")
    if profile.get("has_trained_model"):
        parts.append("Trained voice model available.")

    solution = " ".join(parts)

    # Tags: normalized for search
    memory_tags = ["artist_profile"]
    memory_tags.append(name.lower().replace(" ", "_"))
    if instrument:
        memory_tags.append(instrument)
        memory_tags.append(f"{instrument}_player")
    if profile.get("instrument_family"):
        memory_tags.append(profile["instrument_family"])
    for genre in genres[:3]:
        memory_tags.append(genre.replace(" ", "_").replace("-", "_"))
    for bridge in bridges:
        memory_tags.append(bridge.lower())

    return {
        "problem": problem,
        "solution": solution,
        "category": "music",
        "tags": list(set(memory_tags)),
        "bridge_attributes": bridges,
        "collection_tags": {"domain": "Music", "function": "Recall"},
    }


def export_instrument_summary_to_memory(summary: InstrumentSummary) -> dict:
    """
    Format an instrument summary as a memory entry.

    This enables queries like "who is my human's favorite oud player?"
    by creating a ranked list per instrument.
    """
    instrument = summary["instrument"]
    display = summary["instrument_display"]
    artists = summary["artists"]

    problem = f"Human's favorite {display}s ranked by listen count"

    lines = []
    for i, a in enumerate(artists[:10], 1):
        bridges_str = f" ({', '.join(a['bridge_attributes'])})" if a.get("bridge_attributes") else ""
        model_str = " [trained]" if a.get("has_trained_model") else ""
        lines.append(f"{i}. {a['name']} — {a['listen_count']} listens{bridges_str}{model_str}")

    solution = "\n".join(lines)

    memory_tags = [
        "instrument_ranking", "favorites",
        instrument, f"{instrument}_player",
        summary.get("family", ""),
    ]

    return {
        "problem": problem,
        "solution": solution,
        "category": "music",
        "tags": [t for t in set(memory_tags) if t],
        "bridge_attributes": [],
        "collection_tags": {"domain": "Music", "function": "Recall"},
    }


# =============================================================================
# CLI
# =============================================================================

def _is_music_entry(entry: dict) -> bool:
    """Check if an entry is a music entry."""
    if "YouTube Music" in entry.get("products", []):
        return True
    if entry.get("artist"):
        return True
    # music.youtube.com URLs are music
    url = entry.get("url", "")
    if "music.youtube.com" in url:
        return True
    tags = entry.get("tags", [])
    music_keywords = {"music", "song", "audio", "album", "track"}
    return any(tag.lower() in music_keywords for tag in tags)


def _extract_artist_from_title(title: str) -> Optional[str]:
    """
    Extract artist name from a YouTube Music title.

    Common formats:
        "Artist - Song Title"
        "Artist - Song Title (Official Video)"
        "Artist | Song Title"
    """
    if not title:
        return None
    # "Artist - Song" is the dominant format
    for sep in [" - ", " – ", " — ", " | "]:
        if sep in title:
            artist = title.split(sep, 1)[0].strip()
            # Skip if it looks like a non-artist prefix
            skip_prefixes = ("how to", "review", "tutorial", "ep.", "episode")
            if artist.lower().startswith(skip_prefixes):
                continue
            if len(artist) > 1 and len(artist) < 80:
                return artist
    return None


def build_artist_profiles(
    input_path: str | Path,
    output_path: Optional[str | Path] = None,
    export_memory: bool = False,
    export_file: Optional[str | Path] = None,
    top_n: int = 50,
) -> tuple[List[ArtistProfileEntry], List[InstrumentSummary]]:
    """
    Build artist profiles from music history and optionally export to memory.

    Args:
        input_path: Path to parsed YouTube history JSONL.
        output_path: Path to write artist profiles JSON.
        export_memory: If True, export to /memory via MemoryClient.
        export_file: If set, write memory JSONL to this file.
        top_n: Number of top artists to profile.

    Returns:
        Tuple of (artist profiles, instrument summaries).
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Build profiles
    builder = ArtistProfileBuilder()
    with open(input_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if _is_music_entry(entry):
                builder.process_entry(entry)

    profiles = builder.build(top_n=top_n)
    summaries = build_instrument_summaries(profiles)

    # Write profiles JSON
    if output_path is None:
        output_dir = Path.home() / ".pi" / "ingest-yt-history"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "artist_profiles.json"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    output_data = {
        "artists": profiles,
        "instrument_summaries": [
            {
                "instrument": s["instrument"],
                "instrument_display": s["instrument_display"],
                "family": s["family"],
                "top_artist": s["artists"][0]["name"] if s["artists"] else None,
                "count": len(s["artists"]),
            }
            for s in summaries
        ],
        "total_artists": len(profiles),
    }

    with open(output_path, "w") as f:
        json.dump(output_data, f, indent=2)

    # Memory export
    memory_entries = []
    for profile in profiles:
        memory_entries.append(export_artist_to_memory(profile))
    for summary in summaries:
        memory_entries.append(export_instrument_summary_to_memory(summary))

    if export_file:
        export_file = Path(export_file)
        export_file.parent.mkdir(parents=True, exist_ok=True)
        with open(export_file, "w") as f:
            for entry in memory_entries:
                f.write(json.dumps(entry) + "\n")
        print(f"Wrote {len(memory_entries)} memory entries to {export_file}", file=sys.stderr)

    if export_memory:
        _export_to_memory_service(memory_entries)

    return profiles, summaries


def _export_to_memory_service(entries: List[dict]) -> None:
    """Export entries to memory via MemoryClient."""
    try:
        skills_dir = Path(__file__).parent.parent.parent
        sys.path.insert(0, str(skills_dir))
        from common.memory_client import MemoryClient, MemoryScope

        client = MemoryClient(scope=MemoryScope.HORUS_LORE, use_python_api=True)
        results = client.batch_learn(
            [
                {
                    "problem": e["problem"],
                    "solution": e["solution"],
                    "tags": e["tags"],
                }
                for e in entries
            ],
            concurrency=4,
        )
        success = sum(1 for r in results if r.success)
        print(f"Exported {success}/{len(entries)} entries to memory", file=sys.stderr)
    except Exception as e:
        print(f"Memory export failed: {e}", file=sys.stderr)
        print("Entries are still saved to the export file if --export-file was used.", file=sys.stderr)


def main(
    command: str = typer.Argument(..., help="Command"),
    input_path: str = typer.Argument(..., help="Path to parsed YouTube history JSONL"),
    o: Optional[str] = typer.Option(None, help="Output JSON file path"),
    n: int = typer.Option(50, help="Top N artists (default: 50)"),
    export_memory: bool = typer.Option(False, help="Export to /memory service"),
    export_file: Optional[str] = typer.Option(None, help="Write memory JSONL to file"),
    as_json: bool = typer.Option(False, "--json", help="Print JSON to stdout"),
):
    """CLI entry point."""

    if command == "build":
        profiles, summaries = build_artist_profiles(
            input_path,
            output_path=output,
            export_memory=export_memory,
            export_file=export_file,
            top_n=top,
        )

        if json:
            print(json.dumps({
                "artists": profiles,
                "instrument_summaries": [
                    {"instrument": s["instrument"], "display": s["instrument_display"],
                     "top": s["artists"][0]["name"] if s["artists"] else None,
                     "count": len(s["artists"])}
                    for s in summaries
                ],
            }, indent=2))
        else:
            print(f"Built {len(profiles)} artist profiles")
            print(f"Instrument summaries: {len(summaries)}")

            # Show top 5 overall
            print(f"\nTop artists:")
            for p in profiles[:5]:
                inst = f" [{p.get('instrument_display', '?')}]" if p.get("instrument") else ""
                model = " [trained]" if p.get("has_trained_model") else ""
                bridges = f" ({', '.join(p['bridge_attributes'])})" if p.get("bridge_attributes") else ""
                print(f"  {p['name']}: {p['listen_count']} listens{inst}{bridges}{model}")

            # Show instrument rankings
            if summaries:
                print(f"\nBy instrument:")
                for s in summaries[:10]:
                    top = s["artists"][0]
                    print(f"  {s['instrument_display']}: {top['name']} ({top['listen_count']} listens)")

            output_loc = output or str(Path.home() / ".pi" / "ingest-yt-history" / "artist_profiles.json")
            print(f"\nProfiles saved to: {output_loc}")


if __name__ == "__main__":
    main()
