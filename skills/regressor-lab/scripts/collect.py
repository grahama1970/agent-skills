#!/usr/bin/env python3
"""Collect extraction timing data from profile.json files into training JSONL."""

import json
import sys
from pathlib import Path

import typer

app = typer.Typer()

PROFILE_SOURCES = [
    Path("/mnt/storage12tb/extractor_corpus/results"),
    Path("/home/graham/workspace/experiments/extractor/.skills/review-pdf/extracted_runs"),
]


def extract_features(profile: dict) -> dict | None:
    """Extract regressor features from a profile.json."""
    duration = profile.get("duration_ms")
    if duration is None or duration <= 0:
        return None

    elements = profile.get("elements", {})
    hierarchy = profile.get("hierarchy", {})
    layout = profile.get("layout", {})
    toc = profile.get("toc", {})

    file_path = profile.get("file", "")
    ext = Path(file_path).suffix.lower() if file_path else ".pdf"

    return {
        # Target
        "duration_ms": duration,
        # Document metadata
        "format": ext,
        "page_count": profile.get("page_count", 0),
        "file_size_mb": profile.get("file_size_mb", 0.0),
        "domain": profile.get("domain", "unknown"),
        "route": profile.get("route", "unknown"),
        "complexity_score": profile.get("complexity_score", 0),
        "detected_preset": profile.get("detected_preset", "unknown"),
        # Layout
        "columns": layout.get("columns", 1),
        # Structure
        "estimated_sections": hierarchy.get("estimated_sections", 0),
        "has_structure": hierarchy.get("has_structure", False),
        "section_style": hierarchy.get("section_style", "unknown"),
        "font_body_size": hierarchy.get("font_body_size", 0.0),
        # Content elements
        "has_tables": elements.get("tables", False),
        "table_pages": elements.get("table_pages", 0),
        "has_figures": elements.get("figures", False),
        "image_pages": elements.get("image_pages", 0),
        "has_formulas": elements.get("formulas", False),
        "has_requirements": elements.get("requirements", False),
        "max_tables_per_page": elements.get("max_tables_per_page", 0),
        # TOC
        "has_toc": toc.get("has_toc", False),
        "toc_entry_count": toc.get("entry_count", 0),
        # Timeout context
        "estimated_timeout_seconds": profile.get("estimated_timeout_seconds", 0),
    }


@app.command()
def collect(
    source: str = typer.Option("profiles", help="Data source: profiles"),
    out: Path = typer.Option("data/timeout_training.jsonl", help="Output JSONL path"),
    limit: int = typer.Option(0, help="Max records (0=all)"),
):
    """Collect extraction profiles into training JSONL."""
    out.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    skipped = 0

    with open(out, "w") as fh:
        for source_dir in PROFILE_SOURCES:
            if not source_dir.is_dir():
                print(f"SKIP source not found: {source_dir}", file=sys.stderr)
                continue

            for profile_path in source_dir.rglob("00_profile_detector/profile.json"):
                try:
                    with open(profile_path) as f:
                        profile = json.load(f)
                except (json.JSONDecodeError, OSError):
                    skipped += 1
                    continue

                features = extract_features(profile)
                if features is None:
                    skipped += 1
                    continue

                fh.write(json.dumps(features) + "\n")
                count += 1

                if limit and count >= limit:
                    break

            if limit and count >= limit:
                break

    print(f"Collected {count} records, skipped {skipped}")
    print(f"Output: {out}")


if __name__ == "__main__":
    app()
