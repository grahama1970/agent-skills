"""Stage 0 runtime for the monitor-opportunities skill."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("monitor-opportunities")
except PackageNotFoundError:  # pragma: no cover - source checkout fallback
    __version__ = "0.1.0"

__all__ = ["__version__"]
