# layout-margin-convention

**Severity**: warn
**Category**: layout

## Rule

Use the D3 margin convention: a `<g>` element translated by `(margin.left, margin.top)`, with inner width/height computed as `width - margin.left - margin.right`.

## Good

```typescript
const margin = { top: 20, right: 30, bottom: 40, left: 50 };
const innerWidth = width - margin.left - margin.right;
const innerHeight = height - margin.top - margin.bottom;

const g = svg.append("g")
  .attr("transform", `translate(${margin.left},${margin.top})`);

// All drawing happens inside g, using innerWidth/innerHeight for scales
const x = d3.scaleLinear().range([0, innerWidth]);
const y = d3.scaleLinear().range([innerHeight, 0]);
```

## Why

Without margins, axis labels clip outside the SVG bounds. The margin convention is universal in D3 — every example, tutorial, and production chart uses it. Deviating makes the code unreadable to anyone familiar with D3.
