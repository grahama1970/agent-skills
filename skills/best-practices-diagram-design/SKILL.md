---
name: best-practices-diagram-design
description: >
  Validate diagram meaning and rendered geometry before publication. Use when
  selecting or reviewing flowcharts, decision trees, sequences, lifecycles,
  fanouts, swimlanes, C4/architecture diagrams, or Excalidraw templates.
triggers:
  - design a diagram
  - diagram design
  - diagram template
  - decision tree vs flowchart
  - diagram legibility
  - review a diagram
provides:
  - diagram-semantic-validation
  - rendered-diagram-geometry-validation
  - diagram-template-eligibility-guidance
composes:
  - create-architecture
  - ops-excalidraw
  - create-svg
  - jev
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

A diagram passes only when it preserves the approved process **and** its rendered scene is legible. Do not reject a star merely because it is star-shaped, or a connector merely because it is straight. A star can correctly show independent relationships; a beautifully routed drawing can still describe the wrong process.

## Required acceptance chain

```text
requirements → semantic spec → semantic checks → render → measured scene
             → geometry checks → screenshot review → publication
```

Missing adapters, fonts, or mandatory checks mean `UNVERIFIED`, never PASS.

## 1. Record immutable requirements

Before choosing a view, record source-backed `requirements` in the typed JSON spec:

- `intent`
- `required_order`
- `required_preconditions[]`: `{target, gate, outcome}`
- `required_outcome_targets[]`: `{gate, outcome, target}`

Rendering and layout repair must not alter this fragment. This proves preservation of an approved contract; it does not prove the contract was extracted correctly.

## 2. Choose the semantic view, then the renderer

| Reader question | View |
|---|---|
| What happens next, including decisions, retries, and shared endings? | `flowchart` |
| Which mutually exclusive choices lead to distinct leaves? | strict `decision_tree` |
| Which actor sends what, and in what order? | `sequence` |
| What states exist and what triggers transitions? | `lifecycle` |
| What exists, owns, contains, or depends on what? | `structure` |
| What executes concurrently and how does it complete? | `flowchart` with typed fork/join |
| What independent relationships radiate from one source? | `fanout` |

The gated-escalation example is a **flowchart**, because success branches merge into a shared `resume` endpoint. “Acquire lock” is an action; “Lock acquired?” is a decision.

## 3. Run semantic checks

```bash
./run.sh check path/to/spec.json --json
```

The checker uses `node.kind` (`action`, `decision`, `terminal`, `handoff`, `fork`, `join`) as canonical semantics and examines control-flow edges separately from annotations/dependencies.

Important deterministic errors:

- `INTENT_VIEW_MISMATCH`
- `REQUIRED_RELATION_MISSING`
- `REQUIRED_ORDER_VIOLATED`
- `PRECONDITION_BYPASS` — includes a concrete bypass path
- `UNREACHABLE_PROCESS_NODE`
- `TERMINAL_HAS_CONTINUATION`
- `DECISION_OUTCOMES_INVALID`
- `BRANCH_LABEL_MISMATCH`
- `TREE_TOPOLOGY_INVALID`
- `MISSING_GATES`, `UNLABELED_BRANCH`, `MISSING_TERMINAL_STATE`

`CONDITION_COVERAGE_UNVERIFIED` is advisory for free-text predicates without a finite Boolean/enum domain. `LABEL_TOO_LONG` is authoring guidance; measured fit is the hard rendered gate. `FANOUT_TOO_MANY` is the current `create-svg` adapter ceiling, not a universal design rule.

### Why `PRECONDITION_BYPASS` matters

For each required `{target, gate, outcome}`, the checker removes that required gate/outcome edge and searches from every entry. If the target remains reachable, the process is wrong regardless of layout. A fanout star that bypasses tier gates fails; a legitimate independent fanout passes.

## 4. Select a template or renderer

Use the small typed catalog in `references/template-catalog.md` rather than redrawing repeated patterns. Deterministic eligibility runs first. `$jev` may choose among the locally enumerated eligible templates; because Jev is a closed-set classifier, it must abstain/fall back rather than invent a template.

`ops-excalidraw` owns parameterized template rendering. This skill owns eligibility and acceptance. A template passing once does not qualify all populated instances.

## 5. Check actual rendered geometry

For the implemented Graphviz SVG adapter:

```bash
./run.sh geometry rendered.svg --json
```

It reads renderer-produced shapes, text, paths, transforms, stroke widths, and viewport. It does not trust author-written collision metadata.

Deterministic errors:

- `NODE_OVERLAP`
- `TEXT_OUTSIDE_CONTAINER`
- `EDGE_TEXT_INTERSECTION`
- `EDGE_NODE_INTERSECTION`
- `CONTENT_CLIPPED`

`ROUTING_NOT_REALIZED` is advisory. A clean straight edge passes; an orthogonal or curved edge crossing text fails. Geometry support is currently Graphviz SVG only. Mermaid and Excalidraw remain `UNVERIFIED` until normalized-scene adapters and fixtures exist; see `references/roadmap.md`.

## 6. Screenshot acceptance

Inspect the actual intended reading size with Surf/`ops-excalidraw`: reading order, emphasis, crowding, branch comprehension, and whether the diagram answers its stated question. Screenshot judgment supplements semantic and geometry checks; it cannot replace them.

## Validation

```bash
bash sanity.sh
```

The retained mutations prove: a correct gated escalation passes; a relabeled star and an unrelated-gate variant still fail by semantics; a direct tier bypass returns a path; swapped branch labels fail; a five-target independent fanout passes semantics but hits only the adapter ceiling; clean straight Graphviz geometry passes; overlap, overflow, and connector intersection fixtures fail.

Research provenance: `references/webgpt-design-review.md`. Template plan: `references/template-catalog.md`.
