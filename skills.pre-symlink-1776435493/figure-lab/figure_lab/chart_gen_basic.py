"""Basic cartesian chart generators for figure-lab compositions.

Contains generators for standard bar and area chart types:
  - Vertical bar (fallback default)
  - Horizontal bar
  - Stacked bar
  - Grouped bar
  - Area
  - Stacked area

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


def gen_bar_fallback(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Vertical bar chart — default fallback for unknown types."""
    return f"""
const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const width = rect.width || 800;
const height = rect.height || 500;
const margin = {{top: 40, right: 24, bottom: 60, left: 64}};

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

const x = d3.scaleBand()
  .domain(data.map(d => d.label || d.name || String(d.x)))
  .range([margin.left, width - margin.right])
  .padding(0.3);

const y = d3.scaleLinear()
  .domain([0, d3.max(data, d => d.value || d.y || 0)])
  .nice()
  .range([height - margin.bottom, margin.top]);

const colors = d3.scaleOrdinal(d3.schemeTableau10);

svg.selectAll('rect').data(data).join('rect')
  .attr('x', d => x(d.label || d.name || String(d.x)))
  .attr('width', x.bandwidth())
  .attr('y', height - margin.bottom)
  .attr('height', 0)
  .attr('rx', 4)
  .attr('fill', (d, i) => colors(i))
  .attr('opacity', 0.85)
  .transition().duration({anim}).ease(d3.easeCubicOut)
  .attr('y', d => y(d.value || d.y || 0))
  .attr('height', d => height - margin.bottom - y(d.value || d.y || 0));

svg.append('g')
  .attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x).tickSizeOuter(0))
  .selectAll('text').attr('font-size', '{fs}px');

svg.append('g')
  .attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y).ticks(5))
  .selectAll('text').attr('font-size', '{fs}px');

svg.selectAll('.domain, .tick line')
  .attr('stroke', 'currentColor').attr('stroke-opacity', 0.3);
"""


def gen_hbar(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Horizontal bar chart."""
    return f"""
const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const width = rect.width || 800;
const height = rect.height || 500;
const margin = {{top: 40, right: 40, bottom: 40, left: 140}};

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

const y = d3.scaleBand()
  .domain(data.map(d => d.label || d.name))
  .range([margin.top, height - margin.bottom])
  .padding(0.3);

const x = d3.scaleLinear()
  .domain([0, d3.max(data, d => d.value || d.y || 0)])
  .nice()
  .range([margin.left, width - margin.right]);

const colors = d3.scaleOrdinal(d3.schemeTableau10);

svg.selectAll('rect').data(data).join('rect')
  .attr('y', d => y(d.label || d.name))
  .attr('height', y.bandwidth())
  .attr('x', margin.left)
  .attr('width', 0)
  .attr('rx', 4)
  .attr('fill', (d, i) => colors(i))
  .attr('opacity', 0.85)
  .transition().duration({anim}).ease(d3.easeCubicOut)
  .attr('width', d => x(d.value || d.y || 0) - margin.left);

svg.append('g')
  .attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y).tickSizeOuter(0))
  .selectAll('text').attr('font-size', '{fs}px');

svg.append('g')
  .attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x).ticks(5))
  .selectAll('text').attr('font-size', '{fs}px');

svg.selectAll('.domain, .tick line')
  .attr('stroke', 'currentColor').attr('stroke-opacity', 0.3);
"""


def gen_stacked_bar(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Stacked bar chart — expects data with multiple numeric keys per row."""
    return f"""
const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const width = rect.width || 800;
const height = rect.height || 500;
const margin = {{top: 40, right: 120, bottom: 60, left: 64}};

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

// Expect data like [{{label, ...groups}}]
const keys = Object.keys(data[0]).filter(k => k !== 'label' && k !== 'name');
const stack = d3.stack().keys(keys)(data);

const x = d3.scaleBand()
  .domain(data.map(d => d.label || d.name))
  .range([margin.left, width - margin.right])
  .padding(0.2);

const y = d3.scaleLinear()
  .domain([0, d3.max(stack, s => d3.max(s, d => d[1]))])
  .nice()
  .range([height - margin.bottom, margin.top]);

const color = d3.scaleOrdinal(d3.schemeTableau10).domain(keys);

svg.selectAll('g.layer').data(stack).join('g')
  .attr('class', 'layer')
  .attr('fill', d => color(d.key))
  .selectAll('rect').data(d => d).join('rect')
  .attr('x', d => x(d.data.label || d.data.name))
  .attr('width', x.bandwidth())
  .attr('y', height - margin.bottom)
  .attr('height', 0)
  .attr('opacity', 0.85)
  .transition().duration({anim}).ease(d3.easeCubicOut)
  .attr('y', d => y(d[1]))
  .attr('height', d => y(d[0]) - y(d[1]));

svg.append('g').attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x).tickSizeOuter(0))
  .selectAll('text').attr('font-size', '{fs}px');

svg.append('g').attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y).ticks(5))
  .selectAll('text').attr('font-size', '{fs}px');

// Legend
const legend = svg.append('g').attr('transform', `translate(${{width - margin.right + 12}}, ${{margin.top}})`);
keys.forEach((k, i) => {{
  const g = legend.append('g').attr('transform', `translate(0,${{i * 24}})`);
  g.append('rect').attr('width', 16).attr('height', 16).attr('fill', color(k)).attr('rx', 3);
  g.append('text').attr('x', 22).attr('y', 13).text(k).attr('font-size', '14px');
}});
"""


