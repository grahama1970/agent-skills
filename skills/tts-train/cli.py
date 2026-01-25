import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Union

import typer
from loguru import logger
from rich import print as rprint
from rich import print as rprint
from rich.table import Table
import torch

app = typer.Typer(add_completion=False, no_args_is_help=True)


# -----------------------------
# Configuration
# -----------------------------

REPO_URL = "https://github.com/QwenLM/Qwen3-TTS.git"
DEFAULT_REF = "c25ce958eaa3eef93bd14dcbfb1f308138fd5040" # Pinned SHA
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
THIRD_PARTY_DIR = PROJECT_ROOT / "third_party"
QWEN_REPO_DIR = THIRD_PARTY_DIR / "Qwen3-TTS"

# -----------------------------
# Utilities
# -----------------------------

def run(cmd: List[str], cwd: Optional[Path] = None, env: Optional[dict] = None) -> None:
    path_str = str(cwd) if cwd else os.getcwd()
    logger.info(f"Running in {path_str}: {' '.join(cmd)}")
    subprocess.run(cmd, cwd=path_str, check=True, env=env)


def has_bin(name: str) -> bool:
    return shutil.which(name) is not None


def safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def get_repo_sha(repo_dir: Path) -> str:
    if not (repo_dir / ".git").exists():
        return "unknown"
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo_dir).decode().strip()

# -----------------------------
# Commands
# -----------------------------

@app.command()
def ensure_repo(
    ref: str = typer.Option(DEFAULT_REF, help="Git ref to checkout."),
    force: bool = typer.Option(False, help="Force fresh clone."),
):
    """Clone or update Qwen3-TTS repository."""
    safe_mkdir(THIRD_PARTY_DIR)
    
    if force and QWEN_REPO_DIR.exists():
        shutil.rmtree(QWEN_REPO_DIR)

    if not QWEN_REPO_DIR.exists():
        run(["git", "clone", REPO_URL, str(QWEN_REPO_DIR)])
    
    run(["git", "fetch", "--all"], cwd=QWEN_REPO_DIR)
    run(["git", "checkout", ref], cwd=QWEN_REPO_DIR)
    
    sha = get_repo_sha(QWEN_REPO_DIR)
    sha = get_repo_sha(QWEN_REPO_DIR)
    rprint(f"[green]Repo ready:[/green] {QWEN_REPO_DIR}")
    rprint(f"[blue]Commit SHA:[/blue] {sha}")

    # Apply patches if needed
    patch_file = Path(__file__).resolve().parent / "patches" / "001-fix-sft-optimizations.patch"
    if patch_file.exists():
        rprint(f"[blue]Applying patch:[/blue] {patch_file.name}")
        # Check if patch is already applied to avoid errors (or use --forward to tolerate)
        # We try to apply; if it fails, we assume it's already applied or conflict.
        # Check integrity first
        val = subprocess.run(["git", "apply", "--check", str(patch_file)], cwd=QWEN_REPO_DIR, capture_output=True)
        if val.returncode == 0:
            run(["git", "apply", str(patch_file)], cwd=QWEN_REPO_DIR)
            rprint("[green]Patch applied successfully.[/green]")
        else:
            rprint("[yellow]Patch possibly already applied or conflict (skipping).[/yellow]")
    else:
        rprint("[yellow]No patch file found.[/yellow]")


