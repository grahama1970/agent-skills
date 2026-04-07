"""
Evaluator — scores a composition for render success, visual fidelity, and intent match.

Self-improvement loop: evaluates, diagnoses failures, suggests fixes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from figure_lab.config import (
    EVAL_WEIGHTS,
    PROMOTE_THRESHOLD,
    RECOMPOSE_THRESHOLD,
    MIN_FONT_SIZE_PX,
    MIN_STROKE_WIDTH_PX,
)


@dataclass
class EvalResult:
    """Result of evaluating a composition."""

    render_success: float = 0.0
    data_marks: float = 0.0
    axes_labels: float = 0.0
    intent_match: float = 0.0
    distance_aware: float = 0.0
    errors: list[str] | None = None
    diagnostics: list[str] | None = None

    @property
    def overall(self) -> float:
        return sum(
            getattr(self, k) * w for k, w in EVAL_WEIGHTS.items()
        )

    @property
    def verdict(self) -> str:
        score = self.overall
        if score >= PROMOTE_THRESHOLD:
            return "PROMOTE"
        if score >= RECOMPOSE_THRESHOLD:
            return "ITERATE"
        return "RECOMPOSE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "render_success": self.render_success,
            "data_marks": self.data_marks,
            "axes_labels": self.axes_labels,
            "intent_match": self.intent_match,
            "distance_aware": self.distance_aware,
            "overall": self.overall,
            "verdict": self.verdict,
            "errors": self.errors or [],
            "diagnostics": self.diagnostics or [],
        }


def evaluate_html(html: str, intent: str = "", data_count: int = 0) -> EvalResult:
    """
    Evaluate a self-contained HTML visualization.

    Checks:
    1. Render success — does the HTML contain valid SVG/D3 output structure?
    2. Data marks — does it have rect/circle/path/line elements?
    3. Axes & labels — does it have axis groups and text labels?
    4. Intent match — does the chart type seem right for the description?
    5. Distance-aware — are font sizes >= 18px?
    """
    result = EvalResult(errors=[], diagnostics=[])

    # 1. Render success — static analysis of the HTML
    result.render_success = _check_render(html, result)

    # 2. Data marks present
    result.data_marks = _check_data_marks(html, data_count, result)

    # 3. Axes and labels
    result.axes_labels = _check_axes_labels(html, result)

    # 4. Intent match (heuristic — needs the user's description)
    result.intent_match = _check_intent_match(html, intent, result)

    # 5. Distance-aware (5ft viewing)
    result.distance_aware = _check_distance_aware(html, result)

    return result


def evaluate_file(path: Path, intent: str = "", data_count: int = 0) -> EvalResult:
    """Evaluate an HTML file."""
    html = path.read_text()
    return evaluate_html(html, intent=intent, data_count=data_count)


def _check_render(html: str, result: EvalResult) -> float:
    """Check that the HTML is well-formed and has D3 content."""
    if not html or len(html) < 100:
        result.errors.append("HTML is empty or too short")
        return 0.0

    # Must have basic HTML structure
    if "<svg" not in html and "plotly" not in html.lower():
        # Could be a Plotly div without SVG at parse time
        if "d3." not in html and "Plotly" not in html:
            result.errors.append("No SVG or Plotly content found")
            return 0.0

    # Check for JS errors in the code (static analysis)
    js_errors = []
    if "undefined" in html and "=== undefined" not in html and "!== undefined" not in html:
        # Common but not definitive
        pass

    # Check D3 import
    if "d3" in html.lower() or "plotly" in html.lower():
        score = 0.8
    else:
        score = 0.5
        result.diagnostics.append("No D3 or Plotly import detected")

    # Has a chart container
    if 'id="chart"' in html or 'class="canvas-body"' in html:
        score += 0.2

    return min(1.0, score)


def _check_data_marks(html: str, expected_count: int, result: EvalResult) -> float:
    """Check that data marks (visual elements) are being created."""
    # Look for D3 .join() or .append() calls for visual marks
    mark_patterns = [
        r"\.join\(['\"]rect['\"]",
        r"\.join\(['\"]circle['\"]",
        r"\.join\(['\"]path['\"]",
        r"\.join\(['\"]line['\"]",
        r"\.join\(['\"]text['\"]",
        r"\.append\(['\"]rect['\"]",
        r"\.append\(['\"]circle['\"]",
        r"\.append\(['\"]path['\"]",
        r"\.append\(['\"]line['\"]",
        r"go\.Sankey",
        r"px\.sunburst",
        r"px\.treemap",
    ]

    marks_found = sum(1 for p in mark_patterns if re.search(p, html))

    if marks_found == 0:
        result.errors.append("No data marks (rect/circle/path/line) found in code")
        return 0.0

    # Check that data is being bound
    if ".data(" in html or "datum(" in html or "const data" in html:
        data_bound = True
    else:
        data_bound = False
        result.diagnostics.append("No data binding detected (.data() or .datum())")

    score = min(1.0, marks_found * 0.3)
    if data_bound:
        score = min(1.0, score + 0.4)

    return score


def _check_axes_labels(html: str, result: EvalResult) -> float:
    """Check for axis creation and text labels."""
    score = 0.0

    # Check for D3 axis calls
    has_x_axis = "axisBottom" in html or "axisTop" in html
    has_y_axis = "axisLeft" in html or "axisRight" in html

    if has_x_axis:
        score += 0.3
    else:
        result.diagnostics.append("No X axis (axisBottom/axisTop) found")

    if has_y_axis:
        score += 0.3

    # Check for text elements (labels, titles)
    text_count = html.count(".append('text')") + html.count('.append("text")')
    text_count += html.count(".join('text')") + html.count('.join("text")')

    if text_count > 0:
        score += 0.2

    # Title present
    if "canvas-title" in html or "title_text" in html:
        score += 0.2

    # Some chart types (pie, radar, gauge) don't need traditional axes
    no_axis_types = ["pie", "donut", "radar", "gauge", "sunburst", "treemap", "funnel"]
    for t in no_axis_types:
        if t in html.lower():
            score = max(score, 0.7)  # Don't penalize for missing axes
            break

    return min(1.0, score)


def _check_intent_match(html: str, intent: str, result: EvalResult) -> float:
    """Heuristic check: does the chart type match the user's intent?"""
    if not intent:
        # No intent provided — can't evaluate, give neutral score
        return 0.7

    intent_lower = intent.lower()

    # Map intent keywords to expected D3 patterns
    intent_signals = {
        "bar": ["scaleBand", "rect", "axisBottom"],
        "horizontal bar": ["scaleBand", "barh", "axisLeft"],
        "line": ["line()", "curveMonotone", "path"],
        "scatter": ["circle", "scaleLinear"],
        "pie": ["pie()", "arc()", "innerRadius"],
        "area": ["area()", "curveMonotone"],
        "heatmap": ["scaleSequential", "interpolateBlues"],
        "radar": ["angleSlice", "curveLinearClosed"],
        "waterfall": ["cumulative", "connector"],
        "funnel": ["funnel", "centerX"],
        "histogram": ["bin()", "thresholds"],
        "box": ["quantile", "whisker", "iqr"],
        "ridgeline": ["kde", "overlap", "curveBasis"],
        "beeswarm": ["dodge", "beeswarm"],
        "gauge": ["arcBg", "arcFg", "endAngle"],
        "bubble": ["scaleSqrt", "circle"],
        "stacked": ["stack()", "layer"],
        "grouped": ["scaleBand", "x0", "x1"],
    }

    best_match = 0.0
    for keyword, signals in intent_signals.items():
        if keyword in intent_lower:
            matches = sum(1 for s in signals if s in html)
            match_ratio = matches / len(signals)
            best_match = max(best_match, match_ratio)

    if best_match > 0:
        return min(1.0, best_match + 0.3)  # Bonus for any match

    # Fallback: at least the HTML has chart-like content
    return 0.5


