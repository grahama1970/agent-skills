#!/usr/bin/env python3
"""
Iterative TTS Training Loop with Optional Hyperparameter Search

Two-phase workflow:
1. HYPERPARAMETER PHASE (optional): Find optimal training config via Bayesian search
2. EVALUATION PHASE: Train with config, evaluate quality, iterate until threshold

Why both phases?
- Hyperparameter search optimizes TRAINING EFFICIENCY (loss curves, convergence)
- Evaluation loop optimizes OUTPUT QUALITY (voice similarity, naturalness)
- Loss ≠ Quality: low loss can still produce poor voice (wrong prosody, artifacts)

Usage:
    # Full workflow: hyperparameter search + iterative training
    python iterative_train.py \
        --model-path /path/to/base/model \
        --data /path/to/train.jsonl \
        --output /path/to/output \
        --max-iterations 5 \
        --run-hyperparameter-search \
        --hp-trials 10

    # Evaluation-only (use when you already have good hyperparameters)
    python iterative_train.py \
        --model-path /path/to/base/model \
        --data /path/to/train.jsonl \
        --output /path/to/output \
        --max-iterations 5 \
        --hyperparams config.json
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# Default test phrases for voice quality evaluation
DEFAULT_EVAL_PHRASES = [
    "I am Horus, the Warmaster.",
    "The Emperor's silence was his first betrayal.",
    "Do not speak to me of Erebus.",
    "I see all. I know all.",
]


@dataclass
class EvaluationResult:
    """Result of evaluating a single phrase."""
    phrase: str
    audio_path: str
    duration: float
    rating: Optional[float] = None  # 1-5 scale
    notes: str = ""
    auto_metrics: dict = field(default_factory=dict)


@dataclass
class IterationResult:
    """Result of a single training iteration."""
    iteration: int
    checkpoint_path: str
    training_loss: float
    evaluations: List[EvaluationResult] = field(default_factory=list)
    avg_rating: float = 0.0
    passed: bool = False
    timestamp: str = ""


class IterativeTrainer:
    """Manages iterative training with evaluation loops.

    Two-phase workflow:
    1. HYPERPARAMETER PHASE: Bayesian search for optimal training config
       - Optimizes: learning rate, LoRA config, warmup, weight decay
       - Uses short smoke runs (300 steps) to evaluate loss curves
       - Goal: Find settings that train efficiently

    2. EVALUATION PHASE: Iterative training with quality evaluation
       - Trains for N epochs with optimal config
       - Generates audio samples on test phrases
       - Evaluates perceptual quality (human or auto rating)
       - Continues until quality threshold or max iterations
       - Goal: Achieve target voice quality

    Why both phases?
    - Loss ≠ Quality: low loss can still produce poor voice
    - Hyperparameters affect training efficiency, not final quality
    - Evaluation catches prosody issues, artifacts, speaker drift
    """

    def __init__(
        self,
        model_path: str,
        data_manifest: str,
        output_dir: str,
        max_iterations: int = 5,
        quality_threshold: float = 3.5,
        eval_phrases: Optional[List[str]] = None,
        epochs_per_iteration: int = 1,
        auto_evaluate: bool = False,
        run_hyperparameter_search: bool = False,
        hp_trials: int = 10,
        hyperparams_file: Optional[str] = None,
    ):
        self.model_path = Path(model_path)
        self.data_manifest = Path(data_manifest)
        self.output_dir = Path(output_dir)
        self.max_iterations = max_iterations
        self.quality_threshold = quality_threshold
        self.eval_phrases = eval_phrases or DEFAULT_EVAL_PHRASES
        self.epochs_per_iteration = epochs_per_iteration
        self.auto_evaluate = auto_evaluate

        # Hyperparameter search config
        self.do_hyperparameter_search = run_hyperparameter_search
        self.hp_trials = hp_trials
        self.hyperparams_file = hyperparams_file
        self.optimal_hyperparams: dict = {}

        # State tracking
        self.iterations: List[IterationResult] = []
        self.current_model_path = model_path
        self.best_model_path: Optional[str] = None
        self.best_rating: float = 0.0

        # Setup directories
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.eval_dir = self.output_dir / "evaluations"
        self.eval_dir.mkdir(exist_ok=True)
        self.checkpoint_dir = self.output_dir / "checkpoints"
        self.checkpoint_dir.mkdir(exist_ok=True)
        self.hp_dir = self.output_dir / "hyperparameter_search"
        self.hp_dir.mkdir(exist_ok=True)

    def load_hyperparams(self) -> dict:
        """Load hyperparameters from file or return defaults."""
        if self.hyperparams_file and Path(self.hyperparams_file).exists():
            with open(self.hyperparams_file) as f:
                return json.load(f)
        return {
            "lr": 2e-6,
            "lora_r": 16,
            "lora_alpha": 32,
            "warmup_steps": 500,
            "weight_decay": 0.01,
            "gradient_accumulation_steps": 8,
        }

    def run_hyperparameter_search(self) -> dict:
        """Phase 1: Bayesian search for optimal hyperparameters.

        Uses short smoke runs (300 steps) to evaluate different configs.
        Optimizes for training efficiency (loss curves, convergence speed).

        Returns:
            dict: Optimal hyperparameters found
        """
        print("\n" + "="*60)
        print("PHASE 1: HYPERPARAMETER SEARCH")
        print("="*60)
        print(f"Running {self.hp_trials} trials with Bayesian optimization...")
        print("="*60 + "\n")

        # Check if optuna is available
        try:
            import optuna
        except ImportError:
            print("WARNING: optuna not installed. Using default hyperparameters.")
            print("Install with: uv pip install optuna")
            return self.load_hyperparams()

        # Create Optuna study
        study_path = self.hp_dir / "optuna_study.db"
        study = optuna.create_study(
            study_name="qwen3_tts_hp_search",
            storage=f"sqlite:///{study_path}",
            direction="minimize",  # Minimize loss
            load_if_exists=True,
        )

        def objective(trial: optuna.Trial) -> float:
            """Single hyperparameter trial - runs short smoke test."""
            # Sample hyperparameters
            lr = trial.suggest_float("lr", 1e-6, 5e-5, log=True)
            lora_r = trial.suggest_categorical("lora_r", [8, 16, 32])
            lora_alpha = trial.suggest_categorical("lora_alpha", [16, 32, 64])
            warmup_steps = trial.suggest_int("warmup_steps", 100, 1000)
            weight_decay = trial.suggest_float("weight_decay", 0.001, 0.1, log=True)
            grad_accum = trial.suggest_categorical("gradient_accumulation_steps", [4, 8, 16])

            trial_dir = self.hp_dir / f"trial_{trial.number}"
            trial_dir.mkdir(exist_ok=True)

            # Build training command for smoke test (300 steps)
            skill_dir = Path(__file__).parent
            cmd = [
                str(skill_dir / "run.sh"),
                "train-qwen3",
                f"--base-model={self.model_path}",
                f"--data-manifest={self.data_manifest}",
                f"--out-dir={trial_dir}",
                "--epochs=1",
                "--batch-size=1",
                f"--lr={lr}",
                f"--lora-r={lora_r}",
                f"--lora-alpha={lora_alpha}",
                f"--warmup-steps={warmup_steps}",
                f"--weight-decay={weight_decay}",
                f"--gradient-accumulation-steps={grad_accum}",
                "--max-steps=300",  # Short smoke run
                "--use-lora",
                "--use-8bit-adam",
                "--gradient-checkpointing",
            ]

            print(f"\nTrial {trial.number}: lr={lr:.2e}, lora_r={lora_r}, warmup={warmup_steps}")

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=1800,  # 30 min timeout for smoke run
                )

                # Parse loss from training output
                loss = self._parse_final_loss(result.stdout, trial_dir)
                if loss is None:
                    print(f"  Trial {trial.number} failed - no loss found")
                    return float("inf")

                print(f"  Trial {trial.number} complete: loss={loss:.4f}")
                return loss

            except subprocess.TimeoutExpired:
                print(f"  Trial {trial.number} timed out")
                return float("inf")
            except Exception as e:
                print(f"  Trial {trial.number} error: {e}")
                return float("inf")

        # Run optimization
        study.optimize(objective, n_trials=self.hp_trials, show_progress_bar=True)

        # Get best hyperparameters
        best_params = study.best_params
        best_params["gradient_accumulation_steps"] = best_params.pop("gradient_accumulation_steps", 8)

        # Save best config
        best_config_path = self.hp_dir / "best_config.json"
        with open(best_config_path, "w") as f:
            json.dump({
                "best_value": study.best_value,
                "best_trial": study.best_trial.number,
                "hyperparameters": best_params,
            }, f, indent=2)

        print("\n" + "="*60)
        print("HYPERPARAMETER SEARCH COMPLETE")
        print("="*60)
        print(f"Best loss: {study.best_value:.4f}")
        print(f"Best config: {best_params}")
        print(f"Saved to: {best_config_path}")
        print("="*60 + "\n")

        return best_params

    def _parse_final_loss(self, stdout: str, trial_dir: Path) -> Optional[float]:
        """Extract final loss from training output or logs."""
        import re

        # Try to find loss in stdout
        loss_pattern = r"loss[:\s]+(\d+\.\d+)"
        matches = re.findall(loss_pattern, stdout, re.IGNORECASE)
        if matches:
            return float(matches[-1])  # Return last loss value

        # Try to find in trainer_state.json
        trainer_state = trial_dir / "trainer_state.json"
        if trainer_state.exists():
            with open(trainer_state) as f:
                state = json.load(f)
                if "log_history" in state and state["log_history"]:
                    last_log = state["log_history"][-1]
                    if "loss" in last_log:
                        return last_log["loss"]

        return None

    def run_training_iteration(self, iteration: int) -> str:
        """Run a single training iteration, returns checkpoint path."""
        print(f"\n{'='*60}")
        print(f"ITERATION {iteration + 1}/{self.max_iterations}")
        print(f"{'='*60}\n")

        iter_output = self.checkpoint_dir / f"iteration_{iteration}"
        iter_output.mkdir(exist_ok=True)

        # Get hyperparameters (from search or file or defaults)
        hp = self.optimal_hyperparams if self.optimal_hyperparams else self.load_hyperparams()
        lr = hp.get("lr", 2e-6)
        lora_r = hp.get("lora_r", 16)
        lora_alpha = hp.get("lora_alpha", 32)
        warmup_steps = hp.get("warmup_steps", 500)
        weight_decay = hp.get("weight_decay", 0.01)
        grad_accum = hp.get("gradient_accumulation_steps", 8)

        print(f"Using hyperparameters: lr={lr:.2e}, lora_r={lora_r}, warmup={warmup_steps}")

        # Build training command
        skill_dir = Path(__file__).parent
        train_script = skill_dir / "Qwen3-TTS" / "finetuning" / "sft_12hz.py"

        if not train_script.exists():
            # Fallback to using run.sh
            cmd = [
                str(skill_dir / "run.sh"),
                "train-qwen3",
                f"--base-model={self.current_model_path}",
                f"--data-manifest={self.data_manifest}",
                f"--out-dir={iter_output}",
                f"--epochs={self.epochs_per_iteration}",
                "--batch-size=1",
                f"--lr={lr}",
                f"--lora-r={lora_r}",
                f"--lora-alpha={lora_alpha}",
                f"--warmup-steps={warmup_steps}",
                f"--weight-decay={weight_decay}",
                f"--gradient-accumulation-steps={grad_accum}",
                "--use-lora",
                "--use-8bit-adam",
                "--gradient-checkpointing",
            ]
        else:
            # Direct training
            cmd = [
                "python", str(train_script),
                "--init_model_path", str(self.current_model_path),
                "--train_jsonl", str(self.data_manifest),
                "--output_model_path", str(iter_output),
                "--num_epochs", str(self.epochs_per_iteration),
                "--batch_size", "1",
                f"--learning_rate={lr}",
                f"--gradient_accumulation_steps={grad_accum}",
            ]

        print(f"Running: {' '.join(cmd[:5])}...")

        # Run training
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600 * 2,  # 2 hour timeout per iteration
            )
            if result.returncode != 0:
                print(f"Training failed: {result.stderr[-500:]}")
                return ""
        except subprocess.TimeoutExpired:
            print("Training timed out")
            return ""

        # Find the latest checkpoint
        checkpoints = sorted(iter_output.glob("checkpoint-*"))
        if checkpoints:
            return str(checkpoints[-1])
        elif (iter_output / "model.safetensors").exists():
            return str(iter_output)

        return ""

    def run_inference(self, checkpoint_path: str, phrase: str, output_path: str) -> Optional[EvaluationResult]:
        """Run inference on a single phrase."""
        # Use the persona inference script if available
        inference_script = Path(__file__).parent.parent.parent.parent / \
            "workspace/experiments/memory/persona/code/horus_tts_inference.py"

        if inference_script.exists():
            cmd = [
                "python", str(inference_script),
                phrase,
                f"--model={checkpoint_path}",
                f"--output={output_path}",
            ]
        else:
            # Fallback to direct Qwen3-TTS inference
            cmd = [
                "python", "-c",
                f"""
