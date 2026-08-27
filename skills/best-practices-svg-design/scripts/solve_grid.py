#!/usr/bin/env python3
"""Solve a uniform vertical grid: given row heights and a canvas, emit exact
row y-positions with equal gaps and symmetric margins.

Input JSON: {"canvas": 1200, "origin": 0, "rows": [{"name": "a", "h": 84}, ...],
             "gap": optional forced gap}
Output: solved manifest (same shape as check_grid input) on stdout.
The solver picks the largest integer gap whose margins stay symmetric
within 1px; pass "gap" to force one.
"""
import json, sys

def main() -> int:
    m = json.load(open(sys.argv[1]))
    canvas, origin = m["canvas"], m.get("origin", 0)
    heights = [r["h"] for r in m["rows"]]
    n_gaps = len(heights) - 1
    total_h = sum(heights)
    if "gap" in m:
        gap = m["gap"]
    else:
        gap = (canvas - total_h) // (n_gaps + 2)  # start guess: margins ~ gap
        while gap > 0 and canvas - total_h - n_gaps * gap < 2 * 8:
            gap -= 1
        # prefer margins >= gap*0.8; walk down until margins look sane
        while gap > 0:
            margin2 = canvas - total_h - n_gaps * gap
            if margin2 >= 0 and margin2 % 2 in (0, 1):
                break
            gap -= 1
    margin = (canvas - total_h - n_gaps * gap) / 2
    y = origin + margin
    rows = []
    for r in m["rows"]:
        rows.append({"name": r["name"], "y": round(y), "h": r["h"]})
        y += r["h"] + gap
    out = {"canvas": canvas, "origin": origin, "tolerance": m.get("tolerance", 1),
           "gap": gap, "margin": margin, "rows": rows}
    if "columns" in m:
        out["columns"] = m["columns"]
    json.dump(out, sys.stdout, indent=2)
    print()
    return 0

if __name__ == "__main__":
    sys.exit(main())
