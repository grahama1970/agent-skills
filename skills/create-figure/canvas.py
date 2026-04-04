#!/usr/bin/env python3
"""
Canvas mode — distance-aware responsive HTML wrapper for 5ft answer canvas.

Wraps matplotlib SVG output and Plotly figures in self-contained HTML shells
with distance-aware styling (18px+ text, high contrast, persona accent colors,
800ms animations, ResizeObserver for responsiveness).

Usage:
    # Wrap matplotlib SVG
    html = wrap_svg_canvas(svg_string, title="Convergence Trend")

    # Wrap Plotly figure
    html = wrap_plotly_canvas(fig, title="Flow Diagram")

    # Backend functions can call canvas_render() to auto-select
    html = canvas_render(output_path, title, render_fn, ...)
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Optional

# Distance-aware CSS for 5ft desk viewing
# All sizes designed for comfortable reading at ~5 feet (1.5m)
_CANVAS_CSS = """\
:root {
    /* Persona accent — injected by the answer canvas at runtime */
    --persona-accent: 239 68% 68%;
    --canvas-bg: #f8fafc;
    --canvas-fg: #1e293b;
    --canvas-muted: #64748b;
    --canvas-border: #e2e8f0;
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
    background: var(--canvas-bg);
    color: var(--canvas-fg);
    font-family: system-ui, -apple-system, 'Segoe UI', sans-serif;
    overflow: hidden;
    height: 100vh;
    width: 100vw;
    display: flex;
    flex-direction: column;
}

.canvas-header {
    padding: 16px 24px 8px;
    flex-shrink: 0;
}

.canvas-title {
    font-size: 24px;
    font-weight: 700;
    color: var(--canvas-fg);
    line-height: 1.2;
}

.canvas-subtitle {
    font-size: 14px;
    color: var(--canvas-muted);
    margin-top: 2px;
}

.canvas-body {
    flex: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 8px 24px 24px;
    overflow: hidden;
    animation: canvas-fade-in 800ms cubic-bezier(0.4, 0, 0.2, 1) both;
}

/* SVG container — responsive via ResizeObserver */
.canvas-svg-container {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
}

.canvas-svg-container svg {
    max-width: 100%;
    max-height: 100%;
    width: auto;
    height: auto;
}

/* Plotly container — fills available space */
.canvas-plotly-container {
    width: 100%;
    height: 100%;
}

/* Distance-aware text overrides for matplotlib SVG */
.canvas-svg-container text {
    font-size: 18px !important;
    font-family: system-ui, -apple-system, sans-serif !important;
}

.canvas-svg-container text[font-size] {
    /* Enforce minimum 16px for any text in the chart */
    font-size: max(16px, attr(font-size)) !important;
}

/* Title text inside SVG should be larger */
.canvas-svg-container text.title,
.canvas-svg-container text[class*="title"] {
    font-size: 22px !important;
    font-weight: 700 !important;
}

/* Axis labels */
.canvas-svg-container text.label,
.canvas-svg-container text[class*="label"] {
    font-size: 18px !important;
}

/* Tick labels */
.canvas-svg-container text.tick,
.canvas-svg-container text[class*="tick"] {
    font-size: 16px !important;
}

/* Stroke widths for visibility at 5ft */
.canvas-svg-container path,
.canvas-svg-container line,
.canvas-svg-container rect {
    stroke-width: max(2px, attr(stroke-width)) !important;
}

/* Contrast: WCAG AA 4.5:1 minimum */
.canvas-svg-container text {
    fill: #1e293b !important;
}

@keyframes canvas-fade-in {
    from { opacity: 0; transform: translateY(8px); }
    to { opacity: 1; transform: translateY(0); }
}

