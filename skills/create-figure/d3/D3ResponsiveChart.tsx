/**
 * D3ResponsiveChart — fallback D3 renderer for structured data.
 *
 * Used when the agent returns JSON data instead of a pre-rendered figure.
 * Supports bar, hbar, area, line, scatter, pie, radar, heatmap, bubble,
 * histogram, waterfall, funnel, and gauge chart types.
 * Distance-aware: 18px+ labels, 2-3px strokes, 800ms animations.
 */
import React, { useEffect, useRef } from "react";
import * as d3 from "d3";

export type ChartType =
  | "bar"
  | "hbar"
  | "area"
  | "line"
  | "scatter"
  | "pie"
  | "radar"
  | "heatmap"
  | "bubble"
  | "histogram"
  | "waterfall"
  | "funnel"
  | "gauge";

export type ChartDataPoint = {
  label: string;
  value: number;
  group?: string;
  x?: number;
  y?: number;
  size?: number;
  row?: string;
  col?: string;
  max?: number;
};

type Props = {
  data: ChartDataPoint[];
  chartType?: ChartType;
  accentHsl?: string;
  title?: string;
};

const FONT_SIZE = 18;
const STROKE_WIDTH = 2;
const ANIM_MS = 800;

const COLORS = [
  "hsl(217, 91%, 60%)", // blue
  "hsl(270, 60%, 55%)", // purple
  "hsl(142, 76%, 36%)", // green
  "hsl(25, 95%, 53%)",  // orange
  "hsl(0, 84%, 60%)",   // red
  "hsl(199, 89%, 48%)", // cyan
];

type SVG = d3.Selection<SVGSVGElement, unknown, null, undefined>;
type Margin = { top: number; right: number; bottom: number; left: number };

export default function D3ResponsiveChart({ data, chartType = "bar", accentHsl, title }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !containerRef.current || data.length === 0) return;

    let mounted = true;
    const observer = new ResizeObserver(() => { if (mounted) draw(); });
    observer.observe(containerRef.current);
    draw();

    return () => { mounted = false; observer.disconnect(); };

    function draw() {
      const container = containerRef.current!;
      const svg = d3.select(svgRef.current!);
      svg.selectAll("*").remove();

      const rect = container.getBoundingClientRect();
      const width = rect.width;
      const height = rect.height;
      const margin: Margin = { top: 40, right: 24, bottom: 60, left: 64 };

      svg.attr("viewBox", `0 0 ${width} ${height}`);

      if (title) {
        svg.append("text")
          .attr("x", width / 2)
          .attr("y", 28)
          .attr("text-anchor", "middle")
          .attr("fill", "currentColor")
          .attr("font-size", "24px")
          .attr("font-weight", "700")
          .text(title);
      }

      const primary = accentHsl ? `hsl(${accentHsl})` : COLORS[0];

      const drawFn = CHART_DRAWERS[chartType] ?? drawBar;
      drawFn(svg, data, width, height, margin, primary);
    }
  }, [data, chartType, accentHsl, title]);

  return (
    <div ref={containerRef} className="w-full h-full min-h-[300px]">
      <svg ref={svgRef} className="w-full h-full" />
    </div>
  );
}

function styleAxes(svg: SVG) {
  svg.selectAll(".domain, .tick line")
    .attr("stroke", "currentColor")
    .attr("stroke-opacity", 0.3);
}

function addXAxis(svg: SVG, scale: d3.AxisScale<string>, height: number, margin: Margin) {
  svg.append("g")
    .attr("transform", `translate(0,${height - margin.bottom})`)
    .call(d3.axisBottom(scale).tickSizeOuter(0))
    .selectAll("text")
    .attr("font-size", `${FONT_SIZE}px`)
    .attr("fill", "currentColor");
}

function addYAxis(svg: SVG, scale: d3.AxisScale<number>, margin: Margin) {
  svg.append("g")
    .attr("transform", `translate(${margin.left},0)`)
    .call(d3.axisLeft(scale).ticks(5))
    .selectAll("text")
    .attr("font-size", `${FONT_SIZE}px`)
    .attr("fill", "currentColor");
}

