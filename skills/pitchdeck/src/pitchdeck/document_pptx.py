"""Native-editable PPTX emitter for deck_document.v1 primitives (#1271 phase 3).

Renders the scene graph as REAL PowerPoint objects — nested grpSp, preset sp,
freeform sp, cxnSp connectors, text runs, and pic — never a raster. Group
strategy (validated live against python-pptx 1.x): children are placed at
absolute canvas EMU inside the group (python-pptx recalculates the group's
off/ext/chOff/chExt from them), then the group xfrm is overridden to the
AUTHORED bbox with chOff/chExt pinned identical to off/ext. That identity
mapping means no rescaling ever occurs and a padded child_frame survives as
literal geometry (margin inside the group) rather than being swallowed by
extent recalculation.

Capability decisions are receipts, not silences: connector attach hints are
NOT written as stCxn/endCxn (python-pptx support is experimental); local
links render as link-styled runs without a jump action. Icons resolve
fail-closed via the hash-pinned library (editable shape trees required).
Every emitted object is named ``el:<element-id>`` so reimport can prove
identity. Failure modes: unknown kinds, unresolvable icons, or assets that
cannot be read raise — nothing emits partially.
"""

from __future__ import annotations

import json
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.util import Emu, Inches, Pt

from .document import DeckDocument, DocElement, DocElementKind
from .document_html import _load_theme
from .io import expand_path

SLIDE_W_IN, SLIDE_H_IN = 13.333, 7.5

_PRESETS = {
    "rect": MSO_SHAPE.RECTANGLE,
    "rounded_rect": MSO_SHAPE.ROUNDED_RECTANGLE,
    "ellipse": MSO_SHAPE.OVAL,
    "chevron": MSO_SHAPE.CHEVRON,
    "pill": MSO_SHAPE.ROUNDED_RECTANGLE,  # adjustment 0.5 -> capsule
    "triangle": MSO_SHAPE.ISOSCELES_TRIANGLE,
}

_CONNECTOR_ROUTES = {
    "straight": MSO_CONNECTOR.STRAIGHT,
    "bent": MSO_CONNECTOR.ELBOW,
    "curved": MSO_CONNECTOR.CURVE,
}

_A = "http://schemas.openxmlformats.org/drawingml/2006/main"


class Frame:
    """Absolute inches context: local fractions map into this rectangle."""

    def __init__(self, x: float, y: float, w: float, h: float):
        self.x, self.y, self.w, self.h = x, y, w, h

    def rect(self, bbox) -> tuple:
        return (
            Inches(self.x + bbox.x * self.w),
            Inches(self.y + bbox.y * self.h),
            Inches(bbox.w * self.w),
            Inches(bbox.h * self.h),
        )

    def point(self, x: float, y: float) -> tuple:
        return Inches(self.x + x * self.w), Inches(self.y + y * self.h)

    def sub(self, bbox, child_frame=None) -> "Frame":
        base = Frame(self.x + bbox.x * self.w, self.y + bbox.y * self.h, bbox.w * self.w, bbox.h * self.h)
        if child_frame is None:
            return base
        return Frame(
            base.x + child_frame.x * base.w,
            base.y + child_frame.y * base.h,
            child_frame.w * base.w,
            child_frame.h * base.h,
        )


def _hex(value: str) -> RGBColor:
    return RGBColor.from_string(value.lstrip("#").upper())


def _set_dash(line, dash: str) -> None:
    if dash == "solid":
        return
    from pptx.enum.dml import MSO_LINE_DASH_STYLE

    line.dash_style = MSO_LINE_DASH_STYLE.DASH if dash == "dashed" else MSO_LINE_DASH_STYLE.ROUND_DOT


def _add_arrowheads(connector, *, start: bool, end: bool) -> None:
    ln = connector.line._get_or_add_ln()
    for present, tag in ((start, "headEnd"), (end, "tailEnd")):
        if present:
            el = ln.makeelement(f"{{{_A}}}{tag}", {"type": "triangle", "w": "med", "len": "med"})
            ln.append(el)


