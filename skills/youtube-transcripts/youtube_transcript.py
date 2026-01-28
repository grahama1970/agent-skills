#!/usr/bin/env python3
"""YouTube transcript extraction CLI with three-tier fallback.

Fallback chain:
1. Standard youtube-transcript-api (direct)
2. youtube-transcript-api with IPRoyal proxy rotation
3. Download audio via yt-dlp → OpenAI Whisper transcription

Self-contained - no database dependencies.
Outputs JSON to stdout for pipeline integration.

Requires: pip install youtube-transcript-api requests yt-dlp openai

Environment variables:
    # For proxy (tier 2):
    IPROYAL_HOST     - Proxy host (e.g., geo.iproyal.com)
    IPROYAL_PORT     - Proxy port (e.g., 12321)
    IPROYAL_USER     - Proxy username
    IPROYAL_PASSWORD - Proxy password

    # For Whisper fallback (tier 3):
    OPENAI_API_KEY   - OpenAI API key for Whisper
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

SKILLS_DIR = Path(__file__).resolve().parents[1]
if str(SKILLS_DIR) not in sys.path:
    sys.path.append(str(SKILLS_DIR))

try:
    from dotenv_helper import load_env as _load_env  # type: ignore
except Exception:
    def _load_env():
        try:
            from dotenv import load_dotenv, find_dotenv  # type: ignore
            load_dotenv(find_dotenv(usecwd=True), override=False)
        except Exception:
            pass

_load_env()

# Import Task-Monitor adapter if available
try:
    sys.path.append(str(SKILLS_DIR / "task-monitor"))
    from monitor_adapter import Monitor
except ImportError:
    Monitor = None


import typer

app = typer.Typer(add_completion=False, help="Extract YouTube video transcripts")


def _load_proxy_settings() -> Optional[dict]:
    """Load IPRoyal proxy settings from environment.

    Returns dict with proxy config, or None if not configured.

    Note: IPRoyal residential proxies automatically rotate IPs between requests,
    so no session ID manipulation is needed.
    """
    host = os.getenv("IPROYAL_HOST", "").strip()
    port = os.getenv("IPROYAL_PORT", "").strip()
    user = os.getenv("IPROYAL_USER", "").strip()
    password = os.getenv("IPROYAL_PASSWORD", os.getenv("IPROYAL_PASS", "")).strip()

    if not all([host, port, user, password]):
        return None

    return {
        "host": host,
        "port": port,
        "username": user,
        "password": password,
    }


def _fetch_video_metadata(vid: str) -> dict:
    """Fetch video metadata using yt-dlp (fast extraction)."""
    try:
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,  # Fast extraction (no download)
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
            return {
                "title": info.get("title", ""),
                "channel": info.get("uploader", ""),
                "upload_date": info.get("upload_date", ""),
                "duration_sec": info.get("duration", 0),
                "description": info.get("description", ""),  # Video abstract/description
                "view_count": info.get("view_count", 0),
            }
    except Exception:
        # Silent fail on metadata
        return {}

def _search_videos(query: str, max_results: int = 5) -> list[dict]:
    """Search YouTube videos using yt-dlp."""
    try:
        import yt_dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # ytsearchN:query syntax searches for N results
            info = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            results = []
            if "entries" in info:
                for entry in info["entries"]:
                    results.append({
                        "title": entry.get("title", ""),
                        "id": entry.get("id"),
                        "url": entry.get("url") or f"https://www.youtube.com/watch?v={entry.get('id')}",
                        "duration": entry.get("duration"),
                        "uploader": entry.get("uploader"),
                        "view_count": entry.get("view_count"),
                        "description": entry.get("description", ""),
                    })
            return results
    except Exception as e:
        return [{"error": str(e)}]



def _extract_video_id(url_or_id: str) -> str | None:
    """Extract video ID from URL or return as-is if already an ID."""
    s = (url_or_id or "").strip()

    # Already a video ID (11 chars, alphanumeric + - _)
    if re.match(r"^[\w-]{11}$", s):
        return s

    # Standard watch URL
    m = re.search(r"[?&]v=([\w-]{11})", s)
    if m:
        return m.group(1)

    # Short URL (youtu.be/VIDEO_ID)
    m = re.search(r"youtu\.be/([\w-]{11})", s)
    if m:
        return m.group(1)

    # Embed URL
    m = re.search(r"embed/([\w-]{11})", s)
    if m:
        return m.group(1)

    return None


def _create_proxied_http_client(proxy_config: dict):
    """Create a requests-based HTTP client with proxy support.

    The youtube-transcript-api uses requests internally, so we create
    a custom session with proxy configuration.
    """
    import requests
    from urllib.parse import quote

    host = proxy_config["host"]
    port = proxy_config["port"]
    username = quote(proxy_config["username"], safe="")
    password = quote(proxy_config["password"], safe="")

    # Build proxy URL with credentials embedded
    proxy_url = f"http://{username}:{password}@{host}:{port}"

    session = requests.Session()
    session.proxies = {
        "http": proxy_url,
        "https": proxy_url,
    }

    # Set reasonable timeouts
    session.timeout = 30

    return session


def _is_retriable_error(error_msg: str) -> bool:
    """Check if error is retriable with IP rotation."""
    retriable_patterns = [
        "429", "Too Many Requests",
        "403", "Forbidden",
        "blocked", "captcha",
        "rate limit", "quota",
    ]
    lower_msg = error_msg.lower()
    return any(p.lower() in lower_msg for p in retriable_patterns)


def _download_audio_ytdlp(vid: str, output_dir: Path) -> tuple[Optional[Path], Optional[str]]:
    """Download audio from YouTube video using yt-dlp.

    Returns: (audio_path, error_message)
    """
    try:
        import yt_dlp
    except ImportError:
        return None, "yt-dlp not installed. Run: pip install yt-dlp"

    url = f"https://www.youtube.com/watch?v={vid}"
    output_template = str(output_dir / "%(id)s.%(ext)s")

    ydl_opts = {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])

        # Find the downloaded file
        audio_path = output_dir / f"{vid}.mp3"
        if audio_path.exists():
            return audio_path, None
        else:
            # Try to find any audio file
            for ext in ["mp3", "m4a", "webm", "opus"]:
                p = output_dir / f"{vid}.{ext}"
                if p.exists():
                    return p, None
            return None, "Audio file not found after download"

    except Exception as e:
        return None, f"yt-dlp error: {e}"


def _transcribe_whisper(audio_path: Path, lang: str) -> tuple[list[dict], str, Optional[str]]:
    """Transcribe audio using OpenAI Whisper API.

    Returns: (transcript_segments, full_text, error_message)
    """
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        return [], "", "OPENAI_API_KEY not set for Whisper fallback"

    try:
        from openai import OpenAI
    except ImportError:
        return [], "", "openai not installed. Run: pip install openai"

    try:
        client = OpenAI(api_key=api_key)

        with open(audio_path, "rb") as audio_file:
            # Use verbose_json to get timestamps
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=lang if lang != "en" else None,  # None = auto-detect for English
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        # Convert to our transcript format
        transcript = []
        if hasattr(response, "segments") and response.segments:
            for seg in response.segments:
                transcript.append({
                    "text": seg.get("text", "").strip(),
                    "start": seg.get("start", 0.0),
                    "duration": seg.get("end", 0.0) - seg.get("start", 0.0),
                })
        else:
            # Fallback if no segments (put all text in one segment)
            transcript = [{
                "text": response.text,
                "start": 0.0,
                "duration": 0.0,
            }]

        full_text = " ".join(seg["text"] for seg in transcript)
        return transcript, full_text, None

    except Exception as e:
        return [], "", f"Whisper API error: {e}"


# Cache for local Whisper model (avoid reloading)
_LOCAL_WHISPER_MODEL = None


def _transcribe_whisper_local(audio_path: Path, lang: str, model_size: str = "base") -> tuple[list[dict], str, Optional[str]]:
    """Transcribe audio using faster-whisper (CTranslate2 optimized, 4-8x faster).

    Model sizes: tiny, base, small, medium, large-v3
    - tiny: fastest, lowest quality
    - base: good balance (default)
    - small: better quality
    - medium: high quality
    - large-v3: best quality

    Returns: (transcript_segments, full_text, error_message)
    """
    global _LOCAL_WHISPER_MODEL

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return [], "", "faster-whisper not installed. Run: pip install faster-whisper"

    try:
        # Load model (cached after first load)
        if _LOCAL_WHISPER_MODEL is None:
            typer.echo(f"    Loading faster-whisper model '{model_size}' (first time only)...", err=True)
            # Use GPU with float16 for speed, fall back to CPU with int8
            try:
                _LOCAL_WHISPER_MODEL = WhisperModel(model_size, device="cuda", compute_type="float16")
                typer.echo(f"    Using GPU (CUDA) with float16", err=True)
            except Exception:
                _LOCAL_WHISPER_MODEL = WhisperModel(model_size, device="cpu", compute_type="int8")
                typer.echo(f"    Using CPU with int8", err=True)

        # Transcribe - faster-whisper returns a generator
        segments_gen, info = _LOCAL_WHISPER_MODEL.transcribe(
            str(audio_path),
            language=lang if lang != "en" else None,
            beam_size=5,
            vad_filter=True,  # Filter out silence for speed
        )

        # Convert to our transcript format
        transcript = []
        full_text_parts = []
        for seg in segments_gen:
            text = seg.text.strip()
            transcript.append({
                "text": text,
                "start": seg.start,
                "duration": seg.end - seg.start,
            })
            full_text_parts.append(text)

        full_text = " ".join(full_text_parts)
        if not transcript and full_text:
            transcript = [{"text": full_text, "start": 0.0, "duration": 0.0}]

        return transcript, full_text, None

    except Exception as e:
        return [], "", f"faster-whisper error: {e}"


def _fetch_transcript_with_retry(
    vid: str,
    lang: str,
    use_proxy: bool,
    max_retries: int = 3,
) -> tuple[list[dict], str, list[str], bool, int]:
    """Fetch transcript with retry and IP rotation on failure.

    Returns: (transcript, full_text, errors, proxy_used, retries_used)
    """
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        NoTranscriptFound,
        TranscriptsDisabled,
        VideoUnavailable,
    )

    transcript: list[dict] = []
    full_text = ""
    errors: list[str] = []
    proxy_used = False
    retries_used = 0

    for attempt in range(max_retries + 1):
        try:
            # IPRoyal auto-rotates IPs, so each new request gets a fresh IP
            proxy_config = _load_proxy_settings() if use_proxy else None

            if proxy_config:
                proxy_used = True
                if attempt > 0:
                    typer.echo(f"Retry {attempt}/{max_retries} (IPRoyal auto-rotates IP)...", err=True)
                http_client = _create_proxied_http_client(proxy_config)
                api = YouTubeTranscriptApi(http_client=http_client)
            else:
                api = YouTubeTranscriptApi()

            fetched = api.fetch(vid, languages=[lang])

            # Success - convert to list of dicts
            transcript = [
                {
                    "text": seg.text,
                    "start": seg.start,
                    "duration": seg.duration,
                }
                for seg in fetched
            ]
            full_text = " ".join(seg["text"] for seg in transcript)
            retries_used = attempt
            errors = []  # Clear errors on success
            break

        except TranscriptsDisabled:
            errors = ["Transcripts are disabled for this video"]
            break  # Not retriable
        except VideoUnavailable:
            errors = ["Video is unavailable"]
            break  # Not retriable
        except NoTranscriptFound:
            errors = [f"No transcript found for language: {lang}"]
            break  # Not retriable
        except Exception as e:
            error_msg = str(e)
            errors = [error_msg]

            # Check if retriable
            if _is_retriable_error(error_msg) and attempt < max_retries and use_proxy:
                typer.echo(f"Error: {error_msg[:80]}... Retrying with IP rotation.", err=True)
                time.sleep(1)  # Brief delay before retry
                continue
            else:
                # Not retriable or out of retries
                if "429" in error_msg or "Too Many Requests" in error_msg:
                    errors = [f"Rate limited by YouTube after {attempt + 1} attempts. ({error_msg})"]
                elif "403" in error_msg or "Forbidden" in error_msg:
                    errors = [f"Access forbidden after {attempt + 1} attempts. ({error_msg})"]
                break

    return transcript, full_text, errors, proxy_used, retries_used


def _get_transcript_logic(
    vid: str,
    lang: str,
    no_proxy: bool,
    no_whisper: bool,
    retries: int,
    monitor: Optional[Any] = None,
) -> dict:
    """Core logic to fetch transcript with fallback. Returns dict ready for output."""

    t0 = time.time()
    
    transcript: list[dict] = []
    full_text = ""
    errors: list[str] = []
    method = None
    all_errors: list[str] = []

    # TIER 1: Direct (no proxy)
    typer.echo("Tier 1: Trying direct youtube-transcript-api...", err=True)
    if monitor: monitor.update(0, item="Tier 1: Direct API")
    try:
        transcript, full_text, errors, _, _ = _fetch_transcript_with_retry(
            vid, lang, use_proxy=False, max_retries=0
        )
        if not errors:
            method = "direct"
            if monitor: monitor.update(1, item="Found in Tier 1")

    except ImportError as e:
        errors = [str(e)]

    if errors:
        all_errors.append(f"Tier 1 (direct): {errors[0]}")

    # TIER 2: With proxy (if available and tier 1 failed)
    if errors and not no_proxy and _load_proxy_settings() is not None:
        typer.echo(f"Tier 2: Trying with IPRoyal proxy (retries: {retries})...", err=True)
        if monitor: monitor.update(0, item="Tier 2: Proxy API")
        try:
            transcript, full_text, errors, _, _ = _fetch_transcript_with_retry(
                vid, lang, use_proxy=True, max_retries=retries
            )
            if not errors:
                method = "proxy"
                if monitor: monitor.update(1, item="Found in Tier 2")

        except Exception as e:
            errors = [str(e)]

        if errors:
            all_errors.append(f"Tier 2 (proxy): {errors[0]}")

    # TIER 3: Whisper fallback (if tiers 1-2 failed)
    if errors and not no_whisper and os.getenv("OPENAI_API_KEY"):
        typer.echo("Tier 3: Trying yt-dlp + Whisper fallback...", err=True)
        if monitor: monitor.update(0, item="Tier 3: yt-dlp + Whisper")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Download audio
            typer.echo("  Downloading audio with yt-dlp...", err=True)
            if monitor: monitor.update(0, item="Downloading Audio")
            audio_path, dl_error = _download_audio_ytdlp(vid, tmppath)

            if dl_error:
                all_errors.append(f"Tier 3 (whisper): Download failed - {dl_error}")
            elif audio_path:
                # Transcribe with local Whisper first (free)
                typer.echo("  Transcribing with local Whisper...", err=True)
                if monitor: monitor.update(0, item="Transcribing (Whisper)")
                transcript, full_text, whisper_error = _transcribe_whisper_local(audio_path, lang)

                if whisper_error:
                    # Fallback to API if local fails
                    if os.getenv("OPENAI_API_KEY"):
                        typer.echo("  Local failed, trying Whisper API...", err=True)
                        if monitor: monitor.update(0, item="Transcribing (Whisper API)")
                        transcript, full_text, whisper_error = _transcribe_whisper(audio_path, lang)

                if whisper_error:
                    all_errors.append(f"Tier 3 (whisper): {whisper_error}")
                    errors = [whisper_error]
                else:
                    errors = []
                    method = "whisper-local" if "local" not in (whisper_error or "") else "whisper-api"
                    if monitor: monitor.update(1, item="Found in Tier 3")


    took_ms = int((time.time() - t0) * 1000)

    # Fetch metadata (title, etc.)
    metadata = _fetch_video_metadata(vid)

    # Build output
    return {
        "meta": {
            "video_id": vid,
            "language": lang,
            "took_ms": took_ms,
            "method": method,
            **metadata,  # Merge title, channel, etc.
        },
        "transcript": transcript,
        "full_text": full_text,
        "errors": all_errors if errors else [],
    }


@app.command()
def get(
    url: str = typer.Option("", "--url", "-u", help="YouTube video URL"),
    video_id: str = typer.Option("", "--video-id", "-i", help="YouTube video ID"),
    lang: str = typer.Option("en", "--lang", "-l", help="Language code"),
    no_proxy: bool = typer.Option(False, "--no-proxy", help="Skip proxy tier"),
    no_whisper: bool = typer.Option(False, "--no-whisper", help="Skip Whisper fallback"),
    retries: int = typer.Option(3, "--retries", "-r", help="Max retries per tier"),
):
    """Get transcript for a YouTube video using three-tier fallback.

    Fallback chain:
    1. Direct youtube-transcript-api (no proxy)
    2. With IPRoyal proxy rotation (if configured)
    3. Download audio via yt-dlp → OpenAI Whisper (if OPENAI_API_KEY set)

    Examples:
        python youtube_transcript.py get -i dQw4w9WgXcQ
        python youtube_transcript.py get -u "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        python youtube_transcript.py get -i VIDEO_ID --no-whisper
    """
    t0 = time.time()

    # Resolve video ID
    vid = _extract_video_id(video_id or url)
    if not vid:
        out = {
            "meta": {"video_id": None, "language": lang, "took_ms": 0, "method": None},
            "transcript": [],
            "full_text": "",
            "errors": ["Could not extract video ID from URL or --video-id"],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        raise typer.Exit(code=1)

    # Initialize monitor if requested
    monitor = None
    if Monitor and (no_proxy or not no_whisper): # Only monitor if potentially hitting heavy tiers
        state_file = Path.home() / ".pi" / "youtube-transcripts" / f"state_{vid}.json"
        monitor = Monitor(
            name=f"yt-{vid}",
            total=1,
            desc=f"Transcribing YouTube: {vid}",
            state_file=str(state_file)
        )
        # Register task
        try:
            subprocess.run([
                "python3", str(SKILLS_DIR / "task-monitor" / "monitor.py"),
                "register",
                "--name", f"yt-{vid}",
                "--state", str(state_file),
                "--total", "1",
                "--desc", f"YouTube Transcript: {vid}"
            ], capture_output=True, check=False)
        except Exception:
            pass

    out = _get_transcript_logic(vid, lang, no_proxy, no_whisper, retries, monitor=monitor)

    print(json.dumps(out, ensure_ascii=False, indent=2))

    if errors:
        raise typer.Exit(code=1)


@app.command("list-languages")
def list_languages(
    url: str = typer.Option("", "--url", "-u", help="YouTube video URL"),
    video_id: str = typer.Option("", "--video-id", "-i", help="YouTube video ID"),
    no_proxy: bool = typer.Option(False, "--no-proxy", help="Disable proxy rotation"),
    retries: int = typer.Option(3, "--retries", "-r", help="Max retries with IP rotation"),
):
    """List available transcript languages for a video.

    Examples:
        python youtube_transcript.py list-languages -i dQw4w9WgXcQ
    """
    t0 = time.time()
    errors: list[str] = []
    languages: list[dict] = []
    proxy_used = False
    retries_used = 0

    vid = _extract_video_id(video_id or url)
    if not vid:
        out = {
            "meta": {"video_id": None, "took_ms": 0, "proxy_used": False},
            "languages": [],
            "errors": ["Could not extract video ID"],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        raise typer.Exit(code=1)

    use_proxy = not no_proxy and _load_proxy_settings() is not None

    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        from youtube_transcript_api._errors import TranscriptsDisabled, VideoUnavailable

        for attempt in range(retries + 1):
            try:
                proxy_config = _load_proxy_settings() if use_proxy else None

                if proxy_config:
                    proxy_used = True
                    if attempt > 0:
                        typer.echo(f"Retry {attempt}/{retries} (IPRoyal auto-rotates IP)...", err=True)
                    http_client = _create_proxied_http_client(proxy_config)
                    api = YouTubeTranscriptApi(http_client=http_client)
                else:
                    api = YouTubeTranscriptApi()

                transcript_list = api.list(vid)

                for t in transcript_list:
                    languages.append(
                        {
                            "language": t.language,
                            "language_code": t.language_code,
                            "is_generated": t.is_generated,
                            "is_translatable": t.is_translatable,
                        }
                    )
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
                if _is_retriable_error(error_msg) and attempt < retries and use_proxy:
                    time.sleep(1)
                    continue
                break

    except ImportError:
        errors = ["youtube-transcript-api not installed"]

    took_ms = int((time.time() - t0) * 1000)
    out = {
        "meta": {"video_id": vid, "took_ms": took_ms, "proxy_used": proxy_used, "retries_used": retries_used},
        "languages": languages,
        "errors": errors,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))


@app.command()
def check_proxy(
    test_rotation: bool = typer.Option(False, "--test-rotation", help="Test IP rotation (uses 2 requests)"),
):
    """Check if IPRoyal proxy is configured correctly.

    Example:
        python youtube_transcript.py check-proxy
        python youtube_transcript.py check-proxy --test-rotation
    """
    proxy_config = _load_proxy_settings()

    if not proxy_config:
        result = {
            "configured": False,
            "error": "Missing environment variables. Need: IPROYAL_HOST, IPROYAL_PORT, IPROYAL_USER, IPROYAL_PASSWORD",
            "env_vars": {
                "IPROYAL_HOST": os.getenv("IPROYAL_HOST", ""),
                "IPROYAL_PORT": os.getenv("IPROYAL_PORT", ""),
                "IPROYAL_USER": os.getenv("IPROYAL_USER", ""),
                "IPROYAL_PASSWORD": "(set)" if os.getenv("IPROYAL_PASSWORD") else "(not set)",
            },
        }
    else:
        # Test the proxy by making a simple request
        try:
            session = _create_proxied_http_client(proxy_config)
            resp = session.get("https://api.ipify.org?format=json", timeout=15)
            ip_info = resp.json()
            first_ip = ip_info.get("ip", "unknown")

            result = {
                "configured": True,
                "proxy_host": proxy_config["host"],
                "proxy_port": proxy_config["port"],
                "test_ip": first_ip,
                "status": "working",
            }

            # Test IP rotation if requested (IPRoyal auto-rotates between requests)
            if test_rotation:
                session2 = _create_proxied_http_client(proxy_config)
                resp2 = session2.get("https://api.ipify.org?format=json", timeout=15)
                second_ip = resp2.json().get("ip", "unknown")

                result["rotation_test"] = {
                    "first_ip": first_ip,
                    "second_ip": second_ip,
                    "ip_rotated": first_ip != second_ip,
                    "note": "IPRoyal auto-rotates IPs between requests",
                }

        except Exception as e:
            result = {
                "configured": True,
                "proxy_host": proxy_config["host"],
                "proxy_port": proxy_config["port"],
                "error": str(e),
                "status": "error",
            }

    print(json.dumps(result, indent=2))


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query"),
    max_results: int = typer.Option(5, "--max", "-n", help="Max results"),
    interactive: bool = typer.Option(True, "--interactive/--no-interactive", help="Enable interactive selection"),
):
    """Search for YouTube videos.
    
    Example:
        python youtube_transcript.py search "python tutorial"
    """
    results = _search_videos(query, max_results=max_results)
    
    if not interactive or not sys.stdin.isatty():
        print(json.dumps(results, indent=2))
        return

    # Interactive Mode
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.prompt import Prompt
        from rich import print as rprint
    except ImportError:
        print(json.dumps(results, indent=2))
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
        duration = str(r.get("duration", "?"))
        # Simple duration format if it's seconds
        try:
             d = int(r.get("duration", 0) or 0)
             m, s = divmod(d, 60)
             h, m = divmod(m, 60)
             if h: duration = f"{h}:{m:02d}:{s:02d}"
             else: duration = f"{m}:{s:02d}"
        except (ValueError, TypeError):
            pass
        
        desc = r.get("description", "") or ""
        # Collapse whitespace
        desc = " ".join(desc.split())
        if len(desc) > 80:
            desc = desc[:77] + "..."
        
        table.add_row(
            str(idx),
            r.get("title", "Unknown")[:50],
            r.get("uploader", "Unknown")[:20],
            duration,
            str(r.get("view_count", "?")),
            desc
        )

    console.print(table)
    
    selection = Prompt.ask("Select videos to transcribe (e.g. 1,3 or 'all' or 'q')", default="q")
    if selection.lower() == 'q':
        return

    indices = []
    if selection.lower() == 'all':
        indices = range(len(results))
    else:
        try:
            parts = [p.strip() for p in selection.split(",")]
            indices = [int(p)-1 for p in parts if p.isdigit()]
        except (ValueError, AttributeError):
            rprint("[red]Invalid selection[/red]")
            return

    for idx in indices:
        if 0 <= idx < len(results):
            vid = results[idx].get("id")
            title = results[idx].get("title", vid)
            rprint(f"\n[bold green]Processing:[/bold green] {title} ({vid})")
            
            # Use logic function directly
            result = _get_transcript_logic(
                vid=vid, lang="en", no_proxy=False, no_whisper=False, retries=3
            )
            
            # Brief report
            if result.get("transcript"):
                 rprint(f"  [cyan]Success[/cyan]: {len(result['full_text'])} chars extracted via {result['meta'].get('method')}")
                 # Save to file
                 fname = f"{vid}_transcript.json"
                 with open(fname, 'w') as f:
                     json.dump(result, f, indent=2)
                 rprint(f"  Saved to: [underline]{fname}[/underline]")
            else:
                 rprint(f"  [red]Failed[/red]: {result.get('errors')}")



def _is_rate_limit_error(error_msg: str) -> bool:
    """Check if error indicates rate limiting."""
    rate_limit_indicators = [
        "429", "Too Many Requests", "rate limit", "blocking requests",
        "IP has been blocked", "cloud provider", "quota exceeded"
    ]
    return any(ind.lower() in error_msg.lower() for ind in rate_limit_indicators)


def _fetch_single_transcript_with_backoff(
    vid: str,
    lang: str,
    use_proxy: bool,
    base_delay: int,
    max_delay: int,
) -> tuple[list[dict], str, str | None, str | None]:
    """Fetch a single transcript with tenacity-style exponential backoff.

    Returns: (transcript, full_text, method, error)
    """
    import random

    transcript: list[dict] = []
    full_text = ""
    method = None
    last_error = None

    # Exponential backoff settings
    max_attempts = 5
    multiplier = 2

    for attempt in range(max_attempts):
        # Calculate backoff delay with jitter
        if attempt > 0:
            backoff = min(base_delay * (multiplier ** (attempt - 1)), max_delay)
            jitter = random.uniform(0.8, 1.2)  # +/- 20% jitter
            wait_time = int(backoff * jitter)
            typer.echo(f"    Backoff: waiting {wait_time}s (attempt {attempt + 1}/{max_attempts})...", err=True)
            time.sleep(wait_time)

        # Try with proxy first for batch operations (IPRoyal rotates IPs)
        if use_proxy and _load_proxy_settings() is not None:
            try:
                transcript, full_text, errors, _, _ = _fetch_transcript_with_retry(
                    vid, lang, use_proxy=True, max_retries=2
                )
                if not errors:
                    return transcript, full_text, "proxy", None
                last_error = errors[0] if errors else "Unknown proxy error"

                # If rate limited, continue to backoff
                if _is_rate_limit_error(last_error):
                    typer.echo(f"    Rate limited via proxy, backing off...", err=True)
                    continue
            except Exception as e:
                last_error = str(e)

        # Fallback to direct (might work if proxy is the issue)
        try:
            transcript, full_text, errors, _, _ = _fetch_transcript_with_retry(
                vid, lang, use_proxy=False, max_retries=0
            )
            if not errors:
                return transcript, full_text, "direct", None
            last_error = errors[0] if errors else "Unknown direct error"

            # If rate limited, continue to backoff
            if _is_rate_limit_error(last_error):
                typer.echo(f"    Rate limited (direct), backing off...", err=True)
                continue
            else:
                # Non-rate-limit error (e.g., no captions), don't retry
                break
        except Exception as e:
            last_error = str(e)
            if not _is_rate_limit_error(str(e)):
                break

    return [], "", None, last_error


@app.command()
def batch(
    input_file: str = typer.Option(..., "--input", "-f", help="File with video IDs (one per line)"),
    output_dir: str = typer.Option("./transcripts", "--output", "-o", help="Output directory for transcripts"),
    delay_min: int = typer.Option(300, "--delay-min", help="Min delay between requests (default: 300 = 5 min)"),
    delay_max: int = typer.Option(600, "--delay-max", help="Max delay between requests (default: 600 = 10 min)"),
    lang: str = typer.Option("en", "--lang", "-l", help="Language code"),
    no_proxy: bool = typer.Option(False, "--no-proxy", help="Skip proxy (NOT recommended for bulk)"),
    no_whisper: bool = typer.Option(True, "--no-whisper/--whisper", help="Skip Whisper fallback (default: skip)"),
    resume: bool = typer.Option(True, "--resume/--no-resume", help="Resume from last position (default: True)"),
    max_videos: int = typer.Option(0, "--max", "-n", help="Max videos to process (0 = all)"),
    backoff_base: int = typer.Option(60, "--backoff-base", help="Base backoff delay in seconds (default: 60)"),
    backoff_max: int = typer.Option(900, "--backoff-max", help="Max backoff delay in seconds (default: 900 = 15 min)"),
):
    """Batch process YouTube videos with IPRoyal proxy and exponential backoff.

    Uses IPRoyal proxy by default with exponential backoff on rate limits.
    Delays between 5-10 minutes (configurable) with jitter to avoid detection.
    Supports resume - safe to interrupt and restart.

    Examples:
        python youtube_transcript.py batch -f videos.txt -o ./transcripts
        python youtube_transcript.py batch -f videos.txt --max 10  # Test with 10
        python youtube_transcript.py batch -f videos.txt --delay-min 600 --delay-max 900
    """
    import random
    from pathlib import Path

    input_path = Path(input_file)
    output_path = Path(output_dir)
    state_file = output_path / ".batch_state.json"

    if not input_path.exists():
        typer.echo(f"Error: Input file not found: {input_file}", err=True)
        raise typer.Exit(code=1)

    # Check proxy configuration
    use_proxy = not no_proxy
    if use_proxy and _load_proxy_settings() is None:
        typer.echo("WARNING: IPRoyal proxy not configured. Bulk downloads may fail.", err=True)
        typer.echo("Set: IPROYAL_HOST, IPROYAL_PORT, IPROYAL_USER, IPROYAL_PASSWORD", err=True)
        typer.echo("Continuing without proxy (use --no-proxy to suppress this warning)...\n", err=True)
        use_proxy = False

    # Read video IDs
    with open(input_path) as f:
        video_ids = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    if not video_ids:
        typer.echo("Error: No video IDs found in input file", err=True)
        raise typer.Exit(code=1)

    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)

    # Load state for resume
    completed: set[str] = set()
    consecutive_failures = 0
    if resume and state_file.exists():
        try:
            with open(state_file) as f:
                state = json.load(f)
                completed = set(state.get("completed", []))
                consecutive_failures = state.get("consecutive_failures", 0)
            typer.echo(f"Resuming: {len(completed)} already completed", err=True)
        except Exception:
            pass

    # Filter out completed
    pending = [vid for vid in video_ids if vid not in completed]
    if max_videos > 0:
        pending = pending[:max_videos]

    total = len(pending)
    proxy_status = "IPRoyal proxy" if use_proxy else "direct (no proxy)"
    typer.echo(f"Processing {total} videos via {proxy_status}", err=True)
    typer.echo(f"Delay: {delay_min}-{delay_max}s | Backoff: {backoff_base}-{backoff_max}s", err=True)

    stats = {"success": 0, "failed": 0, "skipped": 0, "rate_limited": 0, "whisper": 0}

    def save_state(current_vid: str = "", current_method: str = ""):
        """Save batch state to file."""
        with open(state_file, 'w') as f:
            json.dump({
                "completed": list(completed),
                "stats": stats,
                "consecutive_failures": consecutive_failures,
                "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                "current_video": current_vid,
                "current_method": current_method,
            }, f, indent=2)

    for idx, vid in enumerate(pending, 1):
        typer.echo(f"\n[{idx}/{total}] Processing: {vid}", err=True)

        # Update state with current video
        save_state(vid, "fetching")

        out_file = output_path / f"{vid}.json"
        if out_file.exists() and resume:
            typer.echo(f"  Skipping (already exists): {out_file}", err=True)
            completed.add(vid)
            stats["skipped"] += 1
            continue

        t0 = time.time()

        # Fetch with exponential backoff
        transcript, full_text, method, error = _fetch_single_transcript_with_backoff(
            vid, lang, use_proxy, backoff_base, backoff_max
        )

        # Try Whisper fallback if enabled and other methods failed
        # Prefer local Whisper (free) over API (costs money)
        if not method and not no_whisper:
            typer.echo(f"  Trying local Whisper fallback...", err=True)
            save_state(vid, "whisper")
            with tempfile.TemporaryDirectory() as tmpdir:
                audio_path, dl_err = _download_audio_ytdlp(vid, Path(tmpdir))
                if not dl_err and audio_path:
                    # Try local Whisper first (free)
                    transcript, full_text, whisper_err = _transcribe_whisper_local(audio_path, lang)
                    if not whisper_err and transcript:
                        method = "whisper-local"
                        error = None
                    # Fallback to API if local fails and API key is set
                    elif os.getenv("OPENAI_API_KEY"):
                        typer.echo(f"    Local failed, trying Whisper API...", err=True)
                        transcript, full_text, whisper_err = _transcribe_whisper(audio_path, lang)
                        if not whisper_err and transcript:
                            method = "whisper-api"
                            error = None

        took_ms = int((time.time() - t0) * 1000)

        # Fetch metadata
        metadata = _fetch_video_metadata(vid)

        result = {
            "meta": {
                "video_id": vid,
                "language": lang,
                "took_ms": took_ms,
                "method": method,
                **metadata,
            },
            "transcript": transcript,
            "full_text": full_text,
            "errors": [error] if error else [],
        }

        # Save result
        with open(out_file, 'w') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        if method:
            typer.echo(f"  Success ({method}, {took_ms}ms): {out_file.name}", err=True)
            stats["success"] += 1
            if "whisper" in method:
                stats["whisper"] += 1
            consecutive_failures = 0
        else:
            if error and _is_rate_limit_error(error):
                typer.echo(f"  Rate limited: {error[:80]}...", err=True)
                stats["rate_limited"] += 1
                consecutive_failures += 1
            else:
                typer.echo(f"  Failed: {error[:80] if error else 'Unknown'}...", err=True)
                stats["failed"] += 1
                consecutive_failures = 0  # Reset on non-rate-limit failure

        completed.add(vid)

        # Save state after each video (clear current)
        save_state("", "")

        # Check for too many consecutive rate limits
        if consecutive_failures >= 5:
            typer.echo(f"\n  WARNING: {consecutive_failures} consecutive rate limits!", err=True)
            typer.echo(f"  Taking extended break (15 min)...", err=True)
            time.sleep(900)
            consecutive_failures = 0

        # Delay before next (except for last)
        if idx < total:
            # Smart delay based on method used:
            # - Direct fetch success: minimal delay (2-5s) - low risk with rotating IPs
            # - Proxy fetch success: short delay (5-15s)
            # - Whisper/failed: full configured delay
            if method == "direct":
                actual_delay = random.randint(2, 5)
            elif method == "proxy":
                actual_delay = random.randint(5, 15)
            else:
                # Whisper, failed, or rate-limited: use configured delay
                delay = random.randint(delay_min, delay_max)
                jitter = random.uniform(0.9, 1.1)
                actual_delay = int(delay * jitter)
            typer.echo(f"  Waiting {actual_delay}s before next...", err=True)
            time.sleep(actual_delay)

    # Final summary
    typer.echo(f"\n{'='*50}", err=True)
    typer.echo(f"=== Batch Complete ===", err=True)
    typer.echo(f"Success:      {stats['success']}", err=True)
    typer.echo(f"Failed:       {stats['failed']}", err=True)
    typer.echo(f"Rate Limited: {stats['rate_limited']}", err=True)
    typer.echo(f"Skipped:      {stats['skipped']}", err=True)
    typer.echo(f"Output:       {output_path}", err=True)

    print(json.dumps({"stats": stats, "output_dir": str(output_path)}, indent=2))


if __name__ == "__main__":
    app()
