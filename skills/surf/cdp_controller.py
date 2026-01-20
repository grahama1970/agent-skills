#!/usr/bin/env python3
"""
CDP-based browser automation controller.
Provides full surf-cli functionality without requiring the Chrome extension.
"""
import argparse
import json
import os
import sys
import time
import base64
from pathlib import Path

try:
    import websocket
except ImportError:
    print("Installing websocket-client...", file=sys.stderr)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client", "-q"])
    import websocket

try:
    import requests
except ImportError:
    print("Installing requests...", file=sys.stderr)
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests


CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))

# Accessibility tree generation script (minified from surf-cli content script)
ACCESSIBILITY_TREE_SCRIPT = '''
(function(filter, maxDepth) {
  filter = filter || "interactive";
  maxDepth = maxDepth || 15;

  if (!window.__piElementMap) window.__piElementMap = {};
  if (!window.__piRefs) window.__piRefs = {};

  let globalRefCounter = window.__piRefCounter || 0;

  const VALID_ARIA_ROLES = new Set([
    "alert", "alertdialog", "application", "article", "banner", "blockquote",
    "button", "caption", "cell", "checkbox", "code", "columnheader", "combobox",
    "complementary", "contentinfo", "definition", "deletion", "dialog", "directory",
    "document", "emphasis", "feed", "figure", "form", "generic", "grid", "gridcell",
    "group", "heading", "img", "insertion", "link", "list", "listbox", "listitem",
    "log", "main", "mark", "marquee", "math", "menu", "menubar", "menuitem",
    "menuitemcheckbox", "menuitemradio", "meter", "navigation", "none", "note",
    "option", "paragraph", "presentation", "progressbar", "radio", "radiogroup",
    "region", "row", "rowgroup", "rowheader", "scrollbar", "search", "searchbox",
    "separator", "slider", "spinbutton", "status", "strong", "subscript",
    "superscript", "switch", "tab", "table", "tablist", "tabpanel", "term",
    "textbox", "time", "timer", "toolbar", "tooltip", "tree", "treegrid", "treeitem"
  ]);

  function isFocusable(element) {
    const tagName = element.tagName.toLowerCase();
    if (["button", "input", "select", "textarea"].includes(tagName)) {
      return !element.disabled;
    }
    if (tagName === "a" && element.hasAttribute("href")) return true;
    if (element.hasAttribute("tabindex")) {
      const tabindex = parseInt(element.getAttribute("tabindex") || "", 10);
      return !isNaN(tabindex) && tabindex >= 0;
    }
    if (element.getAttribute("contenteditable") === "true") return true;
    return false;
  }

  function getExplicitRole(element) {
    const roleAttr = element.getAttribute("role");
    if (!roleAttr) return null;
    const roles = roleAttr.split(/\\s+/).filter(r => r);
    for (const role of roles) {
      if (VALID_ARIA_ROLES.has(role)) return role;
    }
    return null;
  }

  function getImplicitRole(element) {
    const tag = element.tagName.toLowerCase();
    const type = element.getAttribute("type");

    const tagRoles = {
      a: (el) => el.hasAttribute("href") ? "link" : "generic",
      article: "article", aside: "complementary", button: "button",
      datalist: "listbox", dd: "definition", details: "group", dialog: "dialog",
      dt: "term", fieldset: "group", figure: "figure",
      footer: (el) => el.closest("article, aside, main, nav, section") ? "generic" : "contentinfo",
      form: (el) => el.hasAttribute("aria-label") || el.hasAttribute("aria-labelledby") ? "form" : "generic",
      h1: "heading", h2: "heading", h3: "heading", h4: "heading", h5: "heading", h6: "heading",
      header: (el) => el.closest("article, aside, main, nav, section") ? "generic" : "banner",
      hr: "separator",
      img: (el) => el.getAttribute("alt") === "" ? "presentation" : "img",
      li: "listitem", main: "main", math: "math", menu: "list", meter: "meter",
      nav: "navigation", ol: "list", optgroup: "group", option: "option",
      output: "status", p: "paragraph", progress: "progressbar", search: "search",
      section: (el) => el.hasAttribute("aria-label") || el.hasAttribute("aria-labelledby") ? "region" : "generic",
      select: (el) => el.hasAttribute("multiple") || (el.size && el.size > 1) ? "listbox" : "combobox",
      table: "table", tbody: "rowgroup", td: "cell", textarea: "textbox",
      tfoot: "rowgroup", th: "columnheader", thead: "rowgroup", time: "time",
      tr: "row", ul: "list",
    };

    if (tag === "input") {
      const inputRoles = {
        button: "button", checkbox: "checkbox", email: "textbox", file: "button",
        image: "button", number: "spinbutton", radio: "radio", range: "slider",
        reset: "button", search: "searchbox", submit: "button", tel: "textbox",
        text: "textbox", url: "textbox",
      };
      return inputRoles[type || ""] || "textbox";
    }

    const roleOrFn = tagRoles[tag];
    if (typeof roleOrFn === "function") return roleOrFn(element);
    return roleOrFn || "generic";
  }

  function getResolvedRole(element) {
    const explicitRole = getExplicitRole(element);
    if (!explicitRole) return getImplicitRole(element);
    if ((explicitRole === "none" || explicitRole === "presentation") && isFocusable(element)) {
      return getImplicitRole(element);
    }
    return explicitRole;
  }

  function getOrAssignRef(element, role, name) {
    const existing = element._piRef;
    if (existing && existing.role === role && existing.name === name) {
      return existing.ref;
    }
    const ref = `e${++globalRefCounter}`;
    element._piRef = { role, name, ref };
    window.__piRefCounter = globalRefCounter;
    return ref;
  }

  function getName(element) {
    const tag = element.tagName.toLowerCase();

    const labelledBy = element.getAttribute('aria-labelledby');
    if (labelledBy) {
      const names = labelledBy.split(/\\s+/).map(id => {
        const el = document.getElementById(id);
        return el?.textContent?.trim() || '';
      }).filter(Boolean);
      if (names.length) {
        const joined = names.join(' ');
        return joined.length > 100 ? joined.substring(0, 100) + '...' : joined;
      }
    }

    if (tag === "select") {
      const selected = element.querySelector("option[selected]") ||
        (element.selectedIndex >= 0 ? element.options[element.selectedIndex] : null);
      if (selected?.textContent?.trim()) return selected.textContent.trim();
    }

    const ariaLabel = element.getAttribute("aria-label");
    if (ariaLabel?.trim()) return ariaLabel.trim();

    const placeholder = element.getAttribute("placeholder");
    if (placeholder?.trim()) return placeholder.trim();

    const title = element.getAttribute("title");
    if (title?.trim()) return title.trim();

    const alt = element.getAttribute("alt");
    if (alt?.trim()) return alt.trim();

    if (element.id) {
      const label = document.querySelector(`label[for="${element.id}"]`);
      if (label?.textContent?.trim()) return label.textContent.trim();
    }

    if (tag === "input") {
      const type = element.getAttribute("type") || "";
      const value = element.getAttribute("value");
      if (type === "submit" && value?.trim()) return value.trim();
      if (element.value && element.value.length < 50 && element.value.trim()) return element.value.trim();
    }

    if (["button", "a", "summary"].includes(tag)) {
      let textContent = "";
      for (const node of element.childNodes) {
        if (node.nodeType === Node.TEXT_NODE) textContent += node.textContent;
      }
      if (textContent.trim()) return textContent.trim();
    }

    if (/^h[1-6]$/.test(tag)) {
      const text = element.textContent;
      if (text?.trim()) {
        const t = text.trim();
        return t.length > 100 ? t.substring(0, 100) + "..." : t;
      }
    }

    if (tag === "img") return "";

    let directText = "";
    for (const node of element.childNodes) {
      if (node.nodeType === Node.TEXT_NODE) directText += node.textContent;
    }
    if (directText?.trim() && directText.trim().length >= 3) {
      const text = directText.trim();
      return text.length > 100 ? text.substring(0, 100) + "..." : text;
    }

    return "";
  }

  function isVisible(element) {
    const style = window.getComputedStyle(element);
    return (
      style.display !== "none" &&
      style.visibility !== "hidden" &&
      style.opacity !== "0" &&
      element.offsetWidth > 0 &&
      element.offsetHeight > 0
    );
  }

  function isInteractive(element) {
    const tag = element.tagName.toLowerCase();
    return (
      ["a", "button", "input", "select", "textarea", "details", "summary"].includes(tag) ||
      element.hasAttribute("onclick") ||
      element.hasAttribute("tabindex") ||
      element.getAttribute("role") === "button" ||
      element.getAttribute("role") === "link" ||
      element.getAttribute("contenteditable") === "true"
    );
  }

  function isLandmark(element) {
    const tag = element.tagName.toLowerCase();
    return (
      ["h1", "h2", "h3", "h4", "h5", "h6", "nav", "main", "header", "footer", "section", "article", "aside"].includes(tag) ||
      element.hasAttribute("role")
    );
  }

  function hasCursorPointer(element) {
    const style = window.getComputedStyle(element);
    return style.cursor === "pointer";
  }

  function getAriaProps(element) {
    const props = {};
    const checkedAttr = element.getAttribute('aria-checked');
    if (checkedAttr === 'true') props.checked = true;
    else if (checkedAttr === 'false') props.checked = false;
    else if (element instanceof HTMLInputElement && (element.type === 'checkbox' || element.type === 'radio')) {
      props.checked = element.checked;
    }

    if (element.getAttribute('aria-disabled') === 'true' || element.disabled) {
      props.disabled = true;
    }

    const expandedAttr = element.getAttribute('aria-expanded');
    if (expandedAttr === 'true') props.expanded = true;
    else if (expandedAttr === 'false') props.expanded = false;

    const tag = element.tagName.toLowerCase();
    if (/^h[1-6]$/.test(tag)) {
      props.level = parseInt(tag[1], 10);
    }

    return props;
  }

  function formatAriaProps(props) {
    const parts = [];
    if (props.checked !== undefined) {
      parts.push(props.checked ? '[checked]' : '[unchecked]');
    }
    if (props.disabled) parts.push('[disabled]');
    if (props.expanded !== undefined) {
      parts.push(props.expanded ? '[expanded]' : '[collapsed]');
    }
    if (props.level !== undefined) {
      parts.push(`[level=${props.level}]`);
    }
    return parts.join(' ');
  }

  function shouldInclude(element, filter) {
    const tag = element.tagName.toLowerCase();
    if (["script", "style", "meta", "link", "title", "noscript"].includes(tag)) return false;
    if (element.getAttribute("aria-hidden") === "true") return false;
    if (!isVisible(element)) return false;

    const rect = element.getBoundingClientRect();
    if (!(rect.top < window.innerHeight && rect.bottom > 0 && rect.left < window.innerWidth && rect.right > 0)) {
      return false;
    }

    if (filter === "interactive") return isInteractive(element);
    if (isInteractive(element)) return true;
    if (isLandmark(element)) return true;
    if (getName(element).length > 0) return true;

    const role = getResolvedRole(element);
    return role !== "generic" && role !== "img";
  }

  function traverse(element, depth, filter, maxDepth) {
    const lines = [];
    const include = shouldInclude(element, filter);

    if (include) {
      const role = getResolvedRole(element);
      const name = getName(element);
      const ariaProps = getAriaProps(element);

      const elemRefId = getOrAssignRef(element, role, name);
      window.__piRefs[elemRefId] = element;
      window.__piElementMap[elemRefId] = { element: element, role, name };

      const indent = "  ".repeat(depth);
      let line = `${indent}${role}`;
      if (name) {
        const escapedName = name.replace(/\\s+/g, " ").replace(/"/g, '\\\\"');
        line += ` "${escapedName}"`;
      }
      line += ` [${elemRefId}]`;

      const propsStr = formatAriaProps(ariaProps);
      if (propsStr) line += ` ${propsStr}`;

      if (hasCursorPointer(element)) {
        line += " [cursor=pointer]";
      }

      const href = element.getAttribute("href");
      if (href) line += ` href="${href}"`;

      lines.push(line);
    }

    if (depth < maxDepth) {
      for (const child of element.children) {
        lines.push(...traverse(child, include ? depth + 1 : depth, filter, maxDepth));
      }
    }

    return lines;
  }

  const lines = traverse(document.body, 0, filter, maxDepth);
  const content = lines.join("\\n");

  return {
    pageContent: content + `\\n\\n[Viewport: ${window.innerWidth}x${window.innerHeight}]`,
    viewport: { width: window.innerWidth, height: window.innerHeight },
    url: window.location.href,
    title: document.title
  };
})
'''

