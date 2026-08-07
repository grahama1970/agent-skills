---
name: best-practices-d3
description: |
  D3.js visualization best practices for performant, responsive, accessible
  data visualizations. Covers data joins, scales, axes, transitions, responsive
  SVG, interaction patterns, and accessibility.
  Use when writing, reviewing, or refactoring D3 visualizations.
triggers:
  - best practices d3
  - d3 visualization
  - d3 graph
  - d3 chart
  - svg visualization
  - data visualization
  - responsive chart
  - interactive graph
metadata:
  author: pi-mono
  version: "2.0.0"
  language: typescript
provides:
  - best-practices-d3
composes:
  - task-monitor
taxonomy:
  - precision
disciplines:
  - engineering-standards
  - ui-design-engineering
---

# D3 Best Practices

Production rules for performant, responsive, accessible D3.js visualizations.
D3 is a low-level visualization toolkit, not a charting library — these rules
enforce the patterns that make D3 code maintainable and fast.

## Rule Categories

| Category | Focus | Modern Requirement |
|----------|-------|-------------------|
| `rendering` | DOM ownership | Framework-declarative (React/Svelte) for DOM, D3 for math. |
| `data-join` | Enter/update/exit | Keyed joins are mandatory. Use `.join()` for concise lifecycle. |
| `layout` | Responsive SVG | `ResizeObserver` + `viewBox`. No hardcoded pixel dimensions. |
| `interaction` | Pointer events | `d3.pointer` for unified touch/mouse. Voronoi for precision. |
| `performance` | Layering | Canvas/Hybrid rendering for >1000 nodes. |
| `accessibility` | A11y | ARIA roles + Hidden data table + Reduced Motion support. |
| `architecture` | Documentation | Folder-level `DESIGN.md` for visual encoding logic. |

## When to Use

- Writing any D3 visualization in the codebase.
- Reviewing TSX/JSX that imports `d3` or `d3-*`.
- Optimizing slow graph rendering (>1000 nodes, real-time updates).
- Auditing accessibility of existing visualizations.
- Defining the visual mapping logic for new chart types.

## Critical Rules

1. **Always use keyed data joins** — `selection.data(data, d => d.id)`. Matches by identity, not index, to prevent corrupted transitions.
2. **Use viewBox + ResizeObserver** — Derive dimensions from the container's `contentRect`. Use `preserveAspectRatio` to maintain scales during fluid resize.
3. **Hybrid Rendering for Scale** — Use Canvas for heavy data layers and SVG for "Chrome" (Axes/Labels). Switch to full Canvas for >2000 elements.
4. **Declarative DOM, Imperative Math** — Let the UI framework (React/Svelte) handle element creation; use D3 for scales, paths, and interpolators.
5. **Functional Transitions** — Animate for "Object Constancy" (tracking points). Transitions must be 200-500ms and respect `prefers-reduced-motion`.

## Interaction Do's and Don'ts

* **DO** use **Voronoi Overlays** to make small targets "magnetic."
* **DO** use **Pointer Events** (`pointermove`) for unified cross-device support.
* **DON'T** rely on color alone; use redundant encoding (Shape, Pattern, or Labels).
* **DON'T** trigger layout-shifting animations (like changing `stroke-width`) on hover.

## Quick Checklist

```

□ Data join uses unique ID key (not index)
□ SVG uses viewBox; dimensions driven by ResizeObserver
□ DESIGN.md exists (explains Visual Encoding & Scale choices)
□ Logic Split: Framework manages DOM, D3 manages Math
□ Interaction uses pointer events + Voronoi for small targets
□ Transitions are 200-500ms and handle "Exit" before "Enter"
□ Color palette is colorblind-safe (d3-scale-chromatic)
□ Hidden \<table\> or \<ul\> provided for screen readers
□ Scales use .nice() and Axes use .tickFormat() for readability
□ \>1000 elements? Canvas/SVG Hybrid pattern implemented
□ Is a visualization the right medium? (see architecture-right-medium rule)
```

## Is D3 the Right Medium?

Before writing any D3 code, ask: could a sentence, table, or checklist
communicate this better? See the `architecture-right-medium` rule for
the full decision matrix. Key signals:

- **Single number** → text with context, not a gauge
- **Comparing <5 items** → table, not a bar chart
- **Exact lookup** → sortable table, not a chart
- **Pass/fail status** → checklist or badge grid, not a dashboard
- **Trend, distribution, or spatial pattern** → D3 is the right tool

## Creating New Chart Types

When no preset fits, follow this workflow:

1. **Write DESIGN.md first** — define the visual encoding table
   (data dimension → visual channel → scale type → justification)
   before touching code. See `architecture-design-md` rule.

2. **Validate the encoding** — walk through 3 example data points
   mentally. Does the mapping produce the right visual? Can you
   answer the chart's question by looking at it?

3. **Prototype with static data** — hardcode 10-20 data points.
   Get the layout, scales, and axes right before wiring real data.

4. **Add interaction last** — tooltips, zoom, brush. Each one
   should answer a specific question the static chart can't.

5. **Test at scale** — render with 10x the expected data volume.
   If it's slow, apply the hybrid rendering pattern.

6. **Accessibility pass** — add ARIA roles, hidden data table,
   colorblind check, reduced motion support.
