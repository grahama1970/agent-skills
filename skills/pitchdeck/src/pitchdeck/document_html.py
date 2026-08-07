"""House-native HTML renderer for pitchdeck.deck_document.v1 (#1262 golden slice).

The FIRST emitter that consumes the canonical document instead of the bundle
(the #1264 migration renders toward this). Applies a theme_template.v1 (light
canvas, petrol header band, Calibri scale — Graham's house chrome) and renders
every element from its bbox: text with style, images as data URIs (self-
contained), and DiagramGraphs as inline SVG with SEPARATE node/edge/label
shapes — never a raster. Output is one static HTML contact sheet; no external
resources, no JS. Failure modes: a referenced asset that cannot be read, or a
document element kind this renderer does not know, raise — nothing renders
partially.
"""

from __future__ import annotations

import base64
import html
import json
import mimetypes
from pathlib import Path

from .document import DeckDocument, DiagramGraph, DocElement, DocElementKind
from .io import expand_path

CANVAS_W, CANVAS_H = 1920, 1080


def _load_theme(theme_template: Path | None) -> dict:
    if theme_template is None:
        return {
            "mode": "light",
            "palette": {"primary": "#065E7C", "canvas": "#FFFFFF", "ink": "#292929", "muted": "#595959"},
            "theme_tokens": {"heading_font": "Calibri", "body_font": "Calibri"},
            "chrome": {"header_band": {"fill": "#065E7C", "title_color": "#FFFFFF"}},
        }
    return json.loads(theme_template.read_text(encoding="utf-8"))


def _data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def _diagram_svg(graph: DiagramGraph, width: float, height: float, primary: str, ink: str) -> str:
    """Nodes, connectors, and labels as separate SVG shapes (editability contract)."""
    parts: list[str] = [
        f'<svg viewBox="0 0 {width:.0f} {height:.0f}" width="100%" height="100%" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="Calibri, sans-serif">'
    ]
    centers: dict[str, tuple[float, float, float, float]] = {}
    for node in graph.nodes:
        x, y = node.bbox.x * width, node.bbox.y * height
        w, h = node.bbox.w * width, node.bbox.h * height
        centers[node.id] = (x + w / 2, y + h / 2, w, h)
        parts.append(
            f'<g id="node-{html.escape(node.id)}">'
            f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="10" '
            f'fill="none" stroke="{primary}" stroke-width="3"/>'
            + (
                f'<circle cx="{x + w / 2:.0f}" cy="{y + h * 0.32:.0f}" r="{min(w, h) * 0.16:.0f}" '
                f'fill="none" stroke="{primary}" stroke-width="2.5"/>'
                if node.icon
                else ""
            )
            + f'<text x="{x + w / 2:.0f}" y="{y + h * 0.68:.0f}" text-anchor="middle" '
            f'font-size="{max(14, h * 0.14):.0f}" font-weight="bold" fill="{primary}">{html.escape(node.label)}</text>'
            + (
                f'<text x="{x + w / 2:.0f}" y="{y + h * 0.84:.0f}" text-anchor="middle" '
                f'font-size="{max(11, h * 0.09):.0f}" fill="{ink}">{html.escape(node.sublabel)}</text>'
                if node.sublabel
                else ""
            )
            + "</g>"
        )
    marker = (
        f'<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" '
        f'markerHeight="8" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{primary}"/></marker></defs>'
    )
    parts.insert(1, marker)
    for edge in graph.edges:
        sx, sy, sw, _ = centers[edge.source]
        tx, ty, tw, _ = centers[edge.target]
        x1, x2 = sx + sw / 2, tx - tw / 2
        dash = {"solid": "", "dashed": ' stroke-dasharray="10 8"', "dotted": ' stroke-dasharray="3 6"'}[edge.line_style]
        arrow = ' marker-end="url(#arrow)"' if edge.arrowhead else ""
        parts.append(
            f'<g id="edge-{html.escape(edge.id)}">'
            f'<line x1="{x1:.0f}" y1="{sy:.0f}" x2="{x2:.0f}" y2="{ty:.0f}" '
            f'stroke="{primary}" stroke-width="3"{dash}{arrow}/>'
            + (
                f'<text x="{(x1 + x2) / 2:.0f}" y="{(sy + ty) / 2 - 12:.0f}" text-anchor="middle" '
                f'font-size="15" font-style="italic" fill="{ink}">{html.escape(edge.label)}</text>'
                if edge.label
                else ""
            )
            + "</g>"
        )
    parts.append("</svg>")
    return "".join(parts)


