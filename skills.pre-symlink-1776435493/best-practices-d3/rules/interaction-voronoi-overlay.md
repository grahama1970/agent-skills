# interaction-voronoi-overlay

**Severity**: warn
**Category**: interaction

## Rule

Use Voronoi overlays to make small targets (scatter dots, graph nodes) interactive. A 3px circle has ~28px² hit area — a Voronoi cell covers the entire nearest region.

## Bad

```typescript
// 3px circles are nearly impossible to hover on touch/trackpad
circles.on("pointerenter", (event, d) => showTooltip(d));
```

## Good

```typescript
const voronoi = d3.Delaunay.from(data, d => x(d.x), d => y(d.y))
  .voronoi([0, 0, innerWidth, innerHeight]);

g.append("g")
  .selectAll("path")
  .data(data)
  .join("path")
  .attr("d", (_, i) => voronoi.renderCell(i))
  .attr("fill", "transparent")
  .attr("pointer-events", "all")
  .on("pointerenter", (event, d) => showTooltip(event, d))
  .on("pointerleave", hideTooltip);
```

## Why

Voronoi tessellation divides the chart area so every point on the surface belongs to the nearest data point. This makes the entire chart interactive — no dead zones, no precision clicking required. Essential for scatter plots and force-directed graphs.