def _check_distance_aware(html: str, result: EvalResult) -> float:
    """Check that text sizes and strokes meet 5ft viewing requirements."""
    score = 0.0

    # Check font sizes in the code
    font_sizes = re.findall(r"font.size['\"]?\s*[:=,]\s*['\"]?(\d+)", html)
    font_sizes += re.findall(r"fontSize\s*[:=]\s*['\"]?(\d+)", html)
    font_sizes += re.findall(r"font-size['\"]?\s*[:=]\s*['\"]?(\d+)", html)

    if font_sizes:
        min_size = min(int(s) for s in font_sizes)
        if min_size >= MIN_FONT_SIZE_PX:
            score += 0.5
        elif min_size >= 14:
            score += 0.3
            result.diagnostics.append(
                f"Minimum font size {min_size}px < {MIN_FONT_SIZE_PX}px target"
            )
        else:
            result.diagnostics.append(
                f"Font size {min_size}px too small for 5ft viewing"
            )
    else:
        score += 0.3  # Can't determine — neutral

    # Check stroke widths
    stroke_widths = re.findall(r"stroke.width['\"]?\s*[:=,]\s*(\d+)", html)
    if stroke_widths:
        min_stroke = min(int(s) for s in stroke_widths)
        if min_stroke >= MIN_STROKE_WIDTH_PX:
            score += 0.3
        else:
            result.diagnostics.append(
                f"Stroke width {min_stroke}px < {MIN_STROKE_WIDTH_PX}px target"
            )
    else:
        score += 0.2  # Neutral

    # Check for canvas-specific CSS
    if "canvas-body" in html or "canvas-title" in html:
        score += 0.2

    return min(1.0, score)


def diagnose_failures(result: EvalResult) -> list[str]:
    """
    Given an evaluation result, suggest specific fixes.

    Returns a list of actionable suggestions.
    """
    suggestions = []

    if result.render_success < 0.5:
        suggestions.append("RENDER: Check D3 import URL and module syntax")
        suggestions.append("RENDER: Verify data JSON is valid and non-empty")

    if result.data_marks < 0.5:
        suggestions.append("MARKS: Add .data(data).join('rect'/'circle'/'path') calls")
        suggestions.append("MARKS: Ensure data variable is populated before bindings")

    if result.axes_labels < 0.5:
        suggestions.append("AXES: Add d3.axisBottom(x) and d3.axisLeft(y) calls")
        suggestions.append("LABELS: Add .append('text') for axis labels and title")

    if result.intent_match < 0.5:
        suggestions.append("INTENT: Chart type may not match the user's request")
        suggestions.append("INTENT: Consider switching marks (rect→circle, line→area)")

    if result.distance_aware < 0.5:
        suggestions.append(f"DISTANCE: Increase all font sizes to >= {MIN_FONT_SIZE_PX}px")
        suggestions.append(f"DISTANCE: Increase stroke widths to >= {MIN_STROKE_WIDTH_PX}px")
        suggestions.append("DISTANCE: Add canvas-body wrapper with 800ms fade-in")

    return suggestions
