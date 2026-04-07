"""Statistical and specialized chart generators for figure-lab compositions.

Contains generators for non-standard chart types that visualize distributions,
relationships, or specialized data shapes:
  - Radar/spider
  - Bubble
  - Heatmap
  - Histogram
  - Box plot
  - Waterfall
  - Funnel
  - Ridgeline
  - Beeswarm
  - Gauge

Each generator function takes (data_json, font_size, stroke_width, animation_ms)
and returns a JavaScript string with D3 code to render that chart type.
All generators produce self-contained D3 code that expects:
  - An ``#chart`` div container
  - D3 imported as ``* as d3`` via ESM
  - Distance-aware defaults (18px+ fonts, 2px+ strokes, 800ms animations)

Failure modes:
  - Returns empty string if data_json is malformed (caller should validate)
  - Generated JS may throw at runtime if data shape doesn't match chart expectations
"""
from __future__ import annotations

from figure_lab.config import CANVAS_FG


def gen_radar(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Radar/spider chart — data plotted on radial axes."""
    return f"""
const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const size = Math.min(rect.width || 600, rect.height || 600);
const margin = 80;
const radius = size / 2 - margin;

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{size}} ${{size}}`);

const g = svg.append('g').attr('transform', `translate(${{size/2}},${{size/2}})`);

const labels = data.map(d => d.label || d.name || d.axis);
const values = data.map(d => d.value || d.y || 0);
const maxVal = d3.max(values) || 1;
const n = labels.length;

// Grid circles
[0.25, 0.5, 0.75, 1.0].forEach(level => {{
  g.append('circle')
    .attr('r', radius * level)
    .attr('fill', 'none')
    .attr('stroke', '#e2e8f0')
    .attr('stroke-width', 1);
}});

// Axis lines + labels
const angleSlice = (2 * Math.PI) / n;
labels.forEach((label, i) => {{
  const angle = angleSlice * i - Math.PI / 2;
  const lx = Math.cos(angle) * radius;
  const ly = Math.sin(angle) * radius;
  g.append('line')
    .attr('x1', 0).attr('y1', 0)
    .attr('x2', lx).attr('y2', ly)
    .attr('stroke', '#e2e8f0').attr('stroke-width', 1);
  g.append('text')
    .attr('x', Math.cos(angle) * (radius + 20))
    .attr('y', Math.sin(angle) * (radius + 20))
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'central')
    .attr('font-size', '{fs}px')
    .text(label);
}});

// Data polygon
const points = values.map((v, i) => {{
  const angle = angleSlice * i - Math.PI / 2;
  const r = (v / maxVal) * radius;
  return [Math.cos(angle) * r, Math.sin(angle) * r];
}});
points.push(points[0]); // Close

const line = d3.line().curve(d3.curveLinearClosed);

g.append('path')
  .attr('d', line(points))
  .attr('fill', 'steelblue')
  .attr('fill-opacity', 0.25)
  .attr('stroke', 'steelblue')
  .attr('stroke-width', {sw + 1});

g.selectAll('circle.dot').data(points.slice(0, -1)).join('circle')
  .attr('class', 'dot')
  .attr('cx', d => d[0]).attr('cy', d => d[1])
  .attr('r', 4).attr('fill', 'steelblue');
"""


def gen_bubble(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Bubble chart — scatter with size encoding."""
    return f"""
const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const width = rect.width || 800;
const height = rect.height || 500;
const margin = {{top: 40, right: 24, bottom: 60, left: 64}};

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

const x = d3.scaleLinear()
  .domain(d3.extent(data, d => d.x || 0)).nice()
  .range([margin.left, width - margin.right]);

const y = d3.scaleLinear()
  .domain(d3.extent(data, d => d.y || d.value || 0)).nice()
  .range([height - margin.bottom, margin.top]);

const r = d3.scaleSqrt()
  .domain([0, d3.max(data, d => d.size || d.r || d.value || 1)])
  .range([4, 40]);

const color = d3.scaleOrdinal(d3.schemeTableau10);

svg.selectAll('circle').data(data).join('circle')
  .attr('cx', d => x(d.x || 0))
  .attr('cy', d => y(d.y || d.value || 0))
  .attr('r', 0)
  .attr('fill', (d, i) => color(d.group || d.label || i))
  .attr('fill-opacity', 0.7)
  .attr('stroke', (d, i) => color(d.group || d.label || i))
  .attr('stroke-width', 1)
  .transition().duration({anim}).ease(d3.easeCubicOut)
  .attr('r', d => r(d.size || d.r || d.value || 1));

svg.append('g').attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x).ticks(5))
  .selectAll('text').attr('font-size', '{fs}px');

svg.append('g').attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y).ticks(5))
  .selectAll('text').attr('font-size', '{fs}px');
"""


def gen_heatmap(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Heatmap — color-encoded matrix of row x col values."""
    return f"""
const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const width = rect.width || 800;
const height = rect.height || 500;
const margin = {{top: 40, right: 80, bottom: 60, left: 100}};

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

const rows = [...new Set(data.map(d => d.row || d.y))];
const cols = [...new Set(data.map(d => d.col || d.x))];

const x = d3.scaleBand().domain(cols).range([margin.left, width - margin.right]).padding(0.05);
const y = d3.scaleBand().domain(rows).range([margin.top, height - margin.bottom]).padding(0.05);

const vals = data.map(d => d.value || d.z || 0);
const color = d3.scaleSequential(d3.interpolateBlues)
  .domain([d3.min(vals), d3.max(vals)]);

svg.selectAll('rect').data(data).join('rect')
  .attr('x', d => x(d.col || d.x))
  .attr('y', d => y(d.row || d.y))
  .attr('width', x.bandwidth())
  .attr('height', y.bandwidth())
  .attr('rx', 2)
  .attr('fill', d => color(d.value || d.z || 0))
  .attr('opacity', 0)
  .transition().duration({anim}).ease(d3.easeCubicOut)
  .attr('opacity', 1);

// Cell value labels
svg.selectAll('text.cell').data(data).join('text')
  .attr('class', 'cell')
  .attr('x', d => x(d.col || d.x) + x.bandwidth() / 2)
  .attr('y', d => y(d.row || d.y) + y.bandwidth() / 2)
  .attr('text-anchor', 'middle')
  .attr('dominant-baseline', 'central')
  .attr('font-size', '14px')
  .attr('fill', d => (d.value || d.z || 0) > (d3.max(vals) * 0.6) ? 'white' : '#1e293b')
  .text(d => typeof (d.value || d.z) === 'number' ? (d.value || d.z).toFixed(1) : (d.value || d.z));

svg.append('g').attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x).tickSizeOuter(0))
  .selectAll('text').attr('font-size', '{fs}px');

svg.append('g').attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y).tickSizeOuter(0))
  .selectAll('text').attr('font-size', '{fs}px');
"""


def gen_histogram(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Histogram — frequency distribution of values."""
    return f"""
const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const width = rect.width || 800;
const height = rect.height || 500;
const margin = {{top: 40, right: 24, bottom: 60, left: 64}};

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

const values = data.map(d => d.value || d.x || d.y || 0);

const x = d3.scaleLinear()
  .domain(d3.extent(values)).nice()
  .range([margin.left, width - margin.right]);

const bins = d3.bin().domain(x.domain()).thresholds(x.ticks(20))(values);

const y = d3.scaleLinear()
  .domain([0, d3.max(bins, d => d.length)])
  .nice()
  .range([height - margin.bottom, margin.top]);

svg.selectAll('rect').data(bins).join('rect')
  .attr('x', d => x(d.x0) + 1)
  .attr('width', d => Math.max(0, x(d.x1) - x(d.x0) - 2))
  .attr('y', height - margin.bottom)
  .attr('height', 0)
  .attr('fill', 'steelblue')
  .attr('opacity', 0.75)
  .transition().duration({anim}).ease(d3.easeCubicOut)
  .attr('y', d => y(d.length))
  .attr('height', d => height - margin.bottom - y(d.length));

svg.append('g').attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x).ticks(10))
  .selectAll('text').attr('font-size', '{fs}px');

svg.append('g').attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y).ticks(5))
  .selectAll('text').attr('font-size', '{fs}px');
"""


def gen_box_plot(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Box plot — quartiles, median, and whiskers per group."""
    return f"""
const raw = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const width = rect.width || 800;
const height = rect.height || 500;
const margin = {{top: 40, right: 24, bottom: 60, left: 64}};

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

// Group data by label/group
const groups = d3.group(raw, d => d.label || d.group || 'all');
const groupNames = [...groups.keys()];

const x = d3.scaleBand()
  .domain(groupNames)
  .range([margin.left, width - margin.right])
  .padding(0.3);

const allValues = raw.map(d => d.value || d.y || 0);
const y = d3.scaleLinear()
  .domain(d3.extent(allValues)).nice()
  .range([height - margin.bottom, margin.top]);

const colors = d3.scaleOrdinal(d3.schemeTableau10);

groupNames.forEach((name, gi) => {{
  const vals = [...groups.get(name)].map(d => d.value || d.y || 0).sort(d3.ascending);
  const q1 = d3.quantile(vals, 0.25);
  const median = d3.quantile(vals, 0.5);
  const q3 = d3.quantile(vals, 0.75);
  const iqr = q3 - q1;
  const lo = Math.max(vals[0], q1 - 1.5 * iqr);
  const hi = Math.min(vals[vals.length - 1], q3 + 1.5 * iqr);

  const cx = x(name) + x.bandwidth() / 2;
  const bw = x.bandwidth() * 0.6;

  // Box
  svg.append('rect')
    .attr('x', cx - bw / 2).attr('width', bw)
    .attr('y', y(q3)).attr('height', y(q1) - y(q3))
    .attr('fill', colors(gi)).attr('fill-opacity', 0.4)
    .attr('stroke', colors(gi)).attr('stroke-width', {sw});

  // Median line
  svg.append('line')
    .attr('x1', cx - bw / 2).attr('x2', cx + bw / 2)
    .attr('y1', y(median)).attr('y2', y(median))
    .attr('stroke', colors(gi)).attr('stroke-width', {sw + 1});

  // Whiskers
  svg.append('line')
    .attr('x1', cx).attr('x2', cx)
    .attr('y1', y(lo)).attr('y2', y(q1))
    .attr('stroke', colors(gi)).attr('stroke-width', {sw});
  svg.append('line')
    .attr('x1', cx).attr('x2', cx)
    .attr('y1', y(q3)).attr('y2', y(hi))
    .attr('stroke', colors(gi)).attr('stroke-width', {sw});
}});

svg.append('g').attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x).tickSizeOuter(0))
  .selectAll('text').attr('font-size', '{fs}px');

svg.append('g').attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y).ticks(5))
  .selectAll('text').attr('font-size', '{fs}px');
"""


def gen_waterfall(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Waterfall chart — cumulative positive/negative deltas."""
    return f"""
const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const width = rect.width || 800;
const height = rect.height || 500;
const margin = {{top: 40, right: 24, bottom: 60, left: 64}};

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

// Compute running totals
let cumulative = 0;
const waterfallData = data.map(d => {{
  const start = cumulative;
  const val = d.value || d.y || 0;
  cumulative += val;
  return {{ ...d, start, end: cumulative, isNeg: val < 0 }};
}});

const x = d3.scaleBand()
  .domain(waterfallData.map(d => d.label || d.name))
  .range([margin.left, width - margin.right])
  .padding(0.3);

const y = d3.scaleLinear()
  .domain([d3.min(waterfallData, d => Math.min(d.start, d.end)),
           d3.max(waterfallData, d => Math.max(d.start, d.end))])
  .nice()
  .range([height - margin.bottom, margin.top]);

svg.selectAll('rect').data(waterfallData).join('rect')
  .attr('x', d => x(d.label || d.name))
  .attr('width', x.bandwidth())
  .attr('y', d => y(Math.max(d.start, d.end)))
  .attr('height', d => Math.abs(y(d.start) - y(d.end)))
  .attr('rx', 3)
  .attr('fill', d => d.isNeg ? '#ef4444' : '#22c55e')
  .attr('opacity', 0.85);

// Connector lines
waterfallData.forEach((d, i) => {{
  if (i < waterfallData.length - 1) {{
    svg.append('line')
      .attr('x1', x(d.label || d.name) + x.bandwidth())
      .attr('x2', x(waterfallData[i + 1].label || waterfallData[i + 1].name))
      .attr('y1', y(d.end)).attr('y2', y(d.end))
      .attr('stroke', '#94a3b8').attr('stroke-dasharray', '4,2')
      .attr('stroke-width', 1);
  }}
}});

svg.append('g').attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x).tickSizeOuter(0))
  .selectAll('text').attr('font-size', '{fs}px');

svg.append('g').attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y).ticks(5))
  .selectAll('text').attr('font-size', '{fs}px');
"""


def gen_funnel(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Funnel chart — progressively narrowing horizontal bars."""
    return f"""
const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const width = rect.width || 800;
const height = rect.height || 500;
const margin = {{top: 40, right: 24, bottom: 40, left: 24}};

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

const maxVal = d3.max(data, d => d.value || d.y || 0);
const stepH = (height - margin.top - margin.bottom) / data.length;
const centerX = width / 2;
const colors = d3.scaleOrdinal(d3.schemeTableau10);

data.forEach((d, i) => {{
  const val = d.value || d.y || 0;
  const barW = (val / maxVal) * (width - margin.left - margin.right - 100);
  const yPos = margin.top + i * stepH;

  svg.append('rect')
    .attr('x', centerX - barW / 2)
    .attr('y', yPos + 2)
    .attr('width', barW)
    .attr('height', stepH - 4)
    .attr('rx', 6)
    .attr('fill', colors(i))
    .attr('opacity', 0.8);

  svg.append('text')
    .attr('x', centerX)
    .attr('y', yPos + stepH / 2)
    .attr('text-anchor', 'middle')
    .attr('dominant-baseline', 'central')
    .attr('font-size', '{fs}px')
    .attr('font-weight', '600')
    .attr('fill', 'white')
    .text(`${{d.label || d.name}}: ${{val}}`);
}});
"""


def gen_ridgeline(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Ridgeline plot — overlapping density distributions per group."""
    return f"""
const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const width = rect.width || 800;
const height = rect.height || 500;
const margin = {{top: 40, right: 24, bottom: 40, left: 120}};

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

// Group by label/group
const groups = d3.group(data, d => d.label || d.group || 'all');
const groupNames = [...groups.keys()];
const overlap = 0.7;

const x = d3.scaleLinear()
  .domain(d3.extent(data, d => d.value || d.x || 0))
  .range([margin.left, width - margin.right]);

const y = d3.scaleBand()
  .domain(groupNames)
  .range([margin.top, height - margin.bottom])
  .padding(0);

const colors = d3.scaleOrdinal(d3.schemeTableau10);

groupNames.forEach((name, gi) => {{
  const vals = [...groups.get(name)].map(d => d.value || d.x || 0).sort(d3.ascending);

  // Simple kernel density estimation
  const kde = d3.scaleLinear().domain(x.domain()).range([0, 100]);
  const bins = d3.bin().domain(x.domain()).thresholds(30)(vals);
  const maxCount = d3.max(bins, b => b.length) || 1;

  const areaGen = d3.area()
    .x(b => x((b.x0 + b.x1) / 2))
    .y0(y(name) + y.bandwidth())
    .y1(b => y(name) + y.bandwidth() - (b.length / maxCount) * y.bandwidth() * (1 + overlap))
    .curve(d3.curveBasis);

  svg.append('path')
    .datum(bins)
    .attr('fill', colors(gi))
    .attr('fill-opacity', 0.6)
    .attr('stroke', colors(gi))
    .attr('stroke-width', 1.5)
    .attr('d', areaGen);
}});

svg.append('g').attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y).tickSizeOuter(0))
  .selectAll('text').attr('font-size', '{fs}px');

svg.append('g').attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x).ticks(8))
  .selectAll('text').attr('font-size', '{fs}px');
"""


def gen_beeswarm(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Beeswarm plot — dodged dots showing distribution per group."""
    return f"""
const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const width = rect.width || 800;
const height = rect.height || 500;
const margin = {{top: 40, right: 24, bottom: 60, left: 100}};

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

const groups = [...new Set(data.map(d => d.label || d.group || 'all'))];

const x = d3.scaleLinear()
  .domain(d3.extent(data, d => d.value || d.x || 0)).nice()
  .range([margin.left, width - margin.right]);

const y = d3.scaleBand()
  .domain(groups)
  .range([margin.top, height - margin.bottom])
  .padding(0.3);

const colors = d3.scaleOrdinal(d3.schemeTableau10);
const r = 4;

// Simple dodge: stack dots vertically within each band
groups.forEach(grp => {{
  const pts = data.filter(d => (d.label || d.group || 'all') === grp)
    .sort((a, b) => (a.value || a.x || 0) - (b.value || b.x || 0));
  const cy = y(grp) + y.bandwidth() / 2;

  pts.forEach((d, i) => {{
    svg.append('circle')
      .attr('cx', x(d.value || d.x || 0))
      .attr('cy', cy + (i % 3 - 1) * (r * 2.5))
      .attr('r', 0)
      .attr('fill', colors(grp))
      .attr('opacity', 0.7)
      .transition().duration({anim}).delay(i * 10).ease(d3.easeCubicOut)
      .attr('r', r);
  }});
}});

svg.append('g').attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y).tickSizeOuter(0))
  .selectAll('text').attr('font-size', '{fs}px');

svg.append('g').attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x).ticks(8))
  .selectAll('text').attr('font-size', '{fs}px');
"""


def gen_gauge(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Gauge chart — semicircular progress indicator."""
    return f"""
const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const size = Math.min(rect.width || 400, rect.height || 400);

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{size}} ${{size * 0.65}}`);

