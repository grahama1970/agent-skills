"""
FalRenderer: Unified video generation via fal.ai gateway.

Supports multiple video models through a single API:
- Kling v2.6 Pro / v2.1 Pro
- Hailuo (MiniMax) Standard / Pro

Usage:
    renderer = FalRenderer(model="kling-2.6")
    result = renderer.render_shot("A noir scene", Path("out.mp4"), duration_s=5)
"""

from __future__ import annotations

import os
import time
import httpx
from pathlib import Path
from typing import Any

from rich.console import Console

from .renderer import RenderResult, register_renderer

console = Console()

# Retry configuration
MAX_RETRIES = 3
INITIAL_BACKOFF_SECONDS = 30
MAX_BACKOFF_SECONDS = 300


# fal.ai model IDs and their parameters
FAL_MODELS: dict[str, dict[str, Any]] = {
    "kling-2.6": {
        "app_id": "fal-ai/kling-video/v2.6/pro/text-to-video",
        "cost_per_second": 0.07,
        "default_duration": 5,
        "valid_durations": [5, 10],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
    },
    "kling-2.1": {
        "app_id": "fal-ai/kling-video/v2.1/pro/text-to-video",
        "cost_per_second": 0.07,
        "default_duration": 5,
        "valid_durations": [5, 10],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
    },
    "hailuo-std": {
        "app_id": "fal-ai/minimax/hailuo-02/standard/text-to-video",
        "cost_per_second": 0.045,
        "default_duration": 6,
        "valid_durations": [5, 6],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
    },
    "hailuo-pro": {
        "app_id": "fal-ai/minimax/hailuo-02/pro/text-to-video",
        "cost_per_second": 0.08,
        "default_duration": 6,
        "valid_durations": [5, 6],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
    },
}


def _get_fal_key() -> str:
    """Get FAL_KEY from environment."""
    key = os.environ.get("FAL_KEY")
    if not key:
        raise ValueError(
            "FAL_KEY not set. Get your key at https://fal.ai/dashboard/keys"
        )
    return key


@register_renderer("fal")
class FalRenderer:
    """fal.ai unified video renderer supporting Kling and Hailuo/MiniMax."""

    MODELS = FAL_MODELS

    def __init__(self, model: str | None = None):
        self.model_key = model or "kling-2.6"
        if self.model_key not in FAL_MODELS:
            available = list(FAL_MODELS.keys())
            raise ValueError(
                f"Unknown fal model: {self.model_key!r}. Available: {available}"
            )
        self.model_config = FAL_MODELS[self.model_key]
        self.app_id = self.model_config["app_id"]
        self.name = f"fal:{self.model_key}"

    def render_shot(
        self,
        prompt: str,
        output_path: Path,
        duration_s: int = 8,
        aspect_ratio: str = "16:9",
        **kwargs: Any,
    ) -> RenderResult:
        output_path = Path(output_path)

        # Clamp duration to valid values for this model
        valid_durations = self.model_config["valid_durations"]
        clamped_duration = min(valid_durations, key=lambda d: abs(d - duration_s))

        console.print(
            f"[cyan]Submitting to fal.ai ({self.model_key}, "
            f"{clamped_duration}s, {aspect_ratio})...[/cyan]"
        )

        # Build request arguments
        arguments: dict[str, Any] = {
            "prompt": prompt,
            "duration": clamped_duration,
            "aspect_ratio": aspect_ratio,
        }

        # Retry loop
        backoff = INITIAL_BACKOFF_SECONDS
        for attempt in range(MAX_RETRIES + 1):
            try:
                result = self._submit_and_wait(arguments)
                break
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate" in error_str.lower():
                    if attempt < MAX_RETRIES:
                        console.print(
                            f"[yellow]Rate limited. Waiting {backoff}s "
                            f"before retry {attempt + 1}/{MAX_RETRIES}...[/yellow]"
                        )
                        time.sleep(backoff)
                        backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                        continue
                    return RenderResult(
                        success=False,
                        error=f"Rate limited after {MAX_RETRIES} retries",
                    )
                return RenderResult(success=False, error=str(e))

        # Extract video URL from result
        video_url = self._extract_video_url(result)
        if not video_url:
            return RenderResult(
                success=False,
                error=f"No video URL in response: {result}",
            )

        # Download the video
        try:
            self._download_video(video_url, output_path)
        except Exception as e:
            return RenderResult(success=False, error=f"Download failed: {e}")

        if output_path.exists() and output_path.stat().st_size > 0:
            cost = clamped_duration * self.model_config["cost_per_second"]
            console.print(f"[green]Saved: {output_path.name}[/green]")
            return RenderResult(
                success=True,
                output_path=output_path,
                cost_estimate=cost,
            )
        return RenderResult(success=False, error="Downloaded file is empty")

    def _submit_and_wait(self, arguments: dict[str, Any]) -> dict:
        """Submit job to fal.ai and wait for completion using subscribe()."""
        import fal_client

        def on_queue_update(update):
            if isinstance(update, fal_client.InProgress):
                console.print("[dim]  fal.ai: generating...[/dim]")

        result = fal_client.subscribe(
            self.app_id,
            arguments=arguments,
            with_logs=False,
            on_queue_update=on_queue_update,
        )
        return result

    def _extract_video_url(self, result: dict) -> str | None:
        """Extract video download URL from fal.ai response."""
        # Common response format: {"video": {"url": "..."}}
        if isinstance(result, dict):
            video = result.get("video")
            if isinstance(video, dict):
                return video.get("url")
            # Some models return at top level
            if "url" in result:
                return result["url"]
        return None

    def _download_video(self, url: str, output_path: Path) -> None:
        """Download video file from URL."""
        console.print(f"[dim]Downloading to {output_path.name}...[/dim]")
        with httpx.stream("GET", url, timeout=120) as r:
            r.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in r.iter_bytes(chunk_size=8192):
                    f.write(chunk)

    def get_capabilities(self) -> dict[str, Any]:
        return {
            "type": "fal",
            "model": self.model_key,
            "app_id": self.app_id,
            "durations": self.model_config["valid_durations"],
            "aspect_ratios": self.model_config["aspect_ratios"],
            "cost_per_second": self.model_config["cost_per_second"],
        }
