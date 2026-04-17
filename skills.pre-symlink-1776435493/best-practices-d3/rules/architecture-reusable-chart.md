# architecture-reusable-chart

**Severity**: warn
**Category**: architecture

## Rule

Structure reusable D3 charts as functions that accept a container element and a config object. Don't scatter D3 code across React lifecycle hooks.

## Good

```typescript
interface ChartConfig {
  data: Point[];
  width: number;
  height: number;
  margin?: Margin;
  colorScheme?: readonly string[];
  onHover?: (d: Point | null) => void;
}

function renderScatter(container: SVGGElement, config: ChartConfig) {
  const { data, width, height, margin = DEFAULT_MARGIN } = config;
  const innerWidth = width - margin.left - margin.right;
  const innerHeight = height - margin.top - margin.bottom;

  const x = d3.scaleLinear()
    .domain(d3.extent(data, d => d.x) as [number, number])
    .range([0, innerWidth]).nice();

  const sel = d3.select(container);
  sel.selectAll("circle")
    .data(data, (d: any) => d.id)
    .join("circle")
    .attr("cx", d => x(d.x))
    .attr("cy", d => y(d.y))
    .attr("r", 3);
}
```

## Why

A chart function that takes `(container, config)` is testable, composable, and framework-agnostic. It works with React refs, vanilla JS, and server-side rendering. Scattering D3 calls across `useEffect`, `useMemo`, and event handlers makes charts impossible to maintain.
