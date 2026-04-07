"""Load and analyze failure pattern registry."""
from __future__ import annotations

import json
from pathlib import Path

from .models import ManifestEntry


def load_pattern_registry(path: Path) -> dict:
    """Read pattern_registry.json.  Returns empty dict if missing."""
    if not path.exists():
        return {}
    try:
        with open(path) as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}


def analyze_patterns(
    registry: dict,
    entries: list[ManifestEntry],
) -> list[dict]:
    """Cross-reference pattern registry with manifest entries.

    Returns a list of dicts sorted by descending count, each with:
      name, count, files, categories, first_seen, last_seen
    """
    # Build filename -> entry lookup
    by_filename: dict[str, ManifestEntry] = {e.filename: e for e in entries}

    patterns_out: list[dict] = []

    # Registry format: {"patterns": {"pattern_name": {"files": [...], ...}}}
    # or flat: {"pattern_name": {"files": [...], ...}}
    raw = registry.get("patterns", registry)

    for name, info in raw.items():
        if not isinstance(info, dict):
            continue
        files = info.get("files", [])
        if isinstance(files, list):
            file_list = files
        else:
            file_list = []

        # Cross-reference categories
        categories: set[str] = set()
        for f in file_list:
            entry = by_filename.get(f)
            if entry and entry.category:
                categories.add(entry.category)

        patterns_out.append({
            "name": name,
            "count": info.get("count", len(file_list)),
            "files": file_list,
            "categories": sorted(categories),
            "first_seen": info.get("first_seen", "—"),
            "last_seen": info.get("last_seen", "—"),
            "description": info.get("description", ""),
        })

    # Sort by count descending
    patterns_out.sort(key=lambda p: -p["count"])
    return patterns_out
