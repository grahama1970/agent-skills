#!/usr/bin/env bash
# Strip inherited venv to prevent uv conflicts in cross-skill subprocess calls
unset VIRTUAL_ENV
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UV="uv run --project ${SCRIPT_DIR}"

# ---------------------------------------------------------------------------
# Embedded Python — keeps everything in one file for skill simplicity
# ---------------------------------------------------------------------------
exec $UV python3 - "$@" << 'PYTHON_EOF'
"""create-gsn-diagram: GSN diagrams from ArangoDB compliance graph."""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
from dataclasses import dataclass, field
from typing import Any


# ── GSN node types ────────────────────────────────────────────────────────

@dataclass
class GSNNode:
    id: str
    label: str
    node_type: str  # Goal | Strategy | Solution | Context | Assumption

@dataclass
class GSNEdge:
    src: str
    dst: str
    label: str = ""

@dataclass
class GSNGraph:
    nodes: list[GSNNode] = field(default_factory=list)
    edges: list[GSNEdge] = field(default_factory=list)

    def add(self, node: GSNNode) -> None:
        self.nodes.append(node)

    def link(self, src: str, dst: str, label: str = "") -> None:
        self.edges.append(GSNEdge(src=src, dst=dst, label=label))


# ── DOT shapes per GSN type ──────────────────────────────────────────────

GSN_SHAPES: dict[str, dict[str, str]] = {
    "Goal":       {"shape": "box",           "style": "filled", "fillcolor": "#E8F0FE", "color": "#1A73E8"},
    "Strategy":   {"shape": "parallelogram", "style": "filled", "fillcolor": "#FFF3E0", "color": "#E65100"},
    "Solution":   {"shape": "circle",        "style": "filled", "fillcolor": "#E8F5E9", "color": "#2E7D32"},
    "Context":    {"shape": "box",           "style": "filled,rounded", "fillcolor": "#F3E5F5", "color": "#7B1FA2"},
    "Assumption": {"shape": "ellipse",       "style": "filled,dashed", "fillcolor": "#FFF9C4", "color": "#F9A825"},
}


# ── DOT emitter ──────────────────────────────────────────────────────────

def graph_to_dot(g: GSNGraph, title: str = "Assurance Case") -> str:
    lines = [
        "digraph assurance_case {",
        '  rankdir=TB;',
        f'  label="{title}";',
        '  labelloc=t;',
        '  fontname="Helvetica";',
        '  node [fontname="Helvetica", fontsize=10];',
        '  edge [fontname="Helvetica", fontsize=9];',
        "",
    ]
    for n in g.nodes:
        attrs = GSN_SHAPES.get(n.node_type, {"shape": "box"})
        attr_str = ", ".join(f'{k}="{v}"' for k, v in attrs.items())
        label = n.label.replace('"', '\\"')
        lines.append(f'  "{n.id}" [label="{label}", {attr_str}];')
    lines.append("")
    for e in g.edges:
        lbl = f' [label="{e.label}"]' if e.label else ""
        lines.append(f'  "{e.src}" -> "{e.dst}"{lbl};')
    lines.append("}")
    return "\n".join(lines)


# ── Sample / dry-run graph ───────────────────────────────────────────────

def build_sample_graph(control_id: str = "AC-1") -> GSNGraph:
    g = GSNGraph()
    g.add(GSNNode("G1",  f"G1: {control_id} Access Control Policy", "Goal"))
    g.add(GSNNode("S1",  "S1: Verify via evidence chain",           "Strategy"))
    g.add(GSNNode("Sn1", "Sn1: QRA evidence",                      "Solution"))
    g.add(GSNNode("Sn2", "Sn2: Audit log",                         "Solution"))
    g.add(GSNNode("C1",  "C1: NIST 800-171 framework",             "Context"))
    g.link("G1", "S1")
    g.link("S1", "Sn1", "supports")
    g.link("S1", "Sn2", "supports")
    g.link("G1", "C1",  "in context of")
    return g


# ── Memory-first queries (no direct ArangoDB access) ─────────────────────
import subprocess
from pathlib import Path

MEMORY_RUN = str(Path(__file__).resolve().parent.parent / "memory" / "run.sh")


def _memory_sample(collection: str, limit: int = 100, filter_expr: str = "", fields: str = "") -> list[dict]:
    """Query via /memory sample — fail loud, never fallback to direct DB."""
    cmd = [MEMORY_RUN, "sample", "--collection", collection, "--limit", str(limit)]
    if filter_expr:
        cmd += ["--filter", filter_expr]
    if fields:
        cmd += ["--fields", fields]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"FATAL: /memory unavailable: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout).get("items", [])