@app.command()
def doctor():
    """Environment sanity checks."""
    table = Table(title="Qwen3-TTS Doctor")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Details")

    table.add_row("ffmpeg", "✅" if has_bin("ffmpeg") else "❌", "Required for splicing")
    table.add_row("uv", "✅" if has_bin("uv") else "❌", "Required for env management")
    
    try:
        import torch
        table.add_row("torch", "✅", f"{torch.__version__} (CUDA: {torch.cuda.is_available()})")
    except ImportError as e:
        table.add_row("torch", "❌", str(e))

    if QWEN_REPO_DIR.exists():
        sha = get_repo_sha(QWEN_REPO_DIR)
        table.add_row("Qwen3-TTS Repo", "✅", f"SHA: {sha[:7]}...")
        sys.path.append(str(QWEN_REPO_DIR))
        try:
            from qwen_tts import Qwen3TTSTokenizer
            table.add_row("Import: Tokenizer", "✅", "Success")
        except Exception as e:
            table.add_row("Import: Tokenizer", "⚠️", str(e))
    else:
        table.add_row("Qwen3-TTS Repo", "❌", "Run 'ensure-repo' first")
    
    deps = ["tensorboard", "uvicorn", "fastapi", "optuna", "onnxruntime"]
    for d in deps:
        if has_bin(d) or shutil.which(d): # uvicorn is a bin, fastapi is lib, logic imperfect but sufficient for uvx environment
             table.add_row(d, "✅", "Ready")
        else:
             # Basic check for python module if bin check fails
             try:
                 __import__(d)
                 table.add_row(d, "✅", "Module Ready")
             except:
                 table.add_row(d, "❓", "Check install")

    rprint(table)


@app.command()
def prep(
    audio_dir: Path = typer.Option(..., help="Directory of raw narration audio."),
    out_dir: Path = typer.Option(..., help="Output directory."),
    transcribe: bool = typer.Option(False, help="Use WhisperX for VAD+ASR."),
    min_sec: float = typer.Option(2.0),
    max_sec: float = typer.Option(12.0),
    base_model: str = typer.Option("Qwen/Qwen3-TTS-Tokenizer-12Hz", help="Tokenizer model."),
    limit: Optional[int] = typer.Option(None, help="Limit number of segments (for testing)."),
):
    """
    Prepare dataset with memory-safe slicing and mandatory 12Hz tokenization.
    output: manifest.jsonl with {audio, text, audio_codes}
    """
    safe_mkdir(out_dir)
    wav_out = out_dir / "wavs"
    safe_mkdir(wav_out)
    manifest_path = out_dir / "manifest.jsonl"

    segments = [] 

    # 1. Transcription First (WhisperX uses GPU via Docker)
    if transcribe:
        rprint("[yellow]Using thomasvvugt/whisperx:cuda118 pre-built image...[/yellow]")
        # We no longer need to build a custom image. thomasvvugt/whisperx is reputable.

        rprint("[yellow]Running WhisperX (VAD+ASR) in Docker...[/yellow]")
        whisper_in_dir = out_dir / "split_raw"
        safe_mkdir(whisper_in_dir)
        whisper_out = out_dir / "whisper_raw"
        safe_mkdir(whisper_out)
        
        # 2a. Pre-process / Chunk large files
        source_files = []
        for ext in ("*.wav", "*.mp3", "*.m4b", "*.flac"):
            source_files.extend(list(audio_dir.glob(ext)))
            
        rprint(f"Found {len(source_files)} source files.")
        
        processed_sources = []
        
        for sf_path in source_files:
            # Chunking 20m segments
            chunk_pattern = whisper_in_dir / f"{sf_path.stem}_%03d.wav"
            if not list(whisper_in_dir.glob(f"{sf_path.stem}_*.wav")):
                rprint(f"Chunking large file: {sf_path.name}...")
                cmd = [
                    "ffmpeg", "-y", "-v", "error",
                    "-i", str(sf_path),
                    "-f", "segment",
                    "-segment_time", "1200", 
                    "-c", "pcm_s16le", "-ar", "16000", "-ac", "1",
                    str(chunk_pattern)
                ]
                run(cmd)
            
            processed_sources.extend(sorted(list(whisper_in_dir.glob(f"{sf_path.stem}_*.wav"))))

        # 2b. Run WhisperX on chunks using Docker
        for af in processed_sources:
            json_path = whisper_out / (af.stem + ".json")
            if not json_path.exists():
                rprint(f"Transcribing {af.name} (Docker)...")
                # Bind-mount input and output dirs
                # We use absolute paths for Docker mounts
                abs_in = str(whisper_in_dir.resolve())
                abs_out = str(whisper_out.resolve())
                
                cmd = [
                    "docker", "run", "--rm", "--gpus", "all",
                    "--entrypoint", "whisperx",
                    "-v", f"{abs_in}:/app/in",
                    "-v", f"{abs_out}:/app/out",
                    "ghcr.io/jim60105/whisperx:large-v2-en",
                    "--model", "large-v2",
                    "--output_dir", "/app/out",
                    "--output_format", "json",
                    "--compute_type", "int8",
                    f"/app/in/{af.name}"
                ]
                try:
                    run(cmd)
                except subprocess.CalledProcessError:
                    logger.error(f"Failed to transcribe {af.name} via Docker, skipping.")
                    continue

            if json_path.exists():
                data = json.loads(json_path.read_text())
                for seg in data['segments']:
                    dur = seg['end'] - seg['start']
                    if min_sec <= dur <= max_sec:
                        segments.append((af, seg['start'], seg['end'], seg['text'].strip()))
    else:
        rprint("[red]--transcribe is required for unsegmented audio processing.[/red]")
        return
        
    if limit:
        segments = segments[:limit]
        rprint(f"[yellow]Limiting to {limit} segments.[/yellow]")

    # 2. Tokenization Second (Qwen uses GPU)
    # Only load tokenizer now that WhisperX is done.
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        
    sys.path.append(str(QWEN_REPO_DIR))
    try:
        from qwen_tts import Qwen3TTSTokenizer
    except ImportError:
        rprint("[red]Import failed. Run 'ensure-repo' first.[/red]")
        raise typer.Exit(1)
        
    rprint(f"Loading Tokenizer: {base_model}...")
    tokenizer = Qwen3TTSTokenizer.from_pretrained(base_model, device_map="auto")

    rprint(f"Processing {len(segments)} segments...")
    
    with manifest_path.open("w", encoding="utf-8") as manuf:
        for i, (src, start, end, text) in enumerate(segments):
            dur = end - start
            seg_name = f"{src.stem}_{i:05d}.wav"
            seg_path = wav_out / seg_name
            
            if not seg_path.exists():
                cmd = [
                    "ffmpeg", "-y", "-v", "error",
                    "-ss", f"{start:.3f}",
                    "-t", f"{dur:.3f}",
                    "-i", str(src),
                    "-ac", "1", "-ar", "24000",
                    str(seg_path)
                ]
                subprocess.run(cmd, check=True)
            
            try:
                enc = tokenizer.encode(str(seg_path))
                # audio_codes is List[torch.LongTensor] each (codes_len, num_quantizers)
                # For single audio input, we get a list with one element
                codes = enc.audio_codes[0].cpu().tolist()
                
                rec = {
                    "audio": str(seg_path),
                    "text": text,
                    "audio_codes": codes,
                    "duration": dur
                }
                manuf.write(json.dumps(rec, ensure_ascii=False) + "\n")
                
            except Exception as e:
                logger.error(f"Failed to tokenize {seg_name}: {e}")

    rprint(f"[green]Manifest written:[/green] {manifest_path}")


