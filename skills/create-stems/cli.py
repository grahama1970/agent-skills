"""
create-stems CLI

Audio stem separation using Demucs' Python API entrypoint.
Default model: htdemucs_6s (6-source: vocals/drums/bass/other/guitar/piano).

Uses demucs.separate.main() for clean in-process execution.
"""
from __future__ import annotations

import json
import os
import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

app = typer.Typer(add_completion=False, help="Audio stem separation (Demucs + UVR)")

# ---------------------------------------------------------------------------
# Instrument → Demucs source mapping
# ---------------------------------------------------------------------------
# When a caller says "I want the oud", this maps it to the closest Demucs
# source.  htdemucs_6s sources: vocals, drums, bass, other, guitar, piano.
# htdemucs sources: vocals, drums, bass, other.

INSTRUMENT_MAP_6S: dict[str, str] = {
    # Direct source names
    "vocals": "vocals",
    "voice": "vocals",
    "singing": "vocals",
    "drums": "drums",
    "percussion": "drums",
    "bass": "bass",
    "bass guitar": "bass",
    "upright bass": "bass",
    "guitar": "guitar",
    "electric guitar": "guitar",
    "acoustic guitar": "guitar",
    "oud": "guitar",
    "lute": "guitar",
    "banjo": "guitar",
    "mandolin": "guitar",
    "ukulele": "guitar",
    "sitar": "guitar",
    "bouzouki": "guitar",
    "charango": "guitar",
    "piano": "piano",
    "keyboard": "piano",
    "keys": "piano",
    "organ": "piano",
    "synth": "piano",
    "synthesizer": "piano",
    "harpsichord": "piano",
    "accordion": "piano",
    "harmonium": "piano",
    # Everything else falls to "other"
    "other": "other",
    "strings": "other",
    "violin": "other",
    "cello": "other",
    "viola": "other",
    "trumpet": "other",
    "saxophone": "other",
    "flute": "other",
    "clarinet": "other",
    "horn": "other",
    "brass": "other",
    "woodwind": "other",
    "harmonica": "other",
    "fiddle": "other",
    "pedal steel": "other",
}

INSTRUMENT_MAP_4S: dict[str, str] = {
    "vocals": "vocals",
    "voice": "vocals",
    "singing": "vocals",
    "drums": "drums",
    "percussion": "drums",
    "bass": "bass",
    "bass guitar": "bass",
    "upright bass": "bass",
}
# Everything else maps to "other" for 4-stem

VALID_SOURCES_6S = {"vocals", "drums", "bass", "other", "guitar", "piano"}
VALID_SOURCES_4S = {"vocals", "drums", "bass", "other"}


def resolve_instrument(instrument: str, model: str) -> str:
    """Map a natural instrument name to the best Demucs source for --two-stems."""
    key = instrument.lower().strip()

    if "6s" in model:
        if key in VALID_SOURCES_6S:
            return key
        mapped = INSTRUMENT_MAP_6S.get(key)
        if mapped:
            if mapped != key:
                logger.info("Mapped '{}' → '{}' (closest 6-stem source)", key, mapped)
            return mapped
        logger.warning("Unknown instrument '{}', falling back to 'other'", key)
        return "other"
    else:
        if key in VALID_SOURCES_4S:
            return key
        mapped = INSTRUMENT_MAP_4S.get(key)
        if mapped:
            if mapped != key:
                logger.info("Mapped '{}' → '{}' (closest 4-stem source)", key, mapped)
            return mapped
        logger.warning("Unknown instrument '{}' for 4-stem model, falling back to 'other'", key)
        return "other"


# ---------------------------------------------------------------------------
# Config + helpers
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DemucsRunConfig:
    model: str
    device: str
    out_dir: Path
    two_stems: Optional[str]
    mp3: bool
    segment: Optional[int]
    overlap: Optional[float]
    shifts: Optional[int]
    jobs: Optional[int]
    clip_mode: Optional[str]
    no_cuda_mem_caching: bool


def _validate_inputs(audio_path: Path) -> None:
    if not audio_path.exists():
        raise FileNotFoundError(f"Input not found: {audio_path}")
    if audio_path.is_dir():
        raise ValueError(f"Expected a file, got a directory: {audio_path}")


def _build_demucs_args(audio_path: Path, cfg: DemucsRunConfig) -> list[str]:
    args: list[str] = []

    args += ["-n", cfg.model]
    args += ["-d", cfg.device]
    args += ["-o", str(cfg.out_dir)]

    if cfg.two_stems:
        args += ["--two-stems", cfg.two_stems]
    if cfg.mp3:
        args += ["--mp3"]
    if cfg.segment is not None:
        args += ["--segment", str(cfg.segment)]
    if cfg.overlap is not None:
        args += ["--overlap", str(cfg.overlap)]
    if cfg.shifts is not None:
        args += ["--shifts", str(cfg.shifts)]
    if cfg.jobs is not None:
        args += ["-j", str(cfg.jobs)]
    if cfg.clip_mode is not None:
        args += ["--clip-mode", cfg.clip_mode]

    args += [str(audio_path)]
    return args


def _run_demucs(args: list[str], no_cuda_mem_caching: bool) -> int:
    if no_cuda_mem_caching:
        os.environ["PYTORCH_NO_CUDA_MEMORY_CACHING"] = "1"
        logger.info("Set PYTORCH_NO_CUDA_MEMORY_CACHING=1")

    logger.info("demucs.separate.main({})", " ".join(shlex.quote(a) for a in args))

    try:
        import demucs.separate  # type: ignore

        try:
            demucs.separate.main(args)
            return 0
        except SystemExit as e:
            code = int(e.code) if isinstance(e.code, int) else 1
            if code != 0:
                logger.error("Demucs exited with code {}", code)
            return code
    except ImportError:
        logger.error("demucs not installed. Run: uv sync")
        return 1
    except Exception:
        logger.exception("Demucs failed")
        return 1


