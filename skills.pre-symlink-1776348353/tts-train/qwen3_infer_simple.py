#!/usr/bin/env python3
"""qwen3_infer_simple - tts-train.

Purpose: Auto-generated module docstring. Review for accuracy.
Inputs/Outputs/Failures: See functions below.
"""

import os
import sys
import torch
from pathlib import Path

# Add Qwen3-TTS to path
SKILL_DIR = Path(__file__).parent
sys.path.append(str(SKILL_DIR / "Qwen3-TTS"))

from qwen_tts.inference.qwen3_tts_model import Qwen3TTSModel
import soundfile as sf

def synthesize(text: str, output_path: str, model_path: str, speaker: str = "horus"):
    """
    Synthesize speech using Qwen3-TTS 1.7B model.
    """
    print(f"Loading model from {model_path}...")
    
    # Initialize model
    model = Qwen3TTSModel.from_pretrained(
        model_path,
        torch_dtype=torch.bfloat16,
        device_map="auto"
    )
    
    print(f"Synthesizing: '{text[:50]}...'")
    
    # Generate custom voice (for 1.7B trained models)
    # The generate_custom_voice method uses the speaker ID learned during training
    audio_outputs, sample_rate = model.generate_custom_voice(
        text=text,
        speaker=speaker,
        non_streaming_mode=True
    )
    
    # Save output
    if audio_outputs is not None:
        sf.write(output_path, audio_outputs, sample_rate)
        print(f"✓ Saved to {output_path}")
        return True
    else:
        print("✗ Synthesis failed: No audio output.")
        return False

def main(
    text: str = typer.Option(..., help="Text to synthesize"),
    output: str = typer.Option(..., help="Output WAV path"),
    model: str = typer.Option(..., help="Path to checkpoint"),
    speaker: str = typer.Option("horus", help="Speaker name from training"),
) -> None:
    """Qwen3-TTS Inference."""
    success = synthesize(text, output, model, speaker)
    raise SystemExit(0 if success else 1)


if __name__ == "__main__":
    import typer
    typer.run(main)