function addLinearXAxis(svg: SVG, scale: d3.AxisScale<number>, height: number, margin: Margin, ticks = 5) {
  svg.append("g")
    .attr("transform", `translate(0,${height - margin.bottom})`)
    .call(d3.axisBottom(scale).ticks(ticks))
    .selectAll("text")
    .attr("font-size", `${FONT_SIZE}px`)
    .attr("fill", "currentColor");
}

function addBandYAxis(svg: SVG, scale: d3.AxisScale<string>, margin: Margin) {
  svg.append("g")
    .attr("transform", `translate(${margin.left},0)`)
    .call(d3.axisLeft(scale).tickSizeOuter(0))
    .selectAll("text")
    .attr("font-size", `${FONT_SIZE}px`)
    .attr("fill", "currentColor");
}

// --- Chart draw functions ---

type DrawFn = (svg: SVG, data: ChartDataPoint[], w: number, h: number, m: Margin, color: string) => void;

function drawBar(svg: SVG, data: ChartDataPoint[], w: number, h: number, m: Margin, _color: string) {
  const x = d3.scaleBand().domain(data.map((d) => d.label)).range([m.left, w - m.right]).padding(0.3);
  const y = d3.scaleLinear().domain([0, d3.max(data, (d) => d.value) ?? 1]).nice().range([h - m.bottom, m.top]);

  svg.selectAll("rect").data(data).join("rect")
    .attr("x", (d) => x(d.label)!)
    .attr("width", x.bandwidth())
    .attr("y", h - m.bottom).attr("height", 0)
    .attr("rx", 4)
    .attr("fill", (_, i) => COLORS[i % COLORS.length])
    .attr("opacity", 0.85)
    .transition().duration(ANIM_MS).ease(d3.easeCubicOut)
    .attr("y", (d) => y(d.value))
    .attr("height", (d) => h - m.bottom - y(d.value));

  addXAxis(svg, x, h, m);
  addYAxis(svg, y, m);
  styleAxes(svg);
}

function drawHbar(svg: SVG, data: ChartDataPoint[], w: number, h: number, m: Margin, _color: string) {
  const hm: Margin = { ...m, left: 120 };
  const y = d3.scaleBand().domain(data.map((d) => d.label)).range([hm.top, h - hm.bottom]).padding(0.3);
  const x = d3.scaleLinear().domain([0, d3.max(data, (d) => d.value) ?? 1]).nice().range([hm.left, w - hm.right]);

  svg.selectAll("rect").data(data).join("rect")
    .attr("y", (d) => y(d.label)!)
    .attr("height", y.bandwidth())
    .attr("x", hm.left).attr("width", 0)
    .attr("rx", 4)
    .attr("fill", (_, i) => COLORS[i % COLORS.length])
    .attr("opacity", 0.85)
    .transition().duration(ANIM_MS).ease(d3.easeCubicOut)
    .attr("width", (d) => x(d.value) - hm.left);

  addBandYAxis(svg, y, hm);
  addLinearXAxis(svg, x, h, hm);
  styleAxes(svg);
}

function drawArea(svg: SVG, data: ChartDataPoint[], w: number, h: number, m: Margin, color: string) {
  const x = d3.scalePoint().domain(data.map((d) => d.label)).range([m.left, w - m.right]).padding(0.5);
  const y = d3.scaleLinear().domain([0, d3.max(data, (d) => d.value) ?? 1]).nice().range([h - m.bottom, m.top]);

  const area = d3.area<ChartDataPoint>()
    .x((d) => x(d.label)!)
    .y0(h - m.bottom)
    .y1((d) => y(d.value))
    .curve(d3.curveMonotoneX);

  svg.append("path").datum(data)
    .attr("fill", color).attr("fill-opacity", 0.3)
    .attr("d", area);

  const line = d3.line<ChartDataPoint>()
    .x((d) => x(d.label)!)
    .y((d) => y(d.value))
    .curve(d3.curveMonotoneX);

  const path = svg.append("path").datum(data)
    .attr("fill", "none").attr("stroke", color)
    .attr("stroke-width", STROKE_WIDTH + 1).attr("d", line);

  const totalLength = (path.node() as SVGPathElement)?.getTotalLength() ?? 0;
  path.attr("stroke-dasharray", `${totalLength} ${totalLength}`)
    .attr("stroke-dashoffset", totalLength)
    .transition().duration(ANIM_MS).ease(d3.easeCubicOut)
    .attr("stroke-dashoffset", 0);

  addXAxis(svg, x, h, m);
  addYAxis(svg, y, m);
  styleAxes(svg);
}

