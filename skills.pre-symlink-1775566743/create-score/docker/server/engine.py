"""
ACE-Step Engine Adapter.

Wraps the ACE-Step model for generation.
Handles model loading, inference, and output formatting.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import soundfile as sf
import torch
from loguru import logger

# Try to import ACE-Step
try:
    from ace_step import ACEStep
    ACE_STEP_AVAILABLE = True
except ImportError:
    ACE_STEP_AVAILABLE = False
    logger.warning("ACE-Step not available, using mock engine")


@dataclass
class GenerationParams:
    """Parameters for music generation."""

    prompt: str
    tags: Optional[str] = None
    lyrics: Optional[str] = None
    instrumental: bool = True
    duration_s: float = 30.0
    steps: int = 27
    seed: int = -1
    cfg_scale: float = 4.0
    format: str = "wav"
    reference_audio_path: Optional[Path] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class ACEStepEngine:
    """ACE-Step generation engine."""

    def __init__(self, output_dir: Path = Path("/app/outputs")):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.model: Optional[Any] = None
        self._loaded = False

    def load(self) -> None:
        """Load the ACE-Step model."""
        if self._loaded:
            logger.info("Model already loaded")
            return

        logger.info("Loading ACE-Step model...")

        if ACE_STEP_AVAILABLE:
            try:
                # Initialize ACE-Step with appropriate settings for A5000
                self.model = ACEStep(
                    device="cuda" if torch.cuda.is_available() else "cpu",
                    dtype=torch.float16,  # Use FP16 for A5000
                )
                self._loaded = True
                logger.info("ACE-Step model loaded successfully")
            except Exception as e:
                logger.error("Failed to load ACE-Step: {}", e)
                raise
        else:
            logger.warning("Using mock engine (ACE-Step not installed)")
            self._loaded = True

    def is_ready(self) -> bool:
        """Check if model is loaded and ready."""
        return self._loaded

    def generate(self, params: GenerationParams) -> Path:
        """
        Generate music from parameters.

        Returns path to generated audio file.
        """
        if not self._loaded:
            self.load()

        # Determine seed
        seed = params.seed if params.seed >= 0 else torch.randint(0, 2**32, (1,)).item()

        # Generate unique output filename
        output_id = str(uuid.uuid4())[:8]
        output_filename = f"score_{output_id}_{seed}.{params.format}"
        output_path = self.output_dir / output_filename

        logger.info(
            "Generating: prompt='{}...', duration={}s, steps={}, seed={}",
            params.prompt[:50], params.duration_s, params.steps, seed
        )

        if ACE_STEP_AVAILABLE and self.model is not None:
            try:
                # Set seed for reproducibility
                torch.manual_seed(seed)

                # Build generation kwargs
                gen_kwargs = {
                    "prompt": params.prompt,
                    "duration": params.duration_s,
                    "num_inference_steps": params.steps,
                    "guidance_scale": params.cfg_scale,
                }

                # Add optional parameters
                if params.tags:
                    gen_kwargs["tags"] = params.tags
                if params.lyrics and not params.instrumental:
                    gen_kwargs["lyrics"] = params.lyrics
                if params.reference_audio_path and params.reference_audio_path.exists():
                    gen_kwargs["reference_audio"] = str(params.reference_audio_path)

                # Generate
                audio = self.model.generate(**gen_kwargs)

                # Save output
                sample_rate = getattr(self.model, "sample_rate", 44100)
                sf.write(str(output_path), audio, sample_rate)

                logger.info("Generated: {} ({} bytes)", output_path, output_path.stat().st_size)

            except Exception as e:
                logger.error("Generation failed: {}", e)
                raise
        else:
            # Mock generation for testing
            self._mock_generate(params, output_path, seed)

        return output_path

    def _mock_generate(self, params: GenerationParams, output_path: Path, seed: int) -> None:
        """Generate mock audio for testing when ACE-Step is not available."""
        import numpy as np

        logger.warning("Using mock generation (ACE-Step not available)")

        # Generate simple sine wave as placeholder
        sample_rate = 44100
        duration = params.duration_s
        t = np.linspace(0, duration, int(sample_rate * duration), dtype=np.float32)

        # Create a simple chord based on seed
        np.random.seed(seed)
        freqs = [220 * (2 ** (i / 12)) for i in np.random.choice(range(12), 3, replace=False)]
        audio = np.zeros_like(t)
        for freq in freqs:
            audio += 0.3 * np.sin(2 * np.pi * freq * t)

        # Apply envelope
        envelope = np.minimum(t / 0.5, 1.0) * np.minimum((duration - t) / 0.5, 1.0)
        audio *= envelope

        # Normalize
        audio = audio / np.max(np.abs(audio)) * 0.8

        # Save
        sf.write(str(output_path), audio, sample_rate)
        logger.info("Mock generated: {} ({} bytes)", output_path, output_path.stat().st_size)


# Singleton instance
_engine: Optional[ACEStepEngine] = None


def get_engine() -> ACEStepEngine:
    """Get or create the singleton engine instance."""
    global _engine
    if _engine is None:
        output_dir = Path(os.environ.get("OUTPUT_DIR", "/app/outputs"))
        _engine = ACEStepEngine(output_dir=output_dir)
    return _engine
