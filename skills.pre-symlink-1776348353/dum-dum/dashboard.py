"""D3 dashboard: generates self-contained HTML with embedded quality data.

Inputs: --export for custom output path (default: ~/.embry/dum-dum/dashboard.html).
Outputs: static HTML file with inline D3.js and per-channel charts.
Failure modes: empty data (dashboard renders with "no data" placeholders).
"""

import json
import typing as t
from datetime import datetime, timezone
from pathlib import Path

import typer
from loguru import logger

DATA_DIR = Path.home() / ".embry" / "dum-dum"

app = typer.Typer(add_completion=False)


def load_all_data() -> dict:
    """Load all JSONL data files into a single structure for the dashboard."""
    data: dict[str, list] = {"probes": [], "signals": [], "drift": []}

    for name in ("probes", "signals", "drift"):
        path = DATA_DIR / f"{name}.jsonl"
        if not path.exists():
            continue
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data[name].append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    return data


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>dum-dum: Model Integrity Dashboard</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
         background: #0d1117; color: #c9d1d9; padding: 20px; }
  h1 { color: #58a6ff; margin-bottom: 8px; font-size: 24px; }
  .subtitle { color: #8b949e; margin-bottom: 24px; font-size: 14px; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 20px; }
  .card h2 { color: #58a6ff; font-size: 16px; margin-bottom: 12px; }
  .grade { font-size: 48px; font-weight: bold; text-align: center; padding: 20px; }
  .grade-A { color: #3fb950; }
  .grade-B { color: #d29922; }
  .grade-C { color: #db6d28; }
  .grade-F { color: #f85149; }
  .metric { display: flex; justify-content: space-between; padding: 8px 0;
            border-bottom: 1px solid #21262d; }
  .metric:last-child { border-bottom: none; }
  .metric-label { color: #8b949e; }
  .metric-value { color: #c9d1d9; font-weight: 600; }
  .chart-container { width: 100%; height: 200px; }
  .probe-line { fill: none; stroke: #58a6ff; stroke-width: 2; }
  .signal-line { fill: none; stroke: #d29922; stroke-width: 2; }
  .probe-dot { fill: #58a6ff; }
  .signal-dot { fill: #d29922; }
  .axis text { fill: #8b949e; font-size: 11px; }
  .axis path, .axis line { stroke: #30363d; }
  .no-data { color: #8b949e; text-align: center; padding: 40px; font-style: italic; }
  .full-width { grid-column: 1 / -1; }
  table { width: 100%; border-collapse: collapse; }
  th, td { padding: 8px 12px; text-align: left; border-bottom: 1px solid #21262d; }
  th { color: #8b949e; font-weight: 500; font-size: 12px; text-transform: uppercase; }
  td { font-size: 13px; }
  .badge { padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: 600; }
  .badge-pass { background: #1b4332; color: #3fb950; }
  .badge-fail { background: #4a1f1f; color: #f85149; }
  .badge-partial { background: #3d2e00; color: #d29922; }
  .badge-high { background: #4a1f1f; color: #f85149; }
  .badge-medium { background: #3d2e00; color: #d29922; }
  .legend { display: flex; gap: 16px; margin-bottom: 8px; font-size: 12px; }
  .legend-item { display: flex; align-items: center; gap: 4px; }
  .legend-swatch { width: 12px; height: 3px; border-radius: 2px; }
</style>
</head>
<body>
<h1>dum-dum: Model Integrity Dashboard</h1>
<p class="subtitle">Generated __TIMESTAMP__</p>

<div class="grid">
  <div class="card">
    <h2>Current Grade</h2>
    <div id="grade-display" class="no-data">No probe data</div>
  </div>
  <div class="card">
    <h2>Signal Summary</h2>
    <div id="signal-summary" class="no-data">No signal data</div>
  </div>
  <div class="card full-width">
    <h2>Quality Over Time (Per Channel)</h2>
    <div id="legend" class="legend"></div>
    <div id="quality-chart" class="chart-container"></div>
  </div>
  <div class="card full-width">
    <h2>Recent Probes</h2>
    <div id="probe-table"></div>
  </div>
  <div class="card full-width">
    <h2>Drift Alerts</h2>
    <div id="drift-table"></div>
  </div>
</div>

<script>
const DATA = __DATA_JSON__;

function mkEl(tag, cls, text) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined) el.textContent = String(text);
  return el;
}

// Grade display
if (DATA.probes.length > 0) {
  const latest = DATA.probes[DATA.probes.length - 1];
  const grade = latest.summary.grade;
  const score = latest.summary.score;
  const container = document.getElementById('grade-display');
  container.innerHTML = '';
  container.appendChild(mkEl('div', 'grade grade-' + grade, grade));
  const info = mkEl('div', '', '');
  info.style.textAlign = 'center';
  info.style.color = '#8b949e';
  const parts = [score + '/100', latest.model];
  if (latest.summary.avg_latency_ms != null) parts.push(latest.summary.avg_latency_ms + 'ms avg');
  info.textContent = parts.join(' \\u2014 ');
  container.appendChild(info);
}

// Signal summary
if (DATA.signals.length > 0) {
  const latest = DATA.signals[DATA.signals.length - 1];
  const types = {};
  (latest.signals || []).forEach(s => { types[s.type] = (types[s.type] || 0) + 1; });
  const container = document.getElementById('signal-summary');
  container.innerHTML = '';
  Object.entries(types).forEach(([type, count]) => {
    const row = mkEl('div', 'metric');
    row.appendChild(mkEl('span', 'metric-label', type));
    row.appendChild(mkEl('span', 'metric-value', count));
    container.appendChild(row);
  });
  const totalRow = mkEl('div', 'metric');
  totalRow.appendChild(mkEl('span', 'metric-label', 'Total'));
  totalRow.appendChild(mkEl('span', 'metric-value', latest.signal_count));
  container.appendChild(totalRow);
}

// Per-channel quality chart
const probePoints = DATA.probes.map(p => ({ date: new Date(p.timestamp), score: p.summary.score }));
const signalPoints = DATA.signals.map(s => ({
  date: new Date(s.timestamp),
  score: Math.max(0, 100 - s.signal_count * 10)
}));

if (probePoints.length > 1 || signalPoints.length > 1) {
  const margin = {top: 10, right: 20, bottom: 30, left: 40};
  const container = document.getElementById('quality-chart');
  const width = container.clientWidth - margin.left - margin.right;
  const height = 200 - margin.top - margin.bottom;

  const legendEl = document.getElementById('legend');
  [{color: '#58a6ff', label: 'Probe scores'}, {color: '#d29922', label: 'Signal quality'}].forEach(l => {
    const item = mkEl('div', 'legend-item');
    const swatch = mkEl('span', 'legend-swatch');
    swatch.style.background = l.color;
    item.appendChild(swatch);
    item.appendChild(mkEl('span', '', l.label));
    legendEl.appendChild(item);
  });

  const svg = d3.select('#quality-chart')
    .append('svg')
    .attr('width', width + margin.left + margin.right)
    .attr('height', height + margin.top + margin.bottom)
    .append('g')
    .attr('transform', `translate(${margin.left},${margin.top})`);

  const allDates = probePoints.map(d=>d.date).concat(signalPoints.map(d=>d.date));
  const x = d3.scaleTime().domain(d3.extent(allDates)).range([0, width]);
  const y = d3.scaleLinear().domain([0, 100]).range([height, 0]);

  svg.append('g').attr('class','axis').attr('transform',`translate(0,${height})`).call(d3.axisBottom(x).ticks(5));
  svg.append('g').attr('class','axis').call(d3.axisLeft(y).ticks(5));

  svg.append('rect').attr('x',0).attr('y',y(100)).attr('width',width).attr('height',y(90)-y(100)).attr('fill','#1b4332').attr('opacity',0.2);
  svg.append('rect').attr('x',0).attr('y',y(70)).attr('width',width).attr('height',y(50)-y(70)).attr('fill','#3d2e00').attr('opacity',0.2);
  svg.append('rect').attr('x',0).attr('y',y(50)).attr('width',width).attr('height',y(0)-y(50)).attr('fill','#4a1f1f').attr('opacity',0.2);

  if (probePoints.length > 1) {
    const line = d3.line().x(d=>x(d.date)).y(d=>y(d.score));
    svg.append('path').datum(probePoints).attr('class','probe-line').attr('d',line);
    svg.selectAll('.probe-dot').data(probePoints).join('circle').attr('class','probe-dot').attr('cx',d=>x(d.date)).attr('cy',d=>y(d.score)).attr('r',3);
  }

  if (signalPoints.length > 1) {
    const line2 = d3.line().x(d=>x(d.date)).y(d=>y(d.score));
    svg.append('path').datum(signalPoints).attr('class','signal-line').attr('d',line2);
    svg.selectAll('.signal-dot').data(signalPoints).join('circle').attr('class','signal-dot').attr('cx',d=>x(d.date)).attr('cy',d=>y(d.score)).attr('r',3);
  }

  DATA.drift.forEach(d => {
    (d.detections || []).forEach(det => {
      const dt = new Date(det.timestamp);
      if (dt >= x.domain()[0] && dt <= x.domain()[1]) {
        svg.append('line')
          .attr('x1',x(dt)).attr('x2',x(dt)).attr('y1',0).attr('y2',height)
          .attr('stroke','#f85149').attr('stroke-dasharray','4,4').attr('opacity',0.5);
      }
    });
  });
} else {
  document.getElementById('quality-chart').innerHTML = '<div class="no-data">Need 2+ data points for chart</div>';
}

function buildTable(headers, rows, containerId) {
  const container = document.getElementById(containerId);
  if (!rows.length) { container.appendChild(mkEl('div','no-data','No data')); return; }
  const table = document.createElement('table');
  const thead = document.createElement('tr');
  headers.forEach(h => thead.appendChild(mkEl('th','',h)));
  table.appendChild(thead);
  rows.forEach(cells => {
    const tr = document.createElement('tr');
    cells.forEach(cell => {
      const td = document.createElement('td');
      if (typeof cell === 'object' && cell.badge) {
        td.appendChild(mkEl('span','badge badge-'+cell.badge,cell.text));
      } else {
        td.textContent = String(cell);
      }
      tr.appendChild(td);
    });
    table.appendChild(tr);
  });
  container.appendChild(table);
}

if (DATA.probes.length > 0) {
  const rows = DATA.probes.slice(-10).reverse().map(p => {
    const badge = p.summary.grade==='A'?'pass':p.summary.grade==='F'?'fail':'partial';
    const lat = p.summary.avg_latency_ms != null ? p.summary.avg_latency_ms+'ms' : '-';
    return [
      p.timestamp.slice(0,19), p.model,
      {badge, text: p.summary.grade},
      p.summary.score, p.summary.passed+'/'+p.summary.total_probes, lat
    ];
  });
  buildTable(['Time','Model','Grade','Score','Probes','Latency'], rows, 'probe-table');
} else {
  document.getElementById('probe-table').appendChild(mkEl('div','no-data','No probe data'));
}

const allDrift = DATA.drift.flatMap(d => d.detections || []);
if (allDrift.length > 0) {
  const rows = allDrift.slice(-10).reverse().map(d => [
    d.channel || '-',
    d.timestamp.slice(0,19), d.method,
    {badge: d.severity==='HIGH'?'high':'medium', text: d.severity},
    d.cusum_value
  ]);
  buildTable(['Channel','Time','Method','Severity','Value'], rows, 'drift-table');
} else {
  document.getElementById('drift-table').appendChild(mkEl('div','no-data','No drift alerts'));
}
</script>
</body>
</html>"""


@app.command()
def main(
    export: t.Annotated[t.Optional[str], typer.Option("--export", help="Export path")] = None,
) -> None:
    """Generate D3 model integrity dashboard."""
    data = load_all_data()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    html = DASHBOARD_HTML.replace("__DATA_JSON__", json.dumps(data))
    html = html.replace("__TIMESTAMP__", timestamp)

    if export:
        out = Path(export)
    else:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        out = DATA_DIR / "dashboard.html"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    print(f"Dashboard exported to {out}")
    if not export:
        print(f"Open in browser: file://{out}")
    logger.info("Dashboard exported to {}", out)


if __name__ == "__main__":
    app()
