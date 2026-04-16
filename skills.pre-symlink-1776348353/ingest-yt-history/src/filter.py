#!/usr/bin/env python3
"""
Filter YouTube watch history by date, service, or channel.
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Optional

import typer


def filter_history(
    input_path: str | Path,
    service: str | None = None,
    channel: str | None = None,
    after: str | None = None,
    before: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Filter history entries by criteria.

    Args:
        input_path: Path to parsed history JSONL file
        service: Filter by service ("YouTube" or "YouTube Music")
        channel: Filter by channel name (substring match)
        after: Only entries after this date (YYYY-MM-DD)
        before: Only entries before this date (YYYY-MM-DD)

    Yields:
        Matching entries
    """
    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"File not found: {input_path}")

    # Parse date filters
    after_dt = datetime.fromisoformat(after + "T00:00:00+00:00") if after else None
    before_dt = datetime.fromisoformat(before + "T23:59:59+00:00") if before else None

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Filter by service
            if service:
                products = entry.get("products", [])
                url = entry.get("url", "")
                if service.lower() == "youtube music":
                    if "YouTube Music" not in products and "music.youtube.com" not in url:
                        continue
                elif service.lower() == "youtube":
                    if "YouTube Music" in products or "music.youtube.com" in url:
                        continue

            # Filter by channel
            if channel:
                entry_channel = entry.get("channel", "") or entry.get("channel_title", "")
                if channel.lower() not in entry_channel.lower():
                    continue

            # Filter by date
            ts = entry.get("ts", "")
            if ts and (after_dt or before_dt):
                try:
                    entry_dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                    if after_dt and entry_dt < after_dt:
                        continue
                    if before_dt and entry_dt > before_dt:
                        continue
                except (ValueError, AttributeError):
                    continue

            yield entry


def main(
    input_path: str = typer.Argument(..., help="Path to parsed history JSONL file"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Output JSONL file path (default: stdout)"),
    service: Optional[str] = typer.Option(None, help="Filter by service"),
    channel: Optional[str] = typer.Option(None, help="Filter by channel name (substring match)"),
    after: Optional[str] = typer.Option(None, help="Only entries after this date (YYYY-MM-DD)"),
    before: Optional[str] = typer.Option(None, help="Only entries before this date (YYYY-MM-DD)"),
) -> None:
    """Filter YouTube watch history by date, service, or channel."""
    try:
        count = 0

        if output:
            with open(output, "w", encoding="utf-8") as out:
                for entry in filter_history(
                    input_path,
                    service=service,
                    channel=channel,
                    after=after,
                    before=before,
                ):
                    out.write(json.dumps(entry) + "\n")
                    count += 1
        else:
            for entry in filter_history(
                input_path,
                service=service,
                channel=channel,
                after=after,
                before=before,
            ):
                print(json.dumps(entry))
                count += 1

        print(f"Filtered {count} entries", file=sys.stderr)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    typer.run(main)
