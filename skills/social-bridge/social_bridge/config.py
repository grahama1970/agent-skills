"""
Social Bridge Configuration Module

Contains all constants, paths, and default configuration values.
"""

import os
from pathlib import Path
from typing import Any

# =============================================================================
# ENVIRONMENT CONFIGURATION
# =============================================================================

# Resilience settings (configurable via environment)
MAX_RETRIES = int(os.environ.get("SOCIAL_BRIDGE_MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.environ.get("SOCIAL_BRIDGE_RETRY_DELAY", "0.5"))
RATE_LIMIT_RPS = int(os.environ.get("SOCIAL_BRIDGE_RATE_LIMIT_RPS", "3"))

# Fields to redact in logs
REDACT_FIELDS = {"token", "api_key", "api_hash", "password", "secret", "authorization"}

# =============================================================================
# PATHS
# =============================================================================

DATA_DIR = Path(os.environ.get("SOCIAL_BRIDGE_DIR", Path.home() / ".social-bridge"))
CONFIG_FILE = DATA_DIR / "config.json"
CACHE_DIR = DATA_DIR / "cache"
TELEGRAM_SESSION = DATA_DIR / "telegram"

# Memory integration - uses graph-memory project
MEMORY_ROOT = Path(os.environ.get("MEMORY_ROOT", Path.home() / "workspace/experiments/memory"))
MEMORY_SCOPE = "social_intel"

# =============================================================================
# SECURITY KEYWORD PATTERNS FOR AUTO-TAGGING
# =============================================================================

SECURITY_KEYWORDS = [
    (r"CVE-\d{4}-\d+", "cve"),
    (r"APT\d+", "apt"),
    (r"DARPA|IARPA|BAA", "darpa"),
    (r"0-?day|zero.?day", "0day"),
    (r"exploit|RCE|LPE|privesc", "exploit"),
    (r"malware|ransomware|trojan|backdoor", "malware"),
    (r"HTB|Hack.?The.?Box|TryHackMe|CTF", "ctf"),
    (r"MITRE|ATT&CK|T\d{4}", "mitre"),
    (r"cobalt.?strike|C2|beacon", "c2"),
    (r"IOC|indicator", "ioc"),
]

# =============================================================================
# DEFAULT SOURCES
# =============================================================================

# Pre-configured security sources for Telegram
DEFAULT_TELEGRAM_CHANNELS = [
    {"name": "vaborivs", "focus": "vulnerability research"},
    {"name": "exploitin", "focus": "exploit announcements"},
    {"name": "TheHackersNews", "focus": "security news"},
    {"name": "cikitech", "focus": "malware/threats"},
    {"name": "CISAgov", "focus": "CISA alerts"},
]

# Pre-configured security sources for X/Twitter
DEFAULT_X_ACCOUNTS = [
    {"name": "malwaretechblog", "focus": "malware analysis"},
    {"name": "SwiftOnSecurity", "focus": "security insights"},
    {"name": "0xdea", "focus": "vulnerability research"},
    {"name": "thegrugq", "focus": "opsec, threat intel"},
    {"name": "GossiTheDog", "focus": "threat intel"},
]

# =============================================================================
# DISCORD EMBED COLORS
# =============================================================================

PLATFORM_COLORS = {
    "telegram": 0x0088CC,  # Telegram blue
    "x": 0x1DA1F2,         # Twitter blue
    "default": 0x5865F2,   # Discord blurple
}


def ensure_directories() -> None:
    """Ensure all required directories exist."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / "telegram").mkdir(exist_ok=True)
    (CACHE_DIR / "x").mkdir(exist_ok=True)
