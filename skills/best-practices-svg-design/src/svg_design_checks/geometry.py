"""Geometry extraction and layout math for SVG cards.

Inputs: an SVG file path. Outputs: panel-scale boxes, text anchors, marker-ended
connector endpoints, row clusters, and audits: row gaps, column widths/gutters,
label offsets, connector clearances, and composition metrics (rule-of-thirds,
golden ratio). Failure modes: raises only on unreadable XML; audits return
(ok, findings) and never raise on layout defects.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

GOLDEN = 0.6180339887


@dataclass
class Box:
    x: float
    y: float
    w: float
    h: float
    cls: str


@dataclass
class Text:
    x: float
    y: float
    anchor: str
    content: str


@dataclass
class Conn:
    x_end: float
    y_end: float
    x_start: float
    y_start: float


@dataclass
class Layout:
    width: float
    height: float
    boxes: list[Box] = field(default_factory=list)
    texts: list[Text] = field(default_factory=list)
    conns: list[Conn] = field(default_factory=list)


def _translates(chain) -> tuple[float, float]:
    tx = ty = 0.0
    for e in chain:
        m = re.match(r"\s*translate\(\s*(-?[\d.]+)[ ,]+(-?[\d.]+)\s*\)", e.get("transform", ""))
        if m:
            tx += float(m.group(1))
            ty += float(m.group(2))
    return tx, ty


def _path_endpoints(d: str) -> tuple[float, float, float, float] | None:
    tokens = re.findall(r"([MLHVCQTSAZmlhvcqtsaz])|(-?[\d.]+)", d)
    x = y = sx = sy = None
    cmd = ""
    nums: list[float] = []

    def flush():
        nonlocal x, y
        if cmd in ("M", "L") and len(nums) >= 2:
            x, y = nums[-2], nums[-1]
        elif cmd == "H" and nums:
            x = nums[-1]
        elif cmd == "V" and nums:
            y = nums[-1]
        elif cmd == "C" and len(nums) >= 6:
            x, y = nums[-2], nums[-1]

    for t_cmd, t_num in tokens:
        if t_cmd:
            flush()
            cmd = t_cmd.upper()
            nums = []
            continue
        nums.append(float(t_num))
        if cmd == "M" and sx is None and len(nums) == 2:
            sx, sy = nums[0], nums[1]
    flush()
    if None in (x, y, sx, sy):
        return None
    return sx, sy, x, y


def load_layout(path: str) -> Layout:
    root = ET.parse(path).getroot()
    width = float(re.sub(r"[^\d.]", "", root.get("width", "0")) or 0)
    height = float(re.sub(r"[^\d.]", "", root.get("height", "0")) or 0)
    lay = Layout(width=width, height=height)

    def walk(e, chain):
        chain = chain + [e]
        tag = e.tag.split("}")[-1]
        cls = e.get("class", "")
        tx, ty = _translates(chain)
        if "stage-halo" in cls:
            pass
        elif tag == "rect" and e.get("width") and e.get("height"):
            w, h = float(e.get("width")), float(e.get("height"))
            if 200 <= w <= width * 0.8 and 28 <= h <= 300:
                lay.boxes.append(Box(float(e.get("x", 0)) + tx, float(e.get("y", 0)) + ty, w, h, cls or "rect"))
        elif tag == "circle" and e.get("r") and float(e.get("r")) >= 20:
            r = float(e.get("r"))
            lay.boxes.append(Box(float(e.get("cx")) + tx - r, float(e.get("cy")) + ty - r, 2 * r, 2 * r, cls or "circle"))
        elif tag == "text" and e.get("x") and e.get("y"):
            lay.texts.append(Text(float(e.get("x")) + tx, float(e.get("y")) + ty,
                                  e.get("text-anchor", "start"), (e.text or "").strip()))
        elif tag == "path" and e.get("marker-end") and "flow-path" not in cls:
            pts = _path_endpoints(e.get("d", ""))
            if pts:
                lay.conns.append(Conn(pts[2] + tx, pts[3] + ty, pts[0] + tx, pts[1] + ty))
        for c in e:
            walk(c, chain)

    walk(root, [])
    return lay


def cluster_rows(boxes: list[Box], merge_tol: float = 24.0) -> list[dict]:
    rows: list[dict] = []
    for b in sorted(boxes, key=lambda b: b.y):
        if rows and b.y <= rows[-1]["bottom"] + merge_tol:
            rows[-1]["items"].append(b)
            rows[-1]["bottom"] = max(rows[-1]["bottom"], b.y + b.h)
        else:
            rows.append({"top": b.y, "bottom": b.y + b.h, "items": [b]})
    return rows


def audit_spacing(lay: Layout, tol: float = 2.0) -> tuple[bool, list[str]]:
    out: list[str] = []
    ok = True
    rows = cluster_rows(lay.boxes)
    if not rows:
        return False, ["SPACING_FAIL no panel-scale boxes found"]
    gaps = [round(rows[i + 1]["top"] - rows[i]["bottom"], 1) for i in range(len(rows) - 1)]
    for i, r in enumerate(rows):
        names = ",".join(sorted({it.cls.split()[0] for it in r["items"]}))
        out.append(f"row{i}: y={r['top']:.0f}-{r['bottom']:.0f} n={len(r['items'])} [{names}]")
    out.append(f"row gaps: {gaps}")
    if gaps and max(gaps) - min(gaps) > tol:
        out.append(f"SPACING_FAIL uneven row gaps (spread {max(gaps) - min(gaps):.1f} > {tol})")
        ok = False
    for i, r in enumerate(rows):
        items = sorted(r["items"], key=lambda b: b.x)
        sibs = [b for b in items if abs(b.h - items[0].h) <= tol]
        if len(sibs) >= 3:
            widths = [round(b.w, 1) for b in sibs]
            gutters = [round(sibs[j + 1].x - (sibs[j].x + sibs[j].w), 1) for j in range(len(sibs) - 1)]
            out.append(f"row{i} widths={widths} gutters={gutters}")
            if max(widths) - min(widths) > tol or (gutters and max(gutters) - min(gutters) > tol):
                out.append(f"SPACING_FAIL uneven columns in row{i}")
                ok = False
        contained = [(b, t) for t in lay.texts for b in items
                     if b.x <= t.x <= b.x + b.w and b.y <= t.y <= b.y + b.h]
        if len(contained) >= 2:
            offs = sorted(round(t.y - b.y, 1) for b, t in contained)
            if max(offs) - min(offs) > tol:
                out.append(f"SPACING_FAIL row{i} label baselines uneven: {offs}")
                ok = False
            for b, t in contained:
                if t.anchor == "middle" and abs(t.x - (b.x + b.w / 2)) > tol:
                    out.append(f"SPACING_FAIL row{i} centered label '{t.content[:20]}' off-center by {t.x - (b.x + b.w / 2):+.1f}")
                    ok = False
            lefts = [(b, t) for b, t in contained if t.anchor != "middle"]
            if len(lefts) >= 2:
                xoffs = sorted(round(t.x - b.x, 1) for b, t in lefts)
                if max(xoffs) - min(xoffs) > tol:
                    out.append(f"SPACING_FAIL row{i} label x-offsets uneven: {xoffs}")
                    ok = False
    c_ok, c_out = audit_connectors(lay, rows, tol)
    out += c_out
    ok = ok and c_ok
    return ok, out


def audit_connectors(lay: Layout, rows: list[dict], tol: float = 2.0) -> tuple[bool, list[str]]:
    """Every marker-ended connector must start a uniform distance below its
    source row bottom and end a uniform distance above its target row top."""
    out: list[str] = []
    ok = True
    starts: list[float] = []
    ends: list[float] = []
    for c in lay.conns:
        src = min((r for r in rows if r["bottom"] <= c.y_start + tol), default=None,
                  key=lambda r: c.y_start - r["bottom"] if c.y_start >= r["bottom"] - tol else 1e9)
        tgt = min((r for r in rows if r["top"] >= c.y_end - tol), default=None,
                  key=lambda r: r["top"] - c.y_end if r["top"] >= c.y_end - tol else 1e9)
        if src and 0 <= c.y_start - src["bottom"] <= 20:
            starts.append(round(c.y_start - src["bottom"], 1))
        if tgt and 0 <= tgt["top"] - c.y_end <= 20:
            ends.append(round(tgt["top"] - c.y_end, 1))
    if starts:
        out.append(f"connector start clearances: {sorted(starts)}")
        if max(starts) - min(starts) > tol:
            out.append(f"SPACING_FAIL connector start clearances uneven (spread {max(starts) - min(starts):.1f} > {tol})")
            ok = False
    if ends:
        out.append(f"connector end clearances: {sorted(ends)}")
        if max(ends) - min(ends) > tol:
            out.append(f"SPACING_FAIL connector end clearances uneven (spread {max(ends) - min(ends):.1f} > {tol})")
            ok = False
    return ok, out


def audit_composition(lay: Layout) -> list[str]:
    out: list[str] = []
    if not lay.boxes:
        return ["COMPOSITION no boxes found"]
    xs = [b.x for b in lay.boxes]
    xe = [b.x + b.w for b in lay.boxes]
    ys = [b.y for b in lay.boxes]
    ye = [b.y + b.h for b in lay.boxes]
    cx = (min(xs) + max(xe)) / 2
    cy = (min(ys) + max(ye)) / 2
    out.append(f"content bbox x={min(xs):.0f}-{max(xe):.0f} y={min(ys):.0f}-{max(ye):.0f} centroid=({cx:.0f},{cy:.0f})")
    for name, line in (("thirds-x1", lay.width / 3), ("thirds-x2", 2 * lay.width / 3),
                       ("golden-x", lay.width * GOLDEN), ("golden-x-conjugate", lay.width * (1 - GOLDEN))):
        d = min(min(abs(b.x - line), abs(b.x + b.w - line), abs(b.x + b.w / 2 - line)) for b in lay.boxes)
        out.append(f"{name}={line:.0f} nearest-anchor-delta={d:.0f}px")
    rows = cluster_rows(lay.boxes)
    for name, line in (("thirds-y1", lay.height / 3), ("thirds-y2", 2 * lay.height / 3),
                       ("golden-y", lay.height * GOLDEN)):
        d = min(min(abs(r["top"] - line), abs(r["bottom"] - line), abs((r["top"] + r["bottom"]) / 2 - line)) for r in rows)
        out.append(f"{name}={line:.0f} nearest-row-delta={d:.0f}px")
    return out
