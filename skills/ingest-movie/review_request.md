# Code Review Request: movie-ingest skill

## Objective
Brutal code review of the movie-ingest skill. Focus on:
1. Error handling and resilience
2. Security issues (command injection, path traversal)
3. Code quality and maintainability
4. Type safety and edge cases
5. Performance issues
6. Missing input validation

## Target Files

### movie_ingest.py (809 lines)
Primary CLI tool for:
- Searching NZBGeek for movie releases with subtitle hints
- Parsing .srt subtitle files to find emotion-tagged windows
- Extracting video clips via ffmpeg
- Transcribing via Whisper with rhythm metrics
- Generating PersonaPlex-ready JSON output

## Key Areas of Concern

1. **Subprocess calls** - ffmpeg and whisper invocations (potential command injection)
2. **File path handling** - subtitle resolution, clip output directories
3. **HTTP requests** - NZBGeek API calls (error handling, timeouts)
4. **Subtitle parsing** - robust handling of malformed .srt files
5. **Audio processing** - numpy/soundfile operations on potentially large files
6. **JSON output** - PersonaPlex schema validation

## Code

```python
#!/usr/bin/env python3
"""
Movie Ingest Skill
Search NZBGeek and transcribe local video files using Whisper for PersonaPlex alignment.
"""
import os
import sys
import json
import re
import shutil
import subprocess
import requests
import typer
from pathlib import Path
from typing import Optional
from collections import Counter
from functools import lru_cache
from rich.console import Console
from rich.table import Table
from datetime import datetime, timezone

app = typer.Typer(help="Movie Ingest & Transcription Skill")
scenes_app = typer.Typer(help="Transcript scene utilities")
app.add_typer(scenes_app, name="scenes")
console = Console()

# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------
NZB_API_KEY = os.environ.get("NZBD_GEEK_API_KEY") or os.environ.get("NZB_GEEK_API_KEY")
NZB_BASE_URL = (
    os.environ.get("NZBD_GEEK_BASE_URL")
    or os.environ.get("NZB_GEEK_BASE_URL")
    or "https://api.nzbgeek.info/"
)
WHISPER_BIN = os.environ.get("WHISPER_BIN", os.path.expanduser("~/.local/bin/whisper"))
FFMPEG_BIN = os.environ.get("FFMPEG_BIN", "/usr/bin/ffmpeg")

@lru_cache(maxsize=1)
def get_ffmpeg_bin() -> str:
    """Return ffmpeg path preferring env override but falling back to PATH."""
    configured = FFMPEG_BIN
    if configured and Path(configured).exists():
        return configured
    discovered = shutil.which("ffmpeg")
    return discovered or configured

# Audio intensity tagging thresholds (override via env)
RMS_THRESHOLD = float(os.environ.get("AUDIO_RMS_THRESHOLD", "0.2"))
RMS_WINDOW_SEC = float(os.environ.get("AUDIO_RMS_WINDOW_SEC", "0.5"))

CUE_KEYWORDS = {
    "laugh": "laugh",
    "laughs": "laugh",
    "chuckle": "laugh",
    "giggle": "laugh",
    "snicker": "laugh",
    "sob": "cry",
    "cry": "cry",
    "scream": "shout",
    "shout": "shout",
    "yell": "shout",
    "shouting": "shout",
    "yelling": "shout",
    "angry": "anger",
    "anger": "anger",
    "rage": "rage",
    "sigh": "sigh",
    "breath": "breath",
    "breathing": "breath",
    "whisper": "whisper",
    "snarl": "rage",
    "growl": "rage",
}

EMOTION_TAG_MAP = {
    "rage": {"rage", "rage_candidate", "anger_candidate", "shout"},
    "anger": {"anger", "anger_candidate", "shout"},
    "humor": {"laugh"},
    "regret": {"cry", "sob", "sigh"},
    "respect": {"whisper", "whisper_candidate", "breath"},
}

TAG_TO_EMOTION = {
    "rage": "rage",
    "rage_candidate": "rage",
    "anger": "anger",
    "anger_candidate": "anger",
    "shout": "anger",
    "laugh": "humor",
    "cry": "regret",
    "sob": "regret",
    "sigh": "regret",
    "whisper": "respect",
    "whisper_candidate": "respect",
    "breath": "respect",
}

SUBTITLE_HINT_KEYWORDS = (" subs", "subbed", "subtitle", "subtitles", ".srt", "cc", "sdh", "caption")

def _validate_env():
    if os.environ.get("NZBD_GEEK_API_KEY") and not os.environ.get("NZB_GEEK_API_KEY"):
        console.print("[yellow]Note: prefer NZB_GEEK_API_KEY (without the extra 'D').[/yellow]")
    if not NZB_API_KEY:
        console.print(
            "[yellow]Warning: NZB_GEEK_API_KEY not set. NZB search will fail.[/yellow]"
        )


def release_has_subtitle_hint(item: dict) -> bool:
    haystack = " ".join(
        [
            str(item.get("title", "")),
            str(item.get("description", "")),
            str(item.get("attr", "")),
        ]
    ).lower()
    return any(keyword in haystack for keyword in SUBTITLE_HINT_KEYWORDS)


@scenes_app.command("find")
def find_scene_windows(
    subtitle_file: Path = typer.Option(..., "--subtitle", "-s", exists=True, help="Subtitle .srt to scan"),
    query: Optional[str] = typer.Option(None, "--query", "-q", help="Case-insensitive text substring to find"),
    tag: Optional[str] = typer.Option(None, "--tag", "-t", help="Filter by subtitle cue tag (e.g. laugh, shout)"),
    emotion: Optional[str] = typer.Option(None, "--emotion", "-e", help="Filter by canonical emotion (rage, anger, humor, respect, regret)"),
    window: float = typer.Option(15.0, help="Seconds of padding before/after the match for suggested clips"),
    max_matches: int = typer.Option(5, help="Maximum matches to display"),
    offset: float = typer.Option(0.0, help="Seconds to add when referencing the full movie (useful if .srt was trimmed)"),
    video_file: Optional[Path] = typer.Option(None, "--video", help="Optional video file path for ffmpeg command hints"),
):
    """Search subtitle text/tags to locate clip timestamps."""
    # ... implementation continues
```

## Review Instructions

Be brutal. Find:
- Security vulnerabilities (command injection via file paths in subprocess calls)
- Missing error handling
- Edge cases that will crash
- Type safety issues
- Performance bottlenecks
- Code smells and maintainability issues

Provide unified diff patches for all recommended fixes.
