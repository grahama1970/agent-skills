#!/usr/bin/env python3
"""
voice-lab: Test and iterate on trained Qwen3-TTS voice models.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from dotenv import load_dotenv, find_dotenv
load_dotenv(find_dotenv(usecwd=True), override=False)

app = typer.Typer(help="Test and iterate on trained voice models")
console = Console()

# Paths
VOICE_STORAGE = Path(os.environ.get("VOICE_STORAGE", "/mnt/storage12tb/media/personas"))
SKILL_DIR = Path(__file__).parent
TRAIN_VOICE_DIR = SKILL_DIR.parent / "train-voice"

# Fallback for systems without 12TB storage
if not VOICE_STORAGE.exists():
    VOICE_STORAGE = Path.home() / "personas"


def get_persona_dir(persona: str) -> Path:
    """Get the storage directory for a persona."""
    slug = persona.lower().replace(" ", "_")
    return VOICE_STORAGE / slug


def find_latest_checkpoint(persona: str) -> Optional[Path]:
    """Find the latest Qwen3-TTS checkpoint for a persona."""
    persona_dir = get_persona_dir(persona)
    qwen3_dir = persona_dir / "qwen3_tts" / "model"

    if not qwen3_dir.exists():
        return None

    checkpoints = sorted(qwen3_dir.glob("checkpoint-epoch-*"))
    if checkpoints:
        return checkpoints[-1]
    return None


def generate_audio(
    persona: str,
    text: str,
    output_path: Path,
    checkpoint: Optional[Path] = None,
    temperature: float = 0.7,
    top_p: float = 0.9,
) -> bool:
    """Generate audio using trained Qwen3-TTS model."""
    if checkpoint is None:
        checkpoint = find_latest_checkpoint(persona)

    if checkpoint is None or not checkpoint.exists():
        console.print(f"[red]No checkpoint found for {persona}[/red]")
        return False

    # Build inference script
    speaker_name = persona.lower().replace(" ", "_")

    inference_code = f'''
import torch
from qwen_tts.inference.qwen3_tts_model import Qwen3TTSModel
import soundfile as sf

model = Qwen3TTSModel.from_pretrained(
    "{checkpoint}",
    torch_dtype=torch.bfloat16,
    device_map="auto"
)

audio_outputs, sample_rate = model.generate_custom_voice(
    text="{text}",
    speaker="{speaker_name}",
    temperature={temperature},
    top_p={top_p},
    non_streaming_mode=True
)

# Convert to numpy and save
audio = audio_outputs[0].cpu().numpy()
sf.write("{output_path}", audio, sample_rate)
print(f"Generated: {output_path}")
'''

    # Run inference
    result = subprocess.run(
        [sys.executable, "-c", inference_code],
        capture_output=True,
        text=True,
        timeout=120,
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )

    if result.returncode != 0:
        console.print(f"[red]Generation failed: {result.stderr}[/red]")
        return False

    return output_path.exists()


@app.command()
def test(
    persona: str = typer.Argument(..., help="Persona name"),
    phrases: str = typer.Option("Hello, I am testing this voice model.", help="Test phrases"),
    output: Path = typer.Option(Path("output"), help="Output directory"),
    checkpoint: Optional[Path] = typer.Option(None, help="Specific checkpoint"),
    show_waveform: bool = typer.Option(False, help="Show ASCII waveform"),
):
    """Generate test audio from trained voice model."""
    output.mkdir(parents=True, exist_ok=True)

    slug = persona.lower().replace(" ", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    console.print(Panel(f"Testing voice: {persona}", title="voice-lab"))

    for i, phrase in enumerate(phrases.split(";")):
        phrase = phrase.strip()
        if not phrase:
            continue

        output_path = output / f"{slug}_test_{i:02d}_{timestamp}.wav"
        console.print(f"\n[cyan]Phrase {i+1}:[/cyan] {phrase[:60]}...")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Generating audio...", total=None)

            success = generate_audio(
                persona=persona,
                text=phrase,
                output_path=output_path,
                checkpoint=checkpoint,
            )

            if success:
                progress.update(task, description=f"[green]Generated: {output_path.name}[/green]")

                if show_waveform:
                    from waveform import load_audio, ascii_waveform
                    audio, sr = load_audio(output_path)
                    print(ascii_waveform(audio, sr, title=output_path.name))
            else:
                progress.update(task, description="[red]Generation failed[/red]")


@app.command()
def waveform(
    audio_file: Path = typer.Argument(..., help="Audio file to visualize"),
    width: int = typer.Option(80, help="ASCII width"),
    height: int = typer.Option(16, help="ASCII height"),
    html: bool = typer.Option(False, help="Generate HTML viewer"),
    output: Optional[Path] = typer.Option(None, help="Output path for HTML"),
):
    """Visualize audio waveform."""
    if not audio_file.exists():
        console.print(f"[red]File not found: {audio_file}[/red]")
        raise typer.Exit(1)

    from waveform import load_audio, ascii_waveform, html_waveform

    audio, sr = load_audio(audio_file)

    if html:
        output_path = output or audio_file.with_suffix('.html')
        html_waveform(audio, sr, audio_file, output_path)
        console.print(f"[green]Generated HTML viewer: {output_path}[/green]")
    else:
        print(ascii_waveform(audio, sr, width, height, audio_file.name))


@app.command()
def eval(
    persona: str = typer.Argument(..., help="Persona name"),
    phrases_file: Optional[Path] = typer.Option(None, help="File with test phrases"),
    reference: Optional[Path] = typer.Option(None, help="Reference audio for similarity"),
    threshold: float = typer.Option(3.5, help="Quality threshold (1-5)"),
    output_json: bool = typer.Option(False, "--json", help="Output JSON"),
):
    """Run quality evaluation on generated voice."""
    from quality import evaluate_quality

    # Load test phrases
    if phrases_file and phrases_file.exists():
        phrases = [l.strip() for l in phrases_file.read_text().splitlines() if l.strip()]
    else:
        phrases = [
            "Hello, I am testing this voice model.",
            "The quick brown fox jumps over the lazy dog.",
            "What do you think about this approach?",
        ]

    # Generate test audio
    output_dir = Path("output") / persona.lower().replace(" ", "_")
    output_dir.mkdir(parents=True, exist_ok=True)

    results = []

    console.print(Panel(f"Evaluating voice: {persona}", title="voice-lab"))

    for i, phrase in enumerate(phrases):
        output_path = output_dir / f"eval_{i:02d}.wav"

        console.print(f"\n[cyan]Test {i+1}/{len(phrases)}:[/cyan] {phrase[:50]}...")

        # Generate
        success = generate_audio(persona, phrase, output_path)
        if not success:
            console.print("[red]  Generation failed[/red]")
            continue

        # Evaluate
        metrics = evaluate_quality(output_path, reference, phrase)
        results.append({
            "phrase": phrase,
            "metrics": metrics.to_dict(),
            "path": str(output_path),
        })

        # Show results
        quality_color = "green" if metrics.overall_score >= threshold else "yellow"
        console.print(f"  Similarity: {metrics.similarity:.2f}")
        console.print(f"  Naturalness: {metrics.naturalness:.2f}")
        console.print(f"  Artifacts: {metrics.artifact_score:.2f}")
        console.print(f"  [{quality_color}]Overall: {metrics.overall_score:.2f}/5.0[/{quality_color}]")

    # Summary
    if results:
        avg_score = sum(r["metrics"]["overall_score"] for r in results) / len(results)
        passed = avg_score >= threshold

        console.print("\n" + "=" * 50)
        if passed:
            console.print(f"[green]PASSED[/green] - Average score: {avg_score:.2f}/5.0")
        else:
            console.print(f"[red]FAILED[/red] - Average score: {avg_score:.2f}/5.0 (threshold: {threshold})")

        if output_json:
            print(json.dumps({
                "persona": persona,
                "average_score": avg_score,
                "threshold": threshold,
                "passed": passed,
                "results": results,
            }, indent=2))


@app.command()
def compare(
    persona: str = typer.Argument(..., help="Persona name"),
    checkpoints: str = typer.Option("", help="Comma-separated checkpoint names"),
    phrases_file: Optional[Path] = typer.Option(None, help="File with test phrases"),
    html: bool = typer.Option(False, help="Generate HTML comparison"),
):
    """Compare different checkpoints or models."""
    from quality import evaluate_quality

    persona_dir = get_persona_dir(persona)
    model_dir = persona_dir / "qwen3_tts" / "model"

    # Get checkpoints to compare
    if checkpoints:
        checkpoint_list = [model_dir / cp.strip() for cp in checkpoints.split(",")]
    else:
        checkpoint_list = sorted(model_dir.glob("checkpoint-epoch-*"))

    if not checkpoint_list:
        console.print(f"[red]No checkpoints found for {persona}[/red]")
        raise typer.Exit(1)

    # Test phrase
    test_phrase = "Hello, I am testing this voice model."
    if phrases_file and phrases_file.exists():
        test_phrase = phrases_file.read_text().splitlines()[0].strip()

    # Compare
    table = Table(title=f"Checkpoint Comparison: {persona}")
    table.add_column("Checkpoint")
    table.add_column("Similarity", justify="right")
    table.add_column("Naturalness", justify="right")
    table.add_column("Artifacts", justify="right")
    table.add_column("Overall", justify="right")

    output_dir = Path("output") / "compare"
    output_dir.mkdir(parents=True, exist_ok=True)

    for checkpoint in checkpoint_list:
        if not checkpoint.exists():
            continue

        output_path = output_dir / f"{checkpoint.name}.wav"

        # Generate
        success = generate_audio(persona, test_phrase, output_path, checkpoint)
        if not success:
            table.add_row(checkpoint.name, "ERROR", "-", "-", "-")
            continue

        # Evaluate
        metrics = evaluate_quality(output_path)

        overall_color = "green" if metrics.overall_score >= 3.5 else "yellow"
        table.add_row(
            checkpoint.name,
            f"{metrics.similarity:.2f}",
            f"{metrics.naturalness:.2f}",
            f"{metrics.artifact_score:.2f}",
            f"[{overall_color}]{metrics.overall_score:.2f}[/{overall_color}]",
        )

    console.print(table)


@app.command()
def iterate(
    persona: str = typer.Argument(..., help="Persona name"),
    target_quality: float = typer.Option(4.0, help="Target quality score (1-5)"),
    max_iterations: int = typer.Option(5, help="Maximum improvement attempts"),
    strategy: str = typer.Option("temperature", help="Strategy: temperature,checkpoint"),
    auto: bool = typer.Option(False, help="Run without human feedback"),
):
    """Self-improvement iteration loop."""
    from quality import evaluate_quality

    console.print(Panel(f"Iteration Loop: {persona}", title="voice-lab"))
    console.print(f"Target quality: {target_quality}/5.0")
    console.print(f"Strategy: {strategy}")
    console.print(f"Max iterations: {max_iterations}")

    test_phrase = "Hello, I am testing this voice model with the iteration loop."
    output_dir = Path("output") / "iterate"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Iteration parameters
    temperatures = [0.7, 0.5, 0.8, 0.6, 0.9]
    current_temp_idx = 0

    for iteration in range(max_iterations):
        console.print(f"\n[cyan]Iteration {iteration + 1}/{max_iterations}[/cyan]")

        # Adjust parameters based on strategy
        if strategy == "temperature":
            temperature = temperatures[current_temp_idx % len(temperatures)]
            console.print(f"  Temperature: {temperature}")
        else:
            temperature = 0.7

        output_path = output_dir / f"iter_{iteration:02d}.wav"

        # Generate
        success = generate_audio(
            persona=persona,
            text=test_phrase,
            output_path=output_path,
            temperature=temperature,
        )

        if not success:
            console.print("[red]  Generation failed - retrying...[/red]")
            current_temp_idx += 1
            continue

        # Evaluate
        metrics = evaluate_quality(output_path)
        console.print(f"  Quality score: {metrics.overall_score:.2f}/5.0")

        # Check if target met
        if metrics.overall_score >= target_quality:
            console.print(f"\n[green]TARGET REACHED![/green] Score: {metrics.overall_score:.2f}")
            console.print(f"Best output: {output_path}")
            return

        # Human feedback (if not auto)
        if not auto:
            console.print(f"\n  [dim]Listen to: {output_path}[/dim]")
            try:
                rating = typer.prompt("Rate quality (1-5, or 's' to skip)", default="s")
                if rating.lower() != "s":
                    human_score = float(rating)
                    if human_score >= target_quality:
                        console.print(f"\n[green]Human rating passed![/green]")
                        return
            except (ValueError, KeyboardInterrupt):
                pass

        # Adjust for next iteration
        current_temp_idx += 1
        console.print("  [yellow]Adjusting parameters...[/yellow]")

    console.print(f"\n[yellow]Max iterations reached. Best quality not achieved.[/yellow]")


@app.command()
def status(
    persona: Optional[str] = typer.Argument(None, help="Persona name (optional)"),
):
    """Show voice training status."""
    if persona:
        # Show specific persona
        persona_dir = get_persona_dir(persona)

        console.print(Panel(f"Voice Status: {persona}", title="voice-lab"))

        # PersonaPlex
        personaplex_dir = persona_dir / "personaplex"
        if personaplex_dir.exists():
            embeddings = list(personaplex_dir.glob("**/*.pt"))
            console.print(f"[green]PersonaPlex:[/green] {len(embeddings)} embeddings")
            for emb in embeddings[:3]:
                console.print(f"  - {emb.name}")
        else:
            console.print("[yellow]PersonaPlex:[/yellow] Not trained")

        # Qwen3-TTS
        qwen3_dir = persona_dir / "qwen3_tts" / "model"
        if qwen3_dir.exists():
            checkpoints = list(qwen3_dir.glob("checkpoint-epoch-*"))
            console.print(f"[green]Qwen3-TTS:[/green] {len(checkpoints)} checkpoints")
            for cp in checkpoints[-3:]:
                console.print(f"  - {cp.name}")
        else:
            console.print("[yellow]Qwen3-TTS:[/yellow] Not trained")

    else:
        # Show all personas
        table = Table(title="Trained Voices")
        table.add_column("Persona")
        table.add_column("PersonaPlex")
        table.add_column("Qwen3-TTS")

        for persona_dir in sorted(VOICE_STORAGE.iterdir()):
            if not persona_dir.is_dir():
                continue

            name = persona_dir.name.replace("_", " ").title()

            # Check PersonaPlex
            pp_dir = persona_dir / "personaplex"
            pp_status = "Yes" if pp_dir.exists() and list(pp_dir.glob("**/*.pt")) else "No"

            # Check Qwen3-TTS
            qwen_dir = persona_dir / "qwen3_tts" / "model"
            if qwen_dir.exists():
                checkpoints = list(qwen_dir.glob("checkpoint-epoch-*"))
                qwen_status = f"Yes ({len(checkpoints)} epochs)"
            else:
                qwen_status = "No"

            table.add_row(name, pp_status, qwen_status)

        console.print(table)


# --- RVC Parameter Sweep commands (merged from hum-lab) ---


@app.command()
def sweep(
    persona: str = typer.Option("embry", help="Target persona"),
    track: str = typer.Option("hawaiian_war_chant", help="Track ID in hum cache"),
    phase: str = typer.Option("full", help="Phase: diagnostic, cross, or full"),
) -> None:
    """Run a full RVC parameter sweep on a track."""
    from sweep import run_sweep

    console.print(f"[bold]Sweep:[/bold] {persona}/{track} (phase={phase})")
    run_sweep(persona=persona, track=track, phase=phase)


@app.command()
def rank(
    persona: str = typer.Option("embry", help="Target persona"),
    track: Optional[str] = typer.Option(None, help="Track ID (latest if omitted)"),
    top: int = typer.Option(20, help="Number of results to show"),
) -> None:
    """Show ranked results from the last sweep."""
    from sweep import print_ranked

    print_ranked(persona=persona, track=track, n=top)


@app.command()
def preset(
    persona: str = typer.Option("embry", help="Target persona"),
    save_winner: bool = typer.Option(False, "--save-winner", help="Save winning params as preset"),
    name: str = typer.Option("default", help="Preset name"),
    track: Optional[str] = typer.Option(None, help="Track to source winner from"),
    load: bool = typer.Option(False, help="Load and display a preset"),
) -> None:
    """Save or load parameter presets."""
    from presets import load_preset as _load_preset, save_winner as _save_winner

    if save_winner:
        _save_winner(persona=persona, track=track, name=name)
    elif load:
        params = _load_preset(persona, name)
        if params:
            console.print(f"[bold]Preset '{name}':[/bold]")
            for k, v in params.items():
                console.print(f"  {k}: {v}")
        else:
            console.print(f"[yellow]Preset '{name}' not found for {persona}[/yellow]")
    else:
        console.print("Use --save-winner or --load")


@app.command()
def presets(
    persona: str = typer.Option("embry", help="Target persona"),
) -> None:
    """List all presets for a persona."""
    from presets import print_presets

    print_presets(persona)


@app.command(name="export-to-hum")
def export_to_hum(
    persona: str = typer.Option("embry", help="Target persona"),
    name: str = typer.Option("default", help="Preset name to export"),
) -> None:
    """Export winning RVC preset to /hum skill format."""
    from presets import load_preset

    params = load_preset(persona, name)
    if not params:
        console.print(f"[red]No preset '{name}' found for {persona}[/red]")
        console.print("Run: ./run.sh preset --persona embry --save-winner")
        raise typer.Exit(1)

    console.print(f"[bold]Preset '{name}' for {persona}:[/bold]")
    for k, v in params.items():
        console.print(f"  {k}: {v}")

    # Write to well-known location for /hum
    hum_presets_dir = VOICE_STORAGE / persona / "hum-cache" / "presets"
    hum_presets_dir.mkdir(parents=True, exist_ok=True)
    hum_preset_path = hum_presets_dir / f"{name}.json"

    console.print(f"\n[green]Preset available at:[/green] {hum_preset_path}")
    console.print(f"\n[bold]Use with /hum:[/bold]")

    pitch = params.get("pitch", 0)
    f0 = params.get("f0method", "rmvpe")
    console.print(
        f"  ./run.sh convert --persona {persona} "
        f"--pitch {pitch} --f0method {f0}"
    )


# --- PipeWire Device & Recording commands ---


@app.command()
def devices(
    source_only: bool = typer.Option(False, "--source-only", help="Show only sources (mics)"),
    sink_only: bool = typer.Option(False, "--sink-only", help="Show only sinks (speakers)"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """List PipeWire audio devices."""
    from devices import print_devices

    print_devices(source_only=source_only, sink_only=sink_only, json_output=json_output)


@app.command()
def record(
    device: Optional[str] = typer.Option(None, help="Device name substring (e.g. 'Jabra')"),
    duration: int = typer.Option(30, help="Recording duration in seconds"),
    output: Path = typer.Option(Path("/tmp/voice-lab-recording.wav"), help="Output WAV path"),
    denoise: bool = typer.Option(False, help="Apply noise reduction after recording"),
    sample_rate: int = typer.Option(48000, "--sr", help="Sample rate"),
) -> None:
    """Record audio from a PipeWire device."""
    from capture import record_audio

    record_audio(
        device_name=device,
        duration_s=duration,
        output_path=output,
        denoise=denoise,
        sample_rate=sample_rate,
    )


# --- Alignment commands ---


@app.command()
def align(
    graham_audio: Path = typer.Argument(..., help="Graham's recording WAV"),
    original_audio: Path = typer.Argument(..., help="Original vocals WAV"),
    srt_file: Path = typer.Argument(..., help="SRT subtitle file"),
    output_dir: Path = typer.Option(Path("alignment_output"), help="Output directory"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """SRT-aligned audio segmentation and comparison."""
    from alignment import align_recordings, save_alignment, print_alignment

    results = align_recordings(graham_audio, original_audio, srt_file, output_dir)

    alignment_path = output_dir / "alignment.json"
    save_alignment(results, alignment_path)

    if json_output:
        print(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        print_alignment(results)


def _extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from any URL format."""
    import re
    for pat in [
        r"youtube\.com/watch\?v=([a-zA-Z0-9_-]+)",
        r"youtu\.be/([a-zA-Z0-9_-]+)",
        r"youtube\.com/embed/([a-zA-Z0-9_-]+)",
    ]:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


