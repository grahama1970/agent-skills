"""Safe filesystem and YAML boundary functions.

All user-authored YAML is loaded with ``safe_load`` and immediately validated through
Pydantic. Paths use ``pathlib``. Errors propagate to the thin CLI, which logs them and
returns a non-zero exit status.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import SCENE_ADAPTER, Scene, Theme


def skill_root() -> Path:
    """Return the skill source root when run through the repository's uv project."""

    return Path(__file__).resolve().parents[2]


def load_yaml(path: Path) -> dict[str, Any]:
    """Load one YAML mapping without constructing arbitrary Python objects."""

    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"expected a YAML mapping: {path}")
    return raw


def resolve_theme_path(theme_ref: str, base_dir: Path | None = None) -> Path:
    """Resolve a bundled theme name or an explicit path."""

    candidate = Path(theme_ref)
    if candidate.suffix in {".yml", ".yaml"} or candidate.is_absolute() or "/" in theme_ref:
        if not candidate.is_absolute() and base_dir is not None:
            candidate = base_dir / candidate
        return candidate.resolve()
    return (skill_root() / "references" / "themes" / f"{theme_ref}.yml").resolve()


def load_theme(theme_ref: str, base_dir: Path | None = None) -> Theme:
    """Load and validate a theme."""

    path = resolve_theme_path(theme_ref, base_dir)
    return Theme.model_validate(load_yaml(path))


def load_scene(path: Path) -> Scene:
    """Load and validate a discriminated scene model."""

    return SCENE_ADAPTER.validate_python(load_yaml(path))


def template_path(name: str) -> Path:
    """Return the path to a bundled semantic template."""

    path = skill_root() / "assets" / "templates" / f"{name}.yml"
    if not path.exists():
        raise ValueError(f"unknown template: {name}")
    return path


def available_templates() -> tuple[str, ...]:
    """List bundled template names deterministically."""

    directory = skill_root() / "assets" / "templates"
    return tuple(path.stem for path in sorted(directory.glob("*.yml")))
