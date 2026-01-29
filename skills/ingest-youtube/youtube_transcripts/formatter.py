"""Output formatting for youtube-transcripts skill.

This module handles:
- Result formatting for JSON output
- Rich console formatting for interactive mode
- Batch state management
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional, Any

from youtube_transcripts.utils import format_duration, truncate_text


def build_result(
    vid: Optional[str],
    lang: str,
    took_ms: int,
    method: Optional[str],
    transcript: list[dict],
    full_text: str,
    errors: list[str],
    metadata: Optional[dict] = None,
) -> dict:
    """Build a standardized result dictionary.

    Args:
        vid: YouTube video ID
        lang: Language code
        took_ms: Time taken in milliseconds
        method: Extraction method used (direct, proxy, whisper-local, whisper-api)
        transcript: List of transcript segments
        full_text: Full concatenated text
        errors: List of error messages
        metadata: Optional video metadata dict

    Returns:
        Standardized result dictionary
    """
    result = {
        "meta": {
            "video_id": vid,
            "language": lang,
            "took_ms": took_ms,
            "method": method,
        },
        "transcript": transcript,
        "full_text": full_text,
        "errors": errors if errors else [],
    }

    # Merge metadata if provided
    if metadata:
        result["meta"].update(metadata)

    return result


def build_languages_result(
    vid: Optional[str],
    took_ms: int,
    proxy_used: bool,
    retries_used: int,
    languages: list[dict],
    errors: list[str],
) -> dict:
    """Build result for list-languages command.

    Args:
        vid: YouTube video ID
        took_ms: Time taken in milliseconds
        proxy_used: Whether proxy was used
        retries_used: Number of retries used
        languages: List of available languages
        errors: List of error messages

    Returns:
        Result dictionary for languages listing
    """
    return {
        "meta": {
            "video_id": vid,
            "took_ms": took_ms,
            "proxy_used": proxy_used,
            "retries_used": retries_used,
        },
        "languages": languages,
        "errors": errors,
    }


def build_proxy_check_result(
    configured: bool,
    proxy_config: Optional[dict] = None,
    test_ip: Optional[str] = None,
    rotation_test: Optional[dict] = None,
    error: Optional[str] = None,
) -> dict:
    """Build result for check-proxy command.

    Args:
        configured: Whether proxy is configured
        proxy_config: Proxy configuration (host, port)
        test_ip: IP address from test request
        rotation_test: Rotation test results
        error: Error message if any

    Returns:
        Result dictionary for proxy check
    """
    import os
    from youtube_transcripts.config import (
        PROXY_ENV_HOST,
        PROXY_ENV_PORT,
        PROXY_ENV_USER,
        PROXY_ENV_PASSWORD,
    )

    if not configured:
        return {
            "configured": False,
            "error": error or "Missing environment variables",
            "env_vars": {
                PROXY_ENV_HOST: os.getenv(PROXY_ENV_HOST, ""),
                PROXY_ENV_PORT: os.getenv(PROXY_ENV_PORT, ""),
                PROXY_ENV_USER: os.getenv(PROXY_ENV_USER, ""),
                PROXY_ENV_PASSWORD: "(set)" if os.getenv(PROXY_ENV_PASSWORD) else "(not set)",
            },
        }

    result = {
        "configured": True,
        "proxy_host": proxy_config["host"] if proxy_config else "",
        "proxy_port": proxy_config["port"] if proxy_config else "",
        "status": "error" if error else "working",
    }

    if test_ip:
        result["test_ip"] = test_ip

    if error:
        result["error"] = error

    if rotation_test:
        result["rotation_test"] = rotation_test

    return result


def print_json(data: dict, indent: int = 2) -> None:
    """Print data as formatted JSON.

    Args:
        data: Dictionary to print
        indent: JSON indentation level
    """
    print(json.dumps(data, ensure_ascii=False, indent=indent))


def save_json(data: dict, path: Path, indent: int = 2) -> None:
    """Save data as JSON to file.

    Args:
        data: Dictionary to save
        path: File path
        indent: JSON indentation level
    """
    with open(path, 'w') as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


class BatchStateManager:
    """Manages batch processing state for resume capability."""

    def __init__(self, state_file: Path):
        """Initialize batch state manager.

        Args:
            state_file: Path to state file
        """
        self.state_file = state_file
        self.completed: set[str] = set()
        self.stats = {
            "success": 0,
            "failed": 0,
            "skipped": 0,
            "rate_limited": 0,
            "whisper": 0,
        }
        self.consecutive_failures = 0

    def load(self) -> bool:
        """Load state from file.

        Returns:
            True if state was loaded, False otherwise
        """
        if not self.state_file.exists():
            return False

        try:
            with open(self.state_file) as f:
                state = json.load(f)
                self.completed = set(state.get("completed", []))
                self.stats = state.get("stats", self.stats)
                self.consecutive_failures = state.get("consecutive_failures", 0)
            return True
        except Exception:
            return False

    def save(
        self,
        current_vid: str = "",
        current_method: str = "",
    ) -> None:
        """Save current state to file.

        Args:
            current_vid: Currently processing video ID
            current_method: Current processing method
        """
        with open(self.state_file, 'w') as f:
            json.dump({
                "completed": list(self.completed),
                "stats": self.stats,
                "consecutive_failures": self.consecutive_failures,
                "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "current_video": current_vid,
                "current_method": current_method,
            }, f, indent=2)

    def mark_completed(self, vid: str) -> None:
        """Mark a video as completed.

        Args:
            vid: Video ID
        """
        self.completed.add(vid)

    def is_completed(self, vid: str) -> bool:
        """Check if video is already completed.

        Args:
            vid: Video ID

        Returns:
            True if video was already processed
        """
        return vid in self.completed

    def record_success(self, method: str) -> None:
        """Record a successful transcript fetch.

        Args:
            method: Method used (direct, proxy, whisper-local, whisper-api)
        """
        self.stats["success"] += 1
        if "whisper" in method:
            self.stats["whisper"] += 1
        self.consecutive_failures = 0

    def record_failure(self, is_rate_limit: bool = False) -> None:
        """Record a failed transcript fetch.

        Args:
            is_rate_limit: Whether the failure was due to rate limiting
        """
        if is_rate_limit:
            self.stats["rate_limited"] += 1
            self.consecutive_failures += 1
        else:
            self.stats["failed"] += 1
            self.consecutive_failures = 0

    def record_skipped(self) -> None:
        """Record a skipped video (already exists)."""
        self.stats["skipped"] += 1


def print_search_results_table(results: list[dict], query: str) -> None:
    """Print search results as a Rich table.

    Args:
        results: List of search result dicts
        query: Original search query
    """
    try:
        from rich.console import Console
        from rich.table import Table
    except ImportError:
        print_json(results)
        return

    console = Console()
    table = Table(title=f"Search Results: {query}")
    table.add_column("#", justify="right", style="cyan", no_wrap=True)
    table.add_column("Title", style="magenta")
    table.add_column("Channel", style="green")
    table.add_column("Duration", justify="right")
    table.add_column("Views", justify="right")
    table.add_column("Abstract", style="dim white")

    for idx, r in enumerate(results, 1):
        if "error" in r:
            continue

        duration = format_duration(r.get("duration"))
        desc = truncate_text(r.get("description", ""), max_length=80)

        table.add_row(
            str(idx),
            truncate_text(r.get("title", "Unknown"), 50),
            truncate_text(r.get("uploader", "Unknown"), 20),
            duration,
            str(r.get("view_count", "?")),
            desc
        )

    console.print(table)


def print_batch_summary(stats: dict, output_path: Path) -> None:
    """Print batch processing summary.

    Args:
        stats: Statistics dictionary
        output_path: Output directory path
    """
    import typer

    typer.echo(f"\n{'='*50}", err=True)
    typer.echo(f"=== Batch Complete ===", err=True)
    typer.echo(f"Success:      {stats['success']}", err=True)
    typer.echo(f"Failed:       {stats['failed']}", err=True)
    typer.echo(f"Rate Limited: {stats['rate_limited']}", err=True)
    typer.echo(f"Skipped:      {stats['skipped']}", err=True)
    typer.echo(f"Output:       {output_path}", err=True)

    print_json({"stats": stats, "output_dir": str(output_path)})
