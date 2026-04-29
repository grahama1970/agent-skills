"""Read-only browser viewer for /ask runtime artifacts."""

from __future__ import annotations

import json
import secrets
import time
import webbrowser
from datetime import datetime, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .run_state import TERMINAL_STATES, atomic_write_json, read_event_tail, resolve_run_target


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>/ask run monitor</title>
  <link rel="stylesheet" href="ask-viewer.css">
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div>
        <p class="eyebrow">/ask runtime monitor</p>
        <h1 id="run-title">Loading run…</h1>
      </div>
      <div id="state-pill" class="pill">loading</div>
    </section>
    <section class="grid">
      <article class="card">
        <h2>Route</h2>
        <dl id="route-list"></dl>
      </article>
      <article class="card">
        <h2>Artifacts</h2>
        <ul id="artifact-list"></ul>
      </article>
      <article class="card wide">
        <h2>Needs Attention</h2>
        <pre id="attention-block">No active needs_attention state.</pre>
      </article>
      <article class="card wide">
        <h2>Events</h2>
        <ol id="event-list" class="events"></ol>
      </article>
    </section>
  </main>
  <script src="ask-viewer.js"></script>
</body>
</html>
"""


STYLE_CSS = """:root {
  color-scheme: dark;
  --bg: #0b1020;
  --card: #121a2f;
  --card-2: #18213a;
  --text: #e8eefc;
  --muted: #97a4bd;
  --line: #2b3658;
  --ok: #41d48f;
  --warn: #f4c95d;
  --bad: #ff6b7a;
  --info: #66a3ff;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: radial-gradient(circle at top left, #18213a 0, var(--bg) 42rem);
  color: var(--text);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.shell { width: min(1180px, calc(100vw - 32px)); margin: 28px auto; }
.hero {
  display: flex;
  justify-content: space-between;
  gap: 20px;
  align-items: flex-start;
  margin-bottom: 20px;
}
.eyebrow { color: var(--muted); letter-spacing: .12em; text-transform: uppercase; font-size: 12px; margin: 0 0 8px; }
h1 { font-size: clamp(28px, 4vw, 44px); margin: 0; }
h2 { margin: 0 0 14px; font-size: 16px; color: #cfd8ef; }
.pill {
  border: 1px solid var(--line);
  border-radius: 999px;
  padding: 8px 14px;
  color: var(--muted);
  background: rgba(18, 26, 47, .84);
  white-space: nowrap;
}
.pill.running { color: var(--info); border-color: var(--info); }
.pill.answered, .pill.completed { color: var(--ok); border-color: var(--ok); }
.pill.needs_attention { color: var(--warn); border-color: var(--warn); }
.pill.failed { color: var(--bad); border-color: var(--bad); }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.card {
  background: linear-gradient(180deg, rgba(24, 33, 58, .94), rgba(18, 26, 47, .94));
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 18px;
  box-shadow: 0 16px 48px rgba(0, 0, 0, .22);
}
.wide { grid-column: 1 / -1; }
dl { display: grid; grid-template-columns: 140px 1fr; gap: 10px 14px; margin: 0; }
dt { color: var(--muted); }
dd { margin: 0; overflow-wrap: anywhere; }
ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
a { color: #a9c8ff; text-decoration: none; }
a:hover { text-decoration: underline; }
pre {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: #dce6ff;
  background: rgba(11, 16, 32, .55);
  border: 1px solid rgba(43, 54, 88, .8);
  border-radius: 12px;
  padding: 12px;
}
.events { margin: 0; padding: 0; list-style: none; display: grid; gap: 10px; }
.event {
  display: grid;
  grid-template-columns: 210px 190px 1fr;
  gap: 10px;
  align-items: baseline;
  padding: 10px 12px;
  background: rgba(11, 16, 32, .45);
  border: 1px solid rgba(43, 54, 88, .72);
  border-radius: 12px;
}
.event time { color: var(--muted); font-size: 12px; }
.event strong { color: #ffffff; }
.event code { color: #b8c5df; white-space: pre-wrap; overflow-wrap: anywhere; }
@media (max-width: 780px) {
  .grid { grid-template-columns: 1fr; }
  .hero { flex-direction: column; }
  dl, .event { grid-template-columns: 1fr; }
}
"""


SCRIPT_JS = """const params = new URLSearchParams(window.location.search);
const token = params.get("token") || "";
const statusFile = params.get("status") || window.ASK_STATUS_FILE || "";
const eventsFile = params.get("events") || window.ASK_EVENTS_FILE || "";
const requestFile = params.get("request") || window.ASK_REQUEST_FILE || "";
const runDir = window.ASK_RUN_DIR || "";

function withToken(path) {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}token=${encodeURIComponent(token)}&t=${Date.now()}`;
}

function text(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

function renderRoute(status, request) {
  const list = document.getElementById("route-list");
  const rows = [
    ["Question", request.question || status.question || status.result_summary?.question],
    ["Mode", status.mode || request.command || "ask"],
    ["Scope", request.scope],
    ["Current step", status.current_step],
    ["Oracle", request.oracle ? `${request.oracle_backend || "auto"} / ${request.oracle_model || ""}` : "off"],
    ["SPARTA preflight", status.preflight?.route || request.preflight?.route],
    ["Updated", status.updated_at],
  ];
  list.replaceChildren(...rows.map(([key, value]) => {
    const fragment = document.createDocumentFragment();
    const term = document.createElement("dt");
    term.textContent = key;
    const detail = document.createElement("dd");
    detail.textContent = text(value);
    fragment.append(term, detail);
    return fragment;
  }));
}

function renderArtifacts(status) {
  const list = document.getElementById("artifact-list");
  const artifacts = status.artifacts || {};
  const rows = Object.entries(artifacts).map(([name, path]) => {
    const item = document.createElement("li");
    const anchor = document.createElement("a");
    const absolutePath = String(path);
    let relativePath = absolutePath.split("/").pop();
    if (runDir && absolutePath.startsWith(runDir + "/")) {
      relativePath = absolutePath.slice(runDir.length + 1);
    }
    anchor.href = withToken(relativePath);
    anchor.textContent = `${name}: ${path}`;
    item.append(anchor);
    return item;
  });
  list.replaceChildren(...rows);
}

function renderEvents(lines) {
  const list = document.getElementById("event-list");
  const events = lines.filter(Boolean).slice(-80).map((line) => {
    try { return JSON.parse(line); } catch { return { event: "unparseable", raw: line }; }
  });
  list.replaceChildren(...events.map((event) => {
    const item = document.createElement("li");
    item.className = "event";
    const time = document.createElement("time");
    time.textContent = event.ts || "";
    const name = document.createElement("strong");
    name.textContent = event.event || "event";
    const data = document.createElement("code");
    const clone = { ...event };
    delete clone.ts;
    delete clone.event;
    data.textContent = Object.keys(clone).length ? JSON.stringify(clone) : "";
    item.append(time, name, data);
    return item;
  }));
}

async function fetchJson(path) {
  const response = await fetch(withToken(path), { cache: "no-store" });
  if (!response.ok) throw new Error(`${path}: ${response.status}`);
  return await response.json();
}

async function fetchText(path) {
  const response = await fetch(withToken(path), { cache: "no-store" });
  if (!response.ok) return "";
  return await response.text();
}

async function refresh() {
  const [status, request, eventsText] = await Promise.all([
    fetchJson(statusFile),
    requestFile ? fetchJson(requestFile).catch(() => ({})) : Promise.resolve({}),
    eventsFile ? fetchText(eventsFile) : Promise.resolve(""),
  ]);
  const state = status.state || "unknown";
  const title = document.getElementById("run-title");
  title.textContent = status.ask_id || status.run_id || "ask run";
  const pill = document.getElementById("state-pill");
  pill.className = `pill ${state}`;
  pill.textContent = state;
  renderRoute(status, request);
  renderArtifacts(status);
  document.getElementById("attention-block").textContent = status.needs_attention
    ? JSON.stringify(status.needs_attention, null, 2)
    : "No active needs_attention state.";
  renderEvents(eventsText.split("\\n"));
}

refresh().catch((error) => {
  document.getElementById("attention-block").textContent = `Viewer error: ${error.message}`;
});
setInterval(() => refresh().catch(() => undefined), 1000);
"""


class TokenHandler(SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler with a query-token gate."""

    token: str = ""

    def do_GET(self) -> None:
        if self.token:
            parsed = urlparse(self.path)
            values = parse_qs(parsed.query).get("token", [])
            if values != [self.token]:
                self.send_error(403, "missing or invalid token")
                return
            self.path = parsed.path
        super().do_GET()

    def log_message(self, format: str, *args: Any) -> None:
        return None


def write_viewer_files(status_path: Path) -> dict[str, str]:
    status = json.loads(status_path.read_text())
    artifacts = status.get("artifacts", {})
    run_dir = Path(artifacts.get("run_dir") or status_path.parent)
    request_path = Path(artifacts.get("request") or run_dir / f"{status_path.stem.replace('.status', '')}.request.json")
    events_path = Path(artifacts.get("events") or run_dir / f"{status_path.stem.replace('.status', '')}.events.jsonl")

    index_path = run_dir / "index.html"
    css_path = run_dir / "ask-viewer.css"
    js_path = run_dir / "ask-viewer.js"
    manifest_path = run_dir / "viewer.json"

    index_path.write_text(
        INDEX_HTML.replace(
            "<script src=\"ask-viewer.js\"></script>",
            (
                "<script>"
                f"window.ASK_STATUS_FILE = {json.dumps(status_path.name)};"
                f"window.ASK_REQUEST_FILE = {json.dumps(request_path.name)};"
                f"window.ASK_EVENTS_FILE = {json.dumps(events_path.name)};"
                f"window.ASK_RUN_DIR = {json.dumps(str(run_dir))};"
                "</script>\n  <script src=\"ask-viewer.js\"></script>"
            ),
        )
    )
    css_path.write_text(STYLE_CSS)
    js_path.write_text(SCRIPT_JS)

    viewer_artifacts = {
        "viewer": str(index_path),
        "viewer_manifest": str(manifest_path),
    }
    updated_artifacts = dict(artifacts)
    updated_artifacts.update(viewer_artifacts)
    status["artifacts"] = updated_artifacts
    status["updated_at"] = datetime.now(timezone.utc).isoformat()
    atomic_write_json(status_path, status)

    manifest = {
        "schema": "ask.viewer.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": str(status_path),
        "request": str(request_path),
        "events": str(events_path),
        "index": str(index_path),
    }
    atomic_write_json(manifest_path, manifest)
    return {
        "run_dir": str(run_dir),
        "index": str(index_path),
        "status": str(status_path),
        "request": str(request_path),
        "events": str(events_path),
        "manifest": str(manifest_path),
    }


def serve_run_viewer(
    target: str,
    *,
    output_root: Path | str | None = None,
    host: str = "127.0.0.1",
    port: int = 0,
    open_browser: bool = False,
    terminal_ttl_seconds: float = 30.0,
    max_seconds: float = 900.0,
) -> dict[str, Any]:
    status_path = resolve_run_target(target, output_root)
    if not status_path.exists():
        raise FileNotFoundError(f"Run status not found: {target}")
    artifacts = write_viewer_files(status_path)
    run_dir = Path(artifacts["run_dir"])
    token = secrets.token_urlsafe(18)

    class BoundTokenHandler(TokenHandler):
        pass

    BoundTokenHandler.token = token

    handler_class = partial(BoundTokenHandler, directory=str(run_dir))
    server = ThreadingHTTPServer((host, port), handler_class)
    server.timeout = 0.5
    actual_port = int(server.server_address[1])
    status_name = Path(artifacts["status"]).name
    request_name = Path(artifacts["request"]).name
    events_name = Path(artifacts["events"]).name
    url = (
        f"http://{host}:{actual_port}/index.html"
        f"?token={token}&status={status_name}&request={request_name}&events={events_name}"
    )
    marker = run_dir / "viewer-latest.json"
    atomic_write_json(marker, {"url": url, "artifacts": artifacts, "updated_at": datetime.now(timezone.utc).isoformat()})
    print(url, flush=True)
    if open_browser:
        webbrowser.open(url)

    started = time.monotonic()
    terminal_seen_at: float | None = None
    try:
        while True:
            server.handle_request()
            if time.monotonic() - started > max_seconds:
                break
            try:
                status = json.loads(status_path.read_text())
            except (OSError, json.JSONDecodeError):
                status = {}
            if status.get("state") in TERMINAL_STATES:
                if terminal_seen_at is None:
                    terminal_seen_at = time.monotonic()
                elif time.monotonic() - terminal_seen_at >= terminal_ttl_seconds:
                    break
            else:
                terminal_seen_at = None
    finally:
        server.server_close()
    return {"url": url, "artifacts": artifacts, "marker": str(marker)}


def viewer_snapshot(target: str, *, output_root: Path | str | None = None, tail_events: int = 80) -> dict[str, Any]:
    status_path = resolve_run_target(target, output_root)
    artifacts = write_viewer_files(status_path)
    status = json.loads(status_path.read_text())
    events_path = Path(status.get("artifacts", {}).get("events", ""))
    return {
        "artifacts": artifacts,
        "status": status,
        "events": read_event_tail(events_path, tail_events),
    }
