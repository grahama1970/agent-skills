#!/usr/bin/env python3
"""YouTube search integration for Dogpile.

Provides multi-stage video search:
- Stage 1: Video metadata search via yt-dlp
- Stage 2: Transcript extraction
"""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Dict, Any, List

# Add parent directory to path for package imports when running as script
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR.parent))

from dogpile.config import SKILLS_DIR
from dogpile.utils import log_status, with_semaphore, run_command, capture_execution_metadata


@capture_execution_metadata("youtube", stage="stage1")
@with_semaphore("youtube")
def search_youtube(query: str) -> List[Dict[str, str]]:
    """Search YouTube (Stage 1: Metadata) with rate limiting protection.

    YouTube/yt-dlp can get rate limited. Uses semaphore to limit concurrent requests.
    Delegates to canonical ingest-youtube search_videos().

    Args:
        query: Search query

    Returns:
        List of video dicts with title, id, url, description
    """
    log_status(f"Starting YouTube Search for '{query}'...", provider="youtube", status="RUNNING")

    # Delegate to canonical ingest-youtube skill
    _iy_dir = str(SKILLS_DIR / "ingest-youtube")
    if _iy_dir not in sys.path:
        sys.path.insert(0, _iy_dir)
    from youtube_transcripts.downloader import search_videos

    raw_results = search_videos(query, max_results=5)

    # Check for errors from canonical API
    if raw_results and "error" in raw_results[0]:
        error_msg = raw_results[0]["error"]
        if "429" in error_msg or "rate limit" in error_msg.lower():
            log_status("YouTube rate limited, backing off 30s...", provider="youtube", status="RATE_LIMITED")
            time.sleep(30)
            raw_results = search_videos(query, max_results=5)

        if raw_results and "error" in raw_results[0]:
            return [{"title": f"Error searching YouTube: {raw_results[0]['error']}", "url": "", "id": "", "description": ""}]

    # Map canonical output to dogpile format
    results = []
    for entry in raw_results:
        desc = entry.get("description") or "No description available."
        desc = desc.replace("\n", " ").strip()
        if len(desc) > 200:
            desc = desc[:197] + "..."

        results.append({
            "title": entry.get("title", "Unknown Title"),
            "id": entry.get("id", ""),
            "url": entry.get("url", ""),
            "description": desc,
        })

    log_status("YouTube Search finished.", provider="youtube", status="DONE")
    return results


@with_semaphore("youtube")
def search_youtube_transcript(video_id: str) -> Dict[str, Any]:
    """Search YouTube (Stage 2: Transcript) with rate limiting protection.

    Args:
        video_id: YouTube video ID

    Returns:
        Dict with full_text or error
    """
    log_status(f"Fetching YouTube Transcript for {video_id}...")
    skill_dir = SKILLS_DIR / "ingest-youtube"
    cmd = [sys.executable, str(skill_dir / "youtube_transcript.py"), "get", "-i", video_id]

    try:
        output = run_command(cmd)
        log_status(f"YouTube Transcript for {video_id} finished.")

        if output.startswith("Error:"):
            return {"error": output}

        return json.loads(output)
    except Exception as e:
        return {"error": str(e)}


def run_stage2_youtube(youtube_res: List[Dict]) -> List[Dict]:
    """Stage 2: YouTube transcript fetch for top videos.

    Args:
        youtube_res: Stage 1 YouTube search results

    Returns:
        List of transcript dicts with full_text, title, url
    """
    youtube_transcripts = []

    if youtube_res:
        valid_videos = [v for v in youtube_res if v.get("id")][:2]

        if valid_videos:
            log_status(
                f"YouTube Stage 2: Fetching transcripts for {len(valid_videos)} videos...",
                provider="youtube",
                status="RUNNING"
            )

            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = {executor.submit(search_youtube_transcript, v["id"]): v for v in valid_videos}
                for f in as_completed(futures):
                    res = f.result()
                    if "full_text" in res:
                        res["title"] = futures[f]["title"]
                        res["url"] = futures[f]["url"]
                        youtube_transcripts.append(res)
            log_status("YouTube Stage 2 finished.", provider="youtube", status="DONE")

    return youtube_transcripts
