# architecture-design-md

**Severity**: warn
**Category**: architecture

## Rule

Every visualization directory must have a `DESIGN.md` that documents the visual encoding logic: what data dimension maps to what visual channel (position, size, color, shape), what scale type is used, and why.

## Good — `components/charts/risk-heatmap/DESIGN.md`

```markdown
# Risk Heatmap

## Visual Encoding

| Data Dimension | Visual Channel | Scale | Justification |
|---|---|---|---|
| Control family | X position | Band (categorical) | Families are discrete groups |
| Risk tier | Y position | Band (ordinal, High→Low) | Natural ordering top-down |
| Compliance % | Fill color | Sequential (interpolateRdYlGn) | Red=bad, green=good is universal |
| Finding count | Cell label | Direct text | Exact numbers matter for audit |

## Interaction

- Hover cell → tooltip with control name, exact %, and finding list
- Click cell → navigate to control detail (shared slide-over panel)
- Voronoi not needed — cells are large enough targets

## Responsiveness

- viewBox 960×400, scales down via container width
- Below 600px: rotate X labels 45°, hide Y axis title
```

## Why

D3 code without a design document is write-only. Six months later, nobody knows why the color scale is `interpolateRdYlGn` instead of `interpolateBlues`. The DESIGN.md captures the reasoning so the chart can be maintained, reviewed, and iterated without re-deriving every decision.