@dataclass
class Trial:
    name: str; lr: float; lora_r: int; lora_alpha: int; warmup_ratio: float

def call_qwen_finetune(
    script_rel: str,
    out_dir: Path,
    data_manifest: Path,
    base_model: str,
    steps: int,
    trial: Optional[Trial] = None,
    extra: List[str] = [],
):
    script = QWEN_REPO_DIR / script_rel
    if not script.exists():
        rprint(f"[red]Missing script:[/red] {script}")
        rprint("Did you run 'ensure-repo'?")
        raise typer.Exit(1)
        
    cmd = [sys.executable, str(script)]
    cmd.extend(["--init_model_path", base_model])
    cmd.extend(["--output_model_path", str(out_dir)])
    cmd.extend(["--train_jsonl", str(data_manifest)])
    
    if trial:
         cmd.extend(["--lr", str(trial.lr)])
    
    cmd.extend(extra)
    safe_mkdir(out_dir)
    run(cmd, cwd=QWEN_REPO_DIR)


@app.command()
def smoke(
    base_model: str = typer.Option("Qwen/Qwen3-TTS-12Hz-0.6B-Base", help="Base model ID (0.6B default)."),
    data_manifest: Path = typer.Option(..., help="Path to manifest.jsonl"),
    out_dir: Path = typer.Option(..., help="Output directory"),
):
    """Run a short smoke test."""
    rprint("[bold]Running Smoke Test...[/bold]")
    trial = Trial("smoke", 2e-4, 8, 16, 0.05)
    call_qwen_finetune(
        script_rel="finetuning/sft_12hz.py",
        out_dir=out_dir,
        data_manifest=data_manifest,
        base_model=base_model,
        steps=200, 
        trial=trial,
        extra=["--num_epochs", "1"] 
    )