def _element_html(el: DocElement, assets_by_id: dict, asset_base: Path, theme: dict) -> str:
    palette = theme["palette"]
    left, top = el.bbox.x * 100, el.bbox.y * 100
    width, height = el.bbox.w * 100, el.bbox.h * 100
    pos = (
        f"position:absolute;left:{left:.2f}%;top:{top:.2f}%;width:{width:.2f}%;height:{height:.2f}%;"
        f"z-index:{el.z};"
    )
    qid = f'data-qid="doc:element:{html.escape(el.id)}"'
    if el.kind is DocElementKind.TEXT:
        style = el.style
        css = (
            f"font-size:{(style.size_pt if style else 20) * 1.6:.0f}px;"
            f"font-weight:{'bold' if style and style.bold else 'normal'};"
            f"color:{(style.color if style and style.color else palette['ink'])};"
            f"text-align:{style.align if style else 'left'};"
            f"font-family:{(style.font if style and style.font else theme['theme_tokens']['body_font'])}, sans-serif;"
            "white-space:pre-line;line-height:1.25;"
        )
        return f'<div {qid} style="{pos}{css}">{html.escape(el.text or "")}</div>'
    if el.kind is DocElementKind.IMAGE:
        spec = assets_by_id[el.asset_id]
        path = expand_path(spec.local_path, base_dir=asset_base)
        return (
            f'<div {qid} style="{pos}">'
            f'<img src="{_data_uri(path)}" alt="{html.escape(spec.alt_text)}" '
            f'style="width:100%;height:100%;object-fit:contain;"/></div>'
        )
    if el.kind is DocElementKind.SVG:
        return f'<div {qid} style="{pos}">{el.svg}</div>'
    if el.kind is DocElementKind.DIAGRAM:
        svg = _diagram_svg(el.diagram, el.bbox.w * CANVAS_W, el.bbox.h * CANVAS_H, palette["primary"], palette["ink"])
        return f'<div {qid} style="{pos}">{svg}</div>'
    raise ValueError(f"element '{el.id}': no renderer for kind '{el.kind.value}'")


def render_document_html(
    document: DeckDocument,
    *,
    asset_base: Path,
    theme_template: Path | None = None,
    title: str | None = None,
) -> str:
    """One self-contained HTML page: each slide a 16:9 canvas in house chrome."""
    theme = _load_theme(theme_template)
    palette = theme["palette"]
    band = theme.get("chrome", {}).get("header_band", {})
    assets_by_id = {a.id: a for a in document.assets}
    slides_html: list[str] = []
    for slide in document.slides:
        recipe = slide.intent.recipe if slide.intent else None
        # Cover/statement recipes are banner-free (hero composition); everything
        # else gets the house header band for 5-20ft title/body separation.
        banded = recipe not in {"cover-brand", "statement-thesis"}
        band_html = ""
        elements = slide.elements
        if banded:
            title_el = next((e for e in elements if e.role == "title"), None)
            band_html = (
                f'<div style="position:absolute;left:0;top:0;width:100%;height:8.5%;'
                f'background:{band.get("fill", palette["primary"])};display:flex;align-items:center;">'
                f'<span style="color:{band.get("title_color", "#FFFFFF")};font-family:'
                f'{theme["theme_tokens"]["heading_font"]}, sans-serif;font-size:38px;font-weight:bold;'
                f'padding-left:2.5%;">{html.escape(title_el.text if title_el else "")}</span></div>'
            )
            elements = [e for e in elements if e.role != "title"]
        body = "".join(_element_html(e, assets_by_id, asset_base, theme) for e in sorted(elements, key=lambda e: e.z))
        footer_rule = (
            f'<div style="position:absolute;left:0;bottom:0;width:100%;height:0.6%;background:{palette["primary"]};"></div>'
        )
        slides_html.append(
            f'<section data-qid="doc:slide:{html.escape(slide.id)}" style="position:relative;'
            f"width:{CANVAS_W}px;height:{CANVAS_H}px;background:{palette['canvas']};"
            f'overflow:hidden;margin:24px auto;box-shadow:0 4px 24px rgba(0,0,0,0.25);">'
            f"{band_html}{body}{footer_rule}</section>"
        )
    page_title = html.escape(title or document.deck.title)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{page_title}</title>"
        "<style>body{margin:0;background:#1a1a1e;}</style></head><body>"
        + "".join(slides_html)
        + "</body></html>"
    )
