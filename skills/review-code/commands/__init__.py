"""CLI command implementations for code-review skill."""

try:
    from .basic import check, login, models, template  # noqa: F401
    from .build import build  # noqa: F401
    from .bundle import bundle  # noqa: F401
    from .find import find  # noqa: F401
    from .review import review  # noqa: F401
    from .review_full import review_full  # noqa: F401
    from .loop import loop  # noqa: F401
except ImportError:
    from commands.basic import check, login, models, template  # noqa: F401
    from commands.build import build  # noqa: F401
    from commands.bundle import bundle  # noqa: F401
    from commands.find import find  # noqa: F401
    from commands.review import review  # noqa: F401
    from commands.review_full import review_full  # noqa: F401
    from commands.loop import loop  # noqa: F401
