#!/usr/bin/env python3
"""Assert a card's rows sit on a uniform vertical grid.

Manifest JSON: {"canvas": 1200, "tolerance": 1,
  "rows": [{"name": "query", "y": 110, "h": 84}, ...],
  "relations": [{"type": "equal_gap", "name": "terminal_gap_match",
    "a": ["request", "intent"], "b": ["outcomes", "response"]}]}
Rows are top-to-bottom in the artwork's local coordinates.
Exit 0 with GRID_OK only when every inter-row gap is equal within
tolerance, top/bottom margins are equal within 2*tolerance, and named
relations are satisfied.
"""
import json, sys

def main() -> int:
    m = json.load(open(sys.argv[1]))
    if "centers" in m:
        c = m["centers"]
        tol = m.get("tolerance", 1)
        steps = [c[i+1] - c[i] for i in range(len(c) - 1)]
        print(f"center steps: {steps}")
        if max(steps) - min(steps) <= tol:
            print("GRID_OK")
            return 0
        print(f"GRID_FAIL uneven center steps (spread {max(steps)-min(steps)} > {tol})")
        return 1
    rows = m["rows"]
    tol = m.get("tolerance", 1)
    gaps = [rows[i+1]["y"] - (rows[i]["y"] + rows[i]["h"]) for i in range(len(rows)-1)]
    top = rows[0]["y"] - m.get("origin", 0)
    bottom = m["canvas"] + m.get("origin", 0) - (rows[-1]["y"] + rows[-1]["h"])
    ok_gaps = max(gaps) - min(gaps) <= tol
    ok_margins = abs(top - bottom) <= 2 * tol
    print(f"gaps={gaps} top={top} bottom={bottom}")
    rows_by_name = {r.get("name"): r for r in rows}

    def bounds(row, measure="row"):
        if measure == "row":
            return row["y"], row["y"] + row["h"]
        if measure == "visual":
            top = row.get("visual_top", row.get("visual_y", row["y"]))
            if "visual_bottom" in row:
                bottom = row["visual_bottom"]
            else:
                bottom = top + row.get("visual_h", row["h"])
            return top, bottom
        raise ValueError(f"unknown measure {measure!r}")

    ok_relations = True
    for rel in m.get("relations", []):
        if rel.get("type") != "equal_gap":
            print(f"GRID_FAIL unknown relation type {rel.get('type')!r} in {rel.get('name', '<unnamed>')}")
            ok_relations = False
            continue
        try:
            a0, a1 = (rows_by_name[n] for n in rel["a"])
            b0, b1 = (rows_by_name[n] for n in rel["b"])
        except KeyError as exc:
            print(f"GRID_FAIL relation {rel.get('name', '<unnamed>')} references missing row {exc}")
            ok_relations = False
            continue
        try:
            measure = rel.get("measure", "row")
            _, a0_bottom = bounds(a0, measure)
            a1_top, _ = bounds(a1, measure)
            _, b0_bottom = bounds(b0, measure)
            b1_top, _ = bounds(b1, measure)
        except ValueError as exc:
            print(f"GRID_FAIL relation {rel.get('name', '<unnamed>')} {exc}")
            ok_relations = False
            continue
        gap_a = a1_top - a0_bottom
        gap_b = b1_top - b0_bottom
        label_a = f"{a0.get('name')}→{a1.get('name')}"
        label_b = f"{b0.get('name')}→{b1.get('name')}"
        print(f"relation={rel.get('name', '<unnamed>')} measure={measure} {label_a}={gap_a} {label_b}={gap_b}")
        if abs(gap_a - gap_b) > tol:
            print(f"GRID_FAIL relation {rel.get('name', '<unnamed>')} differs by {abs(gap_a-gap_b)} > {tol}")
            ok_relations = False
    ok_cols = True
    for group in m.get("columns", []):
        cols = group["items"]
        widths = [c["w"] for c in cols]
        gutters = [cols[i+1]["x"] - (cols[i]["x"] + cols[i]["w"]) for i in range(len(cols)-1)]
        print(f"row={group['name']} widths={widths} gutters={gutters}")
        if max(widths) - min(widths) > tol or (gutters and max(gutters) - min(gutters) > tol):
            ok_cols = False
            print(f"GRID_FAIL columns uneven in {group['name']}")
    if ok_gaps and ok_margins and ok_cols and ok_relations:
        print("GRID_OK")
        return 0
    if not ok_gaps:
        print(f"GRID_FAIL uneven gaps (spread {max(gaps)-min(gaps)} > {tol})")
    if not ok_margins:
        print(f"GRID_FAIL margins differ by {abs(top-bottom)} > {2*tol}")
    return 1

if __name__ == "__main__":
    sys.exit(main())
