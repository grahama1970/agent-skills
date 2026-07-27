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
    create_webshare_proxy_config,
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
from youtube_transcripts.enrichment import enrich_transcript

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
    no_enrich: bool = True,
) -> dict:
    """Core logic to fetch transcript with fallback and optional doc2qra enrichment."""
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
    # Local faster-whisper needs no API key; OpenAI API is a sub-fallback within Tier 3
    if errors and not no_whisper:
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

    # Legacy enrichment is opt-in until this path is routed through Tau.
    summary = ""
    qra: list[dict] = []
    if method and full_text and not no_enrich:
        typer.echo("Enriching transcript via legacy scillm path (summary + QRA)...", err=True)
        if monitor:
            monitor.update(0, item="Enriching via legacy scillm")
        enrichment = enrich_transcript(
            full_text=full_text,
            metadata=metadata,
        )
        summary = enrichment.get("summary", "")
        qra = enrichment.get("qra", [])
        if summary:
            typer.echo(f"  Summary: {len(summary)} chars, {len(qra)} QRA pairs", err=True)

    return build_result(
        vid=vid,
        lang=lang,
        took_ms=took_ms,
        method=method,
        transcript=transcript,
        full_text=full_text,
        errors=all_errors if errors else [],
        metadata=metadata,
        summary=summary,
        qra=qra,
    )


@app.command()
def get(
    url: str = typer.Option("", "--url", "-u", help="YouTube video URL"),
    video_id: str = typer.Option("", "--video-id", "-i", help="YouTube video ID"),
    lang: str = typer.Option("en", "--lang", "-l", help="Language code"),
    no_proxy: bool = typer.Option(False, "--no-proxy", help="Skip proxy tier"),
    no_whisper: bool = typer.Option(False, "--no-whisper", help="Skip Whisper fallback"),
    enrich: bool = typer.Option(False, "--enrich/--no-enrich", help="Opt into legacy transcript enrichment (summary + QRA)"),
    learn: bool = typer.Option(False, "--learn", help="Store transcript + enrichment to ArangoDB memory"),
    scope: str = typer.Option("research", "--scope", "-s", help="Memory scope for --learn"),
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

    out = _get_transcript_logic(vid, lang, no_proxy, no_whisper, retries, monitor=monitor, no_enrich=not enrich)
    print_json(out)

    if out.get("errors"):
        raise typer.Exit(code=1)

    if learn and out.get("meta", {}).get("method"):
        from memory_integration import learn_transcript
        meta = out["meta"]
        ids = learn_transcript(
            video_id=vid,
            title=meta.get("title", ""),
            channel=meta.get("channel", ""),
            duration_sec=meta.get("duration_sec", 0),
            method=meta.get("method", ""),
            word_count=len(out.get("full_text", "").split()),
            summary=out.get("summary", ""),
            qra_count=len(out.get("qra", [])),
            scope=scope,
        )
        if ids:
            typer.echo(f"Learned to memory ({scope}): {len(ids)} entries", err=True)


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
                proxy_settings = load_proxy_settings() if use_proxy else None
                if proxy_settings:
                    proxy_used = True
                    if attempt > 0:
                        typer.echo(f"Retry {attempt}/{retries}...", err=True)
                    wpc = create_webshare_proxy_config(proxy_settings)
                    api = YouTubeTranscriptApi(proxy_config=wpc)
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
    """Check if Webshare proxy is configured correctly."""
    proxy_settings = load_proxy_settings()

    if not proxy_settings:
        result = build_proxy_check_result(
            configured=False,
            error="Missing WEBSHARE_API_KEY environment variable",
        )
    else:
        try:
            import httpx
            # Use Webshare proxy endpoint for IP check
            wpc = create_webshare_proxy_config(proxy_settings)
            # WebshareProxyConfig builds the proxy URL internally;
            # for the IP check we construct the URL manually
            proxy_url = f"http://{proxy_settings['username']}:{proxy_settings['password']}@p.webshare.io:80"
            client = httpx.Client(proxy=proxy_url, timeout=15.0)
            resp = client.get("https://api.ipify.org?format=json")
            first_ip = resp.json().get("ip", "unknown")
            client.close()

            rotation_test = None
            if test_rotation:
                client2 = httpx.Client(proxy=proxy_url, timeout=15.0)
                resp2 = client2.get("https://api.ipify.org?format=json")
                second_ip = resp2.json().get("ip", "unknown")
                client2.close()
                rotation_test = {
                    "first_ip": first_ip,
                    "second_ip": second_ip,
                    "ip_rotated": first_ip != second_ip,
                    "note": "Webshare auto-rotates IPs between requests",
                }

            result = build_proxy_check_result(
                configured=True, proxy_config={"username": proxy_settings["username"]},
                test_ip=first_ip, rotation_test=rotation_test,
            )
        except Exception as e:
            result = build_proxy_check_result(
                configured=True, proxy_config={"username": proxy_settings["username"]}, error=str(e),
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
