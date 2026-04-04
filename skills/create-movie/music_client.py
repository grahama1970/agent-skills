"""music_client - create-movie.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import json
import os
import sys
import random
from pathlib import Path
from typing import List, Dict, Optional
from rich.console import Console

# Add memory project to path to import horus_music_taxonomy
# Priority: MEMORY_PROJECT_PATH env var > relative path > common known locations
MEMORY_PROJECT_PATH = os.environ.get(
    "MEMORY_PROJECT_PATH",
    str(Path(__file__).parent.parent.parent.parent / "memory")  # Relative to skill
)
PERSONA_BRIDGE_PATH = os.path.join(MEMORY_PROJECT_PATH, "persona", "bridge")

# Ensure we can import the bridge module
if Path(MEMORY_PROJECT_PATH).exists() and MEMORY_PROJECT_PATH not in sys.path:
    sys.path.append(MEMORY_PROJECT_PATH)
if Path(PERSONA_BRIDGE_PATH).exists() and PERSONA_BRIDGE_PATH not in sys.path:
    sys.path.append(PERSONA_BRIDGE_PATH)

HorusMusicTaxonomyVerifier = None
try:
    # Try importing as a module if package structure allows
    from persona.bridge.horus_music_taxonomy import HorusMusicTaxonomyVerifier
except ImportError:
    try:
        # Try direct import from the directory
        from horus_music_taxonomy import HorusMusicTaxonomyVerifier
    except ImportError:
        # Silent fail - music taxonomy is optional
        pass

console = Console()

class MusicClient:
    """
    Client for retrieving music based on scene context using Horus Music Taxonomy.
    """
    
    def __init__(self, history_path: str = None, cache_dir: str = ".cache/music"):
        # Default history path: check env var, then common locations
        if history_path is None:
            history_path = os.environ.get(
                "YT_HISTORY_PATH",
                str(Path.home() / ".pi" / "ingest-yt-history" / "history.jsonl")
            )
        self.history_path = Path(history_path)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.music_history: List[Dict] = []
        self._load_history()
        
        if HorusMusicTaxonomyVerifier:
            self.verifier = HorusMusicTaxonomyVerifier()
        else:
            self.verifier = None
            console.print("[yellow]Warning: Music Taxonomy Verifier not available. Falling back to random selection.[/yellow]")

    def _load_history(self):
        """Load music history from jsonl file."""
        if not self.history_path.exists():
            console.print(f"[red]Error: History file not found at {self.history_path}[/red]")
            return

        try:
            with open(self.history_path, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        # Basic filter for music-like entries if product is YouTube Music or category is Music
                        # The ingested history seems to have 'products': ['YouTube']
                        # We'll rely on the verifier to score them, but we can verify it has a video_id
                        if "video_id" in entry:
                            self.music_history.append(entry)
                    except json.JSONDecodeError:
                        continue
            console.print(f"[green]Loaded {len(self.music_history)} candidates from history.[/green]")
        except Exception as e:
            console.print(f"[red]Failed to load history: {e}[/red]")

    def _download_audio(self, url: str, video_id: str) -> Optional[Path]:
        """Download audio using ingest-youtube skill."""
        # Check cache first (any format)
        cached = list(self.cache_dir.glob(f"{video_id}.*"))
        if cached:
            console.print(f"[dim]Using cached audio: {cached[0]}[/dim]")
            return cached[0]

        console.print(f"[cyan]Downloading audio for {video_id}...[/cyan]")

        SKILLS_DIR = Path(__file__).resolve().parent.parent
        _iy_dir = str(SKILLS_DIR / "ingest-youtube")
        if _iy_dir not in sys.path:
            sys.path.insert(0, _iy_dir)

        from youtube_transcripts.downloader import download_audio

        audio_path, error = download_audio(video_id, self.cache_dir)
        if error or audio_path is None:
            console.print(f"[red]Failed to download audio: {error}[/red]")
            return None

        return audio_path

    def get_music_for_scene(self, scene_description: str, dry_run: bool = False) -> Optional[Path]:
        """
        Find and retrieve music for a given scene description.
        
        Args:
            scene_description: Text describing the scene (mood, events).
            dry_run: If True, don't actually download, just return a dummy path or None.
        
        Returns:
            Path to the audio file, or None if failed.
        """
        if not self.music_history:
            return None
            
        candidate = None
        
        if self.verifier:
            results = self.verifier.find_music_for_scene(scene_description, self.music_history)
            if results:
                top_result = results[0]
                console.print(f"[green]Selected Music: {top_result['music'].get('title', 'Unknown')} (Score: {top_result['score']:.2f})[/green]")
                candidate = top_result['music']
            else:
                console.print("[yellow]No suitable music matched. Picking random.[/yellow]")
                candidate = random.choice(self.music_history)
        else:
            candidate = random.choice(self.music_history)
            console.print(f"[green]Selected Random Music: {candidate.get('title', 'Unknown')}[/green]")
            
        if not candidate:
            return None
            
        url = candidate.get("url")
        video_id = candidate.get("video_id")
        
        if not url or not video_id:
            # Construct url if missing but video_id exists
            if video_id:
                url = f"https://www.youtube.com/watch?v={video_id}"
            else:
                return None

        if dry_run:
            console.print(f"[dim]Dry Run: Would download {url}[/dim]")
            return self.cache_dir / f"{video_id}.mp3" # Return expected path
            
        return self._download_audio(url, video_id)

if __name__ == "__main__":
    # Smoke test
    client = MusicClient()
    scene = "A dark, ominous corridor where ancient secrets lie hidden in the shadows."
    path = client.get_music_for_scene(scene, dry_run=True)
    if path:
        print(f"Smoke test successful: {path}")
    else:
        print("Smoke test failed")
