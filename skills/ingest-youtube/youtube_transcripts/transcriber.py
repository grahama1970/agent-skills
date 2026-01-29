"""Transcription functionality for youtube-transcripts skill.

This module handles:
- YouTube transcript API fetching (with proxy support)
- OpenAI Whisper API transcription
- Local faster-whisper transcription
- Retry logic with exponential backoff
"""
from __future__ import annotations

import os
import time
import random
import tempfile
from pathlib import Path
from typing import Optional, Any

import typer

from youtube_transcripts.config import (
    load_proxy_settings,
    get_openai_api_key,
    WHISPER_DEFAULT_MODEL,
    WHISPER_GPU_DEVICE,
    WHISPER_GPU_COMPUTE_TYPE,
    WHISPER_CPU_DEVICE,
    WHISPER_CPU_COMPUTE_TYPE,
    WHISPER_BEAM_SIZE,
    WHISPER_VAD_FILTER,
    BACKOFF_MULTIPLIER,
    BACKOFF_JITTER_MIN,
    BACKOFF_JITTER_MAX,
    BACKOFF_MAX_ATTEMPTS,
)
from youtube_transcripts.utils import (
    is_retriable_error,
    is_rate_limit_error,
    create_proxied_http_client,
)
from youtube_transcripts.downloader import download_audio


# Cache for local Whisper model (avoid reloading)
_LOCAL_WHISPER_MODEL = None


