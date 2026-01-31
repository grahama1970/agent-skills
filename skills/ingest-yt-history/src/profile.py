#!/usr/bin/env python3
"""
Music Taste Profile Builder with HMT taxonomy analysis.

Task 8: Build a comprehensive taste profile from the user's music history,
extracting bridge attributes, domains, thematic weights, and listening patterns.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, TextIO, TypedDict

from .sync_memory import TaxonomyConfig, extract_taxonomy


class ArtistProfile(TypedDict):
    """Profile for a single artist."""
    artist: str
    count: int
    bridges: list[str]


class ListeningPatterns(TypedDict):
    """Listening patterns breakdown."""
    by_hour: dict[str, int]
    by_day: dict[str, int]
    by_bridge: dict[str, int]


class DateRange(TypedDict):
    """Date range for the profile."""
    start: str
    end: str


class TasteProfile(TypedDict):
    """Complete taste profile structure."""
    top_bridge_attributes: list[str]
    top_domains: list[str]
    top_thematic_weights: list[str]
    top_artists: list[ArtistProfile]
    listening_patterns: ListeningPatterns
    total_tracks: int
    date_range: DateRange


@dataclass
class ProfileBuilder:
    """Builds a taste profile from music history entries."""

    config: TaxonomyConfig = field(default_factory=TaxonomyConfig)

    # Counters for aggregation
    bridge_counts: Counter = field(default_factory=Counter)
    domain_counts: Counter = field(default_factory=Counter)
    thematic_counts: Counter = field(default_factory=Counter)
    artist_counts: Counter = field(default_factory=Counter)
    artist_bridges: dict[str, set[str]] = field(default_factory=dict)
    hour_counts: Counter = field(default_factory=Counter)
    day_counts: Counter = field(default_factory=Counter)

    # Track date range
    timestamps: list[str] = field(default_factory=list)
    total_tracks: int = 0

    def process_entry(self, entry: dict[str, Any]) -> None:
        """Process a single music history entry.

        Args:
            entry: A parsed music history entry with fields like
                   artist, title, tags, ts, products, etc.
        """
        self.total_tracks += 1

        # Extract taxonomy data
        bridge_attributes, collection_tags = extract_taxonomy(entry, self.config)

        # Count bridges
        for bridge in bridge_attributes:
            self.bridge_counts[bridge] += 1

        # Count domains
        if "domain" in collection_tags:
            self.domain_counts[collection_tags["domain"]] += 1

        # Count thematic weights
        if "thematic_weight" in collection_tags:
            self.thematic_counts[collection_tags["thematic_weight"]] += 1

        # Count artists and track their bridges
        artist = entry.get("artist") or entry.get("channel") or "Unknown"
        if artist and artist != "Unknown":
            self.artist_counts[artist] += 1
            if artist not in self.artist_bridges:
                self.artist_bridges[artist] = set()
            self.artist_bridges[artist].update(bridge_attributes)

        # Extract timestamp patterns
        ts = entry.get("ts", "")
        if ts:
            self.timestamps.append(ts)
            try:
                # Parse ISO 8601 timestamp
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                # Count by hour (24-hour format)
                hour = str(dt.hour)
                self.hour_counts[hour] += 1
                # Count by day name
                day_name = dt.strftime("%A")
                self.day_counts[day_name] += 1
            except (ValueError, AttributeError):
                pass

    def build(self, top_n: int = 10) -> TasteProfile:
        """Build the complete taste profile.

        Args:
            top_n: Number of top items to include in each category.

        Returns:
            TasteProfile with all aggregated data.
        """
        # Get top bridges
        top_bridges = [b for b, _ in self.bridge_counts.most_common(top_n)]

        # Get top domains
        top_domains = [d for d, _ in self.domain_counts.most_common(top_n)]

        # Get top thematic weights
        top_thematic = [t for t, _ in self.thematic_counts.most_common(top_n)]

        # Build top artists with their bridges
        top_artists: list[ArtistProfile] = []
        for artist, count in self.artist_counts.most_common(top_n):
            bridges = list(self.artist_bridges.get(artist, set()))
            top_artists.append(ArtistProfile(
                artist=artist,
                count=count,
                bridges=bridges,
            ))

        # Build listening patterns
        # Get top hours (sorted by count)
        top_hours = {
            str(h): c
            for h, c in self.hour_counts.most_common(top_n)
        }

        # Get top days (sorted by count)
        top_days = {
            d: c
            for d, c in self.day_counts.most_common(top_n)
        }

        # Bridge counts as dict
        bridge_pattern = dict(self.bridge_counts.most_common(top_n))

        listening_patterns = ListeningPatterns(
            by_hour=top_hours,
            by_day=top_days,
            by_bridge=bridge_pattern,
        )

        # Calculate date range
        date_range = DateRange(start="", end="")
        if self.timestamps:
            sorted_ts = sorted(self.timestamps)
            # Extract just the date part (YYYY-MM-DD)
            try:
                start_dt = datetime.fromisoformat(sorted_ts[0].replace("Z", "+00:00"))
                end_dt = datetime.fromisoformat(sorted_ts[-1].replace("Z", "+00:00"))
                date_range = DateRange(
                    start=start_dt.strftime("%Y-%m-%d"),
                    end=end_dt.strftime("%Y-%m-%d"),
                )
            except (ValueError, IndexError):
                pass

        return TasteProfile(
            top_bridge_attributes=top_bridges,
            top_domains=top_domains,
            top_thematic_weights=top_thematic,
            top_artists=top_artists,
            listening_patterns=listening_patterns,
            total_tracks=self.total_tracks,
            date_range=date_range,
        )


def _is_music_entry(entry: dict[str, Any]) -> bool:
    """Check if an entry is a music entry.

    Args:
        entry: Parsed history entry.

    Returns:
        True if the entry appears to be music.
    """
    # Check products for YouTube Music
    products = entry.get("products", [])
    if "YouTube Music" in products:
        return True

    # Check if it has an artist field
    if entry.get("artist"):
        return True

    # Check tags for music-related keywords
    tags = entry.get("tags", [])
    music_keywords = {"music", "song", "audio", "album", "track"}
    for tag in tags:
        if tag.lower() in music_keywords:
            return True

    return False


def build_profile(
    input_path: str | Path,
    output_path: str | Path | None = None,
    music_only: bool = True,
    top_n: int = 10,
    config: TaxonomyConfig | None = None,
) -> TasteProfile:
    """Build a taste profile from music history.

    Args:
        input_path: Path to parsed YouTube history JSONL file.
        output_path: Optional path to write profile JSON. If None, writes to
                     ~/.pi/ingest-yt-history/profile.json
        music_only: If True, only process music entries.
        top_n: Number of top items to include in each category.
        config: Optional TaxonomyConfig for custom mappings.

    Returns:
        TasteProfile dict with all aggregated data.

    Example:
        >>> profile = build_profile("music_history.jsonl")
        >>> profile["top_bridge_attributes"]
        ['Fragility', 'Resilience']
    """
    if config is None:
        config = TaxonomyConfig()

    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    # Build the profile
    builder = ProfileBuilder(config=config)

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Skip non-music entries if music_only is True
            if music_only and not _is_music_entry(entry):
                continue

            builder.process_entry(entry)

    profile = builder.build(top_n=top_n)

    # Determine output path
    if output_path is None:
        output_dir = Path.home() / ".pi" / "ingest-yt-history"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "profile.json"
    else:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write profile to JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)

    return profile


def main() -> None:
    """CLI entry point for profile command."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Build taste profile from YouTube music history"
    )
    parser.add_argument(
        "command",
        choices=["build"],
        help="Command to run",
    )
    parser.add_argument(
        "input_path",
        nargs="?",
        help="Path to parsed YouTube history JSONL file",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output JSON file path (default: ~/.pi/ingest-yt-history/profile.json)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="include_all",
        help="Include non-music entries",
    )
    parser.add_argument(
        "-n", "--top",
        type=int,
        default=10,
        help="Number of top items per category (default: 10)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output profile to stdout as JSON",
    )

    args = parser.parse_args()

    if args.command == "build":
        if not args.input_path:
            parser.error("input_path is required for build command")

        try:
            profile = build_profile(
                args.input_path,
                output_path=args.output,
                music_only=not args.include_all,
                top_n=args.top,
            )

            if args.json:
                print(json.dumps(profile, indent=2))
            else:
                # Print summary
                print(f"Profile built successfully!")
                print(f"Total tracks: {profile['total_tracks']}")
                print(f"Date range: {profile['date_range']['start']} to {profile['date_range']['end']}")
                print(f"\nTop bridge attributes: {', '.join(profile['top_bridge_attributes'])}")
                print(f"Top domains: {', '.join(profile['top_domains'])}")
                print(f"Top thematic weights: {', '.join(profile['top_thematic_weights'])}")
                print(f"\nTop artists:")
                for artist_info in profile["top_artists"][:5]:
                    bridges = ", ".join(artist_info["bridges"]) if artist_info["bridges"] else "none"
                    print(f"  {artist_info['artist']}: {artist_info['count']} plays (bridges: {bridges})")

                # Print output location
                output_loc = args.output or str(Path.home() / ".pi" / "ingest-yt-history" / "profile.json")
                print(f"\nProfile saved to: {output_loc}")

        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
