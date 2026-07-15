#!/usr/bin/env python3
"""Best-effort KDE Plasma desktop-space inventory for Surf."""

from __future__ import annotations

import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from urllib.error import URLError
from urllib.request import Request, urlopen
from typing import Any


HELPER_DEFAULT_HOST = "127.0.0.1"
HELPER_DEFAULT_PORT = 8765
HELPER_ENV_URL = "SURF_KDE_HELPER_URL"
HELPER_URL_FILE = "/tmp/surf-kde-helper-url"


@dataclass
class KdeWindow:
    x11_window_id: str
    desktop_index: int | None
    wm_class: str
    title: str


def _run(cmd: list[str], timeout: float = 2.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except Exception as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _qdbus(*args: str) -> str | None:
    for binary in ("qdbus", "qdbus6"):
        code, stdout, _stderr = _run([binary, *args])
        if code == 0 and stdout:
            return stdout.splitlines()[0].strip()
    return None


def _parse_wmctrl_lx(text: str) -> list[KdeWindow]:
    windows: list[KdeWindow] = []
    for line in text.splitlines():
        parts = line.split(None, 4)
        if len(parts) < 5:
            continue
        window_id, desktop_raw, _host, wm_class, title = parts
        try:
            desktop_index = int(desktop_raw)
        except ValueError:
            desktop_index = None
        windows.append(KdeWindow(window_id, desktop_index, wm_class, title))
    return windows


def _helper_url() -> str:
    configured = os.environ.get(HELPER_ENV_URL, "").strip()
    if configured:
        return configured.rstrip("/")
    try:
        saved = open(HELPER_URL_FILE, encoding="utf-8").read().strip()
    except OSError:
        saved = ""
    if saved:
        return saved.rstrip("/")
    port = os.environ.get("SURF_KDE_HELPER_PORT", str(HELPER_DEFAULT_PORT)).strip() or str(HELPER_DEFAULT_PORT)
    return f"http://{HELPER_DEFAULT_HOST}:{port}"


def _request_helper(path: str, *, payload: Any | None = None, timeout: float = 1.5) -> dict[str, Any] | None:
    url = f"{_helper_url()}/{path.lstrip('/')}"
    data = None
    headers: dict[str, str] = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method="POST" if payload is not None else "GET")
    try:
        with urlopen(request, timeout=timeout) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, TimeoutError, json.JSONDecodeError):
        return None
    if isinstance(decoded, dict):
        return decoded
    return None


def kde_inventory(*, use_helper: bool = True) -> dict[str, Any]:
    if use_helper:
        helper_inventory = _request_helper("/spaces")
        if helper_inventory is not None:
            helper_inventory["source"] = helper_inventory.get("source") or "helper"
            helper_inventory["helper_available"] = True
            return helper_inventory

    issues: list[str] = []
    current_index_raw = _qdbus("org.kde.KWin", "/KWin", "currentDesktop")
    current_id = _qdbus("org.kde.KWin", "/VirtualDesktopManager", "current")
    count_raw = _qdbus("org.kde.KWin", "/VirtualDesktopManager", "count")
    activity_id = _qdbus("org.kde.ActivityManager", "/ActivityManager/Activities", "CurrentActivity")

    def parse_int(value: str | None) -> int | None:
        if not value:
            return None
        try:
            return int(value)
        except ValueError:
            return None

    current_index = parse_int(current_index_raw)
    desktop_count = parse_int(count_raw)
    kde_available = any(value is not None for value in (current_index, current_id, desktop_count, activity_id))
    if not kde_available:
        issues.append("kde_dbus_unavailable")

    code, wm_stdout, _wm_stderr = _run(["wmctrl", "-lx"])
    windows = _parse_wmctrl_lx(wm_stdout) if code == 0 and wm_stdout else []
    windows_available = bool(windows)
    if code == 127:
        issues.append("wmctrl_unavailable")
    elif code != 0:
        issues.append("wmctrl_failed")
    elif not windows:
        issues.append("wmctrl_returned_no_windows")

    return {
        "schema": "surf.kde_spaces.v1",
        "source": "local",
        "helper_available": False,
        "kde_available": kde_available,
        "windows_available": windows_available,
        "session": {
            "xdg_session_type": os.environ.get("XDG_SESSION_TYPE", ""),
            "kde_full_session": os.environ.get("KDE_FULL_SESSION", ""),
            "display": os.environ.get("DISPLAY", ""),
            "wayland_display": os.environ.get("WAYLAND_DISPLAY", ""),
        },
        "current_desktop_index": current_index,
        "current_desktop_id": current_id,
        "desktop_count": desktop_count,
        "current_activity_id": activity_id,
        "windows": [asdict(window) for window in windows],
        "issues": issues,
    }


def _normalize_title(value: str) -> str:
    value = re.sub(r"\s+-\s+(Google Chrome|Chromium)\s*$", "", value or "", flags=re.I)
    return re.sub(r"\s+", " ", value).strip().lower()


