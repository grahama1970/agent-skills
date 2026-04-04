"""Thin CDP WebSocket client for direct browser control.

Single persistent connection, no subprocess overhead.
"""

import base64
import json
import os
import subprocess
import time
from pathlib import Path

try:
    import websocket as _ws
except ImportError:
    subprocess.check_call(["uv", "pip", "install", "websocket-client", "-q"])
    import websocket as _ws

CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))


class CDPClient:
    """CDP WebSocket client — one connection for the entire test run."""

    def __init__(self, port: int = None):
        self.port = port or CDP_PORT
        self.ws = None
        self.msg_id = 0

    def connect(self):
        tabs = json.loads(
            subprocess.check_output(
                ["curl", "-s", f"http://127.0.0.1:{self.port}/json/list"],
                timeout=5,
            )
        )
        pages = [t for t in tabs if t.get("type") == "page"]
        if not pages:
            raise ConnectionError(f"No browser page found on CDP port {self.port}")
        ws_url = pages[0]["webSocketDebuggerUrl"]
        self.ws = _ws.create_connection(ws_url, timeout=30)

    def reconnect(self):
        self.close()
        time.sleep(0.5)
        self.connect()

    def send(self, method: str, params: dict = None) -> dict:
        if not self.ws:
            self.connect()
        self.msg_id += 1
        msg = {"id": self.msg_id, "method": method}
        if params:
            msg["params"] = params
        self.ws.send(json.dumps(msg))
        while True:
            resp = json.loads(self.ws.recv())
            if resp.get("id") == self.msg_id:
                if "error" in resp:
                    raise RuntimeError(f"CDP error: {resp['error']}")
                return resp.get("result", {})

    def evaluate(self, js: str):
        result = self.send("Runtime.evaluate", {
            "expression": js,
            "returnByValue": True,
            "awaitPromise": True,
        })
        if "exceptionDetails" in result:
            raise RuntimeError(f"JS error: {result['exceptionDetails'].get('text', result['exceptionDetails'])}")
        return result.get("result", {}).get("value")

    def navigate(self, url: str, wait_ms: int = 1000):
        self.send("Page.enable")
        self.send("Page.navigate", {"url": url})
        time.sleep(wait_ms / 1000.0)
        self.reconnect()

    def screenshot(self, output_path: str) -> str:
        result = self.send("Page.captureScreenshot", {"format": "png"})
        img_data = base64.b64decode(result["data"])
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(img_data)
        return output_path

    def wait_for_selector(self, selector: str, timeout_ms: int = 5000) -> bool:
        deadline = time.time() + timeout_ms / 1000.0
        while time.time() < deadline:
            found = self.evaluate(
                f"document.querySelector({json.dumps(selector)}) !== null"
            )
            if found:
                return True
            time.sleep(0.2)
        return False

    def selector_exists(self, selector: str) -> bool:
        return bool(self.evaluate(
            f"document.querySelector({json.dumps(selector)}) !== null"
        ))

    def selector_count(self, selector: str) -> int:
        return int(self.evaluate(
            f"document.querySelectorAll({json.dumps(selector)}).length"
        ) or 0)

    def get_text_content(self, selector: str) -> str:
        return self.evaluate(
            f"(function() {{"
            f"  var el = document.querySelector({json.dumps(selector)});"
            f"  return el ? el.textContent : '';"
            f"}})()"
        ) or ""

    def get_inner_text(self) -> str:
        return self.evaluate("document.body.innerText") or ""

    def click_selector(self, selector: str) -> dict:
        result = self.evaluate(
            f"(function() {{"
            f"  var el = document.querySelector({json.dumps(selector)});"
            f"  if (!el) return {{ok: false, found: false, error: 'selector not found: ' + {json.dumps(selector)}}};"
            f"  el.scrollIntoView({{block: 'center'}});"
            f"  el.click();"
            f"  return {{ok: true, found: true, tag: el.tagName, text: (el.textContent || '').slice(0, 80)}};"
            f"}})()"
        )
        return result or {"ok": False, "found": False, "error": "evaluate returned null"}

    def type_into(self, selector: str, value: str) -> dict:
        result = self.evaluate(
            f"(function() {{"
            f"  var el = document.querySelector({json.dumps(selector)});"
            f"  if (!el) return {{ok: false, error: 'selector not found'}};"
            f"  el.focus();"
            f"  var nativeSetter = Object.getOwnPropertyDescriptor("
            f"    window.HTMLInputElement.prototype, 'value').set;"
            f"  nativeSetter.call(el, {json.dumps(value)});"
            f"  el.dispatchEvent(new Event('input', {{bubbles: true}}));"
            f"  el.dispatchEvent(new Event('change', {{bubbles: true}}));"
            f"  return {{ok: true, value: el.value}};"
            f"}})()"
        )
        return result or {"ok": False, "error": "evaluate returned null"}

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
