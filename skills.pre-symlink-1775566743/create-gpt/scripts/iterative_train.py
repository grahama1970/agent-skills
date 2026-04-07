#!/usr/bin/env python3
"""Self-improvement loop: HP search → iterative train → holdout gate.

Adapted from create-classifier/scripts/iterative_train.py.

Two-phase training with automated convergence detection:
- Phase 1: Bayesian HP Search (Optuna)
- Phase 2: Iterative Training with holdout gates

Usage:
    python iterative_train.py iterate --task qra-validator --max-iterations 5
    python iterative_train.py iterate --task qra-validator --mock
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import typer
from loguru import logger
from rich.console import Console

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from task_spec import load_task_spec, DATA_DIR, MODELS_DIR

app = typer.Typer(add_completion=False)
console = Console()

# Hyperparameter adjustments for retry (from create-intent-map pattern)
RETRY_ADJUSTMENTS = [
    {"learning_rate": 2e-6, "beta": 0.02},
    {"learning_rate": 1e-5, "beta": 0.005},
    {"num_generations": 4, "temperature": 0.5},
]


class IterativeGPTTrainer:
    """Iterative training with quality-driven + holdout-gated promotion."""

    def __init__(
        self,
        spec,
        output_dir: Path,
        quality_threshold: float = 0.85,
        max_iterations: int = 5,
        holdout_ratio: float = 0.10,
        mock: bool = False,
        use_wandb: bool = False,
    ):
        self.spec = spec
        self.output_dir = output_dir
        self.quality_threshold = quality_threshold
        self.max_iterations = max_iterations
        self.holdout_ratio = holdout_ratio
        self.mock = mock
        self.use_wandb = use_wandb

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.best_accuracy = 0.0
        self.best_model_path: Optional[str] = None
        self.iteration_results: List[Dict[str, Any]] = []
        self._monitor = TaskClient(f"create-gpt/iterate/{spec.name}", total=max_iterations, description=f"Iterative training {spec.name}") if TaskClient else None

    def run_iteration(
        self,
        iteration: int,
        hyperparams: Dict[str, Any],
        train_file: Path,
        val_file: Path,
        holdout_file: Path,
        checkpoint_path: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Run a single training + evaluation iteration."""
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Iteration {iteration + 1}/{self.max_iterations}")
        logger.info(f"{'=' * 60}")

        iter_output = self.output_dir / f"iteration_{iteration + 1}"

        if self.mock:
            return self._mock_iteration(iteration, hyperparams)

        # SFT training
        sft_cmd = [
            sys.executable, "train_sft.py", "train",
            "--task", self.spec.name,
            "--train-file", str(train_file),
            "--output", str(iter_output),
            "--epochs", str(self.spec.get_training_param("sft_epochs", 1)),
        ]

        result = subprocess.run(
            sft_cmd,
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.error(f"Training failed: {result.stderr[-500:]}")
            return {
                "iteration": iteration + 1,
                "accuracy": 0.0,
                "format_valid": 0.0,
                "holdout_gate_pass": False,
                "error": result.stderr[-500:],
            }

        # Evaluate on validation set
        val_metrics = self._evaluate(iter_output, val_file)

        # Evaluate on holdout set
        holdout_metrics = self._evaluate(iter_output, holdout_file)

        accuracy = val_metrics.get("accuracy", 0.0)
        format_valid = val_metrics.get("format_valid", 0.0)
        holdout_accuracy = holdout_metrics.get("accuracy", 0.0)
        holdout_f1 = holdout_metrics.get("exact_match", 0.0)

        # Holdout gate: both accuracy and f1 must pass
        holdout_pass = (
            holdout_accuracy >= self.quality_threshold
            and holdout_f1 >= self.quality_threshold * 0.8
        )

        return {
            "iteration": iteration + 1,
            "accuracy": accuracy,
            "format_valid": format_valid,
            "holdout_accuracy": holdout_accuracy,
            "holdout_f1": holdout_f1,
            "holdout_gate_pass": holdout_pass,
            "model_path": str(iter_output),
            "hyperparams": hyperparams,
        }

    def _evaluate(self, model_path: Path, test_file: Path) -> Dict[str, Any]:
        """Run evaluation and return metrics."""
        eval_output = model_path / "eval_results.json"
        cmd = [
            sys.executable, "evaluate.py", "run",
            "--task", self.spec.name,
            "--model", str(model_path),
            "--test-file", str(test_file),
            "--output", str(eval_output),
        ]
        if self.mock:
            cmd.append("--mock")

        result = subprocess.run(
            cmd,
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
        )

        if eval_output.exists():
            data = json.loads(eval_output.read_text())
            return data.get("metrics", {})

        return {"accuracy": 0.0, "format_valid": 0.0}

    def _mock_iteration(self, iteration: int, hyperparams: Dict) -> Dict[str, Any]:
        """Mock iteration for testing."""
        import random

        # Simulate improving accuracy over iterations
        base_acc = 0.70 + iteration * 0.05 + random.random() * 0.10
        accuracy = min(0.98, base_acc)
        format_valid = min(0.99, 0.85 + iteration * 0.03 + random.random() * 0.05)

        holdout_accuracy = accuracy - random.random() * 0.05
        holdout_f1 = accuracy - random.random() * 0.08

        holdout_pass = (
            holdout_accuracy >= self.quality_threshold
            and holdout_f1 >= self.quality_threshold * 0.8
        )

        return {
            "iteration": iteration + 1,
            "accuracy": accuracy,
            "format_valid": format_valid,
            "holdout_accuracy": holdout_accuracy,
            "holdout_f1": holdout_f1,
            "holdout_gate_pass": holdout_pass,
            "model_path": str(self.output_dir / f"iteration_{iteration + 1}"),
            "hyperparams": hyperparams,
            "mock": True,
        }

    def run(self, train_file: Path, val_file: Path, holdout_file: Path) -> bool:
        """Run complete iterative training loop."""
        logger.info("=" * 60)
        logger.info("PHASE 2: Iterative Training")
        logger.info("=" * 60)
        logger.info(f"Quality threshold: {self.quality_threshold:.1%}")
        logger.info(f"Max iterations: {self.max_iterations}")

        # Load or use default hyperparams
        hp_path = MODELS_DIR / self.spec.name / "best_hyperparams.json"
        if hp_path.exists():
            hp_data = json.loads(hp_path.read_text())
            hyperparams = hp_data.get("hyperparameters", {})
            logger.info(f"Using HP search results: {hyperparams}")
        else:
            hyperparams = {
                "learning_rate": 2e-4,
                "lora_r": self.spec.get_training_param("lora_r", 16),
                "lora_alpha": self.spec.get_training_param("lora_alpha", 32),
                "batch_size": 4,
            }
            logger.info(f"Using default hyperparams: {hyperparams}")

        checkpoint_path = None
        for iteration in range(self.max_iterations):
            result = self.run_iteration(
                iteration, hyperparams, train_file, val_file, holdout_file, checkpoint_path
            )
            self.iteration_results.append(result)

            if self._monitor:
                self._monitor.update(item=f"iter {iteration+1} acc={result.get('accuracy', 0):.1%}")

            accuracy = result.get("accuracy", 0.0)
            if accuracy > self.best_accuracy:
                self.best_accuracy = accuracy
                self.best_model_path = result.get("model_path")

            # Check convergence
            threshold_met = (
                accuracy >= self.quality_threshold
                and result.get("format_valid", 0) >= self.spec.eval_thresholds.get("format_valid", 0.95)
                and result.get("holdout_gate_pass", False)
            )

            if threshold_met:
                console.print(
                    f"\n[bold green]THRESHOLD MET at iteration {iteration + 1}![/bold green]"
                )
                console.print(f"  Accuracy: {accuracy:.1%}")
                console.print(f"  Format valid: {result.get('format_valid', 0):.1%}")
                console.print(f"  Holdout: {result.get('holdout_accuracy', 0):.1%}")

                # Promote best model
                if self.best_model_path:
                    best_dir = self.output_dir / "best_model"
                    best_dir.mkdir(parents=True, exist_ok=True)
                    (best_dir / "promotion_info.json").write_text(json.dumps({
                        "source": self.best_model_path,
                        "accuracy": self.best_accuracy,
                        "iteration": iteration + 1,
                    }, indent=2))

                self._save_summary(True, hyperparams)
                if self._monitor:
                    self._monitor.finish()
                return True

            console.print(
                f"\n[yellow]Iteration {iteration + 1}: "
                f"acc={accuracy:.1%}, "
                f"holdout_pass={result.get('holdout_gate_pass', False)}[/yellow]"
            )

            # Apply retry adjustments
            if iteration < len(RETRY_ADJUSTMENTS):
                adjustment = RETRY_ADJUSTMENTS[iteration]
                hyperparams.update(adjustment)
                logger.info(f"Adjusted hyperparams: {adjustment}")

            checkpoint_path = Path(result["model_path"]) if result.get("model_path") else None

        console.print("\n[bold red]Max iterations reached without meeting thresholds[/bold red]")
        console.print(f"  Best accuracy: {self.best_accuracy:.1%}")
        self._save_summary(False, hyperparams)
        if self._monitor:
            self._monitor.finish(success=False)
        return False

    def _save_summary(self, success: bool, hyperparams: Dict) -> None:
        """Save training summary."""
        summary = {
            "task": self.spec.name,
            "threshold_met": success,
            "best_accuracy": self.best_accuracy,
            "best_model_path": self.best_model_path,
            "quality_threshold": self.quality_threshold,
            "max_iterations": self.max_iterations,
            "iterations": self.iteration_results,
            "final_hyperparams": hyperparams,
        }
        summary_path = self.output_dir / "training_summary.json"
        summary_path.write_text(json.dumps(summary, indent=2))
        logger.info(f"Summary saved to: {summary_path}")


@app.command("iterate")
def iterate(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    max_iterations: int = typer.Option(5, "--max-iterations", "-n"),
    quality_threshold: float = typer.Option(0.85, "--quality-threshold", "-q"),
    mock: bool = typer.Option(False, "--mock"),
    output_dir: Optional[Path] = typer.Option(None, "--output", "-o"),
    train_file: Optional[Path] = typer.Option(None, "--train-file"),
    val_file: Optional[Path] = typer.Option(None, "--val-file"),
    holdout_file: Optional[Path] = typer.Option(None, "--holdout-file"),
    use_wandb: bool = typer.Option(False, "--wandb/--no-wandb"),
):
    """Run iterative self-improvement training loop."""
    spec = load_task_spec(task)

    if output_dir is None:
        output_dir = MODELS_DIR / spec.name / "iterative"
    if train_file is None:
        train_file = DATA_DIR / spec.name / "sft" / "train.jsonl"
    if val_file is None:
        val_file = DATA_DIR / spec.name / "sft" / "val.jsonl"
    if holdout_file is None:
        holdout_file = DATA_DIR / spec.name / "sft" / "holdout.jsonl"

    # Verify files exist (for mock, create dummy files)
    for f in [train_file, val_file, holdout_file]:
        if not f.exists():
            if mock:
                f.parent.mkdir(parents=True, exist_ok=True)
                # Create minimal mock data
                with open(f, "w") as fh:
                    for i in range(10):
                        fh.write(json.dumps({
                            "input": f"test input {i}",
                            "output": {"valid": True, "confidence": 0.9},
                        }) + "\n")
            else:
                logger.error(f"File not found: {f}")
                raise typer.Exit(code=1)

    trainer = IterativeGPTTrainer(
        spec=spec,
        output_dir=output_dir,
        quality_threshold=quality_threshold,
        max_iterations=max_iterations,
        mock=mock,
        use_wandb=use_wandb,
    )

    success = trainer.run(train_file, val_file, holdout_file)
    raise typer.Exit(code=0 if success else 1)


if __name__ == "__main__":
    app()
