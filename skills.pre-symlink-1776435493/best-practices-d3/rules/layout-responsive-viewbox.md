# layout-responsive-viewbox

**Severity**: error
**Category**: layout

## Rule

Use `viewBox` on the SVG element instead of hardcoded `width`/`height` attributes. Derive actual pixel dimensions from the container via `ResizeObserver`.

## Bad

```typescript
const svg = d3.select("#chart")
  .append("svg")
  .attr("width", 800)
  .attr("height", 400);  // fixed size, breaks on resize
```

## Good

```typescript
const margin = { top: 20, right: 30, bottom: 40, left: 50 };
const container = document.getElementById("chart")!;
const { width, height } = container.getBoundingClientRect();
const innerWidth = width - margin.left - margin.right;
const innerHeight = height - margin.top - margin.bottom;

const svg = d3.select(container)
  .append("svg")
  .attr("viewBox", `0 0 ${width} ${height}`)
  .attr("preserveAspectRatio", "xMidYMid meet");

const g = svg.append("g")
  .attr("transform", `translate(${margin.left},${margin.top})`);
```

## Why

Hardcoded dimensions break on mobile, in resizable panels, and in split views. `viewBox` makes the SVG scale to its container. The margin convention (`g` with transform) keeps axes from clipping.
