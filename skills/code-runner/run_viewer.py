#!/usr/bin/env python3
"""Run Viewer — Web-based single run detail page.

Phase 2 of multica-inspired upgrades. Renders run.json + events.jsonl
into a clean, inspectable HTML page.

Usage:
    # Serve a run directory
    python run_viewer.py serve /tmp/code-runner/task-123

    # Generate static HTML
    python run_viewer.py generate /tmp/code-runner/task-123 -o run_report.html

    # View latest run in default output dir
    python run_viewer.py serve --latest
"""
from __future__ import annotations

import html
import json
import http.server
import socketserver
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import typer
from loguru import logger


def _esc(text: str | None) -> str:
    """HTML-escape text to prevent XSS."""
    return html.escape(str(text) if text else "")

app = typer.Typer(no_args_is_help=True)


def _fmt_ts(ts: float) -> str:
    """Format Unix timestamp as human-readable."""
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def _fmt_duration(seconds: float) -> str:
    """Format duration in seconds as human-readable."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"


def _state_badge(state: str) -> str:
    """Return styled badge HTML for run state."""
    colors = {
        "queued": "#6b7280",
        "running": "#3b82f6",
        "passed": "#22c55e",
        "failed": "#ef4444",
        "blocked": "#f59e0b",
        "timed_out": "#f97316",
        "crashed": "#dc2626",
        "preflight_failed": "#8b5cf6",
    }
    safe_state = _esc(state)
    color = colors.get(state, "#6b7280")
    return f'<span class="badge" style="background:{color}">{safe_state.upper()}</span>'


def _event_icon(event: str) -> str:
    """Return emoji icon for event type."""
    icons = {
        "run_queued": "📋",
        "preflight_started": "🔍",
        "preflight_failed": "❌",
        "run_started": "🚀",
        "run_blocked": "🚧",
        "round_started": "🔄",
        "round_timeout": "⏰",
        "diagnosis_started": "🔬",
        "diagnosis_complete": "✅",
        "diagnosis_rejected": "🚫",
        "tool_use_started": "🔧",
        "tool_use_complete": "✅",
        "evidence_collected": "📊",
        "round_scored": "📈",
        "round_kept": "💾",
        "round_discarded": "🗑️",
        "zero_write_detected": "⚠️",
        "dod_checked": "✔️",
        "dod_passed": "🎉",
        "run_passed": "✅",
        "run_failed": "❌",
        "run_crashed": "💥",
        "run_timed_out": "⏰",
    }
    return icons.get(event, "•")


def load_run_data(output_dir: Path) -> dict[str, Any]:
    """Load run.json and events.jsonl from output directory."""
    data: dict[str, Any] = {"run": None, "events": [], "result": None, "rounds": []}

    # Load run.json snapshot
    run_file = output_dir / "run.json"
    if run_file.exists():
        data["run"] = json.loads(run_file.read_text())

    # Load events.jsonl
    events_file = output_dir / "events.jsonl"
    if events_file.exists():
        for line in events_file.read_text().strip().split("\n"):
            if line:
                try:
                    data["events"].append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    # Load result.json if exists
    result_files = list(output_dir.glob("*.result.json"))
    if result_files:
        data["result"] = json.loads(result_files[0].read_text())
        # Extract round_details if present
        if "round_details" in data["result"]:
            data["rounds"] = data["result"]["round_details"]

    # Load individual round context files
    logs_dir = output_dir / "logs"
    if logs_dir.exists():
        for ctx_file in sorted(logs_dir.glob("round_*_context.json")):
            try:
                ctx = json.loads(ctx_file.read_text())
                # Merge with existing round data or add new
                round_num = ctx.get("round", 0)
                found = False
                for r in data["rounds"]:
                    if r.get("round") == round_num:
                        r.update(ctx)
                        found = True
                        break
                if not found:
                    data["rounds"].append(ctx)
            except json.JSONDecodeError:
                pass
        data["rounds"].sort(key=lambda x: x.get("round", 0))

    return data


def render_summary(run: dict | None, result: dict | None) -> str:
    """Render run summary section."""
    if not run and not result:
        return "<p>No run data found.</p>"

    r = run or {}
    res = result or {}

    state = r.get("state") or res.get("status", "unknown")
    reason = r.get("reason_code") or ""
    task_id = r.get("run_id", "").split("-")[1] if r.get("run_id") else res.get("task_id", "unknown")
    title = res.get("title", task_id)
    backend = res.get("backend", r.get("backend", "unknown"))
    rounds = r.get("current_round", res.get("rounds", 0))
    best_score = r.get("best_score", res.get("best_score", 0))
    dod_passed = res.get("dod_passed", False)
    started = r.get("started_at", 0)
    updated = r.get("updated_at", 0)
    elapsed = updated - started if started and updated else 0

    return f"""
    <div class="summary-grid">
        <div class="summary-item">
            <div class="label">State</div>
            <div class="value">{_state_badge(state)}{f' <span class="reason">({_esc(reason)})</span>' if reason else ''}</div>
        </div>
        <div class="summary-item">
            <div class="label">Task</div>
            <div class="value">{_esc(title)}</div>
        </div>
        <div class="summary-item">
            <div class="label">Backend</div>
            <div class="value">{_esc(backend)}</div>
        </div>
        <div class="summary-item">
            <div class="label">Rounds</div>
            <div class="value">{rounds}</div>
        </div>
        <div class="summary-item">
            <div class="label">Best Score</div>
            <div class="value score">{best_score:.3f}</div>
        </div>
        <div class="summary-item">
            <div class="label">DoD</div>
            <div class="value">{'✅ Passed' if dod_passed else '❌ Not passed'}</div>
        </div>
        <div class="summary-item">
            <div class="label">Elapsed</div>
            <div class="value">{_fmt_duration(elapsed)}</div>
        </div>
        <div class="summary-item">
            <div class="label">Started</div>
            <div class="value">{_fmt_ts(started) if started else 'N/A'}</div>
        </div>
    </div>
    """


def render_timeline(events: list[dict]) -> str:
    """Render event timeline section."""
    if not events:
        return "<p>No events recorded.</p>"

    rows = []
    for ev in events:
        ts = _fmt_ts(ev.get("ts", 0))
        event = ev.get("event", "unknown")
        icon = _event_icon(event)
        round_num = ev.get("round")
        round_str = f"R{round_num}" if round_num else ""

        # Format payload highlights
        payload = ev.get("payload", {})
        details = []
        if "score" in payload:
            details.append(f"score={payload['score']:.3f}")
        if "error_count" in payload:
            details.append(f"errors={payload['error_count']}")
        if "dod_passed" in payload:
            details.append(f"dod={'✓' if payload['dod_passed'] else '✗'}")
        if "consecutive_count" in payload:
            details.append(f"zero_writes={payload['consecutive_count']}")
        if ev.get("reason_code"):
            details.append(f"reason={ev['reason_code']}")

        detail_str = " | ".join(details) if details else ""

        rows.append(f"""
        <tr>
            <td class="ts">{ts}</td>
            <td class="round">{round_str}</td>
            <td class="event">{icon} {_esc(event.replace('_', ' '))}</td>
            <td class="details">{_esc(detail_str)}</td>
        </tr>
        """)

    return f"""
    <table class="timeline-table">
        <thead>
            <tr><th>Time</th><th>Round</th><th>Event</th><th>Details</th></tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    """


def render_rounds_table(rounds: list[dict]) -> str:
    """Render round-by-round table."""
    if not rounds:
        return "<p>No round data available.</p>"

    rows = []
    for r in rounds:
        round_num = r.get("round", "?")
        strategy = r.get("strategy", "")
        backend = r.get("backend", "")
        reasoning = r.get("reasoning", "")
        score = r.get("score", 0)
        status = r.get("status", "")
        dod = "✓" if r.get("dod_passed") else "✗"
        errors = r.get("error_count", 0)
        files = len(r.get("written_files", []))
        duration = r.get("duration_ms", 0) / 1000

        status_class = "keep" if status == "keep" else "discard"

        rows.append(f"""
        <tr class="{_esc(status_class)}">
            <td>{round_num}</td>
            <td>{_esc(strategy)}</td>
            <td>{_esc(backend)}:{_esc(reasoning)}</td>
            <td class="score">{score:.3f}</td>
            <td>{_esc(status).upper()}</td>
            <td>{dod}</td>
            <td>{errors}</td>
            <td>{files}</td>
            <td>{duration:.1f}s</td>
        </tr>
        """)

    return f"""
    <table class="rounds-table">
        <thead>
            <tr>
                <th>#</th>
                <th>Strategy</th>
                <th>Backend</th>
                <th>Score</th>
                <th>Decision</th>
                <th>DoD</th>
                <th>Errors</th>
                <th>Files</th>
                <th>Duration</th>
            </tr>
        </thead>
        <tbody>
            {''.join(rows)}
        </tbody>
    </table>
    """


def render_evidence(rounds: list[dict]) -> str:
    """Render latest evidence panel."""
    if not rounds:
        return "<p>No evidence available.</p>"

    latest = rounds[-1]
    error_ev = latest.get("error_evidence") or {}

    sections = []

    # Error summary
    if error_ev:
        failure_type = error_ev.get("failure_type", "unknown")
        summary = error_ev.get("summary", "")
        loc = error_ev.get("primary_location") or {}
        loc_str = f"{loc.get('file', '')}:{loc.get('line', '')}" if loc.get("file") else ""

        sections.append(f"""
        <div class="evidence-section">
            <h4>Error Evidence (Round {latest.get('round', '?')})</h4>
            <div class="evidence-item"><strong>Type:</strong> {_esc(failure_type)}</div>
            <div class="evidence-item"><strong>Location:</strong> {_esc(loc_str)}</div>
            <div class="evidence-item"><strong>Summary:</strong> {_esc(summary[:200])}{'...' if len(summary) > 200 else ''}</div>
        </div>
        """)

    # Written files
    written = latest.get("written_files", [])
    if written:
        files_list = "<br>".join(f"• {_esc(f)}" for f in written[:10])
        sections.append(f"""
        <div class="evidence-section">
            <h4>Written Files</h4>
            <div class="files-list">{files_list}</div>
        </div>
        """)

    # Stderr/stdout preview
    stderr = latest.get("stderr", "")[:500]
    if stderr:
        sections.append(f"""
        <div class="evidence-section">
            <h4>Stderr (truncated)</h4>
            <pre class="output">{_esc(stderr)}</pre>
        </div>
        """)

    return "".join(sections) if sections else "<p>No error evidence.</p>"


def render_artifacts(output_dir: Path) -> str:
    """Render artifacts panel with links."""
    artifacts = []

    # Check for common artifact files
    artifact_types = [
        ("result.json", "*.result.json", "Result"),
        ("response.txt", "*.response.txt", "LLM Response"),
        ("debug.html", "*.debug.html", "Debug Dashboard"),
        ("hunk.md", "*.hunk.md", "Hunk Review"),
    ]

    for pattern_name, pattern, label in artifact_types:
        matches = list(output_dir.glob(pattern))
        if matches:
            for m in matches[:3]:  # Limit to 3 matches per type
                artifacts.append(f'<li><a href="{m.name}" target="_blank">{label}: {m.name}</a></li>')

    # Logs directory
    logs_dir = output_dir / "logs"
    if logs_dir.exists():
        log_files = list(logs_dir.glob("*.txt")) + list(logs_dir.glob("*.json"))
        if log_files:
            artifacts.append(f'<li><strong>Logs:</strong> {len(log_files)} files in logs/</li>')

    if not artifacts:
        return "<p>No artifacts found.</p>"

    return f"<ul class='artifacts-list'>{''.join(artifacts)}</ul>"


def generate_html(output_dir: Path) -> str:
    """Generate complete HTML page for a run."""
    data = load_run_data(output_dir)

    task_id = ""
    if data["run"]:
        task_id = data["run"].get("run_id", "")
    elif data["result"]:
        task_id = data["result"].get("task_id", "")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Run: {task_id}</title>
    <style>
        :root {{
            --bg: #0d1117;
            --card-bg: #161b22;
            --border: #30363d;
            --text: #c9d1d9;
            --text-muted: #8b949e;
            --accent: #58a6ff;
            --green: #3fb950;
            --red: #f85149;
            --orange: #d29922;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
            background: var(--bg);
            color: var(--text);
            padding: 20px;
            line-height: 1.5;
        }}
        h1 {{ color: var(--accent); margin-bottom: 20px; font-size: 1.5rem; }}
        h2 {{ color: var(--text); margin: 20px 0 10px; font-size: 1.1rem; border-bottom: 1px solid var(--border); padding-bottom: 8px; }}
        h3 {{ color: var(--text-muted); margin: 15px 0 8px; font-size: 0.95rem; }}
        h4 {{ color: var(--text-muted); margin: 10px 0 5px; font-size: 0.85rem; }}

        .container {{ max-width: 1200px; margin: 0 auto; }}
        .card {{ background: var(--card-bg); border: 1px solid var(--border); border-radius: 8px; padding: 15px; margin-bottom: 15px; }}

        .badge {{
            display: inline-block;
            padding: 3px 10px;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
            color: white;
            text-transform: uppercase;
        }}
        .reason {{ color: var(--text-muted); font-size: 0.85rem; }}

        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 15px;
        }}
        .summary-item .label {{ color: var(--text-muted); font-size: 0.75rem; text-transform: uppercase; }}
        .summary-item .value {{ font-size: 1rem; margin-top: 4px; }}
        .summary-item .score {{ font-family: monospace; font-size: 1.2rem; color: var(--accent); }}

        table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
        th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
        th {{ color: var(--text-muted); font-weight: 500; text-transform: uppercase; font-size: 0.7rem; }}

        .timeline-table .ts {{ color: var(--text-muted); font-family: monospace; white-space: nowrap; }}
        .timeline-table .round {{ color: var(--accent); font-weight: 500; }}
        .timeline-table .event {{ white-space: nowrap; }}
        .timeline-table .details {{ color: var(--text-muted); font-size: 0.8rem; }}

        .rounds-table .keep {{ background: rgba(63, 185, 80, 0.1); }}
        .rounds-table .discard {{ background: rgba(248, 81, 73, 0.05); }}
        .rounds-table .score {{ font-family: monospace; color: var(--accent); }}

        .evidence-section {{ margin-bottom: 15px; }}
        .evidence-item {{ margin: 5px 0; font-size: 0.9rem; }}
        .files-list {{ font-family: monospace; font-size: 0.8rem; color: var(--text-muted); }}
        pre.output {{
            background: var(--bg);
            padding: 10px;
            border-radius: 4px;
            overflow-x: auto;
            font-size: 0.75rem;
            max-height: 200px;
            overflow-y: auto;
        }}

        .artifacts-list {{ list-style: none; }}
        .artifacts-list li {{ margin: 5px 0; }}
        .artifacts-list a {{ color: var(--accent); text-decoration: none; }}
        .artifacts-list a:hover {{ text-decoration: underline; }}

        .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; }}
        @media (max-width: 768px) {{ .grid-2 {{ grid-template-columns: 1fr; }} }}

        .refresh-note {{ color: var(--text-muted); font-size: 0.75rem; margin-top: 20px; text-align: center; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Run Detail: {task_id}</h1>

        <div class="card">
            <h2>Summary</h2>
            {render_summary(data['run'], data['result'])}
        </div>

        <div class="card">
            <h2>Timeline</h2>
            {render_timeline(data['events'])}
        </div>

        <div class="card">
            <h2>Rounds</h2>
            {render_rounds_table(data['rounds'])}
        </div>

        <div class="grid-2">
            <div class="card">
                <h2>Evidence</h2>
                {render_evidence(data['rounds'])}
            </div>

            <div class="card">
                <h2>Artifacts</h2>
                {render_artifacts(output_dir)}
            </div>
        </div>

        <p class="refresh-note">Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
</body>
</html>
"""
    return html


class RunViewerHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler that serves the run viewer."""

    def __init__(self, *args, output_dir: Path, **kwargs):
        self.output_dir = output_dir
        super().__init__(*args, directory=str(output_dir), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path

        # Support ?dir= query param for fleet dashboard click-through
        if "dir" in query:
            target_dir = Path(query["dir"][0])
            if target_dir.exists() and target_dir.is_dir():
                html_content = generate_html(target_dir)
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.send_header("Content-Length", len(html_content))
                self.end_headers()
                self.wfile.write(html_content.encode())
                return
            else:
                self.send_error(404, f"Directory not found: {target_dir}")
                return

        if path == "/" or path == "/index.html":
            html_content = generate_html(self.output_dir)
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.send_header("Content-Length", len(html_content))
            self.end_headers()
            self.wfile.write(html_content.encode())
        else:
            super().do_GET()

    def log_message(self, format, *args):
        logger.info(format % args)


def find_latest_run(base_dir: Path = Path("/tmp/code-runner")) -> Path | None:
    """Find the most recently modified run directory."""
    if not base_dir.exists():
        return None

    # Look for directories with run.json or events.jsonl
    candidates = []
    for d in base_dir.iterdir():
        if d.is_dir():
            if (d / "run.json").exists() or (d / "events.jsonl").exists():
                candidates.append((d, d.stat().st_mtime))

    if not candidates:
        # Maybe files are directly in base_dir
        if (base_dir / "run.json").exists() or (base_dir / "events.jsonl").exists():
            return base_dir
        return None

    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates[0][0]


@app.command()
def serve(
    output_dir: str = typer.Argument(None, help="Run output directory"),
    port: int = typer.Option(8765, "--port", "-p", help="Port to serve on"),
    latest: bool = typer.Option(False, "--latest", "-l", help="Serve latest run"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser"),
):
    """Serve run detail page in browser."""
    if latest or not output_dir:
        dir_path = find_latest_run()
        if not dir_path:
            logger.error("No runs found in /tmp/code-runner")
            raise typer.Exit(1)
    else:
        dir_path = Path(output_dir)

    if not dir_path.exists():
        logger.error(f"Directory not found: {dir_path}")
        raise typer.Exit(1)

    logger.info(f"Serving run from: {dir_path}")

    handler = lambda *args, **kwargs: RunViewerHandler(*args, output_dir=dir_path, **kwargs)

    with socketserver.TCPServer(("", port), handler) as httpd:
        url = f"http://localhost:{port}"
        logger.info(f"Run viewer at: {url}")

        if not no_browser:
            webbrowser.open(url)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down...")


@app.command()
def generate(
    output_dir: str = typer.Argument(..., help="Run output directory"),
    output: str = typer.Option(None, "--output", "-o", help="Output HTML file"),
    latest: bool = typer.Option(False, "--latest", "-l", help="Use latest run"),
):
    """Generate static HTML report for a run."""
    if latest:
        dir_path = find_latest_run()
        if not dir_path:
            logger.error("No runs found in /tmp/code-runner")
            raise typer.Exit(1)
    else:
        dir_path = Path(output_dir)

    if not dir_path.exists():
        logger.error(f"Directory not found: {dir_path}")
        raise typer.Exit(1)

    html = generate_html(dir_path)

    if output:
        out_path = Path(output)
    else:
        out_path = dir_path / "run_report.html"

    out_path.write_text(html)
    logger.info(f"Report written to: {out_path}")


if __name__ == "__main__":
    app()
