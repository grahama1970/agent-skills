"""CLI command implementations for code-review skill.

All commands are exported from submodules for use in code_review.py
"""
# Handle both import modes
try:
    from .basic import check, login, models, template
    from .build import build
    from .bundle import bundle, find
    from .review import review
    from .review_full import review_full
    from .loop import loop
except ImportError:
    from commands.basic import check, login, models, template
    from commands.build import build
    from commands.bundle import bundle, find
    from commands.review import review
    from commands.review_full import review_full
    from commands.loop import loop

__all__ = [
    "build",
    "bundle",
    "check",
    "find",
    "login",
    "loop",
    "models",
    "review",
    "review_full",
    "template",
]