def _pin_group_xfrm(group, bbox_rect: tuple) -> None:
    """Override off/ext AND chOff/chExt to the authored bbox (identity map):
    padding inside the group survives as literal geometry."""
    left, top, width, height = (int(v) for v in bbox_rect)
    xfrm = group._element.find(f".//{{{_A}}}xfrm")
    for tag, attrs in (
        ("off", {"x": str(left), "y": str(top)}),
        ("ext", {"cx": str(width), "cy": str(height)}),
        ("chOff", {"x": str(left), "y": str(top)}),
        ("chExt", {"cx": str(width), "cy": str(height)}),
    ):
        node = xfrm.find(f"{{{_A}}}{tag}")
        for key, value in attrs.items():
            node.set(key, value)


def _emit_icon(container, element: DocElement, frame: Frame, palette: dict, receipt: dict) -> None:
    from .icons import resolve_icon

    resolved = resolve_icon(element.icon.library_id, require_editable=True)
    tint = _hex(palette.get(element.icon.tint_role, palette["primary"]))
    group = container.add_group_shape()
    icon_frame = frame.sub(element.bbox)
    for index, part in enumerate(resolved["mapping"]["parts"]):
        if part["kind"] == "preset":
            x, y, w, h = part["bbox"]
            shape = group.shapes.add_shape(
                _PRESETS[part["preset"]],
                Inches(icon_frame.x + x * icon_frame.w), Inches(icon_frame.y + y * icon_frame.h),
                Inches(w * icon_frame.w), Inches(h * icon_frame.h),
            )
            shape.fill.background()
            shape.line.color.rgb = tint
            shape.line.width = Pt(2.5)
            shape.name = f"el:{element.id}:part{index}"
        else:  # straight-segment freeform
            vertices = [(Emu(Inches(icon_frame.x + vx * icon_frame.w)), Emu(Inches(icon_frame.y + vy * icon_frame.h))) for vx, vy in part["vertices"]]
            builder = group.shapes.build_freeform(vertices[0][0], vertices[0][1], scale=1)
            builder.add_line_segments(vertices[1:], close=part.get("closed", False))
            shape = builder.convert_to_shape()
            shape.fill.background()
            shape.line.color.rgb = tint
            shape.line.width = Pt(2.5)
            shape.name = f"el:{element.id}:part{index}"
    _pin_group_xfrm(group, frame.rect(element.bbox))
    group.name = f"el:{element.id}"
    receipt["icons"].append({
        "element": element.id,
        "library_id": element.icon.library_id,
        "representation": resolved["representation"],
        "svg_sha256": resolved["svg_sha256"],
    })


def _emit_rich_text(container, element: DocElement, frame: Frame, palette: dict, scale: dict, receipt: dict) -> None:
    left, top, width, height = frame.rect(element.bbox)
    box = container.add_textbox(left, top, width, height)
    box.name = f"el:{element.id}"
    tf = box.text_frame
    tf.word_wrap = True
    for b_index, block in enumerate(element.rich_text.blocks):
        paragraph = tf.paragraphs[0] if b_index == 0 else tf.add_paragraph()
        if block.bullet_level:
            paragraph.level = block.bullet_level - 1
        for run_spec in block.runs:
            run = paragraph.add_run()
            run.text = run_spec.text
            run.font.size = Pt(scale.get(block.style_role.value, 20))
            for mark in run_spec.marks:
                if mark.type == "bold":
                    run.font.bold = True
                elif mark.type == "italic":
                    run.font.italic = True
                elif mark.type == "underline":
                    run.font.underline = True
                elif mark.type == "code":
                    run.font.name = "Consolas"
                elif mark.type == "color":
                    run.font.color.rgb = _hex(palette.get(mark.role, palette["ink"]))
                elif mark.type == "link":
                    run.font.color.rgb = _hex(palette["primary"])
                    run.font.underline = True
                    receipt["capability_decisions"].append(
                        f"{element.id}: local link to '{mark.target_slide_id}' rendered as styled run (no jump action)"
                    )


