#!/usr/bin/env python3
"""
Iterative voice training with Bayesian hyperparameter search and quality evaluation.

Consolidates the best features from tts-train's iterative_train.py into train-voice.

Two-phase workflow:
1. HYPERPARAMETER PHASE: Bayesian search for optimal training config
2. EVALUATION PHASE: Train with config, evaluate quality, iterate until threshold

Usage:
    python iterative.py train "Cate Blanchett" \
        --max-iterations 5 \
        --quality-threshold 4.0 \
        --run-hyperparameter-search \
        --hp-trials 10
"""

import json
import os
import subprocess
import sys
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

app = typer.Typer(help="Iterative voice training with quality evaluation")
console = Console()

# Paths
VOICE_STORAGE = Path(os.environ.get("VOICE_STORAGE", "/mnt/storage12tb/media/personas"))
SKILL_DIR = Path(__file__).parent
PYTHON_EXE = sys.executable

# Default evaluation phrases
DEFAULT_EVAL_PHRASES = [
    "Hello, I am testing this voice model.",
    "The quick brown fox jumps over the lazy dog.",
    "What do you think about that approach?",
    "I cannot believe this is happening!",
]


@dataclass
class HyperParams:
    """Training hyperparameters."""
    lr: float = 2e-5
    lora_r: int = 16
    lora_alpha: int = 32
    warmup_steps: int = 500
    weight_decay: float = 0.01
    gradient_accumulation_steps: int = 8
    batch_size: int = 1
    epochs_per_iteration: int = 1

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "HyperParams":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class EvaluationResult:
    """Result of evaluating a single phrase."""
    phrase: str
    audio_path: str
    similarity: float
    naturalness: float
    artifact_score: float
    overall_score: float
    rating: Optional[float] = None  # Human rating if provided


@dataclass
class IterationResult:
    """Result of a single training iteration."""
    iteration: int
    checkpoint_path: str
    training_loss: Optional[float]
    evaluations: List[EvaluationResult] = field(default_factory=list)
    avg_score: float = 0.0
    passed: bool = False
    timestamp: str = ""


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


