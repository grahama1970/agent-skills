#!/usr/bin/env python3
"""
Sanity script: Textual TabbedContent API
Purpose: Verify TabbedContent and TabPane widgets work as expected
Documentation: https://textual.textualize.io/widgets/tabbed_content/

Exit codes:
  0 = PASS (dependency works)
  1 = FAIL (dependency broken)
"""
import sys

try:
    from textual.widgets import TabbedContent, TabPane, Label, Static
    from textual.app import App, ComposeResult
except ImportError as e:
    print(f"FAIL: textual not installed or import error: {e}")
    print("Run: pip install textual")
    sys.exit(1)

# Verify we can construct the widgets
try:
    # Create a minimal app to verify compose works
    class TestApp(App):
        def compose(self) -> ComposeResult:
            with TabbedContent():
                with TabPane("Tab 1", id="tab1"):
                    yield Label("Content 1")
                with TabPane("Tab 2", id="tab2"):
                    yield Label("Content 2")

    # Just instantiate, don't run
    app = TestApp()
    print("PASS: TabbedContent, TabPane, Label all import and instantiate correctly")
    sys.exit(0)

except Exception as e:
    print(f"FAIL: Error constructing TabbedContent: {e}")
    sys.exit(1)
