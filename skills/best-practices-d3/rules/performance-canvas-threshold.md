# performance-canvas-threshold

**Severity**: error
**Category**: performance

## Rule

Switch from SVG to Canvas rendering when visualizing more than ~500-1000 elements. SVG DOM nodes are expensive — each one is a full DOM element with event handling, styling, and layout.

## Bad

```typescript
// 5000 SVG circles — browser will lag on hover, scroll, and resize
svg.selectAll("circle")
  .data(largeDataset)  // 5000+ points
  .join("circle")
  .attr("r", 2);
```

## Good

```typescript
const canvas = d3.select(container).append("canvas")
  .attr("width", width * devicePixelRatio)
  .attr("height", height * devicePixelRatio)
  .style("width", `${width}px`)
  .style("height", `${height}px`);

const ctx = canvas.node()!.getContext("2d")!;
ctx.scale(devicePixelRatio, devicePixelRatio);

function render(data: Point[]) {
  ctx.clearRect(0, 0, width, height);
  for (const d of data) {
    ctx.beginPath();
    ctx.arc(x(d.x), y(d.y), 2, 0, 2 * Math.PI);
    ctx.fill();
  }
}
```

## Thresholds

| Elements | Recommendation |
|----------|---------------|
| < 500 | SVG (full interactivity via DOM) |
| 500-5000 | Canvas with quadtree hit-testing for interaction |
| > 5000 | Canvas + WebGL (via regl, deck.gl, or raw WebGL) |

## Why

SVG with 5000+ elements causes:
- 60fps drops to <10fps on hover/transition
- Layout thrashing on any DOM mutation
- Memory bloat (each SVG element ~1KB overhead)

Canvas draws pixels directly — 100K points render in <16ms. Use `d3-quadtree` for hit-testing to restore interactivity.
