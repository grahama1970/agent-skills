#!/usr/bin/env python3
"""
Enrich YouTube watch history entries with YouTube Data API metadata.

Adds: duration_seconds, category_id, category_name, tags, channel_id, channel_title
"""
import logging
import os
import re
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

# YouTube category ID to name mapping
# https://developers.google.com/youtube/v3/docs/videoCategories/list
CATEGORY_NAMES = {
    "1": "Film & Animation",
    "2": "Autos & Vehicles",
    "10": "Music",
    "15": "Pets & Animals",
    "17": "Sports",
    "18": "Short Movies",
    "19": "Travel & Events",
    "20": "Gaming",
    "21": "Videoblogging",
    "22": "People & Blogs",
    "23": "Comedy",
    "24": "Entertainment",
    "25": "News & Politics",
    "26": "Howto & Style",
    "27": "Education",
    "28": "Science & Technology",
    "29": "Nonprofits & Activism",
    "30": "Movies",
    "31": "Anime/Animation",
    "32": "Action/Adventure",
    "33": "Classics",
    "34": "Comedy",
    "35": "Documentary",
    "36": "Drama",
    "37": "Family",
    "38": "Foreign",
    "39": "Horror",
    "40": "Sci-Fi/Fantasy",
    "41": "Thriller",
    "42": "Shorts",
    "43": "Shows",
    "44": "Trailers",
}


def load_env() -> None:
    """Load .env file from skill directory or parents."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        # Manual loading if dotenv not installed
        for env_path in [
            Path(__file__).parent.parent / ".env",
            Path(__file__).parent.parent.parent / ".env",
            Path(__file__).parent.parent.parent.parent / ".env",
        ]:
            if env_path.exists():
                with open(env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            key, _, value = line.partition("=")
                            os.environ.setdefault(
                                key.strip(), value.strip().strip("\"'")
                            )
        return

    # Use dotenv if available
    for env_path in [
        Path(__file__).parent.parent / ".env",
        Path(__file__).parent.parent.parent / ".env",
        Path(__file__).parent.parent.parent.parent / ".env",
    ]:
        if env_path.exists():
            load_dotenv(env_path)
            break


def parse_duration(iso_duration: str) -> int:
    """Parse ISO 8601 duration (PT1H2M3S) to seconds.

    Examples:
        PT1H2M3S -> 3723
        PT5M30S -> 330
        PT45S -> 45
        PT1H -> 3600
    """
    if not iso_duration or not iso_duration.startswith("PT"):
        return 0

    # Remove PT prefix
    duration_str = iso_duration[2:]

    hours = 0
    minutes = 0
    seconds = 0

    # Extract hours
    if "H" in duration_str:
        match = re.match(r"(\d+)H", duration_str)
        if match:
            hours = int(match.group(1))
        duration_str = re.sub(r"\d+H", "", duration_str)

    # Extract minutes
    if "M" in duration_str:
        match = re.match(r"(\d+)M", duration_str)
        if match:
            minutes = int(match.group(1))
        duration_str = re.sub(r"\d+M", "", duration_str)

    # Extract seconds
    if "S" in duration_str:
        match = re.match(r"(\d+)S", duration_str)
        if match:
            seconds = int(match.group(1))

    return hours * 3600 + minutes * 60 + seconds


def enrich_entries(
    entries: list[dict],
    api_key: str | None = None,
    batch_size: int = 50,
) -> Iterator[dict]:
    """Enrich entries with YouTube Data API metadata.

    Args:
        entries: List of parsed watch history entries (from parse_takeout)
        api_key: YouTube API key. If None, loads from env YOUTUBE_API_KEY.
        batch_size: Number of videos per API request (max 50 for quota optimization)

    Yields:
        dict: Enriched entries with additional fields:
            - duration_seconds: Video duration in seconds
            - category_id: YouTube category ID
            - category_name: Human-readable category name
            - tags: List of video tags
            - channel_id: Channel ID
            - channel_title: Channel name

    Notes:
        - Handles quota limits gracefully by logging warnings and yielding unenriched entries
        - Batches API calls to optimize quota usage (50 videos = ~3 quota units vs 50 single calls)
    """
    # Load env if needed
    load_env()

    if api_key is None:
        api_key = os.environ.get("YOUTUBE_API_KEY")

    if not api_key:
        logger.warning(
            "YOUTUBE_API_KEY not set - returning entries without enrichment"
        )
        yield from entries
        return

    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError:
        logger.warning(
            "google-api-python-client not installed - returning entries without enrichment"
        )
        yield from entries
        return

    # Build YouTube API client
    youtube = build("youtube", "v3", developerKey=api_key)

    # Process entries in batches
    entries_list = list(entries)
    total = len(entries_list)

    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch = entries_list[batch_start:batch_end]

        # Collect video IDs for this batch
        video_ids = [e["video_id"] for e in batch if e.get("video_id")]

        if not video_ids:
            yield from batch
            continue

        # Make API request
        try:
            request = youtube.videos().list(
                part="snippet,contentDetails,statistics",
                id=",".join(video_ids),
            )
            response = request.execute()
        except HttpError as e:
            if e.resp.status == 403:
                logger.warning(
                    f"YouTube API quota exceeded or key invalid: {e.reason}"
                )
                logger.warning("Continuing with unenriched entries")
                yield from batch
                continue
            else:
                logger.error(f"YouTube API error: {e}")
                yield from batch
                continue
        except Exception as e:
            logger.error(f"Unexpected error calling YouTube API: {e}")
            yield from batch
            continue

        # Build lookup table from API response
        video_data = {}
        for item in response.get("items", []):
            vid = item.get("id")
            if vid:
                video_data[vid] = item

        # Enrich each entry in the batch
        for entry in batch:
            video_id = entry.get("video_id")
            if video_id and video_id in video_data:
                item = video_data[video_id]
                snippet = item.get("snippet", {})
                content_details = item.get("contentDetails", {})

                # Parse duration
                iso_duration = content_details.get("duration", "")
                entry["duration_seconds"] = parse_duration(iso_duration)

                # Category
                category_id = snippet.get("categoryId", "")
                entry["category_id"] = category_id
                entry["category_name"] = CATEGORY_NAMES.get(category_id, "Unknown")

                # Tags
                entry["tags"] = snippet.get("tags", [])

                # Channel info
                entry["channel_id"] = snippet.get("channelId", "")
                entry["channel_title"] = snippet.get("channelTitle", "")

            yield entry


def main():
    """CLI entry point for enrichment testing."""
    import sys

    from .ingest import parse_takeout

    if len(sys.argv) < 2:
        print(
            "Usage: python -m src.enrich <takeout_json_path>",
            file=sys.stderr,
        )
        sys.exit(1)

    input_path = sys.argv[1]

    # Parse and enrich
    entries = list(parse_takeout(input_path))
    enriched = list(enrich_entries(entries))

    import json

    for entry in enriched:
        print(json.dumps(entry))


if __name__ == "__main__":
    main()