function drawLineOrScatter(svg: SVG, data: ChartDataPoint[], w: number, h: number, m: Margin, color: string) {
  drawLineOrScatterImpl(svg, data, w, h, m, color, "line");
}

function drawScatter(svg: SVG, data: ChartDataPoint[], w: number, h: number, m: Margin, color: string) {
  drawLineOrScatterImpl(svg, data, w, h, m, color, "scatter");
}

function drawLineOrScatterImpl(svg: SVG, data: ChartDataPoint[], w: number, h: number, m: Margin, color: string, type: "line" | "scatter") {
  const x = d3.scalePoint().domain(data.map((d) => d.label)).range([m.left, w - m.right]).padding(0.5);
  const y = d3.scaleLinear().domain([0, d3.max(data, (d) => d.value) ?? 1]).nice().range([h - m.bottom, m.top]);

  if (type === "line") {
    const line = d3.line<ChartDataPoint>().x((d) => x(d.label)!).y((d) => y(d.value)).curve(d3.curveMonotoneX);
    const path = svg.append("path").datum(data)
      .attr("fill", "none").attr("stroke", color).attr("stroke-width", 3).attr("d", line);
    const totalLength = (path.node() as SVGPathElement)?.getTotalLength() ?? 0;
    path.attr("stroke-dasharray", `${totalLength} ${totalLength}`)
      .attr("stroke-dashoffset", totalLength)
      .transition().duration(ANIM_MS).ease(d3.easeCubicOut).attr("stroke-dashoffset", 0);
  }

  svg.selectAll("circle").data(data).join("circle")
    .attr("cx", (d) => x(d.label)!).attr("cy", (d) => y(d.value))
    .attr("r", 0).attr("fill", color)
    .transition().duration(ANIM_MS).ease(d3.easeCubicOut).attr("r", 5);

  addXAxis(svg, x, h, m);
  addYAxis(svg, y, m);
  styleAxes(svg);
}

function drawPie(svg: SVG, data: ChartDataPoint[], w: number, h: number, _m: Margin, _color: string) {
  const radius = Math.min(w, h) / 2 - 60;
  const g = svg.append("g").attr("transform", `translate(${w / 2},${h / 2})`);

  const pie = d3.pie<ChartDataPoint>().value((d) => d.value).sort(null);
  const arc = d3.arc<d3.PieArcDatum<ChartDataPoint>>().innerRadius(radius * 0.4).outerRadius(radius);

  g.selectAll("path").data(pie(data)).join("path")
    .attr("fill", (_, i) => COLORS[i % COLORS.length])
    .attr("opacity", 0.85)
    .attr("stroke", "hsl(var(--background))").attr("stroke-width", 2)
    .transition().duration(ANIM_MS).ease(d3.easeCubicOut)
    .attrTween("d", function (d) {
      const interp = d3.interpolate({ startAngle: 0, endAngle: 0 }, d);
      return (t: number) => arc(interp(t)) ?? "";
    });

  const labelArc = d3.arc<d3.PieArcDatum<ChartDataPoint>>().innerRadius(radius * 0.75).outerRadius(radius * 0.75);
  g.selectAll("text").data(pie(data)).join("text")
    .attr("transform", (d) => `translate(${labelArc.centroid(d)})`)
    .attr("text-anchor", "middle").attr("font-size", `${FONT_SIZE}px`)
    .attr("fill", "currentColor").attr("opacity", 0)
    .text((d) => d.data.label)
    .transition().delay(600).duration(400).attr("opacity", 1);
}

