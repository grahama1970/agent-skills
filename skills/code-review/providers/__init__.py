"""Provider modules for code-review skill.

Exports common provider functions for convenience.
"""
# Handle both import modes
try:
    from .base import (
        build_provider_cmd,
        find_provider_cli,
        get_provider_model,
        run_provider_async,
    )
    from .github import check_gh_auth
except ImportError:
    from providers.base import (
        build_provider_cmd,
        find_provider_cli,
        get_provider_model,
        run_provider_async,
    )
    from providers.github import check_gh_auth

__all__ = [
    "build_provider_cmd",
    "check_gh_auth",
    "find_provider_cli",
    "get_provider_model",
    "run_provider_async",
]
