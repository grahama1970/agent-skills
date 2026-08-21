#!/usr/bin/env python3
"""Live OS pointer replay against Chrome inside Xvfb.

This isolates the OS input path from the user's desktop session. Chrome is
visible to the virtual X server, Surf dispatches pointer samples through
xdotool, and CDP is used only for setup/readback on a random non-9222 port.
"""

from __future__ import annotations

import argparse
import contextlib
import functools
import http.server
import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any


SURF_ROOT = Path(__file__).resolve().parents[1]
RUN_SH = SURF_ROOT / "run.sh"
UV_ENV = "/tmp/surf-live-os-pointer-xvfb-venv"


def free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def tcp_open(port: int) -> bool:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def find_chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError("Chrome/Chromium executable not found")


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}\n"
            f"stdout={completed.stdout}\nstderr={completed.stderr}"
        )
    return completed


def wait_json(url: str, timeout_seconds: float = 15.0) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    raise RuntimeError(f"timed out waiting for {url}: {last_error}")


def run_surf(args: list[str], *, env: dict[str, str], port: int, timeout: int = 45) -> dict[str, Any]:
    surf_env = env.copy()
    surf_env["CDP_PORT"] = str(port)
    surf_env.setdefault("UV_PROJECT_ENVIRONMENT", UV_ENV)
    completed = run([str(RUN_SH), *args], cwd=SURF_ROOT, env=surf_env, timeout=timeout)
    return json.loads(completed.stdout)


def evaluate(expression: str, *, env: dict[str, str], port: int) -> Any:
    result = run_surf(
        [
            "cdp.raw",
            "Runtime.evaluate",
            "--params-json",
            json.dumps({"expression": expression, "returnByValue": True, "awaitPromise": True}),
            "--json",
        ],
        env=env,
        port=port,
    )
    return result["result"]["result"].get("value")


