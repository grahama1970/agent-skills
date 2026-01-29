"""Configuration constants and paths for youtube-transcripts skill.

This module centralizes all configuration, environment variables,
and path definitions used across the youtube-transcripts skill.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional, TypedDict

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
    """Load environment variables from .env file if available."""
    try:
        from dotenv_helper import load_env as dotenv_load  # type: ignore
        dotenv_load()
    except Exception:
        try:
            from dotenv import load_dotenv, find_dotenv  # type: ignore
            load_dotenv(find_dotenv(usecwd=True), override=False)
        except Exception:
            pass

# Load env on module import
_load_env()

# ============================================================================
# Proxy Configuration
# ============================================================================

# Typed proxy configuration
class ProxyConfig(TypedDict):
    """Proxy configuration for IPRoyal."""
    host: str
    port: str
    username: str
    password: str

# IPRoyal proxy environment variable names
PROXY_ENV_HOST = "IPROYAL_HOST"
PROXY_ENV_PORT = "IPROYAL_PORT"
PROXY_ENV_USER = "IPROYAL_USER"
PROXY_ENV_PASSWORD = "IPROYAL_PASSWORD"
PROXY_ENV_PASSWORD_ALT = "IPROYAL_PASS"  # Alternative name

# Default proxy settings
PROXY_TIMEOUT = 30  # seconds


def load_proxy_settings() -> Optional[ProxyConfig]:
    """Load IPRoyal proxy settings from environment.

    Returns dict with proxy config, or None if not configured.

    Note: IPRoyal residential proxies automatically rotate IPs between requests,
    so no session ID manipulation is needed.
    """
    host = os.getenv(PROXY_ENV_HOST, "").strip()
    port = os.getenv(PROXY_ENV_PORT, "").strip()
    user = os.getenv(PROXY_ENV_USER, "").strip()
    password = os.getenv(PROXY_ENV_PASSWORD, os.getenv(PROXY_ENV_PASSWORD_ALT, "")).strip()

    if not all([host, port, user, password]):
        return None

    return {
        "host": host,
        "port": port,
        "username": user,
        "password": password,
    }


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
BACKOFF_BASE = 60  # 1 minute
BACKOFF_MAX = 900  # 15 minutes
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
