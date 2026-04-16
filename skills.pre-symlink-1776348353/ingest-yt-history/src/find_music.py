#!/usr/bin/env python3
"""
Find music from parsed YouTube history by mood, genre, or artist.

This is the primary Horus interface for music discovery.
"""
import json
import re
from pathlib import Path
from typing import Any, Optional

import typer

# Mood mappings - basic for now, HMT integration comes in Task 6
MOOD_MAPPINGS: dict[str, list[str]] = {
    "melancholic": [
        "sad",
        "acoustic",
        "folk",
        "chelsea wolfe",
        "daughter",
        "phoebe bridgers",
        "melancholy",
        "haunting",
        "somber",
    ],
    "epic": [
        "epic",
        "orchestral",
        "metal",
        "sabaton",
        "two steps from hell",
        "power metal",
        "symphonic",
        "cinematic",
        "trailer",
    ],
    "atmospheric": [
        "ambient",
        "atmospheric",
        "drone",
        "post-rock",
        "shoegaze",
        "ethereal",
        "dream pop",
        "soundscape",
    ],
}


def _normalize(text: str) -> str:
    """Normalize text for case-insensitive matching."""
    return text.lower().strip()


def _calculate_relevance(
    entry: dict[str, Any],
    query: str | None = None,
    mood: str | None = None,
    genre: str | None = None,
    artist: str | None = None,
) -> float:
    """Calculate relevance score for an entry.

    Higher scores = more relevant.

    Args:
        entry: History entry with title, artist, tags, etc.
        query: Free-text search query
        mood: Mood to match (melancholic, epic, atmospheric)
        genre: Genre to match
        artist: Artist to match

    Returns:
        float: Relevance score (0.0 if no match)
    """
    score = 0.0

    # Extract searchable fields
    title = _normalize(entry.get("title", ""))
    entry_artist = _normalize(entry.get("artist", ""))
    channel = _normalize(entry.get("channel", ""))
    tags = [_normalize(t) for t in entry.get("tags", [])]
    products = [_normalize(p) for p in entry.get("products", [])]

    # Build combined searchable text
    searchable = f"{title} {entry_artist} {channel} {' '.join(tags)}"

    # Free-text query matching
    if query:
        query_lower = _normalize(query)
        if query_lower in searchable:
            score += 10.0
            # Bonus for exact title match
            if query_lower in title:
                score += 5.0
            # Bonus for artist match
            if query_lower in entry_artist or query_lower in channel:
                score += 3.0

    # Mood matching
    if mood:
        mood_lower = _normalize(mood)
        keywords = MOOD_MAPPINGS.get(mood_lower, [])
        for keyword in keywords:
            if keyword in searchable:
                score += 5.0
                # Higher weight for artist matches in mood
                if keyword in entry_artist or keyword in channel:
                    score += 10.0

    # Genre matching
    if genre:
        genre_lower = _normalize(genre)
        if genre_lower in searchable:
            score += 8.0
        # Check tags specifically for genre
        for tag in tags:
            if genre_lower in tag:
                score += 5.0

    # Artist matching
    if artist:
        artist_lower = _normalize(artist)
        if artist_lower in entry_artist:
            score += 15.0
        elif artist_lower in channel:
            score += 12.0
        elif artist_lower in title:
            score += 5.0

    # Bonus for being from YouTube Music (more likely to be actual music)
    if "youtube music" in products or any("music" in p for p in products):
        score *= 1.2

    return score


def find_music(
    history_path: str | Path,
    query: str | None = None,
    mood: str | None = None,
    genre: str | None = None,
    artist: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Find music from parsed history by mood, genre, or artist.

    Args:
        history_path: Path to parsed history JSONL file
        query: Free-text search query
        mood: Mood filter (melancholic, epic, atmospheric)
        genre: Genre filter
        artist: Artist filter
        limit: Maximum number of results to return

    Returns:
        list[dict]: Matching entries sorted by relevance (highest first)

    Example:
        >>> results = find_music("history.jsonl", mood="melancholic")
        >>> # Returns entries matching Chelsea Wolfe, Daughter, etc.
    """
    history_path = Path(history_path)

    if not history_path.exists():
        raise FileNotFoundError(f"History file not found: {history_path}")

    # Collect all entries with scores
    scored_entries: list[tuple[float, dict[str, Any]]] = []

    with open(history_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            score = _calculate_relevance(
                entry,
                query=query,
                mood=mood,
                genre=genre,
                artist=artist,
            )

            if score > 0:
                scored_entries.append((score, entry))

    # Sort by score (descending) and return top N
    scored_entries.sort(key=lambda x: x[0], reverse=True)

    return [entry for _, entry in scored_entries[:limit]]


def main(
    history_path: str = typer.Argument(..., help="Path to parsed history JSONL file"),
    query: Optional[str] = typer.Option(None, "-q", "--query", help="Free-text search query"),
    mood: Optional[str] = typer.Option(None, "-m", "--mood", help="Mood filter (melancholic, epic, atmospheric)"),
    genre: Optional[str] = typer.Option(None, "-g", "--genre", help="Genre filter"),
    artist: Optional[str] = typer.Option(None, "-a", "--artist", help="Artist filter"),
    limit: int = typer.Option(10, "-n", "--limit", help="Maximum number of results (default: 10)"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON array instead of human-readable format"),
):
    """Find music from YouTube history by mood, genre, or artist."""
    import sys

    # Require at least one filter
    if not any([query, mood, genre, artist]):
        print("Error: At least one of --query, --mood, --genre, or --artist is required", file=sys.stderr)
        raise typer.Exit(code=1)

    try:
        results = find_music(
            history_path,
            query=query,
            mood=mood,
            genre=genre,
            artist=artist,
            limit=limit,
        )
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(code=1)

    if as_json:
        print(json.dumps(results, indent=2))
    else:
        if not results:
            print("No matches found.")
            raise typer.Exit()

        print(f"Found {len(results)} matches:\n")
        for i, entry in enumerate(results, 1):
            title = entry.get("title", "Unknown")
            artist_name = entry.get("artist") or entry.get("channel", "Unknown artist")
            video_id = entry.get("video_id", "")
            print(f"{i}. {title}")
            print(f"   Artist: {artist_name}")
            if video_id:
                print(f"   https://youtube.com/watch?v={video_id}")
            print()


if __name__ == "__main__":
    typer.run(main)
