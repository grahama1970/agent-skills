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
from textual.containers import Container, Vertical, Horizontal
from textual.widgets import (
    Header,
    Footer,
    Static,
    Button,
    Input,
    Label,
    TabbedContent,
    TabPane,
    Rule,
)
from textual.binding import Binding
from textual import on
from textual.message import Message
from rich.text import Text

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .interview import Session, Question


class OptionItem(Horizontal):
    """A single numbered option with label and description."""

    DEFAULT_CSS = """
    OptionItem {
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }

    OptionItem.selected {
        background: $primary-darken-2;
    }

    OptionItem .option-number {
        width: 4;
        color: $text-muted;
    }

    OptionItem .option-content {
        width: 1fr;
    }

    OptionItem .option-label {
        text-style: bold;
    }

    OptionItem .option-description {
        color: $text-muted;
        padding-left: 2;
    }
    """

    def __init__(self, index: int, label: str, description: str = "", selected: bool = False, **kwargs):
        super().__init__(**kwargs)
        self.index = index
        self.label_text = label
        self.description_text = description
        self._selected = selected

    def compose(self) -> ComposeResult:
        marker = ">" if self._selected else " "
        yield Static(f"{marker}{self.index}.", classes="option-number")
        with Vertical(classes="option-content"):
            yield Static(self.label_text, classes="option-label")
            if self.description_text:
                yield Static(self.description_text, classes="option-description")

    def set_selected(self, selected: bool):
        self._selected = selected
        self.set_class(selected, "selected")
        # Update marker
        number_widget = self.query_one(".option-number", Static)
        marker = ">" if selected else " "
        number_widget.update(f"{marker}{self.index}.")


