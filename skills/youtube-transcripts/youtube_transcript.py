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

    transcript: list[dict] = []
    full_text = ""
    errors: list[str] = []
    method = None
    all_errors: list[str] = []

    # TIER 1: Direct (no proxy)
    typer.echo("Tier 1: Trying direct youtube-transcript-api...", err=True)
    try:
        transcript, full_text, errors, _, _ = _fetch_transcript_with_retry(
            vid, lang, use_proxy=False, max_retries=0
        )
        if not errors:
            method = "direct"
    except ImportError as e:
        errors = [str(e)]

    if errors:
        all_errors.append(f"Tier 1 (direct): {errors[0]}")

    # TIER 2: With proxy (if available and tier 1 failed)
    if errors and not no_proxy and _load_proxy_settings() is not None:
        typer.echo(f"Tier 2: Trying with IPRoyal proxy (retries: {retries})...", err=True)
        try:
            transcript, full_text, errors, _, _ = _fetch_transcript_with_retry(
                vid, lang, use_proxy=True, max_retries=retries
            )
            if not errors:
                method = "proxy"
        except Exception as e:
            errors = [str(e)]

        if errors:
            all_errors.append(f"Tier 2 (proxy): {errors[0]}")

    # TIER 3: Whisper fallback (if tiers 1-2 failed)
    if errors and not no_whisper and os.getenv("OPENAI_API_KEY"):
        typer.echo("Tier 3: Trying yt-dlp + Whisper fallback...", err=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)

            # Download audio
            typer.echo("  Downloading audio with yt-dlp...", err=True)
            audio_path, dl_error = _download_audio_ytdlp(vid, tmppath)

            if dl_error:
                all_errors.append(f"Tier 3 (whisper): Download failed - {dl_error}")
            elif audio_path:
                # Transcribe with Whisper
                typer.echo("  Transcribing with OpenAI Whisper...", err=True)
                transcript, full_text, whisper_error = _transcribe_whisper(audio_path, lang)

                if whisper_error:
                    all_errors.append(f"Tier 3 (whisper): {whisper_error}")
                    errors = [whisper_error]
                else:
                    errors = []
                    method = "whisper"

    took_ms = int((time.time() - t0) * 1000)

    # Build output
    out = {
        "meta": {
            "video_id": vid,
            "language": lang,
            "took_ms": took_ms,
            "method": method,
        },
        "transcript": transcript,
        "full_text": full_text,
        "errors": all_errors if errors else [],
    }
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


if __name__ == "__main__":
    app()