def _emit_element(container, element: DocElement, frame: Frame, *, palette: dict, scale: dict, assets: dict, asset_base: Path, receipt: dict) -> None:
    kind = element.kind
    if kind is DocElementKind.GROUP:
        group = container.add_group_shape()
        inner = frame.sub(element.bbox, element.child_frame)
        ordered = sorted(enumerate(element.children or []), key=lambda pair: (pair[1].z, pair[0]))
        for _, child in ordered:
            _emit_element(group.shapes, child, inner, palette=palette, scale=scale, assets=assets, asset_base=asset_base, receipt=receipt)
        _pin_group_xfrm(group, frame.rect(element.bbox))
        if element.rotation_deg:
            group.rotation = element.rotation_deg
        group.name = f"el:{element.id}"
        return
    if kind is DocElementKind.SHAPE:
        left, top, width, height = frame.rect(element.bbox)
        shape = container.add_shape(_PRESETS[element.shape.preset.value], left, top, width, height)
        if element.shape.preset.value == "pill":
            shape.adjustments[0] = 0.5
        if element.shape.fill_role:
            shape.fill.solid()
            shape.fill.fore_color.rgb = _hex(palette.get(element.shape.fill_role, "#FFFFFF"))
        else:
            shape.fill.background()
        if element.shape.stroke:
            shape.line.color.rgb = _hex(palette.get(element.shape.stroke.role, palette["primary"]))
            shape.line.width = Pt(element.shape.stroke.width_pt)
            _set_dash(shape.line, element.shape.stroke.dash)
        else:
            shape.line.fill.background()
        if element.rotation_deg:
            shape.rotation = element.rotation_deg
        shape.name = f"el:{element.id}"
        return
    if kind is DocElementKind.LINE:
        spec = element.line
        bx, by = frame.point(spec.start.x, spec.start.y)
        ex, ey = frame.point(spec.end.x, spec.end.y)
        connector = container.add_connector(_CONNECTOR_ROUTES[spec.route], bx, by, ex, ey)
        connector.line.color.rgb = _hex(palette["primary"])
        connector.line.width = Pt(spec.width_pt)
        _set_dash(connector.line, spec.dash)
        _add_arrowheads(connector, start=spec.arrow_start, end=spec.arrow_end)
        if spec.start_hint or spec.end_hint:
            receipt["capability_decisions"].append(
                f"{element.id}: attach hints present but stCxn/endCxn NOT written (python-pptx support experimental); geometry authoritative"
            )
        connector.name = f"el:{element.id}"
        return
    if kind is DocElementKind.ICON:
        _emit_icon(container, element, frame, palette, receipt)
        return
    if kind is DocElementKind.RICH_TEXT:
        _emit_rich_text(container, element, frame, palette, scale, receipt)
        return
    if kind is DocElementKind.TEXT:
        left, top, width, height = frame.rect(element.bbox)
        box = container.add_textbox(left, top, width, height)
        box.name = f"el:{element.id}"
        tf = box.text_frame
        tf.word_wrap = True
        run = tf.paragraphs[0].add_run()
        run.text = element.text or ""
        style = element.style
        run.font.size = Pt(style.size_pt if style else 20)
        run.font.bold = bool(style and style.bold)
        if style and style.color:
            run.font.color.rgb = _hex(style.color)
        return
    if kind is DocElementKind.IMAGE:
        spec = assets[element.asset_id]
        path = expand_path(spec.local_path, base_dir=asset_base)
        left, top, width, height = frame.rect(element.bbox)
        source: object = str(path)
        if path.suffix.lower() in {".webp", ".avif"}:
            # python-pptx accepts BMP/GIF/JPEG/PNG/TIFF/WMF; convert losslessly.
            import io

            from PIL import Image

            buffer = io.BytesIO()
            Image.open(path).convert("RGB").save(buffer, format="PNG")
            buffer.seek(0)
            source = buffer
        picture = container.add_picture(source, left, top, width=width, height=height)
        if element.rotation_deg:
            picture.rotation = element.rotation_deg
        picture.name = f"el:{element.id}"
        return
    if kind is DocElementKind.DIAGRAM:
        _emit_diagram(container, element, frame, palette=palette, receipt=receipt)
        return
    raise ValueError(f"element '{element.id}': PPTX emitter has no handler for kind '{kind.value}'")