class ImageOptionItem(Horizontal):
    """An image option for image_compare questions."""

    DEFAULT_CSS = """
    ImageOptionItem {
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
    }

    ImageOptionItem.selected {
        background: $primary-darken-2;
    }

    ImageOptionItem .option-number {
        width: 4;
        color: $text-muted;
    }

    ImageOptionItem .option-content {
        width: 1fr;
    }

    ImageOptionItem .image-placeholder {
        color: $primary;
    }

    ImageOptionItem .option-label {
        text-style: bold;
        margin-top: 1;
    }

    ImageOptionItem .option-description {
        color: $text-muted;
        padding-left: 2;
    }
    """

    def __init__(
        self,
        index: int,
        label: str,
        placeholder: str,
        description: str = "",
        selected: bool = False,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.index = index
        self.label_text = label
        self.placeholder_text = placeholder
        self.description_text = description
        self._selected = selected

    def compose(self) -> ComposeResult:
        marker = ">" if self._selected else " "
        yield Static(f"{marker}{self.index}.", classes="option-number")
        with Vertical(classes="option-content"):
            yield Static(self.placeholder_text, classes="image-placeholder")
            if self.label_text:
                yield Static(self.label_text, classes="option-label")
            if self.description_text:
                yield Static(self.description_text, classes="option-description")

    def set_selected(self, selected: bool):
        self._selected = selected
        self.set_class(selected, "selected")
        number_widget = self.query_one(".option-number", Static)
        marker = ">" if selected else " "
        number_widget.update(f"{marker}{self.index}.")


class OtherOption(Horizontal):
    """The 'Other' option with text input and file path detection."""

    DEFAULT_CSS = """
    OtherOption {
        height: auto;
        padding: 0 1;
        margin: 0;
    }

    OtherOption.selected {
        background: $primary-darken-2;
    }

    OtherOption .option-number {
        width: 4;
        color: $text-muted;
    }

    OtherOption .other-content {
        width: 1fr;
    }

    OtherOption Input {
        width: 1fr;
        margin-left: 1;
    }

    OtherOption .image-preview {
        color: $success;
        margin-left: 5;
        margin-top: 1;
    }

    OtherOption .reason-input {
        margin-left: 5;
        margin-top: 1;
    }
    """

    def __init__(
        self,
        index: int,
        selected: bool = False,
        allow_image: bool = False,
        show_reason: bool = False,
        **kwargs
    ):
        super().__init__(**kwargs)
        self.index = index
        self._selected = selected
        self.allow_image = allow_image
        self.show_reason = show_reason
        self._detected_image_path: Path | None = None

    def compose(self) -> ComposeResult:
        marker = ">" if self._selected else " "
        yield Static(f"{marker}{self.index}.", classes="option-number")
        with Vertical(classes="other-content"):
            placeholder = "Other (type response or paste image path)" if self.allow_image else "Other (type your response)"
            yield Input(placeholder=placeholder, id="other-input")
            yield Static("", classes="image-preview", id="image-preview")
            if self.show_reason:
                yield Input(placeholder="I prefer this because...", id="reason-input", classes="reason-input")

    def set_selected(self, selected: bool):
        self._selected = selected
        self.set_class(selected, "selected")
        number_widget = self.query_one(".option-number", Static)
        marker = ">" if selected else " "
        number_widget.update(f"{marker}{self.index}.")

    def check_for_image_path(self, text: str, base_path: Path | None = None):
        """Check if input looks like an image path and update preview."""
        from .images import resolve_image_path, get_image_dimensions

        path = resolve_image_path(text, base_path)
        self._detected_image_path = path

        try:
            preview = self.query_one("#image-preview", Static)
            if path:
                dims = get_image_dimensions(path)
                if dims:
                    preview.update(f"[Your Image] ({dims[0]}x{dims[1]}) - {path.name}")
                else:
                    preview.update(f"[Your Image] - {path.name}")
            else:
                preview.update("")
        except Exception:
            pass

    def get_image_path(self) -> Path | None:
        """Get the detected image path if any."""
        return self._detected_image_path


class QuestionPane(TabPane):
    """A single question displayed in a tab pane."""

    DEFAULT_CSS = """
    QuestionPane {
        padding: 1 2;
    }

    QuestionPane .question-text {
        margin-bottom: 1;
    }

    QuestionPane .image-placeholder {
        color: $primary;
        margin: 1 0;
        padding: 0 2;
    }

    QuestionPane .options-container {
        margin-top: 1;
    }

    QuestionPane .multi-hint {
        color: $text-muted;
        margin-bottom: 1;
        text-style: italic;
    }
    """

    def __init__(self, question: "Question", base_path: Path | None = None, **kwargs):
        # Use header as tab title, fallback to truncated question
        title = question.header or question.text[:12]
        super().__init__(title, id=f"pane_{question.id}", **kwargs)
        self.question = question
        self.base_path = base_path
        self.selected_indices: set[int] = set()
        self._other_selected = False

    def compose(self) -> ComposeResult:
        # Question text
        yield Static(self.question.text, classes="question-text")

        # Images as placeholders
        if self.question.images:
            from .images import render_images_for_tui
            placeholders = render_images_for_tui(self.question.images, self.base_path)
            for placeholder in placeholders:
                yield Static(f"  {placeholder}", classes="image-placeholder")

        # Multi-select hint
        if self.question.multi_select:
            yield Static("(Select multiple with Space, Enter to confirm)", classes="multi-hint")

        # Options
        with Vertical(classes="options-container"):
            if self.question.options:
                for i, opt in enumerate(self.question.options, 1):
                    yield OptionItem(
                        index=i,
                        label=opt.label,
                        description=opt.description,
                        id=f"opt_{self.question.id}_{i}"
                    )

            # Always add "Other" option
            other_index = len(self.question.options or []) + 1
            yield OtherOption(
                index=other_index,
                allow_image=self.question.allow_custom_image,
                id=f"other_{self.question.id}"
            )

    def select_option(self, index: int):
        """Select or toggle an option."""
        if self.question.multi_select:
            if index in self.selected_indices:
                self.selected_indices.discard(index)
            else:
                self.selected_indices.add(index)
        else:
            self.selected_indices = {index}
            self._other_selected = False

        self._update_visual_selection()

    def select_other(self):
        """Select the 'Other' option."""
        if not self.question.multi_select:
            self.selected_indices.clear()
        self._other_selected = True
        self._update_visual_selection()

        # Focus the input
        try:
            other_input = self.query_one(f"#other_{self.question.id} Input", Input)
            other_input.focus()
        except Exception:
            pass

    def _update_visual_selection(self):
        """Update visual state of all options."""
        for i in range(1, len(self.question.options or []) + 1):
            try:
                opt = self.query_one(f"#opt_{self.question.id}_{i}", OptionItem)
                opt.set_selected(i in self.selected_indices)
            except Exception:
                pass

        try:
            other = self.query_one(f"#other_{self.question.id}", OtherOption)
            other.set_selected(self._other_selected)
        except Exception:
            pass

    def get_response(self) -> dict | None:
        """Extract response from this pane."""
        if not self.selected_indices and not self._other_selected:
            return None

        if self._other_selected:
            try:
                other_widget = self.query_one(f"#other_{self.question.id}", OtherOption)
                other_input = other_widget.query_one("#other-input", Input)
                other_text = other_input.value.strip()

                if other_text:
                    response = {
                        "decision": "override",
                        "value": other_text,
                        "other_text": other_text,
                    }

                    # Check for custom image
                    image_path = other_widget.get_image_path()
                    if image_path:
                        from .images import create_custom_image_response
                        response["custom_image"] = create_custom_image_response(path=image_path)

                    return response
            except Exception:
                pass
            return None

        # Get selected option labels
        values = []
        for idx in sorted(self.selected_indices):
            if self.question.options and 1 <= idx <= len(self.question.options):
                values.append(self.question.options[idx - 1].label)

        if self.question.multi_select:
            return {"decision": "override", "value": values}
        elif values:
            return {"decision": "override", "value": values[0]}

        return None


class ImageComparePane(TabPane):
    """A question pane for comparing images."""

    DEFAULT_CSS = """
    ImageComparePane {
        padding: 1 2;
    }

    ImageComparePane .question-text {
        margin-bottom: 1;
    }

    ImageComparePane .images-grid {
        margin: 1 0;
    }

    ImageComparePane .options-container {
        margin-top: 1;
    }

    ImageComparePane .custom-image-hint {
        color: $text-muted;
        margin-top: 1;
        text-style: italic;
    }
    """

    def __init__(self, question: "Question", base_path: Path | None = None, **kwargs):
        title = question.header or question.text[:12]
        super().__init__(title, id=f"pane_{question.id}", **kwargs)
        self.question = question
        self.base_path = base_path
        self.selected_index: int | None = None
        self._custom_selected = False

    def compose(self) -> ComposeResult:
        from .images import render_comparison_images_for_tui

        # Question text
        yield Static(self.question.text, classes="question-text")

        # Render comparison images
        with Vertical(classes="options-container"):
            if self.question.comparison_images:
                images_info = render_comparison_images_for_tui(
                    [{"path": img.path, "label": img.label} for img in self.question.comparison_images],
                    self.base_path
                )

                for img_info in images_info:
                    yield ImageOptionItem(
                        index=img_info["index"],
                        label=img_info["label"],
                        placeholder=img_info["placeholder"],
                        id=f"imgopt_{self.question.id}_{img_info['index']}"
                    )

            # Custom image option (always shown for image_compare)
            custom_index = len(self.question.comparison_images or []) + 1
            yield OtherOption(
                index=custom_index,
                allow_image=True,
                show_reason=True,
                id=f"custom_{self.question.id}"
            )

        if self.question.allow_custom_image:
            yield Static(
                "(Paste an image path to provide your own image)",
                classes="custom-image-hint"
            )

    def select_option(self, index: int):
        """Select an image option."""
        self.selected_index = index
        self._custom_selected = False
        self._update_visual_selection()

    def select_custom(self):
        """Select the custom image option."""
        self.selected_index = None
        self._custom_selected = True
        self._update_visual_selection()

        # Focus the input
        try:
            custom_input = self.query_one(f"#custom_{self.question.id} Input", Input)
            custom_input.focus()
        except Exception:
            pass

    def _update_visual_selection(self):
        """Update visual state of all options."""
        if self.question.comparison_images:
            for i in range(1, len(self.question.comparison_images) + 1):
                try:
                    opt = self.query_one(f"#imgopt_{self.question.id}_{i}", ImageOptionItem)
                    opt.set_selected(self.selected_index == i)
                except Exception:
                    pass

        try:
            custom = self.query_one(f"#custom_{self.question.id}", OtherOption)
            custom.set_selected(self._custom_selected)
        except Exception:
            pass

    def get_response(self) -> dict | None:
        """Extract response from this pane."""
        if self.selected_index is None and not self._custom_selected:
            return None

        if self._custom_selected:
            try:
                custom_widget = self.query_one(f"#custom_{self.question.id}", OtherOption)
                path_input = custom_widget.query_one("#other-input", Input)
                path_text = path_input.value.strip()

                reason = ""
                try:
                    reason_input = custom_widget.query_one("#reason-input", Input)
                    reason = reason_input.value.strip()
                except Exception:
                    pass

                if path_text:
                    from .images import create_custom_image_response, resolve_image_path
                    image_path = resolve_image_path(path_text, self.base_path)

                    response = {
                        "decision": "override",
                        "value": "Custom Image",
                        "other_text": path_text,
                    }

                    if image_path:
                        response["custom_image"] = create_custom_image_response(
                            path=image_path,
                            reason=reason
                        )
                    elif reason:
                        response["reason"] = reason

                    return response
            except Exception:
                pass
            return None

        # Selected one of the predefined images
        if self.selected_index and self.question.comparison_images:
            idx = self.selected_index - 1
            if 0 <= idx < len(self.question.comparison_images):
                img = self.question.comparison_images[idx]
                return {
                    "decision": "override",
                    "value": img.label or f"Image {self.selected_index}",
                    "selected_image": {
                        "index": self.selected_index,
                        "path": img.path,
                        "label": img.label,
                    }
                }

        return None


class SubmitPane(TabPane):
    """Final pane for submission."""

    DEFAULT_CSS = """
    SubmitPane {
        padding: 2;
        align: center middle;
    }

    SubmitPane .summary {
        margin-bottom: 2;
    }

    SubmitPane Button {
        margin: 1;
    }
    """

    def __init__(self, **kwargs):
        super().__init__("Submit", id="pane_submit", **kwargs)

    def compose(self) -> ComposeResult:
        yield Static("Review your answers in the tabs above.", classes="summary")
        yield Static("Press Enter or click Submit when ready.", classes="summary")
        with Horizontal():
            yield Button("Submit", id="submit-btn", variant="success")
            yield Button("Cancel", id="cancel-btn", variant="error")


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
                    # Use ImageComparePane for image_compare type
                    if q.type == "image_compare" and q.comparison_images:
                        yield ImageComparePane(q, base_path=self.base_path)
                    else:
                        yield QuestionPane(q, base_path=self.base_path)

                yield SubmitPane()

            yield Static(
                "Enter: select · Space: toggle (multi) · Tab/Shift+Tab: navigate · 1-5: quick select · Esc: cancel",
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
        except Exception:
            pass
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
        except Exception:
            pass

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
        except Exception:
            pass

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
                if isinstance(pane, (QuestionPane, ImageComparePane)):
                    resp = pane.get_response()
                    if resp:
                        self.responses[pane.question.id] = resp
        except Exception:
            pass

    @on(Button.Pressed, "#submit-btn")
    def on_submit(self):
        self._do_submit()

    @on(Button.Pressed, "#cancel-btn")
    def on_cancel(self):
        self.action_cancel()

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
        except Exception:
            pass


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
