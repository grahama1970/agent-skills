"""Video and audio download functionality for youtube-transcripts skill.

This module handles:
- Video metadata fetching via yt-dlp
- Video search via yt-dlp
- Audio download for Whisper transcription
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from youtube_transcripts.config import (
    YTDLP_AUDIO_FORMAT,
    YTDLP_AUDIO_CODEC,
    YTDLP_AUDIO_QUALITY,
    AUDIO_EXTENSIONS,
)


def fetch_video_metadata(vid: str) -> dict:
    """Fetch video metadata using yt-dlp (fast extraction).

    Args:
        vid: YouTube video ID

    Returns:
        Dictionary with title, channel, upload_date, duration_sec, description, view_count.
        Empty dict on failure.
    """
    try:
        import yt_dlp
    except ImportError:
        return {}

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,  # Fast extraction (no download)
        "skip_download": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={vid}",
                download=False
            )
            return {
                "title": info.get("title", ""),
                "channel": info.get("uploader", ""),
                "upload_date": info.get("upload_date", ""),
                "duration_sec": info.get("duration", 0),
                "description": info.get("description", ""),
                "view_count": info.get("view_count", 0),
            }
    except Exception:
        # Silent fail on metadata
        return {}


def search_videos(query: str, max_results: int = 5) -> list[dict]:
    """Search YouTube videos using yt-dlp.

    Args:
        query: Search query string
        max_results: Maximum number of results to return

    Returns:
        List of dicts with title, id, url, duration, uploader, view_count, description.
        Returns [{"error": str}] on failure.
    """
    try:
        import yt_dlp
    except ImportError:
        return [{"error": "yt-dlp not installed. Run: pip install yt-dlp"}]

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "skip_download": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # ytsearchN:query syntax searches for N results
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            results = []
            if "entries" in info:
                for entry in info["entries"]:
                    results.append({
                        "title": entry.get("title", ""),
                        "id": entry.get("id"),
                        "url": entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}",
                        "duration": entry.get("duration"),
                        "uploader": entry.get("uploader"),
                        "view_count": entry.get("view_count"),
                        "description": entry.get("description", ""),
                    })
            return results
    except Exception as e:
        return [{"error": str(e)}]


def download_audio(vid: str, output_dir: Path) -> tuple[Optional[Path], Optional[str]]:
    """Download audio from YouTube video using yt-dlp.

    Args:
        vid: YouTube video ID
        output_dir: Directory to save the audio file

    Returns:
        Tuple of (audio_path, error_message).
        On success: (Path to audio file, None)
        On failure: (None, error message)
    """
    try:
        import yt_dlp
    except ImportError:
        return None, "yt-dlp not installed. Run: pip install yt-dlp"

    url = f"https://www.youtube.com/watch?v={vid}"
    output_template = str(output_dir / "%(id)s.%(ext)s")
    output_dir.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "format": YTDLP_AUDIO_FORMAT,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": YTDLP_AUDIO_CODEC,
            "preferredquality": YTDLP_AUDIO_QUALITY,
        }],
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Find the downloaded file (prefer mp3)
        audio_path = output_dir / f"{vid}.{YTDLP_AUDIO_CODEC}"
        if audio_path.exists():
            return audio_path, None

        # Try to find any audio file
        for ext in AUDIO_EXTENSIONS:
            p = output_dir / f"{vid}.{ext}"
            if p.exists():
                return p, None

        return None, "Audio file not found after download"

    except Exception as e:
        return None, f"yt-dlp error: {e}"


def get_video_url(vid: str) -> str:
    """Get the full YouTube URL for a video ID.

    Args:
        vid: YouTube video ID

    Returns:
        Full YouTube watch URL
    """
    return f"https://www.youtube.com/watch?v={vid}"
