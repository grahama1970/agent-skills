#!/usr/bin/env python3
"""Actionable error hints for Dogpile providers.

Maps error patterns to troubleshooting suggestions so users know how to fix issues
instead of just seeing "timed out" or "failed".
"""
import re
from typing import Dict, List, Optional, Tuple

# Provider → (error_pattern, hint, severity)
# Patterns are checked in order; first match wins
PROVIDER_HINTS: Dict[str, List[Tuple[str, str, str]]] = {
    "brave": [
        (r"API key not found|BRAVE_API_KEY",
         "BRAVE_API_KEY missing. Add to ~/.env or pi-mono/.env", "config"),
        (r"429|rate.?limit",
         "Rate limited. Wait 60s or check Brave API quota at brave.com/dashboard", "rate_limit"),
        (r"401|403|unauthorized",
         "Auth failed. Verify BRAVE_API_KEY is valid at brave.com/dashboard", "auth"),
        (r"timeout|timed.?out",
         "Brave API slow. Try again or check https://status.brave.com", "timeout"),
        (r"connection|network|refused",
         "Network error. Check internet connection", "network"),
    ],
    "perplexity": [
        (r"API.?key|PERPLEXITY_API_KEY",
         "PERPLEXITY_API_KEY missing. Add to ~/.env", "config"),
        (r"429|rate.?limit|quota",
         "Perplexity rate limited. This is a paid API - check your plan limits", "rate_limit"),
        (r"401|403",
         "Perplexity auth failed. Verify API key at perplexity.ai/settings", "auth"),
        (r"timeout",
         "Perplexity timeout. Sonar Reasoning can be slow - try shorter query", "timeout"),
    ],
    "github": [
        (r"gh.?CLI.?not.?installed|command.?not.?found.*gh",
         "GitHub CLI missing. Install: brew install gh && gh auth login", "dependency"),
        (r"401|not.?logged.?in|auth",
         "GitHub not authenticated. Run: gh auth login", "auth"),
        (r"403|rate.?limit|API rate",
         "GitHub rate limited. Wait or check: gh api rate_limit", "rate_limit"),
        (r"timeout",
         "GitHub slow. Large repos take longer - try more specific query", "timeout"),
        (r"no.?results|not.?found",
         "No matches. Try different keywords or check repo exists", "no_results"),
    ],
    "arxiv": [
        (r"timeout",
         "ArXiv slow (academic API). Try again in 30s", "timeout"),
        (r"429|rate.?limit",
         "ArXiv rate limited. Be patient - it's a free academic resource", "rate_limit"),
        (r"no.?results|not.?found",
         "No papers found. Try broader search terms or check arXiv categories", "no_results"),
        (r"fetcher.*not.?found",
         "Fetcher skill missing. Run: ls ~/.pi/skills/fetcher/", "dependency"),
        (r"extractor.*not.?found",
         "Extractor skill missing. Run: ls ~/.pi/skills/extractor/", "dependency"),
    ],
    "youtube": [
        (r"API.?key|YOUTUBE_API_KEY",
         "YOUTUBE_API_KEY missing. Get one at console.cloud.google.com", "config"),
        (r"quota|exceeded",
         "YouTube quota exceeded. Daily limit is 10K units - try tomorrow", "rate_limit"),
        (r"timeout",
         "YouTube slow. Transcript extraction can take 30s+", "timeout"),
        (r"no.?transcript|captions.?disabled",
         "No captions available. Video may not have transcripts", "no_results"),
    ],
    "readarr": [
        (r"connection.?refused|not.?running",
         "Readarr not running. Start with: docker compose up -d readarr", "dependency"),
        (r"401|api.?key",
         "Readarr API key invalid. Check Settings → General in Readarr UI", "auth"),
        (r"timeout",
         "Readarr/Usenet slow. Large searches take time", "timeout"),
        (r"no.?results",
         "No books found. Try author name or ISBN", "no_results"),
    ],
    "discord": [
        (r"clawdbot.?not.?found|skill.?missing",
         "Discord search skill missing. Check ~/.pi/skills/clawdbot/", "dependency"),
        (r"no.?guilds|SECURITY_GUILDS",
         "No Discord servers configured. Add guild IDs to config", "config"),
        (r"401|token",
         "Discord token invalid. Re-auth with Discord bot", "auth"),
        (r"timeout",
         "Discord search slow. Large servers take longer", "timeout"),
    ],
    "wayback": [
        (r"timeout",
         "Wayback Machine slow (archive.org). Try again later", "timeout"),
        (r"no.?snapshots|not.?archived",
         "URL not in Wayback Machine. Check archive.org manually", "no_results"),
        (r"rate.?limit",
         "archive.org rate limited. Wait 30s before retrying", "rate_limit"),
    ],
    "codex": [
        (r"quota|rate.?limit|429",
         "Codex rate limited. Check capacity at ~/.codex/ or use --no-codex", "rate_limit"),
        (r"auth|token|401",
         "Codex auth failed. Run: codex login", "auth"),
        (r"timeout",
         "Codex slow. High-reasoning queries take 30-60s", "timeout"),
    ],
}

