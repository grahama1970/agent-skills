# Flowchart / C4 / connector legibility rules (harvested research)

## Flowchart rules

- **Consistent direction, one start point.** Pick top-down or left-right and
  keep it; a flowchart with two entry arrows confuses readers about where to
  start.
- **Standard symbols.** Rectangle = process/step, diamond = decision, rounded
  rectangle/stadium = terminal (start/end). Don't invent new shape semantics
  per diagram.
- **Short labels, one idea per node.** A node is a single step or decision,
  not a paragraph. The checker's `LABEL_TOO_LONG` rule (default 60 chars) is
  a deterministic proxy for this.
- **Labeled decision branches.** Every edge out of a decision node states the
  condition (`yes`/`no`, or the actual predicate) — never leave a branch
  unlabeled and force the reader to infer it. The checker's
  `UNLABELED_BRANCH` rule enforces this on declared `gates[]`.
- **Minimal arrow crossings.** Route around, not through, other elements.
- **Explicit terminal states.** Every path ends at a visible terminal node
  (`done`, `resume`, `escalate`, `failed`, ...), never trails off. The
  checker's `MISSING_TERMINAL_STATE` rule enforces at least one declared
  terminal state for process views.

## C4 / structure diagrams

- Provide a legend/annotation for any symbol or color convention used more
  than once (box border style, arrow style, color coding by layer).
  Diagrams without a legend force readers to guess semantics.
- Show hierarchy explicitly (containers inside systems, components inside
  containers) rather than flattening everything to one level.
- Explain the rationale near the diagram (why this boundary, why this
  dependency direction) — a structure diagram without a sentence of context
  is a picture, not an explanation.

## Connector routing (Excalidraw-specific)

Excalidraw supports **orthogonal (elbow)** and **curved** connectors, not
just straight lines. For `decision_tree`/`flowchart` views:

- **Default to orthogonal or curved routing** that goes around nodes and
  labels, not through them.
- **Straight diagonal arrows that cross a label or a box are a legibility
  defect.** This is the exact bug that made the original star fan-out
  unreadable: diagonal arrows crossed the tier labels, so readers couldn't
  tell which arrow belonged to which label.
- Labels must sit beside or on their own edge segment, never underneath a
  diagonal arrow stroke.

This is advisory, not a hard gate: whether a specific arrow visually crosses
a specific label in the final render can only be confirmed by looking at the
rendered image (SKILL.md step 5, screenshot read-back), not by inspecting
the spec's topology alone. The checker's `CONNECTOR_ROUTING_STRAIGHT` rule
flags `routing: straight` on flow/decision edges as an advisory warning and
never fails the gate by itself.
