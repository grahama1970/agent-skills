#!/usr/bin/env python3
"""
D3 rendering backend for /create-figure.

Generates self-contained interactive HTML visualizations using D3.js v7.
Each output includes the d3-manipulate-runtime.js for zoom/pan/highlight.

Supports two surface targets:
- Canvas mode (5ft desk): 18px+ text, WCAG AA contrast, ResizeObserver re-render
- Discord mode (phone): 500px viewport, touch-friendly, smaller margins

Usage:
    from d3_backend import render_d3

    render_d3("bar", data, output_path, canvas=True)
    render_d3("scatter", data, output_path, discord=True)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from loguru import logger

from d3_catalog import get_viz_type
from d3_catalog_types import RenderBackend, VizType

# Paths relative to this file
_SKILL_DIR = Path(__file__).resolve().parent
_D3_DIR = _SKILL_DIR / "d3"
_GALLERY_DIR = _D3_DIR / "gallery"
_RUNTIME_JS = _D3_DIR / "d3-manipulate-runtime.js"


def _load_runtime_js() -> str:
    """Load the d3-manipulate-runtime.js injection script."""
    if _RUNTIME_JS.exists():
        return _RUNTIME_JS.read_text(encoding="utf-8")
    logger.warning("d3-manipulate-runtime.js not found at {}", _RUNTIME_JS)
    return ""


def _load_gallery_template(viz_name: str) -> Optional[str]:
    """Load a gallery HTML template for a given viz type."""
    template_path = _GALLERY_DIR / f"{viz_name}.html"
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    logger.debug("No gallery template for '{}' at {}", viz_name, template_path)
    return None


def _normalize_data(
    data: Union[Dict[str, Any], List[Any], str, Path],
) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
    """Normalize input data for D3 consumption.

    Accepts:
    - List[Dict]: pass through
    - Dict with graph structure (nodes+links, children): pass through (preserve topology)
    - Dict with 'data' key: extract the list
    - Dict of {label: value}: convert to [{label, value}]
    - str/Path: load JSON from file

    Returns list of dicts for flat data, or dict for structured data
    (network graphs, hierarchies).
    """
    if isinstance(data, (str, Path)):
        path = Path(data)
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as e:
                logger.error("Invalid JSON in file {}: {}", path, e)
                return []
            return _normalize_data(raw)
        # Try parsing as JSON string
        try:
            raw = json.loads(str(data))
        except json.JSONDecodeError as e:
            logger.error("Cannot parse data as JSON: {}", e)
            return []
        return _normalize_data(raw)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        # Preserve graph topology: {nodes, links/edges}
        if "nodes" in data and any(k in data for k in ("links", "edges")):
            return data
        # Preserve hierarchy: {name, children}
        if "children" in data:
            return data
        # Preserve source-target pairs: {source, target, ...}
        if "source" in data and "target" in data:
            return data

        if "data" in data and isinstance(data["data"], list):
            return data["data"]
        # Handle analytics output: {"metrics": {"label": value}}
        if "metrics" in data and isinstance(data["metrics"], dict):
            return _normalize_data(data["metrics"])
        # Handle analytics wrapper: {"figure_data": {"bar": {"metrics": {...}}}}
        if "figure_data" in data and isinstance(data["figure_data"], dict):
            fd = data["figure_data"]
            # Try bar, pie, line in order
            for chart_key in ("bar", "pie", "line", "hbar"):
                if chart_key in fd and isinstance(fd[chart_key], dict):
                    inner = fd[chart_key]
                    if "metrics" in inner:
                        return _normalize_data(inner["metrics"])
                    return _normalize_data(inner)
            # Fall through to try first value
            first_val = next(iter(fd.values()), None)
            if isinstance(first_val, dict):
                return _normalize_data(first_val)
        # Dict of {label: value} → [{label, value}]
        if all(isinstance(v, (int, float)) for v in data.values()):
            return [{"label": k, "value": v} for k, v in data.items()]
        # Dict of {label: {...}} → flat list (only if not a known structure)
        if all(isinstance(v, dict) for v in data.values()):
            result = []
            for k, v in data.items():
                entry = {"label": k, **v}
                result.append(entry)
            return result

    return []


def _build_d3_html(
    viz_type: VizType,
    data: List[Dict[str, Any]],
    title: str = "",
    discord: bool = False,
) -> str:
    """Build self-contained D3 HTML from a gallery template or inline generation.

    Injects:
    - D3 v7 via CDN
    - d3-manipulate-runtime.js for interactive manipulation
    - Data as inline JSON
    - Distance-aware CSS (canvas mode by default)
    """
    runtime_js = _load_runtime_js()
    template_html = _load_gallery_template(viz_type.name)
    data_json = json.dumps(data, default=str).replace("</", "<\\/")

    if not title:
        title = viz_type.label

    viewport_meta = (
        '<meta name="viewport" content="width=500, initial-scale=1">'
        if discord
        else '<meta name="viewport" content="width=device-width, initial-scale=1">'
    )

    if template_html:
        # Template exists — inject real data + runtime
        if data:
            # Inject data as global BEFORE the module script so templates
            # can read it via: const data = window.__INJECTED_DATA__ || [sample]
            data_script = (
                f'<script>window.__INJECTED_DATA__ = {data_json};</script>'
            )
            template_html = template_html.replace(
                '<script type="module">',
                f'{data_script}\n<script type="module">',
                1,
            )
        # Insert runtime script before closing </body>
        if "</body>" in template_html:
            injection = f"<script>\n{runtime_js}\n</script>"
            template_html = template_html.replace(
                "</body>", f"{injection}\n</body>"
            )
        return template_html

    # No template — generate inline D3 HTML
    font_size = "11px" if discord else "18px"
    margin_cfg = (
        "{top: 20, right: 12, bottom: 40, left: 40}"
        if discord
        else "{top: 40, right: 24, bottom: 60, left: 64}"
    )

    touch_listeners = ""
    if discord:
        touch_listeners = """
    // Touch-friendly: prevent default zoom on double-tap
    document.addEventListener('touchstart', function(e) {
        if (e.touches.length > 1) e.preventDefault();
    }, {passive: false});
