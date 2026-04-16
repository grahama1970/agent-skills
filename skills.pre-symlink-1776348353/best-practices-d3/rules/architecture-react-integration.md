# architecture-react-integration

**Severity**: error
**Category**: architecture

## Rule

When using D3 inside React, let React own the DOM and D3 own the math. Use D3 for scales, layouts, and data transforms — use React for rendering SVG elements. Only use D3's DOM manipulation (`d3.select`) inside a `useEffect` with a ref, and clean up on unmount.

## Bad

```typescript
// D3 and React fighting over the same DOM
function Chart({ data }) {
  useEffect(() => {
    d3.select("#chart").selectAll("*").remove();  // nuke React's DOM
    d3.select("#chart").append("svg")...          // D3 takes over
  }, [data]);
  return <div id="chart" />;
}
```

## Good — React renders, D3 computes

```typescript
function Chart({ data }: { data: Point[] }) {
  const x = d3.scaleLinear()
    .domain(d3.extent(data, d => d.x) as [number, number])
    .range([0, innerWidth]).nice();

  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="...">
      <g transform={`translate(${margin.left},${margin.top})`}>
        {data.map(d => (
          <circle key={d.id} cx={x(d.x)} cy={y(d.y)} r={3} />
        ))}
      </g>
    </svg>
  );
}
```

## Good — D3 imperative with ref (for complex animations/transitions)

```typescript
function ForceGraph({ data }: { data: GraphData }) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current) return;
    const svg = d3.select(svgRef.current);
    // D3 imperative code here — owns this subtree
    const sim = d3.forceSimulation(data.nodes)...;

    return () => { sim.stop(); svg.selectAll("*").remove(); };
  }, [data]);

  return <svg ref={svgRef} viewBox="..." />;
}
```

## When to use which

| Pattern | When |
|---------|------|
| React renders SVG | Static charts, bar/line/scatter, tooltips via React state |
| D3 imperative + ref | Force layouts, brush/zoom, complex transitions, Canvas |
