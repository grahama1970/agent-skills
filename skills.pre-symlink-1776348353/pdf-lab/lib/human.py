"""Human-in-the-loop escalation for pdf-lab convergence.

Re-exports from submodules for backward compatibility:
- ``human_escalation``: Interactive escalation (interview, screenshots, bbox)
- ``human_deferred``: Batch-mode deferred question/answer books

See each submodule's docstring for details.
"""

from __future__ import annotations

# --- Interactive escalation (human_escalation.py) ---
from .human_escalation import (  # noqa: F401
    HumanGuidance,
    INTERVIEW_SKILL,
    PDF_SCREENSHOT_SKILL,
    STALL_ITERATIONS,
    MIN_DELTA_IMPROVEMENT,
    should_escalate,
    escalate_to_human,
    apply_human_guidance,
)

# --- Deferred / batch mode (human_deferred.py) ---
from .human_deferred import (  # noqa: F401
    DeferredQuestion,
    DEFAULT_BOOK_DIR,
    defer_question,
    load_question_book,
    build_batch_interview,
    run_batch_interview,
    save_answer_book,
    load_answer_book,
    lookup_guidance,
    clear_question_book,
)

__all__ = [
    # Escalation
    "HumanGuidance",
    "INTERVIEW_SKILL",
    "PDF_SCREENSHOT_SKILL",
    "STALL_ITERATIONS",
    "MIN_DELTA_IMPROVEMENT",
    "should_escalate",
    "escalate_to_human",
    "apply_human_guidance",
    # Deferred
    "DeferredQuestion",
    "DEFAULT_BOOK_DIR",
    "defer_question",
    "load_question_book",
    "build_batch_interview",
    "run_batch_interview",
    "save_answer_book",
    "load_answer_book",
    "lookup_guidance",
    "clear_question_book",
]
