"""Multi-element scene clusters for slide illustrations (#1315).

Blind judges separated generated slides from the author's 12/12, and the tell
they named most often after chrome was illustration: the author draws SCENES —
a labelled subject, smaller supporting glyphs, a ground mark, and dotted flow
between them — where the compiler drew a row of identical ringed icons.

A scene is declarative and deterministic. Each composition places 2-4 glyphs at
DIFFERENT scales on an asymmetric grid, so no scene can degenerate into the
evenly-spaced row that reads as machine output; ``assert_not_mechanical``
reports uniformity as an ADVISORY note. It is deliberately not a refusal:
symmetry can encode a truthful claim (parallel agents, repeated stages), so a
compiler that rejects it would distort meaning to avoid a stylistic tell. Glyphs
come from the hash-pinned icon library, so every part stays natively editable.

Inputs: a semantic role plus the label and icon hints for the subject. Outputs:
DiagramNode/DiagramEdge sets the existing emitters already render. Failure
modes: an unknown scene id raises; a composition that violates the asymmetry
invariant raises at construction, never at render time.
"""

from __future__ import annotations

from typing import Literal

from .document import Bbox, DiagramEdge, DiagramGraph, DiagramNode

SceneId = Literal["source-to-review", "evidence-cluster", "gate-run", "actor-exchange", "capture-surface", "single-subject"]

# Declarative compositions. Each entry is (cx, cy, scale, decoration) where cx/cy
# are the glyph CENTRE as a fraction of the diagram box — centres keep a scene
# readable when glyph weights differ, which corner offsets do not. The scale
# column is what makes a scene a scene rather than a row: the subject dominates
# and support glyphs recede.
_COMPOSITIONS: dict[str, list[tuple[float, float, float, str]]] = {
    # a subject flanked by a smaller origin and a smaller outcome, off-centre
    "source-to-review": [
        (0.13, 0.60, 0.72, "support"),
        (0.45, 0.34, 1.30, "principal"),
        (0.83, 0.66, 0.86, "support"),
    ],
    # a dense middle with satellites above and below (the datalake habit)
    "evidence-cluster": [
        (0.42, 0.32, 1.34, "principal"),
        (0.12, 0.62, 0.70, "support"),
        (0.76, 0.64, 0.82, "support"),
        (0.52, 0.80, 0.58, "ground"),
    ],
    # checkpoints along a route, deliberately uneven, terminal emphasised
    "gate-run": [
        (0.10, 0.62, 0.74, "support"),
        (0.33, 0.40, 0.92, "support"),
        (0.57, 0.66, 0.78, "support"),
        (0.85, 0.34, 1.36, "principal"),
    ],
    # two actors in exchange, one dominant
    "actor-exchange": [
        (0.24, 0.38, 1.24, "principal"),
        (0.72, 0.56, 0.84, "support"),
        (0.50, 0.82, 0.52, "ground"),
    ],
    # a surface being inspected, with a small inspector glyph
    "capture-surface": [
        (0.35, 0.40, 1.40, "principal"),
        (0.78, 0.66, 0.66, "support"),
    ],
    "single-subject": [
        (0.46, 0.42, 1.45, "principal"),
        (0.70, 0.74, 0.48, "ground"),
    ],
}

_SCENE_HINTS: dict[str, SceneId] = {
    "architecture": "source-to-review",
    "problem_solution": "actor-exchange",
    "proof": "capture-surface",
    "roadmap": "gate-run",
    "thesis": "single-subject",
    "value_prop": "evidence-cluster",
}


class SceneError(ValueError):
    """Raised when a scene cannot be composed honestly."""


def describe_uniformity(nodes: list[DiagramNode]) -> list[str]:
    """ADVISORY notes about uniform composition — never a refusal (#1335).

    This was a hard invariant that refused evenly weighted, evenly pitched
    glyphs as "mechanical". The state audit overturned it: symmetry can encode a
    TRUTHFUL claim — parallel agents, repeated stages, redundant paths, equal
    controls — so refusing it makes the compiler distort structure to avoid a
    stylistic tell, which is a correctness bug, not a style win. Uniformity is
    now reported for a human to judge; the compiler no longer overrides meaning
    for aesthetics."""
    notes: list[str] = []
    if len(nodes) < 3:
        return notes
    if len({round(n.scale, 2) for n in nodes}) < 2:
        notes.append("uniform glyph weight — intentional only if the claim asserts equivalence")
    xs = sorted(n.bbox.x for n in nodes)
    gaps = [round(b - a, 3) for a, b in zip(xs, xs[1:])]
    if len(set(gaps)) == 1 and len(gaps) > 1:
        notes.append(f"even pitch ({gaps}) — intentional only if the claim asserts parallel or repeated stages")
    return notes


def compose_scene(
    scene: SceneId,
    *,
    subject_label: str,
    icons: list[str],
    support_labels: list[str] | None = None,
    node_prefix: str = "scene",
    binding_paths: list[str] | None = None,
) -> DiagramGraph:
    """Build one illustration: a labelled subject, supporting glyphs, dotted flow."""
    layout = _COMPOSITIONS.get(scene)
    if layout is None:
        raise SceneError(f"unknown scene '{scene}'")
    if not icons:
        raise SceneError(f"scene '{scene}' needs at least one glyph")

    supports = list(support_labels or [])
    support_icons = list(icons[1:]) or [icons[0]]
    nodes: list[DiagramNode] = []
    support_index = 0
    for index, (dx, dy, scale, decoration) in enumerate(layout):
        if decoration == "principal":
            icon = icons[0]  # the subject keeps the caller's first glyph
            label = subject_label
        else:
            icon = support_icons[support_index % len(support_icons)]
            support_index += 1
            label = supports.pop(0) if supports else " "
        size = round(0.30 * scale, 3)
        # centre -> corner, clamped so a heavy glyph never leaves the box
        x = min(max(dx - size / 2, 0.0), 1.0 - size)
        y = min(max(dy - size / 2, 0.0), 1.0 - size)
        nodes.append(
            DiagramNode(
                id=f"{node_prefix}-{index}",
                bbox=Bbox(x=round(x, 3), y=round(y, 3), w=size, h=size),
                icon=icon,
                label=label,
                decoration=decoration,  # type: ignore[arg-type]
                scale=scale,
                # per-LABEL provenance (#1328): a labelled glyph asserts something,
                # so it carries its own path rather than sharing the element's.
                binding_paths=([f"{node_prefix}-{index}:label"] if label.strip() else []),
            )
        )
    # uniformity is advisory now, not a refusal (#1335)
    describe_uniformity(nodes)

    # Dotted flow from each support into the principal — the author's meander,
    # not a straight process arrow.
    principal = next((n for n in nodes if n.decoration == "principal"), nodes[0])
    edges = [
        DiagramEdge(
            id=f"{node_prefix}-flow-{i}",
            source=node.id,
            target=principal.id,
            line_style="dotted",
            route="dotted-path",
            arrowhead=True,
            decorative=True,  # visual association only; claims live on the nodes
        )
        for i, node in enumerate(nodes)
        if node.id != principal.id and node.decoration != "ground"
    ]
    return DiagramGraph(recipe="scene", nodes=nodes, edges=edges)


def scene_for_module(module: str) -> SceneId:
    """Semantic selection — a module gets the scene that fits its rhetorical beat."""
    return _SCENE_HINTS.get(module, "evidence-cluster")
