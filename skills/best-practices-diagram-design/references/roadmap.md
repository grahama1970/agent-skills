# Diagram-design roadmap

## Implemented P0

- Source-bound semantic requirements: ordering, required gate outcomes, and outcome targets.
- Counterexample-path detection for precondition bypasses.
- Graphviz SVG measured-scene checks for node overlap, text overflow, edge/text intersection, edge/node intersection, and clipping.
- Mutation fixtures for semantic and Graphviz geometry failures.

## P1 — adapters and publication evidence

- Normalize Excalidraw and Mermaid output into the measured-scene contract.
- Replace the current Graphviz Bézier control-polygon approximation with bounded-error curve subdivision.
- Add semantic-spec/requirements/scene/artifact/configuration digests to the publication receipt.
- Add renderer capability matrices, pinned fonts, display-space typography/spacing profiles, contrast, legends, and style roles.
- Add Excalidraw export/reload plus move/resize binding fixtures.

Until an adapter exists, its geometry status is `UNVERIFIED`; Graphviz success must not be generalized to Mermaid or Excalidraw.

## P2 — generation

Implement the typed catalog in `template-catalog.md` behind `ops-excalidraw`. Qualify imported starters individually and keep semantic requirements immutable during layout repair.
