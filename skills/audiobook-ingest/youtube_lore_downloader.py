#!/usr/bin/env python3
"""
YouTube Warhammer 40k Lore Transcript Downloader

Discovers and downloads transcripts from major Warhammer 40k lore channels.
"""

import json
import subprocess
import sys
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
import asyncio
import argparse

# Major Warhammer 40k lore channels (channel IDs or handles)
LORE_CHANNELS = {
    "Luetin09": "UCQwpt0g29CjLzt26al2GrOA",  # Deep lore dives
    "OculusImperia": "UC8AaO8zkIoxbUp1_p0rl13g",  # Historical style
    "Baldemort": "UCeBevM1N_nuMCpanYO5A7fQ",  # Guided by the Codex
    "40kTheories": "UC_e7KuB3g90VLO3acrIZGqA",  # Theory deep-dives
    "Majorkill": "UCxFbdkOp61Bs79vS8dYcXkA",  # Lore with humor
    "ABorderPrince": "UCLiYYY8p-mIxPgPNiGGbCqA",  # Horus Heresy specific
    "AdeptusRidiculous": "UCnHhGJUlnP8R1z7-dBNxEow",  # Podcast style
    "WolfLordRho": "UC_qb-Iy1ldg9nwCGcYVFJog",  # Primarch focused
    "Remleiz": "UCpIpmwxqHjyEKyc5xoO1XrA",  # Faction lore
    "Snipe_and_Wib": "UCLBITrCIYfAqUwKEL3FDqLw",  # Book reviews
}

# Keywords to filter for Horus/Heresy content
HORUS_KEYWORDS = [
    "horus", "heresy", "primarch", "emperor", "warmaster",
    "luna wolves", "sons of horus", "siege of terra",
    "istvaan", "davin", "chaos", "traitor", "loyalist",
    "sanguinius", "fulgrim", "angron", "mortarion",
    "magnus", "lorgar", "perturabo", "konrad curze",
    "alpharius", "lion el'jonson", "roboute", "vulkan",
    "corax", "ferrus manus", "rogal dorn", "leman russ",
    "jaghatai khan", "malcador"
]

OUTPUT_DIR = Path(__file__).parent / "youtube-lore"
PROGRESS_FILE = OUTPUT_DIR / "progress.json"


@dataclass
class VideoInfo:
    video_id: str
    title: str
    channel: str
    duration: int  # seconds
    upload_date: str
    transcript_status: str = "pending"  # pending, completed, failed, no_captions
    transcript_path: str = ""
    horus_relevance: float = 0.0


def get_channel_videos(channel_id: str, channel_name: str, max_videos: int = 500) -> list[VideoInfo]:
    """Get all video IDs from a YouTube channel using yt-dlp."""
    print(f"  Fetching videos from {channel_name}...")

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "--flat-playlist",
                "--dump-json",
                f"https://www.youtube.com/channel/{channel_id}/videos",
                "--playlist-end", str(max_videos),
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )

        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            try:
                data = json.loads(line)
                video = VideoInfo(
                    video_id=data.get("id", ""),
                    title=data.get("title", ""),
                    channel=channel_name,
                    duration=data.get("duration", 0) or 0,
                    upload_date=data.get("upload_date", ""),
                )

                # Calculate Horus relevance score
                title_lower = video.title.lower()
                relevance = sum(1 for kw in HORUS_KEYWORDS if kw in title_lower)
                video.horus_relevance = min(relevance / 3, 1.0)  # Normalize

                videos.append(video)
            except json.JSONDecodeError:
                continue

        return videos
    except subprocess.TimeoutExpired:
        print(f"  [WARN] Timeout fetching {channel_name}")
        return []
    except Exception as e:
        print(f"  [ERROR] {channel_name}: {e}")
        return []


