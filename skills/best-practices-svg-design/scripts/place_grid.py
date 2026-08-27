#!/usr/bin/env python3
"""Place an SVG card's rows onto a solved grid manifest (machine-readable law).

Usage: place_grid.py <svg> <manifest>

- Clusters the artwork's current rows in final user coords (svgelements, same
  loader/clusterer as the spacing checker).
- Reads target row tops from the manifest (canvas coords, from solve_grid.py).
- Derives per-row deltas mechanically; NO hand-computed tables.
- Shifts row content by its row delta. Connector y-coords that span a gap
  interpolate (same fraction of the new gap); anchors within 14px of a row
  edge snap so connector clearances stay exact.
- Updates CSS transform-origin y values by their row's delta (halo/dot
  origins are element centers in local coords).
Exemptions (named): full-canvas rects (h>=500), the headline column group,
defs/style blocks, relative-command paths (icons inside translated groups),
and background divider lines (x1 == 730).
The edited SVG's group-translate offset (file -> canvas coords) is detected
from the artwork itself and asserted against every rect-bearing row.
"""
from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ET.register_namespace("", "http://www.w3.org/2000/svg")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from svg_design_checks.geometry import cluster_rows, load_layout  # noqa: E402

NS = "{http://www.w3.org/2000/svg}"
YATTRS = ("y", "cy", "y1", "y2")
ANCHOR_SNAP_PX = 14.0


def fmt(v: float) -> str:
    s = f"{v:.1f}".rstrip("0").rstrip(".")
    return s if s else "0"


def detect_ty(svg_path: str, old_tops: list[float]) -> float:
    """File->canvas y offset: canvas_top = file_y + ty (ty is negative here).

    Vote-based: candidates are file-space tops of non-halo rects (y) and
    circles (cy - r). Icon-glyph shapes vote junk, but every true row top
    votes the same ty, so the mode wins; then assert every row matches.
    """
    from collections import Counter

    tree = ET.parse(svg_path)
    file_tops: list[float] = []
    for r in tree.getroot().iter(f"{NS}rect"):
        if r.get("y") is not None and float(r.get("height", 0)) < 500:
            file_tops.append(float(r.get("y")))
    for c in tree.getroot().iter(f"{NS}circle"):
        if c.get("cy") is not None and "stage-halo" not in (c.get("class") or ""):
            file_tops.append(float(c.get("cy")) - float(c.get("r", 0)))
    votes = Counter(round(t - ft, 3) for t in old_tops for ft in file_tops)
    ty = votes.most_common(1)[0][0]
    for top in old_tops:
        if not any(abs(ty - (top - ft)) <= 0.5 for ft in file_tops):
            raise SystemExit(f"PLACING_FAIL row top {top} has no file-space shape at {top - ty} (ty={ty})")
    return ty


def map_path_d(d: str, map_y) -> str:
    if re.search(r"[mlhvqtsaz]", d):  # relative commands: icon glyphs, untouched
        return d
    toks = re.findall(r"([A-Za-z])|(-?[\d.]+)|(\s+)|([^\sA-Za-z\d.-]+)", d)
    out: list[str] = []
    cmd, pending = "", None
    for tc, num, ws, other in toks:
        if tc:
            if pending is not None and cmd in ("M", "L", "C", "V"):
                out.append(fmt(map_y(pending)) if cmd == "V" else f"{pending:g}")
            pending = None
            cmd = tc.upper()
            out.append(tc)
        elif num:
            n = float(num)
            if cmd in ("M", "L", "C"):
                if pending is None:
                    pending = n
                else:
                    out += [f"{pending:g}", " "]
                    out.append(fmt(map_y(n)))
                    pending = None
            elif cmd == "V":
                out.append(fmt(map_y(n)))
            else:  # H and anything else: unchanged
                out.append(num)
        elif ws:
            out.append(" ")
        elif other:
            out.append(other)
    if pending is not None and cmd in ("M", "L", "C", "V"):
        out.append(fmt(map_y(pending)) if cmd == "V" else f"{pending:g}")
    return re.sub(r" {2,}", " ", "".join(out))


