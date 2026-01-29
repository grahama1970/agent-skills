"""Common utilities for youtube-transcripts skill.

This module provides shared utility functions used across multiple modules
in the youtube-transcripts skill.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote

from youtube_transcripts.config import (
    VIDEO_ID_PATTERN,
    URL_PATTERNS,
    RETRIABLE_ERROR_PATTERNS,
    RATE_LIMIT_PATTERNS,
    ProxyConfig,
)


def extract_video_id(url_or_id: str) -> Optional[str]:
    """Extract video ID from URL or return as-is if already an ID.

    Supports:
    - Direct video IDs (11 alphanumeric chars + - _)
    - Standard watch URLs: youtube.com/watch?v=VIDEO_ID
    - Short URLs: youtu.be/VIDEO_ID
    - Embed URLs: youtube.com/embed/VIDEO_ID

    Args:
        url_or_id: YouTube video URL or video ID

    Returns:
        Video ID string, or None if extraction failed
    """
    s = (url_or_id or "").strip()

    # Already a video ID (11 chars, alphanumeric + - _)
    if re.match(VIDEO_ID_PATTERN, s):
        return s

    # Try each URL pattern
    for pattern in URL_PATTERNS:
        m = re.search(pattern, s)
        if m:
            return m.group(1)

    return None


def is_retriable_error(error_msg: str) -> bool:
    """Check if error is retriable with IP rotation.

    Args:
        error_msg: Error message to check

    Returns:
        True if the error indicates a retriable condition (rate limit, block, etc.)
    """
    lower_msg = error_msg.lower()
    return any(p.lower() in lower_msg for p in RETRIABLE_ERROR_PATTERNS)


def is_rate_limit_error(error_msg: str) -> bool:
    """Check if error indicates rate limiting.

    Args:
        error_msg: Error message to check

    Returns:
        True if the error specifically indicates rate limiting
    """
    return any(ind.lower() in error_msg.lower() for ind in RATE_LIMIT_PATTERNS)


def create_proxied_http_client(proxy_config: ProxyConfig) -> "requests.Session":
    """Create a requests-based HTTP client with proxy support.

    The youtube-transcript-api uses requests internally, so we create
    a custom session with proxy configuration.

    Args:
        proxy_config: Dictionary with host, port, username, password

    Returns:
        requests.Session configured with proxy
    """
    import requests

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

    return session


def format_duration(seconds: Optional[int]) -> str:
    """Format duration in seconds to human-readable string.

    Args:
        seconds: Duration in seconds (can be None or 0)

    Returns:
        Formatted string like "1:23:45" or "12:34"
    """
    if not seconds:
        return "?"
    try:
        d = int(seconds)
        m, s = divmod(d, 60)
        h, m = divmod(m, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"
    except (ValueError, TypeError):
        return "?"


def truncate_text(text: str, max_length: int = 80, suffix: str = "...") -> str:
    """Truncate text to maximum length with suffix.

    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add if truncated

    Returns:
        Truncated text with suffix if needed
    """
    if not text:
        return ""
    # Collapse whitespace
    text = " ".join(text.split())
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix


def validate_video_ids(video_ids: list[str]) -> tuple[list[str], list[str]]:
    """Validate a list of video IDs.

    Args:
        video_ids: List of potential video IDs or URLs

    Returns:
        Tuple of (valid_ids, invalid_entries)
    """
    valid = []
    invalid = []
    for entry in video_ids:
        vid = extract_video_id(entry)
        if vid:
            valid.append(vid)
        else:
            invalid.append(entry)
    return valid, invalid
