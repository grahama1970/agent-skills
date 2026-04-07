#!/usr/bin/env python3
"""Harvest Shadow S00 training data from corpus.

Scans S00 profiles + S05 actual outcomes to create training data for
a shadow classifier that predicts table extraction needs from document features.

Shadow-LEGO pattern: S00 features (seeds) → classifier → S05 strategy hints.
The classifier is a SEED PRODUCER, never a gatekeeper.

Output: classifier-lab tabular JSONL with S00 features + S05-derived labels.

Labels:
  - needs_stream: PDF has tables found ONLY by stream mode (borderless)
  - lattice_sufficient: All tables found by lattice mode
  - no_tables: PDF has no tables despite S00 prediction

Usage:
    python harvest_shadow_s00.py --corpus /mnt/storage12tb/extractor_corpus
    python harvest_shadow_s00.py --corpus /mnt/storage12tb/extractor_corpus --output data/shadow_s00.jsonl
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path


def _find_run_dirs(roots: list[Path]) -> list[Path]:
    """Find all extraction run directories with S00 profiles.

    Scans multiple root directories. Each root contains slug-named dirs
    with pipeline stage subdirectories (00_profile_detector, 05_table_extractor, etc.).
    """
    dirs = []
    seen = set()
    for root in roots:
        if not root.exists():
            continue
        for slug_dir in root.iterdir():
            if not slug_dir.is_dir():
                continue
            # Follow symlinks
            real = slug_dir.resolve()
            if real in seen:
                continue
            seen.add(real)
            profile = slug_dir / "00_profile_detector" / "profile.json"
            if profile.exists():
                dirs.append(slug_dir)
    return dirs


def _extract_s00_features(profile: dict) -> dict:
    """Extract numeric features from S00 profile for classifier-lab tabular format."""
    elements = profile.get("elements", {})
    layout = profile.get("layout", {})
    hierarchy = profile.get("hierarchy", {})
    preset = profile.get("preset_match", {})

    # All features must be numeric for classifier-lab tabular benchmark
    features = {
        "page_count": profile.get("page_count", 0),
        "file_size_mb": profile.get("file_size_mb", 0.0),
        "complexity_score": profile.get("complexity_score", 0.0),
        "columns": layout.get("columns", 1),
        "has_structure": 1.0 if hierarchy.get("has_structure") else 0.0,
        "estimated_sections": hierarchy.get("estimated_sections", 0),
        "estimated_sections_regex": hierarchy.get("estimated_sections_regex", 0),
        "estimated_sections_font": hierarchy.get("estimated_sections_font", 0),
        "font_body_size": hierarchy.get("font_body_size", 0.0),
        "s00_tables_predicted": 1.0 if elements.get("tables") else 0.0,
        "s00_table_pages": elements.get("table_pages", 0),
        "s00_figures_predicted": 1.0 if elements.get("figures") else 0.0,
        "s00_image_pages": elements.get("image_pages", 0),
        "s00_formulas_predicted": 1.0 if elements.get("formulas") else 0.0,
        "s00_requirements_predicted": 1.0 if elements.get("requirements") else 0.0,
        "estimated_table_count": elements.get("estimated_table_count", 0),
        "is_accurate_route": 1.0 if profile.get("route") == "accurate" else 0.0,
        "preset_matched": 1.0 if preset.get("matched") else 0.0,
    }

    # Domain as numeric encoding
    domain_map = {
        "engineering": 1, "scientific": 2, "defense": 3,
        "legal": 4, "medical": 5, "financial": 6,
        "general": 7, "academic": 8,
    }
    features["domain_code"] = domain_map.get(profile.get("domain", ""), 0)

    # Section style encoding
    style_map = {"decimal": 1, "labeled": 2, "roman": 3, "alpha": 4, "none": 0}
    features["section_style_code"] = style_map.get(
        hierarchy.get("section_style", "none"), 0
    )

    # Section breakdown ratios
    breakdown = hierarchy.get("section_breakdown", {})
    total_sections = sum(breakdown.values()) or 1
    features["decimal_section_ratio"] = breakdown.get("decimal", 0) / total_sections
    features["labeled_section_ratio"] = breakdown.get("labeled", 0) / total_sections

    return features


def _analyze_s05_tables(s05_path: Path) -> dict:
    """Analyze S05 output to determine table extraction characteristics."""
    try:
        with open(s05_path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    tables = data.get("tables", [])
    if not tables:
        return {
            "actual_table_count": 0,
            "stream_table_count": 0,
            "lattice_table_count": 0,
            "has_stream_tables": False,
            "stream_only": False,
            "avg_accuracy": 0.0,
            "avg_data_density": 0.0,
        }

    stream_count = 0
    lattice_count = 0
    accuracies = []
    densities = []
    strategies_seen = set()

    for t in tables:
        strat = t.get("strategy", "")
        strategies_seen.add(strat)

        if "stream" in strat:
            stream_count += 1
        else:
            lattice_count += 1

        cm = t.get("camelot_metrics", {})
        if cm.get("accuracy") is not None:
            accuracies.append(cm["accuracy"])

        pm = t.get("pandas_metrics", {})
        if pm.get("data_density") is not None:
            densities.append(pm["data_density"])

    return {
        "actual_table_count": len(tables),
        "stream_table_count": stream_count,
        "lattice_table_count": lattice_count,
        "has_stream_tables": stream_count > 0,
        "stream_only": stream_count > 0 and lattice_count == 0,
        "avg_accuracy": sum(accuracies) / len(accuracies) if accuracies else 0.0,
        "avg_data_density": sum(densities) / len(densities) if densities else 0.0,
    }


def _determine_label(s00_features: dict, s05_analysis: dict) -> str:
    """Determine classification label from S05 actual outcomes.

    Labels represent what the shadow classifier should PREDICT about a document
    to help S05 choose the right strategy upfront.
    """
    actual = s05_analysis.get("actual_table_count", 0)
    stream = s05_analysis.get("stream_table_count", 0)
    lattice = s05_analysis.get("lattice_table_count", 0)

    if actual == 0:
        return "no_tables"
    elif stream > 0:
        return "needs_stream"
    else:
        return "lattice_sufficient"


def harvest(corpus: Path, output: Path, limit: int = 0) -> dict:
    """Harvest training data from corpus.

    Returns summary stats.
    """
    print(f"Scanning corpus: {corpus}")
    # Scan all known locations for extraction results
    roots = [
        corpus / "results",
        Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb")) / "skills/review-pdf/extracted_runs",
    ]
    run_dirs = _find_run_dirs(roots)
    print(f"Found {len(run_dirs)} extraction runs with S00 profiles")

    label_counts = Counter()
    written = 0
    skipped_no_s05 = 0
    skipped_error = 0

    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w") as out:
        for i, run_dir in enumerate(run_dirs):
            if limit and written >= limit:
                break

            profile_path = run_dir / "00_profile_detector" / "profile.json"
            # S05 tables can be at either path depending on pipeline version
            s05_path = run_dir / "05_table_extractor" / "json_output" / "05_tables.json"
            if not s05_path.exists():
                s05_path = run_dir / "05_tables" / "05_tables.json"

            # We need BOTH S00 and S05 for supervised training
            if not s05_path.exists():
                skipped_no_s05 += 1
                continue

            try:
                with open(profile_path) as f:
                    profile = json.load(f)

                s00_features = _extract_s00_features(profile)
                s05_analysis = _analyze_s05_tables(s05_path)

                if not s05_analysis:
                    skipped_error += 1
                    continue

                label = _determine_label(s00_features, s05_analysis)
                label_counts[label] += 1

                # Build classifier-lab tabular row
                row = {
                    "features": s00_features,
                    "label": label,
                    # Metadata (ignored by classifier-lab tabular, useful for debugging)
                    "source_dir": str(run_dir.name),
                    "actual_table_count": s05_analysis["actual_table_count"],
                    "stream_table_count": s05_analysis["stream_table_count"],
                    "lattice_table_count": s05_analysis["lattice_table_count"],
                    "avg_accuracy": s05_analysis["avg_accuracy"],
                }
                out.write(json.dumps(row) + "\n")
                written += 1

            except Exception as e:
                skipped_error += 1
                if skipped_error <= 5:
                    print(f"  Error processing {run_dir.name}: {e}", file=sys.stderr)

            if (i + 1) % 500 == 0:
                print(f"  Processed {i+1}/{len(run_dirs)}, written={written}")

    summary = {
        "total_runs": len(run_dirs),
        "written": written,
        "skipped_no_s05": skipped_no_s05,
        "skipped_error": skipped_error,
        "label_distribution": dict(label_counts),
        "output": str(output),
    }
    print(f"\nSummary:")
    print(f"  Written: {written}")
    print(f"  Skipped (no S05): {skipped_no_s05}")
    print(f"  Skipped (error): {skipped_error}")
    print(f"  Labels: {dict(label_counts)}")
    return summary


import typer

app = typer.Typer()


@app.command()
def main(
    corpus: Path = typer.Option(..., help=""),
    output: Path = typer.Option(
        Path(__file__).parent.parent / "data" / "shadow_s00.jsonl",
        help="",
    ),
    limit: int = typer.Option(0, help="Max samples (0=all)"),
):
    summary = harvest(corpus, output, limit)
    # Write summary JSON alongside
    summary_path = output.with_suffix(".summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nSummary written to: {summary_path}")


if __name__ == "__main__":
    app()
