#!/usr/bin/env python3
"""
Discord Operations - Configuration Module

Constants, paths, and default settings for the discord-ops skill.
"""

import logging
import os
from pathlib import Path

__all__ = [
    "logger",
    "CLAWDBOT_DIR",
    "SKILL_DIR",
    "CONFIG_FILE",
    "KEYWORDS_FILE",
    "MATCHES_LOG",
    "MEMORY_ROOT",
    "MEMORY_SCOPE",
    "MAX_RETRIES",
    "RETRY_BASE_DELAY",
    "RATE_LIMIT_RPS",
    "REDACT_FIELDS",
    "DEFAULT_KEYWORDS",
    "KEYWORD_TAG_MAP",
]


# Configure logging - don't log tokens or sensitive data
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("discord-ops")


# =============================================================================
# PATHS
# =============================================================================

CLAWDBOT_DIR = Path(os.environ.get("CLAWDBOT_DIR", "/home/graham/workspace/experiments/clawdbot"))
# SKILL_DIR is the parent of the discord_ops package (the skill root)
SKILL_DIR = Path(__file__).parent.parent
CONFIG_FILE = SKILL_DIR / "config.json"
KEYWORDS_FILE = SKILL_DIR / "keywords.json"
MATCHES_LOG = SKILL_DIR / "matches.jsonl"

# Memory integration paths
MEMORY_ROOT = Path(os.environ.get("MEMORY_ROOT", Path.home() / "workspace/experiments/memory"))
MEMORY_SCOPE = "social_intel"


# =============================================================================
# RESILIENCE SETTINGS (configurable via environment)
# =============================================================================

MAX_RETRIES = int(os.environ.get("DISCORD_OPS_MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.environ.get("DISCORD_OPS_RETRY_DELAY", "0.5"))
RATE_LIMIT_RPS = int(os.environ.get("DISCORD_OPS_RATE_LIMIT_RPS", "5"))


# =============================================================================
# SECURITY SETTINGS
# =============================================================================

# Fields to redact in logs
REDACT_FIELDS = {"token", "api_key", "password", "secret", "authorization", "bot_token"}


# =============================================================================
# DEFAULT SECURITY KEYWORDS
# =============================================================================

DEFAULT_KEYWORDS = [
    # Vulnerabilities
    r"CVE-\d{4}-\d+",
    r"0-?day",
    r"zero.?day",
    r"exploit",
    r"vuln(erability)?",
    r"RCE",
    r"LPE",
    r"privesc",
    # Programs & Funding
    r"DARPA",
    r"IARPA",
    r"BAA",
    r"grants?\.gov",
    # Platforms
    r"HTB",
    r"Hack.?The.?Box",
    r"TryHackMe",
    r"CTF",
    # Threat Intel
    r"APT\d+",
    r"malware",
    r"ransomware",
    r"C2",
    r"cobalt.?strike",
    # Techniques
    r"MITRE",
    r"ATT&CK",
    r"T\d{4}",  # MITRE technique IDs
]


# =============================================================================
# KEYWORD TO TAG MAPPING
# =============================================================================

KEYWORD_TAG_MAP = {
    r"CVE-\d{4}-\d+": "cve",
    r"APT\d+": "apt",
    r"DARPA|IARPA|BAA": "darpa",
    r"0-?day|zero.?day": "0day",
    r"exploit|RCE|LPE|privesc": "exploit",
    r"malware|ransomware": "malware",
    r"HTB|Hack.?The.?Box|TryHackMe|CTF": "ctf",
    r"MITRE|ATT&CK|T\d{4}": "mitre",
    r"cobalt.?strike|C2": "c2",
}
