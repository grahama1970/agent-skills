#!/usr/bin/env python3
"""
Statistics for YouTube watch history.

Shows breakdown by service (YouTube vs YouTube Music), by channel, by date, etc.
"""
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


def load_history(path: str | Path) -> list[dict[str, Any]]:
    """Load history entries from JSONL file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def compute_stats(entries: list[dict[str, Any]], by_service: bool = False) -> dict[str, Any]:
    """Compute statistics for history entries.

    Args:
        entries: List of parsed history entries
        by_service: If True, include service breakdown

    Returns:
        Dict with statistics
    """
    stats: dict[str, Any] = {
        "total_entries": len(entries),
    }

    if not entries:
        return stats

    # Service breakdown (YouTube vs YouTube Music)
    service_counts: Counter[str] = Counter()
    channel_counts: Counter[str] = Counter()
    day_counts: Counter[str] = Counter()
    hour_counts: Counter[int] = Counter()

    timestamps = []

    for entry in entries:
        # Count by service/product
        products = entry.get("products", [])
        for product in products:
            service_counts[product] += 1
        if not products:
            # Infer from URL
            url = entry.get("url", "")
            if "music.youtube.com" in url:
                service_counts["YouTube Music"] += 1
            else:
                service_counts["YouTube"] += 1

        # Count by channel
        channel = entry.get("channel") or entry.get("channel_title", "Unknown")
        if channel:
            channel_counts[channel] += 1

        # Count by timestamp
        ts = entry.get("ts", "")
        if ts:
            timestamps.append(ts)
            try:
                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                day_counts[dt.strftime("%A")] += 1
                hour_counts[dt.hour] += 1
            except (ValueError, AttributeError):
                pass

    # Add service breakdown
    if by_service or service_counts:
        stats["by_service"] = dict(service_counts.most_common())

    # Add top channels
    stats["top_channels"] = dict(channel_counts.most_common(10))

    # Add day distribution
    if day_counts:
        stats["by_day"] = dict(day_counts.most_common())

    # Add hour distribution (sorted by hour)
    if hour_counts:
        stats["by_hour"] = {str(h): hour_counts[h] for h in sorted(hour_counts.keys())}

    # Add date range
    if timestamps:
        sorted_ts = sorted(timestamps)
        try:
            start_dt = datetime.fromisoformat(sorted_ts[0].replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(sorted_ts[-1].replace("Z", "+00:00"))
            stats["date_range"] = {
                "start": start_dt.strftime("%Y-%m-%d"),
                "end": end_dt.strftime("%Y-%m-%d"),
            }
        except (ValueError, IndexError):
            pass

    return stats


def format_stats(stats: dict[str, Any]) -> str:
    """Format statistics for human-readable output."""
    lines = []

    lines.append(f"Total entries: {stats.get('total_entries', 0)}")

    # Date range
    date_range = stats.get("date_range", {})
    if date_range:
        lines.append(f"Date range: {date_range.get('start')} to {date_range.get('end')}")

    # Service breakdown
    by_service = stats.get("by_service", {})
    if by_service:
        lines.append("\nBy service:")
        for service, count in by_service.items():
            pct = (count / stats["total_entries"]) * 100
            lines.append(f"  {service}: {count} ({pct:.1f}%)")

    # Top channels
    top_channels = stats.get("top_channels", {})
    if top_channels:
        lines.append("\nTop channels:")
        for channel, count in list(top_channels.items())[:10]:
            lines.append(f"  {channel}: {count}")

    # Day distribution
    by_day = stats.get("by_day", {})
    if by_day:
        lines.append("\nBy day of week:")
        for day, count in by_day.items():
            lines.append(f"  {day}: {count}")

    return "\n".join(lines)


def main() -> None:
    """CLI entry point for stats command."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Show statistics for YouTube watch history"
    )
    parser.add_argument(
        "input_path",
        help="Path to parsed history JSONL file",
    )
    parser.add_argument(
        "--by-service",
        action="store_true",
        help="Show breakdown by service (YouTube vs YouTube Music)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of human-readable format",
    )

    args = parser.parse_args()

    try:
        entries = load_history(args.input_path)
        stats = compute_stats(entries, by_service=args.by_service)

        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print(format_stats(stats))

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
