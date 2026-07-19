"""Centralized configuration for watch skill.

All environment variables are loaded once here so scripts don't scatter
os.getenv calls with different defaults.
"""
from __future__ import annotations

import os
from pathlib import Path

# Whisper
WHISPER_API_URL: str = os.getenv("WHISPER_API_URL", "http://127.0.0.1:9000/v1/audio/transcriptions")
WHISPER_API_KEY: str = os.getenv("WHISPER_API_KEY", "")

# Memory daemon
MEMORY_DAEMON_URL: str = os.getenv("MEMORY_DAEMON_URL", "http://127.0.0.1:8601")

# Visual descriptions
WATCH_VISUAL_DESCRIPTION_MODEL: str = os.getenv("WATCH_VISUAL_DESCRIPTION_MODEL", "vlm-chutes")
WATCH_VISUAL_DESCRIPTION_FALLBACK_MODELS: str = os.getenv("WATCH_VISUAL_DESCRIPTION_FALLBACK_MODELS", "")
# NOTE: watch model inference routes through Tau (only /tau may reach /scillm); the
# former WATCH_SCILLM_API_BASE / WATCH_SCILLM_PROXY_KEY direct-proxy settings were
# removed when qra.py migrated to the Tau adapters.

# Persistent media storage
_WATCH_MEDIA_ROOT = os.getenv("WATCH_MEDIA_ROOT", "")
if _WATCH_MEDIA_ROOT:
    WATCH_MEDIA_ROOT = Path(_WATCH_MEDIA_ROOT)
else:
    WATCH_MEDIA_ROOT = Path.home() / ".local" / "share" / "agent-skills" / "watch-frames"

# Default report path (for the UI)
WATCH_REPORT_PATH: str = os.getenv("WATCH_REPORT_PATH", "")

# Movie library
MOVIE_LIBRARY: Path | None = None
_movie_lib = os.getenv("MOVIE_LIBRARY_PATH", "")
if _movie_lib:
    MOVIE_LIBRARY = Path(_movie_lib)
