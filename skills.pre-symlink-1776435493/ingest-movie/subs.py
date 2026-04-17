"""
Movie Ingest Skill - Subtitle Management
Subtitle downloading and batch management using subliminal.
"""
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()


def download_subtitles(
    video_path: Path,
    language: str = "en",
    providers: Optional[list[str]] = None,
    prefer_sdh: bool = True,
) -> Optional[Path]:
    """
    Download subtitles for a video file using subliminal.

    Args:
        video_path: Path to the video file
        language: Language code (default 'en')
        providers: List of providers to use (default: opensubtitles, podnapisi)
        prefer_sdh: Prefer SDH/CC subtitles

    Returns:
        Path to downloaded subtitle, or None if not found
    """
    try:
        import subliminal
        from subliminal.video import Video
        from babelfish import Language as BabelLanguage
    except ImportError:
        console.print("[yellow]subliminal not installed. Run: uv pip install subliminal babelfish[/yellow]")
        return None

    if providers is None:
        providers = ['opensubtitles', 'podnapisi', 'tvsubtitles']

    console.print(f"[cyan]Searching for subtitles: {video_path.name}...[/cyan]")

    try:
        # Scan for video
        video = Video.fromname(str(video_path))

        # Configure and search
        lang = BabelLanguage(language)
        subtitles = subliminal.download_best_subtitles(
            {video},
            {lang},
            providers=providers,
            hearing_impaired=prefer_sdh,
        )

        if video in subtitles and subtitles[video]:
            # Save subtitle
            srt_path = video_path.with_suffix('.srt')
            subliminal.save_subtitles(video, subtitles[video])

            # Find the saved file
            for ext in ['.srt', f'.{language}.srt']:
                candidate = video_path.with_suffix(ext)
                if candidate.exists():
                    console.print(f"[green]Downloaded: {candidate.name}[/green]")
                    return candidate

            console.print(f"[green]Downloaded subtitle (check video directory)[/green]")
            return srt_path

        console.print(f"[yellow]No subtitles found for {video_path.name}[/yellow]")
        return None

    except Exception as e:
        console.print(f"[red]Subtitle download failed: {e}[/red]")
        return None


def batch_download_subtitles(
    directory: Path,
    language: str = "en",
    recursive: bool = False,
    skip_existing: bool = True,
) -> dict:
    """
    Download subtitles for all videos in a directory.

    Args:
        directory: Directory containing videos
        language: Language code
        recursive: Search subdirectories
        skip_existing: Skip videos that already have subtitles

    Returns:
        Dict with 'success', 'skipped', 'failed' lists
    """
    results = {"success": [], "skipped": [], "failed": []}

    video_extensions = {'.mkv', '.mp4', '.avi', '.m4v', '.mov'}
    pattern = "**/*" if recursive else "*"

    videos = [
        f for f in directory.glob(pattern)
        if f.suffix.lower() in video_extensions and f.is_file()
    ]

    console.print(f"[cyan]Found {len(videos)} video files[/cyan]")

    for video in videos:
        # Check for existing subtitle
        existing_srt = list(video.parent.glob(f"{video.stem}*.srt"))
        if skip_existing and existing_srt:
            console.print(f"[dim]Skipping (has subtitle): {video.name}[/dim]")
            results["skipped"].append(str(video))
            continue

        result = download_subtitles(video, language=language)
        if result:
            results["success"].append(str(video))
        else:
            results["failed"].append(str(video))

    console.print(f"\n[green]Success: {len(results['success'])}[/green], "
                  f"[yellow]Skipped: {len(results['skipped'])}[/yellow], "
                  f"[red]Failed: {len(results['failed'])}[/red]")

    return results


def check_subtitle_availability(video_path: Path, language: str = "en") -> dict:
    """
    Check if subtitles are available without downloading.

    Returns:
        Dict with provider availability info
    """
    try:
        import subliminal
        from subliminal.video import Video
        from babelfish import Language as BabelLanguage
    except ImportError:
        return {"error": "subliminal not installed"}

    try:
        video = Video.fromname(str(video_path))
        lang = BabelLanguage(language)

        # Search without downloading
        subtitles = subliminal.list_subtitles(
            {video},
            {lang},
            providers=['opensubtitles', 'podnapisi'],
        )

        if video in subtitles:
            providers = {}
            for sub in subtitles[video]:
                provider = sub.provider_name
                providers[provider] = providers.get(provider, 0) + 1

            return {
                "available": True,
                "count": len(subtitles[video]),
                "providers": providers,
            }

        return {"available": False, "count": 0, "providers": {}}

    except Exception as e:
        return {"error": str(e)}
