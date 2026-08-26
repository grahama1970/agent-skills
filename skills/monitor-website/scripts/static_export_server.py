#!/usr/bin/env python3
"""Serve a Next static export with extensionless route fallback."""

from __future__ import annotations

import http.server
import socketserver
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


class StaticExportHandler(http.server.SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        root = Path(self.directory).resolve()
        parsed = urlsplit(path)
        route = unquote(parsed.path)
        if route == "/":
            return str(root / "index.html")

        candidate = (root / route.lstrip("/")).resolve()
        if candidate.is_dir():
            return str(candidate / "index.html")
        if candidate.exists():
            return str(candidate)

        if not Path(route).suffix:
            html = candidate.with_suffix(".html")
            if html.exists():
                return str(html)

        return str(candidate)


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: static_export_server.py <port> <directory>")
    port = int(sys.argv[1])
    directory = sys.argv[2]
    handler = lambda *args, **kwargs: StaticExportHandler(*args, directory=directory, **kwargs)
    with socketserver.TCPServer(("127.0.0.1", port), handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    main()
