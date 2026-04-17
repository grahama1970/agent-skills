#!/usr/bin/env python3
"""Fleet Dashboard — Monitor multiple code-runner runs.

Phase 3 of multica-inspired upgrades. Shows all active runs at a glance.

Usage:
    # Serve dashboard on port 8766
    python fleet_dashboard.py serve

    # Watch specific directories
    python fleet_dashboard.py serve --watch /tmp/code-runner --watch /home/user/runs

    # Auto-refresh interval (default 5s)
    python fleet_dashboard.py serve --refresh 3
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

import typer
from loguru import logger


def _esc(text: str | None) -> str:
    """HTML-escape text to prevent XSS."""
    return html.escape(str(text) if text else "")

app = typer.Typer(no_args_is_help=True)

DEFAULT_WATCH_DIRS = [
    Path("/tmp/code-runner"),
    Path.home() / ".pi" / "code-runner",
]


def _fmt_ts(ts: float) -> str:
    """Format Unix timestamp as human-readable."""
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S")


def _fmt_duration(seconds: float) -> str:
    """Format duration in seconds as human-readable."""
    if seconds < 60:
        return f"{seconds:.0f}s"
    elif seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    else:
        return f"{int(seconds // 3600)}h {int((seconds % 3600) // 60)}m"


def _fmt_ago(ts: float) -> str:
    """Format timestamp as 'X ago'."""
    if not ts:
        return "never"
    ago = datetime.now().timestamp() - ts
    if ago < 60:
        return f"{int(ago)}s ago"
    elif ago < 3600:
        return f"{int(ago // 60)}m ago"
    else:
        return f"{int(ago // 3600)}h ago"


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


def discover_runs(watch_dirs: list[Path]) -> list[dict[str, Any]]:
    """Discover all runs in watched directories."""
    runs = []

    for base_dir in watch_dirs:
        if not base_dir.exists():
            continue

        # Check if base_dir itself is a run directory
        if (base_dir / "run.json").exists() or (base_dir / "events.jsonl").exists():
            run_data = load_run(base_dir)
            if run_data:
                runs.append(run_data)
            continue

        # Scan subdirectories
        for d in base_dir.iterdir():
            if d.is_dir():
                if (d / "run.json").exists() or (d / "events.jsonl").exists():
                    run_data = load_run(d)
                    if run_data:
                        runs.append(run_data)

    # Sort by most recent activity first
    runs.sort(key=lambda x: x.get("updated_at", 0), reverse=True)
    return runs


def load_run(run_dir: Path) -> dict[str, Any] | None:
    """Load run data from a directory."""
    data: dict[str, Any] = {
        "dir": str(run_dir),
        "run_id": run_dir.name,
        "state": "unknown",
        "reason_code": None,
        "task_id": run_dir.name,
        "title": "",
        "backend": "",
        "current_round": 0,
        "max_rounds": 5,
        "best_score": 0.0,
        "dod_passed": False,
        "started_at": 0,
        "updated_at": 0,
        "elapsed": 0,
        "last_event": "",
        "heartbeat_fresh": True,
    }

    # Load run.json
    run_file = run_dir / "run.json"
    if run_file.exists():
        try:
            r = json.loads(run_file.read_text())
            data.update({
                "run_id": r.get("run_id", data["run_id"]),
                "state": r.get("state", "unknown"),
                "reason_code": r.get("reason_code"),
                "current_round": r.get("current_round", 0),
                "best_score": r.get("best_score", 0),
                "started_at": r.get("started_at", 0),
                "updated_at": r.get("updated_at", 0),
            })
            # Check heartbeat freshness (stale if >60s)
            if r.get("updated_at"):
                age = datetime.now().timestamp() - r["updated_at"]
                data["heartbeat_fresh"] = age < 60
        except json.JSONDecodeError:
            pass

    # Load result.json for additional context
    result_files = list(run_dir.glob("*.result.json"))
    if result_files:
        try:
            res = json.loads(result_files[0].read_text())
            data.update({
                "task_id": res.get("task_id", data["task_id"]),
                "title": res.get("title", ""),
                "backend": res.get("backend", ""),
                "dod_passed": res.get("dod_passed", False),
                "max_rounds": len(res.get("round_details", [])) or data["max_rounds"],
            })
            # Use result status if run.json state is missing
            if data["state"] == "unknown" and res.get("status"):
                data["state"] = res["status"]
        except json.JSONDecodeError:
            pass

    # Load last event from events.jsonl
    events_file = run_dir / "events.jsonl"
    if events_file.exists():
        try:
            lines = events_file.read_text().strip().split("\n")
            if lines and lines[-1]:
                last = json.loads(lines[-1])
                data["last_event"] = last.get("event", "")
                # Use latest event timestamp if newer
                if last.get("ts", 0) > data.get("updated_at", 0):
                    data["updated_at"] = last["ts"]
        except (json.JSONDecodeError, IndexError):
            pass

    # Calculate elapsed time
    if data["started_at"]:
        end_time = data["updated_at"] or datetime.now().timestamp()
        data["elapsed"] = end_time - data["started_at"]

    return data if data["state"] != "unknown" or data["last_event"] else None


def render_run_card(run: dict[str, Any]) -> str:
    """Render a single run card."""
    state = run["state"]
    reason = run.get("reason_code") or ""
    task_id = run.get("task_id", "unknown")
    title = run.get("title") or task_id
    backend = run.get("backend", "?")
    current = run.get("current_round", 0)
    best_score = run.get("best_score", 0)
    elapsed = run.get("elapsed", 0)
    last_event = run.get("last_event", "")
    updated = run.get("updated_at", 0)
    fresh = run.get("heartbeat_fresh", True)
    run_dir = run.get("dir", "")

    # Determine card style
    state_classes = {
        "running": "running",
        "passed": "passed",
        "failed": "failed",
        "blocked": "blocked",
        "crashed": "crashed",
        "timed_out": "timed_out",
        "preflight_failed": "preflight_failed",
    }
    card_class = state_classes.get(state, "")
    stale_class = "stale" if state == "running" and not fresh else ""

    return f"""
    <div class="run-card {_esc(card_class)} {_esc(stale_class)}" data-dir="{_esc(run_dir)}">
        <div class="card-header">
            <div class="task-title">{_esc(title[:40])}{'...' if len(title) > 40 else ''}</div>
            <div class="state">{_state_badge(state)}</div>
        </div>
        <div class="card-body">
            <div class="metric">
                <span class="label">Score</span>
                <span class="value score">{best_score:.3f}</span>
            </div>
            <div class="metric">
                <span class="label">Round</span>
                <span class="value">{current}</span>
            </div>
            <div class="metric">
                <span class="label">Backend</span>
                <span class="value">{_esc(backend)}</span>
            </div>
            <div class="metric">
                <span class="label">Elapsed</span>
                <span class="value">{_fmt_duration(elapsed)}</span>
            </div>
        </div>
        <div class="card-footer">
            <span class="last-event">{_esc(last_event.replace('_', ' '))}</span>
            <span class="updated {'stale-warn' if not fresh else ''}">{_fmt_ago(updated)}</span>
        </div>
        {f'<div class="reason-bar">{_esc(reason)}</div>' if reason else ''}
    </div>
    """


def generate_dashboard_html(runs: list[dict], refresh_interval: int = 5) -> str:
    """Generate the fleet dashboard HTML."""
    now = datetime.now().strftime("%H:%M:%S")

    # Categorize runs
    active = [r for r in runs if r["state"] in ("running", "queued")]
    completed = [r for r in runs if r["state"] in ("passed", "failed")]
    problems = [r for r in runs if r["state"] in ("blocked", "crashed", "timed_out", "preflight_failed")]

    active_cards = "".join(render_run_card(r) for r in active) or '<p class="empty">No active runs</p>'
    problem_cards = "".join(render_run_card(r) for r in problems) or '<p class="empty">No issues</p>'
    completed_cards = "".join(render_run_card(r) for r in completed[:10]) or '<p class="empty">No completed runs</p>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="{refresh_interval}">
    <title>Code-Runner Fleet</title>
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
            --purple: #a371f7;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
            background: var(--bg);
            color: var(--text);
            padding: 20px;
            line-height: 1.4;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 20px;
            padding-bottom: 15px;
            border-bottom: 1px solid var(--border);
        }}
        h1 {{ color: var(--accent); font-size: 1.4rem; }}
        .status-bar {{
            display: flex;
            gap: 20px;
            font-size: 0.85rem;
        }}
        .status-item {{ color: var(--text-muted); }}
        .status-item strong {{ color: var(--text); }}

        h2 {{
            color: var(--text-muted);
            font-size: 0.9rem;
            margin: 20px 0 10px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}

        .runs-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 12px;
        }}

        .run-card {{
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 12px;
            cursor: pointer;
            transition: border-color 0.2s, transform 0.1s;
        }}
        .run-card:hover {{
            border-color: var(--accent);
            transform: translateY(-2px);
        }}
        .run-card.running {{ border-left: 3px solid var(--accent); }}
        .run-card.passed {{ border-left: 3px solid var(--green); }}
        .run-card.failed {{ border-left: 3px solid var(--red); }}
        .run-card.blocked {{ border-left: 3px solid var(--orange); background: rgba(210, 153, 34, 0.05); }}
        .run-card.crashed {{ border-left: 3px solid var(--red); background: rgba(248, 81, 73, 0.08); }}
        .run-card.timed_out {{ border-left: 3px solid var(--orange); }}
        .run-card.preflight_failed {{ border-left: 3px solid var(--purple); }}
        .run-card.stale {{ opacity: 0.7; }}

        .card-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 10px;
        }}
        .task-title {{
            font-size: 0.9rem;
            font-weight: 500;
            color: var(--text);
        }}

        .badge {{
            display: inline-block;
            padding: 2px 8px;
            border-radius: 3px;
            font-size: 0.65rem;
            font-weight: 600;
            color: white;
            text-transform: uppercase;
        }}

        .card-body {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 8px;
            margin-bottom: 10px;
        }}
        .metric {{
            display: flex;
            flex-direction: column;
        }}
        .metric .label {{
            font-size: 0.65rem;
            color: var(--text-muted);
            text-transform: uppercase;
        }}
        .metric .value {{
            font-size: 0.9rem;
            font-family: monospace;
        }}
        .metric .score {{ color: var(--accent); font-weight: 500; }}

        .card-footer {{
            display: flex;
            justify-content: space-between;
            font-size: 0.75rem;
            color: var(--text-muted);
            border-top: 1px solid var(--border);
            padding-top: 8px;
        }}
        .last-event {{ text-transform: capitalize; }}
        .updated.stale-warn {{ color: var(--orange); }}

        .reason-bar {{
            margin-top: 8px;
            padding: 4px 8px;
            background: rgba(248, 81, 73, 0.1);
            border-radius: 4px;
            font-size: 0.75rem;
            color: var(--orange);
        }}

        .empty {{
            color: var(--text-muted);
            font-size: 0.85rem;
            padding: 20px;
            text-align: center;
        }}

        .section {{ margin-bottom: 30px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Code-Runner Fleet</h1>
        <div class="status-bar">
            <span class="status-item"><strong>{len(active)}</strong> active</span>
            <span class="status-item"><strong>{len(problems)}</strong> issues</span>
            <span class="status-item"><strong>{len(completed)}</strong> completed</span>
            <span class="status-item">Updated: {now}</span>
        </div>
    </div>

    <div class="section">
        <h2>Active Runs ({len(active)})</h2>
        <div class="runs-grid">
            {active_cards}
        </div>
    </div>

    {'<div class="section"><h2>Issues (' + str(len(problems)) + ')</h2><div class="runs-grid">' + problem_cards + '</div></div>' if problems else ''}

    <div class="section">
        <h2>Recent Completed ({min(len(completed), 10)})</h2>
        <div class="runs-grid">
            {completed_cards}
        </div>
    </div>

    <script>
        document.querySelectorAll('.run-card').forEach(card => {{
            card.addEventListener('click', () => {{
                const dir = card.dataset.dir;
                // Open run detail in new tab (assumes run_viewer is running on 8765)
                window.open('http://localhost:8765?dir=' + encodeURIComponent(dir), '_blank');
            }});
        }});
    </script>
</body>
</html>
"""


class FleetHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler for fleet dashboard."""

    watch_dirs: list[Path] = []
    refresh_interval: int = 5

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            runs = discover_runs(self.watch_dirs)
            html = generate_dashboard_html(runs, self.refresh_interval)
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.send_header("Content-Length", len(html))
            self.end_headers()
            self.wfile.write(html.encode())
        elif self.path == "/api/runs":
            runs = discover_runs(self.watch_dirs)
            data = json.dumps(runs, default=str)
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Content-Length", len(data))
            self.end_headers()
            self.wfile.write(data.encode())
        else:
            self.send_error(404)

    def log_message(self, format, *args):
        logger.debug(format % args)


@app.command()
def serve(
    port: int = typer.Option(8766, "--port", "-p", help="Port to serve on"),
    watch: list[str] = typer.Option(None, "--watch", "-w", help="Directories to watch"),
    refresh: int = typer.Option(5, "--refresh", "-r", help="Auto-refresh interval in seconds"),
    no_browser: bool = typer.Option(False, "--no-browser", help="Don't open browser"),
):
    """Serve the fleet dashboard."""
    if watch:
        watch_dirs = [Path(w) for w in watch]
    else:
        watch_dirs = [d for d in DEFAULT_WATCH_DIRS if d.exists()]
        if not watch_dirs:
            watch_dirs = [Path("/tmp/code-runner")]

    logger.info(f"Watching directories: {[str(d) for d in watch_dirs]}")

    FleetHandler.watch_dirs = watch_dirs
    FleetHandler.refresh_interval = refresh

    with socketserver.TCPServer(("", port), FleetHandler) as httpd:
        url = f"http://localhost:{port}"
        logger.info(f"Fleet dashboard at: {url}")

        if not no_browser:
            webbrowser.open(url)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down...")


@app.command()
def list_runs(
    watch: list[str] = typer.Option(None, "--watch", "-w", help="Directories to watch"),
    json_out: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all discovered runs."""
    if watch:
        watch_dirs = [Path(w) for w in watch]
    else:
        watch_dirs = [d for d in DEFAULT_WATCH_DIRS if d.exists()]
        if not watch_dirs:
            watch_dirs = [Path("/tmp/code-runner")]

    runs = discover_runs(watch_dirs)

    if json_out:
        print(json.dumps(runs, indent=2, default=str))
    else:
        if not runs:
            print("No runs found.")
            return

        print(f"{'STATE':<12} {'SCORE':>6} {'ROUND':>5} {'TASK':<30} {'ELAPSED':>10}")
        print("-" * 70)
        for r in runs:
            state = r.get("state", "?")[:10]
            score = r.get("best_score", 0)
            round_n = r.get("current_round", 0)
            task = (r.get("title") or r.get("task_id", "?"))[:28]
            elapsed = _fmt_duration(r.get("elapsed", 0))
            print(f"{state:<12} {score:>6.3f} {round_n:>5} {task:<30} {elapsed:>10}")


if __name__ == "__main__":
    app()