GET_ELEMENT_COORDS_SCRIPT = '''
(function(ref) {
  const element = window.__piRefs && window.__piRefs[ref];
  if (!element) {
    return { error: `Element ${ref} not found. Run read first to get current elements.` };
  }
  const rect = element.getBoundingClientRect();
  return {
    x: Math.round(rect.left + rect.width / 2),
    y: Math.round(rect.top + rect.height / 2),
    width: rect.width,
    height: rect.height
  };
})
'''

CLICK_ELEMENT_SCRIPT = '''
(function(ref) {
  const element = window.__piRefs && window.__piRefs[ref];
  if (!element) {
    return { error: `Element ${ref} not found. Run read first to get current elements.` };
  }
  element.click();
  return { success: true };
})
'''

TYPE_IN_ELEMENT_SCRIPT = '''
(function(ref, value) {
  const element = window.__piRefs && window.__piRefs[ref];
  if (!element) {
    return { error: `Element ${ref} not found. Run read first to get current elements.` };
  }
  element.focus();
  if (element.tagName === 'INPUT' || element.tagName === 'TEXTAREA') {
    element.value = value;
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
  } else if (element.contentEditable === 'true') {
    element.textContent = value;
    element.dispatchEvent(new Event('input', { bubbles: true }));
  }
  return { success: true };
})
'''

