"""Configuration constants and paths for youtube-transcripts skill.

This module centralizes all configuration, environment variables,
and path definitions used across the youtube-transcripts skill.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, TypedDict
from loguru import logger

# ============================================================================
# Path Configuration
# ============================================================================

# Skills directory (parent of youtube-transcripts)
SKILLS_DIR = Path(__file__).resolve().parents[1]

# Ensure skills dir is in path for imports
if str(SKILLS_DIR) not in sys.path:
    sys.path.append(str(SKILLS_DIR))

# ============================================================================
# Environment Loading
# ============================================================================

def _load_env() -> None:
    """Load environment variables from .env files.

    Loads skill-local .env first, then walks upward via find_dotenv
    to find the project root .env. Neither overrides already-set vars.
    """
    try:
        from dotenv import load_dotenv, find_dotenv  # type: ignore
    except ImportError:
        logger.debug(".env loading skipped — python-dotenv not installed")
        return

    # 1. Skill-local .env
    skill_env = SKILLS_DIR / ".env"
    if skill_env.exists():
        load_dotenv(skill_env, override=False)

    # 2. Walk upward to find project root .env
    root_env = find_dotenv(filename=".env", usecwd=False)
    if root_env:
        load_dotenv(root_env, override=False)

# Load env on module import
_load_env()

# ============================================================================
# Proxy Configuration (Webshare — native youtube-transcript-api support)
# ============================================================================

WEBSHARE_API_KEY_ENV = "WEBSHARE_API_KEY"
WEBSHARE_CONFIG_URL = "https://proxy.webshare.io/api/v2/proxy/config/"

# Cache fetched credentials for the process lifetime
_webshare_cache: Optional[dict] = None


def load_proxy_settings() -> Optional[dict]:
    """Load Webshare proxy credentials via API key.

    Uses WEBSHARE_API_KEY to fetch username/password from the Webshare API.
    Credentials are cached for the process lifetime.

    Returns dict with username/password, or None if not configured.
    """
    global _webshare_cache
    if _webshare_cache is not None:
        return _webshare_cache

    api_key = os.getenv(WEBSHARE_API_KEY_ENV, "").strip().strip('"')
    if not api_key:
        return None

    try:
        import httpx
        resp = httpx.get(
            WEBSHARE_CONFIG_URL,
            headers={"Authorization": f"Token {api_key}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        username = data.get("username", "").strip()
        password = data.get("password", "").strip()
        if not username or not password:
            logger.warning("Webshare API returned empty credentials")
            return None
        # Webshare rotating proxies require the "-1" sub-user suffix
        _webshare_cache = {"username": f"{username}-1", "password": password}
        return _webshare_cache
    except Exception as e:
        logger.warning("Failed to fetch Webshare proxy config: {}", e)
        return None


# ============================================================================
# API Configuration
# ============================================================================

# OpenAI/Whisper
OPENAI_API_KEY_ENV = "OPENAI_API_KEY"

def get_openai_api_key() -> Optional[str]:
    """Get OpenAI API key from environment."""
    key = os.getenv(OPENAI_API_KEY_ENV, "").strip()
    return key if key else None


# ============================================================================
# Whisper Model Configuration
# ============================================================================

# Available model sizes (from fastest/smallest to slowest/largest)
WHISPER_MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"]
WHISPER_DEFAULT_MODEL = "base"

# Compute configurations for faster-whisper
WHISPER_GPU_DEVICE = "cuda"
WHISPER_GPU_COMPUTE_TYPE = "float16"
WHISPER_CPU_DEVICE = "cpu"
WHISPER_CPU_COMPUTE_TYPE = "int8"

# Transcription settings
WHISPER_BEAM_SIZE = 5
WHISPER_VAD_FILTER = True  # Filter out silence for speed


# ============================================================================
# Batch Processing Configuration
# ============================================================================

# Default delays (seconds)
BATCH_DELAY_MIN = 300  # 5 minutes
BATCH_DELAY_MAX = 600  # 10 minutes

# Backoff settings
BACKOFF_BASE = 5  # 5 seconds
BACKOFF_MAX = 60  # 1 minute
BACKOFF_MULTIPLIER = 2
BACKOFF_JITTER_MIN = 0.8
BACKOFF_JITTER_MAX = 1.2
BACKOFF_MAX_ATTEMPTS = 5

# Consecutive failure threshold for extended break
CONSECUTIVE_FAILURE_THRESHOLD = 5
EXTENDED_BREAK_DURATION = 900  # 15 minutes

# Smart delay based on method (seconds)
SMART_DELAY_DIRECT = (2, 5)
SMART_DELAY_PROXY = (5, 15)


# ============================================================================
# Rate Limiting Detection
# ============================================================================

# Patterns that indicate retriable errors (rate limits, blocks, etc.)
RETRIABLE_ERROR_PATTERNS = [
    "429", "Too Many Requests",
    "403", "Forbidden",
    "blocked", "captcha",
    "rate limit", "quota",
]

# Patterns that indicate rate limiting specifically
RATE_LIMIT_PATTERNS = [
    "429", "Too Many Requests", "rate limit", "blocking requests",
    "IP has been blocked", "cloud provider", "quota exceeded"
]


# ============================================================================
# Audio Download Configuration
# ============================================================================

# yt-dlp audio extraction settings
YTDLP_AUDIO_FORMAT = "bestaudio/best"
YTDLP_AUDIO_CODEC = "mp3"
YTDLP_AUDIO_QUALITY = "192"

# Audio file extensions to look for after download
AUDIO_EXTENSIONS = ["mp3", "m4a", "webm", "opus"]


# ============================================================================
# Video ID Extraction Patterns
# ============================================================================

# YouTube video ID format: 11 alphanumeric chars + - _
VIDEO_ID_PATTERN = r"^[\w-]{11}$"

# URL patterns for video ID extraction
URL_PATTERNS = [
    r"[?&]v=([\w-]{11})",       # Standard watch URL
    r"youtu\.be/([\w-]{11})",   # Short URL
    r"embed/([\w-]{11})",       # Embed URL
]
