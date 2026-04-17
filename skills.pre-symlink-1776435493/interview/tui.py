#!/usr/bin/env python3
"""
Textual TUI for Interview Skill v2.1 - Claude Code UX Style.

Wizard-style interface with:
- TabbedContent for question navigation
- Numbered options with descriptions
- Automatic "Other" option for custom input
- Image placeholders [Image X] with graphics protocol support
- Multi-select support
- Image comparison mode with custom image support
- File path detection for custom images
"""
from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import (
    Button,
    Header,
    Footer,
    Static,
    Input,
    TabbedContent,
    TabPane,
)
from textual.binding import Binding
from textual import on

from typing import TYPE_CHECKING
from loguru import logger
if TYPE_CHECKING:
    from .interview import Session, Question

# Re-export all public names from submodules for backward compatibility
from .tui_widgets import OptionItem, ImageOptionItem, OtherOption
from .tui_panes import QuestionPane, ImageComparePane, BboxAnnotationPane, SubmitPane


class InterviewApp(App):
    """Textual app for interview with Claude Code-style wizard UX."""

    CSS = """
    Screen {
        background: $background;
    }

    #main-container {
        height: 1fr;
    }

    #title-bar {
        background: $primary;
        padding: 1;
        text-align: center;
        text-style: bold;
    }

    #context-bar {
        background: $surface;
        padding: 1;
        color: $text-muted;
    }

    TabbedContent {
        height: 1fr;
    }

    #nav-hints {
        dock: bottom;
        height: 1;
        background: $surface;
        padding: 0 2;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("enter", "select_or_submit", "Select/Submit", show=True),
        Binding("space", "toggle_option", "Toggle (multi)", show=True),
        Binding("tab", "next_tab", "Next Tab", show=True),
        Binding("shift+tab", "prev_tab", "Prev Tab", show=True),
        Binding("up", "prev_option", "Up", show=False),
        Binding("down", "next_option", "Down", show=False),
        Binding("1", "select_1", "Option 1", show=False),
        Binding("2", "select_2", "Option 2", show=False),
        Binding("3", "select_3", "Option 3", show=False),
        Binding("4", "select_4", "Option 4", show=False),
        Binding("5", "select_5", "Option 5", show=False),
        Binding("escape", "cancel", "Cancel", show=True),
    ]

    def __init__(self, session: "Session", **kwargs):
        super().__init__(**kwargs)
        self.session = session
        self.responses: dict[str, dict] = {}
        self.current_option_index = 1
        self.base_path = Path(session.context).parent if session.context else None

    def compose(self) -> ComposeResult:
        yield Header()

        with Container(id="main-container"):
            yield Static(self.session.title, id="title-bar")

            if self.session.context:
                yield Static(self.session.context, id="context-bar")

            with TabbedContent(id="tabs"):
                for q in self.session.questions:
                    # Check registry for custom TUI pane factory
                    from .registry import get_tui_factory
                    factory = get_tui_factory(q.type)
                    if factory:
                        yield factory(q, base_path=self.base_path)
                    elif q.type == "image_compare" and q.comparison_images:
                        yield ImageComparePane(q, base_path=self.base_path)
                    else:
                        yield QuestionPane(q, base_path=self.base_path)

                yield SubmitPane()

            yield Static(
                "Enter: select \u00b7 Space: toggle (multi) \u00b7 Tab/Shift+Tab: navigate \u00b7 1-5: quick select \u00b7 Esc: cancel",
                id="nav-hints"
            )

        yield Footer()

    def _get_current_pane(self) -> QuestionPane | ImageComparePane | SubmitPane | None:
        """Get the currently active question pane."""
        try:
            tabs = self.query_one("#tabs", TabbedContent)
            active = tabs.active
            if active:
                pane = self.query_one(f"#{active}")
                return pane
        except Exception as e:
            logger.debug("widget query failed: {}", e)
        return None

    def _get_option_count(self) -> int:
        """Get number of options in current pane (including Other/Custom)."""
        pane = self._get_current_pane()
        if isinstance(pane, QuestionPane) and pane.question.options:
            return len(pane.question.options) + 1  # +1 for Other
        elif isinstance(pane, ImageComparePane) and pane.question.comparison_images:
            return len(pane.question.comparison_images) + 1  # +1 for Custom
        return 1

    def action_select_or_submit(self):
        """Select current option or submit if on submit pane."""
        pane = self._get_current_pane()
        if isinstance(pane, SubmitPane):
            self._do_submit()
        elif isinstance(pane, QuestionPane):
            max_opts = self._get_option_count()
            if self.current_option_index == max_opts:
                pane.select_other()
            else:
                pane.select_option(self.current_option_index)
                if not pane.question.multi_select:
                    # Auto-advance to next tab
                    self.action_next_tab()
        elif isinstance(pane, ImageComparePane):
            max_opts = self._get_option_count()
            if self.current_option_index == max_opts:
                pane.select_custom()
            else:
                pane.select_option(self.current_option_index)
                # Auto-advance for image compare
                self.action_next_tab()

    def action_toggle_option(self):
        """Toggle option for multi-select."""
        pane = self._get_current_pane()
        if isinstance(pane, QuestionPane) and pane.question.multi_select:
            max_opts = self._get_option_count()
            if self.current_option_index == max_opts:
                pane.select_other()
            else:
                pane.select_option(self.current_option_index)

    def action_next_option(self):
        """Move to next option."""
        max_opts = self._get_option_count()
        self.current_option_index = min(self.current_option_index + 1, max_opts)
        self._highlight_current_option()

    def action_prev_option(self):
        """Move to previous option."""
        self.current_option_index = max(self.current_option_index - 1, 1)
        self._highlight_current_option()

    def _highlight_current_option(self):
        """Visually highlight the current option (for keyboard nav)."""
        # This could be enhanced with a cursor indicator
        pass

    def action_next_tab(self):
        """Move to next tab."""
        try:
            tabs = self.query_one("#tabs", TabbedContent)
            # Find current index
            panes = list(tabs.query(TabPane))
            current = tabs.active
            for i, pane in enumerate(panes):
                if pane.id == current and i < len(panes) - 1:
                    tabs.active = panes[i + 1].id
                    self.current_option_index = 1
                    break
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    def action_prev_tab(self):
        """Move to previous tab."""
        try:
            tabs = self.query_one("#tabs", TabbedContent)
            panes = list(tabs.query(TabPane))
            current = tabs.active
            for i, pane in enumerate(panes):
                if pane.id == current and i > 0:
                    tabs.active = panes[i - 1].id
                    self.current_option_index = 1
                    break
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    def action_select_1(self):
        self._quick_select(1)

    def action_select_2(self):
        self._quick_select(2)

    def action_select_3(self):
        self._quick_select(3)

    def action_select_4(self):
        self._quick_select(4)

    def action_select_5(self):
        self._quick_select(5)

    def _quick_select(self, num: int):
        """Quick select option by number."""
        pane = self._get_current_pane()
        if isinstance(pane, QuestionPane):
            max_opts = self._get_option_count()
            if num <= max_opts:
                self.current_option_index = num
                if num == max_opts:
                    pane.select_other()
                else:
                    pane.select_option(num)
                    if not pane.question.multi_select:
                        self.action_next_tab()
        elif isinstance(pane, ImageComparePane):
            max_opts = self._get_option_count()
            if num <= max_opts:
                self.current_option_index = num
                if num == max_opts:
                    pane.select_custom()
                else:
                    pane.select_option(num)
                    self.action_next_tab()

    def action_cancel(self):
        """Cancel and exit."""
        self.exit(self.responses)

    def _do_submit(self):
        """Collect all responses and exit."""
        self._collect_responses()
        self.exit(self.responses)

    def _collect_responses(self):
        """Collect responses from all question panes."""
        try:
            tabs = self.query_one("#tabs", TabbedContent)
            for pane in tabs.query(TabPane):
                if isinstance(pane, (QuestionPane, ImageComparePane, BboxAnnotationPane)):
                    resp = pane.get_response()
                    if resp:
                        self.responses[pane.question.id] = resp
        except Exception as e:
            logger.debug("value lookup failed: {}", e)

    @on(Input.Changed)
    def on_input_changed(self, event: Input.Changed):
        """Handle input changes to detect image paths."""
        # Check if this is an "other" input that allows images
        try:
            parent = event.input.parent
            while parent and not isinstance(parent, OtherOption):
                parent = parent.parent

            if isinstance(parent, OtherOption) and parent.allow_image:
                parent.check_for_image_path(event.value, self.base_path)
        except Exception as e:
            logger.debug("value extraction failed: {}", e)

    # Button handlers imported from textual's on decorator
    @on(Input.Submitted)
    def _on_button_submit(self, event):
        """Handle submit button press."""
        pass

    @on(Button.Pressed, "#submit-btn")
    def _handle_submit_btn(self):
        self._do_submit()

    @on(Button.Pressed, "#cancel-btn")
    def _handle_cancel_btn(self):
        self.action_cancel()


def run_tui_interview(session: "Session", timeout: int) -> dict[str, dict]:
    """
    Run TUI interview and return responses.

    Args:
        session: Interview session
        timeout: Timeout in seconds (not enforced in TUI, user controls)

    Returns:
        Dict mapping question IDs to response dicts
    """
    # Need to convert session questions to proper format
    from .interview import Question

    # Ensure questions have the right type
    questions = []
    for q in session.questions:
        if isinstance(q, dict):
            questions.append(Question(**q))
        else:
            questions.append(q)
    session.questions = questions

    app = InterviewApp(session)
    result = app.run()
    return result or {}