@app.command()
def train(
    base_model: str = typer.Option("Qwen/Qwen3-TTS-12Hz-0.6B-Base", help="Base model ID (0.6B default)."),
    data_manifest: Path = typer.Option(..., help="Path to manifest.jsonl"),
    out_dir: Path = typer.Option(..., help="Output directory"),
    epochs: int = typer.Option(5, help="Number of epochs."),
    batch_size: int = typer.Option(8, help="Per-device batch size."),
    lr: float = typer.Option(1e-4, help="Learning rate."),
):
    """Full training run."""
    rprint(f"[bold]Starting Training (0.6B Base) BS={batch_size} LR={lr}...[/bold]")
    trial = Trial("final", lr, 16, 32, 0.05) 
    
    call_qwen_finetune(
        script_rel="finetuning/sft_12hz.py",
        out_dir=out_dir,
        data_manifest=data_manifest,
        base_model=base_model,
        steps=0,
        trial=trial,
        extra=["--num_epochs", str(epochs), "--batch_size", str(batch_size)]
    )

@app.command()
def synth(
    checkpoint: str = typer.Option(..., help="Path to fine-tuned model dir."),
    text: str = typer.Option(..., help="Text to speak."),
    out: Path = typer.Option(Path("out.wav"), help="Output wav file."),
    instruct: str = typer.Option("Neutral.", help="Style instruction."),
):
    """Synthesize audio (Offline)."""
    sys.path.append(str(QWEN_REPO_DIR))
    try:
        from qwen_tts.inference.qwen3_tts_model import Qwen3TTSModel
        import torch
        import soundfile as sf
    except ImportError:
        rprint("[red]Could not import qwen_tts.[/red]")
        raise typer.Exit(1)

    rprint(f"Loading from {checkpoint}...")
    model = Qwen3TTSModel.from_pretrained(
        checkpoint,
        device_map="auto",
        torch_dtype=torch.bfloat16
    )
    
    wavs, sr = model.generate_custom_voice(
        text=text,
        language="Auto",
        speaker="speaker_test",
        instruct=instruct
    )
    
    safe_mkdir(out.parent)
    sf.write(str(out), wavs[0], sr)
    rprint(f"[green]Saved:[/green] {out}")