"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
{viewport_meta}
<title>{_escape(title)}</title>
<style>
body {{
    background: #f8fafc;
    color: #1e293b;
    font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
    margin: 0; padding: 0;
    height: 100vh; width: 100vw;
    overflow: hidden;
    display: flex; flex-direction: column;
}}
.canvas-header {{ padding: 16px 24px 8px; flex-shrink: 0; }}
.canvas-title {{ font-size: 24px; font-weight: 700; }}
.canvas-body {{
    flex: 1;
    display: flex; align-items: center; justify-content: center;
    padding: 8px 24px 24px;
    overflow: hidden;
    animation: fade-in 800ms cubic-bezier(0.4, 0, 0.2, 1) both;
}}
@keyframes fade-in {{
    from {{ opacity: 0; transform: translateY(8px); }}
    to {{ opacity: 1; transform: translateY(0); }}
}}
#chart {{ width: 100%; height: 100%; }}
text {{ font-size: {font_size} !important; }}
</style>
</head>
<body>
<div class="canvas-header"><div class="canvas-title">{_escape(title)}</div></div>
<div class="canvas-body">
<div id="chart"></div>
</div>
<script type="module">
import * as d3 from "https://cdn.jsdelivr.net/npm/d3@7/+esm";

const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const width = rect.width || 800;
const height = rect.height || 500;
const margin = {margin_cfg};

{_get_draw_script(viz_type, discord)}
</script>
<script>
{runtime_js}
</script>
<script>
{touch_listeners}
// ResizeObserver for true re-render (not just SVG scaling)
new ResizeObserver(function() {{
    const chart = document.getElementById('chart');
    if (!chart) return;
    const svg = chart.querySelector('svg');
    if (svg) svg.remove();
    // Re-import and re-draw by reloading the module
    const scripts = document.querySelectorAll('script[type="module"]');
    if (scripts.length > 0) {{
        const newScript = document.createElement('script');
        newScript.type = 'module';
        newScript.textContent = scripts[0].textContent;
        document.body.appendChild(newScript);
    }}
}}).observe(document.getElementById('chart'));
</script>
</body>
</html>"""


def _get_draw_script(viz_type: VizType, discord: bool = False) -> str:
    """Return the D3 draw script for a given viz type.

    Uses the viz family to select the appropriate drawing logic.
    """
    family = viz_type.family.value
    name = viz_type.name
    stroke_w = "1" if discord else "2"

    # Family-specific draw scripts
    scripts = {
        "bar": f"""
const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

const x = d3.scaleBand()
  .domain(data.map(d => d.label || d.name || String(d.x)))
  .range([margin.left, width - margin.right])
  .padding(0.3);