def _match_chrome_window(active_title: str, kde_windows: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized_active = _normalize_title(active_title)
    if not normalized_active:
        return None
    candidates: list[tuple[int, dict[str, Any]]] = []
    for window in kde_windows:
        title = _normalize_title(str(window.get("title", "")))
        wm_class = str(window.get("wm_class", "")).lower()
        score = 0
        if "chrome" in wm_class or "chromium" in wm_class:
            score += 2
        if normalized_active == title:
            score += 4
        elif normalized_active in title:
            score += 3
        elif title and title in normalized_active:
            score += 2
        if score:
            candidates.append((score, window))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def annotate_tabs(payload: Any, *, use_helper: bool = True) -> dict[str, Any]:
    if use_helper:
        helper_annotated = _request_helper("/annotate-tabs", payload=payload)
        if helper_annotated is not None:
            kde = helper_annotated.get("kde")
            if isinstance(kde, dict):
                kde["source"] = kde.get("source") or "helper"
                kde["helper_available"] = True
            helper_annotated["source"] = helper_annotated.get("source") or "helper"
            return helper_annotated

    if isinstance(payload, list):
        tabs = payload
    elif isinstance(payload, dict):
        tabs = payload.get("tabs", [])
    else:
        tabs = []

    inventory = kde_inventory(use_helper=False)
    kde_windows = inventory.get("windows", [])
    active_by_window: dict[str, str] = {}
    for tab in tabs:
        if isinstance(tab, dict) and tab.get("active") and tab.get("windowId") is not None:
            active_by_window[str(tab["windowId"])] = str(tab.get("title", ""))

    kde_by_chrome_window: dict[str, dict[str, Any]] = {}
    for window_id, active_title in active_by_window.items():
        match = _match_chrome_window(active_title, kde_windows)
        if match:
            kde_by_chrome_window[window_id] = match

    enriched_tabs: list[dict[str, Any]] = []
    for tab in tabs:
        if not isinstance(tab, dict):
            continue
        enriched = dict(tab)
        window_id = str(enriched.get("windowId", ""))
        match = kde_by_chrome_window.get(window_id)
        enriched["kde"] = {
            "desktop_index": match.get("desktop_index") if match else None,
            "x11_window_id": match.get("x11_window_id") if match else "",
            "window_match_confidence": "title" if match else "none",
        }
        enriched_tabs.append(enriched)

    return {"schema": "surf.tab_list_with_kde.v1", "source": inventory.get("source", "local"), "tabs": enriched_tabs, "kde": inventory}


class _KdeHelperHandler(BaseHTTPRequestHandler):
    server_version = "SurfKdeHelper/1"

    def log_message(self, format: str, *args: Any) -> None:
        if os.environ.get("SURF_KDE_HELPER_LOG"):
            super().log_message(format, *args)

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        encoded = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _read_json(self) -> Any:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:
        if self.path in ("/health", "/"):
            self._send_json({"schema": "surf.kde_helper.v1", "ok": True})
            return
        if self.path == "/spaces":
            payload = kde_inventory(use_helper=False)
            payload["source"] = "helper"
            payload["helper_available"] = True
            self._send_json(payload)
            return
        if self.path == "/windows":
            inventory = kde_inventory(use_helper=False)
            self._send_json(
                {
                    "schema": "surf.kde_windows.v1",
                    "source": "helper",
                    "windows": inventory.get("windows", []),
                    "kde": inventory,
                }
            )
            return
        self._send_json({"schema": "surf.kde_helper_error.v1", "error": "not_found", "path": self.path}, status=404)

    def do_POST(self) -> None:
        if self.path == "/annotate-tabs":
            try:
                payload = annotate_tabs(self._read_json(), use_helper=False)
            except Exception as exc:
                self._send_json({"schema": "surf.kde_helper_error.v1", "error": str(exc)}, status=400)
                return
            payload["source"] = "helper"
            kde = payload.get("kde")
            if isinstance(kde, dict):
                kde["source"] = "helper"
                kde["helper_available"] = True
            self._send_json(payload)
            return
        self._send_json({"schema": "surf.kde_helper_error.v1", "error": "not_found", "path": self.path}, status=404)


def serve_helper(host: str, port: int) -> None:
    server = ThreadingHTTPServer((host, port), _KdeHelperHandler)
    url_host = "127.0.0.1" if host in ("", "0.0.0.0") else host
    with open(HELPER_URL_FILE, "w", encoding="utf-8") as handle:
        handle.write(f"http://{url_host}:{port}\n")
    print(json.dumps({"schema": "surf.kde_helper_started.v1", "host": host, "port": port}), flush=True)
    server.serve_forever()


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    inventory_parser = sub.add_parser("inventory")
    inventory_parser.add_argument("--no-helper", action="store_true")
    annotate_parser = sub.add_parser("annotate-tabs")
    annotate_parser.add_argument("--no-helper", action="store_true")
    health_parser = sub.add_parser("health")
    health_parser.add_argument("--url", default="")
    serve_parser = sub.add_parser("serve")
    serve_parser.add_argument("--host", default=HELPER_DEFAULT_HOST)
    serve_parser.add_argument("--port", type=int, default=HELPER_DEFAULT_PORT)
    args = parser.parse_args()
    if args.command == "inventory":
        print(json.dumps(kde_inventory(use_helper=not args.no_helper), indent=2))
        return 0
    if args.command == "annotate-tabs":
        print(json.dumps(annotate_tabs(json.load(sys.stdin), use_helper=not args.no_helper), indent=2))
        return 0
    if args.command == "health":
        if args.url:
            os.environ[HELPER_ENV_URL] = args.url
        payload = _request_helper("/health")
        if payload is None:
            print(json.dumps({"schema": "surf.kde_helper_health.v1", "ok": False}, indent=2))
            return 1
        print(json.dumps(payload, indent=2))
        return 0
    if args.command == "serve":
        serve_helper(args.host, args.port)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
