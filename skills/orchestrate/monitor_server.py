"""Session-scoped HTTP server launcher for /orchestrate monitors."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

from loguru import logger


def launch_monitor_server(session_dir: Path) -> str:
    """Serve a session directory and return the monitor URL.

    The browser monitor polls status.json and plan.json. Serving the session
    directory over an owned localhost HTTP surface avoids opaque shared-service
    assumptions and keeps live CDP verification authoritative.
    """
    if os.environ.get("ORCHESTRATE_MONITOR", "1") == "0":
        return ""

    host = "127.0.0.1"
    port = _pick_port()
    command = [
        sys.executable,
        "-m",
        "http.server",
        str(port),
        "--bind",
        host,
        "-d",
        str(session_dir),
    ]
    proc = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    url = f"http://{host}:{port}/monitor.html"
    metadata = {
        "url": url,
        "pid": proc.pid,
        "host": host,
        "port": port,
        "command": command,
    }
    (session_dir / "monitor-server.json").write_text(json.dumps(metadata, indent=2))
    logger.info("Live monitor: {}", url)
    return url


def _pick_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
