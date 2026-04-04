#!/usr/bin/env python3
"""
surf-qml: QML/Qt Application Automation via AT-SPI

Uses Linux Accessibility (AT-SPI) to interact with Qt/QML applications.
Similar to surf skill but for native desktop applications.
"""

import typer
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv, find_dotenv
from loguru import logger
load_dotenv(find_dotenv(usecwd=True), override=False)

# AT-SPI imports
try:
    import gi
    gi.require_version('Atspi', '2.0')
    from gi.repository import Atspi
    ATSPI_AVAILABLE = True
except (ImportError, ValueError):
    ATSPI_AVAILABLE = False
    Atspi = None

# ImageMagick + ffmpeg for screenshots/video (no PIL dependency)
IMPORT_BIN = "/usr/bin/import"  # ImageMagick
FFMPEG_BIN = "/usr/bin/ffmpeg"


@dataclass
class Element:
    """Represents an accessible element."""
    ref: str
    role: str
    name: str
    description: str
    states: list[str]
    bounds: tuple[int, int, int, int]  # x, y, width, height
    accessible: object  # Atspi.Accessible

    def to_dict(self) -> dict:
        return {
            "ref": self.ref,
            "role": self.role,
            "name": self.name,
            "description": self.description,
            "states": self.states,
            "bounds": self.bounds,
        }


