#!/usr/bin/env python3
"""
Discord Operations - Keyword Matching Module

Keyword pattern matching and tag extraction for security content.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from discord_ops.config import KEYWORD_TAG_MAP

__all__ = [
    "KeywordMatch",
    "match_keywords",
    "extract_tags_from_keywords",
    "create_match_tags",
]


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class KeywordMatch:
    """A message that matched watched keywords."""
    timestamp: str
    guild_id: str
    guild_name: str
    channel_id: str
    channel_name: str
    author: str
    content: str
    matched_keywords: list[str]
    message_url: str

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp,
            "guild_id": self.guild_id,
            "guild_name": self.guild_name,
            "channel_id": self.channel_id,
            "channel_name": self.channel_name,
            "author": self.author,
            "content": self.content,
            "matched_keywords": self.matched_keywords,
            "message_url": self.message_url,
        }

    def to_webhook_payload(self) -> dict[str, Any]:
        """Format for paper-writer/dogpile webhook."""
        return {
            "source": "discord",
            "content": self.content[:2000],
            "author": self.author,
            "channel": f"{self.guild_name}/#{self.channel_name}",
            "url": self.message_url,
            "keywords": self.matched_keywords,
            "timestamp": self.timestamp,
        }

    def to_discord_embed(self) -> dict[str, Any]:
        """Format for Discord webhook forwarding."""
        return {
            "title": f"Keyword Match: {', '.join(self.matched_keywords[:3])}",
            "description": self.content[:2000],
            "url": self.message_url,
            "color": 0x5865F2,  # Discord blurple
            "author": {"name": self.author},
            "footer": {"text": f"{self.guild_name} #{self.channel_name}"},
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KeywordMatch":
        """Create from dictionary."""
        return cls(
            timestamp=data.get("timestamp", ""),
            guild_id=data.get("guild_id", ""),
            guild_name=data.get("guild_name", ""),
            channel_id=data.get("channel_id", ""),
            channel_name=data.get("channel_name", ""),
            author=data.get("author", ""),
            content=data.get("content", ""),
            matched_keywords=data.get("matched_keywords", []),
            message_url=data.get("message_url", ""),
        )

    @classmethod
    def create_test_match(cls) -> "KeywordMatch":
        """Create a test match for webhook testing."""
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            guild_id="test",
            guild_name="Test Server",
            channel_id="test",
            channel_name="test-channel",
            author="discord-ops",
            content="Test message: CVE-2024-0001 exploit detected!",
            matched_keywords=["CVE-2024-0001", "exploit"],
            message_url="https://discord.com/channels/test/test/test",
        )


# =============================================================================
# MATCHING FUNCTIONS
# =============================================================================

def match_keywords(text: str, patterns: list[str]) -> list[str]:
    """Find all keyword patterns that match in text.

    Args:
        text: The text to search
        patterns: List of regex patterns (or literal strings)

    Returns:
        List of patterns that matched
    """
    matches = []
    for pattern in patterns:
        try:
            if re.search(pattern, text, re.IGNORECASE):
                matches.append(pattern)
        except re.error:
            # Invalid regex, try literal match
            if pattern.lower() in text.lower():
                matches.append(pattern)
    return matches


def extract_tags_from_keywords(matched_keywords: list[str], content: str) -> list[str]:
    """Extract semantic tags from matched keywords and content.

    Uses KEYWORD_TAG_MAP to map regex patterns to semantic tags.

    Args:
        matched_keywords: Keywords that matched (for reference)
        content: Original content to scan for tags

    Returns:
        List of extracted semantic tags
    """
    tags = set()
    for pattern, tag in KEYWORD_TAG_MAP.items():
        if re.search(pattern, content, re.IGNORECASE):
            tags.add(tag)
    return list(tags)


def create_match_tags(match: KeywordMatch) -> list[str]:
    """Create full tag list for a match.

    Combines auto-extracted tags with metadata tags.

    Args:
        match: The keyword match

    Returns:
        Complete list of tags for storage
    """
    auto_tags = extract_tags_from_keywords(match.matched_keywords, match.content)
    metadata_tags = [
        "discord",
        f"channel:{match.channel_name}",
        f"guild:{match.guild_name}",
    ]
    return list(set(auto_tags + metadata_tags))
