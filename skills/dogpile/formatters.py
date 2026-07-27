#!/usr/bin/env python3
"""Formatters for Dogpile report sections.

Contains format functions for smaller providers:
- Wayback Machine
- Codex Knowledge
- Perplexity
- Readarr
- Discord
"""
from typing import Dict, Any, List


def format_wayback_section(wayback_res: Dict[str, Any]) -> List[str]:
    """Format Wayback Machine results."""
    lines = []
    if wayback_res.get("skipped"):
        lines.append(f"> **Wayback Machine**: Skipped: {wayback_res['skipped']}")
        if wayback_res.get("hint"):
            lines.append(f"> Hint: {wayback_res['hint']}")
        lines.append("")
    elif wayback_res.get("available"):
        lines.append(f"> **Wayback Machine**: [Snapshot available]({wayback_res['url']}) (Timestamp: {wayback_res.get('timestamp')})")
        lines.append("")
    elif "error" in wayback_res:
        lines.append(f"> Wayback Error: {wayback_res['error']}")
        lines.append("")
    return lines


def format_codex_section(codex_res: str | Dict[str, Any]) -> List[str]:
    """Format Codex technical overview.

    Args:
        codex_res: String result on success, or {"error": "..."} dict on Stage 1 failure.
    """
    lines = ["## Codex Technical Overview"]
    if isinstance(codex_res, dict):
        lines.append(f"> Error: {codex_res.get('error', codex_res)}")
    elif isinstance(codex_res, str) and not codex_res.startswith("Error:"):
        lines.append(codex_res)
    else:
        lines.append(f"> Error: {codex_res}")
    lines.append("")
    return lines


def format_perplexity_section(perp_res: Dict[str, Any]) -> List[str]:
    """Format Perplexity AI research results."""
    lines = ["## AI Research (Perplexity)"]
    if "skipped" in perp_res:
        lines.append(f"> Skipped: {perp_res['skipped']}")
        if perp_res.get("replacement"):
            lines.append(f"> Replacement: {perp_res['replacement']}")
        if perp_res.get("hint"):
            lines.append(f"> Hint: {perp_res['hint']}")
    elif "error" in perp_res:
        lines.append(f"> Error: {perp_res['error']}")
    else:
        lines.append(perp_res.get("answer", "No answer."))
        if perp_res.get("citations"):
            lines.append("\n**Citations:**")
            for cite in perp_res.get("citations", []):
                lines.append(f"- {cite}")
    lines.append("")
    return lines


def format_readarr_section(readarr_res: List[Dict[str, Any]] | Dict[str, Any]) -> List[str]:
    """Format Readarr search results."""
    lines = ["## Books & Usenet (Readarr)"]
    if isinstance(readarr_res, dict) and readarr_res.get("skipped"):
        lines.append(f"> Skipped: {readarr_res['skipped']}")
        if readarr_res.get("hint"):
            lines.append(f"> Hint: {readarr_res['hint']}")
    elif readarr_res and isinstance(readarr_res, list) and len(readarr_res) > 0:
        if "error" in readarr_res[0]:
            lines.append(f"> Error: {readarr_res[0]['error']}")
        else:
            for item in readarr_res[:5]:
                title = item.get("title", "Unknown")
                cat = item.get("category", "")
                size = int(item.get("size", "0")) / (1024 * 1024)
                lines.append(f"- **{title}** ({cat}) - {size:.1f} MB")
    else:
        lines.append("No books or Usenet results found.")
    lines.append("")
    return lines


def format_feeds_section(feeds_res: Dict[str, Any]) -> List[str]:
    """Format optional consume-feed monitor results."""
    lines = ["## Feed Monitors"]
    if not isinstance(feeds_res, dict):
        lines.append(f"> Error: unexpected result type {type(feeds_res).__name__}")
    elif feeds_res.get("skipped"):
        lines.append(f"> Skipped: {feeds_res['skipped']}")
        if feeds_res.get("hint"):
            lines.append(f"> Hint: {feeds_res['hint']}")
    elif feeds_res.get("error"):
        lines.append(f"> Error: {feeds_res['error']}")
        if feeds_res.get("stderr"):
            lines.append("```text")
            lines.append(str(feeds_res["stderr"])[-1000:])
            lines.append("```")
    else:
        if feeds_res.get("feed_pack"):
            lines.append(f"Feed pack: `{feeds_res['feed_pack']}`")
        if feeds_res.get("default_use"):
            lines.append(f"Default use: `{feeds_res['default_use']}`")
        if feeds_res.get("false_positive_policy"):
            lines.append(f"> False-positive policy: {feeds_res['false_positive_policy']}")
        lines.append(f"Dry-run limit per source: {feeds_res.get('limit', 'unknown')}")
        lines.append(f"Sources checked: {feeds_res.get('source_count', 0)}")
        lines.append(f"Parsed items: {feeds_res.get('parsed_total', 0)}")
        if feeds_res.get("error_total"):
            lines.append(f"Degraded sources/errors: {feeds_res.get('error_total')}")
        for item in feeds_res.get("results", [])[:12]:
            lines.append(
                f"- **{item.get('source_key')}**: {item.get('status')} "
                f"({item.get('parsed_count', 0)} parsed, {item.get('errors', 0)} errors) "
                f"{item.get('rss_url', '')}"
            )
    lines.append("")
    return lines


def format_discord_section(discord_res: Dict[str, Any]) -> List[str]:
    """Format Discord search results."""
    lines = ["## Discord (Security Servers)"]
    if discord_res.get("skipped"):
        lines.append(f"> Skipped: {discord_res.get('reason', 'Not configured')}")
    elif discord_res.get("error"):
        lines.append(f"> Error: {discord_res['error']}")
    elif discord_res.get("results"):
        messages = discord_res.get("results", [])
        guilds_searched = discord_res.get("guilds_searched", 0)
        lines.append(f"*Searched {guilds_searched} security servers*\n")

        for msg in messages[:10]:
            author = msg.get("author", {}).get("username", "Unknown")
            content = msg.get("content", "")[:200]
            guild = msg.get("guild_name", "Unknown")
            timestamp = msg.get("timestamp", "")[:10]
            msg_id = msg.get("id", "")
            channel_id = msg.get("channel_id", "")
            guild_id = msg.get("guild_id", "")
            link = f"https://discord.com/channels/{guild_id}/{channel_id}/{msg_id}"

            lines.append(f"- **[{guild}]** @{author} ({timestamp})")
            lines.append(f"  > {content}")
            lines.append(f"  [Jump to message]({link})")
            lines.append("")

        if discord_res.get("errors"):
            lines.append(f"> Some servers had errors: {', '.join(discord_res['errors'][:3])}")
    else:
        lines.append("No Discord messages found. Configure servers with `ops-discord setup`.")
    lines.append("")
    return lines
