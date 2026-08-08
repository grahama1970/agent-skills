#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from dotenv import load_dotenv
from project_registry import expand_url, load_registry, workspace_path


load_dotenv(override=False)
HOST = os.environ.get("UX_LAB_HOST", "127.0.0.1")
PORT = int(os.environ.get("UX_LAB_PORT", "3002"))


def render_project(project: dict, selected: bool) -> str:
    surfaces = []
    for surface in project["surfaces"]:
        mounted = "mounted" if surface.get("mounted") else "declared"
        note = surface.get("note", "")
        surfaces.append(
            "<li>"
            f"<a href=\"{html.escape(expand_url(surface['url']))}\">{html.escape(surface.get('label', surface['id']))}</a>"
            f"<span class=\"badge {mounted}\">{mounted}</span>"
            f"<code>{html.escape(surface['id'])}</code>"
            + (f"<p>{html.escape(note)}</p>" if note else "")
            + "</li>"
        )
    docs = "".join(f"<li><code>{html.escape(path)}</code></li>" for path in project.get("docs", []))
    selected_class = " selected" if selected else ""
    return f"""
      <section class="project{selected_class}" id="{html.escape(project['id'])}">
        <header>
          <h2>{html.escape(project.get('label', project['id']))}</h2>
          <code>{html.escape(project['id'])}</code>
        </header>
        <p>{html.escape(project.get('description', ''))}</p>
        <dl>
          <dt>Workspace</dt>
          <dd><code>{html.escape(str(workspace_path(project)))}</code></dd>
        </dl>
        <h3>Surfaces</h3>
        <ul class="surfaces">{''.join(surfaces)}</ul>
        <h3>Docs</h3>
        <ul class="docs">{docs}</ul>
      </section>
    """


def render_page(selected_project: str | None = None) -> bytes:
    registry = load_registry()
    selected_project = selected_project or registry.get("default_project")
    cards = "\n".join(render_project(project, project["id"] == selected_project) for project in registry["projects"])
    nav = "\n".join(
        f"<a href=\"/?project={html.escape(project['id'])}\">{html.escape(project.get('label', project['id']))}</a>"
        for project in registry["projects"]
    )
    body = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>UX Lab Project Hub</title>
  <style>
    :root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; background: #111312; color: #edf2ee; }}
    body {{ margin: 0; }}
    main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
    h1 {{ margin: 0 0 8px; font-size: 30px; letter-spacing: 0; }}
    h2 {{ margin: 0; font-size: 18px; letter-spacing: 0; }}
    h3 {{ margin: 18px 0 8px; font-size: 13px; text-transform: uppercase; letter-spacing: .06em; color: #9fb3a8; }}
    p {{ color: #c9d6ce; line-height: 1.48; }}
    nav {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 22px 0; }}
    nav a, .surfaces a {{ color: #9ee6bd; text-decoration: none; }}
    nav a {{ border: 1px solid #2d4738; padding: 7px 10px; border-radius: 6px; background: #17211b; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(330px, 1fr)); gap: 14px; }}
    .project {{ border: 1px solid #27362e; border-radius: 8px; padding: 16px; background: #151a17; }}
    .project.selected {{ border-color: #80d49d; box-shadow: 0 0 0 1px #80d49d33 inset; }}
    .project header {{ display: flex; justify-content: space-between; gap: 16px; align-items: baseline; }}
    code {{ color: #d8e7dd; background: #202821; padding: 2px 5px; border-radius: 4px; font-size: 12px; }}
    dl {{ display: grid; grid-template-columns: 92px 1fr; gap: 6px 12px; }}
    dt {{ color: #91a397; }}
    dd {{ margin: 0; overflow-wrap: anywhere; }}
    ul {{ padding-left: 18px; }}
    li {{ margin: 8px 0; }}
    .surfaces p {{ margin: 5px 0 0; font-size: 13px; }}
    .badge {{ margin: 0 7px; padding: 2px 6px; border-radius: 999px; font-size: 11px; }}
    .badge.mounted {{ background: #21452f; color: #c7f7d5; }}
    .badge.declared {{ background: #443d24; color: #f7e9b6; }}
  </style>
</head>
<body>
  <main>
    <h1>UX Lab Project Hub</h1>
    <p>Multi-project housing for agent-skills UI surfaces. Project apps keep ownership of their runtimes; UX Lab makes their surfaces discoverable and fail-closed when a route is only declared.</p>
    <nav>{nav}</nav>
    <div class="grid">{cards}</div>
  </main>
</body>
</html>"""
    return body.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/projects.json":
            payload = load_registry()
            for project in payload["projects"]:
                for surface in project["surfaces"]:
                    surface["url"] = expand_url(surface["url"])
            data = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if parsed.path not in ("", "/"):
            self.send_error(404)
            return
        selected = parse_qs(parsed.query).get("project", [None])[0]
        data = render_page(selected)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        print(f"ux-lab: {self.address_string()} - {format % args}")


def main() -> int:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"UX Lab Project Hub: http://{HOST}:{PORT}/")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
