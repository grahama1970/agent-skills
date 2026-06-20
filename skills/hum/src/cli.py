#!/usr/bin/env python3
"""CLI for /hum skill — persona humming pipeline."""

from __future__ import annotations

import json
import os
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from .cache import HumCache
from .defaults import DEFAULT_DIFFUSION_STEPS, DEFAULT_SOURCE_HUM_RENDERER
from .decompose import decompose_audio_dataset, decompose_audio_to_hum
from .female_humming_dataset import build_female_humming_dataset, build_humtrans_pair_manifest, ingest_humtrans
from .pipeline import HumPipeline
from .pitch_correction import pitch_correct_guide
from .sample_renderer import render_female_hum
from .score_omr import score_to_midi
from .techsinger_export import export_techsinger_smoke, validate_techsinger_smoke
from .timbre_model import render_trained_hum, train_hum_timbre_model
from .train_control_dataset import build_train_control_dataset
from .neural_hum_renderer import evaluate_hum_render, render_neural_hum, train_neural_hum_renderer

app = typer.Typer(help="Persona humming pipeline")
console = Console()

DEFAULT_PERSONA = "embry"


@app.command()
def decompose(
    audio: Path = typer.Argument(..., help="Local audio file to decompose"),
    out_dir: Path = typer.Option(Path("/tmp/hum_decompose"), help="Output artifact directory"),
    sample_rate: int = typer.Option(22050, help="Analysis/render sample rate"),
    max_duration: Optional[float] = typer.Option(None, help="Maximum seconds to analyze"),
    transcribe: bool = typer.Option(False, help="Try Whisper transcript/word timestamps and approximate phonemes"),
    whisper_model: str = typer.Option("base", help="Whisper model when --transcribe is enabled"),
    language: Optional[str] = typer.Option(None, help="Whisper language code, e.g. en"),
    device: Optional[str] = typer.Option(None, help="Whisper device, e.g. cuda or cpu"),
    phoneme_language: str = typer.Option("en-us", help="phonemizer/espeak language"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Extract melody/cadence JSON and render a neutral closed-mouth hum."""
    result = decompose_audio_to_hum(
        audio,
        out_dir,
        sr=sample_rate,
        max_duration_s=max_duration,
        transcribe=transcribe,
        whisper_model=whisper_model,
        language=language,
        device=device,
        phoneme_language=phoneme_language,
    )
    payload = result.to_dict()
    if output_json:
        print(json.dumps({"status": "ok", **payload}, indent=2))
    else:
        console.print(f"[green]Decomposed:[/green] {audio}")
        console.print(f"  Melody:      {payload['melody_json']}")
        console.print(f"  Cadence:     {payload['cadence_json']}")
        console.print(f"  Sound:       {payload['sound_json']}")
        console.print(f"  Text:        {payload['text_json']}")
        console.print(f"  Neutral hum: {payload['neutral_hum_wav']}")
        console.print(f"  Duration:    {payload['duration_s']}s")
        console.print(f"  Voiced:      {payload['voiced_ratio']}")
        console.print(f"  Onsets:      {payload['onset_count']}")


@app.command("decompose-dataset")
def decompose_dataset(
    input_path: Path = typer.Argument(..., help="Audio file or directory of audio files"),
    out_dir: Path = typer.Option(Path("/tmp/hum_dataset_decompose"), help="Output dataset artifact directory"),
    sample_rate: int = typer.Option(22050, help="Analysis/render sample rate"),
    limit: Optional[int] = typer.Option(None, help="Maximum audio files to process"),
    max_duration: Optional[float] = typer.Option(None, help="Maximum seconds to analyze per file"),
    transcribe: bool = typer.Option(False, help="Try Whisper transcript/word timestamps and approximate phonemes"),
    whisper_model: str = typer.Option("base", help="Whisper model when --transcribe is enabled"),
    language: Optional[str] = typer.Option(None, help="Whisper language code, e.g. en"),
    device: Optional[str] = typer.Option(None, help="Whisper device, e.g. cuda or cpu"),
    phoneme_language: str = typer.Option("en-us", help="phonemizer/espeak language"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Batch extract pitch, cadence, sound/phoneme-proxy, and neutral hum artifacts."""
    result = decompose_audio_dataset(
        input_path,
        out_dir,
        sr=sample_rate,
        limit=limit,
        max_duration_s=max_duration,
        transcribe=transcribe,
        whisper_model=whisper_model,
        language=language,
        device=device,
        phoneme_language=phoneme_language,
    )
    if output_json:
        print(json.dumps({"status": "ok", **result}, indent=2))
    else:
        console.print(f"[green]Dataset decomposed:[/green] {input_path}")
        console.print(f"  Index:  {result['index_json']}")
        console.print(f"  Clips:  {result['count']}")
        console.print(f"  Errors: {result['error_count']}")


@app.command("decompose-youtube")
def decompose_youtube(
    url: str = typer.Argument(..., help="YouTube URL, playlist, or album"),
    out_dir: Path = typer.Option(Path("/tmp/hum_youtube_decompose"), help="Output artifact directory"),
    sample_rate: int = typer.Option(22050, help="Analysis/render sample rate"),
    limit: Optional[int] = typer.Option(None, help="Maximum downloaded entries to process"),
    max_duration: Optional[float] = typer.Option(None, help="Maximum seconds to analyze per downloaded file"),
    transcribe: bool = typer.Option(False, help="Try Whisper transcript/word timestamps and approximate phonemes"),
    whisper_model: str = typer.Option("base", help="Whisper model when --transcribe is enabled"),
    language: Optional[str] = typer.Option(None, help="Whisper language code, e.g. en"),
    device: Optional[str] = typer.Option(None, help="Whisper device, e.g. cuda or cpu"),
    phoneme_language: str = typer.Option("en-us", help="phonemizer/espeak language"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Download YouTube audio with yt-dlp, then batch decompose it."""
    import shutil
    import subprocess

    if not shutil.which("yt-dlp"):
        raise typer.BadParameter("yt-dlp is required for decompose-youtube")

    source_dir = out_dir / "source_audio"
    source_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "yt-dlp",
        "--yes-playlist",
        "--extract-audio",
        "--audio-format",
        "wav",
        "--audio-quality",
        "0",
        "-o",
        str(source_dir / "%(playlist_index)s-%(title).200B.%(ext)s"),
    ]
    if limit is not None:
        cmd.extend(["--max-downloads", str(limit)])
    cmd.append(url)
    completed = subprocess.run(cmd, check=False, capture_output=output_json, text=True)
    downloaded = list(source_dir.rglob("*.wav"))
    if completed.returncode not in {0, 101} and not downloaded:
        raise typer.Exit(completed.returncode)

    result = decompose_audio_dataset(
        source_dir,
        out_dir / "decomposition",
        sr=sample_rate,
        limit=limit,
        max_duration_s=max_duration,
        transcribe=transcribe,
        whisper_model=whisper_model,
        language=language,
        device=device,
        phoneme_language=phoneme_language,
    )
    result = {"source_audio_dir": str(source_dir), **result}
    if output_json:
        print(json.dumps({"status": "ok", **result}, indent=2))
    else:
        console.print(f"[green]YouTube audio decomposed:[/green] {url}")
        console.print(f"  Source audio: {source_dir}")
        console.print(f"  Index:        {result['index_json']}")
        console.print(f"  Clips:        {result['count']}")
        console.print(f"  Errors:       {result['error_count']}")


@app.command("build-female-humming-dataset")
def build_female_humming_dataset_cmd(
    youtube_url: list[str] = typer.Option(
        None, "--youtube-url", help="YouTube video, playlist, or album URL to include"
    ),
    out_dir: Path = typer.Option(Path("/tmp/female_humming_dataset"), help="Output dataset directory"),
    include_hf_tiny: bool = typer.Option(True, help="Include Hugging Face ylacombe/tiny-humming"),
    include_humtrans_metadata: bool = typer.Option(True, help="Record HumTrans supervised melody source metadata"),
    female_only: bool = typer.Option(True, help="Filter HF rows to descriptions containing female/woman"),
    youtube_limit: Optional[int] = typer.Option(None, help="Maximum YouTube entries per URL"),
    sample_rate: int = typer.Option(22050, help="Analysis/render sample rate"),
    max_duration: Optional[float] = typer.Option(60.0, help="Maximum seconds to analyze per file"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Collect female humming sources from HF/YouTube and decompose them."""
    manifest = build_female_humming_dataset(
        out_dir,
        youtube_urls=youtube_url or [],
        include_hf_tiny=include_hf_tiny,
        female_only=female_only,
        youtube_limit=youtube_limit,
        include_humtrans_metadata=include_humtrans_metadata,
        quiet_youtube=output_json,
    )
    source_dir = out_dir / "source_audio"
    decomposition = decompose_audio_dataset(
        source_dir,
        out_dir / "decomposition",
        sr=sample_rate,
        max_duration_s=max_duration,
    )
    result = {"source_manifest": manifest, "decomposition": decomposition}
    if output_json:
        print(json.dumps({"status": "ok", **result}, indent=2))
    else:
        console.print(f"[green]Female humming dataset ready:[/green] {out_dir}")
        console.print(f"  Source manifest: {manifest['manifest_json']}")
        console.print(f"  Source clips:     {manifest['count']}")
        console.print(f"  Decomposition:    {decomposition['index_json']}")
        console.print(f"  Decomposed clips: {decomposition['count']}")
        console.print(f"  Errors:           {decomposition['error_count']}")


@app.command("ingest-humtrans")
def ingest_humtrans_cmd(
    out_dir: Path = typer.Option(Path("/mnt/storage12tb/datasets/humtrans"), help="Output HumTrans dataset dir"),
    download_wav: bool = typer.Option(False, help="Download the 14.7GB all_wav.zip archive"),
    extract: bool = typer.Option(False, help="Extract downloaded zip files"),
    extract_limit: Optional[int] = typer.Option(None, help="Optional max files to extract from each zip"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Download HumTrans MIDI/splits and optionally the full WAV archive."""
    result = ingest_humtrans(
        out_dir,
        download_wav=download_wav,
        extract=extract,
        extract_limit=extract_limit,
    )
    if output_json:
        print(json.dumps({"status": "ok", **result}, indent=2))
    else:
        console.print(f"[green]HumTrans ingested:[/green] {out_dir}")
        console.print(f"  Manifest: {result['manifest_json']}")
        console.print(f"  MIDI zip: {result['downloads']['midi_zip']}")
        console.print(f"  Splits:   {result['downloads']['splits_json']}")
        console.print(f"  WAV zip:  {result['downloads']['wav_zip']}")


@app.command("build-humtrans-pairs")
def build_humtrans_pairs_cmd(
    humtrans_dir: Path = typer.Option(Path("/mnt/storage12tb/datasets/humtrans"), help="HumTrans dataset dir"),
    output_jsonl: Optional[Path] = typer.Option(None, help="Output JSONL manifest path"),
    female_only: bool = typer.Option(True, help="Keep only Fxx HumTrans keys"),
    require_wav: bool = typer.Option(True, help="Require all_wav.zip and matching WAV members"),
    limit: Optional[int] = typer.Option(None, help="Optional maximum pair rows"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Build a HumTrans WAV/MIDI pair manifest for renderer training."""
    result = build_humtrans_pair_manifest(
        humtrans_dir,
        output_jsonl=output_jsonl,
        female_only=female_only,
        require_wav=require_wav,
        limit=limit,
    )
    if output_json:
        print(json.dumps({"status": "ok", **result}, indent=2))
    else:
        console.print(f"[green]HumTrans pair manifest:[/green] {result['pairs_jsonl']}")
        console.print(f"  Pairs:      {result['count']}")
        console.print(f"  Splits:     {result['split_counts']}")
        console.print(f"  MIDI files: {result['midi_member_count']}")
        console.print(f"  WAV files:  {result['wav_member_count']}")


@app.command("train-control-dataset")
def train_control_dataset_cmd(
    pairs_jsonl: Path = typer.Option(..., help="HumTrans pair JSONL manifest"),
    out_dir: Path = typer.Option(Path("/mnt/storage12tb/datasets/hum_mvp/controls"), help="Output controls dir"),
    train_limit: Optional[int] = typer.Option(1024, help="Maximum train rows"),
    valid_limit: Optional[int] = typer.Option(128, help="Maximum valid rows"),
    test_limit: Optional[int] = typer.Option(128, help="Maximum test rows"),
    sample_rate: int = typer.Option(22050, help="Audio sample rate for extracted WAV clips"),
    max_duration: Optional[float] = typer.Option(14.0, help="Maximum seconds per extracted WAV"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Extract a bounded HumTrans WAV/MIDI control dataset for renderer training."""
    result = build_train_control_dataset(
        pairs_jsonl,
        out_dir,
        train_limit=train_limit,
        valid_limit=valid_limit,
        test_limit=test_limit,
        sample_rate=sample_rate,
        max_duration_s=max_duration,
    )
    payload = result.to_dict()
    if output_json:
        print(json.dumps({"status": "ok", **payload}, indent=2))
    else:
        console.print(f"[green]Control dataset ready:[/green] {payload['manifest_json']}")
        console.print(f"  Train: {payload['train_count']}")
        console.print(f"  Valid: {payload['valid_count']}")
        console.print(f"  Test:  {payload['test_count']}")


@app.command("export-techsinger-smoke")
def export_techsinger_smoke_cmd(
    controls_manifest: Path = typer.Option(..., help="Control dataset manifest.json"),
    out_dir: Path = typer.Option(
        Path("/mnt/storage12tb/datasets/hum_mvp/techsinger_smoke"),
        help="Output TechSinger-compatible processed data dir",
    ),
    limit: Optional[int] = typer.Option(None, help="Optional maximum control rows to export"),
    sample_rate: int = typer.Option(22050, help="Export WAV/F0 sample rate"),
    hop_length: int = typer.Option(256, help="F0 hop length in samples"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Export a bounded control dataset into TechSinger-compatible smoke metadata."""
    result = export_techsinger_smoke(
        controls_manifest,
        out_dir,
        limit=limit,
        sample_rate=sample_rate,
        hop_length=hop_length,
    )
    payload = result.to_dict()
    if output_json:
        print(json.dumps({"status": "ok", **payload}, indent=2))
    else:
        console.print(f"[green]TechSinger smoke export:[/green] {payload['metadata_json']}")
        console.print(f"  Items:      {payload['item_count']}")
        console.print(f"  Errors:     {payload['error_count']}")
        console.print(f"  Validation: {payload['validation_json']}")


@app.command("validate-techsinger-smoke")
def validate_techsinger_smoke_cmd(
    out_dir: Path = typer.Option(
        Path("/mnt/storage12tb/datasets/hum_mvp/techsinger_smoke"),
        help="TechSinger-compatible processed data dir",
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Validate TechSinger smoke metadata, WAVs, F0 sidecars, and control lengths."""
    result = validate_techsinger_smoke(out_dir)
    payload = result.to_dict()
    if output_json:
        print(json.dumps({"status": "ok", **payload}, indent=2))
    else:
        color = "green" if payload["error_count"] == 0 else "red"
        console.print(f"[{color}]TechSinger smoke validation:[/{color}] {payload['validation_json']}")
        console.print(f"  Items:    {payload['item_count']}")
        console.print(f"  Errors:   {payload['error_count']}")
        console.print(f"  Warnings: {payload['warning_count']}")
        console.print(f"  Glissando mask present: {payload['has_glissando']}")
    if result.error_count:
        raise typer.Exit(2)


@app.command("score-to-midi")
def score_to_midi_cmd(
    score: Path = typer.Argument(..., help="Score PDF/image or MusicXML file"),
    out_dir: Path = typer.Option(Path("/tmp/hum_score_to_midi"), help="Output directory"),
    backend: str = typer.Option(
        "auto", help="OMR backend: auto, musicxml, audiveris, musescore, or melogen"
    ),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Convert sheet music to MIDI for melody-controlled humming."""
    result = score_to_midi(score, out_dir, backend=backend)  # type: ignore[arg-type]
    payload = result.to_dict()
    if output_json:
        print(json.dumps(payload, indent=2))
    else:
        color = "green" if result.status == "ok" else "yellow"
        console.print(f"[{color}]Score-to-MIDI {result.status}:[/{color}] {result.message}")
        console.print(f"  Manifest: {result.manifest_json}")
        console.print(f"  MusicXML: {result.musicxml_path}")
        console.print(f"  MIDI:     {result.midi_path}")
    if result.status != "ok":
        raise typer.Exit(2)


@app.command("render-female-hum")
def render_female_hum_cmd(
    dataset_index: Path = typer.Option(
        Path("/tmp/female-humming-dataset/decomposition/index.json"),
        help="Decomposition index from build-female-humming-dataset",
    ),
    out_dir: Path = typer.Option(Path("/tmp/female-hum-render-mvp"), help="Output render artifact directory"),
    melody_json: Optional[Path] = typer.Option(None, help="Optional melody JSON with notes"),
    midi: Optional[Path] = typer.Option(None, help="Optional MIDI melody source"),
    max_melody_duration: Optional[float] = typer.Option(None, help="Maximum seconds to render from MIDI melody"),
    midi_track_name: Optional[str] = typer.Option(None, help="Preferred MIDI track/instrument name substring"),
    midi_legato: bool = typer.Option(True, help="Extend MIDI note durations toward the next note for hum phrasing"),
    midi_min_note_duration: float = typer.Option(
        0.18, help="Collapse faster MIDI ornaments into notes at least this long"
    ),
    midi_tempo_bpm: Optional[float] = typer.Option(None, help="Retempo MIDI melody to this BPM before rendering"),
    midi_swing_ratio: float = typer.Option(0.0, help="Swing offbeat eighths, e.g. 0.6667 for 2:1 swing"),
    sample_rate: int = typer.Option(22050, help="Render sample rate"),
    carrier: str = typer.Option("original", help="Carrier source: original or neutral"),
    transpose: float = typer.Option(0.0, help="Transpose rendered melody in semitones"),
    tone: str = typer.Option("neutral", help="Post tone: neutral, dark, or low_breathy"),
    rest: float = typer.Option(0.06, help="Default rest between sequential notes without explicit starts"),
    min_sample_duration: float = typer.Option(0.25, help="Minimum voiced source sample duration in seconds"),
    max_samples: int = typer.Option(512, help="Maximum voiced source samples to index"),
    min_stretch_ratio: float = typer.Option(0.65, help="Preferred minimum source-duration/note-duration ratio"),
    max_stretch_ratio: float = typer.Option(1.55, help="Preferred maximum source-duration/note-duration ratio"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Render a controllable female hum from decomposed sample carriers."""
    result = render_female_hum(
        dataset_index,
        out_dir,
        melody_json=melody_json,
        midi_path=midi,
        max_melody_duration_s=max_melody_duration,
        midi_track_name=midi_track_name,
        midi_legato=midi_legato,
        midi_min_note_duration_s=midi_min_note_duration,
        midi_tempo_bpm=midi_tempo_bpm,
        midi_swing_ratio=midi_swing_ratio,
        sr=sample_rate,
        carrier=carrier,
        transpose_semitones=transpose,
        tone=tone,
        rest_s=rest,
        min_sample_duration_s=min_sample_duration,
        max_samples=max_samples,
        min_stretch_ratio=min_stretch_ratio,
        max_stretch_ratio=max_stretch_ratio,
    )
    payload = result.to_dict()
    if output_json:
        print(json.dumps({"status": "ok", **payload}, indent=2))
    else:
        console.print(f"[green]Female hum rendered:[/green] {payload['output_wav']}")
        console.print(f"  Manifest: {payload['render_manifest']}")
        console.print(f"  Samples:  {payload['sample_count']}")
        console.print(f"  Notes:    {payload['note_count']}")
        console.print(f"  Duration: {payload['duration_s']}s")
        console.print(f"  Peak:     {payload['peak']}")


@app.command("train-hum-timbre")
def train_hum_timbre_cmd(
    dataset_index: Path = typer.Option(
        Path("/tmp/female-humming-dataset/decomposition/index.json"),
        help="Decomposition index from build-female-humming-dataset",
    ),
    out_dir: Path = typer.Option(Path("/tmp/hum-timbre-model"), help="Output model directory"),
    sample_rate: int = typer.Option(22050, help="Training analysis sample rate"),
    harmonics: int = typer.Option(16, help="Number of harmonics to model"),
    max_duration: Optional[float] = typer.Option(60.0, help="Maximum seconds per source clip"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Train a lightweight harmonic female-hum timbre model."""
    result = train_hum_timbre_model(
        dataset_index,
        out_dir,
        sr=sample_rate,
        n_harmonics=harmonics,
        max_duration_s=max_duration,
    )
    payload = result.to_dict()
    if output_json:
        print(json.dumps({"status": "ok", **payload}, indent=2))
    else:
        console.print(f"[green]Hum timbre model trained:[/green] {payload['model_json']}")
        console.print(f"  Clips:     {payload['clip_count']}")
        console.print(f"  Frames:    {payload['frame_count']}")
        console.print(f"  Harmonics: {payload['harmonic_count']}")


@app.command("render-trained-hum")
def render_trained_hum_cmd(
    model_json: Path = typer.Option(Path("/tmp/hum-timbre-model/hum_timbre_model.json"), help="Trained model JSON"),
    out_dir: Path = typer.Option(Path("/tmp/trained-hum-render"), help="Output render directory"),
    melody_json: Optional[Path] = typer.Option(None, help="Optional melody JSON with notes"),
    midi: Optional[Path] = typer.Option(None, help="Optional MIDI melody source"),
    max_melody_duration: Optional[float] = typer.Option(None, help="Maximum seconds to render from MIDI melody"),
    midi_track_name: Optional[str] = typer.Option(None, help="Preferred MIDI track/instrument name substring"),
    midi_min_note_duration: float = typer.Option(
        0.28, help="Collapse faster MIDI ornaments into notes at least this long"
    ),
    transpose: float = typer.Option(0.0, help="Transpose rendered melody in semitones"),
    portamento: float = typer.Option(0.055, help="Pitch glide smoothing in seconds"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Render MIDI/notes through the trained continuous hum timbre model."""
    result = render_trained_hum(
        model_json,
        out_dir,
        melody_json=melody_json,
        midi_path=midi,
        max_melody_duration_s=max_melody_duration,
        midi_track_name=midi_track_name,
        midi_min_note_duration_s=midi_min_note_duration,
        transpose_semitones=transpose,
        portamento_s=portamento,
    )
    payload = result.to_dict()
    if output_json:
        print(json.dumps({"status": "ok", **payload}, indent=2))
    else:
        console.print(f"[green]Trained hum rendered:[/green] {payload['output_wav']}")
        console.print(f"  Manifest: {payload['render_manifest']}")
        console.print(f"  Notes:    {payload['note_count']}")
        console.print(f"  Duration: {payload['duration_s']}s")
        console.print(f"  Peak:     {payload['peak']}")


@app.command("train-neural-hum-renderer")
def train_neural_hum_renderer_cmd(
    controls_dir: Path = typer.Option(..., help="Control dataset directory with manifest.json"),
    out_dir: Path = typer.Option(Path("/mnt/storage12tb/datasets/hum_mvp/runs/local_mvp"), help="Output training run dir"),
    epochs: int = typer.Option(3, help="Bounded training epochs metadata"),
    batch_size: int = typer.Option(8, help="Bounded batch size metadata"),
    sample_rate: int = typer.Option(22050, help="Training sample rate"),
    harmonics: int = typer.Option(18, help="Number of harmonic weights to learn"),
    max_duration: Optional[float] = typer.Option(10.0, help="Maximum seconds per clip for training stats"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Train the bounded MIDI-control female hum renderer."""
    result = train_neural_hum_renderer(
        controls_dir,
        out_dir,
        epochs=epochs,
        batch_size=batch_size,
        sample_rate=sample_rate,
        harmonics=harmonics,
        max_duration_s=max_duration,
    )
    payload = result.to_dict()
    if output_json:
        print(json.dumps({"status": "ok", **payload}, indent=2))
    else:
        console.print(f"[green]Neural hum renderer trained:[/green] {payload['checkpoint']}")
        console.print(f"  Metrics: {payload['metrics_json']}")
        console.print(f"  Train:   {payload['train_count']}")
        console.print(f"  Valid:   {payload['valid_count']}")


@app.command("render-neural-hum")
def render_neural_hum_cmd(
    checkpoint: Path = typer.Option(..., help="Renderer checkpoint .npz"),
    midi: Path = typer.Option(..., help="MIDI melody source"),
    out_dir: Path = typer.Option(Path("/mnt/storage12tb/datasets/hum_mvp/renders/hawaiian_war_chant"), help="Output render dir"),
    max_melody_duration: Optional[float] = typer.Option(None, help="Maximum seconds to render from MIDI"),
    midi_track_name: Optional[str] = typer.Option(None, help="Preferred MIDI track/instrument substring"),
    midi_min_note_duration: float = typer.Option(0.12, help="Minimum note duration after MIDI simplification"),
    transpose: float = typer.Option(-5.0, help="Transpose output in semitones"),
    portamento: float = typer.Option(0.085, help="Pitch smoothing seconds"),
    lowpass_hz: float = typer.Option(1850.0, help="Low-pass/body filter frequency"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Render a MIDI file through the bounded trained female hum renderer."""
    result = render_neural_hum(
        checkpoint,
        midi,
        out_dir,
        max_melody_duration_s=max_melody_duration,
        midi_track_name=midi_track_name,
        midi_min_note_duration_s=midi_min_note_duration,
        transpose_semitones=transpose,
        portamento_s=portamento,
        lowpass_hz=lowpass_hz,
    )
    payload = result.to_dict()
    if output_json:
        print(json.dumps({"status": "ok", **payload}, indent=2))
    else:
        console.print(f"[green]Neural female hum rendered:[/green] {payload['output_wav']}")
        console.print(f"  Manifest: {payload['render_manifest']}")
        console.print(f"  Notes:    {payload['note_count']}")


@app.command("evaluate-hum-render")
def evaluate_hum_render_cmd(
    render_dir: Path = typer.Option(..., help="Render directory containing female_hum.wav and manifest"),
    target_midi: Path = typer.Option(..., help="Target MIDI used for rendering"),
    out: Path = typer.Option(..., help="Output evaluation JSON"),
    transpose: float = typer.Option(-5.0, help="Transpose used during render"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Compare rendered F0/timing against the target MIDI/control curve."""
    result = evaluate_hum_render(render_dir, target_midi, out, transpose_semitones=transpose)
    payload = result.to_dict()
    if output_json:
        print(json.dumps({"status": "ok", **payload}, indent=2))
    else:
        console.print(f"[green]Hum render evaluated:[/green] {payload['report_json']}")
        console.print(f"  Median pitch error: {payload['median_abs_pitch_error_cents']}")
        console.print(f"  Voiced ratio:        {payload['voiced_ratio']}")


@app.command("render-articulated-psola")
def render_articulated_psola_cmd(
    midi: Path = typer.Option(..., help="Input MIDI containing a monophonic Melody track"),
    samples: Path = typer.Option(..., help="Directory containing required articulation WAV tokens"),
    output_dir: Path = typer.Option(..., help="Output artifact directory"),
    phrases_json: Optional[Path] = typer.Option(None, help="Optional phrase JSON; defaults to Hawaiian War Chant phrases"),
    baseline_wav: Optional[Path] = typer.Option(None, help="Optional baseline WAV for A/B review artifact"),
    melody_track_name: str = typer.Option("Melody", help="MIDI melody track name to select"),
    sample_rate: int = typer.Option(44100, help="Render sample rate"),
    cycles: Optional[int] = typer.Option(None, help="Phrase cycles; default infers a feasible count"),
    swing_ratio: float = typer.Option(0.58, help="Deterministic long-short swing ratio"),
    swing_tolerance: float = typer.Option(0.10, help="Swing detection tolerance as beat fraction"),
    crossfade_ms: float = typer.Option(35.0, help="PSOLA/sample crossfade in milliseconds"),
    breath_gap_ms: float = typer.Option(250.0, help="Minimum phrase gap for breath gesture"),
    gliss_max_semitones: int = typer.Option(3, help="Maximum adjacent-note interval for glissando"),
    gliss_gap_ms: float = typer.Option(40.0, help="Maximum adjacent-note gap for glissando"),
    target_peak_dbfs: float = typer.Option(-1.2, help="Output normalization peak target"),
    seed: int = typer.Option(20260620, help="Deterministic review/random seed"),
    allow_no_swing_pairs: bool = typer.Option(False, help="Waive swing-pair QA requirement"),
    run_elevenlabs: bool = typer.Option(False, help="Explicit opt-in for ElevenLabs voice changer comparison"),
    elevenlabs_voice_id: Optional[str] = typer.Option(None, help="ElevenLabs voice ID when --run-elevenlabs is set"),
    elevenlabs_model_id: str = typer.Option("eleven_multilingual_sts_v2", help="ElevenLabs model ID"),
    elevenlabs_output_format: str = typer.Option("mp3_44100_128", help="ElevenLabs output format"),
    elevenlabs_enable_logging: bool = typer.Option(True, help="Allow ElevenLabs request logging"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Render deterministic articulated PSOLA hum artifacts from MIDI and sample tokens."""
    from .articulated_psola_renderer import main as renderer_main

    argv = [
        "--midi",
        str(midi),
        "--samples",
        str(samples),
        "--output-dir",
        str(output_dir),
        "--melody-track-name",
        melody_track_name,
        "--sample-rate",
        str(sample_rate),
        "--swing-ratio",
        str(swing_ratio),
        "--swing-tolerance",
        str(swing_tolerance),
        "--crossfade-ms",
        str(crossfade_ms),
        "--breath-gap-ms",
        str(breath_gap_ms),
        "--gliss-max-semitones",
        str(gliss_max_semitones),
        "--gliss-gap-ms",
        str(gliss_gap_ms),
        "--target-peak-dbfs",
        str(target_peak_dbfs),
        "--seed",
        str(seed),
    ]
    if phrases_json is not None:
        argv.extend(["--phrases-json", str(phrases_json)])
    if baseline_wav is not None:
        argv.extend(["--baseline-wav", str(baseline_wav)])
    if cycles is not None:
        argv.extend(["--cycles", str(cycles)])
    if allow_no_swing_pairs:
        argv.append("--allow-no-swing-pairs")
    if run_elevenlabs:
        argv.append("--run-elevenlabs")
        if elevenlabs_voice_id:
            argv.extend(["--elevenlabs-voice-id", elevenlabs_voice_id])
        argv.extend(["--elevenlabs-model-id", elevenlabs_model_id])
        argv.extend(["--elevenlabs-output-format", elevenlabs_output_format])
        if not elevenlabs_enable_logging:
            argv.append("--elevenlabs-disable-logging")

    captured = StringIO()
    with redirect_stdout(captured):
        exit_code = renderer_main(argv)
    raw = captured.getvalue().strip()
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        payload = {"renderer_output": raw}
    payload = {"status": "ok" if exit_code == 0 else "qa_failed", "exit_code": exit_code, **payload}

    if output_json:
        print(json.dumps(payload, indent=2))
    else:
        status_color = "green" if exit_code == 0 else "yellow"
        console.print(f"[{status_color}]Articulated PSOLA render complete:[/{status_color}] {payload.get('output_dir', output_dir)}")
        console.print(f"  Local QA:    {payload.get('passes_local_gate')}")
        console.print(f"  Cycles:      {payload.get('cycles')}")
        console.print(f"  Swing pairs: {payload.get('swing_pairs')}")
        console.print(f"  Audio:       {output_dir / 'articulated_psola_dry_v1.wav'}")
        console.print(f"  Manifest:    {output_dir / 'render_manifest_v1.json'}")
        console.print(f"  QA:          {output_dir / 'qa_metrics_v1.json'}")

    if exit_code != 0:
        raise typer.Exit(exit_code)


@app.command("generate-elevenlabs-articulations")
def generate_elevenlabs_articulations_cmd(
    output_dir: Path = typer.Option(..., help="Output directory for raw audio, WAV samples, and manifests"),
    api_key: Optional[str] = typer.Option(None, help="ElevenLabs API key; defaults to ELEVENLABS_API_KEY"),
    model_id: str = typer.Option("eleven_text_to_sound_v2", help="ElevenLabs Sound Effects model ID"),
    output_format: str = typer.Option("mp3_44100_128", help="ElevenLabs output format"),
    sample_rate: int = typer.Option(44100, help="Converted WAV sample rate"),
    duration_seconds: Optional[float] = typer.Option(1.2, help="Duration per token in seconds; omit with --duration-seconds none is not supported by Typer"),
    prompt_influence: float = typer.Option(0.72, help="Prompt adherence from 0 to 1"),
    loop: bool = typer.Option(False, help="Request seamless looping from Sound Effects model"),
    timeout_s: float = typer.Option(180.0, help="Per-token request timeout in seconds"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Generate required PSOLA articulation WAV tokens with ElevenLabs Sound Effects."""
    from .elevenlabs_articulation import generate_elevenlabs_articulation_inventory

    try:
        result = generate_elevenlabs_articulation_inventory(
            output_dir=output_dir,
            api_key=api_key,
            model_id=model_id,
            output_format=output_format,
            sample_rate=sample_rate,
            duration_seconds=duration_seconds,
            prompt_influence=prompt_influence,
            loop=loop,
            timeout_s=timeout_s,
        )
    except Exception as exc:
        if output_json:
            print(json.dumps({"status": "error", "error": str(exc)}, indent=2))
        else:
            console.print(f"[red]Failed:[/red] {exc}")
        raise typer.Exit(1)

    payload = {"status": "ok", **result.to_dict()}
    if output_json:
        print(json.dumps(payload, indent=2))
    else:
        console.print(f"[green]ElevenLabs Sound Effects articulation inventory generated:[/green] {payload['samples_dir']}")
        console.print(f"  Tokens:   {payload['token_count']}")
        console.print(f"  Manifest: {payload['manifest_json']}")
        console.print(f"  Receipts: {payload['receipt_json']}")


@app.command("pitch-correct-guide")
def pitch_correct_guide_cmd(
    audio: Path = typer.Argument(..., help="Guide WAV to analyze and lightly pitch-center before STS"),
    out_dir: Path = typer.Option(Path("/tmp/hum_pitch_corrected_guide"), help="Output artifact directory"),
    sample_rate: int = typer.Option(44100, help="Analysis/output sample rate"),
    max_correction_cents: float = typer.Option(35.0, help="Maximum global correction in cents"),
    min_voiced_ratio: float = typer.Option(0.08, help="Minimum voiced-frame ratio required to apply correction"),
    target_peak_dbfs: float = typer.Option(-1.0, help="Peak normalization target in dBFS"),
    dry_run: bool = typer.Option(False, help="Only write analysis/manifest; do not write corrected WAV"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Create a light pre-ElevenLabs pitch-corrected guide variant for bakeoffs."""
    result = pitch_correct_guide(
        audio,
        out_dir,
        sample_rate=sample_rate,
        max_correction_cents=max_correction_cents,
        min_voiced_ratio=min_voiced_ratio,
        target_peak_dbfs=target_peak_dbfs,
        dry_run=dry_run,
    )
    payload = result.to_dict()
    if output_json:
        print(json.dumps({"status": "ok", **payload}, indent=2))
    else:
        console.print(f"[green]Pitch guide analyzed:[/green] {audio}")
        console.print(f"  Output WAV:   {payload['output_wav']}")
        console.print(f"  Manifest:     {payload['manifest_json']}")
        console.print(f"  Analysis:     {payload['analysis_json']}")
        console.print(f"  Correction:   {payload['correction_cents']} cents")
        console.print(f"  Voiced ratio: {payload['voiced_ratio']}")


@app.command()
def add(
    url: Optional[str] = typer.Argument(None, help="YouTube URL (optional if --song provided)"),
    persona: str = typer.Option(DEFAULT_PERSONA, help="Target persona"),
    song: Optional[Path] = typer.Option(None, help="Licensed local audio file (preferred)"),
    start: str = typer.Option("00:00:00", help="Segment start (ffmpeg -ss)"),
    duration: str = typer.Option("00:00:20", help="Segment duration (ffmpeg -t)"),
    mood: Optional[str] = typer.Option(None, help="Comma-separated mood tags"),
    bridges: Optional[str] = typer.Option(None, help="Comma-separated bridge attributes"),
    title: Optional[str] = typer.Option(None, help="Track title (auto-detected if omitted)"),
    artist: Optional[str] = typer.Option(None, help="Artist name"),
    connection: Optional[str] = typer.Option(None, help="Persona connection note"),
    semi_tone_shift: int = typer.Option(0, help="Seed-VC semitone shift"),
    diffusion_steps: int = typer.Option(DEFAULT_DIFFUSION_STEPS, help="Seed-VC diffusion steps"),
    melody_audio: str = typer.Option("auto", help="Melody transcription input: auto, vocals, or mix"),
    source_hum_renderer: str = typer.Option(
        DEFAULT_SOURCE_HUM_RENDERER,
        help="Guide renderer: vocal_stem, acestep_api, ace, suno_manual, elevenlabs_manual, neural_hum, real_hum, old_synth, vocal_stem_diag",
    ),
    source_mode: Optional[str] = typer.Option(
        None, help="Deprecated alias for source_hum_renderer (vocal_stem→vocal_stem_diag, midi_hum→old_synth)"
    ),
    midi: Optional[Path] = typer.Option(None, help="Manual MIDI melody override (old_synth only)"),
    source_hum: Optional[Path] = typer.Option(None, help="Imported guide hum WAV (ACE/Suno/human)"),
    force: bool = typer.Option(False, help="Skip melody/source-hum quality gates"),
    allow_diagnostic_cache: bool = typer.Option(
        False, help="Allow caching vocal_stem_diag output (not for production)"
    ),
    orpheus_url: Optional[str] = typer.Option(None, help="Orpheus infer base URL"),
    seedvc_dir: Optional[str] = typer.Option(None, help="Seed-VC repo root"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Full pipeline: segment → melody hum → Orpheus ref → Seed-VC → cache."""
    pipeline = HumPipeline(persona=persona)

    mood_list = [m.strip() for m in mood.split(",")] if mood else []
    bridge_list = [b.strip() for b in bridges.split(",")] if bridges else []

    label = song or url or "<missing>"
    console.print(f"[bold]Adding hum for {persona}[/bold]: {label}")
    console.print()

    result = pipeline.add(
        url=url,
        song=song,
        title=title,
        artist=artist,
        mood=mood_list,
        bridges=bridge_list,
        persona_connection=connection or "",
        start=start,
        duration=duration,
        semi_tone_shift=semi_tone_shift,
        diffusion_steps=diffusion_steps,
        manual_midi=midi,
        manual_source_hum=source_hum,
        melody_audio=melody_audio,
        source_hum_renderer=source_hum_renderer,
        source_mode=source_mode,
        force=force,
        allow_diagnostic_cache=allow_diagnostic_cache,
        orpheus_url=orpheus_url,
        seedvc_dir=seedvc_dir,
    )

    if output_json:
        print(json.dumps(result, indent=2))
    else:
        if result.get("status") == "ok":
            console.print(f"[green]Cached:[/green] {result['track_id']}")
            console.print(f"  File: {result['audio_path']}")
            console.print(f"  Duration: {result.get('duration_s', '?')}s")
            console.print(f"  Pipeline: {result.get('pipeline', '?')}")
        else:
            console.print(f"[red]Failed:[/red] {result.get('error', 'unknown')}")
            raise typer.Exit(1)



@app.command("prepare-ace")
def prepare_ace(
    song: Path = typer.Option(..., help="Licensed local audio file"),
    start: str = typer.Option("00:00:00", help="Segment start"),
    duration: str = typer.Option("00:00:20", help="Segment duration"),
    out_dir: Path = typer.Option(Path("/tmp/hum_ace_bundle"), help="Output bundle directory"),
    melody_audio: str = typer.Option("mix", help="Melody transcription input: auto, vocals, mix"),
    midi: Optional[Path] = typer.Option(None, help="Manual MIDI override"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Prepare ACE Studio MIDI + closed-mouth lyric bundle (manual export step)."""
    from .melody import transcribe_to_midi
    from .neural_hum import prepare_ace_bundle
    from .pipeline import HumPipeline

    pipeline = HumPipeline()
    import tempfile
    with tempfile.TemporaryDirectory(prefix="hum_ace_") as tmp:
        work = Path(tmp)
        segment = pipeline._trim_segment(song, work / "segment.wav", start, duration)
        vocals = pipeline._separate_vocals(segment, work)
        if not vocals:
            raise typer.Exit("Stem separation failed")
        if midi:
            midi_path = Path(midi)
        else:
            melody_input = pipeline._pick_melody_input(segment, vocals, melody_audio, work, transcribe_to_midi)
            midi_path = transcribe_to_midi(melody_input, work / "midi")
        bundle = prepare_ace_bundle(midi_path, out_dir)
    if output_json:
        print(json.dumps({"status": "ok", **bundle}, indent=2))
    else:
        console.print(f"[green]ACE bundle ready:[/green] {out_dir}")
        for k, v in bundle.items():
            console.print(f"  {k}: {v}")

@app.command()
def train(
    persona: str = typer.Option(DEFAULT_PERSONA, help="Target persona"),
    epochs: int = typer.Option(200, help="Deprecated — ignored"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Deprecated: use /tts-voice to train Orpheus persona voice."""
    pipeline = HumPipeline(persona=persona)
    result = pipeline.train_voice(epochs=epochs)

    if output_json:
        print(json.dumps(result, indent=2))
    else:
        console.print(f"[yellow]{result.get('error')}[/yellow]")
        if result.get("hint"):
            console.print(f"  Hint: {result['hint']}")
        raise typer.Exit(1)


@app.command("list")
def list_tracks(
    persona: str = typer.Option(DEFAULT_PERSONA, help="Target persona"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """List all cached hums for a persona."""
    cache = HumCache(persona=persona)
    tracks = cache.list_tracks()

    if output_json:
        print(json.dumps([t.to_dict() for t in tracks], indent=2))
        return

    if not tracks:
        console.print(f"No hums cached for {persona}")
        console.print(f"  Add one: ./run.sh add --song /path/to/song.wav --persona {persona}")
        return

    table = Table(title=f"Hum Cache: {persona}")
    table.add_column("ID", style="cyan")
    table.add_column("Title")
    table.add_column("Artist")
    table.add_column("Pipeline")
    table.add_column("Mood")
    table.add_column("Duration")

    for t in tracks:
        table.add_row(
            t.id,
            t.title,
            t.artist,
            getattr(t, "pipeline", "rvc_v1"),
            ", ".join(t.mood),
            f"{t.duration_s}s" if t.duration_s else "?",
        )

    console.print(table)


@app.command()
def play(
    track_id: str = typer.Argument(..., help="Track ID to play"),
    persona: str = typer.Option(DEFAULT_PERSONA, help="Target persona"),
):
    """Play a cached hum through PipeWire."""
    cache = HumCache(persona=persona)
    track = cache.get_track(track_id)

    if not track:
        console.print(f"[red]Track not found:[/red] {track_id}")
        raise typer.Exit(1)

    audio_path = cache.get_audio_path(track_id)
    if not audio_path.exists():
        console.print(f"[red]Audio file missing:[/red] {audio_path}")
        raise typer.Exit(1)

    console.print(f"Playing: {track.title} by {track.artist}")
    console.print(f"  Mood: {', '.join(track.mood)}")

    import subprocess
    subprocess.run(["pw-play", str(audio_path)], check=True,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )


@app.command()
def info(
    track_id: str = typer.Argument(..., help="Track ID"),
    persona: str = typer.Option(DEFAULT_PERSONA, help="Target persona"),
    output_json: bool = typer.Option(False, "--json", help="Output as JSON"),
):
    """Show detailed track metadata."""
    cache = HumCache(persona=persona)
    track = cache.get_track(track_id)

    if not track:
        console.print(f"[red]Track not found:[/red] {track_id}")
        raise typer.Exit(1)

    if output_json:
        print(json.dumps(track.to_dict(), indent=2))
    else:
        console.print(f"[bold]{track.title}[/bold] by {track.artist}")
        console.print(f"  ID:          {track.id}")
        console.print(f"  Source:      {track.source_url}")
        console.print(f"  Pipeline:    {getattr(track, 'pipeline', 'rvc_v1')}")
        console.print(f"  Melody:      {getattr(track, 'melody_source', '?')}")
        console.print(f"  Renderer:    {getattr(track, 'source_hum_renderer', '?')}")
        console.print(f"  Mood:        {', '.join(track.mood)}")
        console.print(f"  Bridges:     {', '.join(track.bridge_attributes)}")
        console.print(f"  Connection:  {track.persona_connection}")
        console.print(f"  Duration:    {track.duration_s}s")
        console.print(f"  Semi-tone:   {track.pitch_shift}")
        console.print(f"  Diffusion:   {getattr(track, 'diffusion_steps', '?')}")
        console.print(f"  Created:     {track.created}")
        console.print(f"  Forbidden:   {track.forbidden}")


def main():
    app()


if __name__ == "__main__":
    main()