# Generic hints for error types when no provider-specific hint matches
GENERIC_HINTS: Dict[str, str] = {
    "rate_limit": "Rate limited. Wait 30-60s before retrying",
    "timeout": "Request timed out. Try again or use a more specific query",
    "auth": "Authentication failed. Check API keys in ~/.env",
    "config": "Missing configuration. Check ~/.env for required keys",
    "network": "Network error. Check internet connection",
    "dependency": "Missing dependency. Check skill installation",
    "no_results": "No results found. Try different search terms",
}


def get_error_hint(provider: str, error_message: str) -> Optional[Dict[str, str]]:
    """Get actionable hint for a provider error.

    Args:
        provider: Provider name (brave, github, arxiv, etc.)
        error_message: The error message to analyze

    Returns:
        Dict with 'hint' and 'category' if match found, else None
    """
    if not error_message:
        return None

    error_lower = error_message.lower()

    # Check provider-specific hints first
    hints = PROVIDER_HINTS.get(provider.lower(), [])
    for pattern, hint, category in hints:
        if re.search(pattern, error_lower, re.IGNORECASE):
            return {"hint": hint, "category": category}

    # Fall back to generic hints based on common patterns
    for category, generic_hint in GENERIC_HINTS.items():
        patterns = {
            "rate_limit": r"429|rate.?limit|quota|throttl",
            "timeout": r"timeout|timed.?out",
            "auth": r"401|403|auth|unauthorized|forbidden",
            "config": r"key.?not.?found|missing.?key|not.?set",
            "network": r"connection|network|refused|unreachable",
            "dependency": r"not.?found|not.?installed|missing",
            "no_results": r"no.?results|not.?found|empty",
        }
        if category in patterns and re.search(patterns[category], error_lower, re.IGNORECASE):
            return {"hint": generic_hint, "category": category}

    return None


def format_error_with_hint(provider: str, error_message: str) -> str:
    """Format error message with actionable hint for display.

    Args:
        provider: Provider name
        error_message: Raw error message

    Returns:
        Formatted string with error and hint
    """
    hint_info = get_error_hint(provider, error_message)

    # Truncate long error messages
    short_error = error_message[:100] + "..." if len(error_message) > 100 else error_message

    if hint_info:
        return f"{short_error}\n    → {hint_info['hint']}"

    return short_error


def summarize_errors_with_hints(errors: List[Dict]) -> str:
    """Generate a summary of errors with actionable hints.

    Args:
        errors: List of error dicts with 'provider' and 'message' keys

    Returns:
        Formatted summary string
    """
    if not errors:
        return ""

    lines = ["--- Errors (with troubleshooting hints) ---"]

    # Group by category
    by_category: Dict[str, List[Tuple[str, str, str]]] = {}

    for err in errors:
        provider = err.get("provider", "unknown")
        message = err.get("message", str(err))
        hint_info = get_error_hint(provider, message)
        category = hint_info["category"] if hint_info else "other"

        if category not in by_category:
            by_category[category] = []
        by_category[category].append((
            provider,
            message[:80],
            hint_info["hint"] if hint_info else "Check logs for details"
        ))

    # Priority order for display
    priority = ["config", "auth", "dependency", "rate_limit", "timeout", "network", "no_results", "other"]

    for category in priority:
        if category not in by_category:
            continue

        category_label = {
            "config": "Configuration Issues",
            "auth": "Authentication Issues",
            "dependency": "Missing Dependencies",
            "rate_limit": "Rate Limits",
            "timeout": "Timeouts",
            "network": "Network Issues",
            "no_results": "No Results",
            "other": "Other Errors",
        }.get(category, category.title())

        lines.append(f"\n[{category_label}]")
        for provider, msg, hint in by_category[category]:
            lines.append(f"  {provider}: {msg}")
            lines.append(f"    → {hint}")

    return "\n".join(lines)
