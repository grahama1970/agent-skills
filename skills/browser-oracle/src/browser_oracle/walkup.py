"""Directory walk-up discovery for `.ask/browser-oracles.yaml`.

Mirrors python-dotenv's parent-chain search: start at cwd (or a given path),
walk toward filesystem root, return the nearest registry file found.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RegistryHit:
    """A discovered registry file and the directory it applies to."""

    registry_path: Path
    registry_root: Path


def _normalize_start(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.is_file():
        return resolved.parent
    return resolved


def find_registry(
    start: Path | str,
    *,
    container_dir: str | None = None,
    filename: str | None = None,
    stop_at: Path | str | None = None,
) -> RegistryHit | None:
    """Walk from ``start`` toward root; return nearest ``.ask/browser-oracles.yaml``.

    Args:
        start: File or directory to begin the search from.
        container_dir: Subdirectory holding the registry (default: ``.ask``).
        filename: Registry filename (default: ``browser-oracles.yaml``).
        stop_at: Optional boundary; do not search above this directory.

    Returns:
        ``RegistryHit`` when a registry file exists, else ``None``.
    """
    container = container_dir or os.environ.get("BROWSER_ORACLE_REGISTRY_DIR", ".ask")
    fname = filename or os.environ.get(
        "BROWSER_ORACLE_REGISTRY_FILENAME", "browser-oracles.yaml"
    )
    current = _normalize_start(Path(start))
    boundary = _normalize_start(Path(stop_at)) if stop_at else None
    filesystem_root = current.anchor and Path(current.anchor) or Path("/")

    while True:
        candidate = current / container / fname
        if candidate.is_file():
            return RegistryHit(registry_path=candidate, registry_root=current)
        if boundary is not None and current == boundary:
            return None
        if current == filesystem_root or current.parent == current:
            return None
        current = current.parent


def find_all_registries(
    start: Path | str,
    *,
    container_dir: str | None = None,
    filename: str | None = None,
    stop_at: Path | str | None = None,
) -> list[RegistryHit]:
    """Collect every registry on the walk-up chain (child-nearest first)."""
    container = container_dir or os.environ.get("BROWSER_ORACLE_REGISTRY_DIR", ".ask")
    fname = filename or os.environ.get(
        "BROWSER_ORACLE_REGISTRY_FILENAME", "browser-oracles.yaml"
    )
    current = _normalize_start(Path(start))
    boundary = _normalize_start(Path(stop_at)) if stop_at else None
    filesystem_root = current.anchor and Path(current.anchor) or Path("/")
    hits: list[RegistryHit] = []

    while True:
        candidate = current / container / fname
        if candidate.is_file():
            hits.append(RegistryHit(registry_path=candidate, registry_root=current))
        if boundary is not None and current == boundary:
            break
        if current == filesystem_root or current.parent == current:
            break
        current = current.parent
    return hits
