# performance-hybrid-rendering

**Severity**: warn
**Category**: performance

## Rule

For large datasets, use a hybrid approach: Canvas for the data layer (points, edges, areas), SVG for the chrome layer (axes, labels, legends). This gives Canvas performance with SVG text quality.

## Good

```typescript
// Layer 1: Canvas for data (thousands of points)
const canvas = container.append("canvas")
  .attr("width", width * dpr).attr("height", height * dpr)
  .style("width", `${width}px`).style("height", `${height}px`)
  .style("position", "absolute");

const ctx = canvas.node()!.getContext("2d")!;
ctx.scale(dpr, dpr);

// Layer 2: SVG for axes and labels (crisp text, accessible)
const svg = container.append("svg")
  .attr("viewBox", `0 0 ${width} ${height}`)
  .style("position", "absolute")
  .style("pointer-events", "none");  // let Canvas handle interaction

// Render data to Canvas
function renderData(data: Point[]) {
  ctx.clearRect(0, 0, width, height);
  for (const d of data) {
    ctx.beginPath();
    ctx.arc(x(d.x), y(d.y), 2, 0, Math.PI * 2);
    ctx.fillStyle = color(d.category);
    ctx.fill();
  }
}

// Render axes to SVG
svg.append("g").call(d3.axisBottom(x));
svg.append("g").call(d3.axisLeft(y));
```

## Thresholds

| Elements | Strategy |
|----------|----------|
| < 1000 | Pure SVG |
| 1000-5000 | Hybrid (Canvas data + SVG chrome) |
| > 5000 | Full Canvas or WebGL |

## Why

SVG text renders crisply at any zoom and is accessible to screen readers. Canvas pixels are resolution-dependent and invisible to assistive technology. The hybrid approach gives you fast rendering for data AND accessible, crisp axes.
