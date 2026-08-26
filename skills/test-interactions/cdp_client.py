"""Thin CDP WebSocket client for direct browser control.

Single persistent connection, no subprocess overhead.
"""

import base64
import atexit
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

try:
    import websocket as _ws
except ImportError:
    subprocess.check_call(["uv", "pip", "install", "websocket-client", "-q"])
    import websocket as _ws

DEFAULT_CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))


class CDPClient:
    """CDP WebSocket client — one connection for the entire test run."""

    def __init__(self, port: int = None):
        self.attach_existing = os.environ.get("TEST_INTERACTIONS_ATTACH_EXISTING") == "1"
        self.port = port or (DEFAULT_CDP_PORT if self.attach_existing or "CDP_PORT" in os.environ else self._free_port())
        self.ws = None
        self.msg_id = 0
        self.target_id = None
        self.browser_process = None
        self.user_data_dir = None
        self.owns_browser = False
        self.events: list[dict] = []

    def _free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _browser_binary(self) -> str | None:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
            path = shutil.which(name)
            if path:
                return path
        return None

    def _json_get(self, path: str) -> dict | list:
        raw = subprocess.check_output(
            ["curl", "-s", f"http://127.0.0.1:{self.port}{path}"],
            timeout=5,
        )
        return json.loads(raw)

    def _endpoint_ready(self) -> bool:
        try:
            self._json_get("/json/version")
            return True
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
            return False

    def _ensure_browser(self):
        if self.attach_existing:
            return
        if self._endpoint_ready():
            return

        binary = self._browser_binary()
        if not binary:
            raise ConnectionError(
                "No Chrome/Chromium binary found. Install Chrome/Chromium or set "
                "TEST_INTERACTIONS_ATTACH_EXISTING=1 to attach to an existing CDP browser."
            )

        self.user_data_dir = tempfile.mkdtemp(prefix="test-interactions-cdp-")
        args = [
            binary,
            f"--remote-debugging-port={self.port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={self.user_data_dir}",
            "--headless=new",
            "--disable-gpu",
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-dev-shm-usage",
            "--no-first-run",
            "--no-default-browser-check",
            "--window-size=1600,1000",
            "about:blank",
        ]
        self.browser_process = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.owns_browser = True
        atexit.register(self._cleanup_browser)

        deadline = time.time() + 10
        while time.time() < deadline:
            if self._endpoint_ready():
                return
            time.sleep(0.2)
        raise ConnectionError(f"Dedicated Chrome CDP endpoint did not start on port {self.port}")

    def _new_page(self) -> dict | None:
        try:
            raw = subprocess.check_output(
                ["curl", "-s", "-X", "PUT", f"http://127.0.0.1:{self.port}/json/new?{quote('about:blank', safe='')}"],
                timeout=5,
            )
            page = json.loads(raw)
            if page.get("type") == "page" and page.get("webSocketDebuggerUrl"):
                return page
        except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
            return None
        return None

    def connect(self):
        self._ensure_browser()
        tabs = self._json_get("/json/list")
        pages = [t for t in tabs if t.get("type") == "page"]
        page = None
        if self.target_id:
            page = next((p for p in pages if p.get("id") == self.target_id), None)
        if page is None:
            page = self._new_page()
        if page is None:
            if not pages:
                raise ConnectionError(f"No browser page found on CDP port {self.port}")
            page = pages[0]
            self.target_id = page.get("id")
        else:
            self.target_id = page.get("id")
        self.ws = _ws.create_connection(page["webSocketDebuggerUrl"], timeout=30)

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
            if resp.get("method"):
                self.events.append(resp)

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

    def current_url(self) -> str:
        return self.evaluate("window.location.href") or ""

    def enable_observers(self):
        """Enable console/network event streams for discovery diagnostics."""
        for method in ("Runtime.enable", "Log.enable", "Network.enable"):
            try:
                self.send(method)
            except RuntimeError:
                pass

    def drain_events(self) -> list[dict]:
        """Flush pending protocol events by issuing a cheap Runtime call."""
        try:
            self.evaluate("void 0")
        except RuntimeError:
            pass
        events = list(self.events)
        self.events.clear()
        return events

    def viewport(self) -> dict:
        return self.evaluate(
            "(function(){ return {width: window.innerWidth, height: window.innerHeight, "
            "deviceScaleFactor: window.devicePixelRatio || 1}; })()"
        ) or {"width": 1200, "height": 900, "deviceScaleFactor": 1}

    def screenshot(self, output_path: str) -> str:
        result = self.send("Page.captureScreenshot", {"format": "png"})
        img_data = base64.b64decode(result["data"])
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(img_data)
        return output_path

    def screenshot_clip(self, output_path: str, clip: dict) -> str:
        """Capture a viewport clip to a PNG file."""
        result = self.send("Page.captureScreenshot", {
            "format": "png",
            "clip": {
                "x": max(0, float(clip["x"])),
                "y": max(0, float(clip["y"])),
                "width": max(1, float(clip["width"])),
                "height": max(1, float(clip["height"])),
                "scale": float(clip.get("scale", 1)),
            },
        })
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

    def get_attribute(self, selector: str, attribute: str) -> str | None:
        return self.evaluate(
            f"(function() {{"
            f"  var el = document.querySelector({json.dumps(selector)});"
            f"  return el ? el.getAttribute({json.dumps(attribute)}) : null;"
            f"}})()"
        )

    def get_inner_text(self) -> str:
        return self.evaluate("document.body.innerText") or ""

    def scroll_into_view(self, selector: str) -> bool:
        return bool(self.evaluate(
            f"(function() {{"
            f"  var el = document.querySelector({json.dumps(selector)});"
            f"  if (!el) return false;"
            f"  el.scrollIntoView({{block: 'center', inline: 'center'}});"
            f"  return true;"
            f"}})()"
        ))

    def click_selector(self, selector: str) -> dict:
        result = self.evaluate(
            f"(function() {{"
            f"  var el = document.querySelector({json.dumps(selector)});"
            f"  if (!el) return {{ok: false, found: false, error: 'selector not found: ' + {json.dumps(selector)}}};"
            f"  if (typeof el.scrollIntoView === 'function') el.scrollIntoView({{block: 'center', inline: 'center'}});"
            f"  function pickHit() {{"
            f"    var r = el.getBoundingClientRect();"
            f"    var hit = r;"
            f"    if (el.namespaceURI === 'http://www.w3.org/2000/svg') {{"
            f"    var candidates = Array.from(el.querySelectorAll('image,circle,rect,path,text')).map(function(child) {{"
            f"      var cr = child.getBoundingClientRect();"
            f"      return {{x: cr.x, y: cr.y, width: cr.width, height: cr.height, area: cr.width * cr.height}};"
            f"    }}).filter(function(cr) {{ return cr.width > 0 && cr.height > 0; }});"
            f"    candidates.sort(function(a, b) {{ return b.area - a.area; }});"
            f"    if (candidates.length) hit = candidates[0];"
            f"    }}"
            f"    return hit;"
            f"  }}"
            f"  var hit = pickHit();"
            f"  var cx = hit.x + hit.width / 2;"
            f"  var cy = hit.y + hit.height / 2;"
            f"  if (cx < 1 || cy < 1 || cx > window.innerWidth - 1 || cy > window.innerHeight - 1) {{"
            f"    window.scrollBy({{left: cx - window.innerWidth / 2, top: cy - window.innerHeight / 2, behavior: 'instant'}});"
            f"    hit = pickHit();"
            f"  }}"
            f"  return {{ok: true, found: true, tag: el.tagName, text: (el.textContent || '').slice(0, 80),"
            f"    x: hit.x + hit.width / 2, y: hit.y + hit.height / 2, width: hit.width, height: hit.height}};"
            f"}})()"
        )
        if not result or not result.get("ok"):
            return result or {"ok": False, "found": False, "error": "evaluate returned null"}
        if result.get("width", 0) <= 0 or result.get("height", 0) <= 0:
            return {"ok": False, "found": True, "error": f"selector has zero-size bounds: {selector}"}
        x = float(result["x"])
        y = float(result["y"])
        self.send("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        self.send(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
        )
        self.send(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
        )
        return result

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

    def hover_selector(self, selector: str) -> dict:
        """Hover over an element by dispatching mouseMoved event at its center."""
        rect = self.get_bounding_rect(selector)
        if not rect:
            return {"ok": False, "error": f"selector not found: {selector}"}

        center_x = rect["x"] + rect["width"] / 2
        center_y = rect["y"] + rect["height"] / 2

        self.evaluate(
            f"document.querySelector({json.dumps(selector)}).scrollIntoView({{block: 'center'}})"
        )
        rect = self.get_bounding_rect(selector)
        center_x = rect["x"] + rect["width"] / 2
        center_y = rect["y"] + rect["height"] / 2

        self.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": center_x,
            "y": center_y,
        })

        self.evaluate(
            f"(function() {{"
            f"  var el = document.querySelector({json.dumps(selector)});"
            f"  if (el) {{"
            f"    el.dispatchEvent(new MouseEvent('mouseenter', {{bubbles: true, clientX: {center_x}, clientY: {center_y}}}));"
            f"    el.dispatchEvent(new MouseEvent('mouseover', {{bubbles: true, clientX: {center_x}, clientY: {center_y}}}));"
            f"  }}"
            f"}})()"
        )

        tag = self.evaluate(f"document.querySelector({json.dumps(selector)})?.tagName") or "?"
        text = self.evaluate(
            f"(document.querySelector({json.dumps(selector)})?.textContent || '').slice(0, 80)"
        ) or ""

        return {"ok": True, "tag": tag, "text": text, "x": center_x, "y": center_y}

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

    def screenshot_element_bounds(self, output_path: str, selector: str, padding: int = 0) -> dict:
        """Capture a selector's current bounding box with optional viewport padding."""
        self.scroll_into_view(selector)
        rect = self.get_bounding_rect(selector)
        if not rect:
            raise RuntimeError(f"selector not found for screenshot: {selector}")
        viewport = self.viewport()
        x = max(0, rect["x"] - padding)
        y = max(0, rect["y"] - padding)
        max_w = max(1, viewport["width"] - x)
        max_h = max(1, viewport["height"] - y)
        clip = {
            "x": x,
            "y": y,
            "width": min(max_w, rect["width"] + padding * 2),
            "height": min(max_h, rect["height"] + padding * 2),
            "scale": 1,
        }
        self.screenshot_clip(output_path, clip)
        return clip

    def nearest_semantic_container(self, selector: str) -> dict | None:
        """Return nearest stable ancestor with data-qid/role or review metadata."""
        return self.evaluate(
            f"(function() {{"
            f"  var el = document.querySelector({json.dumps(selector)});"
            f"  if (!el) return null;"
            f"  var cur = el.parentElement;"
            f"  while (cur) {{"
            f"    var qid = cur.getAttribute('data-qid');"
            f"    var role = cur.getAttribute('role');"
            f"    if (qid || role || cur.getAttribute('data-review-surface') || cur.getAttribute('data-review-kind')) {{"
            f"      var r = cur.getBoundingClientRect();"
            f"      return {{"
            f"        selector: qid ? \"[data-qid='\" + qid.replace(/'/g, \"\\\\'\") + \"']\" : null,"
            f"        qid: qid,"
            f"        role: role,"
            f"        rect: {{width: r.width, height: r.height, x: r.x, y: r.y}}"
            f"      }};"
            f"    }}"
            f"    cur = cur.parentElement;"
            f"  }}"
            f"  return null;"
            f"}})()"
        )

    def clipping_status(self, selector: str) -> dict:
        """Detect whether selector bounds overflow a clipping ancestor."""
        return self.evaluate(
            f"(function() {{"
            f"  var el = document.querySelector({json.dumps(selector)});"
            f"  if (!el) return {{clipped: false, reason: 'target_not_found'}};"
            f"  var target = el.getBoundingClientRect();"
            f"  var cur = el.parentElement;"
            f"  while (cur) {{"
            f"    var style = getComputedStyle(cur);"
            f"    var overflow = style.overflow + ' ' + style.overflowX + ' ' + style.overflowY;"
            f"    if (/(hidden|clip|auto|scroll)/.test(overflow)) {{"
            f"      var r = cur.getBoundingClientRect();"
            f"      var clipped = target.left < r.left || target.top < r.top || target.right > r.right || target.bottom > r.bottom;"
            f"      if (clipped) return {{"
            f"        clipped: true,"
            f"        ancestorQid: cur.getAttribute('data-qid'),"
            f"        ancestorTag: cur.tagName,"
            f"        overflow: overflow,"
            f"        targetRect: {{x: target.x, y: target.y, width: target.width, height: target.height}},"
            f"        ancestorRect: {{x: r.x, y: r.y, width: r.width, height: r.height}}"
            f"      }};"
            f"    }}"
            f"    cur = cur.parentElement;"
            f"  }}"
            f"  return {{clipped: false}};"
            f"}})()"
        ) or {"clipped": False}

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
        self._cleanup_browser()

    def _cleanup_browser(self):
        if self.browser_process:
            try:
                self.browser_process.terminate()
                self.browser_process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError):
                try:
                    self.browser_process.kill()
                except OSError:
                    pass
            self.browser_process = None
        if self.user_data_dir:
            shutil.rmtree(self.user_data_dir, ignore_errors=True)
            self.user_data_dir = None