def _emit_diagram(container, element: DocElement, frame: Frame, *, palette: dict, receipt: dict) -> None:
    """DiagramGraph compiles to the SAME primitive contract (#1271 review):
    a native group of rounded-rect nodes, icon circles, label textboxes, and
    cxnSp connectors — separately editable, never one raster."""
    graph = element.diagram
    primary = _hex(palette["primary"])
    ink = _hex(palette["ink"])
    group = container.add_group_shape()
    dframe = frame.sub(element.bbox)
    centers: dict[str, tuple[float, float, float, float]] = {}
    for node in graph.nodes:
        nx = dframe.x + node.bbox.x * dframe.w
        ny = dframe.y + node.bbox.y * dframe.h
        nw = node.bbox.w * dframe.w
        nh = node.bbox.h * dframe.h
        centers[node.id] = (nx, ny, nw, nh)
        box = group.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(nx), Inches(ny), Inches(nw), Inches(nh))
        box.fill.background()
        box.line.color.rgb = primary
        box.line.width = Pt(2.5)
        box.name = f"el:{element.id}:node:{node.id}"
        if node.icon:
            radius = min(nw, nh) * 0.16
            icon_circle = group.shapes.add_shape(
                MSO_SHAPE.OVAL,
                Inches(nx + nw / 2 - radius), Inches(ny + nh * 0.32 - radius),
                Inches(radius * 2), Inches(radius * 2),
            )
            icon_circle.fill.background()
            icon_circle.line.color.rgb = primary
            icon_circle.name = f"el:{element.id}:node:{node.id}:icon"
        label = group.shapes.add_textbox(Inches(nx), Inches(ny + nh * 0.52), Inches(nw), Inches(nh * 0.44))
        label.name = f"el:{element.id}:node:{node.id}:label"
        tf = label.text_frame
        tf.word_wrap = True
        run = tf.paragraphs[0].add_run()
        run.text = node.label
        run.font.bold = True
        run.font.size = Pt(14)
        run.font.color.rgb = primary
        from pptx.enum.text import PP_ALIGN

        tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        if node.sublabel:
            para = tf.add_paragraph()
            para.alignment = PP_ALIGN.CENTER
            sub = para.add_run()
            sub.text = node.sublabel
            sub.font.size = Pt(10)
            sub.font.color.rgb = ink
    for edge in graph.edges:
        sx, sy, sw, sh = centers[edge.source]
        tx, ty, tw, th = centers[edge.target]
        begin = (Inches(sx + sw), Inches(sy + sh / 2))
        end = (Inches(tx), Inches(ty + th / 2))
        route = MSO_CONNECTOR.ELBOW if edge.route == "curve" else MSO_CONNECTOR.STRAIGHT
        connector = group.shapes.add_connector(route, begin[0], begin[1], end[0], end[1])
        connector.line.color.rgb = primary
        connector.line.width = Pt(2.5)
        _set_dash(connector.line, "dashed" if edge.line_style == "dashed" else ("dotted" if edge.line_style == "dotted" else "solid"))
        _add_arrowheads(connector, start=False, end=edge.arrowhead)
        connector.name = f"el:{element.id}:edge:{edge.id}"
        if edge.label:
            mid_x = (sx + sw + tx) / 2
            mid_y = (sy + sh / 2 + ty + th / 2) / 2
            caption = group.shapes.add_textbox(Inches(mid_x - 1.2), Inches(mid_y - 0.42), Inches(2.4), Inches(0.32))
            caption.name = f"el:{element.id}:edge:{edge.id}:label"
            run = caption.text_frame.paragraphs[0].add_run()
            run.text = edge.label
            run.font.italic = True
            run.font.size = Pt(11)
            run.font.color.rgb = ink
    _pin_group_xfrm(group, frame.rect(element.bbox))
    group.name = f"el:{element.id}"