def discover_videos() -> dict:
    """Discover all videos from lore channels."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_videos = {}
    total = 0
    horus_relevant = 0

    print("=" * 60)
    print("Discovering Warhammer 40k Lore Videos")
    print("=" * 60)

    for channel_name, channel_id in LORE_CHANNELS.items():
        videos = get_channel_videos(channel_id, channel_name)
        print(f"  → Found {len(videos)} videos")

        for video in videos:
            all_videos[video.video_id] = asdict(video)
            total += 1
            if video.horus_relevance > 0:
                horus_relevant += 1

    print(f"\nTotal: {total} videos ({horus_relevant} Horus-relevant)")

    # Save progress
    progress = {
        "discovered_at": datetime.now().isoformat(),
        "total_videos": total,
        "horus_relevant": horus_relevant,
        "channels": list(LORE_CHANNELS.keys()),
        "videos": all_videos,
    }

    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)

    print(f"Saved to {PROGRESS_FILE}")
    return progress


def download_transcript(video_id: str, output_path: Path) -> tuple[bool, str]:
    """Download transcript for a video using youtube-transcripts skill."""
    skill_path = Path.home() / ".claude/skills/youtube-transcripts/youtube_transcript.py"

    if not skill_path.exists():
        return False, "youtube-transcripts skill not found"

    try:
        result = subprocess.run(
            [
                sys.executable, str(skill_path),
                "get", "-i", video_id,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data.get("full_text"):
                output_path.write_text(data["full_text"])
                return True, data.get("meta", {}).get("method", "unknown")
            else:
                return False, "no transcript content"
        else:
            return False, result.stderr[:200] if result.stderr else "unknown error"

    except subprocess.TimeoutExpired:
        return False, "timeout"
    except json.JSONDecodeError:
        return False, "invalid JSON response"
    except Exception as e:
        return False, str(e)


async def download_transcripts_batch(
    concurrency: int = 3,
    horus_only: bool = False,
    max_videos: int = None,
):
    """Download transcripts with concurrency control."""
    if not PROGRESS_FILE.exists():
        print("Run 'discover' first to find videos")
        return

    with open(PROGRESS_FILE) as f:
        progress = json.load(f)

    videos = progress["videos"]
    transcripts_dir = OUTPUT_DIR / "transcripts"
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    # Filter and sort by relevance
    to_process = []
    for vid_id, video in videos.items():
        if video["transcript_status"] == "completed":
            continue
        if horus_only and video["horus_relevance"] == 0:
            continue
        to_process.append((vid_id, video))

    # Sort by relevance (highest first)
    to_process.sort(key=lambda x: x[1]["horus_relevance"], reverse=True)

    if max_videos:
        to_process = to_process[:max_videos]

    print(f"Processing {len(to_process)} videos (concurrency={concurrency})")

    semaphore = asyncio.Semaphore(concurrency)
    completed = 0
    failed = 0

    async def process_video(video_id: str, video: dict):
        nonlocal completed, failed

        async with semaphore:
            output_path = transcripts_dir / f"{video_id}.txt"

            # Run in thread pool to not block
            loop = asyncio.get_event_loop()
            success, method = await loop.run_in_executor(
                None, download_transcript, video_id, output_path
            )

            if success:
                video["transcript_status"] = "completed"
                video["transcript_path"] = str(output_path)
                completed += 1
                print(f"  ✓ {video['title'][:50]}... ({method})")
            else:
                if "no captions" in method.lower() or "no transcript" in method.lower():
                    video["transcript_status"] = "no_captions"
                else:
                    video["transcript_status"] = "failed"
                failed += 1
                print(f"  ✗ {video['title'][:50]}... ({method})")

            # Update progress file periodically
            if (completed + failed) % 10 == 0:
                with open(PROGRESS_FILE, "w") as f:
                    json.dump(progress, f, indent=2)

    tasks = [process_video(vid_id, video) for vid_id, video in to_process]
    await asyncio.gather(*tasks)

    # Final save
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)

    print(f"\nCompleted: {completed}, Failed: {failed}")


def status():
    """Show current download status."""
    if not PROGRESS_FILE.exists():
        print("No progress file. Run 'discover' first.")
        return

    with open(PROGRESS_FILE) as f:
        progress = json.load(f)

    videos = progress["videos"]
    by_status = {}
    by_channel = {}

    for video in videos.values():
        status = video["transcript_status"]
        channel = video["channel"]

        by_status[status] = by_status.get(status, 0) + 1
        if channel not in by_channel:
            by_channel[channel] = {"total": 0, "completed": 0, "horus": 0}
        by_channel[channel]["total"] += 1
        if status == "completed":
            by_channel[channel]["completed"] += 1
        if video["horus_relevance"] > 0:
            by_channel[channel]["horus"] += 1

    print("=" * 60)
    print("YouTube Lore Transcript Status")
    print("=" * 60)
    print(f"\nBy Status:")
    for status, count in sorted(by_status.items()):
        print(f"  {status}: {count}")

    print(f"\nBy Channel:")
    for channel, stats in sorted(by_channel.items()):
        pct = stats["completed"] / stats["total"] * 100 if stats["total"] > 0 else 0
        print(f"  {channel:20} {stats['completed']:4}/{stats['total']:4} ({pct:5.1f}%) [Horus: {stats['horus']}]")

    total = len(videos)
    completed = by_status.get("completed", 0)
    horus_total = sum(1 for v in videos.values() if v["horus_relevance"] > 0)

    print(f"\nTotal: {completed}/{total} transcripts ({completed/total*100:.1f}%)")
    print(f"Horus-relevant: {horus_total} videos")


def main():
    parser = argparse.ArgumentParser(description="YouTube Warhammer 40k Lore Downloader")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # discover
    subparsers.add_parser("discover", help="Discover videos from lore channels")

    # download
    dl_parser = subparsers.add_parser("download", help="Download transcripts")
    dl_parser.add_argument("--concurrency", "-c", type=int, default=3)
    dl_parser.add_argument("--horus-only", action="store_true", help="Only Horus-relevant videos")
    dl_parser.add_argument("--max", "-m", type=int, help="Max videos to process")

    # status
    subparsers.add_parser("status", help="Show download status")

    args = parser.parse_args()

    if args.command == "discover":
        discover_videos()
    elif args.command == "download":
        asyncio.run(download_transcripts_batch(
            concurrency=args.concurrency,
            horus_only=args.horus_only,
            max_videos=args.max,
        ))
    elif args.command == "status":
        status()


if __name__ == "__main__":
    main()
