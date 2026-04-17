"""Composable pane registry for the Interview skill.

Allows consuming skills (pdf-lab, table-lab, etc.) to register custom
HTML and TUI pane renderers for their own question types without modifying
interview core code.

Usage from a consuming skill::

    from interview.registry import register_html_pane

    def my_renderer(question, base_path=None):
        return "<div>custom html</div>"

    register_html_pane("my_custom_type", my_renderer)
"""
from __future__ import annotations

from typing import Any, Callable, Protocol, runtime_checkable
from pathlib import Path


@runtime_checkable
class HtmlPaneRenderer(Protocol):
    """Protocol for HTML pane renderers.

    A callable that takes a question dict and optional base_path,
    and returns an HTML string for the question pane.
    """

    def __call__(self, question: dict, base_path: Path | None = None) -> str: ...


@runtime_checkable
class TuiPaneFactory(Protocol):
    """Protocol for TUI pane factories.

    A callable that takes a Question object and optional base_path,
    and returns a TabPane widget instance.
    """

    def __call__(self, question: Any, base_path: Path | None = None) -> Any: ...


# Global registries
_html_renderers: dict[str, HtmlPaneRenderer] = {}
_tui_factories: dict[str, TuiPaneFactory] = {}


def register_html_pane(question_type: str, renderer: HtmlPaneRenderer) -> None:
    """Register an HTML pane renderer for a question type."""
    _html_renderers[question_type] = renderer


def register_tui_pane(question_type: str, factory: TuiPaneFactory) -> None:
    """Register a TUI pane factory for a question type."""
    _tui_factories[question_type] = factory


def get_html_renderer(question_type: str) -> HtmlPaneRenderer | None:
    """Get the registered HTML renderer for a question type, or None."""
    return _html_renderers.get(question_type)


def get_tui_factory(question_type: str) -> TuiPaneFactory | None:
    """Get the registered TUI pane factory for a question type, or None."""
    return _tui_factories.get(question_type)


def register_builtin_panes() -> None:
    """Register built-in pane renderers (image_compare, bbox_annotation)."""
    from .bbox_pane import generate_bbox_annotation_pane, create_bbox_tui_pane

    register_html_pane("bbox_annotation", generate_bbox_annotation_pane)
    register_tui_pane("bbox_annotation", create_bbox_tui_pane)