def emit_document_pptx(
    document: DeckDocument,
    output_path: Path,
    *,
    asset_base: Path,
    theme_template: Path | None = None,
) -> dict:
    from .publish_gate import assert_publishable

    assert_publishable(document)
    theme = _load_theme(theme_template)
    palette = theme["palette"]
    scale = theme.get("type_scale_pt", {"body": 20, "support": 16, "title": 28})
    assets = {a.id: a for a in document.assets}
    presentation = Presentation()
    presentation.slide_width = Inches(SLIDE_W_IN)
    presentation.slide_height = Inches(SLIDE_H_IN)
    blank = presentation.slide_layouts[6]
    receipt: dict = {
        "schema": "pitchdeck.pptx_primitive_receipt.v1",
        "capability_decisions": [],
        "icons": [],
        "slides": [],
    }
    root = Frame(0.0, 0.0, SLIDE_W_IN, SLIDE_H_IN)
    band_cfg = theme.get("chrome", {}).get("header_band", {})
    for slide_doc in document.slides:
        if slide_doc.hidden:
            continue
        slide = presentation.slides.add_slide(blank)
        # House chrome parity with the HTML renderer (render-oracle finding
        # 2026-08-07: PPTX shipped without the band — cross-target drift):
        # banded recipes get the petrol band with the white title inside it,
        # plus the footer rule; hero recipes stay banner-free.
        # Corpus correction (render-oracle, 2026-08-07): EVERY slide carries the
        # band in the house style — hero recipes put the deck KICKER in the
        # band and keep the assertion as the hero body (reqml-12 pattern).
        hero = bool(slide_doc.intent) and slide_doc.intent.recipe in {"cover-brand", "statement-thesis"}
        banded = slide_doc.intent is not None
        skip_title = False
        if banded:
            band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(0), Inches(SLIDE_W_IN), Inches(SLIDE_H_IN * 0.10))
            band.fill.solid()
            band.fill.fore_color.rgb = _hex(band_cfg.get("fill", palette["primary"]))
            band.line.fill.background()
            band.name = "chrome:band"
            title_el = next((e for e in slide_doc.elements if e.role == "title"), None)
            band_text = (document.deck.title.split("—")[0].strip().upper() if hero else (title_el.text if title_el else ""))
            title_box = slide.shapes.add_textbox(Inches(0.33), Inches(0.07), Inches(SLIDE_W_IN - 0.66), Inches(SLIDE_H_IN * 0.10 - 0.1))
            title_box.name = "chrome:band-title" if hero else (f"el:{title_el.id}" if title_el else "chrome:band-title")
            run = title_box.text_frame.paragraphs[0].add_run()
            run.text = band_text or ""
            run.font.size = Pt(24)
            run.font.bold = True
            run.font.color.rgb = _hex(band_cfg.get("title_color", "#FFFFFF"))
            skip_title = not hero
        rule = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0), Inches(SLIDE_H_IN - 0.045), Inches(SLIDE_W_IN), Inches(0.045))
        rule.fill.solid()
        rule.fill.fore_color.rgb = _hex(palette["primary"])
        rule.line.fill.background()
        rule.name = "chrome:footer-rule"
        ordered = sorted(enumerate(slide_doc.elements), key=lambda pair: (pair[1].z, pair[0]))
        for _, element in ordered:
            if skip_title and element.role == "title":
                continue
            _emit_element(slide.shapes, element, root, palette=palette, scale=scale, assets=assets, asset_base=asset_base, receipt=receipt)
        receipt["slides"].append({"id": slide_doc.id, "elements": sum(1 for _ in __import__("pitchdeck.document", fromlist=["iter_tree"]).iter_tree(slide_doc.elements))})
    output_path.parent.mkdir(parents=True, exist_ok=True)
    presentation.save(str(output_path))
    receipt["output"] = str(output_path.resolve())
    (output_path.with_suffix(".receipt.json")).write_text(json.dumps(receipt, indent=1), encoding="utf-8")
    return receipt
