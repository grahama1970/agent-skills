"""Chart data exporter for /create-figure integration.

Produces JSON files matching /create-figure input schemas:
- radar.json — 8-dimension rubric scores per session
- heatmap.json — difficulty × grade distribution
- grade_distribution.json — grade letter counts
- resolution_distribution.json — resolution outcome counts
- issue_distribution.json — systemic issue frequency
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Optional

# Dimension names from the SPARTA 8-dimension rubric
RUBRIC_DIMENSIONS = [
    "accuracy", "completeness", "clarity", "relevance",
    "citation_coverage", "reasoning_soundness", "framework_alignment",
    "iteration_efficiency",
]


def _build_radar(sessions: list[dict]) -> dict:
    """Radar chart: 8-dimension rubric scores per session."""
    series = {}
    for i, s in enumerate(sessions, 1):
        persona = s.get("persona", "Unknown")
        grade = s.get("grade", {})
        scores = grade.get("scores", grade.get("dimensions", {})) if isinstance(grade, dict) else {}
        if not scores:
            continue
        label = f"#{i} {persona}"
        series[label] = {
            dim: round(scores.get(dim, 0), 3)
            for dim in RUBRIC_DIMENSIONS
        }
    return {"series": series}


def _build_heatmap(sessions: list[dict]) -> dict:
    """Heatmap: difficulty (rows) × grade (columns) → count."""
    grid: dict[str, Counter] = {}
    for s in sessions:
        diff = s.get("seed_question", {}).get("difficulty", "unknown")
        grade = s.get("grade", {})
        letter = grade.get("grade", "?") if isinstance(grade, dict) else "?"
        grid.setdefault(diff, Counter())[letter] += 1
    return {diff: dict(counts) for diff, counts in sorted(grid.items())}


def _build_grade_dist(diagnosis: dict) -> dict:
    """Bar chart: grade letter distribution."""
    return {"metrics": diagnosis.get("summary", {}).get("grades", {})}


def _build_resolution_dist(diagnosis: dict) -> dict:
    """Bar/pie chart: resolution outcome distribution."""
    return {"metrics": diagnosis.get("summary", {}).get("resolutions", {})}


def _build_issue_dist(diagnosis: dict) -> dict:
    """Bar chart: systemic issue frequency."""
    issues = diagnosis.get("systemic_issues", [])
    return {"metrics": {i["issue"]: i["count"] for i in issues}}


# Registry: chart_name → (builder_fn, needs_sessions, needs_diagnosis)
_CHARTS: dict[str, tuple] = {
    "radar": (_build_radar, True, False),
    "heatmap": (_build_heatmap, True, False),
    "grade_distribution": (_build_grade_dist, False, True),
    "resolution_distribution": (_build_resolution_dist, False, True),
    "issue_distribution": (_build_issue_dist, False, True),
}


def build_chart_data(
    sessions: list[dict],
    diagnosis: dict,
    out_dir: Path,
    chart_filter: Optional[str] = None,
) -> dict[str, Path]:
    """Build chart JSON files for /create-figure.

    Returns dict of chart_name → file_path for each file written.
    """
    written = {}
    for name, (builder, needs_sess, needs_diag) in _CHARTS.items():
        if chart_filter and name != chart_filter:
            continue
        if needs_sess and needs_diag:
            data = builder(sessions, diagnosis)
        elif needs_sess:
            data = builder(sessions)
        else:
            data = builder(diagnosis)
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(data, indent=2))
        written[name] = path
    return written
