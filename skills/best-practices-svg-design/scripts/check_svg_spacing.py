#!/usr/bin/env python3
"""Deterministic even-spacing check computed FROM the SVG artwork itself.

Reads the SVG, accumulates ancestor translate() transforms, collects
panel-scale boxes (rect w>=200 & h>=28, circle r>=20; halos excluded),
clusters them into horizontal rows (vertical clearance < merge_tol joins a
row), then asserts:
  - consecutive row gaps are uniform within --tol (default 2px)
  - within a row, boxes of equal height have equal widths and equal gutters
Prints the row table and SPACING_OK / SPACING_FAIL; exit 1 on failure.
No manifest is consulted — the artwork is the only input.
"""
import re, sys, xml.etree.ElementTree as ET

def translates(elem_chain):
    tx = ty = 0.0
    for e in elem_chain:
        t = e.get("transform", "")
        m = re.match(r"\s*translate\(\s*(-?[\d.]+)[ ,]+(-?[\d.]+)\s*\)", t)
        if m:
            tx += float(m.group(1)); ty += float(m.group(2))
    return tx, ty

def main() -> int:
    path = sys.argv[1]
    tol = float(sys.argv[sys.argv.index("--tol")+1]) if "--tol" in sys.argv else 2.0
    merge_tol = 24.0
    tree = ET.parse(path)
    ns = {"s": "http://www.w3.org/2000/svg"}
    boxes = []
    def walk(e, chain):
        chain = chain + [e]
        tag = e.tag.split("}")[-1]
        cls = e.get("class", "")
        if "stage-halo" not in cls:
            tx, ty = translates(chain)
            if tag == "rect" and e.get("width") and e.get("height"):
                w, h = float(e.get("width")), float(e.get("height"))
                if 200 <= w <= 1200 and 28 <= h <= 300:
                    boxes.append((float(e.get("x", 0))+tx, float(e.get("y", 0))+ty, w, h, cls or "rect"))
            elif tag == "circle" and e.get("r") and float(e.get("r")) >= 20:
                r = float(e.get("r"))
                boxes.append((float(e.get("cx"))+tx-r, float(e.get("cy"))+ty-r, 2*r, 2*r, cls or "circle"))
        for c in e:
            walk(c, chain)
    walk(tree.getroot(), [])
    if not boxes:
        print("SPACING_FAIL no panel-scale boxes found"); return 1
    boxes.sort(key=lambda b: b[1])
    rows = []
    for b in boxes:
        if rows and b[1] <= rows[-1]["bottom"] + merge_tol:
            rows[-1]["items"].append(b)
            rows[-1]["bottom"] = max(rows[-1]["bottom"], b[1]+b[3])
        else:
            rows.append({"top": b[1], "bottom": b[1]+b[3], "items": [b]})
    ok = True
    gaps = [round(rows[i+1]["top"] - rows[i]["bottom"], 1) for i in range(len(rows)-1)]
    for i, r in enumerate(rows):
        names = ",".join(sorted({it[4].split()[0] for it in r["items"]}))
        print(f"row{i}: y={r['top']:.0f}-{r['bottom']:.0f} n={len(r['items'])} [{names}]")
    print(f"row gaps: {gaps}")
    if gaps and max(gaps) - min(gaps) > tol:
        print(f"SPACING_FAIL uneven row gaps (spread {max(gaps)-min(gaps):.1f} > {tol})"); ok = False
    for i, r in enumerate(rows):
        items = sorted(r["items"], key=lambda b: b[0])
        sibs = [b for b in items if abs(b[3] - items[0][3]) <= tol]
        if len(sibs) >= 3:
            widths = [round(b[2], 1) for b in sibs]
            gutters = [round(sibs[j+1][0] - (sibs[j][0]+sibs[j][2]), 1) for j in range(len(sibs)-1)]
            print(f"row{i} widths={widths} gutters={gutters}")
            if max(widths)-min(widths) > tol or (gutters and max(gutters)-min(gutters) > tol):
                print(f"SPACING_FAIL uneven columns in row{i}"); ok = False
    print("SPACING_OK" if ok else "SPACING_FAIL")
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
