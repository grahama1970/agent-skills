#!/usr/bin/env python3
"""Local clipboard bridge for pipeline review HTML (KDE text/uri-list file paste)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PERSONA_DREAM_ROOT = Path(__file__).resolve().parents[1]
REGENERATE_SCRIPT = PERSONA_DREAM_ROOT / "scripts" / "regenerate_asset.py"


def clipboard_run_sh() -> Path:
    skills_root = Path(__file__).resolve().parents[2]
    return skills_root / "clipboard" / "run.sh"


class ClipboardBridgeHandler(BaseHTTPRequestHandler):

    def _handle_regenerate(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_error(400, "invalid json")
            return
        kind = str(payload.get("kind") or "").strip()
        bundle = Path(str(payload.get("bundle") or "")).expanduser().resolve()
        run_root = Path(str(payload.get("run_root") or "")).expanduser().resolve() if payload.get("run_root") else None
        if kind not in {"contact-sheet", "panel"} or not bundle.is_file():
            self.send_error(400, "kind must be contact-sheet|panel with existing bundle path")
            return
        if not REGENERATE_SCRIPT.is_file():
            self.send_error(500, f"missing regenerate script: {REGENERATE_SCRIPT}")
            return
        cmd = [sys.executable, str(REGENERATE_SCRIPT), kind, "--bundle", str(bundle)]
        if run_root is not None:
            cmd.extend(["--run-root", str(run_root)])
        proc = subprocess.run(cmd, capture_output=True, text=True)
        body = json.dumps(
            {
                "ok": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }
        ).encode("utf-8")
        status = 200 if proc.returncode == 0 else 500
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


    server_version = "PipelineReviewClipboardBridge/1.0"

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/regenerate/run":
            self._handle_regenerate()
            return
        if self.path != "/clipboard/file":
            self.send_error(404, "not found")
            return

        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            self.send_error(400, "invalid json")
            return

        raw_path = str(payload.get("path") or "").strip()
        if not raw_path:
            self.send_error(400, "missing path")
            return

        file_path = Path(raw_path).expanduser().resolve()
        if not file_path.is_file():
            self.send_error(404, f"file not found: {file_path}")
            return

        script = clipboard_run_sh()
        if not script.is_file():
            self.send_error(500, f"clipboard skill missing: {script}")
            return

        target = str(payload.get("target") or "kde")
        proc = subprocess.run(
            [str(script), "file", "--target", target, str(file_path)],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            message = (proc.stderr or proc.stdout or "clipboard copy failed").strip()
            self.send_error(500, message)
            return

        body = json.dumps(
            {
                "ok": True,
                "path": str(file_path),
                "clipboard": (proc.stdout or "").strip(),
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8893)
    args = parser.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), ClipboardBridgeHandler)
    print(f"Pipeline review clipboard bridge on http://{args.host}:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
