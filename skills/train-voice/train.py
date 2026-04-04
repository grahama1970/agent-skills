#!/usr/bin/env python3
"""
train-voice: Unified voice training orchestrator.

Combines PersonaPlex (real-time) and Qwen3-TTS (recorded) training
from a single workflow.
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from loguru import logger as log

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

app = typer.Typer(help="Unified voice training for personas")
console = Console()

# Paths
_EMBRY_STORAGE = Path(os.environ.get("EMBRY_STORAGE", "/mnt/storage12tb"))
VOICE_STORAGE = Path(os.environ.get("VOICE_STORAGE", str(_EMBRY_STORAGE / "media/personas")))
PERSONAPLEX_CACHE = Path(os.environ.get("PERSONAPLEX_CACHE", Path.home() / ".cache/personaplex"))
SKILLS_DIR = Path(__file__).parent.parent

# Fallback for systems without 12TB storage
if not VOICE_STORAGE.exists():
    VOICE_STORAGE = Path.home() / "personas"


@dataclass
class VoiceReference:
    """A voice reference (actor + register)."""
    actor: str
    register: str = "default"
    clips: list[Path] = field(default_factory=list)
    youtube_urls: list[str] = field(default_factory=list)


@dataclass
class VoiceStatus:
    """Status of voice training for a persona."""
    persona: str
    personaplex_ready: bool = False
    personaplex_registers: list[str] = field(default_factory=list)
    qwen3_ready: bool = False
    qwen3_model_path: Optional[str] = None
    qwen3_epochs_completed: int = 0
    qwen3_epochs_total: int = 0
    qwen3_training_pid: Optional[int] = None
    voice_design_exists: bool = False


def get_persona_dir(persona: str) -> Path:
    """Get the storage directory for a persona."""
    slug = persona.lower().replace(" ", "_")
    return VOICE_STORAGE / slug


def parse_references(refs_str: str) -> list[VoiceReference]:
    """Parse reference string like 'Actor1:register1,Actor2:register2'."""
    refs = []
    for ref in refs_str.split(","):
        ref = ref.strip()
        if ":" in ref:
            actor, register = ref.split(":", 1)
        else:
            actor, register = ref, "default"
        refs.append(VoiceReference(actor=actor.strip(), register=register.strip()))
    return refs


def discover_youtube_clips(actor: str, cache_dir: Path, max_clips: int = 3) -> list[Path]:
    """Search YouTube and download reference clips for an actor.

    Delegates to canonical ingest-youtube skill for search and download.
    """
    # Import canonical ingest-youtube functions
    _iy_dir = str(SKILLS_DIR / "ingest-youtube")
    if _iy_dir not in sys.path:
        sys.path.insert(0, _iy_dir)
    from youtube_transcripts.downloader import search_videos, download_audio

    actor_slug = actor.lower().replace(" ", "_")
    audio_dir = cache_dir / "audio" / actor_slug
    audio_dir.mkdir(parents=True, exist_ok=True)

    existing = list(audio_dir.glob("*.wav"))
    if existing:
        console.print(f"  [dim]Found {len(existing)} cached clips for {actor}[/dim]")
        return existing[:max_clips]

    console.print(f"  [yellow]Searching YouTube for {actor} interview clips...[/yellow]")

    try:
        search_results = search_videos(f"{actor} interview", max_results=max_clips)
        if not search_results or (search_results and "error" in search_results[0]):
            console.print(f"  [red]YouTube search failed[/red]")
            return []

        clips = []
        for entry in search_results[:max_clips]:
            video_id = entry.get("id", "")
            if not video_id:
                continue

            output_path = audio_dir / f"{video_id}.wav"
            if output_path.exists():
                clips.append(output_path)
                continue

            console.print(f"  [dim]Downloading {video_id}...[/dim]")

            audio_path, error = download_audio(video_id, audio_dir)
            if audio_path and audio_path.exists():
                clips.append(audio_path)

        return clips

    except Exception as e:
        console.print(f"  [red]Error discovering clips: {e}[/red]")
        return []


def cleanup_gpu_memory():
    """Clear GPU memory between major operations."""
    try:
        import torch
        import gc
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.synchronize()
    except Exception as e:
        logger.debug("import failed: {}", e)


def extract_personaplex_embedding(audio_path: Path, output_path: Path) -> bool:
    """Extract PersonaPlex speaker embedding from audio."""
    try:
        import torch
        from resemblyzer import VoiceEncoder, preprocess_wav

        encoder = VoiceEncoder()
        wav = preprocess_wav(str(audio_path))
        embedding = encoder.embed_utterance(wav)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        torch.save(torch.from_numpy(embedding), output_path)
        return True

    except ImportError:
        console.print("[red]Missing: pip install resemblyzer torch[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Embedding extraction failed: {e}[/red]")
        return False


def generate_training_data_from_clips(
    persona: str, references: list[VoiceReference], output_dir: Path
) -> Optional[Path]:
    """Generate training JSONL from audio clips using Whisper transcription."""
    try:
        import whisper
    except ImportError:
        console.print("  [red]Missing: pip install openai-whisper[/red]")
        return None

    # Collect all audio clips
    all_clips = []
    for ref in references:
        all_clips.extend(ref.clips)

    if not all_clips:
        console.print("  [yellow]No audio clips found for transcription[/yellow]")
        return None

    console.print(f"  [dim]Transcribing {len(all_clips)} clips with Whisper...[/dim]")

    # Load Whisper model (medium for balance of speed/quality)
    model = whisper.load_model("medium", device="cuda")

    training_entries = []
    slug = persona.lower().replace(" ", "_")

    # Official best practice: use the same ref_audio for ALL samples
    # This will be set to the first valid segment extracted
    canonical_ref_audio: Optional[str] = None

    for i, clip_path in enumerate(all_clips):
        console.print(f"    [{i+1}/{len(all_clips)}] Transcribing {clip_path.name}...")

        try:
            # Transcribe with Whisper
            result = model.transcribe(str(clip_path), language="en", word_timestamps=True)

            # Create training entries from segments
            for seg in result.get("segments", []):
                text = seg.get("text", "").strip()
                if len(text) < 10:  # Skip very short segments
                    continue

                start = seg.get("start", 0)
                end = seg.get("end", 0)
                duration = end - start

                # Skip segments that are too short or too long for TTS training
                if duration < 1.0 or duration > 15.0:
                    continue

                # Extract audio segment to separate file
                segment_filename = f"{clip_path.stem}_seg{len(training_entries):04d}.wav"
                segment_path = output_dir / "segments" / segment_filename
                segment_path.parent.mkdir(parents=True, exist_ok=True)

                # Extract segment with ffmpeg
                ffmpeg_result = subprocess.run(
                    ["ffmpeg", "-y", "-i", str(clip_path),
                     "-ss", str(start), "-t", str(duration),
                     "-ar", "24000", "-ac", "1",  # 24kHz mono for Qwen3-TTS
                     str(segment_path)],
                    capture_output=True, timeout=30,
                    env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
                )

                if ffmpeg_result.returncode == 0 and segment_path.exists():
                    # Use first valid segment as canonical ref_audio for all samples
                    # Official best practice: same ref_audio for ALL samples improves consistency
                    if canonical_ref_audio is None:
                        canonical_ref_audio = str(segment_path)
                        console.print(f"    [dim]Using as reference audio: {segment_path.name}[/dim]")

                    training_entries.append({
                        "audio_file": str(segment_path),
                        "audio": str(segment_path),  # Qwen3-TTS prepare_data format
                        "ref_audio": canonical_ref_audio,  # Same ref for ALL samples (official best practice)
                        "text": text,
                        "speaker": slug,
                        "duration": duration,
                    })

        except Exception as e:
            console.print(f"    [yellow]Failed to transcribe {clip_path.name}: {e}[/yellow]")
            continue

    # Clean up Whisper model from GPU
    del model
    cleanup_gpu_memory()

    if not training_entries:
        console.print("  [yellow]No valid training segments extracted[/yellow]")
        return None

    console.print(f"  [green]Extracted {len(training_entries)} training segments[/green]")

    # Write training JSONL
    output_path = output_dir / f"{slug}_combined.jsonl"
    with open(output_path, "w") as f:
        for entry in training_entries:
            f.write(json.dumps(entry) + "\n")

    return output_path


def prepare_qwen3_training_data(persona: str, references: list[VoiceReference]) -> Optional[Path]:
    """Prepare training data for Qwen3-TTS."""
    persona_dir = get_persona_dir(persona)
    tts_training_dir = persona_dir / "tts_training"
    qwen3_dir = persona_dir / "qwen3_tts"

    # Check if training data already exists
    manifest_path = qwen3_dir / f"{persona.lower()}_manifest_qwen3.jsonl"
    if manifest_path.exists():
        console.print(f"  [dim]Using existing training manifest: {manifest_path}[/dim]")
        return manifest_path

    # Check for raw training data
    raw_manifest = tts_training_dir / f"{persona.lower()}_combined.jsonl"
    if not raw_manifest.exists():
        console.print(f"  [yellow]No training data found at {raw_manifest}[/yellow]")
        console.print("  [dim]Generating from reference clips via transcription...[/dim]")

        # Generate training JSONL from reference clips with Whisper transcription
        if not references:
            console.print("  [red]No reference clips available for transcription[/red]")
            return None

        tts_training_dir.mkdir(parents=True, exist_ok=True)
        generated = generate_training_data_from_clips(persona, references, tts_training_dir)
        if not generated:
            console.print("  [yellow]No training data available[/yellow]")
            return None
        raw_manifest = generated

    # Convert to Qwen3 format with audio_codes
    qwen3_dir.mkdir(parents=True, exist_ok=True)

    # Use local copy of Qwen3-TTS finetuning scripts
    train_voice_skill = Path(__file__).parent
    prepare_script = train_voice_skill / "Qwen3-TTS" / "finetuning" / "prepare_data.py"

    if not prepare_script.exists():
        console.print(f"  [red]Qwen3-TTS prepare_data.py not found at {prepare_script}[/red]")
        return None

    console.print("  [dim]Converting to Qwen3-TTS format with audio_codes...[/dim]")

    # Use miniconda Python which has qwen_tts installed
    python_exe = Path.home() / "miniconda3" / "bin" / "python"
    if not python_exe.exists():
        python_exe = Path(sys.executable)

    result = subprocess.run(
        [str(python_exe), str(prepare_script),
         "--input_jsonl", str(raw_manifest),
         "--output_jsonl", str(manifest_path)],
        capture_output=True, text=True, timeout=1800,  # Longer timeout for audio encoding
        cwd=str(train_voice_skill / "Qwen3-TTS" / "finetuning"),
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )

    if result.returncode != 0:
        console.print(f"  [red]Conversion failed: {result.stderr[:500]}[/red]")
        return None

    return manifest_path


def run_qwen3_training(persona: str, manifest_path: Path, epochs: int = 5, background: bool = True) -> Optional[int]:
    """Run Qwen3-TTS training."""
    persona_dir = get_persona_dir(persona)
    output_dir = persona_dir / "qwen3_tts" / "model"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Use local copy of Qwen3-TTS finetuning scripts (modified for 24GB GPU)
    train_voice_skill = Path(__file__).parent
    sft_script = train_voice_skill / "Qwen3-TTS" / "finetuning" / "sft_12hz.py"

    if not sft_script.exists():
        console.print(f"  [red]sft_12hz.py not found at {sft_script}[/red]")
        return None

    log_path = persona_dir / "qwen3_tts" / "training.log"

    # Use 1.7B model with gradient checkpointing for 24GB GPUs
    cmd = [
        sys.executable, str(sft_script),
        "--init_model_path", "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
        "--output_model_path", str(output_dir),
        "--train_jsonl", str(manifest_path),
        "--speaker_name", persona.lower().replace(" ", "_"),
        "--batch_size", "1",
        "--gradient_accumulation_steps", "8",
        "--gradient_checkpointing",  # Critical for 24GB GPU
        "--lr", "2e-5",
        "--num_epochs", str(epochs),
    ]

    if background:
        with open(log_path, "w") as log_file:
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=str(train_voice_skill / "Qwen3-TTS" / "finetuning"),
                start_new_session=True,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
        console.print(f"  [green]Training started in background (PID {process.pid})[/green]")
        console.print(f"  [dim]Log: {log_path}[/dim]")
        return process.pid
    else:
        result = subprocess.run(cmd, cwd=str(train_voice_skill / "Qwen3-TTS" / "finetuning"),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )
        return 0 if result.returncode == 0 else None


def get_voice_status(persona: str) -> VoiceStatus:
    """Get current voice training status for a persona."""
    persona_dir = get_persona_dir(persona)
    slug = persona.lower().replace(" ", "_")

    status = VoiceStatus(persona=persona)

    # Check PersonaPlex
    voices_dir = persona_dir / "personaplex" / "voices"
    if voices_dir.exists():
        for pt_file in voices_dir.glob("*.pt"):
            register = pt_file.stem.replace(f"{slug}_", "")
            status.personaplex_registers.append(register)
        status.personaplex_ready = len(status.personaplex_registers) > 0

    # Check Qwen3-TTS
    model_dir = persona_dir / "qwen3_tts" / "model"
    if model_dir.exists():
        checkpoints = list(model_dir.glob("checkpoint-epoch-*"))
        if checkpoints:
            status.qwen3_ready = True
            status.qwen3_model_path = str(max(checkpoints, key=lambda p: p.stat().st_mtime))
            status.qwen3_epochs_completed = len(checkpoints)

    # Check for running training
    try:
        result = subprocess.run(
            ["pgrep", "-f", f"sft_12hz.*{slug}"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            status.qwen3_training_pid = int(result.stdout.strip().split()[0],
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )
    except Exception as e:
        logger.debug("result extraction failed: {}", e)

    # Check voice design
    design_file = persona_dir / "voice_design.json"
    status.voice_design_exists = design_file.exists()

    return status


@app.command()
def train(
    persona: str,
    references: str = typer.Option(None, "--references", "-r", help="Actor:register pairs"),
    persona_type: str = typer.Option("fictional", "--type", "-t", help="fictional, learning, narrator"),
    skip_personaplex: bool = typer.Option(False, "--skip-personaplex", help="Skip PersonaPlex"),
    skip_qwen3: bool = typer.Option(False, "--skip-qwen3", help="Skip Qwen3-TTS"),
    epochs: int = typer.Option(5, "--epochs", "-e", help="Qwen3-TTS epochs"),
    background: bool = typer.Option(True, "--background/--foreground", help="Run in background"),
):
    """Train voice from known references."""
    console.print(Panel(f"[bold]Training voice for {persona}[/bold]", style="blue"))

    _steps = (0 if skip_personaplex else 2) + (0 if skip_qwen3 else 2)
    _monitor = TaskClient(f"train-voice/{persona}", total=max(_steps, 1), description=f"Voice training {persona}") if TaskClient else None

    persona_dir = get_persona_dir(persona)
    slug = persona.lower().replace(" ", "_")

    # Parse references
    refs = []
    if references:
        refs = parse_references(references)
        console.print(f"[dim]References: {', '.join(f'{r.actor}:{r.register}' for r in refs)}[/dim]")

    # Step 1: Discover/download reference clips
    if refs and not skip_personaplex:
        console.print("\n[bold]Step 1: Discovering reference clips[/bold]")
        for ref in refs:
            clips = discover_youtube_clips(ref.actor, PERSONAPLEX_CACHE)
            ref.clips = clips
            console.print(f"  {ref.actor}: {len(clips)} clips")

        if _monitor:
            _monitor.update(item="clips discovered")

    # Step 2: Extract PersonaPlex embeddings
    if refs and not skip_personaplex:
        console.print("\n[bold]Step 2: Extracting PersonaPlex embeddings[/bold]")
        voices_dir = persona_dir / "personaplex" / "voices"
        voices_dir.mkdir(parents=True, exist_ok=True)

        for ref in refs:
            if not ref.clips:
                console.print(f"  [yellow]No clips for {ref.actor}, skipping[/yellow]")
                continue

            output_path = voices_dir / f"{slug}_{ref.register}.pt"
            console.print(f"  Extracting {ref.register} from {ref.actor}...")

            if extract_personaplex_embedding(ref.clips[0], output_path):
                console.print(f"    [green]Saved: {output_path.name}[/green]")
            else:
                console.print(f"    [red]Failed[/red]")

        # Clean up GPU memory after PersonaPlex extraction
        cleanup_gpu_memory()

        if _monitor:
            _monitor.update(item="embeddings extracted")

    # Step 3: Prepare Qwen3-TTS training data
    if not skip_qwen3:
        console.print("\n[bold]Step 3: Preparing Qwen3-TTS training data[/bold]")
        manifest_path = prepare_qwen3_training_data(persona, refs)

        if manifest_path:
            console.print(f"  [green]Manifest ready: {manifest_path}[/green]")
            if _monitor:
                _monitor.update(item="manifest prepared")

            # Step 4: Run Qwen3-TTS training
            console.print("\n[bold]Step 4: Training Qwen3-TTS[/bold]")
            pid = run_qwen3_training(persona, manifest_path, epochs, background)

            if pid:
                console.print(f"  [green]Training started![/green]")
                if _monitor:
                    _monitor.update(item="qwen3 training launched")
        else:
            console.print("  [yellow]No training data available[/yellow]")

    if _monitor:
        _monitor.finish()

    # Summary
    console.print("\n[bold]Summary[/bold]")
    status = get_voice_status(persona)

    if status.personaplex_ready:
        console.print(f"  PersonaPlex: [green]{len(status.personaplex_registers)} registers ready[/green]")
    else:
        console.print("  PersonaPlex: [yellow]Not ready[/yellow]")

    if status.qwen3_training_pid:
        console.print(f"  Qwen3-TTS: [yellow]Training (PID {status.qwen3_training_pid})[/yellow]")
    elif status.qwen3_ready:
        console.print(f"  Qwen3-TTS: [green]Ready ({status.qwen3_epochs_completed} epochs)[/green]")
    else:
        console.print("  Qwen3-TTS: [yellow]Not ready[/yellow]")


@app.command()
def status(persona: str):
    """Check training status for a persona."""
    s = get_voice_status(persona)

    console.print(Panel(f"[bold]Voice Status: {persona}[/bold]", style="blue"))

    # PersonaPlex
    console.print("\n[bold]PersonaPlex (Real-time)[/bold]")
    if s.personaplex_ready:
        for reg in s.personaplex_registers:
            console.print(f"  [green]\u2713[/green] {reg}")
    else:
        console.print("  [dim]No embeddings extracted[/dim]")

    # Qwen3-TTS
    console.print("\n[bold]Qwen3-TTS (Recorded)[/bold]")
    if s.qwen3_training_pid:
        console.print(f"  [yellow]\u25cf Training in progress (PID {s.qwen3_training_pid})[/yellow]")
        console.print(f"    Epochs: {s.qwen3_epochs_completed}")
    elif s.qwen3_ready:
        console.print(f"  [green]\u2713 Ready[/green]")
        console.print(f"    Model: {s.qwen3_model_path}")
        console.print(f"    Epochs: {s.qwen3_epochs_completed}")
    else:
        console.print("  [dim]Not trained[/dim]")

    # Voice Design
    if s.voice_design_exists:
        console.print("\n[dim]Voice design file exists (from /interview)[/dim]")


@app.command("list")
def list_voices(json_output: bool = typer.Option(False, "--json")):
    """List all voices with status."""

    if not VOICE_STORAGE.exists():
        console.print("[yellow]No personas directory found[/yellow]")
        return

    personas = [d.name for d in VOICE_STORAGE.iterdir() if d.is_dir()]

    if json_output:
        data = []
        for p in personas:
            s = get_voice_status(p)
            data.append({
                "persona": p,
                "personaplex": {"ready": s.personaplex_ready, "registers": s.personaplex_registers},
                "qwen3": {"ready": s.qwen3_ready, "training": s.qwen3_training_pid is not None},
                "designed": s.voice_design_exists,
            })
        print(json.dumps(data, indent=2))
        return

    table = Table(title="Voice Training Status")
    table.add_column("Persona", style="cyan")
    table.add_column("PersonaPlex")
    table.add_column("Qwen3-TTS")
    table.add_column("Status")

    for p in sorted(personas):
        s = get_voice_status(p)

        plex = f"{len(s.personaplex_registers)} reg" if s.personaplex_ready else "-"

        if s.qwen3_training_pid:
            qwen = f"Training..."
            status_str = "[yellow]TRAINING[/yellow]"
        elif s.qwen3_ready:
            qwen = f"{s.qwen3_epochs_completed} epochs"
            status_str = "[green]READY[/green]"
        elif s.voice_design_exists:
            qwen = "-"
            status_str = "[blue]DESIGNED[/blue]"
        else:
            qwen = "-"
            status_str = "[dim]NONE[/dim]"

        table.add_row(p, plex, qwen, status_str)

    console.print(table)


@app.command()
def test(
    persona: str,
    text: str = typer.Option(..., "--text", "-t", help="Text to synthesize"),
    register: str = typer.Option("default", "--register", "-r"),
    output: str = typer.Option(None, "--output", "-o"),
    use_personaplex: bool = typer.Option(False, "--personaplex"),
):
    """Generate test audio from trained voice."""
    s = get_voice_status(persona)

    if use_personaplex:
        if not s.personaplex_ready:
            console.print("[red]PersonaPlex not ready for this persona[/red]")
            raise typer.Exit(1)
        console.print("[yellow]PersonaPlex test not implemented yet[/yellow]")
    else:
        if not s.qwen3_ready:
            console.print("[red]Qwen3-TTS not trained for this persona[/red]")
            raise typer.Exit(1)

        # Use tts-train synthesize command
        console.print(f"[dim]Synthesizing with Qwen3-TTS...[/dim]")

        output_file = output or f"/tmp/{persona.lower()}_test.wav"

        tts_train = SKILLS_DIR / "tts-train" / "run.sh"
        result = subprocess.run(
            [str(tts_train), "synthesize",
             "--text", text,
             "--output", output_file],
            capture_output=True, text=True
        )

        if result.returncode == 0:
            console.print(f"[green]Saved: {output_file}[/green]")
        else:
            console.print(f"[red]Synthesis failed: {result.stderr}[/red]")


if __name__ == "__main__":
    app()
