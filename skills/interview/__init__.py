"""Interview Skill - Structured human-agent Q&A via HTML or TUI forms."""
from .interview import Interview, Question, Response, Session, load_questions_file
from .registry import register_html_pane, register_tui_pane, register_builtin_panes

# Register built-in pane renderers (bbox_annotation, etc.)
register_builtin_panes()

__all__ = [
    "Interview",
    "Question",
    "Response",
    "Session",
    "load_questions_file",
    "register_html_pane",
    "register_tui_pane",
]
