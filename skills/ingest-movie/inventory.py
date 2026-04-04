"""
Movie Ingest Skill - Inventory Management
Clip inventory registry with file locking and atomic writes.
"""
import fcntl
import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from rich.console import Console

from config import INVENTORY_FILE, INVENTORY_LOCK_FILE

console = Console()


def load_inventory() -> Dict[str, Any]:
    """
    Load the clip inventory registry with file locking.
    Uses shared lock (LOCK_SH) for reads.
    Returns empty structure if file doesn't exist or is corrupted.
    """
    if not INVENTORY_FILE.exists():
        return {"clips": [], "movies_processed": [], "last_updated": None}

    try:
        with open(INVENTORY_LOCK_FILE, 'a+') as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
            try:
                content = INVENTORY_FILE.read_text()
                if not content.strip():
                    return {"clips": [], "movies_processed": [], "last_updated": None}
                return json.loads(content)
            except json.JSONDecodeError as e:
                # Corrupted file - backup and return empty
                backup = INVENTORY_FILE.with_suffix(".corrupted.json")
                console.print(f"[yellow]Warning: Inventory corrupted, backing up to {backup}[/yellow]")
                shutil.copy(INVENTORY_FILE, backup)
                return {"clips": [], "movies_processed": [], "last_updated": None}
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load inventory: {e}[/yellow]")
        return {"clips": [], "movies_processed": [], "last_updated": None}


def save_inventory(inventory: Dict[str, Any]) -> bool:
    """
    Save the clip inventory registry with file locking and atomic writes.
    Uses exclusive lock (LOCK_EX) for writes.
    Uses tempfile + os.replace for crash safety.
    Returns True on success, False on failure.
    """
    inventory["last_updated"] = datetime.now(timezone.utc).isoformat()

    try:
        # Ensure parent directory exists
        INVENTORY_FILE.parent.mkdir(parents=True, exist_ok=True)

        with open(INVENTORY_LOCK_FILE, 'a+') as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                # Write to temp file first
                fd, tmp_path = tempfile.mkstemp(
                    dir=INVENTORY_FILE.parent,
                    suffix=".tmp"
                )
                try:
                    with os.fdopen(fd, 'w') as tmp_file:
                        json.dump(inventory, tmp_file, indent=2)
                        # Flush and sync to ensure durability before atomic replace
                        tmp_file.flush()
                        os.fsync(tmp_file.fileno())
                    # Atomic replace
                    os.replace(tmp_path, INVENTORY_FILE)
                    # Sync parent directory to ensure rename is durable
                    dir_fd = os.open(str(INVENTORY_FILE.parent), os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        os.fsync(dir_fd)
                    finally:
                        os.close(dir_fd)
                    return True
                except Exception:
                    # Clean up temp file on error
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    raise
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    except Exception as e:
        console.print(f"[red]Error saving inventory: {e}[/red]")
        return False


def add_clip_to_inventory(
    movie_title: str,
    emotion: str,
    clip_path: Path,
    persona_path: Optional[Path] = None,
    scene_description: str = "",
    timestamp: str = "",
) -> bool:
    """
    Add a processed clip to the inventory.
    Thread-safe via file locking.
    """
    inventory = load_inventory()

    clip_entry = {
        "movie_title": movie_title,
        "emotion": emotion,
        "clip_path": str(clip_path),
        "persona_path": str(persona_path) if persona_path else None,
        "scene_description": scene_description,
        "timestamp": timestamp,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    # Check for duplicate (same movie + emotion + timestamp)
    for existing in inventory["clips"]:
        if (existing.get("movie_title") == movie_title and
            existing.get("emotion") == emotion and
            existing.get("timestamp") == timestamp):
            console.print(f"[yellow]Clip already in inventory, skipping duplicate[/yellow]")
            return True

    inventory["clips"].append(clip_entry)

    # Track processed movies
    if movie_title not in inventory["movies_processed"]:
        inventory["movies_processed"].append(movie_title)

    return save_inventory(inventory)


def get_inventory_stats() -> Dict[str, Any]:
    """
    Get summary statistics from the inventory.
    Returns dict with counts by emotion, total clips, etc.
    """
    inventory = load_inventory()

    clips_by_emotion: Dict[str, int] = {}
    for clip in inventory.get("clips", []):
        emotion = clip.get("emotion", "unknown")
        clips_by_emotion[emotion] = clips_by_emotion.get(emotion, 0) + 1

    return {
        "total_clips": len(inventory.get("clips", [])),
        "movies_processed": len(inventory.get("movies_processed", [])),
        "clips_by_emotion": clips_by_emotion,
        "last_updated": inventory.get("last_updated"),
        "threshold_status": {
            emotion: count >= 5
            for emotion, count in clips_by_emotion.items()
        },
    }


def get_clips_for_emotion(emotion: str) -> list[Dict[str, Any]]:
    """Get all clips for a specific emotion."""
    inventory = load_inventory()
    return [
        clip for clip in inventory.get("clips", [])
        if clip.get("emotion") == emotion
    ]


def clear_inventory() -> bool:
    """Clear the entire inventory (use with caution)."""
    return save_inventory({
        "clips": [],
        "movies_processed": [],
        "last_updated": None,
    })
