"""YuE CLI wrapper — thin entrypoint for Docker-based music generation.

Wraps inference/infer.py with a simpler interface for /create-music integration.
Supports --stage1-only to emit symbolic tokens as JSON without audio rendering.
"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(help="YuE music generation CLI")


@app.command()
def generate(
    lyrics: str = typer.Option(..., help="Path to lyrics file with [Section] markers"),
    genre: str = typer.Option(..., help="Genre/style tags (comma-separated or file path)"),
    out: str = typer.Option(..., help="Output directory for generated audio"),
    stage1_only: bool = typer.Option(False, "--stage1-only", help="Only run Stage 1 (emit symbolic tokens as JSON)"),
    quantization: str = typer.Option("int8", help="Model quantization level (bf16, int8, int4, nf4)"),
    max_tokens: int = typer.Option(3000, "--max-tokens", help="Max new tokens per segment"),
    segments: int = typer.Option(2, help="Number of song sections to generate"),
    seed: Optional[int] = typer.Option(None, help="Random seed for reproducibility"),
    # Audio reference conditioning — the most powerful generation feature
    audio_prompt: Optional[str] = typer.Option(None, "--audio-prompt", help="Path to reference audio clip for timbre/style conditioning"),
    prompt_start: float = typer.Option(0.0, "--prompt-start", help="Start time in seconds for audio prompt extraction"),
    prompt_end: float = typer.Option(30.0, "--prompt-end", help="End time in seconds for audio prompt extraction"),
    # Dual track conditioning — separate vocal and instrumental references (from stems)
    vocal_ref: Optional[str] = typer.Option(None, "--vocal-ref", help="Path to vocal stem reference for vocal timbre conditioning"),
    instrumental_ref: Optional[str] = typer.Option(None, "--instrumental-ref", help="Path to instrumental stem reference for arrangement/timbre conditioning"),
    stage1_model: str = typer.Option("m-a-p/YuE-s1-7B-anneal-en-cot", "--stage1-model"),
    stage2_model: str = typer.Option("m-a-p/YuE-s2-1B-general", "--stage2-model"),
):
    """Generate music from lyrics using YuE 2-stage pipeline.

    Three reference modes:
    - No reference: text-only generation from lyrics + genre
    - Single audio prompt: --audio-prompt FILE (overall style/timbre reference)
    - Dual track prompt: --vocal-ref FILE --instrumental-ref FILE (separate stems)

    Dual track mode is ideal when stems are available from /create-stems — pass
    the vocal stem as vocal reference and the mixed instrumentals as the other.
    """
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write genre to temp file if it's a string (not a file path)
    genre_path = Path(genre)
    if not genre_path.exists():
        genre_path = out_dir / "genre.txt"
        genre_path.write_text(genre)

    cmd = [
        sys.executable, "inference/infer.py",
        "--stage1_model", stage1_model,
        "--stage2_model", stage2_model,
        "--genre_txt", str(genre_path),
        "--lyrics_txt", str(lyrics),
        "--run_n_segments", str(segments),
        "--stage2_batch_size", "4",
        "--output_dir", str(out_dir),
        "--max_new_tokens", str(max_tokens),
        "--quantization_stage1", quantization,
        "--quantization_stage2", quantization,
    ]

    if seed is not None:
        cmd.extend(["--seed", str(seed)])

    # Audio reference conditioning
    if vocal_ref and instrumental_ref:
        # Dual track mode — separate vocal + instrumental stems
        cmd.extend([
            "--use_dual_tracks_prompt",
            "--vocal_track_prompt_path", vocal_ref,
            "--instrumental_track_prompt_path", instrumental_ref,
        ])
        typer.echo(f"[yue_cli] Dual track reference: vocal={vocal_ref}, instrumental={instrumental_ref}", err=True)
    elif audio_prompt:
        # Single audio prompt mode
        cmd.extend([
            "--use_audio_prompt",
            "--audio_prompt_path", audio_prompt,
            "--prompt_start_time", str(prompt_start),
            "--prompt_end_time", str(prompt_end),
        ])
        typer.echo(f"[yue_cli] Audio reference: {audio_prompt} [{prompt_start}s-{prompt_end}s]", err=True)

    if stage1_only:
        cmd.append("--stage1_only")

    typer.echo(f"[yue_cli] Running: {' '.join(cmd)}", err=True)
    result = subprocess.run(cmd, cwd="/workspace/yue")

    if result.returncode != 0:
        typer.echo(f"[yue_cli] infer.py failed with exit code {result.returncode}", err=True)
        raise typer.Exit(result.returncode)

    if stage1_only:
        stage1_dir = out_dir / "stage1"
        if stage1_dir.exists():
            manifest = {
                "type": "stage1_tokens",
                "files": [str(f) for f in sorted(stage1_dir.glob("*.npy"))],
                "model": stage1_model,
                "quantization": quantization,
            }
            (out_dir / "stage1_manifest.json").write_text(json.dumps(manifest, indent=2))
            typer.echo(json.dumps(manifest, indent=2))
        else:
            typer.echo("[yue_cli] WARNING: No stage1 output directory found", err=True)
    else:
        vocoder_dir = out_dir / "vocoder" / "mix"
        outputs = list(vocoder_dir.glob("*.mp3")) + list(vocoder_dir.glob("*.wav")) if vocoder_dir.exists() else []
        manifest = {
            "type": "full_generation",
            "audio_files": [str(f) for f in outputs],
            "model": stage1_model,
            "quantization": quantization,
        }
        (out_dir / "output_manifest.json").write_text(json.dumps(manifest, indent=2))
        typer.echo(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    app()
