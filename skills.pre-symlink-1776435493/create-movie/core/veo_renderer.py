"""
VeoRenderer: Google Veo video generation backend.

Wraps the existing veo_client.VeoClient to satisfy the VideoRenderer protocol.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

from rich.console import Console

from .renderer import RenderResult, register_renderer

console = Console()

# Ensure skill root is on path so veo_client can be imported
_SKILL_DIR = Path(__file__).parent.parent
if str(_SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(_SKILL_DIR))


@register_renderer("veo")
class VeoRenderer:
    """Google Veo video renderer (wraps veo_client.VeoClient)."""

    name = "veo"

    MODELS = {
        "veo-3.1": "veo-3.1-generate-preview",
    }

    def __init__(self, model: str | None = None):
        from veo_client import VeoClient
        self.client = VeoClient()
        self.model = model or "veo-3.1-generate-preview"

    def render_shot(
        self,
        prompt: str,
        output_path: Path,
        duration_s: int = 8,
        aspect_ratio: str = "16:9",
        **kwargs: Any,
    ) -> RenderResult:
        output_path = Path(output_path)
        url = self.client.generate_video(
            prompt,
            model=self.model,
            duration=str(duration_s),
        )
        if url:
            self.client.download_video(url, str(output_path))
            if output_path.exists() and output_path.stat().st_size > 0:
                return RenderResult(
                    success=True,
                    output_path=output_path,
                    cost_estimate=duration_s * 0.40,
                )
            return RenderResult(success=False, error="Download produced empty file")
        return RenderResult(success=False, error="Veo generation returned no URL")

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "type": "veo",
            "durations": [4, 6, 8],
            "aspect_ratios": ["16:9", "9:16", "1:1"],
            "cost_per_second": 0.40,
        }