/* Source/citation footer */
.canvas-footer {
    padding: 4px 24px 12px;
    flex-shrink: 0;
    font-size: 12px;
    color: var(--canvas-muted);
    text-align: right;
}
"""

_CANVAS_JS = """\
// ResizeObserver for responsive SVG scaling
document.addEventListener('DOMContentLoaded', () => {
    const container = document.querySelector('.canvas-svg-container');
    if (!container) return;

    const svg = container.querySelector('svg');
    if (!svg) return;

    // Remove fixed width/height from matplotlib SVG, use viewBox
    const w = svg.getAttribute('width');
    const h = svg.getAttribute('height');
    if (w && h) {
        const wNum = parseFloat(w);
        const hNum = parseFloat(h);
        if (wNum > 0 && hNum > 0) {
            if (!svg.getAttribute('viewBox')) {
                svg.setAttribute('viewBox', `0 0 ${wNum} ${hNum}`);
            }
            svg.removeAttribute('width');
            svg.removeAttribute('height');
            svg.style.width = '100%';
            svg.style.height = '100%';
        }
    }

    // Bump text sizes for 5ft viewing
    svg.querySelectorAll('text').forEach(t => {
        const current = parseFloat(getComputedStyle(t).fontSize);
        if (current < 16) {
            t.style.fontSize = '16px';
        }
    });
});
"""


def wrap_svg_canvas(
    svg: str,
    title: str = "",
    subtitle: str = "",
    source: str = "",
) -> str:
    """Wrap an SVG string in a distance-aware responsive HTML shell.

    Args:
        svg: Raw SVG string from matplotlib
        title: Chart title (displayed above)
        subtitle: Optional subtitle
        source: Optional source/citation (displayed bottom-right)

    Returns:
        Self-contained HTML string
    """
    header = ""
    if title:
        header = f'<div class="canvas-header">'
        header += f'<div class="canvas-title">{_escape(title)}</div>'
        if subtitle:
            header += f'<div class="canvas-subtitle">{_escape(subtitle)}</div>'
        header += "</div>"

    footer = ""
    if source:
        footer = f'<div class="canvas-footer">{_escape(source)}</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(title or 'Canvas')}</title>
<style>{_CANVAS_CSS}</style>
</head>
<body>
{header}
<div class="canvas-body">
<div class="canvas-svg-container">
{svg}
</div>
</div>
{footer}
<script>{_CANVAS_JS}</script>
</body>
</html>"""


def wrap_plotly_canvas(
    fig: Any,
    title: str = "",
    subtitle: str = "",
    source: str = "",
) -> str:
    """Wrap a Plotly figure in a distance-aware responsive HTML shell.

    Applies 5ft-distance-aware layout settings to the Plotly figure
    and writes to a self-contained HTML string.

    Args:
        fig: Plotly figure object
        title: Chart title
        subtitle: Optional subtitle
        source: Optional source/citation

    Returns:
        Self-contained HTML string
    """
    # Apply distance-aware Plotly layout
    fig.update_layout(
        font=dict(size=18, family="system-ui, -apple-system, sans-serif"),
        title=dict(
            text=title,
            font=dict(size=24),
            x=0.02,
            xanchor="left",
        ) if title else None,
        margin=dict(l=60, r=30, t=60 if title else 30, b=60),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(248,250,252,1)",
        hoverlabel=dict(font_size=16),
    )

    # Update axis label sizes
    fig.update_xaxes(
        tickfont=dict(size=16),
        title_font=dict(size=18),
    )
    fig.update_yaxes(
        tickfont=dict(size=16),
        title_font=dict(size=18),
    )

    # Generate Plotly HTML div (not full page — we wrap it ourselves)
    plotly_html = fig.to_html(
        full_html=False,
        include_plotlyjs="cdn",
        config={
            "responsive": True,
            "displayModeBar": False,
            "displaylogo": False,
        },
    )

    header = ""
    if subtitle:
        header = f'<div class="canvas-header">'
        header += f'<div class="canvas-subtitle">{_escape(subtitle)}</div>'
        header += "</div>"

    footer = ""
    if source:
        footer = f'<div class="canvas-footer">{_escape(source)}</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{_escape(title or 'Canvas')}</title>
<style>{_CANVAS_CSS}</style>
</head>
<body>
{header}
<div class="canvas-body">
<div class="canvas-plotly-container">
{plotly_html}
</div>
</div>
{footer}
</body>
</html>"""


def matplotlib_to_canvas(
    title: str = "",
    subtitle: str = "",
    source: str = "",
) -> str:
    """Capture current matplotlib figure as SVG and wrap in canvas HTML.

    Call this INSTEAD of plt.savefig() when --canvas is active.
    The caller should have already created the figure and axes.

    Returns:
        Self-contained HTML string
    """
    import matplotlib.pyplot as plt

    buf = io.BytesIO()
    plt.savefig(buf, format="svg", bbox_inches="tight", dpi=150)
    plt.close()
    buf.seek(0)
    svg = buf.read().decode("utf-8")

    return wrap_svg_canvas(svg, title=title, subtitle=subtitle, source=source)


def wrap_d3_canvas(
    d3_html: str,
    title: str = "",
    subtitle: str = "",
    source: str = "",
    discord: bool = False,
) -> str:
    """Wrap D3 interactive HTML in a distance-aware responsive canvas shell.

    Unlike wrap_svg_canvas() which scales a static SVG via viewBox, this
    injects a ResizeObserver that triggers a full D3 re-render on resize.
    Also injects d3-manipulate-runtime.js for zoom/pan/highlight/drill-down.

    Args:
        d3_html: Self-contained D3 HTML string (with inline <script type="module">)
        title: Chart title (displayed above)
        subtitle: Optional subtitle
        source: Optional source/citation (displayed bottom-right)
        discord: Optimize for Discord phone viewing (500px width, touch events)

    Returns:
        Self-contained HTML string with canvas wrapper
    """
    # Load the manipulation runtime
    runtime_path = Path(__file__).resolve().parent / "d3" / "d3-manipulate-runtime.js"
    runtime_js = ""
    if runtime_path.exists():
        runtime_js = runtime_path.read_text(encoding="utf-8")

    # Discord-specific viewport and touch handling
    viewport_meta = (
        '<meta name="viewport" content="width=500, initial-scale=1">'
        if discord
        else '<meta name="viewport" content="width=device-width, initial-scale=1">'
    )

    touch_script = ""
    if discord:
        touch_script = """
