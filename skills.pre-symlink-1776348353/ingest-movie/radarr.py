"""
Movie Ingest Skill - Radarr Integration
Automated movie acquisition via Radarr.
"""
import json
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console
from rich.table import Table

from config import (
    RADARR_URL,
    RADARR_API_KEY,
    RADARR_HORUS_PRESET,
    VALID_EMOTIONS,
    EMOTION_MOVIE_MAPPINGS,
)
from utils import get_requests_session

console = Console()


def check_radarr_connection() -> bool:
    """Check if Radarr is accessible."""
    if not RADARR_API_KEY:
        console.print("[yellow]RADARR_API_KEY not set[/yellow]")
        return False

    try:
        session = get_requests_session()
        resp = session.get(
            f"{RADARR_URL}/api/v3/system/status",
            headers={"X-Api-Key": RADARR_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        status = resp.json()
        console.print(f"[green]Radarr connected: v{status.get('version', 'unknown')}[/green]")
        return True
    except Exception as e:
        console.print(f"[red]Radarr connection failed: {e}[/red]")
        return False


def get_quality_profiles() -> list[Dict[str, Any]]:
    """Get available quality profiles from Radarr."""
    if not RADARR_API_KEY:
        return []

    try:
        session = get_requests_session()
        resp = session.get(
            f"{RADARR_URL}/api/v3/qualityprofile",
            headers={"X-Api-Key": RADARR_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        console.print(f"[red]Failed to get quality profiles: {e}[/red]")
        return []


def get_root_folders() -> list[Dict[str, Any]]:
    """Get root folders from Radarr."""
    if not RADARR_API_KEY:
        return []

    try:
        session = get_requests_session()
        resp = session.get(
            f"{RADARR_URL}/api/v3/rootfolder",
            headers={"X-Api-Key": RADARR_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        console.print(f"[red]Failed to get root folders: {e}[/red]")
        return []


def search_movie(title: str, year: Optional[int] = None) -> list[Dict[str, Any]]:
    """Search for a movie in Radarr's lookup."""
    if not RADARR_API_KEY:
        return []

    try:
        session = get_requests_session()
        query = f"{title} {year}" if year else title
        resp = session.get(
            f"{RADARR_URL}/api/v3/movie/lookup",
            params={"term": query},
            headers={"X-Api-Key": RADARR_API_KEY},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        console.print(f"[red]Movie search failed: {e}[/red]")
        return []


def add_movie_to_radarr(
    tmdb_id: int,
    title: str,
    year: int,
    quality_profile_id: int,
    root_folder_path: str,
    monitored: bool = True,
    search_for_movie: bool = True,
) -> Optional[Dict[str, Any]]:
    """Add a movie to Radarr."""
    if not RADARR_API_KEY:
        console.print("[red]RADARR_API_KEY not set[/red]")
        return None

    payload = {
        "tmdbId": tmdb_id,
        "title": title,
        "year": year,
        "qualityProfileId": quality_profile_id,
        "rootFolderPath": root_folder_path,
        "monitored": monitored,
        "addOptions": {
            "searchForMovie": search_for_movie,
        },
    }

    try:
        session = get_requests_session()
        resp = session.post(
            f"{RADARR_URL}/api/v3/movie",
            json=payload,
            headers={"X-Api-Key": RADARR_API_KEY},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        console.print(f"[red]Failed to add movie: {e}[/red]")
        return None


def acquire_movies(
    emotions: Optional[list[str]] = None,
    preset: str = "horus_standard",
    dry_run: bool = True,
    max_per_emotion: int = 3,
) -> Dict[str, Any]:
    """
    Add missing movies from emotion mappings to Radarr.

    Args:
        emotions: List of emotions to acquire for (default: all)
        preset: Quality preset name
        dry_run: Preview without adding
        max_per_emotion: Maximum movies to add per emotion

    Returns:
        Acquisition results
    """
    if not check_radarr_connection():
        return {"error": "Radarr not connected", "added": [], "skipped": []}

    # Get quality profile
    profiles = get_quality_profiles()
    horus_profile = None
    for p in profiles:
        if "horus" in p.get("name", "").lower() or "tts" in p.get("name", "").lower():
            horus_profile = p
            break
    if not horus_profile and profiles:
        # Use first 1080p profile as fallback
        for p in profiles:
            if "1080" in p.get("name", ""):
                horus_profile = p
                break
    if not horus_profile and profiles:
        horus_profile = profiles[0]  # Last resort

    if not horus_profile:
        console.print("[red]No quality profile found[/red]")
        return {"error": "No quality profile", "added": [], "skipped": []}

    # Get root folder
    root_folders = get_root_folders()
    if not root_folders:
        console.print("[red]No root folders configured in Radarr[/red]")
        return {"error": "No root folders", "added": [], "skipped": []}
    root_folder = root_folders[0]["path"]

    console.print(f"[cyan]Acquiring movies with preset: {preset}[/cyan]")
    console.print(f"[dim]Quality profile: {horus_profile['name']}[/dim]")
    console.print(f"[dim]Root folder: {root_folder}[/dim]")

    if dry_run:
        console.print("[yellow]DRY RUN - no movies will be added[/yellow]\n")

    target_emotions = emotions or list(VALID_EMOTIONS)
    results = {"added": [], "skipped": [], "not_found": []}

    # Print preset info
    console.print(f"\n[bold]Horus TTS Preset Constraints:[/bold]")
    console.print(f"  Max quality: 1080p (no 4K)")
    console.print(f"  Max size: 15GB")
    console.print(f"  Language: English")
    console.print(f"  Subtitles: SDH preferred\n")

    for emotion in target_emotions:
        console.print(f"\n[bold]Emotion: {emotion}[/bold]")
        mappings = EMOTION_MOVIE_MAPPINGS.get(emotion, [])
        added_count = 0

        for mapping in mappings:
            if added_count >= max_per_emotion:
                break

            title = mapping["title"]
            year = mapping.get("year")

            # Search for movie
            results_list = search_movie(title, year)
            if not results_list:
                console.print(f"  [yellow]Not found: {title}[/yellow]")
                results["not_found"].append({"title": title, "year": year})
                continue

            movie = results_list[0]
            tmdb_id = movie.get("tmdbId")

            # Check if already in Radarr
            if movie.get("id"):
                console.print(f"  [dim]Already in library: {title}[/dim]")
                results["skipped"].append({"title": title, "reason": "already_in_library"})
                continue

            if dry_run:
                console.print(f"  [cyan]Would add: {title} ({year})[/cyan]")
                results["added"].append({"title": title, "year": year, "dry_run": True})
                added_count += 1
                continue

            # Add to Radarr
            result = add_movie_to_radarr(
                tmdb_id=tmdb_id,
                title=title,
                year=year or movie.get("year", 0),
                quality_profile_id=horus_profile["id"],
                root_folder_path=root_folder,
            )

            if result:
                console.print(f"  [green]✓ Added: {title}[/green]")
                results["added"].append({"title": title, "year": year})
                added_count += 1
            else:
                results["skipped"].append({"title": title, "reason": "add_failed"})

    console.print(f"\n[bold]Acquisition Summary:[/bold]")
    console.print(f"  Added: {len(results['added'])}")
    console.print(f"  Skipped: {len(results['skipped'])}")
    console.print(f"  Not found: {len(results['not_found'])}")

    return results


def list_radarr_movies() -> list[Dict[str, Any]]:
    """List all movies currently in Radarr."""
    if not RADARR_API_KEY:
        return []

    try:
        session = get_requests_session()
        resp = session.get(
            f"{RADARR_URL}/api/v3/movie",
            headers={"X-Api-Key": RADARR_API_KEY},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        console.print(f"[red]Failed to list movies: {e}[/red]")
        return []


def show_preset_info():
    """Display the Horus TTS preset configuration."""
    console.print("[bold]RADARR_HORUS_PRESET Configuration[/bold]\n")

    console.print(f"[cyan]Name:[/cyan] {RADARR_HORUS_PRESET['name']}")
    console.print(f"[cyan]Description:[/cyan] {RADARR_HORUS_PRESET['description']}")

    console.print(f"\n[bold]Quality Profile:[/bold]")
    qp = RADARR_HORUS_PRESET['quality_profile']
    console.print(f"  Enabled: {', '.join(qp['enabled_qualities'])}")
    console.print(f"  Disabled: {', '.join(qp['disabled_qualities'])}")
    console.print(f"  Max Size: {qp['max_size_mb']} MB ({qp['max_size_mb']/1000:.0f} GB)")

    console.print(f"\n[bold]Custom Formats:[/bold]")
    for name, cfg in RADARR_HORUS_PRESET['custom_formats'].items():
        console.print(f"  {name}: +{cfg['score']} (conditions: {', '.join(cfg['conditions'])})")

    console.print(f"\n[bold]Settings:[/bold]")
    console.print(f"  Language: {RADARR_HORUS_PRESET['language']}")
    console.print(f"  Monitor: {RADARR_HORUS_PRESET['monitor']}")

    console.print(f"\n[dim]Note: Create this profile in Radarr UI before using acquire commands[/dim]")
