"""media - persona_dream_nava_lane.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ffprobe_duration_seconds(path: str | Path) -> float | None:
    if shutil.which("ffprobe") is None:
        return None
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]
    completed = subprocess.run(cmd, check=True, capture_output=True, text=True)
    payload = json.loads(completed.stdout)
    return float(payload["format"]["duration"])


def find_new_mp4s(root: str | Path, started_at: float) -> list[Path]:
    base = Path(root)
    if not base.exists():
        return []
    matches = []
    for p in base.rglob("*.mp4"):
        try:
            if p.stat().st_mtime >= started_at:
                matches.append(p)
        except FileNotFoundError:
            continue
    return sorted(matches, key=lambda p: p.stat().st_mtime, reverse=True)
