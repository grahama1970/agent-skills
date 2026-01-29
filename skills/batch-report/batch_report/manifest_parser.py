"""Manifest file parsing for batch-report skill.

This module handles finding and parsing manifest files from batch output
directories, including extractor manifests, timing files, and final reports.
"""
from __future__ import annotations

from pathlib import Path
from typing import TypedDict, Any

from batch_report.utils import load_json


class ManifestCounts(TypedDict):
    blocks02: int
    sections04: int
    tables05: int


class ManifestDoc(TypedDict):
    counts: ManifestCounts
    timings_ms: dict[str, int]


class FinalReportMetrics(TypedDict):
    total_sections: int
    total_tables: int
    requirements_extracted: int


class FinalReportDoc(TypedDict):
    verification: dict[str, Any]
    statistics: dict[str, dict[str, FinalReportMetrics]]
    content_summary: dict[str, Any]


def find_manifests(output_dir: Path) -> list[Path]:
    """Find all manifest.json files in output directory.

    Args:
        output_dir: Path to the batch output directory.

    Returns:
        List of paths to manifest.json files.
    """
    return list(output_dir.glob("*/manifest.json"))


def find_timings(output_dir: Path) -> list[Path]:
    """Find all timings_summary.json files.

    Args:
        output_dir: Path to the batch output directory.

    Returns:
        List of paths to timings_summary.json files.
    """
    return list(output_dir.glob("*/timings_summary.json"))


def find_final_reports(output_dir: Path) -> list[Path]:
    """Find all final_report.json files.

    Args:
        output_dir: Path to the batch output directory.

    Returns:
        List of paths to final_report.json files.
    """
    return list(output_dir.glob("*/14_report_generator/json_output/final_report.json"))


def analyze_manifests(manifests: list[Path]) -> dict:
    """Analyze manifest files for success/failure patterns.

    Args:
        manifests: List of paths to manifest.json files.

    Returns:
        Analysis dict with total, successful, partial, failed counts
        and item details.
    """
    results = {
        "total": len(manifests),
        "successful": 0,
        "partial": 0,
        "failed": 0,
        "items": [],
        "empty_content": [],
        "zero_metrics": [],
    }

    for manifest_path in manifests:
        manifest = load_json(manifest_path)
        item_id = manifest_path.parent.name

        if "_error" in manifest:
            results["failed"] += 1
            results["items"].append(
                {"id": item_id, "status": "error", "error": manifest["_error"]}
            )
            continue

        counts = manifest.get("counts", {})
        timings = manifest.get("timings_ms", {})

        # Check for empty/zero metrics
        total_blocks = counts.get("blocks02", 0)
        total_sections = counts.get("sections04", 0)

        if total_blocks == 0 and total_sections == 0:
            results["zero_metrics"].append(item_id)
            results["partial"] += 1
            results["items"].append(
                {"id": item_id, "status": "partial", "reason": "zero_metrics"}
            )
        else:
            results["successful"] += 1
            results["items"].append(
                {
                    "id": item_id,
                    "status": "success",
                    "blocks": total_blocks,
                    "sections": total_sections,
                    "tables": counts.get("tables05", 0),
                    "total_time_ms": sum(timings.values()) if timings else 0,
                }
            )

    return results


def analyze_quality(final_reports: list[Path], sample_limit: int = 20) -> dict:
    """Analyze quality metrics from final reports.

    Args:
        final_reports: List of paths to final_report.json files.

    Returns:
        Quality analysis dict with pass/fail counts and samples.
    """
    quality = {
        "total_checked": len(final_reports),
        "pass": 0,
        "fail": 0,
        "empty_toc": 0,
        "no_sections": 0,
        "samples": [],
    }

    for report_path in final_reports[:sample_limit]:  # Sample up to sample_limit
        report = load_json(report_path)
        if "_error" in report:
            continue

        item_id = report_path.parent.parent.parent.name
        verification = report.get("verification", {})
        stats = report.get("statistics", {}).get("metrics", {})

        status = verification.get("status", "UNKNOWN")
        if status == "PASS":
            quality["pass"] += 1
        else:
            quality["fail"] += 1

        # Check for empty content
        if stats.get("total_sections", 0) == 0:
            quality["no_sections"] += 1

        toc = report.get("content_summary", {}).get("toc", [])
        if not toc:
            quality["empty_toc"] += 1

        quality["samples"].append(
            {
                "id": item_id,
                "status": status,
                "sections": stats.get("total_sections", 0),
                "tables": stats.get("total_tables", 0),
                "requirements": stats.get("requirements_extracted", 0),
            }
        )

    return quality
