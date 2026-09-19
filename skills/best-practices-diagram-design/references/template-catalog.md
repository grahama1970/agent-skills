# Parameterized diagram-template catalog

Source: `$ask webgpt` follow-up.

A template catalog is the generation complement to the semantic and geometry gates. The agent should request `gated-escalation/v1` with typed tier and outcome data, not manually place boxes and arrows.

## Initial catalog

| Template | Contract |
|---|---|
| `gated-escalation` | Ordered tiers, decisions, early-success exits, final handoff. It cannot expose an option that converts stages into independent fanout targets. |
| `sequential-pipeline` | Ordered stages without conditional branching. |
| `decision-flow` | Explicit choices, finite labeled outcomes, and optional shared endings. |
| `parallel-fork-join` | Genuine concurrent work with declared `all`, `any`, or `detached` completion policy. |
| `swimlane-process` | Control flow with responsible actor/service lanes. |
| `c4-container` | Declared scope, system boundaries, containers, external systems, and labeled relationships. |

Each qualified entry carries an input schema, supported size range, style tokens, pinned renderer and adapter versions, preview, and semantic/geometry mutation fixtures. A template passing once does not qualify every populated instance: longer labels and additional stages can break geometry.

## Reuse before invention

Candidate sources:

- `github/awesome-copilot` `excalidraw-diagram-generator` native starters.
- Official Excalidraw Libraries for C4, architecture, and UML activity symbols.
- `@excalidraw/mermaid-to-excalidraw`; flowcharts become native elements, while other views may become images.
- `coctostan/pi-excalidraw`; relevant to Pi template save/list/apply, but browser-connected and not fully headless.

Pin `@excalidraw/excalidraw` when using `convertToExcalidrawElements()`; its simplified API is beta and is not an automatic layout engine.

## Ownership and selection

- `ops-excalidraw` owns template implementation and parameterized rendering.
- `best-practices-diagram-design` owns template eligibility and acceptance.
- Deterministic eligibility filters the catalog first.
- `$jev` may select among the remaining locally enumerated candidates as a closed-set judgment. Jev abstention falls back to the normal LLM/human route; Jev never invents a template or overrides a failed eligibility rule.
- Every generated instance still runs semantic checks, rendered-geometry checks, and screenshot acceptance.
