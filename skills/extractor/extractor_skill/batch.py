#!/usr/bin/env python3
"""
Batch processing and reporting for extractor skill.

This module handles batch extraction of multiple documents
and generates comprehensive reports.
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def generate_batch_report(
    results: List[Dict[str, Any]],
    output_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Generate comprehensive batch report with aggregates and downstream integration info.

    Args:
        results: List of extraction results
        output_dir: Optional directory to write report

    Returns:
        Dict with batch report containing:
        - batch_id: Timestamp identifier
        - total_files: Total files processed
        - succeeded: Count of successful extractions
        - failed: Count of failed extractions
        - results: List of per-file results
        - aggregates: Totals for sections/tables/figures
        - ready_for: List of downstream skills
    """
    batch_id = datetime.now().isoformat()

    # Categorize results
    succeeded = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]

    # Aggregate metrics
    total_sections = sum(r.get("counts", {}).get("sections", 0) for r in succeeded)
    total_tables = sum(r.get("counts", {}).get("tables", 0) for r in succeeded)
    total_figures = sum(r.get("counts", {}).get("figures", 0) for r in succeeded)

    # Build result entries
    result_entries = []
    for r in results:
        entry = {
            "file": r.get("file"),
            "status": "success" if r.get("success") else "failed",
        }
        if r.get("success"):
            entry.update({
                "preset": r.get("preset"),
                "mode": r.get("mode"),
                "sections": r.get("counts", {}).get("sections", 0),
                "tables": r.get("counts", {}).get("tables", 0),
                "figures": r.get("counts", {}).get("figures", 0),
                "output_dir": r.get("output_dir"),
                "markdown_path": r.get("outputs", {}).get("markdown"),
            })
        else:
            entry["error"] = r.get("error")
        result_entries.append(entry)

    report = {
        "batch_id": batch_id,
        "total_files": len(results),
        "succeeded": len(succeeded),
        "failed": len(failed),
        "results": result_entries,
        "aggregates": {
            "total_sections": total_sections,
            "total_tables": total_tables,
            "total_figures": total_figures,
        },
        "ready_for": ["doc-to-qra", "edge-verifier", "episodic-archiver"],
    }

    # Write report to file if output_dir provided
    if output_dir:
        report_path = output_dir / "batch_report.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, default=str))
        report["report_path"] = str(report_path)

    return report


def print_batch_summary(report: Dict[str, Any]) -> None:
    """
    Print human-readable batch summary to stderr.

    Args:
        report: Batch report dictionary
    """
    print(f"\nBatch Extraction Complete", file=sys.stderr)
    print(f"========================", file=sys.stderr)
    print(f"Total: {report['total_files']}", file=sys.stderr)
    print(f"Succeeded: {report['succeeded']}", file=sys.stderr)
    print(f"Failed: {report['failed']}", file=sys.stderr)
    print(f"\nAggregates:", file=sys.stderr)
    print(f"  Sections: {report['aggregates']['total_sections']}", file=sys.stderr)
    print(f"  Tables: {report['aggregates']['total_tables']}", file=sys.stderr)
    print(f"  Figures: {report['aggregates']['total_figures']}", file=sys.stderr)
    if report.get("report_path"):
        print(f"\nReport: {report['report_path']}", file=sys.stderr)
    print(f"\nReady for: {', '.join(report['ready_for'])}", file=sys.stderr)


def print_assessment_table(assessment: Dict[str, Any]) -> None:
    """
    Print a project agent friendly table comparing expected vs actual counts.

    Args:
        assessment: Assessment comparison dictionary from pipeline
    """
    if not assessment:
        return

    print("\nExtraction Assessment (Stage 00 vs Reality)", file=sys.stderr)
    print("-" * 65, file=sys.stderr)
    print(f"{'Metric':<15} | {'Expected (Pg)':<15} | {'Actual (Count)':<15} | {'Status':<10}", file=sys.stderr)
    print("-" * 65, file=sys.stderr)

    for key, data in assessment.items():
        status_icon = "+" if data.get("status") == "OK" else "-"
        print(
            f"{key.capitalize():<15} | "
            f"{data.get('expected_pages', 0):<15} | "
            f"{data.get('actual_count', 0):<15} | "
            f"{status_icon} {data.get('status')}",
            file=sys.stderr
        )
    print("-" * 65, file=sys.stderr)