GET_PAGE_TEXT_SCRIPT = '''
(function() {
  const article = document.querySelector("article");
  const main = document.querySelector("main");
  const content = article || main || document.body;
  const text = content.textContent?.replace(/\\s+/g, " ").trim().substring(0, 50000) || "";
  return { text, title: document.title, url: window.location.href };
})()
'''


class CDPController:
    """Control Chrome via Chrome DevTools Protocol."""

    MAX_RETRIES = 3
    INITIAL_BACKOFF = 0.5  # seconds

    def __init__(self, port: int = None):
        self.port = port or CDP_PORT
        self.ws = None
        self.msg_id = 0
        self.target_id = None
        self.session_id = None
        self._ws_url = None

    def _get_ws_url(self) -> str:
        """Get WebSocket URL for the active page target."""
        try:
            resp = requests.get(f"http://127.0.0.1:{self.port}/json", timeout=5)
            targets = resp.json()

            # Find a page target
            for target in targets:
                if target.get("type") == "page" and "webSocketDebuggerUrl" in target:
                    self.target_id = target.get("id")
                    return target["webSocketDebuggerUrl"]

            # Fallback to browser endpoint
            resp = requests.get(f"http://127.0.0.1:{self.port}/json/version", timeout=5)
            info = resp.json()
            return info.get("webSocketDebuggerUrl", f"ws://127.0.0.1:{self.port}/devtools/browser")
        except Exception as e:
            raise ConnectionError(f"Cannot connect to CDP at port {self.port}: {e}")

    def connect(self, max_retries: int = None):
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
                    except:
                        pass

        raise ConnectionError(f"Failed to connect after {max_retries} attempts: {last_error}")

    def _ensure_connected(self):
        """Ensure WebSocket is connected, reconnecting if necessary."""
        if self.ws:
            # Check if connection is still alive
            try:
                self.ws.ping()
                return
            except:
                # Connection lost, close and reconnect
                try:
                    self.ws.close()
                except:
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
                except:
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

    def close(self):
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
            except:
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