def gen_grouped_bar(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Grouped bar chart — multiple series side by side."""
    return f"""
const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const width = rect.width || 800;
const height = rect.height || 500;
const margin = {{top: 40, right: 120, bottom: 60, left: 64}};

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

const keys = Object.keys(data[0]).filter(k => k !== 'label' && k !== 'name');

const x0 = d3.scaleBand()
  .domain(data.map(d => d.label || d.name))
  .range([margin.left, width - margin.right])
  .padding(0.2);

const x1 = d3.scaleBand()
  .domain(keys)
  .range([0, x0.bandwidth()])
  .padding(0.05);

const y = d3.scaleLinear()
  .domain([0, d3.max(data, d => d3.max(keys, k => d[k]))])
  .nice()
  .range([height - margin.bottom, margin.top]);

const color = d3.scaleOrdinal(d3.schemeTableau10).domain(keys);

svg.selectAll('g.group').data(data).join('g')
  .attr('class', 'group')
  .attr('transform', d => `translate(${{x0(d.label || d.name)}},0)`)
  .selectAll('rect').data(d => keys.map(k => ({{key: k, value: d[k]}})))
  .join('rect')
  .attr('x', d => x1(d.key))
  .attr('width', x1.bandwidth())
  .attr('y', height - margin.bottom)
  .attr('height', 0)
  .attr('fill', d => color(d.key))
  .attr('opacity', 0.85)
  .attr('rx', 2)
  .transition().duration({anim}).ease(d3.easeCubicOut)
  .attr('y', d => y(d.value))
  .attr('height', d => height - margin.bottom - y(d.value));

svg.append('g').attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x0).tickSizeOuter(0))
  .selectAll('text').attr('font-size', '{fs}px');

svg.append('g').attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y).ticks(5))
  .selectAll('text').attr('font-size', '{fs}px');
"""


def gen_area(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Area chart with line animation."""
    return f"""
const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const width = rect.width || 800;
const height = rect.height || 500;
const margin = {{top: 40, right: 24, bottom: 60, left: 64}};

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

const x = d3.scalePoint()
  .domain(data.map(d => d.label || d.name || String(d.x)))
  .range([margin.left, width - margin.right])
  .padding(0.5);

const y = d3.scaleLinear()
  .domain([0, d3.max(data, d => d.value || d.y || 0)])
  .nice()
  .range([height - margin.bottom, margin.top]);

const area = d3.area()
  .x(d => x(d.label || d.name || String(d.x)))
  .y0(height - margin.bottom)
  .y1(d => y(d.value || d.y || 0))
  .curve(d3.curveMonotoneX);

const line = d3.line()
  .x(d => x(d.label || d.name || String(d.x)))
  .y(d => y(d.value || d.y || 0))
  .curve(d3.curveMonotoneX);

svg.append('path').datum(data)
  .attr('fill', 'steelblue').attr('fill-opacity', 0.3)
  .attr('d', area);

const path = svg.append('path').datum(data)
  .attr('fill', 'none').attr('stroke', 'steelblue')
  .attr('stroke-width', {sw + 1}).attr('d', line);

const totalLength = path.node()?.getTotalLength() || 0;
path.attr('stroke-dasharray', `${{totalLength}} ${{totalLength}}`)
  .attr('stroke-dashoffset', totalLength)
  .transition().duration({anim}).ease(d3.easeCubicOut)
  .attr('stroke-dashoffset', 0);

svg.append('g').attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x).tickSizeOuter(0))
  .selectAll('text').attr('font-size', '{fs}px');

svg.append('g').attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y).ticks(5))
  .selectAll('text').attr('font-size', '{fs}px');
"""


def gen_stacked_area(data_json: str, fs: int, sw: int, anim: int) -> str:
    """Stacked area chart — multiple series stacked vertically."""
    return f"""
const data = {data_json};
const container = document.getElementById('chart');
const rect = container.getBoundingClientRect();
const width = rect.width || 800;
const height = rect.height || 500;
const margin = {{top: 40, right: 120, bottom: 60, left: 64}};

const svg = d3.select('#chart').append('svg')
  .attr('viewBox', `0 0 ${{width}} ${{height}}`);

const keys = Object.keys(data[0]).filter(k => k !== 'label' && k !== 'name' && k !== 'x');
const stack = d3.stack().keys(keys)(data);

const x = d3.scalePoint()
  .domain(data.map(d => d.label || d.name || String(d.x)))
  .range([margin.left, width - margin.right]);

const y = d3.scaleLinear()
  .domain([0, d3.max(stack, s => d3.max(s, d => d[1]))])
  .nice()
  .range([height - margin.bottom, margin.top]);

const color = d3.scaleOrdinal(d3.schemeTableau10).domain(keys);

const area = d3.area()
  .x((d, i) => x(data[i].label || data[i].name || String(data[i].x)))
  .y0(d => y(d[0]))
  .y1(d => y(d[1]))
  .curve(d3.curveMonotoneX);

svg.selectAll('path.area').data(stack).join('path')
  .attr('class', 'area')
  .attr('fill', d => color(d.key))
  .attr('fill-opacity', 0.7)
  .attr('d', area);

svg.append('g').attr('transform', `translate(0,${{height - margin.bottom}})`)
  .call(d3.axisBottom(x).tickSizeOuter(0))
  .selectAll('text').attr('font-size', '{fs}px');

svg.append('g').attr('transform', `translate(${{margin.left}},0)`)
  .call(d3.axisLeft(y).ticks(5))
  .selectAll('text').attr('font-size', '{fs}px');
"""
