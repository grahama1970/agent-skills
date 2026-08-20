#!/usr/bin/env python3
"""Live Surf CDP exercise against a real bot-detection example.

The example source is the pinned `rebrowser/rebrowser-bot-detector` repository,
served on loopback for the duration of the run. The script drives Surf's real
CDP commands against that page, dispatches pointer input, and reads back the
page's detection JSON. It does not solve CAPTCHA challenges or contact a public
CAPTCHA provider.
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
REBROWSER_REPO = "https://github.com/rebrowser/rebrowser-bot-detector.git"
REBROWSER_COMMIT = "e1a25b1ff264cc9a5b5ea7fe8a6dfc26e3b1c718"
UV_ENV = "/tmp/surf-live-cdp-pointer-example-venv"


def free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def find_chrome() -> str:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    raise RuntimeError("Chrome/Chromium executable not found")


def run(command: list[str], *, cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
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


def clone_rebrowser(dest: Path) -> str:
    run(["git", "clone", "--no-checkout", "--depth", "1", REBROWSER_REPO, str(dest)], timeout=120)
    run(["git", "fetch", "--depth", "1", "origin", REBROWSER_COMMIT], cwd=dest, timeout=120)
    run(["git", "checkout", "--detach", REBROWSER_COMMIT], cwd=dest, timeout=60)
    return run(["git", "rev-parse", "HEAD"], cwd=dest).stdout.strip()


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


def run_surf(args: list[str], *, port: int, output_path: Path | None = None) -> dict[str, Any]:
    env = os.environ.copy()
    env["CDP_PORT"] = str(port)
    env.setdefault("UV_PROJECT_ENVIRONMENT", UV_ENV)
    completed = run([str(RUN_SH), *args], cwd=SURF_ROOT, env=env, timeout=45)
    if output_path is not None:
        output_path.write_text(completed.stdout, encoding="utf-8")
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Surf command did not return JSON: {' '.join(args)}") from exc


def evaluate_json(expression: str, *, port: int, out: Path) -> Any:
    result = run_surf(
        [
            "cdp.raw",
            "Runtime.evaluate",
            "--params-json",
            json.dumps({"expression": expression, "returnByValue": True, "awaitPromise": True}),
            "--json",
        ],
        port=port,
        output_path=out,
    )
    return result["result"]["result"].get("value")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("/tmp/surf-rebrowser-cdp-pointer-live-example.json"))
    args = parser.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="surf-rebrowser-cdp-example-"))
    chrome_proc: subprocess.Popen[str] | None = None
    server: http.server.ThreadingHTTPServer | None = None

    try:
        source_dir = tmp / "rebrowser-bot-detector"
        source_commit = clone_rebrowser(source_dir)
        http_port = free_port()
        cdp_port = free_port()

        handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(source_dir))
        server = http.server.ThreadingHTTPServer(("127.0.0.1", http_port), handler)
        threading.Thread(target=lambda: server.serve_forever(poll_interval=0.1), daemon=True).start()

        chrome = find_chrome()
        profile = tmp / "chrome-profile"
        chrome_proc = subprocess.Popen(
            [
                chrome,
                f"--remote-debugging-port={cdp_port}",
                "--remote-allow-origins=*",
                f"--user-data-dir={profile}",
                "--headless=new",
                "--no-first-run",
                "--no-default-browser-check",
                "--disable-background-networking",
                "--disable-gpu",
                "--window-size=1200,900",
                "about:blank",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        wait_json(f"http://127.0.0.1:{cdp_port}/json/version")

        page_url = f"http://127.0.0.1:{http_port}/index.html"
        artifacts: dict[str, str] = {}

        for name, command in {
            "navigate": ["cdp.raw", "Page.navigate", "--params-json", json.dumps({"url": page_url}), "--json"],
            "raw-layout": ["cdp.raw", "Page.getLayoutMetrics", "--json"],
        }.items():
            path = tmp / f"{name}.json"
            run_surf(command, port=cdp_port, output_path=path)
            artifacts[name] = str(path)
            if name == "navigate":
                time.sleep(1.5)

        layout_path = tmp / "layout.json"
        hit_quads_path = tmp / "hit-quads.json"
        quads_path = tmp / "quads.json"
        hit_path = tmp / "hit-test.json"
        dispatch_path = tmp / "dispatch.json"
        readback_path = tmp / "readback.json"

        layout = run_surf(["cdp.layout", "--json"], port=cdp_port, output_path=layout_path)
        hit_quads = run_surf(["cdp.quads", "h1", "--json"], port=cdp_port, output_path=hit_quads_path)
        hit_center = hit_quads.get("primary_center") or {}
        hit_x = float(hit_center.get("x", 0))
        hit_y = float(hit_center.get("y", 0))
        hit = run_surf(["cdp.hit-test", str(hit_x), str(hit_y), "--json"], port=cdp_port, output_path=hit_path)

        evaluate_json(
            "document.querySelector('#detections-json').scrollIntoView({block: 'center'}); true",
            port=cdp_port,
            out=tmp / "scroll.json",
        )
        time.sleep(0.2)
        quads = run_surf(["cdp.quads", "#detections-json", "--json"], port=cdp_port, output_path=quads_path)
        center = quads.get("primary_center") or {}
        x = float(center.get("x", 0))
        y = float(center.get("y", 0))

        pointer_plan = {
            "schema_version": "surf.synthetic_pointer_plan.v1",
            "source_repo": REBROWSER_REPO,
            "source_commit": source_commit,
            "target_url": page_url,
            "samples": [
                {"event": "mouseMoved", "time_ms": 0, "x_css": x, "y_css": y},
                {"event": "mousePressed", "time_ms": 10, "x_css": x, "y_css": y},
                {"event": "mouseReleased", "time_ms": 25, "x_css": x, "y_css": y},
            ],
        }
        pointer_plan_path = tmp / "pointer-plan.json"
        pointer_plan_path.write_text(json.dumps(pointer_plan, indent=2), encoding="utf-8")
        artifacts["pointer-plan"] = str(pointer_plan_path)

        dispatch = run_surf(
            ["pointer.dispatch", "--plan", str(pointer_plan_path), "--json"],
            port=cdp_port,
            output_path=dispatch_path,
        )
        time.sleep(0.5)
        readback_value = evaluate_json(
            """JSON.stringify({
              url: location.href,
              title: document.title,
              activeElementId: document.activeElement && document.activeElement.id,
              detectionTextareaLength: (document.querySelector('#detections-json') || {}).value?.length || 0,
              detectionRows: document.querySelectorAll('#detections-table tbody tr').length,
              detectionJson: (document.querySelector('#detections-json') || {}).value || ''
            })""",
            port=cdp_port,
            out=readback_path,
        )
        readback = json.loads(readback_value)
        try:
            detections = json.loads(readback.get("detectionJson") or "[]")
        except json.JSONDecodeError:
            detections = []

        for path_name, path in {
            "layout": layout_path,
            "hit-quads": hit_quads_path,
            "quads": quads_path,
            "hit-test": hit_path,
            "dispatch": dispatch_path,
            "readback": readback_path,
        }.items():
            artifacts[path_name] = str(path)

        checks = {
            "source_commit_pinned": source_commit == REBROWSER_COMMIT,
            "layout_schema": layout.get("schema_version") == "surf.layout_metrics.v1",
            "hit_quads_schema": hit_quads.get("schema_version") == "surf.content_quads.v1",
            "quads_schema": quads.get("schema_version") == "surf.content_quads.v1",
            "hit_schema": hit.get("schema_version") == "surf.hit_test.v1",
            "dispatch_schema": dispatch.get("schema_version") == "surf.pointer_dispatch_receipt.v1",
            "dispatch_boundary": dispatch.get("proof_boundary", {}).get("post_observation_required") is True,
            "target_center": x > 0 and y > 0,
            "bot_detector_loaded": readback.get("title") == "rebrowser-bot-detector",
            "pointer_focused_real_element": readback.get("activeElementId") == "detections-json",
            "detector_json_present": readback.get("detectionTextareaLength", 0) > 10,
            "detector_rows_present": readback.get("detectionRows", 0) >= 1,
        }
        errors = [name for name, ok in checks.items() if not ok]
        receipt = {
            "schema_version": "surf.cdp_pointer_live_example.v1",
            "success": not errors,
            "mocked": False,
            "live": True,
            "real_example": True,
            "local_loopback": True,
            "public_captcha_provider": False,
            "source_repo": REBROWSER_REPO,
            "source_commit": source_commit,
            "target_url": page_url,
            "checks": checks,
            "errors": errors,
            "schemas_seen": {
                "layout": layout.get("schema_version"),
                "quads": quads.get("schema_version"),
                "hit": hit.get("schema_version"),
                "dispatch": dispatch.get("schema_version"),
            },
            "pointer": {
                "x_css": x,
                "y_css": y,
                "sample_count": dispatch.get("sample_count"),
                "active_element_after_dispatch": readback.get("activeElementId"),
            },
            "bot_detector": {
                "rows": readback.get("detectionRows"),
                "json_length": readback.get("detectionTextareaLength"),
                "detection_types": [item.get("type") for item in detections if isinstance(item, dict)],
            },
            "proof_boundary": {
                "proves": "Surf CDP geometry and pointer.dispatch commands can drive and read back a pinned real bot-detection page served on loopback.",
                "does_not_prove": "CAPTCHA solving, public bot-detection bypass, provider behavior, or authenticated browser workflow readiness.",
            },
            "artifacts": artifacts,
        }
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0 if not errors else 1
    finally:
        if chrome_proc is not None:
            chrome_proc.terminate()
            try:
                chrome_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                chrome_proc.kill()
        if server is not None:
            server.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
