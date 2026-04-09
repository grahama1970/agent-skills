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
            f"  var proto = el.tagName === 'TEXTAREA'"
            f"    ? window.HTMLTextAreaElement.prototype"
            f"    : window.HTMLInputElement.prototype;"
            f"  var nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value').set;"
            f"  nativeSetter.call(el, {json.dumps(value)});"
            f"  el.dispatchEvent(new Event('input', {{bubbles: true}}));"
            f"  el.dispatchEvent(new Event('change', {{bubbles: true}}));"
            f"  return {{ok: true, value: el.value}};"
            f"}})()"
        )
        return result or {"ok": False, "error": "evaluate returned null"}

    # --- Keyboard actions ---

    def press_key(self, key: str):
        """Press a keyboard key (Tab, Enter, Escape, ArrowDown, ArrowUp, ArrowLeft, ArrowRight, Space)."""
        key_map = {
            "Tab": {"key": "Tab", "code": "Tab", "keyCode": 9},
            "Enter": {"key": "Enter", "code": "Enter", "keyCode": 13},
            "Escape": {"key": "Escape", "code": "Escape", "keyCode": 27},
            "Space": {"key": " ", "code": "Space", "keyCode": 32},
            "ArrowDown": {"key": "ArrowDown", "code": "ArrowDown", "keyCode": 40},
            "ArrowUp": {"key": "ArrowUp", "code": "ArrowUp", "keyCode": 38},
            "ArrowLeft": {"key": "ArrowLeft", "code": "ArrowLeft", "keyCode": 37},
            "ArrowRight": {"key": "ArrowRight", "code": "ArrowRight", "keyCode": 39},
        }
        info = key_map.get(key, {"key": key, "code": key, "keyCode": 0})
        params = {
            "type": "keyDown",
            "key": info["key"],
            "code": info["code"],
            "windowsVirtualKeyCode": info["keyCode"],
            "nativeVirtualKeyCode": info["keyCode"],
        }
        self.send("Input.dispatchKeyEvent", params)
        params["type"] = "keyUp"
        self.send("Input.dispatchKeyEvent", params)

    def get_focused_qid(self) -> str | None:
        """Return the data-qid of the currently focused element, or None."""
        return self.evaluate(
            "(function() {"
            "  var el = document.activeElement;"
            "  return el ? el.getAttribute('data-qid') : null;"
            "})()"
        )

    # --- COTS measurement helpers (deterministic, no LLM) ---

    def get_bounding_rect(self, selector: str) -> dict | None:
        """Get bounding rect {width, height, x, y} for a selector."""
        return self.evaluate(
            f"(function() {{"
            f"  var el = document.querySelector({json.dumps(selector)});"
            f"  if (!el) return null;"
            f"  var r = el.getBoundingClientRect();"
            f"  return {{width: r.width, height: r.height, x: r.x, y: r.y}};"
            f"}})()"
        )

    def get_computed_font_size(self, selector: str) -> float | None:
        """Get computed font-size in px for a selector."""
        return self.evaluate(
            f"(function() {{"
            f"  var el = document.querySelector({json.dumps(selector)});"
            f"  if (!el) return null;"
            f"  return parseFloat(getComputedStyle(el).fontSize);"
            f"}})()"
        )

    def get_contrast_ratio(self, selector: str) -> float | None:
        """Get WCAG contrast ratio of text color vs background for a selector.

        Uses the WCAG 2.1 relative luminance formula. Returns ratio or None.
        """
        js = (
            "(function() {"
            f"  var el = document.querySelector({json.dumps(selector)});"
            "  if (!el) return null;"
            "  var s = getComputedStyle(el);"
            "  function parse(c) {"
            "    var m = c.match(/\\d+/g);"
            "    return m ? m.slice(0,3).map(Number) : null;"
            "  }"
            "  function lum(rgb) {"
            "    var a = rgb.map(function(v) {"
            "      v = v / 255;"
            "      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);"
            "    });"
            "    return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2];"
            "  }"
            "  var fg = parse(s.color);"
            "  var bg = parse(s.backgroundColor);"
            "  if (!fg || !bg) return null;"
            "  var l1 = lum(fg), l2 = lum(bg);"
            "  var ratio = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);"
            "  return Math.round(ratio * 100) / 100;"
            "})()"
        )
        return self.evaluate(js)

    def get_all_qid_elements(self) -> list[dict]:
        """Get all elements with data-qid: [{qid, tag, hasTitle, hasQsAction, width, height}]."""
        js = (
            "(function() {"
            "  var results = [];"
            "  document.querySelectorAll('[data-qid]').forEach(function(el) {"
            "    var r = el.getBoundingClientRect();"
            "    results.push({"
            "      qid: el.getAttribute('data-qid'),"
            "      tag: el.tagName.toLowerCase(),"
            "      hasTitle: el.hasAttribute('title'),"
            "      hasQsAction: el.hasAttribute('data-qs-action'),"
            "      width: r.width,"
            "      height: r.height,"
            "      interactive: !!(el.onclick || el.getAttribute('onclick') ||"
            "        ['BUTTON','A','INPUT','SELECT','TEXTAREA'].indexOf(el.tagName) >= 0 ||"
            "        el.getAttribute('role') === 'button' || el.getAttribute('role') === 'tab' ||"
            "        el.getAttribute('role') === 'link' || el.getAttribute('tabindex'))"
            "    });"
            "  });"
            "  return results;"
            "})()"
        )
        return self.evaluate(js) or []

    def close(self):
        if self.ws:
            try:
                self.ws.close()
            except (OSError, ConnectionError):
                pass
            self.ws = None