function drawRadar(svg: SVG, data: ChartDataPoint[], w: number, h: number, _m: Margin, _color: string) {
  const size = Math.min(w, h);
  const margin = 80;
  const radius = size / 2 - margin;
  const cx = w / 2;
  const cy = h / 2;
  const n = data.length;
  const angleSlice = (2 * Math.PI) / n;
  const maxVal = d3.max(data, (d) => d.value) ?? 1;

  const g = svg.append("g").attr("transform", `translate(${cx},${cy})`);

  // Grid circles
  [0.25, 0.5, 0.75, 1.0].forEach((level) => {
    g.append("circle").attr("r", radius * level)
      .attr("fill", "none").attr("stroke", "currentColor").attr("stroke-opacity", 0.15);
  });

  // Axis lines + labels
  data.forEach((d, i) => {
    const angle = angleSlice * i - Math.PI / 2;
    const lx = Math.cos(angle) * radius;
    const ly = Math.sin(angle) * radius;

    g.append("line").attr("x1", 0).attr("y1", 0).attr("x2", lx).attr("y2", ly)
      .attr("stroke", "currentColor").attr("stroke-opacity", 0.15);

    g.append("text")
      .attr("x", Math.cos(angle) * (radius + 20))
      .attr("y", Math.sin(angle) * (radius + 20))
      .attr("text-anchor", "middle").attr("dominant-baseline", "central")
      .attr("font-size", `${FONT_SIZE}px`).attr("fill", "currentColor")
      .text(d.label);
  });

  // Data polygon
  const points: [number, number][] = data.map((d, i) => {
    const angle = angleSlice * i - Math.PI / 2;
    const r = (d.value / maxVal) * radius;
    return [Math.cos(angle) * r, Math.sin(angle) * r];
  });

  const line = d3.line<[number, number]>().curve(d3.curveLinearClosed);
  g.append("path").attr("d", line([...points, points[0]]))
    .attr("fill", COLORS[0]).attr("fill-opacity", 0.25)
    .attr("stroke", COLORS[0]).attr("stroke-width", STROKE_WIDTH + 1);

  g.selectAll("circle.dot").data(points).join("circle")
    .attr("cx", (d) => d[0]).attr("cy", (d) => d[1])
    .attr("r", 4).attr("fill", COLORS[0]);
}

function drawHeatmap(svg: SVG, data: ChartDataPoint[], w: number, h: number, _m: Margin, _color: string) {
  const hm: Margin = { top: 40, right: 60, bottom: 60, left: 100 };
  const rows = [...new Set(data.map((d) => d.row ?? d.label))];
  const cols = [...new Set(data.map((d) => d.col ?? d.group ?? ""))];

  const x = d3.scaleBand().domain(cols).range([hm.left, w - hm.right]).padding(0.05);
  const y = d3.scaleBand().domain(rows).range([hm.top, h - hm.bottom]).padding(0.05);

  const vals = data.map((d) => d.value);
  const color = d3.scaleSequential(d3.interpolateBlues).domain([d3.min(vals) ?? 0, d3.max(vals) ?? 1]);

  svg.selectAll("rect").data(data).join("rect")
    .attr("x", (d) => x(d.col ?? d.group ?? "")!)
    .attr("y", (d) => y(d.row ?? d.label)!)
    .attr("width", x.bandwidth()).attr("height", y.bandwidth())
    .attr("rx", 2).attr("fill", (d) => color(d.value))
    .attr("opacity", 0)
    .transition().duration(ANIM_MS).ease(d3.easeCubicOut).attr("opacity", 1);

  // Cell labels
  const maxVal = d3.max(vals) ?? 1;
  svg.selectAll("text.cell").data(data).join("text")
    .attr("x", (d) => (x(d.col ?? d.group ?? "") ?? 0) + x.bandwidth() / 2)
    .attr("y", (d) => (y(d.row ?? d.label) ?? 0) + y.bandwidth() / 2)
    .attr("text-anchor", "middle").attr("dominant-baseline", "central")
    .attr("font-size", `${FONT_SIZE}px`)
    .attr("fill", (d) => d.value > maxVal * 0.6 ? "white" : "currentColor")
    .text((d) => d.value.toFixed(1));

  svg.append("g").attr("transform", `translate(0,${h - hm.bottom})`)
    .call(d3.axisBottom(x).tickSizeOuter(0))
    .selectAll("text").attr("font-size", `${FONT_SIZE}px`).attr("fill", "currentColor");
  svg.append("g").attr("transform", `translate(${hm.left},0)`)
    .call(d3.axisLeft(y).tickSizeOuter(0))
    .selectAll("text").attr("font-size", `${FONT_SIZE}px`).attr("fill", "currentColor");
  styleAxes(svg);
}