def write_page(root: Path) -> None:
    (root / "index.html").write_text(
        """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>surf-os-pointer-xvfb-live</title>
  <style>
    body { margin: 0; font-family: sans-serif; }
    #target {
      position: absolute;
      left: 40px;
      top: 40px;
      width: 900px;
      height: 700px;
      background: #d7f5e6;
      border: 4px solid #157347;
      display: block;
    }
    #proof { position: absolute; left: 300px; top: 300px; width: 40px; height: 40px; }
  </style>
</head>
<body>
  <label id="target" for="proof"></label>
  <input id="proof" type="checkbox">
  <script>
    document.addEventListener('click', () => {
      document.querySelector('#proof').checked = true;
    });
    window.__surfOsPointerProof = () => JSON.stringify({
      checked: document.querySelector('#proof').checked,
      devicePixelRatio: window.devicePixelRatio,
      title: document.title,
      href: location.href
    });
  </script>
</body>
</html>
""",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/surf-os-pointer-xvfb-live-example.json"))
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="surf-os-pointer-xvfb-"))
    display = f":{free_port() % 1000 + 100}"
    xvfb_proc: subprocess.Popen[str] | None = None
    chrome_proc: subprocess.Popen[str] | None = None
    server: http.server.ThreadingHTTPServer | None = None

    try:
        env = os.environ.copy()
        env["DISPLAY"] = display
        write_page(tmp)
        http_port = free_port()
        cdp_port = free_port()

        xvfb_proc = subprocess.Popen(
            ["Xvfb", display, "-screen", "0", "1280x900x24"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        time.sleep(0.5)

        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", http_port), handler)
        threading.Thread(target=lambda: server.serve_forever(poll_interval=0.1), daemon=True).start()

        chrome = find_chrome()
        chrome_proc = subprocess.Popen(
            [
                chrome,
                f"--remote-debugging-port={cdp_port}",
                "--remote-allow-origins=*",
                f"--user-data-dir={tmp / 'chrome-profile'}",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-gpu",
                "--window-size=1000,760",
                "--window-position=80,80",
                "about:blank",
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        wait_json(f"http://127.0.0.1:{cdp_port}/json/version")

        target_url = f"http://127.0.0.1:{http_port}/index.html"
        run_surf(["cdp.raw", "Page.navigate", "--params-json", json.dumps({"url": target_url}), "--json"], env=env, port=cdp_port)
        time.sleep(1.0)
        state = json.loads(evaluate("window.__surfOsPointerProof()", env=env, port=cdp_port))

        window_id = run(["xdotool", "search", "--onlyvisible", "--name", "surf-os-pointer-xvfb-live"], env=env).stdout.strip().splitlines()[-1]
        geometry = run(["xdotool", "getwindowgeometry", "--shell", window_id], env=env).stdout
        origin = {}
        for line in geometry.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                if key in {"X", "Y"}:
                    origin[key] = int(value)

        pointer_plan = {
            "schema_version": "surf.synthetic_os_pointer_plan.v1",
            "defensive_scope": "authorized_loopback_synthetic_only",
            "device_pixel_ratio": state["devicePixelRatio"],
            "target_url": target_url,
            "samples": [
                {"event": "mouseMoved", "time_ms": 0, "x_css": 320, "y_css": 320},
                {"event": "mousePressed", "time_ms": 20, "x_css": 320, "y_css": 320},
                {"event": "mouseReleased", "time_ms": 40, "x_css": 320, "y_css": 320},
            ],
        }
        pointer_plan_path = tmp / "pointer-plan.json"
        pointer_plan_path.write_text(json.dumps(pointer_plan, indent=2), encoding="utf-8")

        dispatch = run_surf(
            [
                "pointer.dispatch",
                "--transport",
                "os",
                "--backend",
                "xdotool",
                "--window-origin-x",
                str(origin["X"]),
                "--window-origin-y",
                str(origin["Y"]),
                "--plan",
                str(pointer_plan_path),
                "--json",
            ],
            env=env,
            port=cdp_port,
        )
        time.sleep(0.3)
        final_state = json.loads(evaluate("window.__surfOsPointerProof()", env=env, port=cdp_port))
        checks = {
            "cdp_9222_unavailable": tcp_open(9222) is False,
            "dispatch_schema": dispatch.get("schema_version") == "surf.pointer_dispatch_receipt.v1",
            "dispatch_os_transport": dispatch.get("transport_selected") == "os",
            "dispatch_backend_xdotool": dispatch.get("backend") == "xdotool",
            "dispatch_sample_count": dispatch.get("sample_count") == 3,
            "checkbox_checked": final_state.get("checked") is True,
            "readback": final_state.get("title") == "surf-os-pointer-xvfb-live",
        }
        receipt = {
            "schema_version": "surf.os_pointer_xvfb_live_example.v1",
            "success": all(checks.values()),
            "mocked": False,
            "live": True,
            "local_loopback": True,
            "public_captcha_provider": False,
            "solver_or_bypass": False,
            "xvfb_display": display,
            "cdp_port": cdp_port,
            "cdp_9222_open": tcp_open(9222),
            "target_url": target_url,
            "window_id": window_id,
            "checks": checks,
            "dispatch": {
                "schema_version": dispatch.get("schema_version"),
                "transport_selected": dispatch.get("transport_selected"),
                "backend": dispatch.get("backend"),
                "sample_count": dispatch.get("sample_count"),
                "coordinate_mapping": dispatch.get("coordinate_mapping"),
            },
            "readback": final_state,
            "proof_boundary": {
                "proves": "Surf can deliver an authorized pointer plan through OS input to a real Chrome window and read back the changed checkbox state.",
                "does_not_prove": "CAPTCHA solving, public-site bypass, provider behavior, authenticated extension behavior, or bot-detection evasion.",
            },
        }
        args.output.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        print(json.dumps(receipt, indent=2))
        return 0 if receipt["success"] else 1
    finally:
        if server is not None:
            server.shutdown()
        if chrome_proc is not None:
            chrome_proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                chrome_proc.wait(timeout=5)
            if chrome_proc.poll() is None:
                chrome_proc.kill()
        if xvfb_proc is not None:
            xvfb_proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                xvfb_proc.wait(timeout=5)
            if xvfb_proc.poll() is None:
                xvfb_proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
