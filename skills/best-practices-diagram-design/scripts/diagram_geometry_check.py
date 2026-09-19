#!/usr/bin/env python3
"""Measured rendered-scene geometry gate for SVG diagrams.

Parses a RENDERED SVG (graphviz `dot -Tsvg` or mermaid svg output) into a
typed scene -- node shape bounding boxes, text bounding boxes (with owner),
and edge stroke polylines -- using stdlib `xml.etree.ElementTree` only, then
runs deterministic geometric rules over the MEASURED coordinates. This never
reads author claims (declared routing, declared label text); it reads what
graphviz/mermaid actually drew.

Supported input: graphviz `-Tsvg` output (`<g class="node">` / `<g
class="edge">` groups, `<title>` holding the node id / "a->b" edge id,
`<ellipse>`/`<polygon>` shapes, `<path>` edge strokes, `<text>` labels).
Mermaid SVG uses a different DOM shape and is not parsed by this module yet
-- `UNSUPPORTED_SVG_DIALECT` is emitted instead of a false pass.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from diagram_design_check import Verdict, Violation

SVG_NS = "{http://www.w3.org/2000/svg}"

# Rough monospace-ish average glyph width as a fraction of font-size; graphviz/mermaid
# both use proportional fonts, so this is a conservative (slightly generous) estimate
# used only to size a measured text bbox around the (already measured) anchor point.
# ponytail: heuristic glyph metric, replace with real font metrics if false negatives appear.
GLYPH_WIDTH_RATIO = 0.62
LINE_HEIGHT_RATIO = 1.25


Rect = tuple[float, float, float, float]  # x0, y0, x1, y1


def _rect_from_points(points: list[tuple[float, float]]) -> Rect:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _rects_overlap(a: Rect, b: Rect) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def _rect_contains(outer: Rect, inner: Rect) -> bool:
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def _rect_center(r: Rect) -> tuple[float, float]:
    return (r[0] + r[2]) / 2, (r[1] + r[3]) / 2


def _shrink(r: Rect, factor: float) -> Rect:
    """Shrink a rect toward its center by `factor` (0..1) of each half-dimension -- used
    for the diamond/ellipse *inscribed safe region*, which is smaller than the bbox."""
    cx, cy = _rect_center(r)
    hw = (r[2] - r[0]) / 2 * factor
    hh = (r[3] - r[1]) / 2 * factor
    return cx - hw, cy - hh, cx + hw, cy + hh


def _expand(r: Rect, pad: float) -> Rect:
    return r[0] - pad, r[1] - pad, r[2] + pad, r[3] + pad


def _seg_intersects_rect(p0: tuple[float, float], p1: tuple[float, float], rect: Rect, stroke_width: float) -> bool:
    """Segment-vs-AABB intersection (slab method), rect pre-expanded by half the stroke width."""
    r = _expand(rect, stroke_width / 2)
    x0, y0 = p0
    x1, y1 = p1
    tmin, tmax = 0.0, 1.0
    for lo, hi, d, o in ((r[0], r[2], x1 - x0, x0), (r[1], r[3], y1 - y0, y0)):
        if d == 0:
            if o < lo or o > hi:
                return False
            continue
        t0 = (lo - o) / d
        t1 = (hi - o) / d
        if t0 > t1:
            t0, t1 = t1, t0
        tmin = max(tmin, t0)
        tmax = min(tmax, t1)
        if tmin > tmax:
            return False
    return True


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?(?:e-?\d+)?")


def _path_points(d: str) -> list[tuple[float, float]]:
    """Extract all coordinate pairs from an SVG path `d` attribute as a polyline
    approximation. Good enough for intersection tests: graphviz bezier control
    points hug the actual curve closely."""
    nums = [float(n) for n in _NUM_RE.findall(d)]
    return [(nums[i], nums[i + 1]) for i in range(0, len(nums) - 1, 2)]


class SceneNode:
    def __init__(self, node_id: str, bbox: Rect, shape: str) -> None:
        self.id = node_id
        self.bbox = bbox
        self.shape = shape  # "ellipse" | "polygon" | "unknown"


class SceneText:
    def __init__(self, owner: str, owner_kind: str, string: str, bbox: Rect) -> None:
        self.owner = owner
        self.owner_kind = owner_kind  # "node" | "edge"
        self.string = string
        self.bbox = bbox


class SceneEdge:
    def __init__(self, edge_id: str, source: str, target: str, points: list[tuple[float, float]], stroke_width: float) -> None:
        self.id = edge_id
        self.source = source
        self.target = target
        self.points = points
        self.stroke_width = stroke_width


class Scene:
    def __init__(self) -> None:
        self.viewport: Rect | None = None
        self.nodes: list[SceneNode] = []
        self.texts: list[SceneText] = []
        self.edges: list[SceneEdge] = []


def _stroke_width(el: ET.Element) -> float:
    style = el.get("style", "") or ""
    m = re.search(r"stroke-width:\s*([\d.]+)", style)
    if m:
        return float(m.group(1))
    sw = el.get("stroke-width")
    return float(sw) if sw else 1.0


def _font_size(el: ET.Element) -> float:
    style = el.get("style", "") or ""
    m = re.search(r"font-size:\s*([\d.]+)", style)
    if m:
        return float(m.group(1))
    fs = el.get("font-size")
    return float(fs) if fs else 14.0


def parse_graphviz_svg(svg_text: str) -> Scene:
    scene = Scene()
    root = ET.fromstring(svg_text)

    # Graphviz places its drawing in a translated top-level graph group while
    # retaining negative Y coordinates in child geometry. Apply that measured
    # transform before comparing content with the SVG viewport.
    offset_x = offset_y = 0.0
    for candidate in root.iter(f"{SVG_NS}g"):
        if candidate.get("class") != "graph":
            continue
        transform = candidate.get("transform", "")
        match = re.search(r"translate\(\s*(-?[\d.]+)(?:[ ,]+)(-?[\d.]+)\s*\)", transform)
        if match:
            offset_x, offset_y = map(float, match.groups())
        break

    def shifted(rect: Rect) -> Rect:
        return rect[0] + offset_x, rect[1] + offset_y, rect[2] + offset_x, rect[3] + offset_y

    vb = root.get("viewBox")
    if vb:
        x, y, w, h = (float(v) for v in vb.split())
        scene.viewport = (x, y, x + w, y + h)
    else:
        w = root.get("width", "0").replace("pt", "").replace("px", "")
        h = root.get("height", "0").replace("pt", "").replace("px", "")
        try:
            scene.viewport = (0.0, 0.0, float(w), float(h))
        except ValueError:
            scene.viewport = None

    for g in root.iter(f"{SVG_NS}g"):
        cls = g.get("class", "")
        title_el = g.find(f"{SVG_NS}title")
        title = title_el.text.strip() if title_el is not None and title_el.text else ""

        if cls == "node":
            shape_el = g.find(f"{SVG_NS}ellipse")
            bbox: Rect | None = None
            shape = "unknown"
            if shape_el is not None:
                cx, cy = float(shape_el.get("cx", 0)), float(shape_el.get("cy", 0))
                rx, ry = float(shape_el.get("rx", 0)), float(shape_el.get("ry", 0))
                bbox = (cx - rx, cy - ry, cx + rx, cy + ry)
                shape = "ellipse"
            else:
                shape_el = g.find(f"{SVG_NS}polygon")
                if shape_el is not None:
                    pts_raw = shape_el.get("points", "")
                    pts = [tuple(map(float, p.split(","))) for p in pts_raw.split() if p]
                    if pts:
                        bbox = _rect_from_points(pts)
                        shape = "polygon"
            if bbox is None:
                continue
            node_id = title or f"node{len(scene.nodes)}"
            scene.nodes.append(SceneNode(node_id, shifted(bbox), shape))
            for text_el in g.findall(f"{SVG_NS}text"):
                text = _text_to_scene(text_el, node_id, "node")
                text.bbox = shifted(text.bbox)
                scene.texts.append(text)

        elif cls == "edge":
            path_el = g.find(f"{SVG_NS}path")
            points = _path_points(path_el.get("d", "")) if path_el is not None else []
            stroke_width = _stroke_width(path_el) if path_el is not None else 1.0
            source, _, target = title.partition("->")
            edge_id = title or f"edge{len(scene.edges)}"
            points = [(x + offset_x, y + offset_y) for x, y in points]
            scene.edges.append(SceneEdge(edge_id, source.strip(), target.strip(), points, stroke_width))
            for text_el in g.findall(f"{SVG_NS}text"):
                text = _text_to_scene(text_el, edge_id, "edge")
                text.bbox = shifted(text.bbox)
                scene.texts.append(text)

    return scene


def _text_to_scene(text_el: ET.Element, owner: str, owner_kind: str) -> SceneText:
    x = float(text_el.get("x", 0))
    y = float(text_el.get("y", 0))
    string = "".join(text_el.itertext())
    font_size = _font_size(text_el)
    width = max(len(string), 1) * font_size * GLYPH_WIDTH_RATIO
    height = font_size * LINE_HEIGHT_RATIO
    anchor = text_el.get("text-anchor", "middle")
    if anchor == "middle":
        x0 = x - width / 2
    elif anchor == "end":
        x0 = x - width
    else:
        x0 = x
    # y in SVG text is the baseline; approximate the box as spanning above it.
    y0 = y - height * 0.8
    return SceneText(owner, owner_kind, string, (x0, y0, x0 + width, y0 + height))


def check_scene(scene: Scene) -> Verdict:
    errors: list[Violation] = []
    warnings: list[Violation] = []

    # NODE_OVERLAP: unrelated node interiors overlap. Full containment (nested
    # container, e.g. C4 boxes) is exempt -- only partial overlap is a defect.
    for i, a in enumerate(scene.nodes):
        for b in scene.nodes[i + 1 :]:
            if not _rects_overlap(a.bbox, b.bbox):
                continue
            if _rect_contains(a.bbox, b.bbox) or _rect_contains(b.bbox, a.bbox):
                continue
            errors.append(Violation(code="NODE_OVERLAP", loc=f"nodes.{a.id},{b.id}", msg=f"rendered node '{a.id}' and '{b.id}' interiors overlap (not a containment relationship)", severity="error"))

    node_by_id = {n.id: n for n in scene.nodes}

    # TEXT_OUTSIDE_CONTAINER: label bbox must fit the shape's safe interior
    # (diamond/ellipse inscribed region is smaller than the raw bbox).
    for text in scene.texts:
        if text.owner_kind != "node":
            continue
        node = node_by_id.get(text.owner)
        if node is None:
            continue
        safe_factor = 0.72 if node.shape == "ellipse" else 0.92
        safe = _shrink(node.bbox, safe_factor)
        if not _rect_contains(safe, text.bbox):
            errors.append(Violation(code="TEXT_OUTSIDE_CONTAINER", loc=f"nodes.{node.id}", msg=f"label '{text.string}' bbox exceeds the safe interior of its {node.shape} shape (measured overflow)", severity="error"))

    # EDGE_TEXT_INTERSECTION: connector stroke crosses an unrelated text bbox.
    # A label sitting on its own edge is exempt.
    for edge in scene.edges:
        own_texts = {id(t) for t in scene.texts if t.owner_kind == "edge" and t.owner == edge.id}
        for text in scene.texts:
            if id(text) in own_texts:
                continue
            if text.owner_kind == "node" and text.owner in (edge.source, edge.target):
                continue  # label on the node the edge touches, not a crossing
            for p0, p1 in zip(edge.points, edge.points[1:]):
                if _seg_intersects_rect(p0, p1, text.bbox, edge.stroke_width):
                    errors.append(Violation(code="EDGE_TEXT_INTERSECTION", loc=f"edges.{edge.id}", msg=f"connector '{edge.id}' stroke crosses unrelated text '{text.string}' (owner: {text.owner})", severity="error"))
                    break
            else:
                continue
            break

    # EDGE_NODE_INTERSECTION: connector passes through an unrelated node interior.
    for edge in scene.edges:
        for node in scene.nodes:
            if node.id in (edge.source, edge.target):
                continue
            for p0, p1 in zip(edge.points, edge.points[1:]):
                if _seg_intersects_rect(p0, p1, node.bbox, edge.stroke_width):
                    errors.append(Violation(code="EDGE_NODE_INTERSECTION", loc=f"edges.{edge.id}", msg=f"connector '{edge.id}' passes through unrelated node '{node.id}'", severity="error"))
                    break
            else:
                continue
            break

    # CONTENT_CLIPPED: shapes/text beyond the SVG viewport.
    if scene.viewport is not None:
        for node in scene.nodes:
            if not _rect_contains(scene.viewport, node.bbox):
                errors.append(Violation(code="CONTENT_CLIPPED", loc=f"nodes.{node.id}", msg=f"node '{node.id}' bbox {node.bbox} exceeds the rendered viewport {scene.viewport}", severity="error"))
        for text in scene.texts:
            if not _rect_contains(scene.viewport, text.bbox):
                errors.append(Violation(code="CONTENT_CLIPPED", loc=f"text.{text.owner}", msg=f"text '{text.string}' bbox exceeds the rendered viewport", severity="error"))

    # ROUTING_NOT_REALIZED: advisory -- a >2-point path that is nonetheless visually
    # a straight line (all points collinear) didn't realize orthogonal/curved routing.
    for edge in scene.edges:
        if len(edge.points) < 3:
            continue
        if _approximately_collinear(edge.points):
            warnings.append(Violation(code="ROUTING_NOT_REALIZED", loc=f"edges.{edge.id}", msg=f"connector '{edge.id}' has {len(edge.points)} path points but renders as a straight line -- declared orthogonal/curved routing may not have been realized (advisory, hard to prove from geometry alone)", severity="warning"))

    return Verdict(ok=not errors, errors=errors, warnings=warnings)


def _approximately_collinear(points: list[tuple[float, float]], tol: float = 1.5) -> bool:
    x0, y0 = points[0]
    x1, y1 = points[-1]
    dx, dy = x1 - x0, y1 - y0
    length = (dx * dx + dy * dy) ** 0.5
    if length == 0:
        return True
    for x, y in points[1:-1]:
        # perpendicular distance from point to the line (x0,y0)-(x1,y1)
        dist = abs(dx * (y0 - y) - (x0 - x) * dy) / length
        if dist > tol:
            return False
    return True


def check_svg(svg_path: Path) -> Verdict:
    svg_text = svg_path.read_text(encoding="utf-8")
    if "graphviz" not in svg_text and "<!-- Generated by graphviz" not in svg_text and "class=\"node\"" not in svg_text:
        return Verdict(ok=False, errors=[Violation(code="UNSUPPORTED_SVG_DIALECT", loc="$", msg="only graphviz -Tsvg output is currently parsed; mermaid SVG support is a P1 TODO (see references/roadmap.md)", severity="error")], warnings=[])
    scene = parse_graphviz_svg(svg_text)
    if not scene.nodes:
        return Verdict(ok=False, errors=[Violation(code="UNSUPPORTED_SVG_DIALECT", loc="$", msg="no graphviz node groups found in SVG -- not a supported dialect or an empty render", severity="error")], warnings=[])
    return check_scene(scene)
