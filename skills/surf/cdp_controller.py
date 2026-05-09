#!/usr/bin/env python3
"""
CDP-based browser automation controller.
Provides full surf-cli functionality without requiring the Chrome extension.

This is the assembler module. Implementation lives in:
- cdp_scripts.py: JavaScript injection scripts
- cdp_client.py: CDPController WebSocket client class
"""
import json
import sys
from typing import Optional

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

app = typer.Typer(help="CDP-based browser automation")


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
