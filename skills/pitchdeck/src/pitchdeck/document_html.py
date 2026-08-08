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

from .document import DeckDocument, DiagramGraph, DocElement, DocElementKind, LineSpec, RichTextSpec
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


def _icon_glyph_svg(icon_id: str, x: float, y: float, size: float, tint: str) -> str:
    """Inline a library glyph (already sanitized + hash-verified) at position."""
    try:
        from .icons import load_manifest

        entry = load_manifest().get(icon_id)
    except Exception:
        entry = None
    if entry is None:
        return (f'<circle cx="{x + size / 2:.0f}" cy="{y + size / 2:.0f}" r="{size / 2:.0f}" '
                f'fill="none" stroke="{tint}" stroke-width="2.5"/>')
    inner = entry["svg"].replace("#000", tint)
    inner = inner.replace("<svg ", f'<svg x="{x:.0f}" y="{y:.0f}" width="{size:.0f}" height="{size:.0f}" ', 1)
    return inner


_ROLE_CYCLE = ["#065E7C", "#6F8E30", "#26558E", "#D39500", "#065E7C"]


def _diagram_svg(graph: DiagramGraph, width: float, height: float, primary: str, ink: str) -> str:
    """Nodes, connectors, and labels as separate SVG shapes (editability contract)."""
    parts: list[str] = [
        f'<svg viewBox="0 0 {width:.0f} {height:.0f}" width="100%" height="100%" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="Calibri, sans-serif">'
    ]
    centers: dict[str, tuple[float, float, float, float]] = {}
    unboxed = graph.recipe == "pipeline"  # visual review: unboxed line-art path, differentiated actors
    for n_index, node in enumerate(graph.nodes):
        x, y = node.bbox.x * width, node.bbox.y * height
        w, h = node.bbox.w * width, node.bbox.h * height
        centers[node.id] = (x + w / 2, y + h * (0.28 if unboxed else 0.5), w, h)
        accent = _ROLE_CYCLE[n_index % len(_ROLE_CYCLE)] if unboxed else primary
        terminal = unboxed and n_index == len(graph.nodes) - 1
        # asymmetry (corpus: hand-arranged, never uniform): terminal node
        # emphasized, interior nodes alternate scale.
        _scale = (1.22 if (unboxed and n_index == len(graph.nodes) - 1) else (1.0 if n_index % 2 == 0 else 0.86))
        icon_size = min(w, h) * ((0.40 if unboxed else 0.34) * _scale)
        parts.append(
            f'<g id="node-{html.escape(node.id)}">'
            + (
                ""
                if unboxed
                else f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" rx="10" '
                     f'fill="none" stroke="{primary}" stroke-width="3"/>'
            )
            + (
                f'<circle cx="{x + w / 2:.0f}" cy="{y + h * 0.28:.0f}" r="{icon_size * 0.72:.0f}" '
                f'fill="none" stroke="{accent}" stroke-width="{4 if terminal else 2.5}"/>'
                if unboxed
                else ""
            )
            + (
                _icon_glyph_svg(node.icon, x + w / 2 - icon_size / 2, y + h * (0.28 if unboxed else 0.32) - icon_size / 2, icon_size, accent)
                if node.icon
                else ""
            )
            + f'<text x="{x + w / 2:.0f}" y="{y + h * (0.80 if unboxed else 0.68):.0f}" text-anchor="middle" '
            f'font-size="{max(14, h * 0.14):.0f}" font-weight="bold" fill="{primary}">{html.escape(node.label)}</text>'
            + (
                f'<text x="{x + w / 2:.0f}" y="{y + h * (0.95 if unboxed else 0.84):.0f}" text-anchor="middle" '
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
        if unboxed and edge.line_style == "solid":
            dash = ' stroke-dasharray="2 7" stroke-linecap="round"'  # corpus: dotted meander arrows
        arrow = ' marker-end="url(#arrow)"' if edge.arrowhead else ""
        parts.append(
            f'<g id="edge-{html.escape(edge.id)}">'
            + (f'<path d="M {x1:.0f} {sy:.0f} Q {(x1 + x2) / 2:.0f} {sy - 14:.0f} {x2:.0f} {ty:.0f}" fill="none" '
             f'stroke="{primary}" stroke-width="3"{dash}{arrow}/>' if unboxed else
             f'<line x1="{x1:.0f}" y1="{sy:.0f}" x2="{x2:.0f}" y2="{ty:.0f}" '
             f'stroke="{primary}" stroke-width="3"{dash}{arrow}/>')
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
        rotate = f"transform:rotate({el.rotation_deg}deg);" if el.rotation_deg else ""
        return (
            f'<div {qid} style="{pos}{rotate}">'
            f'<img src="{_data_uri(path)}" alt="{html.escape(spec.alt_text)}" '
            f'style="width:100%;height:100%;object-fit:contain;"/></div>'
        )
    if el.kind is DocElementKind.SVG:
        return f'<div {qid} style="{pos}">{el.svg}</div>'
    if el.kind is DocElementKind.DIAGRAM:
        svg = _diagram_svg(el.diagram, el.bbox.w * CANVAS_W, el.bbox.h * CANVAS_H, palette["primary"], palette["ink"])
        return f'<div {qid} style="{pos}">{svg}</div>'
    if el.kind is DocElementKind.GROUP:
        # Children live in the group's UNROTATED local frame; a padded
        # child_frame maps children into the inner region (chOff/chExt).
        rotate = f"transform:rotate({el.rotation_deg}deg);" if el.rotation_deg else ""
        frame = el.child_frame
        inner_pos = (
            f"position:absolute;left:{frame.x * 100:.2f}%;top:{frame.y * 100:.2f}%;"
            f"width:{frame.w * 100:.2f}%;height:{frame.h * 100:.2f}%;"
            if frame
            else "position:absolute;inset:0;"
        )
        children_sorted = sorted(enumerate(el.children or []), key=lambda pair: (pair[1].z, pair[0]))
        body = "".join(_element_html(child, assets_by_id, asset_base, theme) for _, child in children_sorted)
        return (
            f'<div {qid} style="{pos}{rotate}">'
            f'<div style="{inner_pos}">{body}</div></div>'
        )
    if el.kind is DocElementKind.SHAPE:
        spec = el.shape
        fill = palette.get(spec.fill_role, "none") if spec.fill_role else "none"
        stroke = palette.get(spec.stroke.role, palette["primary"]) if spec.stroke else "none"
        stroke_w = spec.stroke.width_pt if spec.stroke else 0
        dash = {"solid": "", "dashed": "8 6", "dotted": "2 5"}[spec.stroke.dash] if spec.stroke else ""
        rotate = f"transform:rotate({el.rotation_deg}deg);" if el.rotation_deg else ""
        shapes = {
            "rect": '<rect x="1" y="1" width="98" height="98"/>',
            "rounded_rect": '<rect x="1" y="1" width="98" height="98" rx="12"/>',
            "ellipse": '<ellipse cx="50" cy="50" rx="49" ry="49"/>',
            "pill": '<rect x="1" y="20" width="98" height="60" rx="30"/>',
            "chevron": '<polygon points="1,1 75,1 99,50 75,99 1,99 25,50"/>',
            "triangle": '<polygon points="50,2 98,98 2,98"/>',
        }
        body = shapes[spec.preset.value].replace(
            "/>", f' fill="{fill}" stroke="{stroke}" stroke-width="{stroke_w}"'
            + (f' stroke-dasharray="{dash}"' if dash else "") + ' vector-effect="non-scaling-stroke"/>'
        )
        return (
            f'<div {qid} style="{pos}{rotate}">'
            f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" width="100%" height="100%" '
            f'xmlns="http://www.w3.org/2000/svg">{body}</svg></div>'
        )
    if el.kind is DocElementKind.LINE:
        return _line_html(el, el.line, palette, qid)
    if el.kind is DocElementKind.ICON:
        from .icons import resolve_icon

        resolved = resolve_icon(el.icon.library_id, require_editable=False)
        tint = palette.get(el.icon.tint_role, palette["primary"])
        if el.role == "badge":
            # metaphor badge: white circled glyph inside the band
            svg = resolved["svg"].replace("#000", tint).replace("stroke='#000'", f"stroke='{tint}'")
            svg = svg.replace("<svg ", '<svg width="62%" height="62%" style="position:absolute;left:19%;top:19%" ', 1)
            return (
                f'<div {qid} data-icon="{html.escape(el.icon.library_id)}" style="{pos}">'
                f'<div style="position:relative;width:100%;height:100%;border:2.5px solid {tint};'
                f'border-radius:50%;box-sizing:border-box;">{svg}</div></div>'
            )
        svg = resolved["svg"].replace("#000", tint).replace("stroke='#000'", f"stroke='{tint}'")
        svg = svg.replace("<svg ", '<svg width="100%" height="100%" ', 1)
        return f'<div {qid} data-icon="{html.escape(el.icon.library_id)}" style="{pos}">{svg}</div>'
    if el.kind is DocElementKind.RICH_TEXT:
        return _rich_text_html(el, el.rich_text, palette, theme, qid, pos)
    raise ValueError(f"element '{el.id}': no renderer for kind '{el.kind.value}'")


def _line_html(el: DocElement, spec: LineSpec, palette: dict, qid: str) -> str:
    """Full-canvas SVG overlay positioned at the element bbox; endpoints are
    canonical parent-frame fractions mapped into the local viewBox."""
    color = palette["primary"]
    x0, y0 = el.bbox.x, el.bbox.y
    w, h = max(el.bbox.w, 1e-6), max(el.bbox.h, 1e-6)
    sx = (spec.start.x - x0) / w * 100
    sy = (spec.start.y - y0) / h * 100
    ex = (spec.end.x - x0) / w * 100
    ey = (spec.end.y - y0) / h * 100
    dash = {"solid": "", "dashed": ' stroke-dasharray="8 6"', "dotted": ' stroke-dasharray="2 5"'}[spec.dash]
    marker_defs = (
        f'<defs><marker id="ah-{el.id}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        f'orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="{color}"/></marker></defs>'
    )
    markers = (' marker-end="url(#ah-%s)"' % el.id if spec.arrow_end else "") + (
        ' marker-start="url(#ah-%s)"' % el.id if spec.arrow_start else ""
    )
    if spec.route == "bent":
        mid = f"{sx:.1f},{ey:.1f}"
        path = f'<polyline points="{sx:.1f},{sy:.1f} {mid} {ex:.1f},{ey:.1f}" fill="none"'
    elif spec.route == "curved":
        path = f'<path d="M {sx:.1f} {sy:.1f} Q {(sx+ex)/2:.1f} {sy:.1f} {ex:.1f} {ey:.1f}" fill="none"'
    else:
        path = f'<line x1="{sx:.1f}" y1="{sy:.1f}" x2="{ex:.1f}" y2="{ey:.1f}"'
    pos = (
        f"position:absolute;left:{x0 * 100:.2f}%;top:{y0 * 100:.2f}%;"
        f"width:{el.bbox.w * 100:.2f}%;height:{el.bbox.h * 100:.2f}%;z-index:{el.z};overflow:visible;"
    )
    return (
        f'<div {qid} style="{pos}">'
        f'<svg viewBox="0 0 100 100" preserveAspectRatio="none" width="100%" height="100%" style="overflow:visible" '
        f'xmlns="http://www.w3.org/2000/svg">{marker_defs}'
        f'{path} stroke="{color}" stroke-width="{spec.width_pt / 2:.1f}"{dash}{markers} vector-effect="non-scaling-stroke"/></svg></div>'
    )


def _rich_text_html(el: DocElement, spec: RichTextSpec, palette: dict, theme: dict, qid: str, pos: str) -> str:
    scale = theme.get("type_scale_pt", {"body": 20, "support": 16})
    blocks_html = []
    for block in spec.blocks:
        size = scale.get(block.style_role.value, 20) if isinstance(scale, dict) else 20
        runs_html = []
        for run in block.runs:
            css, tag_open, tag_close = [], "", ""
            for mark in run.marks:
                if mark.type == "bold":
                    css.append("font-weight:bold")
                elif mark.type == "italic":
                    css.append("font-style:italic")
                elif mark.type == "underline":
                    css.append("text-decoration:underline")
                elif mark.type == "code":
                    css.append("font-family:Consolas,monospace;background:rgba(0,0,0,0.06);padding:0 3px;border-radius:3px")
                elif mark.type == "color":
                    css.append(f"color:{palette.get(mark.role, palette['ink'])}")
                elif mark.type == "link":
                    tag_open = f'<a href="#doc:slide:{html.escape(mark.target_slide_id)}" style="color:{palette["primary"]};">'
                    tag_close = "</a>"
            runs_html.append(f'{tag_open}<span style="{";".join(css)}">{html.escape(run.text)}</span>{tag_close}')
        bullet = f'<span style="color:{palette["primary"]};margin-right:6px;">&gt;</span>' if block.bullet_level else ""
        blocks_html.append(
            f'<p style="margin:0 0 6px;font-size:{size * 1.6:.0f}px;text-align:{block.align};line-height:1.3;">{bullet}{"".join(runs_html)}</p>'
        )
    ink = palette["ink"]
    return f'<div {qid} style="{pos}color:{ink};font-family:{theme["theme_tokens"]["body_font"]}, sans-serif;">{"".join(blocks_html)}</div>'



def render_document_html(
    document: DeckDocument,
    *,
    asset_base: Path,
    theme_template: Path | None = None,
    title: str | None = None,
    preview: bool = False,
) -> str:
    """One self-contained HTML page: each slide a 16:9 canvas in house chrome."""
    from .publish_gate import assert_publishable

    assert_publishable(document, allow_preview=preview)
    theme = _load_theme(theme_template)
    palette = theme["palette"]
    band = theme.get("chrome", {}).get("header_band", {})
    assets_by_id = {a.id: a for a in document.assets}
    slides_html: list[str] = []
    for slide in document.slides:
        recipe = slide.intent.recipe if slide.intent else None
        # Corpus correction (render-oracle 2026-08-07): every intent slide is
        # banded; hero recipes carry the deck kicker in the band and keep the
        # assertion as hero body (reqml-12 pattern).
        hero = recipe in {"cover-brand", "statement-thesis"}
        banded = slide.intent is not None
        band_html = ""
        elements = slide.elements
        if banded:
            title_el = next((e for e in elements if e.role == "title"), None)
            is_cover = recipe == "cover-brand"
            tagline = document.deck.title.split("—")[-1].strip().upper() if "—" in document.deck.title else ""
            band_text = ((tagline if is_cover else document.deck.title.split("—")[0].strip().upper()) if hero else (title_el.text if title_el else ""))
            band_html = (
                f'<div style="position:absolute;left:0;top:0;width:100%;height:10%;'
                f'background:{band.get("fill", palette["primary"])};display:flex;align-items:center;">'
                f'<span style="color:{band.get("title_color", "#FFFFFF")};font-family:'
                f'{theme["theme_tokens"]["heading_font"]}, sans-serif;'
                f'font-size:{38 if len(band_text) <= 58 else 32}px;font-weight:bold;'
                f'padding-left:2.5%;padding-right:9%;">{html.escape(band_text)}</span></div>'
            )
            if not hero:
                elements = [e for e in elements if e.role != "title"]
        body = "".join(_element_html(e, assets_by_id, asset_base, theme) for e in sorted(elements, key=lambda e: e.z))
        footer_rule = (
            f'<div style="position:absolute;left:0;bottom:0;width:100%;height:0.6%;background:{palette["primary"]};"></div>'
        )
        slides_html.append(
            f'<section data-qid="doc:slide:{html.escape(slide.id)}" style="position:relative;'
            f"width:{CANVAS_W}px;height:{CANVAS_H}px;background:{palette['canvas']};"
            f'overflow:hidden;margin:24px auto;box-shadow:0 4px 24px rgba(0,0,0,0.25);">'
            f"{band_html}{body}{footer_rule}"
            f'<span style="position:absolute;right:1.2%;bottom:1.2%;font:16px Calibri,sans-serif;color:#8a8a8a;">{slide.order}</span></section>'
        )
    page_title = html.escape(title or document.deck.title)
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{page_title}</title>"
        "<style>body{margin:0;background:#1a1a1e;}</style></head><body>"
        + "".join(slides_html)
        + "</body></html>"
    )
