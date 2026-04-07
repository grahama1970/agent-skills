"""Reusable TUI widgets for the Interview skill.

Contains:
- OptionItem: A single numbered option with label and description
- ImageOptionItem: An image option for image_compare questions
- OtherOption: The 'Other' option with text input and file path detection
"""
from __future__ import annotations

from pathlib import Path

from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Input
from textual.app import ComposeResult
from loguru import logger


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
        except Exception as e:
            logger.debug("update failed: {}", e)

    def get_image_path(self) -> Path | None:
        """Get the detected image path if any."""
        return self._detected_image_path