def _count_stems(out_dir: Path, model: str) -> dict[str, int]:
    """Walk the output directory and count produced stem files."""
    counts: dict[str, int] = {}
    model_dir = out_dir / model
    if not model_dir.exists():
        return counts
    for track_dir in model_dir.iterdir():
        if track_dir.is_dir():
            for stem_file in track_dir.iterdir():
                if stem_file.suffix in (".wav", ".mp3"):
                    name = stem_file.stem
                    counts[name] = counts.get(name, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

@app.command()
def separate(
    mix: Path = typer.Option(..., "--mix", "-m", help="Path to an audio file (mp3/wav/flac/etc)."),
    out: Path = typer.Option(Path("./separated"), "--out", "-o", help="Output root directory."),
    model: str = typer.Option(
        "htdemucs_6s",
        "--model",
        "-n",
        help="Demucs model name. htdemucs_6s (6 sources) or htdemucs (4 sources).",
    ),
    device: str = typer.Option("cuda", "--device", "-d", help="cuda or cpu."),
    instrument: Optional[str] = typer.Option(
        None,
        "--instrument",
        "-i",
        help=(
            "Extract a specific instrument/voice. Natural names accepted: "
            "vocals, guitar, oud, piano, drums, bass, etc. "
            "Automatically mapped to the closest Demucs source via --two-stems."
        ),
    ),
    two_stems: Optional[str] = typer.Option(
        None,
        "--two-stems",
        help="Raw Demucs --two-stems value (use --instrument for natural names).",
    ),
    mp3: bool = typer.Option(False, "--mp3", help="Write stems as MP3 (otherwise WAV)."),
    segment: Optional[int] = typer.Option(
        None, "--segment", help="Split size (seconds) for VRAM control. Try 8-12 for low VRAM.",
    ),
    overlap: Optional[float] = typer.Option(
        None, "--overlap", help="Overlap between windows (default 0.25). Reduce for speed.",
    ),
    shifts: Optional[int] = typer.Option(
        None, "--shifts", help="Random time-shifts to average. Higher = better quality, slower.",
    ),
    jobs: Optional[int] = typer.Option(
        None, "--jobs", "-j", help="Parallel jobs (increases RAM proportionally).",
    ),
    clip_mode: Optional[str] = typer.Option(
        None, "--clip-mode", help="Clipping mode. Use 'clamp' for hard clipping.",
    ),
    no_cuda_mem_caching: bool = typer.Option(
        False, "--no-cuda-mem-caching", help="Set PYTORCH_NO_CUDA_MEMORY_CACHING=1 for low VRAM.",
    ),
    with_audio_separator: bool = typer.Option(
        False, "--with-audio-separator", help="Also run UVR models for ensemble comparison.",
    ),
) -> None:
    """Separate an audio file into stems using Demucs."""
    _validate_inputs(mix)
    out.mkdir(parents=True, exist_ok=True)

    # Resolve --instrument to --two-stems
    resolved_two_stems = two_stems
    if instrument and not two_stems:
        resolved_two_stems = resolve_instrument(instrument, model)
        logger.info("Instrument '{}' → --two-stems {}", instrument, resolved_two_stems)

    cfg = DemucsRunConfig(
        model=model,
        device=device,
        out_dir=out,
        two_stems=resolved_two_stems,
        mp3=mp3,
        segment=segment,
        overlap=overlap,
        shifts=shifts,
        jobs=jobs,
        clip_mode=clip_mode,
        no_cuda_mem_caching=no_cuda_mem_caching,
    )

    args = _build_demucs_args(mix, cfg)
    exit_code = _run_demucs(args, cfg.no_cuda_mem_caching)

    if exit_code != 0:
        logger.error("Demucs separation failed (exit code {})", exit_code)
        raise typer.Exit(code=exit_code)

    # Validation gate: verify stems were produced
    stem_counts = _count_stems(out, model)
    if not stem_counts:
        logger.error("No stems produced in {}/{}/", out, model)
        raise typer.Exit(code=1)

    logger.info("Stems produced: {}", dict(stem_counts))

    # Optionally run UVR models for ensemble
    if with_audio_separator:
        _run_uvr(mix, out)

    # Write manifest
    manifest = {
        "mix": str(mix.resolve()),
        "model": model,
        "device": device,
        "two_stems": resolved_two_stems,
        "instrument": instrument,
        "stems": stem_counts,
        "out_dir": str(out.resolve()),
        "mp3": mp3,
    }
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    logger.info("Manifest: {}", manifest_path)


def _run_uvr(mix: Path, out: Path) -> None:
    """Run audio-separator (UVR models) as an ensemble candidate."""
    try:
        from audio_separator.separator import Separator  # type: ignore
    except ImportError:
        logger.warning("audio-separator not installed. Install with: uv sync --extra uvr")
        return

    uvr_out = out / "uvr"
    uvr_out.mkdir(parents=True, exist_ok=True)

    logger.info("Running audio-separator (UVR)...")
    separator = Separator(output_dir=str(uvr_out))
    separator.load_model()
    separator.separate(str(mix))
    logger.info("UVR output: {}", uvr_out)


if __name__ == "__main__":
    app()