function drawBubble(svg: SVG, data: ChartDataPoint[], w: number, h: number, m: Margin, _color: string) {
  const xVals = data.map((d) => d.x ?? 0);
  const yVals = data.map((d) => d.y ?? d.value);

  const x = d3.scaleLinear().domain(d3.extent(xVals) as [number, number]).nice().range([m.left, w - m.right]);
  const y = d3.scaleLinear().domain(d3.extent(yVals) as [number, number]).nice().range([h - m.bottom, m.top]);
  const r = d3.scaleSqrt().domain([0, d3.max(data, (d) => d.size ?? d.value) ?? 1]).range([4, 40]);
  const color = d3.scaleOrdinal(d3.schemeTableau10);

  svg.selectAll("circle").data(data).join("circle")
    .attr("cx", (d) => x(d.x ?? 0)).attr("cy", (d) => y(d.y ?? d.value))
    .attr("r", 0)
    .attr("fill", (d, i) => color(d.group ?? d.label ?? String(i)))
    .attr("fill-opacity", 0.7)
    .attr("stroke", (d, i) => color(d.group ?? d.label ?? String(i)))
    .attr("stroke-width", 1)
    .transition().duration(ANIM_MS).ease(d3.easeCubicOut)
    .attr("r", (d) => r(d.size ?? d.value));

  addLinearXAxis(svg, x, h, m);
  addYAxis(svg, y, m);
  styleAxes(svg);
}

function drawHistogram(svg: SVG, data: ChartDataPoint[], w: number, h: number, m: Margin, _color: string) {
  const values = data.map((d) => d.value);
  const x = d3.scaleLinear().domain(d3.extent(values) as [number, number]).nice().range([m.left, w - m.right]);
  const bins = d3.bin().domain(x.domain() as [number, number]).thresholds(x.ticks(20))(values);
  const y = d3.scaleLinear().domain([0, d3.max(bins, (b) => b.length) ?? 1]).nice().range([h - m.bottom, m.top]);

  svg.selectAll("rect").data(bins).join("rect")
    .attr("x", (d) => x(d.x0!) + 1)
    .attr("width", (d) => Math.max(0, x(d.x1!) - x(d.x0!) - 2))
    .attr("y", h - m.bottom).attr("height", 0)
    .attr("fill", COLORS[0]).attr("opacity", 0.75)
    .transition().duration(ANIM_MS).ease(d3.easeCubicOut)
    .attr("y", (d) => y(d.length))
    .attr("height", (d) => h - m.bottom - y(d.length));

  addLinearXAxis(svg, x, h, m, 10);
  addYAxis(svg, y, m);
  styleAxes(svg);
}

function drawWaterfall(svg: SVG, data: ChartDataPoint[], w: number, h: number, m: Margin, _color: string) {
  let cumulative = 0;
  const wfData = data.map((d) => {
    const start = cumulative;
    cumulative += d.value;
    return { ...d, start, end: cumulative, isNeg: d.value < 0 };
  });

  const x = d3.scaleBand().domain(data.map((d) => d.label)).range([m.left, w - m.right]).padding(0.3);
  const y = d3.scaleLinear()
    .domain([
      d3.min(wfData, (d) => Math.min(d.start, d.end)) ?? 0,
      d3.max(wfData, (d) => Math.max(d.start, d.end)) ?? 1,
    ]).nice().range([h - m.bottom, m.top]);

  svg.selectAll("rect").data(wfData).join("rect")
    .attr("x", (d) => x(d.label)!)
    .attr("width", x.bandwidth())
    .attr("y", (d) => y(Math.max(d.start, d.end)))
    .attr("height", (d) => Math.abs(y(d.start) - y(d.end)))
    .attr("rx", 3)
    .attr("fill", (d) => d.isNeg ? "hsl(0, 84%, 60%)" : "hsl(142, 76%, 36%)")
    .attr("opacity", 0.85);

  // Connector lines
  wfData.forEach((d, i) => {
    if (i < wfData.length - 1) {
      svg.append("line")
        .attr("x1", x(d.label)! + x.bandwidth())
        .attr("x2", x(wfData[i + 1].label)!)
        .attr("y1", y(d.end)).attr("y2", y(d.end))
        .attr("stroke", "currentColor").attr("stroke-opacity", 0.3)
        .attr("stroke-dasharray", "4,2");
    }
  });

  addXAxis(svg, x, h, m);
  addYAxis(svg, y, m);
  styleAxes(svg);
}

