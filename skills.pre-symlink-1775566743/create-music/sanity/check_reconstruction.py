#!/usr/bin/env python3
"""
Check that stems sum to approximately the original mix.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import typer
from rich.console import Console

app = typer.Typer()
console = Console()


def resample_audio(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Resample audio to target sample rate using scipy."""
    if orig_sr == target_sr:
        return audio
    from scipy.signal import resample

    ratio = target_sr / orig_sr
    if audio.ndim == 1:
        new_len = int(len(audio) * ratio)
        return resample(audio, new_len)
    else:
        # Multi-channel: resample each channel
        new_len = int(audio.shape[0] * ratio)
        return np.column_stack(
            [resample(audio[:, ch], new_len) for ch in range(audio.shape[1])]
        )


def calculate_sdr(reference: np.ndarray, estimate: np.ndarray) -> float:
    """Calculate Signal-to-Distortion Ratio in dB."""
    # Ensure same shape
    min_len = min(len(reference), len(estimate))
    reference = reference[:min_len]
    estimate = estimate[:min_len]

    # Handle stereo by averaging channels
    if reference.ndim > 1:
        reference = reference.mean(axis=1)
    if estimate.ndim > 1:
        estimate = estimate.mean(axis=1)

    noise = reference - estimate
    signal_power = np.sum(reference ** 2)
    noise_power = np.sum(noise ** 2)

    if noise_power < 1e-10:
        return float('inf')

    return 10 * np.log10(signal_power / noise_power)


@app.command()
def check(
    mix: Path = typer.Option(..., "--mix", "-m", help="Original mix audio file"),
    stems: Path = typer.Option(
        ..., "--stems", "-s", help="Directory containing stem files"
    ),
    threshold: float = typer.Option(
        10.0, "--threshold", "-t", help="Minimum SDR in dB"
    ),
):
    """Check that sum(stems) = mix (reconstruction quality)."""
    if not mix.exists():
        console.print(f"[red]Mix file not found: {mix}[/red]")
        raise typer.Exit(code=1)

    if not stems.exists():
        console.print(f"[red]Stems directory not found: {stems}[/red]")
        raise typer.Exit(code=1)

    # Load mix
    mix_audio, sr = sf.read(str(mix))
    console.print(f"[blue]Mix: {mix.name}, SR={sr}, shape={mix_audio.shape}[/blue]")

    # Load and sum stems
    stem_files = sorted(stems.glob("*.wav"))
    if not stem_files:
        console.print(f"[red]No .wav files found in {stems}[/red]")
        raise typer.Exit(code=1)

    console.print(f"[blue]Found {len(stem_files)} stems[/blue]")

    summed = None
    for f in stem_files:
        audio, stem_sr = sf.read(str(f))
        console.print(f"  - {f.name}: shape={audio.shape}")

        if stem_sr != sr:
            console.print(
                f"[yellow]Resampling {f.name} from {stem_sr} to {sr}[/yellow]"
            )
            audio = resample_audio(audio, stem_sr, sr)

        if summed is None:
            summed = audio.copy()
        else:
            # Handle potential length mismatch
            min_len = min(len(summed), len(audio))
            summed = summed[:min_len] + audio[:min_len]

    if summed is None:
        console.print("[red]No stems loaded[/red]")
        raise typer.Exit(code=1)

    # Calculate SDR
    sdr = calculate_sdr(mix_audio, summed)
    console.print(f"\n[bold]Reconstruction SDR: {sdr:.2f} dB[/bold]")

    if sdr >= threshold:
        console.print(
            f"[green]PASS: SDR {sdr:.2f} >= {threshold} dB threshold[/green]"
        )
    else:
        console.print(
            f"[red]FAIL: SDR {sdr:.2f} < {threshold} dB threshold[/red]"
        )
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
