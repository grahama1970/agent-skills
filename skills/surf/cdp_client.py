"""
CDP WebSocket client for browser automation.
Handles connection management, command dispatch, and page interaction.
"""

import json
import os
import sys
import time
import base64
import math
from pathlib import Path

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

try:
    import websocket
except ImportError:
    print("Installing websocket-client...", file=sys.stderr)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
    import websocket

try:
    import httpx
except ImportError:
    print("Installing httpx...", file=sys.stderr)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

from cdp_scripts import (
    ACCESSIBILITY_TREE_SCRIPT,
    GET_ELEMENT_COORDS_SCRIPT,
    CLICK_ELEMENT_SCRIPT,
    CLICK_SELECTOR_SCRIPT,
    GET_SELECTOR_COORDS_SCRIPT,
    TYPE_IN_ELEMENT_SCRIPT,
    GET_PAGE_TEXT_SCRIPT,
)

CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))


class CDPController:
    """Control Chrome via Chrome DevTools Protocol."""

    MAX_RETRIES = 3
    INITIAL_BACKOFF = 0.5  # seconds

    def __init__(self, port: int = None) -> None:
        self.port = port or CDP_PORT
        self.ws = None
        self.msg_id = 0
        self.target_id = None
        self.session_id = None
        self._ws_url = None

    def _get_ws_url(self) -> str:
        """Get WebSocket URL for the active page target."""
        try:
            resp = httpx.get(f"http://127.0.0.1:{self.port}/json", timeout=5)
            targets = resp.json()

            # Find a page target
            for target in targets:
                if target.get("type") == "page" and "webSocketDebuggerUrl" in target:
                    self.target_id = target.get("id")
                    return target["webSocketDebuggerUrl"]

            # Fallback to browser endpoint
            resp = httpx.get(f"http://127.0.0.1:{self.port}/json/version", timeout=5)
            info = resp.json()
            return info.get("webSocketDebuggerUrl", f"ws://127.0.0.1:{self.port}/devtools/browser")
        except Exception as e:
            raise ConnectionError(f"Cannot connect to CDP at port {self.port}: {e}")

    def connect(self, max_retries: int = None) -> None:
        """Connect to Chrome via WebSocket with exponential backoff retry."""
        max_retries = max_retries if max_retries is not None else self.MAX_RETRIES
        self._ws_url = self._get_ws_url()

        last_error = None
        for attempt in range(max_retries):
            try:
                self.ws = websocket.create_connection(self._ws_url, timeout=30)
                return  # Success
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    backoff = self.INITIAL_BACKOFF * (2 ** attempt)
                    print(f"WebSocket connection failed, retrying in {backoff}s... ({e})", file=sys.stderr)
                    time.sleep(backoff)
                    # Refresh URL in case target changed
                    try:
                        self._ws_url = self._get_ws_url()
                    except (ConnectionError, TimeoutError, OSError, httpx.HTTPError):
                        pass

        raise ConnectionError(f"Failed to connect after {max_retries} attempts: {last_error}")

    def _ensure_connected(self) -> None:
        """Ensure WebSocket is connected, reconnecting if necessary."""
        if self.ws:
            # Check if connection is still alive
            try:
                self.ws.ping()
                return
            except (ConnectionError, TimeoutError, OSError, websocket.WebSocketException):
                # Connection lost, close and reconnect
                try:
                    self.ws.close()
                except (ConnectionError, TimeoutError, OSError, websocket.WebSocketException):
                    pass
                self.ws = None

        self.connect()

    def send(self, method: str, params: dict = None) -> dict:
        """Send a CDP command and return the result with auto-reconnect."""
        last_error = None

        for attempt in range(self.MAX_RETRIES):
            try:
                self._ensure_connected()

                self.msg_id += 1
                msg = {"id": self.msg_id, "method": method}
                if params:
                    msg["params"] = params

                self.ws.send(json.dumps(msg))

                while True:
                    response = json.loads(self.ws.recv())
                    if response.get("id") == self.msg_id:
                        if "error" in response:
                            raise RuntimeError(f"CDP error: {response['error']}")
                        return response.get("result", {})

            except (websocket.WebSocketConnectionClosedException,
                    websocket.WebSocketTimeoutException,
                    ConnectionError, BrokenPipeError, OSError) as e:
                last_error = e
                # Connection issue - close and retry
                try:
                    self.ws.close()
                except (ConnectionError, TimeoutError, OSError, websocket.WebSocketException):
                    pass
                self.ws = None

                if attempt < self.MAX_RETRIES - 1:
                    backoff = self.INITIAL_BACKOFF * (2 ** attempt)
                    print(f"Connection lost, reconnecting in {backoff}s... ({e})", file=sys.stderr)
                    time.sleep(backoff)
                continue

            except Exception as e:
                # Non-connection error, don't retry
                raise

        raise ConnectionError(f"Failed to send command after {self.MAX_RETRIES} attempts: {last_error}")

    def close(self) -> None:
        """Close the WebSocket connection."""
        if self.ws:
            self.ws.close()
            self.ws = None

    def navigate(self, url: str, wait: bool = True) -> dict:
        """Navigate to a URL."""
        result = self.send("Page.navigate", {"url": url})
        if wait:
            time.sleep(1)  # Basic wait for page load
            # Wait for load event
            self.send("Page.enable")
            try:
                for _ in range(30):  # Wait up to 30 seconds
                    msg = json.loads(self.ws.recv())
                    if msg.get("method") == "Page.loadEventFired":
                        break
                    time.sleep(0.1)
            except (ConnectionError, TimeoutError, OSError, websocket.WebSocketException, json.JSONDecodeError):
                pass
        return {"url": url, "frameId": result.get("frameId")}

    def evaluate(self, expression: str, return_by_value: bool = True) -> any:
        """Evaluate JavaScript in the page context."""
        result = self.send("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": return_by_value,
            "awaitPromise": True
        })

        if "exceptionDetails" in result:
            raise RuntimeError(f"JS error: {result['exceptionDetails']}")

        return result.get("result", {}).get("value")

    def call_function(self, function_declaration: str, args: list = None) -> any:
        """Call a function with arguments."""
        result = self.send("Runtime.callFunctionOn", {
            "functionDeclaration": function_declaration,
            "arguments": [{"value": arg} for arg in (args or [])],
            "returnByValue": True,
            "executionContextId": 1
        })

        if "exceptionDetails" in result:
            raise RuntimeError(f"JS error: {result['exceptionDetails']}")

        return result.get("result", {}).get("value")

    def read_page(self, filter_mode: str = "interactive") -> dict:
        """Read the page and return accessibility tree with element refs."""
        result = self.evaluate(f"({ACCESSIBILITY_TREE_SCRIPT})('{filter_mode}', 15)")
        return result

    def get_element_coords(self, ref: str) -> dict:
        """Get coordinates of an element by ref."""
        result = self.evaluate(f"({GET_ELEMENT_COORDS_SCRIPT})('{ref}')")
        return result

    def click_element(self, ref: str) -> dict:
        """Click an element by ref."""
        # First try JS click
        result = self.evaluate(f"({CLICK_ELEMENT_SCRIPT})('{ref}')")
        if result and result.get("error"):
            return result

        # Also send CDP mouse events for better compatibility
        coords = self.get_element_coords(ref)
        if coords and not coords.get("error"):
            x, y = coords["x"], coords["y"]
            self.send("Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "x": x, "y": y,
                "button": "left",
                "clickCount": 1
            })
            self.send("Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "x": x, "y": y,
                "button": "left",
                "clickCount": 1
            })

        return {"success": True, "ref": ref}

    def click_selector(self, selector: str) -> dict:
        """Click an element by CSS selector (e.g. '[data-testid=\"btn\"]')."""
        result = self.evaluate(f"({CLICK_SELECTOR_SCRIPT})({json.dumps(selector)})")
        if result and result.get("error"):
            return result

        # Also send CDP mouse events for better compatibility
        coords = self.evaluate(f"({GET_SELECTOR_COORDS_SCRIPT})({json.dumps(selector)})")
        if coords and not coords.get("error"):
            x, y = coords["x"], coords["y"]
            self.send("Input.dispatchMouseEvent", {
                "type": "mousePressed",
                "x": x, "y": y,
                "button": "left",
                "clickCount": 1
            })
            self.send("Input.dispatchMouseEvent", {
                "type": "mouseReleased",
                "x": x, "y": y,
                "button": "left",
                "clickCount": 1
            })

        return result or {"success": True, "selector": selector}

    def click_coords(self, x: int, y: int) -> dict:
        """Click at specific coordinates."""
        self.send("Input.dispatchMouseEvent", {
            "type": "mousePressed",
            "x": x, "y": y,
            "button": "left",
            "clickCount": 1
        })
        self.send("Input.dispatchMouseEvent", {
            "type": "mouseReleased",
            "x": x, "y": y,
            "button": "left",
            "clickCount": 1
        })
        return {"success": True, "x": x, "y": y}

    def type_text(self, text: str, ref: str = None) -> dict:
        """Type text, optionally into a specific element."""
        if ref:
            result = self.evaluate(f"({TYPE_IN_ELEMENT_SCRIPT})('{ref}', {json.dumps(text)})")
            if result and result.get("error"):
                return result
        else:
            # Type character by character via CDP
            for char in text:
                self.send("Input.dispatchKeyEvent", {
                    "type": "keyDown",
                    "text": char
                })
                self.send("Input.dispatchKeyEvent", {
                    "type": "keyUp",
                    "text": char
                })

        return {"success": True, "text": text}

    def press_key(self, key: str) -> dict:
        """Press a special key (Enter, Tab, Escape, etc.)."""
        key_codes = {
            "Enter": {"key": "Enter", "code": "Enter", "keyCode": 13},
            "Tab": {"key": "Tab", "code": "Tab", "keyCode": 9},
            "Escape": {"key": "Escape", "code": "Escape", "keyCode": 27},
            "Backspace": {"key": "Backspace", "code": "Backspace", "keyCode": 8},
            "ArrowUp": {"key": "ArrowUp", "code": "ArrowUp", "keyCode": 38},
            "ArrowDown": {"key": "ArrowDown", "code": "ArrowDown", "keyCode": 40},
            "ArrowLeft": {"key": "ArrowLeft", "code": "ArrowLeft", "keyCode": 37},
            "ArrowRight": {"key": "ArrowRight", "code": "ArrowRight", "keyCode": 39},
        }

        key_info = key_codes.get(key, {"key": key, "code": key, "keyCode": 0})

        self.send("Input.dispatchKeyEvent", {
            "type": "keyDown",
            **key_info
        })
        self.send("Input.dispatchKeyEvent", {
            "type": "keyUp",
            **key_info
        })

        return {"success": True, "key": key}

    def screenshot(self, output_path: str = None, full_page: bool = False) -> dict:
        """Take a screenshot."""
        params = {"format": "png"}

        if full_page:
            # Get full page dimensions
            metrics = self.evaluate("""
                ({
                    width: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth),
                    height: Math.max(document.documentElement.scrollHeight, document.body.scrollHeight),
                    deviceScaleFactor: window.devicePixelRatio
                })
            """)

            if metrics:
                self.send("Emulation.setDeviceMetricsOverride", {
                    "width": metrics["width"],
                    "height": metrics["height"],
                    "deviceScaleFactor": metrics.get("deviceScaleFactor", 1),
                    "mobile": False
                })

        result = self.send("Page.captureScreenshot", params)

        if full_page:
            self.send("Emulation.clearDeviceMetricsOverride")

        if not output_path:
            output_path = f"/tmp/screenshot_{int(time.time())}.png"

        img_data = base64.b64decode(result["data"])
        Path(output_path).write_bytes(img_data)

        return {"path": output_path, "size": len(img_data)}

    def screenshot_container(
        self,
        selector: str,
        output_path: str = None,
        nearest: bool = True,
        max_segments: int = 80,
        settle_ms: int = 80,
    ) -> dict:
        """Capture and stitch a vertically scrollable element/container.

        The selector identifies the component of interest. By default we use the
        nearest scrollable ancestor; if none exists, the selected element itself
        is used. This handles fixed-height app panes that full-page screenshots
        cannot reveal.
        """
        if max_segments < 1:
            raise ValueError("max_segments must be >= 1")
        if settle_ms < 0:
            raise ValueError("settle_ms must be >= 0")

        target = self.evaluate(f"""
(() => {{
  const selected = document.querySelector({json.dumps(selector)});
  if (!selected) return {{ error: 'selector_not_found', selector: {json.dumps(selector)} }};
  function isScrollable(el) {{
    const style = getComputedStyle(el);
    const overflowY = style.overflowY;
    return (overflowY === 'auto' || overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 1;
  }}
  let container = selected;
  if ({str(nearest).lower()}) {{
    let node = selected;
    while (node && node !== document.body && node !== document.documentElement) {{
      if (isScrollable(node)) {{ container = node; break; }}
      node = node.parentElement;
    }}
  }}
  const rect = container.getBoundingClientRect();
  const previousScrollTop = container.scrollTop || 0;
  container.scrollTop = 0;
  const maxScrollTop = Math.max(0, container.scrollHeight - container.clientHeight);
  return {{
    selector: {json.dumps(selector)},
    resolvedTag: container.tagName,
    resolvedDataQid: container.getAttribute('data-qid'),
    rect: {{ x: rect.x, y: rect.y, width: rect.width, height: rect.height }},
    scrollHeight: container.scrollHeight,
    clientHeight: container.clientHeight,
    clientWidth: container.clientWidth,
    maxScrollTop,
    previousScrollTop,
  }};
}})()
        """)
        if not target or target.get("error"):
            return target or {"error": "container_resolution_failed", "selector": selector}

        rect = target["rect"]
        viewport = self.evaluate("""
({
  width: window.innerWidth,
  height: window.innerHeight,
  deviceScaleFactor: window.devicePixelRatio || 1
})
        """)

        clip_x = max(0, float(rect["x"]))
        clip_y = max(0, float(rect["y"]))
        clip_width = min(float(rect["width"]), float(viewport["width"]) - clip_x)
        clip_height = min(float(rect["height"]), float(viewport["height"]) - clip_y)
        if clip_width <= 0 or clip_height <= 0:
            return {
                "error": "container_not_visible",
                "selector": selector,
                "rect": rect,
                "viewport": viewport,
            }

        scroll_height = int(target["scrollHeight"])
        client_height = max(1, int(target["clientHeight"]))
        offsets: list[int] = []
        current = 0
        while current < scroll_height and len(offsets) < max_segments:
            offsets.append(current)
            current += client_height
        bottom_offset = max(0, scroll_height - client_height)
        if bottom_offset not in offsets and len(offsets) < max_segments:
            offsets.append(bottom_offset)
        offsets = sorted(set(offsets))
        if len(offsets) >= max_segments and offsets[-1] < bottom_offset:
            return {
                "error": "too_many_segments",
                "selector": selector,
                "segments": len(offsets),
                "max_segments": max_segments,
                "scrollHeight": scroll_height,
                "clientHeight": client_height,
            }

        try:
            from PIL import Image
            from io import BytesIO
        except ImportError as exc:
            raise RuntimeError("snap-container requires Pillow; add pillow to surf dependencies") from exc

        segment_images = []
        for offset in offsets:
            self.evaluate(f"""
(() => {{
  const selected = document.querySelector({json.dumps(selector)});
  let container = selected;
  function isScrollable(el) {{
    const style = getComputedStyle(el);
    const overflowY = style.overflowY;
    return (overflowY === 'auto' || overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 1;
  }}
  if ({str(nearest).lower()}) {{
    let node = selected;
    while (node && node !== document.body && node !== document.documentElement) {{
      if (isScrollable(node)) {{ container = node; break; }}
      node = node.parentElement;
    }}
  }}
  container.scrollTop = {int(offset)};
  return container.scrollTop;
}})()
            """)
            if settle_ms:
                time.sleep(settle_ms / 1000.0)
            shot = self.send("Page.captureScreenshot", {
                "format": "png",
                "clip": {
                    "x": clip_x,
                    "y": clip_y,
                    "width": clip_width,
                    "height": clip_height,
                    "scale": 1,
                },
                "captureBeyondViewport": False,
            })
            image = Image.open(BytesIO(base64.b64decode(shot["data"]))).convert("RGBA")
            segment_images.append((offset, image))

        if not segment_images:
            return {"error": "no_segments_captured", "selector": selector}

        scale = segment_images[0][1].height / clip_height
        output_width = segment_images[0][1].width
        output_height = max(1, int(math.ceil(scroll_height * scale)))
        stitched = Image.new("RGBA", (output_width, output_height), (0, 0, 0, 0))

        written_until = 0
        for offset, image in segment_images:
            start = max(offset, written_until)
            end = min(offset + client_height, scroll_height)
            if end <= start:
                continue
            crop_top = int(round((start - offset) * scale))
            crop_bottom = int(round((end - offset) * scale))
            crop_bottom = min(crop_bottom, image.height)
            crop = image.crop((0, crop_top, image.width, crop_bottom))
            stitched.paste(crop, (0, int(round(start * scale))))
            written_until = end

        # Restore original scroll position for non-destructive verification.
        self.evaluate(f"""
(() => {{
  const selected = document.querySelector({json.dumps(selector)});
  if (!selected) return false;
  function isScrollable(el) {{
    const style = getComputedStyle(el);
    const overflowY = style.overflowY;
    return (overflowY === 'auto' || overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 1;
  }}
  let container = selected;
  if ({str(nearest).lower()}) {{
    let node = selected;
    while (node && node !== document.body && node !== document.documentElement) {{
      if (isScrollable(node)) {{ container = node; break; }}
      node = node.parentElement;
    }}
  }}
  container.scrollTop = {int(target.get("previousScrollTop") or 0)};
  return true;
}})()
        """)

        if not output_path:
            output_path = f"/tmp/container_screenshot_{int(time.time())}.png"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        stitched.save(output_path)

        return {
            "path": output_path,
            "selector": selector,
            "nearest": nearest,
            "resolved_tag": target.get("resolvedTag"),
            "resolved_data_qid": target.get("resolvedDataQid"),
            "scrollHeight": scroll_height,
            "clientHeight": client_height,
            "clientWidth": int(target["clientWidth"]),
            "segments": len(segment_images),
            "offsets": offsets,
            "size": Path(output_path).stat().st_size,
            "image": {"width": stitched.width, "height": stitched.height},
        }

    def get_page_text(self) -> dict:
        """Get the page's text content."""
        return self.evaluate(GET_PAGE_TEXT_SCRIPT)

    def scroll(self, direction: str = "down", amount: int = None) -> dict:
        """Scroll the page."""
        if amount is None:
            amount = 500

        if direction == "down":
            delta_y = amount
        elif direction == "up":
            delta_y = -amount
        elif direction == "top":
            self.evaluate("window.scrollTo(0, 0)")
            return {"success": True, "scrolled_to": "top"}
        elif direction == "bottom":
            self.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            return {"success": True, "scrolled_to": "bottom"}
        else:
            delta_y = amount

        self.send("Input.dispatchMouseEvent", {
            "type": "mouseWheel",
            "x": 400,
            "y": 300,
            "deltaX": 0,
            "deltaY": delta_y
        })

        return {"success": True, "direction": direction, "amount": amount}

    def wait(self, seconds: float) -> dict:
        """Wait for a specified time."""
        time.sleep(seconds)
        return {"waited": seconds}
