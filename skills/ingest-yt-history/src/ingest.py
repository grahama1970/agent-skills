#!/usr/bin/env python3
"""
Parse Google Takeout YouTube watch history JSON and output JSONL.

Each output line contains: video_id, title, timestamp, url, products
"""
import json
import re
import sys
from pathlib import Path
from typing import Iterator, TextIO, TypedDict
from urllib.parse import parse_qs, urlparse


class MusicServiceResult(TypedDict):
    """Result of music service detection."""

    service: str  # "youtube_music" | "youtube"
    is_music: bool
    detection_method: str  # "url" | "channel" | "title" | "category"


def extract_video_id(url: str) -> str | None:
    """Extract video ID from YouTube URL.

    Handles both:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://music.youtube.com/watch?v=VIDEO_ID

    Returns None if no video ID found.
    """
    if not url:
        return None

    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)

    video_ids = query_params.get("v", [])
    return video_ids[0] if video_ids else None


def strip_watched_prefix(title: str) -> str:
    """Strip the 'Watched ' prefix from title if present."""
    prefix = "Watched "
    if title.startswith(prefix):
        return title[len(prefix) :]
    return title


def detect_music_service(
    url: str,
    channel_name: str | None = None,
    title: str | None = None,
    category_id: int | None = None,
) -> MusicServiceResult:
    """Detect whether a video entry is from YouTube or YouTube Music.

    Detection heuristics (in priority order):
    1. music.youtube.com URLs → YouTube Music
    2. VEVO channels (e.g., "ChelseaWolfeVEVO") → Music
    3. " - Topic" suffix in channel → Music (auto-generated artist channels)
    4. "Official Audio" or "Official Music Video" in title → Music
    5. YouTube category 10 → Music (if enriched with API data)

    Args:
        url: The video URL
        channel_name: Optional channel name for channel-based detection
        title: Optional video title for title-based detection
        category_id: Optional YouTube category ID (10 = Music)

    Returns:
        MusicServiceResult with service, is_music, and detection_method
    """
    # 1. URL-based detection: music.youtube.com
    if url:
        parsed = urlparse(url)
        if parsed.netloc == "music.youtube.com":
            return MusicServiceResult(
                service="youtube_music",
                is_music=True,
                detection_method="url",
            )

    # 2. VEVO channel detection
    if channel_name:
        # VEVO channels end with "VEVO" (case-insensitive)
        if re.search(r"VEVO$", channel_name, re.IGNORECASE):
            return MusicServiceResult(
                service="youtube_music",
                is_music=True,
                detection_method="channel",
            )

        # 3. " - Topic" suffix detection (auto-generated artist channels)
        if channel_name.endswith(" - Topic"):
            return MusicServiceResult(
                service="youtube_music",
                is_music=True,
                detection_method="channel",
            )

    # 4. Title-based detection
    if title:
        # Check for "Official Audio" or "Official Music Video"
        title_lower = title.lower()
        if "official audio" in title_lower or "official music video" in title_lower:
            return MusicServiceResult(
                service="youtube_music",
                is_music=True,
                detection_method="title",
            )

    # 5. Category-based detection (YouTube category 10 = Music)
    if category_id == 10:
        return MusicServiceResult(
            service="youtube_music",
            is_music=True,
            detection_method="category",
        )

    # Default: Regular YouTube
    return MusicServiceResult(
        service="youtube",
        is_music=False,
        detection_method="url",
    )


def parse_takeout_entry(entry: dict) -> dict | None:
    """Parse a single Takeout watch history entry.

    Returns a dict with video_id, title, ts, url, products, or None if invalid.
    """
    # Skip entries without titleUrl (deleted videos)
    title_url = entry.get("titleUrl")
    if not title_url:
        return None

    video_id = extract_video_id(title_url)
    if not video_id:
        return None

    raw_title = entry.get("title", "")
    title = strip_watched_prefix(raw_title)

    return {
        "video_id": video_id,
        "title": title,
        "ts": entry.get("time", ""),
        "url": title_url,
        "products": entry.get("products", []),
    }


def parse_takeout(
    input_path: str | Path,
    output: TextIO | None = None,
) -> Iterator[dict]:
    """Parse Google Takeout YouTube history JSON and yield/write JSONL entries.

    Args:
        input_path: Path to the Takeout watch-history.json file
        output: Optional file-like object to write JSONL to. If None, only yields.

    Yields:
        dict: Parsed entries with video_id, title, ts, url, products

    Example output line (JSONL):
        {"video_id": "dQw4w9WgXcQ", "title": "Never Gonna Give You Up",
         "ts": "2025-01-15T14:30:00.000Z", "url": "https://...", "products": ["YouTube"]}
    """
    input_path = Path(input_path)

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Takeout JSON should be a list of watch entries")

    for entry in data:
        parsed = parse_takeout_entry(entry)
        if parsed is None:
            continue

        if output is not None:
            output.write(json.dumps(parsed) + "\n")

        yield parsed


def main():
    """CLI entry point for parsing Takeout JSON."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.ingest <takeout_json_path> [output_jsonl_path]", file=sys.stderr)
        sys.exit(1)

    input_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    if output_path:
        with open(output_path, "w", encoding="utf-8") as out:
            count = sum(1 for _ in parse_takeout(input_path, out))
    else:
        count = 0
        for entry in parse_takeout(input_path, sys.stdout):
            count += 1

    print(f"Processed {count} entries", file=sys.stderr)


if __name__ == "__main__":
    main()
