#!/usr/bin/env python3
"""
Sanity script: Verify YouTube Data API access.

PURPOSE: Validate API key and quota before enrichment.
EXIT CODES: 0=PASS, 1=FAIL, 42=CLARIFY (needs human)

DOCUMENTATION: https://developers.google.com/youtube/v3/docs/videos/list
"""
import os
import sys
from pathlib import Path

# Load .env from skill dir or parent directories
def load_env():
    """Load .env file from skill directory or parents."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        # Try manual loading if dotenv not installed
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
                            os.environ.setdefault(key.strip(), value.strip().strip('"\''))
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

load_env()

# Check for API key first
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
if not YOUTUBE_API_KEY:
    print("FAIL: YOUTUBE_API_KEY not set in environment")
    print("  Set it in .env or export YOUTUBE_API_KEY=your_key")
    sys.exit(1)


def verify_youtube_api():
    """Verify YouTube API access with a known video."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError:
        print("FAIL: google-api-python-client not installed")
        print("  Run: pip install google-api-python-client")
        return 1

    # Build the YouTube API client
    youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

    # Test with Rick Astley - Never Gonna Give You Up (known stable video)
    test_video_id = "dQw4w9WgXcQ"

    try:
        request = youtube.videos().list(
            part="snippet,contentDetails,statistics",
            id=test_video_id
        )
        response = request.execute()
    except HttpError as e:
        if e.resp.status == 403:
            print(f"FAIL: API key invalid or quota exceeded")
            print(f"  Error: {e.reason}")
            return 1
        raise

    if not response.get("items"):
        print(f"FAIL: No data returned for video {test_video_id}")
        return 1

    video = response["items"][0]
    snippet = video.get("snippet", {})
    content = video.get("contentDetails", {})
    stats = video.get("statistics", {})

    print("PASS: YouTube API access verified")
    print(f"\nTest video: {snippet.get('title')}")
    print(f"  Channel: {snippet.get('channelTitle')}")
    print(f"  Category: {snippet.get('categoryId')} (10 = Music)")
    print(f"  Duration: {content.get('duration')}")
    print(f"  Views: {stats.get('viewCount')}")
    print(f"  Tags: {snippet.get('tags', [])[:5]}...")

    # Check quota usage (rough estimate)
    print(f"\nQuota note: This call used ~3 units (videos.list with 3 parts)")
    print(f"  Daily quota: 10,000 units")
    print(f"  Batch 50 videos = ~150 units per batch")

    return 0


if __name__ == "__main__":
    sys.exit(verify_youtube_api())
