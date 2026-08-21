#!/usr/bin/env python3
"""
CDP-based browser automation controller.
Provides full surf-cli functionality without requiring the Chrome extension.

This is the assembler module. Implementation lives in:
- cdp_scripts.py: JavaScript injection scripts
- cdp_client.py: CDPController WebSocket client class
"""
import json
import os
import sys
from typing import Optional
from pathlib import Path

import typer

# Re-export all public API for backward compatibility
from cdp_scripts import (
    ACCESSIBILITY_TREE_SCRIPT,
    GET_ELEMENT_COORDS_SCRIPT,
    CLICK_ELEMENT_SCRIPT,
    CLICK_SELECTOR_SCRIPT,
    GET_SELECTOR_COORDS_SCRIPT,
    TYPE_IN_ELEMENT_SCRIPT,
    GET_PAGE_TEXT_SCRIPT,
)
from cdp_client import CDPController, CDP_PORT
from pointer_os_dispatch import PointerDispatchError, dispatch_os_pointer_plan

app = typer.Typer(help="CDP-based browser automation")


def _red_team_enabled() -> bool:
    """True when SURF_RED_TEAM is set to an enabling value.

    Red-team mode defaults to off. Only when enabled may surf dispatch captcha
    pointer plans whose defensive_scope is ``authorized_live_surf_resolution``.
    """

    value = os.environ.get("SURF_RED_TEAM", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def red_team_gate(plan: dict) -> str | None:
    """Return an error string when a live-resolution plan needs red-team mode.

    The loopback synthetic defensive scope is always permitted; live-resolution
    pointer dispatch is gated behind SURF_RED_TEAM (default off).
    """

    if plan.get("defensive_scope") != "authorized_live_surf_resolution":
        return None
    if _red_team_enabled():
        return None
    return (
        "surf red-team mode is disabled; export SURF_RED_TEAM=1 to dispatch a "
        "live-resolution pointer plan"
    )


def _run_cdp_command(cdp: CDPController, as_json: bool, fn, *args, **kwargs):
    """Helper to run a CDP command with error handling."""
    try:
        result = fn(*args, **kwargs)
        if as_json:
            print(json.dumps(result, indent=2))
        elif result:
            if isinstance(result, dict):
                if result.get("error"):
                    print(f"Error: {result['error']}", file=sys.stderr)
                    raise typer.Exit(code=1)
                elif result.get("success"):
                    print("OK")
                else:
                    print(json.dumps(result, indent=2))
            else:
                print(result)
    except typer.Exit:
        raise
    except Exception as e:
        if as_json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(code=1)
    finally:
        cdp.close()


def _cdp_probe(port: int) -> bool:
    """Return true when a CDP target is reachable without dispatching input."""

    try:
        CDPController(port=port)._get_ws_url()
    except Exception:
        return False
    return True


def _load_json_object(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON file: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


@app.command()
def go(
    url: str = typer.Argument(..., help="URL to navigate to"),
    port: int = typer.Option(CDP_PORT, help="CDP port"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Navigate to a URL."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    cdp = CDPController(port=port)
    _run_cdp_command(cdp, as_json, cdp.navigate, url)


@app.command()
def read(
    port: int = typer.Option(CDP_PORT, help="CDP port"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    filter: str = typer.Option("interactive", help="Filter mode (interactive, all)"),
):
    """Read page accessibility tree."""
    cdp = CDPController(port=port)
    try:
        result = cdp.read_page(filter_mode=filter)
        if not as_json and result:
            print(f"URL: {result.get('url', 'unknown')}")
            print(f"Title: {result.get('title', 'unknown')}")
            print()
            print(result.get("pageContent", ""))
        elif as_json:
            print(json.dumps(result, indent=2))
    except Exception as e:
        if as_json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(code=1)
    finally:
        cdp.close()


@app.command("click")
def click_cmd(
    target: str = typer.Argument(..., help="Element ref (e.g., e5) or CSS selector (e.g., '[data-testid=\"btn\"]')"),
    port: int = typer.Option(CDP_PORT, help="CDP port"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Click an element by ref or CSS selector (auto-detected)."""
    import re
    cdp = CDPController(port=port)
    if re.match(r'^e\d+$', target):
        _run_cdp_command(cdp, as_json, cdp.click_element, target)
    else:
        _run_cdp_command(cdp, as_json, cdp.click_selector, target)


@app.command("cdp.raw")
def cdp_raw(
    method: str = typer.Argument(..., help="CDP method, e.g. Page.getLayoutMetrics"),
    params_json: Optional[str] = typer.Option(None, "--params-json", help="Inline JSON object params"),
    params_file: Optional[Path] = typer.Option(None, "--params-file", exists=True, dir_okay=False),
    port: int = typer.Option(CDP_PORT, help="CDP port"),
    as_json: bool = typer.Option(True, "--json/--no-json", help="Output as JSON"),
):
    """Send one raw CDP command through Surf's CDP fallback transport."""

    if params_json and params_file:
        raise typer.BadParameter("use only one of --params-json or --params-file")
    try:
        if params_file is not None:
            params = _load_json_object(params_file)
        elif params_json:
            params = json.loads(params_json)
            if not isinstance(params, dict):
                raise ValueError("--params-json must be a JSON object")
        else:
            params = {}
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(json.dumps({"schema_version": "surf.cdp_raw_result.v1", "success": False, "error": str(exc)}))
        raise typer.Exit(code=2)

    cdp = CDPController(port=port)
    _run_cdp_command(cdp, as_json, cdp.raw_command, method, params)


@app.command("cdp.layout")
def cdp_layout(
    port: int = typer.Option(CDP_PORT, help="CDP port"),
    as_json: bool = typer.Option(True, "--json/--no-json", help="Output as JSON"),
):
    """Read viewport and CDP layout metrics."""

    cdp = CDPController(port=port)
    _run_cdp_command(cdp, as_json, cdp.layout_metrics)


@app.command("cdp.quads")
def cdp_quads(
    selector: str = typer.Argument(..., help="CSS selector to resolve with DOM.getContentQuads"),
    port: int = typer.Option(CDP_PORT, help="CDP port"),
    as_json: bool = typer.Option(True, "--json/--no-json", help="Output as JSON"),
):
    """Resolve content quads and primary center for a CSS selector."""

    cdp = CDPController(port=port)
    _run_cdp_command(cdp, as_json, cdp.content_quads, selector)


@app.command("cdp.hit-test")
def cdp_hit_test(
    x: float = typer.Argument(..., help="Viewport CSS x coordinate"),
    y: float = typer.Argument(..., help="Viewport CSS y coordinate"),
    port: int = typer.Option(CDP_PORT, help="CDP port"),
    as_json: bool = typer.Option(True, "--json/--no-json", help="Output as JSON"),
):
    """Resolve the DOM node at viewport-relative CSS coordinates."""

    cdp = CDPController(port=port)
    _run_cdp_command(cdp, as_json, cdp.hit_test, x, y)


@app.command("pointer.dispatch")
def pointer_dispatch(
    plan_path: Path = typer.Option(..., "--plan", exists=True, dir_okay=False),
    port: int = typer.Option(CDP_PORT, help="CDP port"),
    transport: str = typer.Option("auto", "--transport", help="Pointer transport: auto, cdp, or os"),
    backend: str = typer.Option("auto", "--backend", help="OS backend: auto, uinput, or xdotool"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Build the OS pointer receipt without moving the pointer"),
    window_id: Optional[str] = typer.Option(None, "--window-id", help="OS window id for geometry lookup"),
    window_origin_x: Optional[int] = typer.Option(None, "--window-origin-x", help="Window origin X in screen pixels"),
    window_origin_y: Optional[int] = typer.Option(None, "--window-origin-y", help="Window origin Y in screen pixels"),
    device_pixel_ratio: Optional[float] = typer.Option(None, "--device-pixel-ratio", help="Viewport CSS to screen pixel scale"),
    as_json: bool = typer.Option(True, "--json/--no-json", help="Output as JSON"),
):
    """Dispatch receipt-bound pointer samples from a pointer-motion plan."""

    try:
        plan = _load_json_object(plan_path)
        samples = plan.get("samples")
        if not isinstance(samples, list):
            raise ValueError("pointer plan must contain a samples array")
    except (OSError, ValueError) as exc:
        print(json.dumps({"schema_version": "surf.pointer_dispatch_receipt.v1", "success": False, "error": str(exc)}))
        raise typer.Exit(code=2)

    gate_error = red_team_gate(plan)
    if gate_error is not None:
        print(json.dumps({
            "schema_version": "surf.pointer_dispatch_receipt.v1",
            "success": False,
            "error": gate_error,
            "red_team_enabled": False,
            "defensive_scope": plan.get("defensive_scope"),
            "hint": "export SURF_RED_TEAM=1",
        }))
        raise typer.Exit(code=2)

    if transport not in {"auto", "cdp", "os"}:
        print(json.dumps({
            "schema_version": "surf.pointer_dispatch_receipt.v1",
            "success": False,
            "error": f"unsupported pointer transport: {transport}; expected auto, cdp, or os",
        }))
        raise typer.Exit(code=2)

    source_path = str(plan_path.expanduser().resolve())
    if transport in {"auto", "cdp"} and _cdp_probe(port):
        cdp = CDPController(port=port)
        _run_cdp_command(
            cdp,
            as_json,
            cdp.dispatch_pointer_samples,
            samples,
            source_path=source_path,
        )
        return
    if transport == "cdp":
        print(json.dumps({
            "schema_version": "surf.pointer_dispatch_receipt.v1",
            "success": False,
            "transport_selected": "cdp",
            "error": f"Cannot connect to CDP at port {port}",
        }))
        raise typer.Exit(code=2)

    try:
        receipt = dispatch_os_pointer_plan(
            plan,
            source_path=source_path,
            backend=backend,
            dry_run=dry_run,
            window_id=window_id,
            window_origin_x=window_origin_x,
            window_origin_y=window_origin_y,
            device_pixel_ratio=device_pixel_ratio,
        )
    except PointerDispatchError as exc:
        print(json.dumps({
            "schema_version": "surf.pointer_dispatch_receipt.v1",
            "success": False,
            "transport_selected": "os",
            "error": str(exc),
        }))
        raise typer.Exit(code=2)

    if as_json:
        print(json.dumps(receipt, indent=2))
    else:
        print("OK")


@app.command("type")
def type_cmd(
    text: list[str] = typer.Argument(..., help="Text to type"),
    port: int = typer.Option(CDP_PORT, help="CDP port"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    ref: Optional[str] = typer.Option(None, help="Element ref for type command"),
    submit: bool = typer.Option(False, help="Press Enter after typing"),
):
    """Type text into an element."""
    cdp = CDPController(port=port)
    try:
        full_text = " ".join(text)
        result = cdp.type_text(full_text, ref=ref)
        if submit:
            cdp.press_key("Enter")
            result["submitted"] = True
        if as_json:
            print(json.dumps(result, indent=2))
        elif result.get("success"):
            print("OK")
    except Exception as e:
        if as_json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(code=1)
    finally:
        cdp.close()


@app.command("key")
def key_cmd(
    key_name: str = typer.Argument(..., help="Key name (Enter, Tab, Escape, etc.)"),
    port: int = typer.Option(CDP_PORT, help="CDP port"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Press a special key."""
    cdp = CDPController(port=port)
    _run_cdp_command(cdp, as_json, cdp.press_key, key_name)


@app.command()
def snap(
    port: int = typer.Option(CDP_PORT, help="CDP port"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    full: bool = typer.Option(False, help="Full page screenshot"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Output path for screenshot"),
):
    """Take a screenshot."""
    cdp = CDPController(port=port)
    try:
        result = cdp.screenshot(output_path=output, full_page=full)
        if not as_json:
            print(f"Screenshot saved: {result['path']}")
        else:
            print(json.dumps(result, indent=2))
    except Exception as e:
        if as_json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(code=1)
    finally:
        cdp.close()


@app.command("snap-container")
def snap_container(
    selector: str = typer.Argument(..., help="CSS selector for the component or scroll container"),
    port: int = typer.Option(CDP_PORT, help="CDP port"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
    output: Optional[str] = typer.Option(None, "-o", "--output", help="Output path for stitched screenshot"),
    nearest: bool = typer.Option(True, help="Use nearest scrollable ancestor instead of the selected element"),
    max_segments: int = typer.Option(80, help="Maximum vertical segments to capture"),
    settle_ms: int = typer.Option(80, help="Milliseconds to wait after each scroll step"),
):
    """Capture and stitch a nested scroll container."""
    cdp = CDPController(port=port)
    try:
        result = cdp.screenshot_container(
            selector=selector,
            output_path=output,
            nearest=nearest,
            max_segments=max_segments,
            settle_ms=settle_ms,
        )
        if result.get("error"):
            if as_json:
                print(json.dumps(result, indent=2))
            else:
                print(f"Error: {result['error']}", file=sys.stderr)
            raise typer.Exit(code=1)
        if as_json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Container screenshot saved: {result['path']}")
    except typer.Exit:
        raise
    except Exception as e:
        if as_json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(code=1)
    finally:
        cdp.close()


@app.command()
def scroll(
    direction: str = typer.Argument("down", help="Scroll direction (down, up, top, bottom)"),
    amount: Optional[int] = typer.Argument(None, help="Scroll amount in pixels"),
    port: int = typer.Option(CDP_PORT, help="CDP port"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Scroll the page."""
    cdp = CDPController(port=port)
    _run_cdp_command(cdp, as_json, cdp.scroll, direction, amount)


@app.command()
def wait(
    seconds: float = typer.Argument(1.0, help="Seconds to wait"),
    port: int = typer.Option(CDP_PORT, help="CDP port"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Wait for a specified time."""
    cdp = CDPController(port=port)
    _run_cdp_command(cdp, as_json, cdp.wait, seconds)


@app.command()
def text(
    port: int = typer.Option(CDP_PORT, help="CDP port"),
    as_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Get the page's text content."""
    cdp = CDPController(port=port)
    try:
        result = cdp.get_page_text()
        if not as_json and result:
            print(result.get("text", ""))
        elif as_json:
            print(json.dumps(result, indent=2))
    except Exception as e:
        if as_json:
            print(json.dumps({"error": str(e)}))
        else:
            print(f"Error: {e}", file=sys.stderr)
        raise typer.Exit(code=1)
    finally:
        cdp.close()


if __name__ == "__main__":
    app()