import torch
import soundfile as sf
from qwen_tts import Qwen3TTSModel

tts = Qwen3TTSModel.from_pretrained("{checkpoint_path}", device_map="auto", dtype=torch.bfloat16)
wavs, sr = tts.generate_custom_voice(text="{phrase}", language="English", speaker="horus")
sf.write("{output_path}", wavs[0], sr)
print(f"Saved to {output_path}")
"""
            ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            if result.returncode == 0 and Path(output_path).exists():
                import soundfile as sf
                data, sr = sf.read(output_path)
                duration = len(data) / sr
                return EvaluationResult(
                    phrase=phrase,
                    audio_path=output_path,
                    duration=duration,
                )
        except Exception as e:
            print(f"Inference failed: {e}")

        return None

    def evaluate_iteration(self, iteration: int, checkpoint_path: str) -> IterationResult:
        """Evaluate a training iteration by generating and rating samples."""
        print(f"\nEvaluating iteration {iteration + 1}...")

        iter_eval_dir = self.eval_dir / f"iteration_{iteration}"
        iter_eval_dir.mkdir(exist_ok=True)

        evaluations = []
        for i, phrase in enumerate(self.eval_phrases):
            output_path = str(iter_eval_dir / f"eval_{i:02d}.wav")
            result = self.run_inference(checkpoint_path, phrase, output_path)
            if result:
                evaluations.append(result)
                print(f"  [{i+1}/{len(self.eval_phrases)}] Generated {result.duration:.1f}s audio")

        # Calculate ratings
        if self.auto_evaluate:
            # Auto-rating based on duration and file size (basic heuristics)
            for eval_result in evaluations:
                # Penalize very short or very long outputs
                expected_wps = 2.5  # words per second
                expected_duration = len(eval_result.phrase.split()) / expected_wps
                duration_ratio = eval_result.duration / max(expected_duration, 0.1)

                if 0.5 <= duration_ratio <= 2.0:
                    eval_result.rating = 3.5 + (1.5 * (1 - abs(1 - duration_ratio)))
                else:
                    eval_result.rating = 2.0
        else:
            # Manual rating mode
            print("\n" + "="*60)
            print("MANUAL EVALUATION")
            print("="*60)
            print("Listen to each audio file and rate 1-5:")
            print("  1 = Unintelligible")
            print("  2 = Poor quality")
            print("  3 = Acceptable")
            print("  4 = Good")
            print("  5 = Excellent")
            print("="*60 + "\n")

            for eval_result in evaluations:
                print(f"\nPhrase: '{eval_result.phrase}'")
                print(f"Audio: {eval_result.audio_path}")
                print(f"Play: aplay {eval_result.audio_path}")

                while True:
                    try:
                        rating = input("Rating (1-5, or 's' to skip): ").strip()
                        if rating.lower() == 's':
                            eval_result.rating = None
                            break
                        rating = float(rating)
                        if 1 <= rating <= 5:
                            eval_result.rating = rating
                            break
                    except ValueError:
                        pass
                    print("Invalid input. Enter 1-5 or 's'.")

                note = input("Notes (optional): ").strip()
                eval_result.notes = note

        # Calculate average rating
        rated = [e for e in evaluations if e.rating is not None]
        avg_rating = sum(e.rating for e in rated) / len(rated) if rated else 0.0

        result = IterationResult(
            iteration=iteration,
            checkpoint_path=checkpoint_path,
            training_loss=0.0,  # TODO: extract from training logs
            evaluations=evaluations,
            avg_rating=avg_rating,
            passed=avg_rating >= self.quality_threshold,
            timestamp=time.strftime("%Y-%m-%d %H:%M:%S"),
        )

        # Save evaluation results
        eval_log = iter_eval_dir / "evaluation.json"
        with open(eval_log, "w") as f:
            json.dump({
                "iteration": result.iteration,
                "avg_rating": result.avg_rating,
                "passed": result.passed,
                "evaluations": [
                    {
                        "phrase": e.phrase,
                        "audio_path": e.audio_path,
                        "duration": e.duration,
                        "rating": e.rating,
                        "notes": e.notes,
                    }
                    for e in result.evaluations
                ],
            }, f, indent=2)

        return result

    def run(self) -> bool:
        """Run the full two-phase workflow.

        Phase 1 (optional): Hyperparameter search via Bayesian optimization
        Phase 2: Iterative training with evaluation loop
        """
        print("\n" + "="*60)
        print("ITERATIVE TTS TRAINING")
        print("="*60)
        print(f"Model: {self.model_path}")
        print(f"Data: {self.data_manifest}")
        print(f"Max iterations: {self.max_iterations}")
        print(f"Quality threshold: {self.quality_threshold}")
        print(f"Evaluation mode: {'auto' if self.auto_evaluate else 'manual'}")
        print(f"Hyperparameter search: {'enabled' if self.do_hyperparameter_search else 'disabled'}")
        print("="*60 + "\n")

        # ===== PHASE 1: HYPERPARAMETER SEARCH =====
        if self.do_hyperparameter_search:
            self.optimal_hyperparams = self.run_hyperparameter_search()
        elif self.hyperparams_file:
            print(f"Loading hyperparameters from {self.hyperparams_file}")
            self.optimal_hyperparams = self.load_hyperparams()
        else:
            print("Using default hyperparameters")
            self.optimal_hyperparams = self.load_hyperparams()

        # ===== PHASE 2: ITERATIVE TRAINING WITH EVALUATION =====
        print("\n" + "="*60)
        print("PHASE 2: ITERATIVE TRAINING WITH EVALUATION")
        print("="*60 + "\n")

        for iteration in range(self.max_iterations):
            # Run training
            checkpoint_path = self.run_training_iteration(iteration)
            if not checkpoint_path:
                print(f"Training failed at iteration {iteration + 1}")
                continue

            # Evaluate
            result = self.evaluate_iteration(iteration, checkpoint_path)
            self.iterations.append(result)

            # Track best model
            if result.avg_rating > self.best_rating:
                self.best_rating = result.avg_rating
                self.best_model_path = checkpoint_path
                print(f"\n*** New best model: {result.avg_rating:.2f}/5 ***")

            # Check if quality threshold met
            if result.passed:
                print(f"\n{'='*60}")
                print(f"SUCCESS - Quality threshold met at iteration {iteration + 1}")
                print(f"Average rating: {result.avg_rating:.2f}/5")
                print(f"Best model: {self.best_model_path}")
                print(f"{'='*60}\n")

                # Copy best model to final output
                final_output = self.output_dir / "final_model"
                if final_output.exists():
                    shutil.rmtree(final_output)
                shutil.copytree(self.best_model_path, final_output)

                return True

            # Update current model for next iteration
            self.current_model_path = checkpoint_path
            print(f"\nIteration {iteration + 1} complete. Rating: {result.avg_rating:.2f}/5")
            print(f"Threshold not met ({self.quality_threshold}). Continuing...")

        # Max iterations reached
        print(f"\n{'='*60}")
        print(f"COMPLETED - Max iterations reached")
        print(f"Best rating achieved: {self.best_rating:.2f}/5")
        print(f"Best model: {self.best_model_path}")
        print(f"{'='*60}\n")

        if self.best_model_path:
            final_output = self.output_dir / "final_model"
            if final_output.exists():
                shutil.rmtree(final_output)
            shutil.copytree(self.best_model_path, final_output)

        return self.best_rating >= self.quality_threshold


def main():
    parser = argparse.ArgumentParser(
        description="Iterative TTS Training Loop with Optional Hyperparameter Search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Full workflow: hyperparameter search + iterative training
    python iterative_train.py \\
        --model-path Qwen/Qwen3-TTS-12Hz-1.7B-Base \\
        --data datasets/horus/train_manifest_qwen3.jsonl \\
        --output artifacts/tts/horus_iterative \\
        --run-hyperparameter-search --hp-trials 10

    # Evaluation-only (use when you have good hyperparameters)
    python iterative_train.py \\
        --model-path artifacts/tts/horus/checkpoint-epoch-0 \\
        --data datasets/horus/train_manifest_qwen3.jsonl \\
        --output artifacts/tts/horus_refined \\
        --hyperparams best_config.json
"""
    )

    # Required arguments
    parser.add_argument("--model-path", required=True, help="Base model path")
    parser.add_argument("--data", required=True, help="Training data JSONL")
    parser.add_argument("--output", required=True, help="Output directory")

    # Evaluation loop config
    parser.add_argument("--max-iterations", type=int, default=5,
                        help="Max training iterations (default: 5)")
    parser.add_argument("--quality-threshold", type=float, default=3.5,
                        help="Quality threshold 1-5 to stop iterating (default: 3.5)")
    parser.add_argument("--eval-phrases", nargs="+",
                        help="Custom phrases for evaluation (default: Horus test phrases)")
    parser.add_argument("--epochs-per-iteration", type=int, default=1,
                        help="Training epochs per iteration (default: 1)")
    parser.add_argument("--auto-evaluate", action="store_true",
                        help="Auto-evaluate using heuristics (no manual rating)")

    # Hyperparameter search config
    parser.add_argument("--run-hyperparameter-search", action="store_true",
                        help="Run Bayesian hyperparameter search before training")
    parser.add_argument("--hp-trials", type=int, default=10,
                        help="Number of hyperparameter search trials (default: 10)")
    parser.add_argument("--hyperparams", type=str, default=None,
                        help="Path to hyperparameters JSON file (skips search)")

    args = parser.parse_args()

    trainer = IterativeTrainer(
        model_path=args.model_path,
        data_manifest=args.data,
        output_dir=args.output,
        max_iterations=args.max_iterations,
        quality_threshold=args.quality_threshold,
        eval_phrases=args.eval_phrases,
        epochs_per_iteration=args.epochs_per_iteration,
        auto_evaluate=args.auto_evaluate,
        run_hyperparameter_search=args.run_hyperparameter_search,
        hp_trials=args.hp_trials,
        hyperparams_file=args.hyperparams,
    )

    success = trainer.run()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
