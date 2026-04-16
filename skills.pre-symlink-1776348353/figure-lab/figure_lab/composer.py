"""
Composer — generates D3 visualization code from primitives.

Takes a user description or catalog type name + data, produces
self-contained HTML with inline D3 code. Chart-specific generators
live in chart_generators.py.

Failure modes:
  - Returns empty HTML if chart_type has no generator and bar fallback fails
  - d3_catalog import may fail if /create-figure skill is not present (degrades gracefully)
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from figure_lab.chart_generators import (
    gen_area,
    gen_bar_fallback,
    gen_beeswarm,
    gen_box_plot,
    gen_bubble,
    gen_funnel,
    gen_gauge,
    gen_grouped_bar,
    gen_hbar,
    gen_heatmap,
    gen_histogram,
    gen_radar,
    gen_ridgeline,
    gen_stacked_area,
    gen_stacked_bar,
    gen_waterfall,
)
from figure_lab.config import (
    CANVAS_ANIMATION_MS,
    CANVAS_BG,
    CANVAS_FG,
    CREATE_FIGURE_DIR,
    FAILED_DIR,
    GALLERY_DIR,
    MIN_FONT_SIZE_PX,
    MIN_STROKE_WIDTH_PX,
)


@dataclass
class Composition:
    """A single visualization composition attempt."""

    name: str
    version: int = 1
    family: str = ""
    description: str = ""
    chart_type: str = ""  # d3_catalog type name
    data_shapes: list[str] = field(default_factory=list)
    marks: list[str] = field(default_factory=list)
    scales: dict[str, str] = field(default_factory=dict)
    encodings: dict[str, str] = field(default_factory=dict)
    d3_modules: list[str] = field(default_factory=list)
    html: str = ""
    test_data: list[dict[str, Any]] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    promoted: bool = False
    promoted_at: str | None = None
    iterations: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    errors: list[str] = field(default_factory=list)

    @property
    def overall_score(self) -> float:
        from figure_lab.config import EVAL_WEIGHTS

        if not self.scores:
            return 0.0
        return sum(
            self.scores.get(k, 0.0) * w for k, w in EVAL_WEIGHTS.items()
        )

    def save(self, failed: bool = False) -> Path:
        """Save composition to gallery or _failed directory."""
        target_dir = FAILED_DIR if failed else GALLERY_DIR
        slug = f"{self.name}_v{self.version}"

        # Save metadata JSON
        meta_path = target_dir / f"{slug}.json"
        meta = {
            "name": self.name,
            "version": self.version,
            "family": self.family,
            "description": self.description,
            "chart_type": self.chart_type,
            "data_shapes": self.data_shapes,
            "marks": self.marks,
            "scales": self.scales,
            "encodings": self.encodings,
            "d3_modules": self.d3_modules,
            "test_data": self.test_data[:5],  # Truncate for storage
            "scores": self.scores,
            "overall_score": self.overall_score,
            "promoted": self.promoted,
            "promoted_at": self.promoted_at,
            "iterations": self.iterations,
            "created_at": self.created_at,
            "errors": self.errors,
        }
        meta_path.write_text(json.dumps(meta, indent=2))

        # Save HTML
        if self.html:
            html_path = target_dir / f"{slug}.html"
            html_path.write_text(self.html)

        return meta_path

    @classmethod
    def load(cls, path: Path) -> "Composition":
        """Load composition from gallery JSON."""
        data = json.loads(path.read_text())
        return cls(**{k: v for k, v in data.items() if k != "overall_score"})


def _load_catalog():
    """Import d3_catalog from /create-figure."""
    sys.path.insert(0, str(CREATE_FIGURE_DIR))
    try:
        import d3_catalog

        return d3_catalog
    except ImportError:
        return None


def _d3_cdn_url() -> str:
    return "https://cdn.jsdelivr.net/npm/d3@7/+esm"


def compose_from_type(
    chart_type: str,
    data: list[dict[str, Any]],
    title: str = "",
    canvas: bool = True,
) -> Composition:
    """
    Compose a visualization from a d3_catalog type name.

    This generates self-contained HTML with inline D3 code
    appropriate for the chart type and data shape.
    """
    catalog = _load_catalog()

    comp = Composition(
        name=chart_type,
        chart_type=chart_type,
        test_data=data,
        description=title or f"{chart_type} visualization",
    )

    # Look up type info from catalog
    viz_info = None
    if catalog:
        viz_info = catalog.get_viz_type(chart_type)
        if viz_info:
            comp.family = viz_info.family.value
            comp.data_shapes = [ds.value for ds in viz_info.data_shapes]
            comp.d3_modules = [viz_info.d3_module] if viz_info.d3_module else []

    # Generate HTML based on chart type
    comp.html = _generate_html(chart_type, data, title, canvas)
    return comp


def compose_from_description(
    description: str,
    data: list[dict[str, Any]],
    canvas: bool = True,
) -> Composition:
    """
    Compose a visualization from a natural language description.

    Uses d3_catalog.match_keywords() to find the best chart type,
    then delegates to compose_from_type().
    """
    catalog = _load_catalog()

    chart_type = "bar"  # Default fallback
    if catalog:
        matches = catalog.match_keywords(description)
        if matches:
            chart_type = matches[0][0]  # Best match name

    return compose_from_type(chart_type, data, title=description, canvas=canvas)


# Chart type → generator function dispatch table
_GENERATORS = {
    "hbar": gen_hbar,
    "stacked_bar": gen_stacked_bar,
    "grouped_bar": gen_grouped_bar,
    "area": gen_area,
    "stacked_area": gen_stacked_area,
    "radar": gen_radar,
    "bubble": gen_bubble,
    "heatmap": gen_heatmap,
    "histogram": gen_histogram,
    "box_plot": gen_box_plot,
    "waterfall": gen_waterfall,
    "funnel": gen_funnel,
    "ridgeline": gen_ridgeline,
    "beeswarm": gen_beeswarm,
    "gauge": gen_gauge,
}


def _generate_html(
    chart_type: str,
    data: list[dict[str, Any]],
    title: str,
    canvas: bool,
) -> str:
    """Generate self-contained HTML with D3 visualization."""
    data_json = json.dumps(data)
    font_size = MIN_FONT_SIZE_PX
    stroke_w = MIN_STROKE_WIDTH_PX
    anim_ms = CANVAS_ANIMATION_MS

    gen_fn = _GENERATORS.get(chart_type, gen_bar_fallback)
    d3_code = gen_fn(data_json, font_size, stroke_w, anim_ms)

    return _wrap_html(d3_code, title, canvas)


def _wrap_html(d3_code: str, title: str, canvas: bool) -> str:
    """Wrap D3 code in a self-contained HTML shell."""
    if canvas:
        canvas_css = f"""
        body {{
            background: {CANVAS_BG};
            color: {CANVAS_FG};
            font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
            margin: 0;
            padding: 0;
            height: 100vh;
            width: 100vw;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }}
        .canvas-header {{
            padding: 16px 24px 8px;
            flex-shrink: 0;
        }}
        .canvas-title {{
            font-size: 24px;
            font-weight: 700;
        }}
        .canvas-body {{
            flex: 1;
            display: flex;
            align-items: center;
            justify-content: center;
            padding: 8px 24px 24px;
            overflow: hidden;
            animation: fade-in {CANVAS_ANIMATION_MS}ms cubic-bezier(0.4, 0, 0.2, 1) both;
        }}
        @keyframes fade-in {{
            from {{ opacity: 0; transform: translateY(8px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        #chart {{ width: 100%; height: 100%; }}
        """
    else:
        canvas_css = """
        body { margin: 20px; font-family: system-ui, sans-serif; }
        #chart { width: 100%; height: 600px; }
        """

    header = ""
    if title and canvas:
        from html import escape

        header = f'<div class="canvas-header"><div class="canvas-title">{escape(title)}</div></div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title or 'Figure Lab'}</title>
<style>{canvas_css}</style>
</head>
<body>
{header}
<div class="canvas-body">
<div id="chart"></div>
</div>
<script type="module">
import * as d3 from "{_d3_cdn_url()}";
{d3_code}
</script>
</body>
</html>"""
