#!/usr/bin/env python3
"""YouTube transcript extraction CLI with three-tier fallback."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional, Any

import typer

# Add parent to path for package imports
SKILL_DIR = Path(__file__).resolve().parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from youtube_transcripts.config import (
    load_proxy_settings,
    get_openai_api_key,
    SKILLS_DIR,
    BATCH_DELAY_MIN,
    BATCH_DELAY_MAX,
    BACKOFF_BASE,
    BACKOFF_MAX,
)
from youtube_transcripts.utils import (
    extract_video_id,
    is_rate_limit_error,
    create_proxied_http_client,
)
from youtube_transcripts.downloader import (
    fetch_video_metadata,
    search_videos,
)
from youtube_transcripts.transcriber import (
    fetch_transcript_with_retry,
    transcribe_with_whisper_fallback,
)
from youtube_transcripts.formatter import (
    build_result,
    build_languages_result,
    build_proxy_check_result,
    print_json,
    save_json,
    print_search_results_table,
)
from youtube_transcripts.batch import run_batch

# Optional monitor import
try:
    sys.path.append(str(SKILLS_DIR / "task-monitor"))
    from monitor_adapter import Monitor
except ImportError:
    Monitor = None

app = typer.Typer(add_completion=False, help="Extract YouTube video transcripts")


def _get_transcript_logic(
    vid: str,
    lang: str,
    no_proxy: bool,
    no_whisper: bool,
    retries: int,
    monitor: Optional[Any] = None,
) -> dict:
    """Core logic to fetch transcript with fallback."""
    t0 = time.time()
    transcript: list[dict] = []
    full_text = ""
    errors: list[str] = []
    method = None
    all_errors: list[str] = []

    # TIER 1: Direct (no proxy)
    typer.echo("Tier 1: Trying direct youtube-transcript-api...", err=True)
    if monitor:
        monitor.update(0, item="Tier 1: Direct API")
    try:
        transcript, full_text, errors, _, _ = fetch_transcript_with_retry(
            vid, lang, use_proxy=False, max_retries=0
        )
        if not errors:
            method = "direct"
            if monitor:
                monitor.update(1, item="Found in Tier 1")
    except ImportError as e:
        errors = [str(e)]

    if errors:
        all_errors.append(f"Tier 1 (direct): {errors[0]}")

    # TIER 2: With proxy (if available and tier 1 failed)
    if errors and not no_proxy and load_proxy_settings() is not None:
        typer.echo(f"Tier 2: Trying with IPRoyal proxy (retries: {retries})...", err=True)
        if monitor:
            monitor.update(0, item="Tier 2: Proxy API")
        try:
            transcript, full_text, errors, _, _ = fetch_transcript_with_retry(
                vid, lang, use_proxy=True, max_retries=retries
            )
            if not errors:
                method = "proxy"
                if monitor:
                    monitor.update(1, item="Found in Tier 2")
        except Exception as e:
            errors = [str(e)]

        if errors:
            all_errors.append(f"Tier 2 (proxy): {errors[0]}")

    # TIER 3: Whisper fallback (if tiers 1-2 failed)
    if errors and not no_whisper and get_openai_api_key():
        typer.echo("Tier 3: Trying yt-dlp + Whisper fallback...", err=True)
        if monitor:
            monitor.update(0, item="Tier 3: yt-dlp + Whisper")

        transcript, full_text, whisper_method, whisper_error = transcribe_with_whisper_fallback(
            vid, lang, use_local=True
        )

        if whisper_method:
            method = whisper_method
            errors = []
            if monitor:
                monitor.update(1, item="Found in Tier 3")
        else:
            all_errors.append(f"Tier 3 (whisper): {whisper_error}")

    took_ms = int((time.time() - t0) * 1000)
    metadata = fetch_video_metadata(vid)

    return build_result(
        vid=vid,
        lang=lang,
        took_ms=took_ms,
        method=method,
        transcript=transcript,
        full_text=full_text,
        errors=all_errors if errors else [],
        metadata=metadata,
    )


@app.command()
def get(
    url: str = typer.Option("", "--url", "-u", help="YouTube video URL"),
    video_id: str = typer.Option("", "--video-id", "-i", help="YouTube video ID"),
    lang: str = typer.Option("en", "--lang", "-l", help="Language code"),
    no_proxy: bool = typer.Option(False, "--no-proxy", help="Skip proxy tier"),
    no_whisper: bool = typer.Option(False, "--no-whisper", help="Skip Whisper fallback"),
    retries: int = typer.Option(3, "--retries", "-r", help="Max retries per tier"),
):
    """Get transcript for a YouTube video using three-tier fallback."""
    vid = extract_video_id(video_id or url)
    if not vid:
        out = build_result(
            vid=None, lang=lang, took_ms=0, method=None,
            transcript=[], full_text="",
            errors=["Could not extract video ID from URL or --video-id"],
        )
        print_json(out)
        raise typer.Exit(code=1)

    monitor = None
    if Monitor and (no_proxy or not no_whisper):
        state_file = Path.home() / ".pi" / "youtube-transcripts" / f"state_{vid}.json"
        monitor = Monitor(
            name=f"yt-{vid}", total=1,
            desc=f"Transcribing YouTube: {vid}",
            state_file=str(state_file)
        )

    out = _get_transcript_logic(vid, lang, no_proxy, no_whisper, retries, monitor=monitor)
    print_json(out)

    if out.get("errors"):
        raise typer.Exit(code=1)


@app.command("list-languages")
def list_languages(
    url: str = typer.Option("", "--url", "-u", help="YouTube video URL"),
    video_id: str = typer.Option("", "--video-id", "-i", help="YouTube video ID"),
    no_proxy: bool = typer.Option(False, "--no-proxy", help="Disable proxy rotation"),
    retries: int = typer.Option(3, "--retries", "-r", help="Max retries with IP rotation"),
):
    """List available transcript languages for a video."""
    t0 = time.time()
    errors: list[str] = []
    languages: list[dict] = []
    proxy_used = False
    retries_used = 0

    vid = extract_video_id(video_id or url)
    if not vid:
        out = build_languages_result(
            vid=None, took_ms=0, proxy_used=False,
            retries_used=0, languages=[], errors=["Could not extract video ID"],
        )
        print_json(out)
        raise typer.Exit(code=1)

    use_proxy = not no_proxy and load_proxy_settings() is not None

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import TranscriptsDisabled, VideoUnavailable

        for attempt in range(retries + 1):
            try:
                proxy_config = load_proxy_settings() if use_proxy else None
                if proxy_config:
                    proxy_used = True
                    if attempt > 0:
                        typer.echo(f"Retry {attempt}/{retries}...", err=True)
                    http_client = create_proxied_http_client(proxy_config)
                    api = YouTubeTranscriptApi(http_client=http_client)
                else:
                    api = YouTubeTranscriptApi()

                transcript_list = api.list(vid)
                for t in transcript_list:
                    languages.append({
                        "language": t.language,
                        "language_code": t.language_code,
                        "is_generated": t.is_generated,
                        "is_translatable": t.is_translatable,
                    })
                retries_used = attempt
                errors = []
                break
            except TranscriptsDisabled:
                errors = ["Transcripts are disabled for this video"]
                break
            except VideoUnavailable:
                errors = ["Video is unavailable"]
                break
            except Exception as e:
                error_msg = str(e)
                errors = [error_msg]
                if is_rate_limit_error(error_msg) and attempt < retries and use_proxy:
                    time.sleep(1)
                    continue
                break
    except ImportError:
        errors = ["youtube-transcript-api not installed"]

    took_ms = int((time.time() - t0) * 1000)
    out = build_languages_result(vid, took_ms, proxy_used, retries_used, languages, errors)
    print_json(out)


@app.command()
def check_proxy(
    test_rotation: bool = typer.Option(False, "--test-rotation", help="Test IP rotation"),
):
    """Check if IPRoyal proxy is configured correctly."""
    proxy_config = load_proxy_settings()

    if not proxy_config:
        result = build_proxy_check_result(
            configured=False,
            error="Missing environment variables. Need: IPROYAL_HOST, IPROYAL_PORT, IPROYAL_USER, IPROYAL_PASSWORD",
        )
    else:
        try:
            session = create_proxied_http_client(proxy_config)
            resp = session.get("https://api.ipify.org?format=json", timeout=15)
            ip_info = resp.json()
            first_ip = ip_info.get("ip", "unknown")

            rotation_test = None
            if test_rotation:
                session2 = create_proxied_http_client(proxy_config)
                resp2 = session2.get("https://api.ipify.org?format=json", timeout=15)
                second_ip = resp2.json().get("ip", "unknown")
                rotation_test = {
                    "first_ip": first_ip,
                    "second_ip": second_ip,
                    "ip_rotated": first_ip != second_ip,
                    "note": "IPRoyal auto-rotates IPs between requests",
                }

            result = build_proxy_check_result(
                configured=True, proxy_config=proxy_config,
                test_ip=first_ip, rotation_test=rotation_test,
            )
        except Exception as e:
            result = build_proxy_check_result(
                configured=True, proxy_config=proxy_config, error=str(e),
            )

    print_json(result)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    max_results: int = typer.Option(5, "--max", "-n", help="Max results"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", help="Interactive mode"),
):
    """Search for YouTube videos."""
    results = search_videos(query, max_results=max_results)

    if not interactive or not sys.stdin.isatty():
        print_json(results)
        return

    try:
        from rich.prompt import Prompt
        from rich import print as rprint
    except ImportError:
        print_json(results)
        return

    print_search_results_table(results, query)

    selection = Prompt.ask("Select videos (e.g. 1,3 or 'all' or 'q')", default="q")
    if selection.lower() == 'q':
        return

    if selection.lower() == 'all':
        indices = range(len(results))
    else:
        try:
            parts = [p.strip() for p in selection.split(",")]
            indices = [int(p) - 1 for p in parts if p.isdigit()]
        except (ValueError, AttributeError):
            rprint("[red]Invalid selection[/red]")
            return

    for idx in indices:
        if 0 <= idx < len(results):
            vid = results[idx].get("id")
            title = results[idx].get("title", vid)
            rprint(f"\n[bold green]Processing:[/bold green] {title} ({vid})")

            result = _get_transcript_logic(
                vid=vid, lang="en", no_proxy=False, no_whisper=False, retries=3
            )

            if result.get("transcript"):
                rprint(f"  [cyan]Success[/cyan]: {len(result['full_text'])} chars via {result['meta'].get('method')}")
                fname = f"{vid}_transcript.json"
                save_json(result, Path(fname))
                rprint(f"  Saved to: [underline]{fname}[/underline]")
            else:
                rprint(f"  [red]Failed[/red]: {result.get('errors')}")


@app.command()
def batch(
    input_file: str = typer.Option(..., "--input", "-f", help="File with video IDs"),
    output_dir: str = typer.Option("./transcripts", "--output", "-o", help="Output directory"),
    delay_min: int = typer.Option(BATCH_DELAY_MIN, "--delay-min", help="Min delay (seconds)"),
    delay_max: int = typer.Option(BATCH_DELAY_MAX, "--delay-max", help="Max delay (seconds)"),
    lang: str = typer.Option("en", "--lang", "-l", help="Language code"),
    no_proxy: bool = typer.Option(False, "--no-proxy", help="Skip proxy"),
    no_whisper: bool = typer.Option(True, "--no-whisper/--whisper", help="Skip Whisper"),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Resume from last"),
    max_videos: int = typer.Option(0, "--max", "-n", help="Max videos (0 = all)"),
    backoff_base: int = typer.Option(BACKOFF_BASE, "--backoff-base", help="Base backoff"),
    backoff_max: int = typer.Option(BACKOFF_MAX, "--backoff-max", help="Max backoff"),
):
    """Batch process YouTube videos with proxy and exponential backoff."""
    run_batch(
        input_path=Path(input_file),
        output_path=Path(output_dir),
        delay_min=delay_min,
        delay_max=delay_max,
        lang=lang,
        no_proxy=no_proxy,
        no_whisper=no_whisper,
        resume=resume,
        max_videos=max_videos,
        backoff_base=backoff_base,
        backoff_max=backoff_max,
    )


if __name__ == "__main__":
    app()