def run_bayesian_search(
    persona: str,
    data_manifest: Path,
    output_dir: Path,
    n_trials: int = 10,
) -> HyperParams:
    """Phase 1: Bayesian search for optimal hyperparameters."""
    console.print(Panel("PHASE 1: HYPERPARAMETER SEARCH", title="iterative"))
    console.print(f"Running {n_trials} trials with Bayesian optimization...")

    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        console.print("[yellow]optuna not installed. Using default hyperparameters.[/yellow]")
        console.print("[dim]Install with: pip install optuna[/dim]")
        return HyperParams()

    hp_dir = output_dir / "hyperparameter_search"
    hp_dir.mkdir(parents=True, exist_ok=True)

    study_path = hp_dir / "optuna_study.db"
    study = optuna.create_study(
        study_name=f"train_voice_{persona.lower().replace(' ', '_')}",
        storage=f"sqlite:///{study_path}",
        direction="minimize",
        load_if_exists=True,
    )

    def objective(trial: optuna.Trial) -> float:
        """Single hyperparameter trial."""
        # Sample hyperparameters
        lr = trial.suggest_float("lr", 1e-6, 5e-5, log=True)
        lora_r = trial.suggest_categorical("lora_r", [8, 16, 32])
        lora_alpha = trial.suggest_categorical("lora_alpha", [16, 32, 64])
        warmup_steps = trial.suggest_int("warmup_steps", 100, 1000)
        weight_decay = trial.suggest_float("weight_decay", 0.001, 0.1, log=True)
        grad_accum = trial.suggest_categorical("gradient_accumulation_steps", [4, 8, 16])

        trial_dir = hp_dir / f"trial_{trial.number}"
        trial_dir.mkdir(exist_ok=True)

        console.print(f"\n[cyan]Trial {trial.number}:[/cyan] lr={lr:.2e}, lora_r={lora_r}")

        # Run smoke test training (limited steps)
        sft_script = SKILL_DIR / "Qwen3-TTS" / "finetuning" / "sft_12hz.py"

        cmd = [
            PYTHON_EXE, str(sft_script),
            "--init_model_path", "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
            "--train_jsonl", str(data_manifest),
            "--output_model_path", str(trial_dir),
            "--num_epochs", "1",
            "--batch_size", "1",
            "--lr", str(lr),
            "--gradient_accumulation_steps", str(grad_accum),
            "--gradient_checkpointing",
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=1800,  # 30 min
                cwd=str(SKILL_DIR / "Qwen3-TTS" / "finetuning"),
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            # Parse loss from output
            import re
            loss_pattern = r"Loss:\s*(\d+\.\d+)"
            matches = re.findall(loss_pattern, result.stdout)
            if matches:
                loss = float(matches[-1])
                console.print(f"  [green]Loss: {loss:.4f}[/green]")
                return loss

            console.print(f"  [yellow]No loss found[/yellow]")
            return float("inf")

        except subprocess.TimeoutExpired:
            console.print(f"  [red]Timeout[/red]")
            return float("inf")
        except Exception as e:
            console.print(f"  [red]Error: {e}[/red]")
            return float("inf")

    # Run optimization
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    # Extract best params
    best_params = HyperParams(
        lr=study.best_params.get("lr", 2e-5),
        lora_r=study.best_params.get("lora_r", 16),
        lora_alpha=study.best_params.get("lora_alpha", 32),
        warmup_steps=study.best_params.get("warmup_steps", 500),
        weight_decay=study.best_params.get("weight_decay", 0.01),
        gradient_accumulation_steps=study.best_params.get("gradient_accumulation_steps", 8),
    )

    # Save best config
    best_config_path = hp_dir / "best_config.json"
    with open(best_config_path, "w") as f:
        json.dump({
            "best_loss": study.best_value,
            "best_trial": study.best_trial.number,
            "hyperparameters": best_params.to_dict(),
        }, f, indent=2)

    console.print(f"\n[green]Best loss: {study.best_value:.4f}[/green]")
    console.print(f"Best config saved to: {best_config_path}")

    return best_params


def evaluate_checkpoint(
    persona: str,
    checkpoint: Path,
    eval_phrases: List[str],
    output_dir: Path,
    reference_audio: Optional[Path] = None,
) -> List[EvaluationResult]:
    """Evaluate a checkpoint on test phrases."""
    # Import voice-lab quality module
    voice_lab_dir = SKILL_DIR.parent / "voice-lab"
    sys.path.insert(0, str(voice_lab_dir))

    try:
        from quality import evaluate_quality
        from waveform import load_audio, ascii_waveform
    except ImportError:
        console.print("[yellow]voice-lab not available, using basic evaluation[/yellow]")
        evaluate_quality = None

    results = []
    speaker_name = persona.lower().replace(" ", "_")

    for i, phrase in enumerate(eval_phrases):
        output_path = output_dir / f"eval_{i:02d}.wav"

        console.print(f"\n  [cyan]Phrase {i+1}:[/cyan] {phrase[:50]}...")

        # Generate audio
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
    text="{phrase}",
    speaker="{speaker_name}",
    non_streaming_mode=True
)

