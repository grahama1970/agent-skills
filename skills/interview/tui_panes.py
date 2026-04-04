"""Tab pane widgets for the Interview TUI.

Contains:
- QuestionPane: A single question displayed in a tab pane
- ImageComparePane: A question pane for comparing images
- SubmitPane: Final pane for submission
"""
from __future__ import annotations

from pathlib import Path

from textual.containers import Vertical, Horizontal
from textual.widgets import Static, Button, Input, TabPane
from textual.app import ComposeResult

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .interview import Question

from .tui_widgets import OptionItem, ImageOptionItem, OtherOption
from loguru import logger


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

    QuestionPane .code-block {
        background: $surface;
        color: $text;
        padding: 1 2;
        margin: 1 0;
        border: tall $primary;
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

        # Code block (v2.3)
        if self.question.code_block:
            lang = self.question.code_lang or ""
            code_text = f"```{lang}\n{self.question.code_block}\n```"
            yield Static(code_text, classes="code-block")

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
        except Exception as e:
            logger.debug("widget focus failed: {}", e)

    def _update_visual_selection(self):
        """Update visual state of all options."""
        for i in range(1, len(self.question.options or []) + 1):
            try:
                opt = self.query_one(f"#opt_{self.question.id}_{i}", OptionItem)
                opt.set_selected(i in self.selected_indices)
            except Exception as e:
                logger.debug("widget update failed: {}", e)

        try:
            other = self.query_one(f"#other_{self.question.id}", OtherOption)
            other.set_selected(self._other_selected)
        except Exception as e:
            logger.debug("widget update failed: {}", e)

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
            except Exception as e:
                logger.debug("value lookup failed: {}", e)
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
        except Exception as e:
            logger.debug("widget focus failed: {}", e)

    def _update_visual_selection(self):
        """Update visual state of all options."""
        if self.question.comparison_images:
            for i in range(1, len(self.question.comparison_images) + 1):
                try:
                    opt = self.query_one(f"#imgopt_{self.question.id}_{i}", ImageOptionItem)
                    opt.set_selected(self.selected_index == i)
                except Exception as e:
                    logger.debug("widget update failed: {}", e)

        try:
            custom = self.query_one(f"#custom_{self.question.id}", OtherOption)
            custom.set_selected(self._custom_selected)
        except Exception as e:
            logger.debug("widget update failed: {}", e)

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
                except Exception as e:
                    logger.debug("value extraction failed: {}", e)

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
            except Exception as e:
                logger.debug("value lookup failed: {}", e)
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


class BboxAnnotationPane(TabPane):
    """TUI fallback pane for bbox annotation questions.

    Shows pre-annotations as a numbered list with accept/reject toggles.
    Type annotation indices into the delete input to reject specific items.
    Use --mode html for full interactive canvas.
    """

    DEFAULT_CSS = """
    BboxAnnotationPane {
        padding: 1 2;
    }

    BboxAnnotationPane .question-text {
        margin-bottom: 1;
    }

    BboxAnnotationPane .bbox-hint {
        color: $warning;
        margin: 1 0;
        text-style: italic;
    }

    BboxAnnotationPane .ann-list {
        margin-top: 1;
    }

    BboxAnnotationPane .ann-item {
        padding: 0 2;
    }

    BboxAnnotationPane .ann-item-rejected {
        padding: 0 2;
        color: $text-muted;
        text-style: strike;
    }

    BboxAnnotationPane .delete-hint {
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
        self.rejected_indices: set[int] = set()

    def compose(self) -> ComposeResult:
        yield Static(self.question.text, classes="question-text")

        # Image placeholder
        if self.question.images:
            from .images import render_images_for_tui
            placeholders = render_images_for_tui(self.question.images, self.base_path)
            for placeholder in placeholders:
                yield Static(f"  {placeholder}", classes="image-placeholder")

        yield Static(
            "Use --mode html for full interactive bbox annotation canvas.",
            classes="bbox-hint",
        )

        # Pre-annotations list
        pre_annotations = self.question.pre_annotations or []
        if pre_annotations:
            yield Static(f"Pre-annotations ({len(pre_annotations)}):", classes="ann-list")
            for i, ann in enumerate(pre_annotations, 1):
                ann_type = ann.get("type", "?")
                bbox = ann.get("bbox", [0, 0, 0, 0])
                page = ann.get("page", 0)
                yield Static(
                    f"  {i}. [{ann_type}] bbox=[{bbox[0]:.0f}, {bbox[1]:.0f}, "
                    f"{bbox[2]:.0f}, {bbox[3]:.0f}] page={page}",
                    classes="ann-item",
                    id=f"bbox_ann_{self.question.id}_{i}",
                )
            yield Static(
                "  Type indices to reject (e.g. '1,3' to delete annotations 1 and 3):",
                classes="delete-hint",
            )
            yield Input(
                placeholder="Indices to delete (e.g. 1,3)",
                id=f"bbox_delete_{self.question.id}",
            )
        else:
            yield Static("  No pre-annotations.", classes="ann-item")

    def _parse_rejected(self) -> set[int]:
        """Parse the delete input for rejected annotation indices."""
        try:
            delete_input = self.query_one(
                f"#bbox_delete_{self.question.id}", Input
            )
            text = delete_input.value.strip()
            if not text:
                return set()
            indices = set()
            for part in text.replace(" ", ",").split(","):
                part = part.strip()
                if part.isdigit():
                    indices.add(int(part))
            return indices
        except Exception:
            return set()

    def get_response(self) -> dict | None:
        """Return annotations with rejected items marked as deleted."""
        pre_annotations = self.question.pre_annotations or []
        if not pre_annotations:
            return None

        rejected = self._parse_rejected()

        annotations = []
        for i, ann in enumerate(pre_annotations, 1):
            action = "delete" if i in rejected else "keep"
            annotations.append({
                "action": action,
                "type": ann.get("type", "?"),
                "bbox": ann.get("bbox", [0, 0, 0, 0]),
                "page": ann.get("page", 0),
            })

        has_changes = len(rejected) > 0
        return {
            "decision": "override" if has_changes else "accept",
            "value": "bbox_annotations",
            "annotations": annotations,
            "render_dpi": self.question.render_dpi,
        }


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
