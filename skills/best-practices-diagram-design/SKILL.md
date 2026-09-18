---
name: best-practices-diagram-design
description: >
  Design gate for diagrams: choose the correct view before drawing, author a
  typed spec, run deterministic legibility/topology checks, then render and
  screenshot-verify. Use when an agent is about to draw a flowchart, decision
  tree, sequence diagram, architecture/C4 diagram, or fan-out, or when a
  rendered diagram needs review.
triggers:
  - design a diagram
  - diagram design
  - which diagram type
  - is this diagram badly designed
  - decision tree vs flowchart
  - diagram legibility
  - review a diagram
provides:
  - diagram-design-review
  - diagram-spec-validation
composes:
  - create-architecture
  - ops-excalidraw
  - create-svg
  - agentic-evals
complies:
  - best-practices-skills
  - best-practices-python
taxonomy:
  - validation
  - ui-design-engineering
runtime_self_improvement: basic
---

# best-practices-diagram-design

This skill exists because an agent flattened a **gated sequential escalation
ladder** into a **fan-out star** (wrong view), with labels overlapping arrows
and no decision gates. It is the gate between "agent wants to draw a diagram"
and "diagram gets shipped."

Grabbing the fastest one-command describe/template render is the mistake this
skill exists to stop. Choosing the view is a design decision, not a rendering
detail — it takes one extra minute and it is not optional.

## Workflow

### 1. Choose the VIEW first

| Intent | View | Renderer |
|---|---|---|
| Sequential steps with yes/no decisions | `decision_tree` / `flowchart` | graphviz or mermaid (compose `create-architecture`) |
| Time-ordered interactions between actors | `sequence` | mermaid sequence diagram |
| Structure / dependencies / components | `structure` (C4-style) | graphviz or `create-architecture` |
| State machine with entry/exit states | `lifecycle` | graphviz/mermaid state diagram |
| Genuinely parallel, independent options (≤4) | `fanout` | `create-svg` fan-out compiler |

A **gated escalation ladder is a `decision_tree`/`flowchart`, never a
`fanout`.** If a "parallel" set of options actually has an order, a lock, or
a resolved?-gate between them, it is not parallel — pick `decision_tree`.

See `references/view_selection.md` for the full table and rationale.

### 2. Author a typed diagram SPEC

Write a JSON spec (`view`, `nodes[]`, `edges[]`, `gates[]`,
`terminal_states[]`) before touching a renderer. Schema and examples:
`references/spec_schema.md`. Reference fixtures:
`fixtures/good_decision_tree.json`, `fixtures/bad_fanout_star.json`.

### 3. Run the checker

```bash
./run.sh check path/to/spec.json --json
```

Deterministic rule codes (error unless marked advisory):

| code | meaning |
|---|---|
| `VIEW_TOPOLOGY_MISMATCH` | `decision_tree`/`flowchart` view but a single source fans out to many targets with zero gates — the star-for-sequence bug |
| `MISSING_GATES` | `decision_tree`/`flowchart` has branching (a node with 2+ outgoing edges) but no decision gates declared |
| `UNLABELED_BRANCH` | a gate's outgoing edge has no `branch_label` (no yes/no) |
| `MISSING_TERMINAL_STATE` | a process view (`decision_tree`/`flowchart`/`sequence`/`lifecycle`) declares no `terminal_states` |
| `LABEL_TOO_LONG` | a node label exceeds the limit (default 60 chars; 80 for fan-out source, 40 for fan-out target, per Excalidraw box sizing) |
| `FANOUT_TOO_MANY` | `view: fanout` with more than 4 targets — the `create-svg` fan-out compiler's ceiling |
| `CONNECTOR_ROUTING_STRAIGHT` (advisory, warning) | a `decision_tree`/`flowchart` edge declares `routing: straight` — prefer `orthogonal`/`curved` |

Exit code is non-zero only on error-level violations; `CONNECTOR_ROUTING_STRAIGHT`
is advisory and never fails the gate on its own — see limits below.

### 4. Render

- `decision_tree`/`flowchart`/`sequence`/`lifecycle` → graphviz/mermaid via
  `create-architecture`.
- Editable/collaborative board → `ops-excalidraw`.
- True fan-out (≤4 targets, checker passed `FANOUT_TOO_MANY`) → `create-svg`
  fan-out compiler. `create-svg`'s fan-out compiler is NOT a general renderer
  for sequences — using it for a sequential process is the exact bug this
  skill was created to stop.

### 5. Screenshot read-back acceptance

Render to an image and **look at it** — do not accept on file-exists alone.
Check: one start point, consistent direction, labels inside boxes, no label
sitting on top of an arrow, decision branches labeled, a visible terminal
state. Compose `agentic-evals` for the fixture-based regression gate; this
step is a human/agent visual read of the rendered artifact, not a checker
rule (routing legibility can't be fully proven from the spec alone).

## Connector routing (legibility)

Excalidraw supports orthogonal (elbow) and curved connectors, not just
straight lines. For `decision_tree`/`flowchart`, default to **orthogonal or
curved** routing that goes around nodes and labels. Straight diagonal arrows
that cross a label or a box are the same defect that made the star fan-out
unreadable in the original incident — the diagonal arrows crossed the tier
labels. Declare `routing` per edge (`orthogonal` | `curved` | `straight`,
default `orthogonal`); the checker warns on `straight` for flow/decision
views. This is advisory because whether a specific arrow visually crosses a
specific label can only be confirmed at step 5 (screenshot read-back), not
from the spec's topology alone. See `references/legibility_rules.md`.

## Common Mistakes

### WRONG: fan-out for a gated sequence (the star)
A detector → lock → tier-1 → tier-2 → tier-3 escalation ladder drawn as one
node fanning out to 5 tier boxes with no gates. Looks like parallel options;
is actually an ordered, gated sequence.

### RIGHT: decision_tree with gates
`detector` → `lock` gate → `tier_1` → `resolved?` gate → (`resume` terminal |
`tier_2`) → ... Each gate's edges carry `branch_label: "yes"/"no"`.

### WRONG: labels overlapping arrows or boxes
Long node text left at renderer defaults, straight diagonal arrows crossing
under the text.

### RIGHT: short labels, routed connectors
Node labels under the limit; orthogonal/curved edges routed around boxes and
text (see Connector routing above).

### WRONG: no decision gates on a branching flow
Two outgoing edges from a node with no gate marking it a decision point —
readers can't tell it's a choice vs. two unconditional continuations.

### RIGHT: explicit gates with labeled branches
Declare the node in `gates[]`; label every outgoing edge `yes`/`no` (or the
actual branch condition).

### WRONG: no terminal states
A flow that trails off with edges but never reaches a node in
`terminal_states[]` — readers can't tell where it ends.

### RIGHT: explicit terminal states
List every ending node (`resume`, `escalate`, `done`, `failed`, ...) in
`terminal_states[]`.

### WRONG: grabbing the one-command describe/template because it's fast
`ops-excalidraw describe` or a fan-out template is one command — but running
it before choosing the view is how the star-for-sequence bug happened.

### RIGHT: view choice before template/render command
Steps 1–2 above happen before any renderer or template command is invoked.

## Limits (do not overclaim)

- The checker proves **topology and label-length** claims deterministically.
  It does NOT prove that a rendered arrow visually crosses a label — that is
  advisory (`CONNECTOR_ROUTING_STRAIGHT`) and requires the step-5 screenshot
  read-back for real confirmation.
- `MISSING_GATES`/`UNLABELED_BRANCH` detect the *absence* of gate/label
  metadata in the spec, not whether the eventual rendered diagram visually
  communicates the decision — still requires read-back.