def main() -> int:
    svg_path, manifest_path = sys.argv[1], sys.argv[2]
    man = json.load(open(manifest_path))
    rows_new = sorted(man["rows"], key=lambda r: r["y"])

    lay = load_layout(svg_path)
    old = cluster_rows(lay.boxes)
    if len(old) != len(rows_new):
        print(f"PLACING_FAIL artwork has {len(old)} rows, manifest has {len(rows_new)}")
        return 1
    old_spans = [(r["top"], r["bottom"]) for r in old]
    new_spans = [(float(r["y"]), float(r["y"]) + float(r["h"])) for r in rows_new]
    for (ot, ob), (nt, nb) in zip(old_spans, new_spans):
        if abs((ob - ot) - (nb - nt)) > 1.0:
            print(f"PLACING_FAIL row height changed: artwork {ob - ot:.0f} vs manifest {nb - nt:.0f} (place never resizes)")
            return 1

    ty = detect_ty(svg_path, [t for t, _ in old_spans])
    # local(file) = canvas - ty
    OLD = [(t - ty, b - ty) for t, b in old_spans]
    NEW = [(t - ty, b - ty) for t, b in new_spans]
    D = [nt - ot for (ot, _), (nt, _) in zip(OLD, NEW)]

    def zone_delta(v: float):
        for (t, b), d in zip(OLD, D):
            if t <= v <= b:
                return d
        return None

    def map_y(v: float) -> float:
        s = zone_delta(v)
        if s is not None:
            return v + s
        if v < OLD[0][0] or v > OLD[-1][1]:
            return v
        for k in range(len(OLD) - 1):
            b0, t1 = OLD[k][1], OLD[k + 1][0]
            if b0 < v < t1:
                nb0, nt1 = NEW[k][1], NEW[k + 1][0]
                if v - b0 <= ANCHOR_SNAP_PX:
                    return nb0 + (v - b0)
                if t1 - v <= ANCHOR_SNAP_PX:
                    return nt1 - (t1 - v)
                f = (v - b0) / (t1 - b0)
                return nb0 + f * (nt1 - nb0)
        return v

    tree = ET.parse(svg_path)
    root = tree.getroot()

    def walk(el, skip_shift=False):
        tag = el.tag.replace(NS, "")
        if tag in ("defs", "style"):
            return
        if tag == "rect" and float(el.get("height", 0)) >= 500:
            return
        if tag == "g":
            m = re.match(r"translate\(\s*(-?[\d.]+)[ ,]+(-?[\d.]+)\s*\)", el.get("transform", ""))
            if m:
                tx, gty = float(m.group(1)), float(m.group(2))
                d = zone_delta(gty)
                if d is not None and not skip_shift:
                    # rewrite ONLY the translate's y-arg; keep any trailing
                    # scale()/matrix() intact (regex-to-end ate scale(1.6) once)
                    el.set("transform", re.sub(
                        r"^(translate\(\s*-?[\d.]+[ ,]+)(-?[\d.]+)(\s*\))",
                        lambda mm: f"{mm.group(1)}{fmt(gty + d)}{mm.group(3)}",
                        el.get("transform"), count=1))
                if abs(gty - ty) < 0.01 and abs(tx) > 0:  # the canvas wrapper group
                    for c in el:
                        walk(c, skip_shift=False)
                    return
                for c in el:
                    walk(c, skip_shift=True)
                return
            for c in el:
                walk(c, skip_shift=skip_shift)
            return
        if tag == "path" and not skip_shift:
            el.set("d", map_path_d(el.get("d"), map_y))
            return
        if tag in ("rect", "circle", "line", "text", "ellipse") and not skip_shift:
            if tag == "line" and el.get("x1") == "730":
                return  # named exemption: background divider
            for a in YATTRS:
                if el.get(a) is not None:
                    el.set(a, fmt(map_y(float(el.get(a)))))
            return
        for c in el:
            walk(c, skip_shift=skip_shift)

    walk(root)

    # CSS transform-origin y values follow their row (halo/dot origins are centers)
    style = root.find(f"{NS}defs/{NS}style")
    if style is not None and style.text:
        def origin_sub(m):
            return f"transform-origin: {m.group(1)}px {fmt(map_y(float(m.group(2))))}px;"
        new_css, n_sub = re.subn(r"transform-origin: (-?[\d.]+)px (-?[\d.]+)px;", origin_sub, style.text)
        style.text = new_css
        if style.text.count("{") != style.text.count("}"):
            print("PLACING_FAIL brace imbalance after CSS edit — aborting, file NOT written")
            return 1
    else:
        n_sub = 0

    tree.write(svg_path, xml_declaration=False, encoding="unicode")
    # keep the file byte-shape sane: default namespace, no ns0: prefixes
    print(f"placed {len(NEW)} rows onto manifest grid: deltas={[fmt(d) for d in D]} ty={ty:g} css-origins-updated={n_sub}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
