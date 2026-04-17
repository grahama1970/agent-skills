"""
VideoRenderer Protocol + Registry

Defines the contract for all video generation backends and provides
a registry/factory for selecting renderers by name.

Usage:
    from core.renderer import get_renderer

    renderer = get_renderer("fal:kling-2.6")
    result = renderer.render_shot("A noir scene", Path("out.mp4"))
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol, runtime_checkable


@dataclass
class RenderResult:
    """Result of a video render operation."""
    success: bool
    output_path: Optional[Path] = None
    error: Optional[str] = None
    cost_estimate: Optional[float] = None  # USD


@runtime_checkable
class VideoRenderer(Protocol):
    """Protocol that all video renderers must satisfy."""

    name: str

    def render_shot(
        self,
        prompt: str,
        output_path: Path,
        duration_s: int = 8,
        aspect_ratio: str = "16:9",
        **kwargs: Any,
    ) -> RenderResult: ...

    def get_capabilities(self) -> dict[str, Any]: ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

RENDERER_REGISTRY: dict[str, type] = {}


def register_renderer(name: str):
    """Decorator to register a renderer class under a given name."""
    def wrapper(cls: type) -> type:
        RENDERER_REGISTRY[name] = cls
        return cls
    return wrapper


def get_renderer(spec: str) -> VideoRenderer:
    """
    Instantiate a renderer from a spec string.

    Formats:
        "veo"              -> VeoRenderer()
        "fal:kling-2.6"    -> FalRenderer(model="kling-2.6")
        "fal:hailuo-std"   -> FalRenderer(model="hailuo-std")
        "none"             -> NullRenderer()
    """
    if spec == "none":
        return NullRenderer()

    if ":" in spec:
        backend, model = spec.split(":", 1)
    else:
        backend, model = spec, None

    if backend not in RENDERER_REGISTRY:
        available = list(RENDERER_REGISTRY.keys()) + ["none"]
        raise ValueError(
            f"Unknown renderer: {backend!r}. "
            f"Available: {available}"
        )

    cls = RENDERER_REGISTRY[backend]
    return cls(model=model) if model else cls()


def list_renderers() -> list[dict[str, Any]]:
    """Return info about all registered renderers."""
    info = []
    for name, cls in RENDERER_REGISTRY.items():
        entry: dict[str, Any] = {"name": name, "class": cls.__name__}
        if hasattr(cls, "MODELS"):
            entry["models"] = list(cls.MODELS.keys())
        info.append(entry)
    # Always include "none"
    info.append({"name": "none", "class": "NullRenderer", "models": []})
    return info


# ---------------------------------------------------------------------------
# NullRenderer (--renderer none)
# ---------------------------------------------------------------------------

@register_renderer("null")
class NullRenderer:
    """No-op renderer for dry runs and testing."""

    name = "none"

    def __init__(self, model: str | None = None):
        self.model = model

    def render_shot(
        self,
        prompt: str,
        output_path: Path,
        duration_s: int = 8,
        aspect_ratio: str = "16:9",
        **kwargs: Any,
    ) -> RenderResult:
        return RenderResult(success=True, output_path=None)

    def get_capabilities(self) -> dict[str, Any]:
        return {"type": "null", "durations": [], "aspect_ratios": []}