<script>
// Touch-friendly: prevent default zoom on double-tap, add touch event passthrough
document.addEventListener('touchstart', function(e) {
    if (e.touches.length > 1) e.preventDefault();
}, {passive: false});
</script>
"""

    # Distance-aware CSS overrides for D3 content
    d3_canvas_css = """
/* D3 Canvas Mode — distance-aware overrides */
.canvas-d3-container {
    width: 100%;
    height: 100%;
}

/* Ensure D3 text is readable at 5ft */
.canvas-d3-container text {
    font-size: 18px !important;
    font-family: system-ui, -apple-system, sans-serif !important;
}

/* D3 stroke widths for visibility */
.canvas-d3-container path,
.canvas-d3-container line,
.canvas-d3-container rect {
    stroke-width: max(2px, attr(stroke-width)) !important;
}

/* WCAG AA contrast */
.canvas-d3-container text {
    fill: #1e293b !important;
}
"""
    if discord:
        d3_canvas_css += """
/* Discord phone overrides */
.canvas-d3-container text {
    font-size: 11px !important;
}
.canvas-header { padding: 8px 12px 4px; }
.canvas-title { font-size: 16px; }
.canvas-body { padding: 4px 12px 12px; }
"""

    header = ""
    if title:
        header = '<div class="canvas-header">'
        header += f'<div class="canvas-title">{_escape(title)}</div>'
        if subtitle:
            header += f'<div class="canvas-subtitle">{_escape(subtitle)}</div>'
        header += "</div>"

    footer = ""
    if source:
        footer = f'<div class="canvas-footer">{_escape(source)}</div>'

    # Extract the body content from the D3 HTML (between <body> and </body>)
    body_content = d3_html
    if "<body>" in d3_html and "</body>" in d3_html:
        start = d3_html.index("<body>") + len("<body>")
        end = d3_html.index("</body>")
        body_content = d3_html[start:end]

    # Extract script tags from body content
    scripts = ""
    import re
    script_pattern = re.compile(r'<script[^>]*>.*?</script>', re.DOTALL)
    script_tags = script_pattern.findall(body_content)
    for tag in script_tags:
        scripts += tag + "\n"
    # Remove scripts from body for wrapping
    clean_body = script_pattern.sub('', body_content).strip()

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
{viewport_meta}
<title>{_escape(title or 'D3 Canvas')}</title>
<style>{_CANVAS_CSS}</style>
<style>{d3_canvas_css}</style>
</head>
<body>
{header}
<div class="canvas-body">
<div class="canvas-d3-container">
{clean_body}
</div>
</div>
{footer}
{scripts}
<script>
{runtime_js}
</script>
{touch_script}
<script>
// ResizeObserver: true D3 re-render on resize (NOT just SVG viewBox scaling)
(function() {{
    var resizeTimer;
    new ResizeObserver(function() {{
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function() {{
            var chart = document.getElementById('chart');
            if (!chart) return;
            var svg = chart.querySelector('svg');
            if (svg) svg.remove();
            // Re-execute the D3 module script to redraw at new dimensions
            var moduleScripts = document.querySelectorAll('script[type="module"]');
            if (moduleScripts.length > 0) {{
                var newScript = document.createElement('script');
                newScript.type = 'module';
                newScript.textContent = moduleScripts[0].textContent;
                document.body.appendChild(newScript);
            }}
        }}, 150); // debounce 150ms
    }}).observe(document.querySelector('.canvas-d3-container'));
}})();
</script>
</body>
</html>"""


def _escape(s: str) -> str:
    """Basic HTML escaping."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