@app.command()
def serve(
    checkpoint: str = typer.Option(..., help="Path to model."),
    host: str = typer.Option("0.0.0.0"),
    port: int = typer.Option(8000),
):
    """Start HTTP server for low-latency bot inference."""
    # We define app logic inside to avoid global imports slowing down CLI
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    import torch
    import io
    import soundfile as sf
    
    sys.path.append(str(QWEN_REPO_DIR))
    try:
        from qwen_tts.inference.qwen3_tts_model import Qwen3TTSModel
    except ImportError:
        rprint("[red]Import failed.[/red]")
        raise typer.Exit(1)

    app_srv = FastAPI(title="Qwen3-TTS-Server")
    
    rprint(f"[bold]Loading Model: {checkpoint}[/bold]")
    model = Qwen3TTSModel.from_pretrained(
        checkpoint,
        device_map="auto",
        torch_dtype=torch.bfloat16
    )
    model.eval()
    
    class TTSRequest(BaseModel):
        text: str
        instruct: str = "Neutral."
        speaker: str = "speaker_test"

    @app_srv.post("/v1/tts")
    async def generate_tts(req: TTSRequest):
        try:
            wavs, sr = model.generate_custom_voice(
                text=req.text,
                language="Auto",
                speaker=req.speaker,
                instruct=req.instruct
            )
            # Convert to bytes
            buf = io.BytesIO()
            sf.write(buf, wavs[0], sr, format='WAV')
            buf.seek(0)
            from fastapi.responses import Response
            return Response(content=buf.read(), media_type="audio/wav")
        except Exception as e:
            logger.error(f"TTS Error: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    rprint(f"[green]Serving on http://{host}:{port}[/green]")
    uvicorn.run(app_srv, host=host, port=port)


@app.command()
def eval(
    checkpoint: str = typer.Option(..., help="Path to model."),
    test_manifest: Path = typer.Option(..., help="Test manifest.jsonl"),
    out_dir: Path = typer.Option(..., help="Output directory."),
    count: int = typer.Option(10, help="Number of samples to evaluate."),
):
    """
    Compute WER (Word Error Rate) using WhisperX.
    Generates audio for 'count' samples from test_manifest, transcribes them, and compares text.
    """
    import jiwer
    
    safe_mkdir(out_dir)
    wav_out = out_dir / "gen_wavs"
    safe_mkdir(wav_out)
    transcripts_out = out_dir / "transcripts"
    safe_mkdir(transcripts_out)

    # 1. Load Test Data
    lines = []
    with test_manifest.open("r") as f:
        for line in f:
            if line.strip(): lines.append(json.loads(line))
    
    if count:
        lines = lines[:count]
    
    rprint(f"Evaluating {len(lines)} samples from {test_manifest}...")

    # 2. Generate Audio (Offline Inference)
    sys.path.append(str(QWEN_REPO_DIR))
    try:
        from qwen_tts.inference.qwen3_tts_model import Qwen3TTSModel
        import torch
        import soundfile as sf
    except ImportError:
        rprint("[red]Import failed.[/red]")
        raise typer.Exit(1)
        
    model = Qwen3TTSModel.from_pretrained(checkpoint, device_map="auto", torch_dtype=torch.bfloat16)
    
    generated_files = []
    references = []
    
    for i, item in enumerate(lines):
        text = item['text']
        out_wav = wav_out / f"eval_{i:04d}.wav"
        
        if not out_wav.exists():
            wavs, sr = model.generate_custom_voice(
                text=text,
                language="Auto",
                speaker="speaker_test", # Using speaker name from training
                instruct="Neutral."
            )
            sf.write(str(out_wav), wavs[0], sr)
        
        generated_files.append(str(out_wav))
        references.append(text)
    
    # 3. Transcribe Generated Audio (using WhisperX via Docker)
    rprint("[yellow]Transcribing generated audio with WhisperX...[/yellow]")
    
    for wav_path in generated_files:
        json_path = transcripts_out / (Path(wav_path).stem + ".json")
        if not json_path.exists():
            rprint(f"Transcribing {Path(wav_path).name}...")
            abs_wav_dir = str(wav_out.resolve())
            abs_transcript_dir = str(transcripts_out.resolve())
            
            cmd = [
                "docker", "run", "--rm", "--gpus", "all",
                "--entrypoint", "whisperx",
                "-v", f"{abs_wav_dir}:/app/in",
                "-v", f"{abs_transcript_dir}:/app/out",
                "ghcr.io/jim60105/whisperx:large-v2-en",
                "--model", "large-v2",
                "--output_dir", "/app/out",
                "--output_format", "json",
                "--compute_type", "int8",
                f"/app/in/{Path(wav_path).name}"
            ]
            try:
                run(cmd)
            except subprocess.CalledProcessError:
                logger.error(f"Failed to transcribe {wav_path}")
                continue
    
    # 4. Compute WER
    rprint("[yellow]Computing WER...[/yellow]")
    hypotheses = []
    for json_path in generated_files:
        json_file = transcripts_out / (Path(json_path).stem + ".json")
        if json_file.exists():
            with json_file.open("r") as f:
                data = json.load(f)
                if 'segments' in data:
                    text = " ".join([seg['text'] for seg in data['segments']])
                    hypotheses.append(text)
    
    if len(hypotheses) == len(references):
        wer = jiwer.wer(references, hypotheses)
        rprint(f"[green]WER: {wer:.4f}[/green]")
    else:
        rprint("[yellow]Warning: Mismatch in generated/transcribed count[/yellow]")
