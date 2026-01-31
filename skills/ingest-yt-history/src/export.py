#!/usr/bin/env python3
"""
Export YouTube watch history in various formats.

Supports: memory (for /memory skill), csv, json
"""
import csv
import json
import sys
from pathlib import Path
from typing import Any, Iterator, TextIO

from .sync_memory import format_memory_entry, TaxonomyConfig


def export_to_memory(
    input_path: str | Path,
    output: TextIO,
    config: TaxonomyConfig | None = None,
) -> int:
    """Export history to memory-compatible JSONL format.

    This is essentially a wrapper around sync_memory.

    Args:
        input_path: Path to parsed history JSONL file
        output: Output file-like object
        config: Optional TaxonomyConfig

    Returns:
        Number of entries exported
    """
    if config is None:
        config = TaxonomyConfig()

    input_path = Path(input_path)
    count = 0

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            memory_entry = format_memory_entry(entry, config)
            output.write(json.dumps(memory_entry) + "\n")
            count += 1

    return count


def export_to_csv(
    input_path: str | Path,
    output: TextIO,
) -> int:
    """Export history to CSV format.

    Args:
        input_path: Path to parsed history JSONL file
        output: Output file-like object

    Returns:
        Number of entries exported
    """
    input_path = Path(input_path)

    # Define CSV columns
    fieldnames = [
        "video_id", "title", "artist", "channel", "ts", "url",
        "products", "tags", "duration_seconds", "category_name"
    ]

    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    count = 0
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Flatten lists for CSV
            row = dict(entry)
            if "products" in row and isinstance(row["products"], list):
                row["products"] = ", ".join(row["products"])
            if "tags" in row and isinstance(row["tags"], list):
                row["tags"] = ", ".join(row["tags"])

            writer.writerow(row)
            count += 1

    return count


def export_to_json(
    input_path: str | Path,
    output: TextIO,
) -> int:
    """Export history to JSON array format.

    Args:
        input_path: Path to parsed history JSONL file
        output: Output file-like object

    Returns:
        Number of entries exported
    """
    input_path = Path(input_path)

    entries = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue

    json.dump(entries, output, indent=2)
    output.write("\n")
    return len(entries)


def main() -> None:
    """CLI entry point for export command."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Export YouTube watch history in various formats"
    )
    parser.add_argument(
        "input_path",
        help="Path to parsed history JSONL file",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (default: stdout)",
    )
    parser.add_argument(
        "-f", "--format",
        choices=["memory", "csv", "json"],
        default="memory",
        help="Output format (default: memory)",
    )

    args = parser.parse_args()

    try:
        if args.output:
            with open(args.output, "w", encoding="utf-8") as out:
                if args.format == "memory":
                    count = export_to_memory(args.input_path, out)
                elif args.format == "csv":
                    count = export_to_csv(args.input_path, out)
                elif args.format == "json":
                    count = export_to_json(args.input_path, out)
        else:
            if args.format == "memory":
                count = export_to_memory(args.input_path, sys.stdout)
            elif args.format == "csv":
                count = export_to_csv(args.input_path, sys.stdout)
            elif args.format == "json":
                count = export_to_json(args.input_path, sys.stdout)

        print(f"Exported {count} entries", file=sys.stderr)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