class SurfQML:
    """QML automation controller using AT-SPI."""

    def __init__(self, timeout: float = 5.0):
        if not ATSPI_AVAILABLE:
            raise RuntimeError(
                "AT-SPI not available. Install: sudo apt install python3-gi gir1.2-atspi-2.0"
            )
        self.timeout = timeout
        self._elements: dict[str, Element] = {}
        self._element_counter = 0
        self._target_app: Optional[object] = None

    def _next_ref(self) -> str:
        """Generate next element reference."""
        self._element_counter += 1
        return f"e{self._element_counter}"

    def _get_states(self, accessible) -> list[str]:
        """Get state names for an accessible."""
        states = []
        state_set = accessible.get_state_set()
        for state in [
            Atspi.StateType.FOCUSED,
            Atspi.StateType.SELECTED,
            Atspi.StateType.CHECKED,
            Atspi.StateType.PRESSED,
            Atspi.StateType.EXPANDED,
            Atspi.StateType.ENABLED,
            Atspi.StateType.VISIBLE,
            Atspi.StateType.SHOWING,
            Atspi.StateType.EDITABLE,
            Atspi.StateType.FOCUSABLE,
        ]:
            if state_set.contains(state):
                name = Atspi.StateType.get_name(state)
                if name not in ("enabled", "visible", "showing"):  # Skip common states
                    states.append(name)
        return states

    def _get_bounds(self, accessible) -> tuple[int, int, int, int]:
        """Get screen bounds for an accessible."""
        try:
            component = accessible.get_component_iface()
            if component:
                rect = component.get_extents(Atspi.CoordType.SCREEN)
                return (rect.x, rect.y, rect.width, rect.height)
        except Exception as e:
            logger.debug("component failed: {}", e)
        return (0, 0, 0, 0)

    def _walk_tree(
        self,
        accessible,
        depth: int = 0,
        max_depth: int = 10,
        role_filter: Optional[str] = None,
        name_filter: Optional[str] = None,
    ) -> list[Element]:
        """Walk accessibility tree and collect elements."""
        if depth > max_depth:
            return []

        elements = []
        try:
            role = accessible.get_role_name()
            name = accessible.get_name() or ""
            desc = accessible.get_description() or ""

            # Apply filters
            include = True
            if role_filter and role_filter.lower() not in role.lower():
                include = False
            if name_filter and name_filter.lower() not in name.lower():
                include = False

            if include and (name or role not in ("filler", "panel", "unknown")):
                ref = self._next_ref()
                element = Element(
                    ref=ref,
                    role=role,
                    name=name,
                    description=desc,
                    states=self._get_states(accessible),
                    bounds=self._get_bounds(accessible),
                    accessible=accessible,
                )
                self._elements[ref] = element
                elements.append(element)

            # Recurse into children
            for i in range(accessible.get_child_count()):
                child = accessible.get_child_at_index(i)
                if child:
                    elements.extend(
                        self._walk_tree(child, depth + 1, max_depth, role_filter, name_filter)
                    )
        except Exception as e:
            pass  # Skip inaccessible elements

        return elements

    def list_apps(self) -> list[dict]:
        """List all accessible applications."""
        apps = []
        desktop = Atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if app:
                name = app.get_name() or "(unnamed)"
                apps.append({
                    "name": name,
                    "windows": app.get_child_count(),
                })
        return apps

    def find_app(self, name: str) -> Optional[object]:
        """Find application by name (partial match)."""
        desktop = Atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if app:
                app_name = app.get_name() or ""
                if name.lower() in app_name.lower():
                    self._target_app = app
                    return app
        return None

    def find_window(self, name: str) -> Optional[object]:
        """Find window by name across all apps."""
        desktop = Atspi.get_desktop(0)
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if app:
                for j in range(app.get_child_count()):
                    window = app.get_child_at_index(j)
                    if window:
                        win_name = window.get_name() or ""
                        if name.lower() in win_name.lower():
                            self._target_app = app
                            return window
        return None

    def focus_window(self, name: str) -> bool:
        """Focus/activate a window by name."""
        window = self.find_window(name)
        if not window:
            return False

        try:
            # Try to activate via AT-SPI action
            action = window.get_action_iface()
            if action:
                for i in range(action.get_n_actions()):
                    action_name = action.get_action_name(i)
                    if action_name in ("activate", "focus", "click"):
                        action.do_action(i)
                        return True

            # Fallback: use xdotool if available
            subprocess.run(
                ["xdotool", "search", "--name", name, "windowactivate"],
                capture_output=True,
                timeout=2,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return True
        except Exception:
            return False

    def read_tree(
        self,
        max_depth: int = 10,
        role_filter: Optional[str] = None,
        name_filter: Optional[str] = None,
    ) -> list[Element]:
        """Read accessibility tree for target app/window."""
        self._elements.clear()
        self._element_counter = 0

        # Use target app if set, otherwise read all
        if self._target_app:
            return self._walk_tree(
                self._target_app, max_depth=max_depth,
                role_filter=role_filter, name_filter=name_filter
            )

        # Read from all visible apps
        desktop = Atspi.get_desktop(0)
        all_elements = []
        for i in range(desktop.get_child_count()):
            app = desktop.get_child_at_index(i)
            if app:
                all_elements.extend(
                    self._walk_tree(
                        app, max_depth=max_depth,
                        role_filter=role_filter, name_filter=name_filter
                    )
                )
        return all_elements

    def get_element(self, ref: str) -> Optional[Element]:
        """Get element by reference."""
        return self._elements.get(ref)

    def click(self, ref: str) -> bool:
        """Click an element by reference."""
        element = self.get_element(ref)
        if not element:
            return False

        try:
            # Try action interface first
            action = element.accessible.get_action_iface()
            if action:
                for i in range(action.get_n_actions()):
                    name = action.get_action_name(i)
                    if name in ("click", "activate", "press"):
                        return action.do_action(i)

            # Fallback: click at center of bounds
            x, y, w, h = element.bounds
            if w > 0 and h > 0:
                cx, cy = x + w // 2, y + h // 2
                subprocess.run(
                    ["xdotool", "mousemove", str(cx), str(cy), "click", "1"],
                    capture_output=True,
                    timeout=2,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                return True
        except Exception as e:
            logger.debug("value lookup failed: {}", e)
        return False

    def type_text(self, text: str, ref: Optional[str] = None, clear: bool = False) -> bool:
        """Type text into element or focused element."""
        if ref:
            element = self.get_element(ref)
            if element:
                # Focus the element first
                self.click(ref)
                time.sleep(0.1)

        try:
            # Clear existing text if requested
            if clear:
                subprocess.run(
                    ["xdotool", "key", "ctrl+a", "BackSpace"],
                    capture_output=True,
                    timeout=2,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                time.sleep(0.05)

            # Type the text
            subprocess.run(
                ["xdotool", "type", "--clearmodifiers", text],
                capture_output=True,
                timeout=5,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return True
        except Exception:
            return False

    def press_key(self, key: str) -> bool:
        """Press a key or key combination."""
        # Map common key names
        key_map = {
            "return": "Return",
            "enter": "Return",
            "tab": "Tab",
            "escape": "Escape",
            "esc": "Escape",
            "up": "Up",
            "down": "Down",
            "left": "Left",
            "right": "Right",
            "space": "space",
            "backspace": "BackSpace",
            "delete": "Delete",
        }

        key_lower = key.lower()
        xdotool_key = key_map.get(key_lower, key)

        try:
            subprocess.run(
                ["xdotool", "key", xdotool_key],
                capture_output=True,
                timeout=2,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return True
        except Exception:
            return False

    def take_screenshot(
        self,
        output: Optional[str] = None,
        element_ref: Optional[str] = None,
    ) -> Optional[str]:
        """Take screenshot of screen or element using ImageMagick import."""
        if not output:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output = f"/tmp/surf-qml-{timestamp}.png"

        try:
            if element_ref:
                element = self.get_element(element_ref)
                if element and element.bounds[2] > 0:
                    x, y, w, h = element.bounds
                    subprocess.run(
                        [IMPORT_BIN, "-window", "root",
                         "-crop", f"{w}x{h}+{x}+{y}", "+repage", output],
                        capture_output=True, timeout=10,
                        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                    )
                    return output if Path(output).exists() else None

            # Full screenshot
            subprocess.run(
                [IMPORT_BIN, "-window", "root", output],
                capture_output=True, timeout=10,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return output if Path(output).exists() else None
        except Exception as e:
            logger.debug("path resolution failed: {}", e)
        return None

    def record_video(
        self,
        output: Optional[str] = None,
        element_ref: Optional[str] = None,
        window_name: Optional[str] = None,
        duration: int = 10,
        framerate: int = 30,
    ) -> Optional[str]:
        """Record video of screen, window, or element using ffmpeg x11grab."""
        if not output:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output = f"/tmp/surf-qml-{timestamp}.mp4"

        display = os.environ.get("DISPLAY", ":0")
        x_off, y_off = 0, 0

        try:
            if element_ref:
                element = self.get_element(element_ref)
                if element and element.bounds[2] > 0:
                    ex, ey, ew, eh = element.bounds
                    margin = 10
                    x_off = max(0, ex - margin)
                    y_off = max(0, ey - margin)
                    w = ew + 2 * margin
                    h = eh + 2 * margin
                else:
                    return None
            elif window_name:
                result = subprocess.run(
                    ["xdotool", "search", "--name", window_name, "getwindowgeometry", "--shell"],
                    capture_output=True, text=True, timeout=5,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                if result.returncode == 0:
                    geo = {}
                    for line in result.stdout.strip().split("\n"):
                        if "=" in line:
                            k, v = line.split("=", 1)
                            geo[k] = int(v)
                    x_off = geo.get("X", 0)
                    y_off = geo.get("Y", 0)
                    w = geo.get("WIDTH", 1920)
                    h = geo.get("HEIGHT", 1080)
                else:
                    return None
            else:
                # Full screen
                result = subprocess.run(
                    ["xdpyinfo"], capture_output=True, text=True, timeout=5,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )
                match = re.search(r"dimensions:\s+(\d+)x(\d+)", result.stdout)
                if match:
                    w, h = int(match.group(1)), int(match.group(2))
                else:
                    w, h = 1920, 1080

            # Round to even (libx264 requirement)
            w = w + (w % 2)
            h = h + (h % 2)

            cmd = [
                FFMPEG_BIN, "-y",
                "-f", "x11grab",
                "-framerate", str(framerate),
                "-video_size", f"{w}x{h}",
                "-i", f"{display}+{x_off},{y_off}",
                "-t", str(duration),
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                output,
            ]
            subprocess.run(cmd, capture_output=True, timeout=duration + 15,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
            return output if Path(output).exists() else None
        except Exception as e:
            logger.debug("path resolution failed: {}", e)
        return None


def format_tree(elements: list[Element], indent: int = 0) -> str:
    """Format element tree for display."""
    lines = []
    for elem in elements:
        states_str = " ".join(f"[{s}]" for s in elem.states) if elem.states else ""
        name_str = f'"{elem.name}"' if elem.name else ""
        line = f"[{elem.ref}] {elem.role} {name_str} {states_str}".strip()
        lines.append(line)
    return "\n".join(lines)


app = typer.Typer(help="QML/Qt automation via AT-SPI")


def _get_surf() -> SurfQML:
    try:
        return SurfQML()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(code=1)


@app.command("list")
def list_cmd():
    """List accessible applications."""
    surf = _get_surf()
    apps = surf.list_apps()
    if not apps:
        print("No accessible applications found")
        print("Hint: Ensure AT-SPI is running: systemctl --user status at-spi-dbus-bus")
        raise typer.Exit(code=1)
    print("Accessible applications:")
    for a in apps:
        print(f"  {a['name']} ({a['windows']} window(s))")


@app.command()
def find(
    name: str = typer.Argument(..., help="Window name to find"),
):
    """Find window by name."""
    surf = _get_surf()
    window = surf.find_window(name)
    if window:
        print(f"Found: {window.get_name()}")
        print(f"  Role: {window.get_role_name()}")
        print(f"  Children: {window.get_child_count()}")
    else:
        print(f"Window not found: {name}")
        raise typer.Exit(code=1)


@app.command()
def focus(
    name: str = typer.Argument(..., help="Window name to focus"),
):
    """Focus window by name."""
    surf = _get_surf()
    if surf.focus_window(name):
        print(f"Focused: {name}")
    else:
        print(f"Failed to focus: {name}")
        raise typer.Exit(code=1)


@app.command()
def read(
    depth: int = typer.Option(10, help="Max tree depth"),
    role: Optional[str] = typer.Option(None, help="Filter by role"),
    name: Optional[str] = typer.Option(None, help="Filter by name"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Read accessibility tree."""
    surf = _get_surf()
    elements = surf.read_tree(
        max_depth=depth,
        role_filter=role,
        name_filter=name,
    )

    if as_json:
        print(json.dumps([e.to_dict() for e in elements], indent=2))
    else:
        if elements:
            print(format_tree(elements))
        else:
            print("No elements found")
            print("Hint: Use './run.sh find <app>' first to target an application")


@app.command()
def props(
    ref: str = typer.Argument(..., help="Element reference (e.g., e5)"),
):
    """Get element properties."""
    surf = _get_surf()
    surf.read_tree()
    element = surf.get_element(ref)
    if element:
        print(f"Element: {ref}")
        print(f"  Role: {element.role}")
        print(f"  Name: {element.name}")
        print(f"  Description: {element.description}")
        print(f"  States: {element.states}")
        print(f"  Bounds: {element.bounds}")
    else:
        print(f"Element not found: {ref}")
        print("Hint: Run './run.sh read' first to get current element references")
        raise typer.Exit(code=1)


@app.command("click")
def click_cmd(
    ref: str = typer.Argument(..., help="Element reference"),
):
    """Click element."""
    surf = _get_surf()
    surf.read_tree()
    if surf.click(ref):
        print(f"Clicked: {ref}")
    else:
        print(f"Failed to click: {ref}")
        raise typer.Exit(code=1)


@app.command("type")
def type_cmd(
    text: str = typer.Argument(..., help="Text to type"),
    ref: Optional[str] = typer.Option(None, help="Element reference to type into"),
    clear: bool = typer.Option(False, help="Clear before typing"),
):
    """Type text."""
    surf = _get_surf()
    surf.read_tree()
    if surf.type_text(text, ref=ref, clear=clear):
        print(f"Typed: {text}")
    else:
        print("Failed to type")
        raise typer.Exit(code=1)


@app.command("key")
def key_cmd(
    key: str = typer.Argument(..., help="Key to press (Tab, Return, Escape, etc.)"),
):
    """Press key."""
    surf = _get_surf()
    if surf.press_key(key):
        print(f"Pressed: {key}")
    else:
        print(f"Failed to press: {key}")
        raise typer.Exit(code=1)


@app.command()
def snap(
    output: Optional[str] = typer.Option(None, help="Output file path"),
    element: Optional[str] = typer.Option(None, help="Element reference to screenshot"),
):
    """Take screenshot."""
    surf = _get_surf()
    result = surf.take_screenshot(
        output=output,
        element_ref=element,
    )
    if result:
        print(f"Screenshot saved: {result}")
    else:
        print("Failed to take screenshot")
        raise typer.Exit(code=1)


@app.command()
def record(
    output: Optional[str] = typer.Option(None, help="Output file path"),
    element: Optional[str] = typer.Option(None, help="Element reference to record"),
    window: Optional[str] = typer.Option(None, help="Window name to record"),
    duration: int = typer.Option(10, help="Duration in seconds"),
    framerate: int = typer.Option(30, help="Framerate"),
):
    """Record video."""
    surf = _get_surf()
    result = surf.record_video(
        output=output,
        element_ref=element,
        window_name=window,
        duration=duration,
        framerate=framerate,
    )
    if result:
        print(f"Recording saved: {result}")
    else:
        print("Failed to record")
        raise typer.Exit(code=1)


@app.command()
def test(
    scenario: str = typer.Argument(..., help="Test scenario name or file"),
):
    """Run test scenario."""
    surf = _get_surf()
    from scenario_runner import run_scenario
    raise typer.Exit(code=run_scenario(surf, scenario) or 0)


if __name__ == "__main__":
    app()
