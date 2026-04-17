"""
TogetherRenderer: Video generation via Together AI REST API.

Supports multiple video models through pay-as-you-go pricing.
Cost depends on model, resolution, and duration.

Usage:
    renderer = TogetherRenderer(model="seedance-lite")
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

# Poll configuration
POLL_INTERVAL_SECONDS = 10
MAX_POLL_SECONDS = 600  # 10 minutes max wait

TOGETHER_API_BASE = "https://api.together.xyz/v2"

# Aspect ratio → (width, height) mapping.
# Must use Together AI supported resolutions.
# Smaller resolutions to keep costs down for research.
ASPECT_RATIO_SIZES: dict[str, tuple[int, int]] = {
    "16:9": (1248, 704),
    "9:16": (704, 1248),
    "1:1": (960, 960),
}

# Together AI video models and their parameters.
# optional_params: kwarg keys this model accepts beyond the required set
# (model, prompt, seconds, width, height are always sent).
TOGETHER_MODELS: dict[str, dict[str, Any]] = {
    "seedance-lite": {
        "model_id": "ByteDance/Seedance-1.0-lite",
        "default_duration": 5,
        "valid_durations": [5, 10],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "optional_params": ["seed", "fps"],
    },
    "seedance-pro": {
        "model_id": "ByteDance/Seedance-1.0-pro",
        "default_duration": 5,
        "valid_durations": [5, 10],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "optional_params": ["seed", "fps"],
    },
    "pixverse-v5": {
        "model_id": "pixverse/pixverse-v5",
        "default_duration": 5,
        "valid_durations": [5, 8],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "optional_params": ["seed"],
    },
    "hailuo-02": {
        "model_id": "minimax/hailuo-02",
        "default_duration": 6,
        "valid_durations": [5, 6],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "optional_params": ["seed"],
    },
    "wan2.2": {
        "model_id": "Wan-AI/Wan2.2-T2V-A14B",
        "default_duration": 5,
        "valid_durations": [5],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "optional_params": ["seed", "steps", "guidance_scale", "negative_prompt"],
    },
    "kling-2.1-std": {
        "model_id": "kwaivgI/kling-2.1-standard",
        "default_duration": 5,
        "valid_durations": [5, 10],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "optional_params": ["seed", "negative_prompt"],
    },
    "kling-2.1-pro": {
        "model_id": "kwaivgI/kling-2.1-pro",
        "default_duration": 5,
        "valid_durations": [5, 10],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "optional_params": ["seed", "negative_prompt"],
    },
    "veo-3": {
        "model_id": "google/veo-3.0-fast",
        "default_duration": 8,
        "valid_durations": [5, 8],
        "aspect_ratios": ["16:9", "9:16", "1:1"],
        "optional_params": ["seed"],
    },
}


def _get_together_key() -> str:
    """Get TOGETHER_API_KEY from environment."""
    key = os.environ.get("TOGETHER_API_KEY")
    if not key:
        raise ValueError(
            "TOGETHER_API_KEY not set. Get your key at https://api.together.xyz/settings/api-keys"
        )
    return key


@register_renderer("together")
class TogetherRenderer:
    """Together AI video renderer supporting Seedance, PixVerse, Hailuo, Kling, Veo, Wan."""

    MODELS = TOGETHER_MODELS

    def __init__(self, model: str | None = None):
        self.model_key = model or "seedance-lite"
        if self.model_key not in TOGETHER_MODELS:
            available = list(TOGETHER_MODELS.keys())
            raise ValueError(
                f"Unknown Together model: {self.model_key!r}. Available: {available}"
            )
        self.model_config = TOGETHER_MODELS[self.model_key]
        self.model_id = self.model_config["model_id"]
        self.name = f"together:{self.model_key}"

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
            f"[cyan]Submitting to Together AI ({self.model_key}, "
            f"{clamped_duration}s, {aspect_ratio})...[/cyan]"
        )

        # Retry loop
        backoff = INITIAL_BACKOFF_SECONDS
        video_url: str | None = None
        actual_cost: float | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                video_url, actual_cost = self._submit_and_poll(
                    prompt, clamped_duration, aspect_ratio, **kwargs
                )
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

        if not video_url:
            return RenderResult(
                success=False,
                error="No video URL returned from Together AI",
            )

        # Download the video
        try:
            self._download_video(video_url, output_path)
        except Exception as e:
            return RenderResult(success=False, error=f"Download failed: {e}")

        if output_path.exists() and output_path.stat().st_size > 0:
            console.print(
                f"[green]Saved: {output_path.name} "
                f"(cost: ${actual_cost:.3f})[/green]"
                if actual_cost
                else f"[green]Saved: {output_path.name}[/green]"
            )
            return RenderResult(
                success=True,
                output_path=output_path,
                cost_estimate=actual_cost,
            )
        return RenderResult(success=False, error="Downloaded file is empty")

    def _submit_and_poll(
        self,
        prompt: str,
        duration: int,
        aspect_ratio: str,
        **kwargs: Any,
    ) -> tuple[str | None, float | None]:
        """Submit video job to Together AI and poll until complete.

        Returns (video_url, actual_cost) tuple.
        """
        api_key = _get_together_key()
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        # Resolve resolution from aspect ratio
        width, height = ASPECT_RATIO_SIZES.get(aspect_ratio, (1366, 768))

        # Build payload with model + required params
        payload: dict[str, Any] = {
            "model": self.model_id,
            "prompt": prompt,
            "seconds": duration,
            "width": width,
            "height": height,
        }

        # Pass through only params this specific model supports
        allowed = self.model_config.get("optional_params", [])
        for key in allowed:
            if key in kwargs:
                payload[key] = kwargs[key]

        resp = httpx.post(
            f"{TOGETHER_API_BASE}/videos",
            json=payload,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        job = resp.json()
        job_id = job.get("id")

        if not job_id:
            raise ValueError(f"No job ID in response: {job}")

        console.print(f"[dim]  Job submitted: {job_id}[/dim]")

        # Check if already complete (some fast models)
        if job.get("status") == "completed":
            url = self._extract_video_url(job)
            cost = self._extract_cost(job)
            return url, cost

        # Poll for completion
        elapsed = 0
        while elapsed < MAX_POLL_SECONDS:
            time.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS

            status_resp = httpx.get(
                f"{TOGETHER_API_BASE}/videos/{job_id}",
                headers=headers,
                timeout=30,
            )
            status_resp.raise_for_status()
            status_data = status_resp.json()

            status = status_data.get("status", "unknown")
            console.print(f"[dim]  Status: {status} ({elapsed}s elapsed)[/dim]")

            if status == "completed":
                url = self._extract_video_url(status_data)
                cost = self._extract_cost(status_data)
                return url, cost
            elif status == "failed":
                # Error can be in info.errors or top-level error
                info = status_data.get("info", {})
                error = info.get("errors") or status_data.get("error", "Unknown error")
                raise RuntimeError(f"Together AI job failed: {error}")

        raise TimeoutError(
            f"Together AI job {job_id} did not complete within {MAX_POLL_SECONDS}s"
        )

    def _extract_video_url(self, data: dict) -> str | None:
        """Extract video URL from Together AI response."""
        outputs = data.get("outputs", {})
        if isinstance(outputs, dict):
            url = outputs.get("video_url")
            if url:
                return url
        return None

    def _extract_cost(self, data: dict) -> float | None:
        """Extract actual cost from Together AI response."""
        outputs = data.get("outputs", {})
        if isinstance(outputs, dict):
            cost = outputs.get("cost")
            if cost is not None:
                return float(cost)
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
            "type": "together",
            "model": self.model_key,
            "model_id": self.model_id,
            "durations": self.model_config["valid_durations"],
            "aspect_ratios": self.model_config["aspect_ratios"],
        }