def _memory_recall(query: str, scope: str = "sparta", collections: str = "", k: int = 10) -> list[dict]:
    """Query via /memory recall — fail loud, never fallback to direct DB."""
    cmd = [MEMORY_RUN, "recall", "--q", query, "--scope", scope, "--k", str(k)]
    if collections:
        cmd += ["--collections", collections]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        print(f"FATAL: /memory unavailable: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout).get("items", [])


def build_graph_from_db(control_id: str) -> GSNGraph:
    """Query /memory for a control and its evidence chain."""
    g = GSNGraph()

    # Fetch the control document via memory sample
    controls = _memory_sample(
        "controls", limit=1,
        filter_expr=f'doc.control_id=="{control_id}"',
    )
    if not controls:
        print(f"error: control '{control_id}' not found via /memory", file=sys.stderr)
        sys.exit(1)

    ctrl = controls[0]
    goal_label = f"G1: {ctrl.get('control_id', control_id)} {ctrl.get('title', '')}"
    g.add(GSNNode("G1", goal_label.strip(), "Goal"))

    # Framework context
    fw = ctrl.get("framework", "Unknown")
    g.add(GSNNode("C1", f"C1: {fw} framework", "Context"))
    g.link("G1", "C1", "in context of")

    # Strategy: evidence verification
    g.add(GSNNode("S1", "S1: Verify via evidence chain", "Strategy"))
    g.link("G1", "S1")

    # Evidence — use memory recall to find related evidence
    evidence = _memory_recall(
        f"evidence for control {control_id}",
        scope="sparta", k=10,
    )
    for i, ev in enumerate(evidence, 1):
        nid = f"Sn{i}"
        title = ev.get("title") or ev.get("problem") or ev.get("_key", "evidence")
        label = f"{nid}: {title}"
        ntype = "Solution"
        if ev.get("type") == "assumption":
            ntype = "Assumption"
        g.add(GSNNode(nid, label, ntype))
        g.link("S1", nid, "supports")

    # Fallback: if no evidence found, note it
    if not evidence:
        g.add(GSNNode("Sn1", "Sn1: (no evidence found)", "Solution"))
        g.link("S1", "Sn1", "supports")

    return g


def build_graph_for_framework(framework: str) -> GSNGraph:
    """Build a combined GSN graph for all controls under a framework."""
    g = GSNGraph()

    controls = _memory_sample(
        "controls", limit=500,
        filter_expr=f'doc.framework=="{framework}"',
    )
    if not controls:
        print(f"error: no controls found for framework '{framework}' via /memory", file=sys.stderr)
        sys.exit(1)

    # Sort by control_id
    controls.sort(key=lambda c: c.get("control_id", ""))

    # Top-level goal
    g.add(GSNNode("G0", f"G0: {framework} Compliance", "Goal"))
    g.add(GSNNode("C0", f"C0: {framework} framework", "Context"))
    g.link("G0", "C0", "in context of")

    for ci, ctrl in enumerate(controls, 1):
        gid = f"G{ci}"
        sid = f"S{ci}"
        cid = ctrl.get("control_id", f"CTRL-{ci}")
        title = ctrl.get("title", "")
        g.add(GSNNode(gid, f"{gid}: {cid} {title}".strip(), "Goal"))
        g.link("G0", gid)
        g.add(GSNNode(sid, f"{sid}: Verify {cid}", "Strategy"))
        g.link(gid, sid)

    return g


# ── Render via graphviz Python package ───────────────────────────────────

def render_graph(dot_src: str, output: str) -> None:
    import graphviz as gv  # type: ignore[import-untyped]
    fmt = "png" if output.endswith(".png") else "svg"
    # graphviz.Source renders from DOT text
    src = gv.Source(dot_src, format=fmt)
    # render writes <output>.<fmt>, we want exact path
    out_base = output.rsplit(".", 1)[0] if "." in output else output
    src.render(filename=out_base, cleanup=True)
    print(f"rendered: {output}")


# ── CLI ──────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="GSN assurance case diagrams from compliance graph",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # render
    p_render = sub.add_parser("render", help="Render GSN diagram to SVG/PNG")
    p_render.add_argument("--control",   type=str, default=None)
    p_render.add_argument("--framework", type=str, default=None)
    p_render.add_argument("--output",    type=str, default=None)
    p_render.add_argument("--dry-run",   action="store_true")

    # export-dot
    p_dot = sub.add_parser("export-dot", help="Export raw DOT notation to stdout")
    p_dot.add_argument("--control",   type=str, default=None)
    p_dot.add_argument("--framework", type=str, default=None)
    p_dot.add_argument("--dry-run",   action="store_true")

    args = parser.parse_args()

    # Validate: need exactly one of --control or --framework
    if not args.control and not args.framework:
        parser.error("provide --control or --framework")
    if args.control and args.framework:
        parser.error("provide --control or --framework, not both")

    # Build the graph
    if args.dry_run:
        ctrl_id = args.control or "AC-1"
        graph = build_sample_graph(ctrl_id)
        title = f"Assurance Case: {ctrl_id} (dry-run)"
    elif args.control:
        graph = build_graph_from_db(args.control)
        title = f"Assurance Case: {args.control}"
    else:
        graph = build_graph_for_framework(args.framework)
        title = f"Assurance Case: {args.framework}"

    dot_src = graph_to_dot(graph, title=title)

    if args.command == "export-dot":
        print(dot_src)
        return

    # render
    output = args.output
    if not output:
        name = args.control or args.framework or "assurance_case"
        output = f"{name}_gsn.svg"

    render_graph(dot_src, output)


if __name__ == "__main__":
    main()
PYTHON_EOF