const g = svg.append('g').attr('transform', `translate(${{size/2}},${{size * 0.55}})`);
const radius = size * 0.4;
const val = data[0]?.value || data[0]?.y || 0;
const maxVal = data[0]?.max || 100;
const pct = Math.min(1, val / maxVal);

const arcBg = d3.arc()
  .innerRadius(radius * 0.7)
  .outerRadius(radius)
  .startAngle(-Math.PI / 2)
  .endAngle(Math.PI / 2);

const arcFg = d3.arc()
  .innerRadius(radius * 0.7)
  .outerRadius(radius)
  .startAngle(-Math.PI / 2);

g.append('path').attr('d', arcBg())
  .attr('fill', '#e2e8f0');

g.append('path')
  .attr('fill', pct > 0.8 ? '#22c55e' : pct > 0.5 ? '#eab308' : '#ef4444')
  .transition().duration({anim}).ease(d3.easeCubicOut)
  .attrTween('d', () => {{
    const interp = d3.interpolate(-Math.PI / 2, -Math.PI / 2 + Math.PI * pct);
    return t => arcFg.endAngle(interp(t))();
  }});

g.append('text')
  .attr('text-anchor', 'middle')
  .attr('y', -10)
  .attr('font-size', `${{size * 0.12}}px`)
  .attr('font-weight', '700')
  .attr('fill', '{CANVAS_FG}')
  .text(`${{(pct * 100).toFixed(0)}}%`);

g.append('text')
  .attr('text-anchor', 'middle')
  .attr('y', size * 0.06)
  .attr('font-size', '{fs}px')
  .attr('fill', '#64748b')
  .text(data[0]?.label || data[0]?.name || '');
"""
