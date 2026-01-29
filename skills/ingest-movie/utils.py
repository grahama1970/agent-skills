"""
Movie Ingest Skill - Utilities
Subprocess helpers, encoding detection, formatting, and path utilities.
"""
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Optional, Sequence

import requests
import typer
from rich.console import Console

from config import FFMPEG_BIN, WHISPER_BIN

console = Console()


def sanitize_bin_path(path_str: str, default_name: str) -> str:
    """
    Ensure a safe binary path:
    - Require absolute path if provided via env.
    - Disallow shell metacharacters.
    - Fall back to default_name discovery.
    """
    if not path_str:
        return default_name
    p = Path(path_str)
    if p.is_absolute():
        s = str(p)
        # Disallow shell metacharacters but allow spaces (quoted in subprocess lists)
        if re.search(r'[`$|;&<>]', s):
            console.print(f"[yellow]Unsafe characters in {default_name} path; falling back to PATH.[/yellow]")
            return default_name
        return s
    # Not absolute: ignore env override
    return default_name


@lru_cache(maxsize=1)
def get_ffmpeg_bin() -> str:
    """Return ffmpeg path preferring env override but falling back to PATH."""
    configured = sanitize_bin_path(FFMPEG_BIN, default_name="ffmpeg")
    if configured and Path(configured).exists():
        return configured
    discovered = shutil.which("ffmpeg")
    return discovered or configured


@lru_cache(maxsize=1)
def get_whisper_bin() -> str:
    """Return whisper path preferring env override but falling back to PATH."""
    configured = sanitize_bin_path(WHISPER_BIN, default_name="whisper")
    if configured and Path(configured).exists():
        return configured
    discovered = shutil.which("whisper")
    return discovered or configured


def get_whisper_model_chain() -> list[str]:
    """
    Return fallback chain of Whisper models from largest to smallest.
    If a model fails (OOM, not available), caller should try next.
    """
    return ["medium", "base", "small", "tiny"]


def run_subprocess(
    cmd: Sequence[str],
    timeout_sec: int = 600,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """
    Safe subprocess wrapper: list-args only, capture outputs, timeout.
    Raises typer.Exit on failure if check=True.
    """
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        console.print(f"[red]Command timed out after {timeout_sec}s: {' '.join(cmd[:3])}...[/red]")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Subprocess error: {e}[/red]")
        raise typer.Exit(code=1)
    if check and result.returncode != 0:
        console.print(f"[red]Command failed ({result.returncode}): {' '.join(cmd[:5])}...[/red]")
        stderr_snippet = result.stderr.decode(errors='ignore')[:500]
        if stderr_snippet:
            console.print(f"[dim]{stderr_snippet}[/dim]")
        raise typer.Exit(code=result.returncode)
    return result


@lru_cache(maxsize=1)
def get_requests_session() -> requests.Session:
    """
    Configure a requests session with timeouts and basic retry/backoff.
    """
    from requests.adapters import HTTPAdapter
    try:
        from urllib3.util.retry import Retry
        retry = Retry(
            total=3,
            read=3,
            connect=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET", "POST"]),
        )
    except ImportError:
        retry = None
    s = requests.Session()
    if retry:
        s.mount("http://", HTTPAdapter(max_retries=retry))
        s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


# -----------------------------------------------------------------------------
# Encoding Detection
# -----------------------------------------------------------------------------
SRT_ENCODING_CHAIN = ['utf-8-sig', 'utf-8', 'latin-1', 'cp1252']


def read_file_with_encoding_fallback(path: Path) -> tuple[str, str]:
    """
    Read a file trying multiple encodings.
    Returns (content, encoding_used).
    Raises ValueError if all encodings fail.
    """
    for encoding in SRT_ENCODING_CHAIN:
        try:
            with open(path, 'r', encoding=encoding) as f:
                content = f.read()
            return content, encoding
        except UnicodeDecodeError:
            continue
    raise ValueError(f"Could not decode file with any encoding: {SRT_ENCODING_CHAIN}")


# -----------------------------------------------------------------------------
# Time Formatting
# -----------------------------------------------------------------------------
def format_seconds(value: float) -> str:
    """Format seconds as MM:SS.mmm for display."""
    minutes = int(value // 60)
    seconds = value % 60
    return f"{minutes:02d}:{seconds:06.3f}"


def format_hms(value: float) -> str:
    """Format seconds as HH:MM:SS for ffmpeg -ss/-to."""
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    secs = value % 60
    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


def format_srt_timestamp(value: float) -> str:
    """Format seconds as HH:MM:SS,mmm for SRT files."""
    hours = int(value // 3600)
    minutes = int((value % 3600) // 60)
    secs = int(value % 60)
    millis = int((value % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def parse_timestamp_to_seconds(ts: str) -> float:
    """
    Parse timestamps in formats like:
    - "01:15:30" (HH:MM:SS)
    - "15:30" (MM:SS)
    - "90" (seconds)
    Returns float seconds.
    """
    ts = ts.strip()
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s = parts
        return float(h) * 3600 + float(m) * 60 + float(s)
    elif len(parts) == 2:
        m, s = parts
        return float(m) * 60 + float(s)
    else:
        return float(ts)


# -----------------------------------------------------------------------------
# File Discovery
# -----------------------------------------------------------------------------
def find_media_file(
    directory: Path,
    extensions: set[str] = {".mkv", ".mp4", ".avi", ".m4v"},
) -> Optional[Path]:
    """Find the largest media file in a directory."""
    candidates = [f for f in directory.iterdir() if f.suffix.lower() in extensions]
    if not candidates:
        return None
    return max(candidates, key=lambda f: f.stat().st_size)


def find_subtitle_file(directory: Path, prefer_sdh: bool = True) -> Optional[Path]:
    """
    Find a subtitle file in directory.
    Prefers SDH/CC versions if prefer_sdh=True.
    """
    srt_files = list(directory.glob("*.srt"))
    if not srt_files:
        return None
    if prefer_sdh:
        # Prefer files with SDH/CC in name
        sdh_files = [f for f in srt_files if any(x in f.name.lower() for x in ['sdh', 'cc', 'hearing'])]
        if sdh_files:
            return sdh_files[0]
        # Then prefer .en.srt or English
        en_files = [f for f in srt_files if '.en.' in f.name.lower() or 'english' in f.name.lower()]
        if en_files:
            return en_files[0]
    return srt_files[0]


def fuzzy_match_title(search: str, available: list[str], threshold: float = 0.6) -> Optional[str]:
    """
    Simple fuzzy matching for movie titles.
    Returns the best match above threshold, or None.
    """
    search_lower = search.lower()
    search_words = set(search_lower.split())

    best_match = None
    best_score = 0.0

    for title in available:
        title_lower = title.lower()
        title_words = set(title_lower.split())

        # Calculate Jaccard similarity
        intersection = len(search_words & title_words)
        union = len(search_words | title_words)
        score = intersection / union if union > 0 else 0.0

        # Boost if search is substring of title
        if search_lower in title_lower:
            score += 0.3

        if score > best_score:
            best_score = score
            best_match = title

    return best_match if best_score >= threshold else None


def release_has_subtitle_hint(item: dict) -> bool:
    """Check if an NZB release item mentions subtitles."""
    from config import SUBTITLE_HINT_KEYWORDS
    haystack = " ".join([
        str(item.get("title", "")),
        str(item.get("description", "")),
        str(item.get("attr", "")),
    ]).lower()
    return any(keyword in haystack for keyword in SUBTITLE_HINT_KEYWORDS)
