#!/usr/bin/env python3
"""Local whiteboard bridge: serve embedded Excalidraw page, list/load libraries, render boards to SVG.

Endpoints:
  GET  /                  -> assets/whiteboard/index.html
  GET  /libraries         -> JSON list of available .excalidrawlib names
  GET  /library/<name>    -> raw .excalidrawlib JSON
  POST /render            -> body: Excalidraw scene JSON; runs compile + create-svg render; returns SVG
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
BOARD_STATE: dict[str, object] = {"version": 0, "scene": None}  # ponytail: in-memory single-board state; move to files if multi-board is ever needed
TOOLKITS = SKILL / "assets/toolkits"
PAGE = SKILL / "assets/whiteboard/index.html"
CREATE_SVG = SKILL.parent / "create-svg/run.sh"


def library_files() -> dict[str, Path]:
    files = list(TOOLKITS.glob("*.excalidrawlib")) + list((TOOLKITS / "vendor").glob("*.excalidrawlib"))
    return {p.name: p for p in files}


def render_scene(raw: bytes) -> tuple[int, bytes, str]:
    with tempfile.TemporaryDirectory() as tmp:
        board = Path(tmp) / "board.excalidraw"
        scene = Path(tmp) / "scene.yml"
        svg = Path(tmp) / "out.svg"
        board.write_bytes(raw)
        compile_proc = subprocess.run(
            [str(SKILL / "run.sh"), "compile", str(board), str(scene)],
            capture_output=True, text=True, timeout=60,
        )
        if compile_proc.returncode != 0:
            return 422, compile_proc.stderr.encode(), "application/json"
        render_proc = subprocess.run(
            [str(CREATE_SVG), "render", str(scene), str(svg)],
            capture_output=True, text=True, timeout=120,
        )
        if render_proc.returncode != 0 or not svg.exists():
            body = json.dumps({"schema": "ops_excalidraw.error.v1", "status": "FAIL", "error": render_proc.stderr[-2000:]})
            return 500, body.encode(), "application/json"
        return 200, svg.read_bytes(), "image/svg+xml"


class Handler(BaseHTTPRequestHandler):
    def reply(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        self.path, _, query = self.path.partition("?")  # route on path only
        if self.path in ("/", "/index.html"):
            self.reply(200, PAGE.read_bytes(), "text/html")
        elif self.path.startswith(("/vendor/", "/static/")):
            name = Path(self.path.split("?")[0]).name  # flatten: no traversal, strip query
            path = PAGE.parent / "vendor" / name
            if path.is_file():
                self.reply(200, path.read_bytes(), "application/javascript")
            else:
                self.reply(404, b"not found", "text/plain")
        elif self.path == "/libraries":
            self.reply(200, json.dumps(sorted(library_files())).encode(), "application/json")
        elif self.path.startswith("/board"):
            since = 0
            if "since=" in query:
                try:
                    since = int(query.split("since=")[1].split("&")[0])
                except ValueError:
                    since = 0
            if BOARD_STATE["scene"] is None or BOARD_STATE["version"] <= since:
                self.reply(204, b"", "application/json")
            else:
                self.reply(200, json.dumps(BOARD_STATE).encode(), "application/json")
        elif self.path.startswith("/library/"):
            name = self.path.removeprefix("/library/")
            path = library_files().get(name)
            if path is None:
                self.reply(404, b'{"error":"unknown library"}', "application/json")
            else:
                self.reply(200, path.read_bytes(), "application/json")
        else:
            self.reply(404, b"not found", "text/plain")

    def do_POST(self) -> None:  # noqa: N802
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.path == "/board":
            try:
                scene = json.loads(raw)
                if scene.get("type") != "excalidraw" or not isinstance(scene.get("elements"), list):
                    raise ValueError("not an excalidraw scene")
            except (ValueError, json.JSONDecodeError) as exc:
                self.reply(422, json.dumps({"error": str(exc)}).encode(), "application/json")
                return
            BOARD_STATE["version"] = int(BOARD_STATE["version"]) + 1
            BOARD_STATE["scene"] = scene
            self.reply(200, json.dumps({"version": BOARD_STATE["version"], "elements": len(scene["elements"])}).encode(), "application/json")
            return
        if self.path != "/render":
            self.reply(404, b"not found", "text/plain")
            return
        try:
            code, body, ctype = render_scene(raw)
        except subprocess.TimeoutExpired:
            code, body, ctype = 504, b'{"error":"render timeout"}', "application/json"
        self.reply(code, body, ctype)

    def log_message(self, *args: object) -> None:
        pass


def main() -> None:
    import sys

    port = int(sys.argv[1]) if len(sys.argv) > 1 else 7683
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(json.dumps({"schema": "ops_excalidraw.whiteboard.v1", "url": f"http://127.0.0.1:{port}/", "libraries": sorted(library_files())}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
