"""Batch processing functionality for youtube-transcripts skill.

This module handles bulk transcript fetching with:
- Resume capability via state file
- Exponential backoff on rate limits
- Smart delays based on method used
"""
from __future__ import annotations

import random
import time
from pathlib import Path

import typer

from youtube_transcripts.config import (
    load_proxy_settings,
    CONSECUTIVE_FAILURE_THRESHOLD,
    EXTENDED_BREAK_DURATION,
    SMART_DELAY_DIRECT,
    SMART_DELAY_PROXY,
)
from youtube_transcripts.utils import is_rate_limit_error
from youtube_transcripts.downloader import fetch_video_metadata
from youtube_transcripts.transcriber import (
    fetch_single_transcript_with_backoff,
    transcribe_with_whisper_fallback,
)
from youtube_transcripts.formatter import (
    build_result,
    save_json,
    BatchStateManager,
    print_batch_summary,
)


def run_batch(
    input_path: Path,
    output_path: Path,
    delay_min: int,
    delay_max: int,
    lang: str,
    no_proxy: bool,
    no_whisper: bool,
    resume: bool,
    max_videos: int,
    backoff_base: int,
    backoff_max: int,
) -> None:
    """Run batch processing of YouTube videos.

    Args:
        input_path: Path to file with video IDs (one per line)
        output_path: Directory for output transcripts
        delay_min: Minimum delay between requests (seconds)
        delay_max: Maximum delay between requests (seconds)
        lang: Language code
        no_proxy: Skip proxy usage
        no_whisper: Skip Whisper fallback
        resume: Resume from last position
        max_videos: Maximum videos to process (0 = all)
        backoff_base: Base backoff delay (seconds)
        backoff_max: Maximum backoff delay (seconds)
    """
    if not input_path.exists():
        typer.echo(f"Error: Input file not found: {input_path}", err=True)
        raise typer.Exit(code=1)

    # Check proxy configuration
    use_proxy = not no_proxy
    if use_proxy and load_proxy_settings() is None:
        typer.echo("WARNING: IPRoyal proxy not configured. Bulk downloads may fail.", err=True)
        typer.echo("Set: IPROYAL_HOST, IPROYAL_PORT, IPROYAL_USER, IPROYAL_PASSWORD", err=True)
        use_proxy = False

    # Read video IDs
    with open(input_path) as f:
        video_ids = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    if not video_ids:
        typer.echo("Error: No video IDs found in input file", err=True)
        raise typer.Exit(code=1)

    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)

    # Initialize state manager
    state_manager = BatchStateManager(output_path / ".batch_state.json")
    if resume:
        if state_manager.load():
            typer.echo(f"Resuming: {len(state_manager.completed)} already completed", err=True)

    # Filter out completed
    pending = [vid for vid in video_ids if not state_manager.is_completed(vid)]
    if max_videos > 0:
        pending = pending[:max_videos]

    total = len(pending)
    proxy_status = "IPRoyal proxy" if use_proxy else "direct (no proxy)"
    typer.echo(f"Processing {total} videos via {proxy_status}", err=True)
    typer.echo(f"Delay: {delay_min}-{delay_max}s | Backoff: {backoff_base}-{backoff_max}s", err=True)

    for idx, vid in enumerate(pending, 1):
        _process_single_video(
            vid=vid,
            idx=idx,
            total=total,
            output_path=output_path,
            lang=lang,
            use_proxy=use_proxy,
            no_whisper=no_whisper,
            resume=resume,
            backoff_base=backoff_base,
            backoff_max=backoff_max,
            delay_min=delay_min,
            delay_max=delay_max,
            state_manager=state_manager,
        )

    print_batch_summary(state_manager.stats, output_path)


def _process_single_video(
    vid: str,
    idx: int,
    total: int,
    output_path: Path,
    lang: str,
    use_proxy: bool,
    no_whisper: bool,
    resume: bool,
    backoff_base: int,
    backoff_max: int,
    delay_min: int,
    delay_max: int,
    state_manager: BatchStateManager,
) -> None:
    """Process a single video in batch mode."""
    typer.echo(f"\n[{idx}/{total}] Processing: {vid}", err=True)
    state_manager.save(vid, "fetching")

    out_file = output_path / f"{vid}.json"
    if out_file.exists() and resume:
        typer.echo(f"  Skipping (already exists): {out_file}", err=True)
        state_manager.mark_completed(vid)
        state_manager.record_skipped()
        return

    t0 = time.time()

    # Fetch with backoff
    transcript, full_text, method, error = fetch_single_transcript_with_backoff(
        vid, lang, use_proxy, backoff_base, backoff_max
    )

    # Try Whisper fallback if enabled
    if not method and not no_whisper:
        typer.echo(f"  Trying Whisper fallback...", err=True)
        state_manager.save(vid, "whisper")
        transcript, full_text, method, whisper_error = transcribe_with_whisper_fallback(
            vid, lang, use_local=True
        )
        if not method:
            error = whisper_error

    took_ms = int((time.time() - t0) * 1000)
    metadata = fetch_video_metadata(vid)

    result = build_result(
        vid=vid,
        lang=lang,
        took_ms=took_ms,
        method=method,
        transcript=transcript,
        full_text=full_text,
        errors=[error] if error else [],
        metadata=metadata,
    )

    save_json(result, out_file)

    if method:
        typer.echo(f"  Success ({method}, {took_ms}ms): {out_file.name}", err=True)
        state_manager.record_success(method)
    else:
        if error and is_rate_limit_error(error):
            typer.echo(f"  Rate limited: {error[:80]}...", err=True)
            state_manager.record_failure(is_rate_limit=True)
        else:
            typer.echo(f"  Failed: {error[:80] if error else 'Unknown'}...", err=True)
            state_manager.record_failure(is_rate_limit=False)

    state_manager.mark_completed(vid)
    state_manager.save("", "")

    # Check for too many consecutive rate limits
    if state_manager.consecutive_failures >= CONSECUTIVE_FAILURE_THRESHOLD:
        typer.echo(f"\n  WARNING: {state_manager.consecutive_failures} consecutive rate limits!", err=True)
        typer.echo(f"  Taking extended break ({EXTENDED_BREAK_DURATION // 60} min)...", err=True)
        time.sleep(EXTENDED_BREAK_DURATION)
        state_manager.consecutive_failures = 0

    # Delay before next (except for last)
    if idx < total:
        if method == "direct":
            actual_delay = random.randint(*SMART_DELAY_DIRECT)
        elif method == "proxy":
            actual_delay = random.randint(*SMART_DELAY_PROXY)
        else:
            delay = random.randint(delay_min, delay_max)
            jitter = random.uniform(0.9, 1.1)
            actual_delay = int(delay * jitter)
        typer.echo(f"  Waiting {actual_delay}s before next...", err=True)
        time.sleep(actual_delay)