def main():
    parser = argparse.ArgumentParser(description="CDP-based browser automation")
    parser.add_argument("command", choices=[
        "go", "read", "click", "type", "key", "snap", "scroll", "wait", "text"
    ])
    parser.add_argument("args", nargs="*", help="Command arguments")
    parser.add_argument("--port", type=int, default=CDP_PORT, help="CDP port")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("--filter", default="interactive", choices=["interactive", "all"],
                       help="Filter mode for read command")
    parser.add_argument("--full", action="store_true", help="Full page screenshot")
    parser.add_argument("--output", "-o", help="Output path for screenshot")
    parser.add_argument("--submit", action="store_true", help="Press Enter after typing")
    parser.add_argument("--ref", help="Element ref for type command")

    args = parser.parse_args()

    cdp = CDPController(port=args.port)

    try:
        if args.command == "go":
            if not args.args:
                print("Error: URL required", file=sys.stderr)
                sys.exit(1)
            url = args.args[0]
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            result = cdp.navigate(url)

        elif args.command == "read":
            result = cdp.read_page(filter_mode=args.filter)
            if not args.json and result:
                # Pretty print the accessibility tree
                print(f"URL: {result.get('url', 'unknown')}")
                print(f"Title: {result.get('title', 'unknown')}")
                print()
                print(result.get("pageContent", ""))
                return

        elif args.command == "click":
            if not args.args:
                print("Error: Element ref required (e.g., e5)", file=sys.stderr)
                sys.exit(1)
            ref = args.args[0]
            result = cdp.click_element(ref)

        elif args.command == "type":
            if not args.args:
                print("Error: Text required", file=sys.stderr)
                sys.exit(1)
            text = " ".join(args.args)
            result = cdp.type_text(text, ref=args.ref)
            if args.submit:
                cdp.press_key("Enter")
                result["submitted"] = True

        elif args.command == "key":
            if not args.args:
                print("Error: Key name required (e.g., Enter, Tab, Escape)", file=sys.stderr)
                sys.exit(1)
            result = cdp.press_key(args.args[0])

        elif args.command == "snap":
            result = cdp.screenshot(output_path=args.output, full_page=args.full)
            if not args.json:
                print(f"Screenshot saved: {result['path']}")
                return

        elif args.command == "scroll":
            direction = args.args[0] if args.args else "down"
            amount = int(args.args[1]) if len(args.args) > 1 else None
            result = cdp.scroll(direction, amount)

        elif args.command == "wait":
            seconds = float(args.args[0]) if args.args else 1
            result = cdp.wait(seconds)

        elif args.command == "text":
            result = cdp.get_page_text()
            if not args.json and result:
                print(result.get("text", ""))
                return

        if args.json:
            print(json.dumps(result, indent=2))
        elif result:
            if isinstance(result, dict):
                if result.get("error"):
                    print(f"Error: {result['error']}", file=sys.stderr)
                    sys.exit(1)
                elif result.get("success"):
                    print("OK")
                else:
                    print(json.dumps(result, indent=2))
            else:
                print(result)

    except Exception as e:
        if args.json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        cdp.close()


if __name__ == "__main__":
    main()