audio = audio_outputs[0].cpu().numpy()
sf.write("{output_path}", audio, sample_rate)
'''

        try:
            result = subprocess.run(
                [PYTHON_EXE, "-c", inference_code],
                capture_output=True,
                text=True,
                timeout=120,
                env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
            )

            if result.returncode != 0 or not output_path.exists():
                console.print(f"    [red]Generation failed[/red]")
                continue

            # Evaluate quality
            if evaluate_quality:
                metrics = evaluate_quality(output_path, reference_audio, phrase)
                eval_result = EvaluationResult(
                    phrase=phrase,
                    audio_path=str(output_path),
                    similarity=metrics.similarity,
                    naturalness=metrics.naturalness,
                    artifact_score=metrics.artifact_score,
                    overall_score=metrics.overall_score,
                )
            else:
                # Basic evaluation without voice-lab
                eval_result = EvaluationResult(
                    phrase=phrase,
                    audio_path=str(output_path),
                    similarity=0.5,
                    naturalness=3.0,
                    artifact_score=0.8,
                    overall_score=3.0,
                )

            results.append(eval_result)
            console.print(f"    Score: {eval_result.overall_score:.2f}/5.0")

        except Exception as e:
            console.print(f"    [red]Error: {e}[/red]")

    return results


def run_iteration(
    persona: str,
    iteration: int,
    data_manifest: Path,
    output_dir: Path,
    hyperparams: HyperParams,
    current_model: Path,
) -> tuple[Path, Optional[float]]:
    """Run a single training iteration."""
    iter_dir = output_dir / f"iteration_{iteration}"
    iter_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"\n[cyan]Training iteration {iteration + 1}...[/cyan]")
    console.print(f"  lr={hyperparams.lr:.2e}, epochs={hyperparams.epochs_per_iteration}")

    sft_script = SKILL_DIR / "Qwen3-TTS" / "finetuning" / "sft_12hz.py"

    cmd = [
        PYTHON_EXE, str(sft_script),
        "--init_model_path", str(current_model),
        "--train_jsonl", str(data_manifest),
        "--output_model_path", str(iter_dir),
        "--num_epochs", str(hyperparams.epochs_per_iteration),
        "--batch_size", str(hyperparams.batch_size),
        "--lr", str(hyperparams.lr),
        "--gradient_accumulation_steps", str(hyperparams.gradient_accumulation_steps),
        "--gradient_checkpointing",
        "--speaker_name", persona.lower().replace(" ", "_"),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=7200,  # 2 hours
            cwd=str(SKILL_DIR / "Qwen3-TTS" / "finetuning"),
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        # Find checkpoint
        checkpoints = sorted(iter_dir.glob("checkpoint-epoch-*"))
        if checkpoints:
            checkpoint = checkpoints[-1]

            # Parse final loss
            import re
            loss_pattern = r"Loss:\s*(\d+\.\d+)"
            matches = re.findall(loss_pattern, result.stdout)
            loss = float(matches[-1]) if matches else None

            return checkpoint, loss

    except Exception as e:
        console.print(f"[red]Training failed: {e}[/red]")

    return iter_dir, None


@app.command()
def train(
    persona: str = typer.Argument(..., help="Persona name"),
    max_iterations: int = typer.Option(5, help="Maximum training iterations"),
    quality_threshold: float = typer.Option(3.5, help="Quality threshold (1-5)"),
    run_hp_search: bool = typer.Option(False, "--hyperparameter-search", help="Run Bayesian HP search"),
    hp_trials: int = typer.Option(10, help="Number of HP search trials"),
    hyperparams_file: Optional[Path] = typer.Option(None, help="Load hyperparams from file"),
    eval_phrases: Optional[str] = typer.Option(None, help="Comma-separated eval phrases"),
    auto: bool = typer.Option(False, help="Skip human feedback"),
):
    """
    Iterative voice training with quality evaluation loop.

    Two phases:
    1. HYPERPARAMETER SEARCH: Find optimal training config (optional)
    2. EVALUATION LOOP: Train, evaluate, iterate until quality threshold
    """
    console.print(Panel(f"Iterative Training: {persona}", title="train-voice"))

    persona_dir = get_persona_dir(persona)
    output_dir = persona_dir / "iterative_training"
    output_dir.mkdir(parents=True, exist_ok=True)

    # Find training data
    qwen3_dir = persona_dir / "qwen3_tts"
    manifests = list(qwen3_dir.glob("*_manifest_qwen3.jsonl"))
    if not manifests:
        console.print(f"[red]No training manifest found for {persona}[/red]")
        console.print("[dim]Run './run.sh train' first to prepare training data[/dim]")
        raise typer.Exit(1)

    data_manifest = manifests[0]
    console.print(f"Using manifest: {data_manifest}")

    # Evaluation phrases
    phrases = eval_phrases.split(",") if eval_phrases else DEFAULT_EVAL_PHRASES

    # Phase 1: Hyperparameter search
    if run_hp_search:
        hyperparams = run_bayesian_search(persona, data_manifest, output_dir, hp_trials)
    elif hyperparams_file and hyperparams_file.exists():
        with open(hyperparams_file) as f:
            hp_data = json.load(f)
            if "hyperparameters" in hp_data:
                hp_data = hp_data["hyperparameters"]
            hyperparams = HyperParams.from_dict(hp_data)
        console.print(f"Loaded hyperparams from {hyperparams_file}")
    else:
        hyperparams = HyperParams()
        console.print("Using default hyperparameters")

    # Find starting model
    existing_checkpoint = find_latest_checkpoint(persona)
    current_model = existing_checkpoint or Path("Qwen/Qwen3-TTS-12Hz-1.7B-Base")

    console.print(f"Starting from: {current_model}")

    # Phase 2: Evaluation loop
    console.print(Panel("PHASE 2: EVALUATION LOOP", title="iterative"))

    best_score = 0.0
    best_checkpoint = None
    iteration_results = []

    for iteration in range(max_iterations):
        console.print(f"\n{'='*60}")
        console.print(f"ITERATION {iteration + 1}/{max_iterations}")
        console.print('='*60)

        # Train
        checkpoint, loss = run_iteration(
            persona, iteration, data_manifest, output_dir,
            hyperparams, current_model
        )

        if not checkpoint.exists():
            console.print("[red]Training produced no checkpoint[/red]")
            continue

        # Evaluate
        eval_dir = output_dir / f"evaluations/iteration_{iteration}"
        eval_dir.mkdir(parents=True, exist_ok=True)

        evaluations = evaluate_checkpoint(
            persona, checkpoint, phrases, eval_dir
        )

        if evaluations:
            avg_score = sum(e.overall_score for e in evaluations) / len(evaluations)
        else:
            avg_score = 0.0

        # Check if passed
        passed = avg_score >= quality_threshold

        result = IterationResult(
            iteration=iteration,
            checkpoint_path=str(checkpoint),
            training_loss=loss,
            evaluations=evaluations,
            avg_score=avg_score,
            passed=passed,
            timestamp=datetime.now().isoformat(),
        )
        iteration_results.append(result)

        # Update best
        if avg_score > best_score:
            best_score = avg_score
            best_checkpoint = checkpoint

        # Report
        score_color = "green" if passed else "yellow"
        console.print(f"\n[{score_color}]Average score: {avg_score:.2f}/5.0[/{score_color}]")

        if passed:
            console.print(f"\n[green]QUALITY THRESHOLD REACHED![/green]")
            break

        # Human feedback
        if not auto:
            console.print(f"\n[dim]Listen to samples in: {eval_dir}[/dim]")
            try:
                rating = typer.prompt("Enter quality rating (1-5) or 'c' to continue", default="c")
                if rating.lower() != "c":
                    human_score = float(rating)
                    if human_score >= quality_threshold:
                        console.print("[green]Human rating passed![/green]")
                        break
            except (ValueError, KeyboardInterrupt):
                pass

        # Use checkpoint for next iteration
        current_model = checkpoint

    # Summary
    console.print("\n" + "="*60)
    console.print("TRAINING COMPLETE")
    console.print("="*60)

    table = Table(title="Iteration Summary")
    table.add_column("Iteration")
    table.add_column("Loss")
    table.add_column("Score")
    table.add_column("Status")

    for r in iteration_results:
        loss_str = f"{r.training_loss:.4f}" if r.training_loss else "-"
        status = "[green]PASSED[/green]" if r.passed else "[yellow]CONTINUE[/yellow]"
        table.add_row(
            str(r.iteration + 1),
            loss_str,
            f"{r.avg_score:.2f}",
            status,
        )

    console.print(table)

    if best_checkpoint:
        console.print(f"\nBest checkpoint: {best_checkpoint}")
        console.print(f"Best score: {best_score:.2f}/5.0")

        # Copy to final_model
        final_dir = output_dir / "final_model"
        if final_dir.exists():
            import shutil
            shutil.rmtree(final_dir)
        import shutil
        shutil.copytree(best_checkpoint, final_dir)
        console.print(f"Saved final model to: {final_dir}")

    # Save results
    results_file = output_dir / "iteration_results.json"
    with open(results_file, "w") as f:
        json.dump([asdict(r) for r in iteration_results], f, indent=2, default=str)


if __name__ == "__main__":
    app()
