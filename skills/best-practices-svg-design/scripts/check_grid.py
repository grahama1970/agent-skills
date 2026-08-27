#!/usr/bin/env python3
"""Assert a card's rows sit on a uniform vertical grid.

Manifest JSON: {"canvas": 1200, "tolerance": 1,
  "rows": [{"name": "query", "y": 110, "h": 84}, ...]}
Rows are top-to-bottom in the artwork's local coordinates.
Exit 0 with GRID_OK only when every inter-row gap is equal within
tolerance AND top/bottom margins are equal within 2*tolerance.
"""
import json, sys

def main() -> int:
    m = json.load(open(sys.argv[1]))
    rows = m["rows"]
    tol = m.get("tolerance", 1)
    gaps = [rows[i+1]["y"] - (rows[i]["y"] + rows[i]["h"]) for i in range(len(rows)-1)]
    top = rows[0]["y"] - m.get("origin", 0)
    bottom = m["canvas"] + m.get("origin", 0) - (rows[-1]["y"] + rows[-1]["h"])
    ok_gaps = max(gaps) - min(gaps) <= tol
    ok_margins = abs(top - bottom) <= 2 * tol
    print(f"gaps={gaps} top={top} bottom={bottom}")
    ok_cols = True
    for group in m.get("columns", []):
        cols = group["items"]
        widths = [c["w"] for c in cols]
        gutters = [cols[i+1]["x"] - (cols[i]["x"] + cols[i]["w"]) for i in range(len(cols)-1)]
        print(f"row={group['name']} widths={widths} gutters={gutters}")
        if max(widths) - min(widths) > tol or (gutters and max(gutters) - min(gutters) > tol):
            ok_cols = False
            print(f"GRID_FAIL columns uneven in {group['name']}")
    if ok_gaps and ok_margins and ok_cols:
        print("GRID_OK")
        return 0
    if not ok_gaps:
        print(f"GRID_FAIL uneven gaps (spread {max(gaps)-min(gaps)} > {tol})")
    if not ok_margins:
        print(f"GRID_FAIL margins differ by {abs(top-bottom)} > {2*tol}")
    return 1

if __name__ == "__main__":
    sys.exit(main())
