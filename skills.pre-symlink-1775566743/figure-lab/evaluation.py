#!/usr/bin/env python3
"""
evaluation.py — HTML evaluation logic for figure-lab.

Scores D3 visualizations on 5 dimensions:
- render_success (0.30): D3 v7 script tag, SVG patterns
- data_marks (0.25): visual mark elements
- axes_labels (0.15): axis groups, text labels
- intent_match (0.20): chart structure presence
- distance_aware (0.10): font sizes, stroke widths for 5ft viewing
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
EVAL_WEIGHTS = {
    "render_success": 0.30,
    "data_marks": 0.25,
    "axes_labels": 0.15,
    "intent_match": 0.20,
    "distance_aware": 0.10,
}
MIN_FONT_SIZE_PX = 18
MIN_STROKE_WIDTH_PX = 2

console = Console()


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------
@dataclass
class EvalScores:
    """Evaluation scores for a visualization."""

    render_success: float = 0.0
    data_marks: float = 0.0
    axes_labels: float = 0.0
    intent_match: float = 0.0
    distance_aware: float = 0.0
    overall: float = field(init=False, default=0.0)

    def __post_init__(self):
        self._recalc()

    def _recalc(self):
        self.overall = sum(
            getattr(self, dim) * w for dim, w in EVAL_WEIGHTS.items()
        )

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if name in EVAL_WEIGHTS:
            super().__setattr__(
                "overall",
                sum(
                    getattr(self, dim, 0.0) * w
                    for dim, w in EVAL_WEIGHTS.items()
                ),
            )

    def to_dict(self) -> dict[str, float]:
        """Return scores as a plain dict."""
        return {
            "render_success": self.render_success,
            "data_marks": self.data_marks,
            "axes_labels": self.axes_labels,
            "intent_match": self.intent_match,
            "distance_aware": self.distance_aware,
            "overall": self.overall,
        }


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def evaluate_html(html: str) -> EvalScores:
    """
    Evaluate an HTML file for D3 visualization quality.

    Checks 5 dimensions:
    - render_success (0.30): D3 v7 script tag, svg element pattern
    - data_marks (0.25): visual mark elements (rect, circle, path, line)
    - axes_labels (0.15): axis groups, text labels
    - intent_match (0.20): chart structure present
    - distance_aware (0.10): font sizes >= 18px, strokes >= 2px
    """
    scores = EvalScores()

    if not html or len(html) < 100:
        return scores

    # --- 1. Render success (0.30 weight) ---
    render = 0.0
    if re.search(r'd3@7|d3\.v7|cdn\.jsdelivr\.net/npm/d3@7', html):
        render += 0.4
    elif "d3" in html.lower():
        render += 0.2

    if re.search(r'<svg\b|\.append\(["\']svg["\']|\.select.*svg', html):
        render += 0.3

    if "d3-manipulate-runtime" in html or "manipulate" in html.lower():
        render += 0.3
    else:
        render += 0.1

    scores.render_success = min(1.0, render)

    # --- 2. Data marks (0.25 weight) ---
    mark_patterns = [
        r"\.join\(['\"]rect['\"]",
        r"\.join\(['\"]circle['\"]",
        r"\.join\(['\"]path['\"]",
        r"\.join\(['\"]line['\"]",
        r"\.append\(['\"]rect['\"]",
        r"\.append\(['\"]circle['\"]",
        r"\.append\(['\"]path['\"]",
        r"\.append\(['\"]line['\"]",
        r"\.append\(['\"]text['\"]",
        r"d3\.arc\(",
        r"d3\.pie\(",
        r"d3\.line\(",
        r"d3\.area\(",
    ]
    marks_found = sum(1 for p in mark_patterns if re.search(p, html))

    data_score = 0.0
    if marks_found >= 3:
        data_score = 1.0
    elif marks_found >= 2:
        data_score = 0.8
    elif marks_found >= 1:
        data_score = 0.5
    if ".data(" in html or ".datum(" in html or "const data" in html:
        data_score = min(1.0, data_score + 0.2)
    scores.data_marks = data_score

    # --- 3. Axes & labels (0.15 weight) ---
    axes_score = 0.0
    if "axisBottom" in html or "axisTop" in html:
        axes_score += 0.3
    if "axisLeft" in html or "axisRight" in html:
        axes_score += 0.3
    text_count = (
        html.count(".append('text')") + html.count('.append("text")')
        + html.count(".join('text')") + html.count('.join("text")')
    )
    if text_count > 0:
        axes_score += 0.2
    if "canvas-title" in html or "<title>" in html:
        axes_score += 0.2
    for no_axis_type in [
        "pie", "donut", "radar", "gauge", "sunburst", "treemap", "funnel"
    ]:
        if no_axis_type in html.lower():
            axes_score = max(axes_score, 0.7)
            break
    scores.axes_labels = min(1.0, axes_score)

    # --- 4. Intent match (0.20 weight) ---
    intent_score = 0.0
    if 'id="chart"' in html or 'class="canvas-body"' in html:
        intent_score += 0.3
    if "d3.scale" in html or "scaleLinear" in html or "scaleBand" in html:
        intent_score += 0.3
    if "viewBox" in html or "getBoundingClientRect" in html:
        intent_score += 0.2
    if len(html) > 500:
        intent_score += 0.2
    scores.intent_match = min(1.0, intent_score)

    # --- 5. Distance-aware (0.10 weight) ---
    dist_score = 0.0
    font_sizes = re.findall(r'font.size["\']?\s*[:=,]\s*["\']?(\d+)', html)
    font_sizes += re.findall(r'fontSize\s*[:=]\s*["\']?(\d+)', html)
    font_sizes += re.findall(r'font-size["\']?\s*[:=]\s*["\']?(\d+)', html)
    if font_sizes:
        min_size = min(int(s) for s in font_sizes)
        if min_size >= MIN_FONT_SIZE_PX:
            dist_score += 0.5
        elif min_size >= 14:
            dist_score += 0.3
    else:
        dist_score += 0.3

    stroke_widths = re.findall(r'stroke.width["\']?\s*[:=,]\s*(\d+)', html)
    if stroke_widths:
        min_stroke = min(int(s) for s in stroke_widths)
        if min_stroke >= MIN_STROKE_WIDTH_PX:
            dist_score += 0.3
    else:
        dist_score += 0.2

    if "canvas-body" in html or "canvas-title" in html:
        dist_score += 0.2
    scores.distance_aware = min(1.0, dist_score)

    return scores


def print_scores(name: str, scores: EvalScores) -> None:
    """Print evaluation scores as a Rich table."""
    table = Table(title=f"Evaluation: {name}")
    table.add_column("Dimension")
    table.add_column("Score", justify="right")
    table.add_column("Weight", justify="right")
    table.add_column("Weighted", justify="right")

    for dim, weight in EVAL_WEIGHTS.items():
        score = getattr(scores, dim, 0.0)
        weighted = score * weight
        style = "green" if score >= 0.8 else ("yellow" if score >= 0.5 else "red")
        table.add_row(
            dim.replace("_", " ").title(),
            f"[{style}]{score:.2f}[/{style}]",
            f"{weight:.2f}",
            f"{weighted:.2f}",
        )

    table.add_row(
        "", "", "[bold]Total[/bold]", f"[bold]{scores.overall:.2f}[/bold]"
    )
    console.print(table)
