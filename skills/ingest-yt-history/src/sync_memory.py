#!/usr/bin/env python3
"""
Sync music entries with HMT taxonomy to the /memory skill for Horus persona recall.

Converts YouTube music history entries with taxonomy tags into memory-compatible
JSONL format for bulk import.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, TextIO, TypedDict


class MemoryEntry(TypedDict):
    """Memory-compatible entry format for /memory skill."""

    problem: str
    solution: str
    category: str
    tags: list[str]
    bridge_attributes: list[str]
    collection_tags: dict[str, str]


@dataclass
class TaxonomyConfig:
    """Configuration for HMT taxonomy mappings.

    This provides default mappings from artist/genre to taxonomy attributes.
    Can be extended or overridden as the HMT taxonomy evolves.
    """

    # Bridge attribute mappings: artist/keyword -> bridge attribute
    bridge_mappings: dict[str, str] = field(default_factory=lambda: {
        # Fragility - delicate, haunting, vulnerable
        "chelsea wolfe": "Fragility",
        "daughter": "Fragility",
        "phoebe bridgers": "Fragility",
        "haunting": "Fragility",
        "melancholy": "Fragility",
        "sad": "Fragility",
        "acoustic": "Fragility",
        # Resilience - powerful, triumphant, epic
        "sabaton": "Resilience",
        "two steps from hell": "Resilience",
        "power metal": "Resilience",
        "epic": "Resilience",
        "triumphant": "Resilience",
        # Precision - technical, complex, mathematical
        "meshuggah": "Precision",
        "tool": "Precision",
        "djent": "Precision",
        "prog": "Precision",
        "progressive metal": "Precision",
        # Transcendence - atmospheric, ethereal, expansive
        "mogwai": "Transcendence",
        "brian eno": "Transcendence",
        "ambient": "Transcendence",
        "post-rock": "Transcendence",
        "atmospheric": "Transcendence",
        "drone": "Transcendence",
        # Defiance - aggressive, rebellious
        "doom metal": "Defiance",
        "funeral doom": "Defiance",
        "bell witch": "Defiance",
    })

    # Domain mappings: genre/tag -> domain
    domain_mappings: dict[str, str] = field(default_factory=lambda: {
        "acoustic": "Dark_Folk",
        "folk": "Dark_Folk",
        "indie folk": "Dark_Folk",
        "haunting": "Dark_Folk",
        "power metal": "Epic_Metal",
        "epic": "Epic_Orchestral",
        "orchestral": "Epic_Orchestral",
        "cinematic": "Epic_Orchestral",
        "trailer": "Epic_Orchestral",
        "ambient": "Ambient",
        "drone": "Ambient",
        "post-rock": "Post_Rock",
        "atmospheric": "Atmospheric",
        "doom metal": "Doom_Metal",
        "funeral doom": "Doom_Metal",
        "prog": "Progressive",
        "progressive metal": "Progressive",
        "djent": "Technical_Metal",
        "pop": "Pop",
        "dance": "Pop",
    })

    # Thematic weight mappings: genre/tag -> thematic weight
    thematic_mappings: dict[str, str] = field(default_factory=lambda: {
        "sad": "Melancholic",
        "melancholy": "Melancholic",
        "haunting": "Melancholic",
        "acoustic": "Introspective",
        "epic": "Triumphant",
        "power metal": "Triumphant",
        "triumphant": "Triumphant",
        "ambient": "Contemplative",
        "atmospheric": "Contemplative",
        "post-rock": "Contemplative",
        "drone": "Meditative",
        "doom metal": "Heavy",
        "funeral doom": "Heavy",
        "prog": "Complex",
        "progressive metal": "Complex",
        "djent": "Technical",
    })

    # Episode associations: bridge attribute -> relevant episode keys
    episode_associations: dict[str, list[str]] = field(default_factory=lambda: {
        "Fragility": ["Webway_Collapse", "Sanguinius_Fall", "Dark_Reflection"],
        "Resilience": ["Siege_of_Terra", "Imperial_Fists_Stand", "Last_Defense"],
        "Precision": ["Iron_Warriors_Siege", "Tactical_Mastery", "Cold_Logic"],
        "Transcendence": ["Warp_Journey", "Astropathic_Visions", "Ascension"],
        "Defiance": ["Istvaan_III", "Betrayal_at_Calth", "Traitor_Legion"],
    })


def extract_taxonomy(
    entry: dict[str, Any],
    config: TaxonomyConfig | None = None,
) -> tuple[list[str], dict[str, str]]:
    """Extract HMT taxonomy data from a music entry.

    Args:
        entry: Music history entry with artist, tags, etc.
        config: Optional TaxonomyConfig for custom mappings.

    Returns:
        Tuple of (bridge_attributes, collection_tags)

    Note:
        This is a stub implementation. Task 6 (HMT Taxonomy Extraction)
        will provide the full taxonomy extraction logic.
    """
    if config is None:
        config = TaxonomyConfig()

    bridge_attributes: set[str] = set()
    domain: str | None = None
    thematic_weight: str | None = None

    # Extract searchable text
    artist = (entry.get("artist") or "").lower()
    tags = [t.lower() for t in entry.get("tags", [])]
    title = (entry.get("title") or "").lower()

    # Build combined text for matching
    all_text = f"{artist} {' '.join(tags)} {title}"

    # Find bridge attributes
    for keyword, bridge in config.bridge_mappings.items():
        if keyword in all_text:
            bridge_attributes.add(bridge)

    # Find domain (use first match)
    for keyword, d in config.domain_mappings.items():
        if keyword in all_text:
            domain = d
            break

    # Find thematic weight (use first match)
    for keyword, t in config.thematic_mappings.items():
        if keyword in all_text:
            thematic_weight = t
            break

    # Build collection_tags
    collection_tags: dict[str, str] = {}
    if domain:
        collection_tags["domain"] = domain
    if thematic_weight:
        collection_tags["thematic_weight"] = thematic_weight

    return list(bridge_attributes), collection_tags


def format_memory_entry(
    entry: dict[str, Any],
    config: TaxonomyConfig | None = None,
) -> MemoryEntry:
    """Format a music entry as a memory-compatible entry.

    Args:
        entry: Music history entry from parsed JSONL.
        config: Optional TaxonomyConfig for custom mappings.

    Returns:
        MemoryEntry dict ready for /memory skill import.

    Example:
        >>> entry = {"artist": "Chelsea Wolfe", "title": "Carrion Flowers", "tags": ["doom", "folk"]}
        >>> result = format_memory_entry(entry)
        >>> result["problem"]
        'Music: Chelsea Wolfe - Carrion Flowers'
    """
    if config is None:
        config = TaxonomyConfig()

    # Extract taxonomy
    bridge_attributes, collection_tags = extract_taxonomy(entry, config)

    # Build problem string: "Music: Artist - Title"
    artist = entry.get("artist") or entry.get("channel") or "Unknown Artist"
    title = entry.get("title") or "Unknown Title"
    problem = f"Music: {artist} - {title}"

    # Build solution string with taxonomy info
    solution_parts: list[str] = []

    # Add genre info from tags
    tags = entry.get("tags", [])
    if tags:
        genre_str = "/".join(tags[:3])  # First 3 tags as genre
        solution_parts.append(f"{genre_str} track.")

    # Add bridge attributes
    if bridge_attributes:
        bridge_str = ", ".join(bridge_attributes)
        solution_parts.append(f"Bridge: {bridge_str}.")

    # Add domain
    if "domain" in collection_tags:
        solution_parts.append(f"Domain: {collection_tags['domain']}.")

    # Add thematic weight
    if "thematic_weight" in collection_tags:
        solution_parts.append(f"Thematic: {collection_tags['thematic_weight']}.")

    # Add episode associations
    episode_keys: list[str] = []
    for bridge in bridge_attributes:
        episode_keys.extend(config.episode_associations.get(bridge, []))
    if episode_keys:
        # Dedupe and limit to first 3
        unique_episodes = list(dict.fromkeys(episode_keys))[:3]
        solution_parts.append(f"Episode associations: {', '.join(unique_episodes)}")

    solution = " ".join(solution_parts) if solution_parts else f"Music track by {artist}."

    # Build tags list: artist name (normalized), tags, bridge attributes
    memory_tags: list[str] = []

    # Add normalized artist name
    artist_tag = artist.lower().replace(" ", "_")
    if artist_tag:
        memory_tags.append(artist_tag)

    # Add original tags (normalized)
    for tag in tags:
        normalized = tag.lower().replace(" ", "_").replace("-", "_")
        if normalized and normalized not in memory_tags:
            memory_tags.append(normalized)

    # Add bridge attributes as tags (lowercase)
    for bridge in bridge_attributes:
        bridge_tag = bridge.lower()
        if bridge_tag not in memory_tags:
            memory_tags.append(bridge_tag)

    # Add thematic weight as tag
    if "thematic_weight" in collection_tags:
        thematic_tag = collection_tags["thematic_weight"].lower()
        if thematic_tag not in memory_tags:
            memory_tags.append(thematic_tag)

    return MemoryEntry(
        problem=problem,
        solution=solution,
        category="music",
        tags=memory_tags,
        bridge_attributes=bridge_attributes,
        collection_tags=collection_tags,
    )


def sync_to_memory(
    input_path: str | Path,
    output: TextIO | None = None,
    config: TaxonomyConfig | None = None,
    music_only: bool = True,
) -> Iterator[MemoryEntry]:
    """Sync music entries to memory-compatible JSONL format.

    Reads a parsed YouTube history JSONL file, extracts taxonomy data,
    and outputs memory-compatible entries.

    Args:
        input_path: Path to parsed YouTube history JSONL file.
        output: Optional file-like object to write JSONL to.
        config: Optional TaxonomyConfig for custom mappings.
        music_only: If True, only process entries with taxonomy data.

    Yields:
        MemoryEntry dicts for each processed entry.

    Example:
        >>> # Write to file
        >>> with open("memory_entries.jsonl", "w") as f:
        ...     list(sync_to_memory("music_history.jsonl", output=f))

        >>> # Or collect entries
        >>> entries = list(sync_to_memory("music_history.jsonl"))
    """
    if config is None:
        config = TaxonomyConfig()

    input_path = Path(input_path)

    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

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
            if music_only:
                # Check if entry has music-related data
                is_music = (
                    "YouTube Music" in entry.get("products", [])
                    or entry.get("artist")
                    or any(
                        keyword in " ".join(entry.get("tags", [])).lower()
                        for keyword in ["music", "song", "audio", "album"]
                    )
                )
                if not is_music:
                    continue

            # Format as memory entry
            memory_entry = format_memory_entry(entry, config)

            # Only yield entries with taxonomy data (bridge_attributes or collection_tags)
            if music_only and not (memory_entry["bridge_attributes"] or memory_entry["collection_tags"]):
                continue

            if output is not None:
                output.write(json.dumps(memory_entry) + "\n")

            yield memory_entry


def main() -> None:
    """CLI entry point for sync-memory command."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Sync YouTube music history to memory-compatible JSONL"
    )
    parser.add_argument(
        "input_path",
        help="Path to parsed YouTube history JSONL file",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output JSONL file path (default: stdout)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="include_all",
        help="Include entries without taxonomy data",
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print statistics after sync",
    )

    args = parser.parse_args()

    try:
        if args.output:
            with open(args.output, "w", encoding="utf-8") as out:
                entries = list(sync_to_memory(
                    args.input_path,
                    output=out,
                    music_only=not args.include_all,
                ))
        else:
            entries = []
            for entry in sync_to_memory(
                args.input_path,
                output=sys.stdout,
                music_only=not args.include_all,
            ):
                entries.append(entry)

        if args.stats:
            # Print statistics to stderr
            total = len(entries)
            with_bridge = sum(1 for e in entries if e["bridge_attributes"])
            with_domain = sum(1 for e in entries if "domain" in e["collection_tags"])

            print(f"\n--- Statistics ---", file=sys.stderr)
            print(f"Total entries: {total}", file=sys.stderr)
            print(f"With bridge attributes: {with_bridge}", file=sys.stderr)
            print(f"With domain: {with_domain}", file=sys.stderr)

            # Count by bridge attribute
            bridge_counts: dict[str, int] = {}
            for entry in entries:
                for bridge in entry["bridge_attributes"]:
                    bridge_counts[bridge] = bridge_counts.get(bridge, 0) + 1

            if bridge_counts:
                print(f"\nBridge attribute distribution:", file=sys.stderr)
                for bridge, count in sorted(bridge_counts.items(), key=lambda x: -x[1]):
                    print(f"  {bridge}: {count}", file=sys.stderr)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