function drawFunnel(svg: SVG, data: ChartDataPoint[], w: number, h: number, m: Margin, _color: string) {
  const maxVal = d3.max(data, (d) => d.value) ?? 1;
  const stepH = (h - m.top - m.bottom) / data.length;
  const centerX = w / 2;

  data.forEach((d, i) => {
    const barW = (d.value / maxVal) * (w - m.left - m.right - 100);
    const yPos = m.top + i * stepH;

    svg.append("rect")
      .attr("x", centerX - barW / 2).attr("y", yPos + 2)
      .attr("width", barW).attr("height", stepH - 4)
      .attr("rx", 6)
      .attr("fill", COLORS[i % COLORS.length]).attr("opacity", 0.8);

    svg.append("text")
      .attr("x", centerX).attr("y", yPos + stepH / 2)
      .attr("text-anchor", "middle").attr("dominant-baseline", "central")
      .attr("font-size", `${FONT_SIZE}px`).attr("font-weight", "600")
      .attr("fill", "white")
      .text(`${d.label}: ${d.value}`);
  });
}

function drawGauge(svg: SVG, data: ChartDataPoint[], w: number, h: number, _m: Margin, _color: string) {
  const size = Math.min(w, h);
  const g = svg.append("g").attr("transform", `translate(${w / 2},${h * 0.55})`);
  const radius = size * 0.4;
  const val = data[0]?.value ?? 0;
  const maxVal = data[0]?.max ?? 100;
  const pct = Math.min(1, val / maxVal);

  const arcBg = d3.arc<unknown>()
    .innerRadius(radius * 0.7).outerRadius(radius)
    .startAngle(-Math.PI / 2).endAngle(Math.PI / 2);

  g.append("path").attr("d", arcBg({} as unknown) as string)
    .attr("fill", "currentColor").attr("fill-opacity", 0.1);

  const arcFg = d3.arc<unknown>()
    .innerRadius(radius * 0.7).outerRadius(radius)
    .startAngle(-Math.PI / 2);

  const fillColor = pct > 0.8 ? "hsl(142, 76%, 36%)" : pct > 0.5 ? "hsl(45, 93%, 47%)" : "hsl(0, 84%, 60%)";

  g.append("path").attr("fill", fillColor)
    .transition().duration(ANIM_MS).ease(d3.easeCubicOut)
    .attrTween("d", () => {
      const interp = d3.interpolate(-Math.PI / 2, -Math.PI / 2 + Math.PI * pct);
      return (t: number) => {
        const end = interp(t);
        return (arcFg.endAngle(end)({} as unknown) as string) ?? "";
      };
    });

  g.append("text")
    .attr("text-anchor", "middle").attr("y", -10)
    .attr("font-size", `${size * 0.12}px`).attr("font-weight", "700")
    .attr("fill", "currentColor")
    .text(`${(pct * 100).toFixed(0)}%`);

  g.append("text")
    .attr("text-anchor", "middle").attr("y", size * 0.06)
    .attr("font-size", `${FONT_SIZE}px`).attr("fill", "currentColor").attr("opacity", 0.6)
    .text(data[0]?.label ?? "");
}

const CHART_DRAWERS: Record<ChartType, DrawFn> = {
  bar: drawBar,
  hbar: drawHbar,
  area: drawArea,
  line: drawLineOrScatter,
  scatter: drawScatter,
  pie: drawPie,
  radar: drawRadar,
  heatmap: drawHeatmap,
  bubble: drawBubble,
  histogram: drawHistogram,
  waterfall: drawWaterfall,
  funnel: drawFunnel,
  gauge: drawGauge,
};