const y = d3.scaleLinear()
  .domain([0, d3.max(data, d => d.value || d.y || 0)])
  .nice()
  .range([height - margin.bottom, margin.top]);

const colors = d3.scaleOrdinal(d3.schemeTableau10);

svg.selectAll('rect.bar').data(data).join('rect')
  .attr('class', 'bar')
  .attr('data-label', d => d.label || d.name || '')
  .attr('x', d => x(d.label || d.name || String(d.x)))
  .attr('width', x.bandwidth())
  .attr('y', d => y(d.value || d.y || 0))
  .attr('height', d => y(0) - y(d.value || d.y || 0))
  .attr('rx', 4)
  .attr('fill', (d, i) => colors(i))
  .attr('stroke-width', {stroke_w});

svg.append('g')
  .attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x));

svg.append('g')
  .attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y));
""",
        "line": f"""
const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

const parseDate = d => {{
    if (d.x instanceof Date) return d.x;
    const parsed = new Date(d.x || d.date || d.time);
    return isNaN(parsed) ? d.x : parsed;
}};

const isTimeSeries = data.length > 0 && !isNaN(new Date(data[0].x || data[0].date || ''));

const x = isTimeSeries
  ? d3.scaleTime()
      .domain(d3.extent(data, d => parseDate(d)))
      .range([margin.left, width - margin.right])
  : d3.scaleLinear()
      .domain(d3.extent(data, d => +d.x))
      .range([margin.left, width - margin.right]);

const y = d3.scaleLinear()
  .domain([0, d3.max(data, d => d.value || d.y || 0)])
  .nice()
  .range([height - margin.bottom, margin.top]);

const line = d3.line()
  .x(d => x(isTimeSeries ? parseDate(d) : +d.x))
  .y(d => y(d.value || d.y || 0))
  .curve(d3.curveMonotoneX);

svg.append('path')
  .datum(data)
  .attr('fill', 'none')
  .attr('stroke', '#4F46E5')
  .attr('stroke-width', {stroke_w})
  .attr('d', line);

svg.append('g')
  .attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x));

svg.append('g')
  .attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y));
""",
        "scatter": f"""
const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

const x = d3.scaleLinear()
  .domain(d3.extent(data, d => d.x)).nice()
  .range([margin.left, width - margin.right]);

const y = d3.scaleLinear()
  .domain(d3.extent(data, d => d.y || d.value)).nice()
  .range([height - margin.bottom, margin.top]);

const colors = d3.scaleOrdinal(d3.schemeTableau10);

svg.selectAll('circle').data(data).join('circle')
  .attr('data-label', d => d.label || d.name || '')
  .attr('cx', d => x(d.x))
  .attr('cy', d => y(d.y || d.value))
  .attr('r', d => Math.sqrt(d.size || d.r || 5) * 3)
  .attr('fill', (d, i) => colors(d.group || d.category || i))
  .attr('opacity', 0.7)
  .attr('stroke', '#fff')
  .attr('stroke-width', {stroke_w});

svg.append('g')
  .attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x));

svg.append('g')
  .attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y));
""",
        "pie": """
const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${width} ${height}`);

const radius = Math.min(width, height) / 2 - 40;
const g = svg.append('g')
  .attr('transform', `translate(${width/2},${height/2})`);

const pie = d3.pie().value(d => d.value || d.y || 0).sort(null);
const arc = d3.arc().innerRadius(0).outerRadius(radius);
const colors = d3.scaleOrdinal(d3.schemeTableau10);

const arcs = g.selectAll('.arc').data(pie(data)).join('g')
  .attr('class', 'arc');

arcs.append('path')
  .attr('d', arc)
  .attr('fill', (d, i) => colors(i))
  .attr('stroke', '#fff')
  .attr('stroke-width', 2)
  .attr('data-label', d => d.data.label || d.data.name || '');

arcs.append('text')
  .attr('transform', d => `translate(${arc.centroid(d)})`)
  .attr('text-anchor', 'middle')
  .text(d => d.data.label || d.data.name || '');
""",
        "area": f"""
const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

const x = d3.scaleLinear()
  .domain(d3.extent(data, (d, i) => d.x != null ? +d.x : i))
  .range([margin.left, width - margin.right]);

const y = d3.scaleLinear()
  .domain([0, d3.max(data, d => d.value || d.y || 0)])
  .nice()
  .range([height - margin.bottom, margin.top]);

const area = d3.area()
  .x((d, i) => x(d.x != null ? +d.x : i))
  .y0(y(0))
  .y1(d => y(d.value || d.y || 0))
  .curve(d3.curveMonotoneX);

svg.append('path')
  .datum(data)
  .attr('fill', 'rgba(79, 70, 229, 0.3)')
  .attr('stroke', '#4F46E5')
  .attr('stroke-width', {stroke_w})
  .attr('d', area);

svg.append('g')
  .attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x));

svg.append('g')
  .attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y));
""",
        "heatmap": """
const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${width} ${height}`);

