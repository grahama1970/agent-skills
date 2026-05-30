#!/usr/bin/env python3
"""HTTP client for cursor-browser-bridge extension.

Posts MCP-style tool calls to the local bridge server:
  POST http://127.0.0.1:{port}/tool  {"name": "browser_snapshot", "args": {...}}

Port discovery:
  1. CURSOR_BROWSER_BRIDGE_PORT env
  2. /tmp/cursor-browser-bridge-port file
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_PORT_FILE = Path("/tmp/cursor-browser-bridge-port")


class CursorBrowserBridgeError(RuntimeError):
    """Bridge unavailable or tool call failed."""


@dataclass(frozen=True)
class BridgeToolResult:
    content: list[dict[str, Any]]
    is_error: bool
    raw: dict[str, Any]

    @property
    def text(self) -> str:
        parts: list[str] = []
        for item in self.content:
            if item.get("type") == "text" and item.get("text"):
                parts.append(str(item["text"]))
        return "\n".join(parts).strip()


def bridge_port(*, port_file: Path | None = None) -> int:
    env = os.environ.get("CURSOR_BROWSER_BRIDGE_PORT", "").strip()
    if env:
        return int(env)
    path = port_file or DEFAULT_PORT_FILE
    try:
        return int(path.read_text().strip())
    except Exception as exc:
        raise CursorBrowserBridgeError(
            "Cursor Browser Bridge is not running. Install cursor-browser-bridge, reload Cursor, "
            f"then verify: curl http://127.0.0.1:$(cat {path})/health"
        ) from exc


def bridge_health(*, port: int | None = None, timeout: float = 5.0) -> dict[str, Any]:
    p = port or bridge_port()
    req = urllib.request.Request(f"http://127.0.0.1:{p}/health", method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def call_tool(
    name: str,
    args: dict[str, Any] | None = None,
    *,
    port: int | None = None,
    timeout: float = 120.0,
) -> BridgeToolResult:
    p = port or bridge_port()
    body = json.dumps({"name": name, "args": args or {}}).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{p}/tool",
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = json.loads(resp.read().decode())
    except urllib.error.URLError as exc:
        raise CursorBrowserBridgeError(
            f"Cursor Browser Bridge request failed on port {p}: {exc}"
        ) from exc
    content = raw.get("content") or []
    if not isinstance(content, list):
        content = [{"type": "text", "text": json.dumps(raw)}]
    return BridgeToolResult(content=content, is_error=bool(raw.get("isError")), raw=raw)


def wait_for_bridge(*, timeout: float = 15.0, poll: float = 0.5) -> int:
    deadline = time.monotonic() + timeout
    last_err: Exception | None = None
    while time.monotonic() < deadline:
        try:
            p = bridge_port()
            health = bridge_health(port=p, timeout=2.0)
            if health.get("ok"):
                return p
        except Exception as exc:
            last_err = exc
        time.sleep(poll)
    raise CursorBrowserBridgeError(
        f"Cursor Browser Bridge did not become ready within {timeout:.0f}s: {last_err}"
    )


def list_tabs(*, port: int | None = None) -> list[dict[str, str]]:
    """Return open Cursor browser tabs as {viewId, title, url} dicts."""
    result = call_tool("browser_tabs", {}, port=port)
    text = result.text
    tabs: list[dict[str, str]] = []
    # Bridge returns markdown-ish lines; also accept JSON array payloads.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    tabs.append(
                        {
                            "viewId": str(item.get("viewId") or item.get("id") or ""),
                            "title": str(item.get("title") or ""),
                            "url": str(item.get("url") or ""),
                        }
                    )
            return [t for t in tabs if t.get("viewId")]
    except json.JSONDecodeError:
        pass
    for line in text.splitlines():
        # viewId: f53e74 | title | url
        m = re.match(r"^\s*(?:-\s*)?(?:viewId:\s*)?([a-f0-9]{4,12})\s*(?:\|\s*)?(.*?)(?:\|\s*(https?://\S+))?\s*$", line, re.I)
        if m:
            tabs.append({"viewId": m.group(1), "title": (m.group(2) or "").strip(), "url": (m.group(3) or "").strip()})
            continue
        m2 = re.search(r"viewId[=:\s]+([a-f0-9]{4,12})", line, re.I)
        url_m = re.search(r"(https?://\S+)", line)
        if m2:
            tabs.append({"viewId": m2.group(1), "title": line.strip(), "url": url_m.group(1) if url_m else ""})
    return [t for t in tabs if t.get("viewId")]


def extract_snapshot_refs(snapshot_text: str) -> dict[str, str]:
    """Find ChatGPT compose box and send button refs from snapshot YAML/text."""
    refs: dict[str, str] = {}
    for line in snapshot_text.splitlines():
        m = re.search(
            r'(?:textbox|textarea)\s+"([^"]*(?:Chat with ChatGPT|Ask anything|Message ChatGPT)[^"]*)"\s+\[(e\d+)\]',
            line,
            re.I,
        )
        if m and "textbox" not in refs:
            refs["textbox"] = m.group(2)
            continue
        m = re.search(
            r'button\s+"([^"]*(?:Send prompt|Send message|Send)[^"]*)"\s+\[(e\d+)\]',
            line,
            re.I,
        )
        if m and "send" not in refs:
            refs["send"] = m.group(2)
    if "textbox" not in refs:
        for line in snapshot_text.splitlines():
            m = re.search(r'textbox\s+"([^"]+)"\s+\[(e\d+)\]', line, re.I)
            if m and "chat" in m.group(1).lower():
                refs["textbox"] = m.group(2)
                break
    return refs


def make_sentinel(prefix: str = "CURSOR_BROWSER_DONE") -> str:
    import secrets

    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    token = secrets.token_hex(4)
    return f"<<<{prefix}:{stamp}:{token}>>>"


def strip_sentinel(text: str, sentinel: str) -> str:
    idx = text.rfind(sentinel)
    if idx == -1:
        return text.strip()
    return text[:idx].strip()


def extract_chatgpt_response(page_text: str, sentinel: str) -> str | None:
    if sentinel not in page_text:
        return None
    before = page_text[: page_text.rfind(sentinel)]
    marker = "ChatGPT said:"
    alt = "Assistant"
    idx = before.rfind(marker)
    if idx == -1:
        idx = before.rfind(alt)
        if idx == -1:
            return strip_sentinel(before, sentinel)
        return before[idx + len(alt) :].strip()
    return before[idx + len(marker) :].strip()


def resolve_view_id_by_url(url: str) -> str:
    tabs = list_tabs()
    matches = [t for t in tabs if t.get("url") == url or t.get("url", "").rstrip("/") == url.rstrip("/")]
    if len(matches) == 1:
        return matches[0]["viewId"]
    if not matches:
        raise CursorBrowserBridgeError(f"No Cursor browser tab matched url: {url}")
    listing = "\n".join(f"  {t['viewId']}\t{t.get('title','')}\t{t.get('url','')}" for t in matches)
    raise CursorBrowserBridgeError(
        "Multiple Cursor browser tabs matched url; pass --view-id explicitly.\n" + listing
    )


def resolve_chatgpt_view_id(explicit_view_id: str = "", explicit_url: str = "") -> tuple[str, list[dict], str]:
    if explicit_view_id:
        return explicit_view_id.strip(), [], "explicit"
    if explicit_url:
        return resolve_view_id_by_url(explicit_url), [], "explicit_url"
    tabs = [t for t in list_tabs() if "chatgpt.com" in t.get("url", "")]
    if len(tabs) == 1:
        return tabs[0]["viewId"], tabs, "auto"
    if not tabs:
        raise CursorBrowserBridgeError(
            "No open chatgpt.com tab in Cursor Browser.\n"
            "Open ChatGPT in Cursor Browser (Simple Browser), then retry or pass --view-id."
        )
    listing = "\n".join(
        f"  {t['viewId']}\t{t.get('title','')}\t{t.get('url','')}" for t in tabs
    )
    raise CursorBrowserBridgeError(
        "Multiple chatgpt.com tabs in Cursor Browser; refusing to guess.\n"
        "Pass --view-id from browser_tabs list.\nCandidates:\n" + listing
    )


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Cursor browser bridge helpers")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("tab.list", help="List Cursor browser tabs")
    p_list.add_argument("--json", action="store_true")

    p_resolve = sub.add_parser("resolve-url", help="Resolve viewId by URL")
    p_resolve.add_argument("--url", required=True)

    args = parser.parse_args()
    if args.cmd == "tab.list":
        tabs = list_tabs()
        if args.json:
            import json

            print(json.dumps(tabs, indent=2))
        else:
            for t in tabs:
                print(f"{t.get('viewId','')}\t{t.get('title','')}\t{t.get('url','')}")
        return 0
    if args.cmd == "resolve-url":
        print(resolve_view_id_by_url(args.url))
        return 0
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CursorBrowserBridgeError as exc:
        import sys
        print(str(exc), file=sys.stderr)
        raise SystemExit(2)