def _download_youtube_audio(url: str, output_dir: Path) -> Path:
    """Download YouTube audio as WAV for waveform display."""
    vid = _extract_video_id(url)
    if not vid:
        raise ValueError(f"Could not extract video ID from: {url}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Check cache — any audio format, not just wav
    for cached in output_dir.glob(f"{vid}.*"):
        if cached.suffix in (".wav", ".mp3", ".m4a", ".ogg", ".opus"):
            console.print(f"[dim]Using cached audio: {cached}[/dim]")
            return cached

    console.print(f"[cyan]Downloading audio from YouTube...[/cyan]")

    SKILLS_DIR = Path(__file__).resolve().parent.parent
    _iy_dir = str(SKILLS_DIR / "ingest-youtube")
    if _iy_dir not in sys.path:
        sys.path.insert(0, _iy_dir)

    from youtube_transcripts.downloader import download_audio

    audio_path, error = download_audio(vid, output_dir)
    if error or audio_path is None:
        raise FileNotFoundError(f"Audio download failed: {error}")

    console.print(f"[green]Audio downloaded: {audio_path}[/green]")
    return audio_path


def _generate_srt_from_audio(audio_path: Path, output_dir: Path) -> Path:
    """Generate a simple SRT with a single segment spanning the full duration."""
    from waveform import load_audio

    srt_path = output_dir / (audio_path.stem + ".srt")
    if srt_path.exists():
        return srt_path

    audio, sr = load_audio(audio_path)
    duration = len(audio) / sr

    # Create a single-segment SRT spanning the full track
    hours = int(duration // 3600)
    mins = int((duration % 3600) // 60)
    secs = int(duration % 60)
    ms = int((duration % 1) * 1000)

    srt_content = (
        f"1\n"
        f"00:00:00,000 --> {hours:02d}:{mins:02d}:{secs:02d},{ms:03d}\n"
        f"Full track\n"
    )
    srt_path.write_text(srt_content)
    return srt_path


@app.command()
def edit(
    ref_audio: Optional[Path] = typer.Argument(None, help="Reference audio (optional if --youtube-url given)"),
    srt: Optional[Path] = typer.Argument(None, help="SRT file (auto-generated if omitted)"),
    output_dir: Optional[Path] = typer.Option(None, help="Output directory for alignment.json + recordings"),
    youtube_url: str = typer.Option("", "--youtube-url", help="YouTube URL — downloads audio as reference track"),
    persona: str = typer.Option("graham", help="Persona name for persistent takes directory"),
) -> None:
    """Open video-editor-style recording editor (QML).

    Usage:
        voice-lab edit --youtube-url "https://youtube.com/watch?v=..."
        voice-lab edit reference.wav subtitles.srt
        voice-lab edit reference.wav subtitles.srt --youtube-url "https://..."
    """
    try:
        from app import launch_app
    except ImportError:
        console.print("[red]PySide6 + QtWebEngine required for editor. Install: uv pip install 'voice-lab[editor]'[/red]")
        raise typer.Exit(1)

    # YouTube-first workflow: download audio if no ref_audio given
    if youtube_url and ref_audio is None:
        cache_dir = Path("/tmp/voice-lab-cache")
        ref_audio = _download_youtube_audio(youtube_url, cache_dir)
        if srt is None:
            srt = _generate_srt_from_audio(ref_audio, cache_dir)
        if output_dir is None:
            output_dir = cache_dir

    if ref_audio is None:
        console.print("[red]Provide either --youtube-url or a reference audio file[/red]")
        raise typer.Exit(1)
    if not ref_audio.exists():
        console.print(f"[red]Reference audio not found: {ref_audio}[/red]")
        raise typer.Exit(1)
    if srt is None or not srt.exists():
        console.print(f"[red]SRT file not found: {srt}[/red]")
        raise typer.Exit(1)

    launch_app(ref_audio, srt, output_dir, youtube_url=youtube_url, persona=persona, start_tab="record")


@app.command()
def gui(
    tab: str = typer.Option("dashboard", help="Start tab: record, tts-compare, dashboard, rvc-sweep"),
) -> None:
    """Launch unified voice-lab app (KDE/QML).

    Opens a tabbed window with Record, TTS Compare, Dashboard, and RVC Sweep tabs.
    Alias for: voice-lab app --tab <tab>

    Usage:
        voice-lab gui
        voice-lab gui --tab tts-compare
    """
    try:
        from app import launch_app
    except ImportError:
        console.print("[red]PySide6 required for GUI. Install: uv sync --extra editor[/red]")
        raise typer.Exit(1)

    launch_app(start_tab=tab)


# --- Quality Gate commands ---


# --- Follow-Along Session commands ---


@app.command()
def follow(
    clip: Path = typer.Option(..., help="Audio clip to play"),
    srt: Path = typer.Option(..., help="SRT subtitle file"),
    stem: Optional[Path] = typer.Option(None, help="Original vocals stem for comparison"),
    persona: str = typer.Option("embry", help="Persona name"),
    device: Optional[str] = typer.Option(None, help="Mic device name"),
    headphones: Optional[str] = typer.Option(None, help="Headphone sink name"),
    output_dir: Optional[Path] = typer.Option(None, "--output", help="Output directory"),
) -> None:
    """Play clip + record simultaneously with SRT karaoke display."""
    from session import run_follow_along

    run_follow_along(
        clip_path=clip,
        srt_path=srt,
        stem_path=stem,
        persona=persona,
        device=device,
        headphones=headphones,
        output_dir=output_dir,
    )


# --- Voice Lesson commands ---


@app.command()
def lesson(
    session_dir: Path = typer.Argument(..., help="Session output directory"),
    persona: str = typer.Option("embry", help="Persona name"),
    source: str = typer.Option("", help="Source content (e.g. movie title)"),
    scene: str = typer.Option("", help="Scene identifier"),
    prompt: Optional[str] = typer.Option(None, help="Custom learning prompt text"),
    registers: Optional[str] = typer.Option(None, help="Voice registers (comma-separated)"),
    emotions: Optional[str] = typer.Option(None, help="Emotions (comma-separated)"),
    qwen3_ready: bool = typer.Option(False, "--qwen3-ready", help="Resample to 24kHz mono for Qwen3-TTS"),
) -> None:
    """Assemble a voice lesson package for Horus."""
    from lesson import create_lesson

    reg_list = [r.strip() for r in registers.split(",")] if registers else []
    emo_list = [e.strip() for e in emotions.split(",")] if emotions else []

    create_lesson(
        session_dir=session_dir,
        persona=persona,
        source=source,
        scene=scene,
        registers=reg_list,
        emotions=emo_list,
        custom_prompt=prompt,
        qwen3_ready=qwen3_ready,
    )


@app.command()
def lessons(
    persona: str = typer.Option("embry", help="Persona name"),
) -> None:
    """List all voice lessons for a persona."""
    from lesson import print_lessons

    print_lessons(persona)


# --- Quality Gate commands ---


@app.command()
def gate(
    audio: Path = typer.Argument(..., help="Audio file or segments directory"),
    reference: Optional[Path] = typer.Option(None, help="Reference audio for similarity"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """Per-segment quality gate."""
    from quality_gate import check_segment, check_session, print_gate_report

    if audio.is_dir():
        ref_dir = Path(str(reference)) if reference else None
        report = check_session(audio, ref_dir)
    else:
        result = check_segment(audio, reference)
        from quality_gate import GateReport
        report = GateReport(
            total_segments=1,
            passed_segments=1 if result.passed else 0,
            failed_segments=0 if result.passed else 1,
            overall_score=result.score,
            results=[result],
        )

    if json_output:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print_gate_report(report)


if __name__ == "__main__":
    app()