// Expect data as [{row, col, value}]
const rows = [...new Set(data.map(d => d.row))];
const cols = [...new Set(data.map(d => d.col))];

const x = d3.scaleBand().domain(cols).range([margin.left, width - margin.right]).padding(0.05);
const y = d3.scaleBand().domain(rows).range([margin.top, height - margin.bottom]).padding(0.05);
const color = d3.scaleSequential(d3.interpolateYlOrRd)
  .domain([0, d3.max(data, d => d.value)]);

svg.selectAll('rect').data(data).join('rect')
  .attr('data-label', d => `${d.row}-${d.col}`)
  .attr('x', d => x(d.col))
  .attr('y', d => y(d.row))
  .attr('width', x.bandwidth())
  .attr('height', y.bandwidth())
  .attr('fill', d => color(d.value))
  .attr('rx', 2);

svg.append('g')
  .attr('transform', `translate(0,${height - margin.bottom})`)
  .call(d3.axisBottom(x));

svg.append('g')
  .attr('transform', `translate(${margin.left},0)`)
  .call(d3.axisLeft(y));
""",
    }

    # Map viz names to their family draw scripts
    name_to_family = {
        "bar": "bar", "hbar": "bar", "stacked_bar": "bar",
        "grouped_bar": "bar", "diverging_bar": "bar", "waterfall": "bar",
        "line": "line", "multi_line": "line", "slope": "line", "sparkline": "line",
        "area": "area", "stacked_area": "area", "streamgraph": "area",
        "ridgeline": "area", "horizon": "area",
        "scatter": "scatter", "bubble": "scatter", "beeswarm": "scatter",
        "dot_plot": "scatter",
        "pie": "pie", "donut": "pie",
        "heatmap": "heatmap",
        "histogram": "bar", "box_plot": "bar", "violin": "bar",
    }

    family_key = name_to_family.get(name, family)
    return scripts.get(family_key, scripts["bar"])


def render_d3(
    viz_name: str,
    data: Union[Dict[str, Any], List[Any], str, Path],
    output_path: Union[str, Path],
    title: str = "",
    canvas: bool = False,
    discord: bool = False,
    format: str = "html",
) -> bool:
    """Render a D3 visualization to file.

    Args:
        viz_name: Catalog viz type name (e.g., "bar", "scatter", "sankey")
        data: Input data (list of dicts, dict, JSON file path, or JSON string)
        output_path: Where to write the output
        title: Chart title
        canvas: Wrap in 5ft canvas mode (via wrap_d3_canvas)
        discord: Optimize for Discord phone viewing (500px width)
        format: Output format ("html" default, "png" for screenshot)

    Returns:
        True if successful, False otherwise
    """
    output_path = Path(output_path)
    viz_type = get_viz_type(viz_name)

    if not viz_type:
        logger.error("Unknown viz type '{}'. Use d3_catalog.py list to see options.", viz_name)
        return False

    # Normalize data
    normalized = _normalize_data(data)
    if normalized is None or (isinstance(normalized, (list, dict)) and len(normalized) == 0):
        logger.error("No data to render for '{}'", viz_name)
        return False

    data_len = len(normalized) if isinstance(normalized, list) else "structured"
    logger.info(
        "Rendering D3 '{}' with {} data points → {}",
        viz_name, data_len, output_path,
    )

    # Build HTML
    html = _build_d3_html(viz_type, normalized, title=title, discord=discord)

    if canvas:
        from canvas import wrap_d3_canvas
        html = wrap_d3_canvas(
            html,
            title=title or viz_type.label,
            source=f"/create-figure {viz_name}",
            discord=discord,
        )

    if format == "html":
        output_path = output_path.with_suffix(".html")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
        logger.info("D3 HTML written to {}", output_path)
        return True

    if format == "png":
        # Screenshot via playwright if available
        html_path = output_path.with_suffix(".html")
        html_path.write_text(html, encoding="utf-8")
        try:
            return _screenshot_html(html_path, output_path.with_suffix(".png"))
        except Exception as e:
            logger.warning("PNG screenshot failed: {}. HTML saved to {}", e, html_path)
            return True

    # Unsupported format — save as HTML anyway
    output_path = output_path.with_suffix(".html")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return True


def _screenshot_html(html_path: Path, png_path: Path) -> bool:
    """Take a screenshot of an HTML file using playwright."""
    import subprocess

    # Try playwright first
    result = subprocess.run(
        ["playwright", "screenshot", "--viewport-size=1920,1080",
         str(html_path), str(png_path)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        logger.info("PNG screenshot saved to {}", png_path)
        return True

    logger.warning("playwright screenshot failed: {}", result.stderr)
    return False


def render_with_fallback(
    data: Union[Dict[str, Any], List[Any], str, Path],
    output_path: Union[str, Path],
    query: Optional[str] = None,
    title: str = "",
    canvas: bool = False,
    discord: bool = False,
    format: str = "html",
    max_attempts: int = 5,
) -> Dict[str, Any]:
    """Render data using the best-fit viz type with automatic fallback.

    Profiles the data, ranks viz types by confidence, and tries each in
    order. If a render fails (data shape mismatch, D3 error), cascades
    to the next recommendation. If all fail, signals /figure-lab escalation.

    Args:
        data: Input data (list of dicts, dict, JSON file path, or JSON string)
        output_path: Where to write the output
        query: Optional NL query for keyword boosting (e.g., "show me trends")
        title: Chart title
        canvas: Wrap in 5ft canvas mode
        discord: Optimize for Discord
        format: "html" or "png"
        max_attempts: Max viz types to try before giving up

    Returns:
        Dict with keys:
            success: bool
            viz_name: str — the viz type that worked (or last tried)
            confidence: float — confidence of the selected viz type
            reason: str — why this viz type was chosen
            attempts: list[dict] — log of all attempts [{viz_name, success, error}]
            escalate_to_figure_lab: bool — True if all attempts failed
    """
    from d3_catalog import profile_data

    normalized = _normalize_data(data)
    if normalized is None or (isinstance(normalized, (list, dict)) and len(normalized) == 0):
        return {
            "success": False,
            "viz_name": "none",
            "confidence": 0.0,
            "reason": "empty data",
            "attempts": [],
            "escalate_to_figure_lab": True,
        }

    # Get ranked recommendations (profile_data expects list of dicts)
    profile_input = normalized if isinstance(normalized, list) else [normalized]
    recommendations = profile_data(profile_input, query=query)
    if not recommendations:
        recommendations = [("table", 0.1, "no recommendations")]

    attempts = []
    for viz_name, confidence, reason in recommendations[:max_attempts]:
        try:
            # Pass original data directly — render_d3 will normalize again
            # but now _normalize_data preserves structured data
            success = render_d3(
                viz_name=viz_name,
                data=data,
                output_path=output_path,
                title=title or f"{viz_name.replace('_', ' ').title()}",
                canvas=canvas,
                discord=discord,
                format=format,
            )
            attempts.append({
                "viz_name": viz_name,
                "success": success,
                "confidence": confidence,
                "error": None,
            })
            if success:
                logger.info(
                    "render_with_fallback: '{}' succeeded (confidence={}, reason={})",
                    viz_name, confidence, reason,
                )
                return {
                    "success": True,
                    "viz_name": viz_name,
                    "confidence": confidence,
                    "reason": reason,
                    "attempts": attempts,
                    "escalate_to_figure_lab": False,
                }
        except Exception as e:
            logger.warning(
                "render_with_fallback: '{}' failed: {}. Trying next.",
                viz_name, e,
            )
            attempts.append({
                "viz_name": viz_name,
                "success": False,
                "confidence": confidence,
                "error": str(e),
            })

    # All attempts failed — escalate to /figure-lab
    logger.warning(
        "render_with_fallback: all {} attempts failed. Escalating to /figure-lab.",
        len(attempts),
    )
    return {
        "success": False,
        "viz_name": attempts[-1]["viz_name"] if attempts else "none",
        "confidence": 0.0,
        "reason": "all recommended viz types failed",
        "attempts": attempts,
        "escalate_to_figure_lab": True,
    }


def _escape(s: str) -> str:
    """Basic HTML escaping."""
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))