def fetch_transcript_with_retry(
    vid: str,
    lang: str,
    use_proxy: bool,
    max_retries: int = 3,
) -> tuple[list[dict], str, list[str], bool, int]:
    """Fetch transcript with retry and IP rotation on failure.

    Args:
        vid: YouTube video ID
        lang: Language code (e.g., 'en')
        use_proxy: Whether to use proxy for requests
        max_retries: Maximum number of retry attempts

    Returns:
        Tuple of (transcript, full_text, errors, proxy_used, retries_used)
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
            proxy_config = load_proxy_settings() if use_proxy else None

            if proxy_config:
                proxy_used = True
                if attempt > 0:
                    typer.echo(f"Retry {attempt}/{max_retries} (IPRoyal auto-rotates IP)...", err=True)
                http_client = create_proxied_http_client(proxy_config)
                api = YouTubeTranscriptApi(http_client=http_client)
            else:
                api = YouTubeTranscriptApi()

            fetched = api.fetch(vid, languages=[lang])

            # Success - convert to list of dicts
            transcript = [
                {
                    "text": seg.get("text", ""),
                    "start": seg.get("start", 0.0),
                    "duration": seg.get("duration", 0.0),
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
            if is_retriable_error(error_msg) and attempt < max_retries and use_proxy:
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


def transcribe_whisper_api(audio_path: Path, lang: str) -> tuple[list[dict], str, Optional[str]]:
    """Transcribe audio using OpenAI Whisper API.

    Args:
        audio_path: Path to audio file
        lang: Language code (e.g., 'en')

    Returns:
        Tuple of (transcript_segments, full_text, error_message)
    """
    api_key = get_openai_api_key()
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


def transcribe_whisper_local(
    audio_path: Path,
    lang: str,
    model_size: str = WHISPER_DEFAULT_MODEL
) -> tuple[list[dict], str, Optional[str]]:
    """Transcribe audio using faster-whisper (CTranslate2 optimized, 4-8x faster).

    Model sizes: tiny, base, small, medium, large-v3
    - tiny: fastest, lowest quality
    - base: good balance (default)
    - small: better quality
    - medium: high quality
    - large-v3: best quality

    Args:
        audio_path: Path to audio file
        lang: Language code (e.g., 'en')
        model_size: Whisper model size to use

    Returns:
        Tuple of (transcript_segments, full_text, error_message)
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
                _LOCAL_WHISPER_MODEL = WhisperModel(
                    model_size,
                    device=WHISPER_GPU_DEVICE,
                    compute_type=WHISPER_GPU_COMPUTE_TYPE
                )
                typer.echo(f"    Using GPU (CUDA) with {WHISPER_GPU_COMPUTE_TYPE}", err=True)
            except Exception:
                _LOCAL_WHISPER_MODEL = WhisperModel(
                    model_size,
                    device=WHISPER_CPU_DEVICE,
                    compute_type=WHISPER_CPU_COMPUTE_TYPE
                )
                typer.echo(f"    Using CPU with {WHISPER_CPU_COMPUTE_TYPE}", err=True)

        # Transcribe - faster-whisper returns a generator
        segments_gen, info = _LOCAL_WHISPER_MODEL.transcribe(
            str(audio_path),
            language=lang if lang != "en" else None,
            beam_size=WHISPER_BEAM_SIZE,
            vad_filter=WHISPER_VAD_FILTER,
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


def fetch_single_transcript_with_backoff(
    vid: str,
    lang: str,
    use_proxy: bool,
    base_delay: int,
    max_delay: int,
) -> tuple[list[dict], str, Optional[str], Optional[str]]:
    """Fetch a single transcript with tenacity-style exponential backoff.

    Args:
        vid: YouTube video ID
        lang: Language code
        use_proxy: Whether to use proxy
        base_delay: Base backoff delay in seconds
        max_delay: Maximum backoff delay in seconds

    Returns:
        Tuple of (transcript, full_text, method, error)
    """
    transcript: list[dict] = []
    full_text = ""
    method = None
    last_error = None

    for attempt in range(BACKOFF_MAX_ATTEMPTS):
        # Calculate backoff delay with jitter
        if attempt > 0:
            backoff = min(base_delay * (BACKOFF_MULTIPLIER ** (attempt - 1)), max_delay)
            jitter = random.uniform(BACKOFF_JITTER_MIN, BACKOFF_JITTER_MAX)
            wait_time = int(backoff * jitter)
            typer.echo(f"    Backoff: waiting {wait_time}s (attempt {attempt + 1}/{BACKOFF_MAX_ATTEMPTS})...", err=True)
            time.sleep(wait_time)

        # Try with proxy first for batch operations (IPRoyal rotates IPs)
        if use_proxy and load_proxy_settings() is not None:
            try:
                transcript, full_text, errors, _, _ = fetch_transcript_with_retry(
                    vid, lang, use_proxy=True, max_retries=2
                )
                if not errors:
                    return transcript, full_text, "proxy", None
                last_error = errors[0] if errors else "Unknown proxy error"

                # If rate limited, continue to backoff
                if is_rate_limit_error(last_error):
                    typer.echo(f"    Rate limited via proxy, backing off...", err=True)
                    continue
            except Exception as e:
                last_error = str(e)

        # Fallback to direct (might work if proxy is the issue)
        try:
            transcript, full_text, errors, _, _ = fetch_transcript_with_retry(
                vid, lang, use_proxy=False, max_retries=0
            )
            if not errors:
                return transcript, full_text, "direct", None
            last_error = errors[0] if errors else "Unknown direct error"

            # If rate limited, continue to backoff
            if is_rate_limit_error(last_error):
                typer.echo(f"    Rate limited (direct), backing off...", err=True)
                continue
            else:
                # Non-rate-limit error (e.g., no captions), don't retry
                break
        except Exception as e:
            last_error = str(e)
            if not is_rate_limit_error(str(e)):
                break

    return [], "", None, last_error


def transcribe_with_whisper_fallback(
    vid: str,
    lang: str,
    use_local: bool = True,
) -> tuple[list[dict], str, Optional[str], Optional[str]]:
    """Download audio and transcribe with Whisper (local first, then API).

    Args:
        vid: YouTube video ID
        lang: Language code
        use_local: Whether to try local Whisper first (default: True)

    Returns:
        Tuple of (transcript, full_text, method, error)
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)

        # Download audio
        typer.echo("  Downloading audio with yt-dlp...", err=True)
        audio_path, dl_error = download_audio(vid, tmppath)

        if dl_error:
            return [], "", None, f"Download failed - {dl_error}"

        if not audio_path:
            return [], "", None, "Audio file not found after download"

        # Try local Whisper first (free)
        if use_local:
            typer.echo("  Transcribing with local Whisper...", err=True)
            transcript, full_text, whisper_error = transcribe_whisper_local(audio_path, lang)

            if not whisper_error and transcript:
                return transcript, full_text, "whisper-local", None

            # Fallback to API if local fails
            if get_openai_api_key():
                typer.echo("  Local failed, trying Whisper API...", err=True)
                transcript, full_text, whisper_error = transcribe_whisper_api(audio_path, lang)
                if not whisper_error and transcript:
                    return transcript, full_text, "whisper-api", None
                return [], "", None, whisper_error

            return [], "", None, whisper_error or "Local Whisper failed, no API key for fallback"

        # API only
        if get_openai_api_key():
            typer.echo("  Transcribing with Whisper API...", err=True)
            transcript, full_text, whisper_error = transcribe_whisper_api(audio_path, lang)
            if not whisper_error and transcript:
                return transcript, full_text, "whisper-api", None
            return [], "", None, whisper_error

        return [], "", None, "No Whisper transcription method available"
