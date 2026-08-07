#!/usr/bin/env python3
"""gen_graph.py — sanitized public relationship graph (#1294).

Explicit, provenance-bearing edges ONLY — never similarity. Nodes: a practice
center, the research areas (by technical/creative/hybrid lens), and the
projects. Edges come from the taxonomy bridge (project -> area) and lens
grouping (area -> practice), so the constellation renders real structure, not
inferred connections. Private projects carry their public-overview href and an
`evidenceAccess: abstract` flag; the private repo is never referenced.

Bounded and public-only, per #1294. Run under monitor-website refresh.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SITE = REPO / "site"
OUT = SITE / "graph.json"

# Concise node labels for the constellation — the full taxonomy titles are too
# wide to sit around the ring without label collisions. Full titles still show
# in the research map and on hover. Keyed by area id; falls back to title.
SHORT_LABELS = {
    "pipelines": "Agentic pipelines",
    "memory": "Agentic memory",
    "extraction": "Extraction",
    "compliance": "Compliance",
    "adaptive-lineage": "Adaptive lineage",
    "applied-ml": "Applied ML",
    "design-interface": "Design",
    "creative-media": "Creative media",
}


def _load(name: str) -> dict:
    return json.loads((SITE / name).read_text(encoding="utf-8"))


def _commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO,
                              capture_output=True, text=True, check=True).stdout.strip()
    except Exception:  # noqa: BLE001
        return "unknown"


def main() -> None:
    rmap = _load("research-map.json")
    vis = {v["slug"]: v for v in _load("project-visibility.json")["projects"]}
    content = {p["slug"]: p for p in _load("content.json")["projects"]}

    nodes = [{"id": "practice", "type": "practice", "label": "one practice",
              "lens": "hybrid"}]
    edges = []

    for a in rmap["areas"]:
        # Every area appears (incl. creative-media, design) so the practice
        # constellation shows the technical AND creative halves — the point of
        # the balanced landing view. Areas may have skills but no flagship.
        aid = f"area:{a['id']}"
        # Representative image: the area's lead (first) flagship project, so the
        # oval carries a real image from that area. Skills-only areas (no
        # flagship) stay imageless — a glow disc — rather than borrow a photo
        # that would misrepresent them.
        lead_img = a["systems"][0]["slug"] if a["systems"] else None
        area_node = {"id": aid, "type": "area",
                     "label": SHORT_LABELS.get(a["id"], a["title"]),
                     "title": a["title"], "lens": a["lens"],
                     "skillCount": a["skillCount"]}
        if lead_img:
            area_node["img"] = lead_img
        nodes.append(area_node)
        edges.append({"source": "practice", "target": aid, "rel": "area"})
        for s in a["systems"]:
            slug = s["slug"]
            v = vis.get(slug, {})
            pid = f"project:{slug}"
            nodes.append({
                "id": pid, "type": "project", "label": s["name"], "slug": slug,
                "lens": a["lens"],
                "href": v.get("href") or content.get(slug, {}).get("href"),
                "question": content.get(slug, {}).get("question", ""),
                "visibility": v.get("visibility", "public"),
                "evidenceAccess": v.get("evidence_access", "source"),
                "img": slug,
            })
            edges.append({"source": aid, "target": pid, "rel": "system"})

    out = {
        "schema": "grahama.graph.v1",
        "sourceCommit": _commit(),
        "counts": {"nodes": len(nodes), "edges": len(edges)},
        "nodes": nodes,
        "edges": edges,
    }
    OUT.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(REPO)} — {len(nodes)} nodes, {len(edges)} edges (public, explicit)")


if __name__ == "__main__":
    main()
