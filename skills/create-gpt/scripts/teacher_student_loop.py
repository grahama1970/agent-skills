#!/usr/bin/env python3
"""Teacher-Student training loop: Bootstrap → Train → Deploy → Correct → Anneal.

Orchestrates the full pipeline from teacher labeling through student training
and iterative correction until convergence.

Usage:
    python teacher_student_loop.py run --task qra-assessor --input raw_qras.jsonl --max-rounds 3
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import typer
from loguru import logger

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

SCRIPTS_DIR = Path(__file__).resolve().parent


class TeacherStudentLoop:
    """Orchestrates the 5-phase teacher-student training loop.

    Phase 1: BOOTSTRAP    teacher.py label → raw teacher labels
    Phase 2: TRAIN        prepare_data.py prepare → train_sft.py train
    Phase 3: DEPLOY       export_gguf.py → evaluate.py gate
    Phase 4: CORRECT      Sample student outputs, teacher validates, disagreements → retrain
    Phase 5: ANNEAL       Reduce correction sample rate (never to 0%)
    """

    def __init__(
        self,
        task_name: str,
        input_file: Path,
        max_rounds: int = 3,
        correction_rate: float = 0.10,
        min_correction_rate: float = 0.02,
    ):
        self.task_name = task_name
        self.input_file = input_file
        self.max_rounds = max_rounds
        self.correction_rate = correction_rate
        self.min_correction_rate = min_correction_rate
        self.spec = load_task_spec(task_name)
        self.history: list[dict] = []
        self._monitor = TaskClient(f"create-gpt/teacher-student/{task_name}", total=max_rounds, description=f"Teacher-student loop {task_name}") if TaskClient else None

    def run(self) -> dict:
        """Run full loop. Returns summary dict with rounds, agreement_rate, final_model."""
        logger.info(f"Starting teacher-student loop for '{self.task_name}'")
        logger.info(f"  max_rounds={self.max_rounds}, correction_rate={self.correction_rate}")

        # Phase 1: Bootstrap
        labeled_data = self._bootstrap()
        if labeled_data is None:
            return {"status": "failed", "reason": "bootstrap_failed", "rounds": 0}

        final_model = None
        agreement_rate = 0.0

        for round_num in range(self.max_rounds):
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Round {round_num + 1}/{self.max_rounds}")
            logger.info(f"{'=' * 60}")

            # Phase 2: Train
            model_path = self._train(labeled_data)
            if model_path is None:
                logger.error(f"Training failed at round {round_num + 1}")
                break

            # Phase 3: Evaluate (deploy gate)
            metrics = self._evaluate(model_path)
            passed = metrics.get("passed", False)

            # Phase 4: Correct
            corrections, agreement_rate = self._correct(
                model_path, self.correction_rate,
            )

            round_result = {
                "round": round_num + 1,
                "model_path": str(model_path),
                "metrics": metrics,
                "agreement_rate": agreement_rate,
                "correction_rate": self.correction_rate,
                "corrections_count": len(corrections) if corrections else 0,
            }
            self.history.append(round_result)
            self._save_history()

            if self._monitor:
                self._monitor.update(item=f"round {round_num+1} agreement={agreement_rate:.1%}")

            final_model = model_path

            # Check convergence
            if agreement_rate > 0.98:
                logger.info(
                    f"Converged at round {round_num + 1} "
                    f"(agreement={agreement_rate:.3f})"
                )
                break

            # Phase 5: Anneal
            self.correction_rate = self._should_anneal(agreement_rate)

            # Merge corrections into training data for next round
            if corrections:
                labeled_data = self._merge_corrections(labeled_data, corrections)

        summary = {
            "status": "converged" if agreement_rate > 0.98 else "max_rounds",
            "rounds": len(self.history),
            "final_agreement_rate": agreement_rate,
            "final_model": str(final_model) if final_model else None,
            "history": self.history,
        }

        summary_path = DATA_DIR / self.task_name / "loop_summary.json"
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2))
        logger.info(f"Loop summary saved to {summary_path}")

        if self._monitor:
            self._monitor.finish(success=summary["status"] == "converged")

        return summary

    def _bootstrap(self) -> Optional[Path]:
        """Phase 1: Generate teacher labels."""
        logger.info("Phase 1: BOOTSTRAP — generating teacher labels")
        output_file = DATA_DIR / self.task_name / "teacher" / "labeled.jsonl"

        result = subprocess.run(
            [
                sys.executable, "teacher.py",
                "--task", self.task_name,
                "--input", str(self.input_file),
                "--output", str(output_file),
            ],
            cwd=SCRIPTS_DIR,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            logger.error(f"Bootstrap failed: {result.stderr[-500:]}")
            return None

        if not output_file.exists() or output_file.stat().st_size == 0:
            logger.error("Bootstrap produced no output")
            return None

        logger.info(f"Bootstrap complete: {output_file}")
        return output_file

    def _train(self, labeled_data: Path) -> Optional[Path]:
        """Phase 2: prepare_data + train_sft."""
        logger.info("Phase 2: TRAIN — preparing data and training SFT")

        sft_dir = DATA_DIR / self.task_name / "sft"
        sft_train = sft_dir / "train.jsonl"

        # Prepare data
        result = subprocess.run(
            [
                sys.executable, "prepare_data.py", "prepare",
                "--task", self.task_name,
                "--input", str(labeled_data),
                "--output", str(sft_train),
            ],
            cwd=SCRIPTS_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error(f"Data prep failed: {result.stderr[-500:]}")
            return None

        # Train
        model_output = MODELS_DIR / self.task_name / "sft"
        epochs = str(self.spec.get_training_param("sft_epochs", 2))

        result = subprocess.run(
            [
                sys.executable, "train_sft.py", "train",
                "--task", self.task_name,
                "--train-file", str(sft_train),
                "--output", str(model_output),
                "--epochs", epochs,
            ],
            cwd=SCRIPTS_DIR,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.error(f"Training failed: {result.stderr[-500:]}")
            return None

        logger.info(f"Training complete: {model_output}")
        return model_output

    def _evaluate(self, model_path: Path) -> dict:
        """Phase 3: Run evaluate.py, return metrics dict."""
        logger.info("Phase 3: DEPLOY — evaluating model")

        eval_output = model_path / "eval_results.json"
        test_file = DATA_DIR / self.task_name / "sft" / "val.jsonl"

        # If no val file, use a subset of train
        if not test_file.exists():
            test_file = DATA_DIR / self.task_name / "sft" / "train.jsonl"

        result = subprocess.run(
            [
                sys.executable, "evaluate.py", "run",
                "--task", self.task_name,
                "--model", str(model_path),
                "--test-file", str(test_file),
                "--output", str(eval_output),
            ],
            cwd=SCRIPTS_DIR,
            capture_output=True,
            text=True,
        )

        if eval_output.exists():
            data = json.loads(eval_output.read_text())
            return data

        return {"metrics": {}, "passed": False}

    def _correct(
        self, model_path: Path, sample_rate: float,
    ) -> tuple[list[dict], float]:
        """Phase 4: Sample student outputs, re-label with teacher, return corrections + agreement."""
        logger.info(f"Phase 4: CORRECT — sampling at {sample_rate:.1%}")

        # Load training data to sample from
        train_file = DATA_DIR / self.task_name / "sft" / "train.jsonl"
        if not train_file.exists():
            return [], 1.0

        train_data = []
        with open(train_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    train_data.append(json.loads(line))

        import random
        sample_size = max(1, int(len(train_data) * sample_rate))
        sample = random.sample(train_data, min(sample_size, len(train_data)))

        # Run student inference on sample
        agreements = 0
        corrections = []

        for item in sample:
            # Extract user input from chat format
            user_input = ""
            expected_output = ""
            for msg in item.get("messages", []):
                if msg["role"] == "user":
                    user_input = msg["content"]
                elif msg["role"] == "assistant":
                    expected_output = msg["content"]

            if not user_input:
                agreements += 1
                continue

            # Run student inference
            try:
                student_result = subprocess.run(
                    [
                        sys.executable, "infer.py", "run",
                        user_input,
                        "--task", self.task_name,
                        "--model", str(model_path),
                    ],
                    cwd=SCRIPTS_DIR,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if student_result.returncode != 0:
                    corrections.append({"input": user_input, "output": expected_output})
                    continue

                student_output = json.loads(student_result.stdout)
                student_text = json.dumps(
                    student_output.get("output", {}), sort_keys=True
                )

                # Compare student vs expected
                try:
                    expected_parsed = json.loads(expected_output)
                    expected_text = json.dumps(expected_parsed, sort_keys=True)
                except (json.JSONDecodeError, TypeError):
                    expected_text = expected_output

                if student_text == expected_text:
                    agreements += 1
                else:
                    corrections.append({
                        "input": user_input,
                        "output": expected_output,
                    })
            except (subprocess.TimeoutExpired, Exception) as e:
                logger.debug(f"Correction check failed: {e}")
                corrections.append({"input": user_input, "output": expected_output})

        agreement_rate = agreements / len(sample) if sample else 1.0
        logger.info(
            f"Correction results: {agreements}/{len(sample)} agree "
            f"({agreement_rate:.1%}), {len(corrections)} corrections"
        )

        return corrections, agreement_rate

    def _should_anneal(self, agreement_rate: float) -> float:
        """Phase 5: Reduce correction rate if agreement > 0.95."""
        if agreement_rate > 0.95:
            new_rate = max(self.min_correction_rate, self.correction_rate * 0.5)
            logger.info(
                f"Annealing correction rate: {self.correction_rate:.3f} → {new_rate:.3f}"
            )
            return new_rate
        return self.correction_rate

    def _merge_corrections(
        self, labeled_data: Path, corrections: list[dict],
    ) -> Path:
        """Merge corrections back into labeled data for next round."""
        existing = []
        with open(labeled_data) as f:
            for line in f:
                line = line.strip()
                if line:
                    existing.append(json.loads(line))

        # Add corrections as new training examples
        for corr in corrections:
            output = corr.get("output", "")
            if isinstance(output, str):
                try:
                    output = json.loads(output)
                except json.JSONDecodeError:
                    pass
            existing.append({"input": corr["input"], "output": output})

        merged_path = labeled_data.parent / "labeled_corrected.jsonl"
        merged_path.parent.mkdir(parents=True, exist_ok=True)
        with open(merged_path, "w") as f:
            for item in existing:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        logger.info(f"Merged {len(corrections)} corrections → {merged_path}")
        return merged_path

    def _save_history(self) -> None:
        """Save round-by-round metrics."""
        history_path = DATA_DIR / self.task_name / "loop_history.jsonl"
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with open(history_path, "w") as f:
            for entry in self.history:
                f.write(json.dumps(entry, default=str) + "\n")


@app.command()
def run_cmd(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    input_file: Path = typer.Option(..., "--input", "-i", help="Raw JSONL input"),
    max_rounds: int = typer.Option(3, "--max-rounds", "-n", help="Max training rounds"),
    correction_rate: float = typer.Option(0.10, "--correction-rate", help="Initial correction sample rate"),
    min_correction_rate: float = typer.Option(0.02, "--min-correction-rate", help="Minimum correction rate"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show config and exit without running"),
):
    """Run the teacher-student training loop."""
    if not input_file.exists():
        logger.error(f"Input file not found: {input_file}")
        raise typer.Exit(code=1)

    if dry_run:
        config = {
            "task": task, "input": str(input_file), "max_rounds": max_rounds,
            "correction_rate": correction_rate, "min_correction_rate": min_correction_rate,
        }
        logger.info(f"Dry-run config: {json.dumps(config, indent=2)}")
        print(json.dumps(config, indent=2))
        raise typer.Exit(code=0)

    loop = TeacherStudentLoop(
        task_name=task,
        input_file=input_file,
        max_rounds=max_rounds,
        correction_rate=correction_rate,
        min_correction_rate=min_correction_rate,
    )
    summary = loop.run()

    print(json.dumps(summary, indent=2, default=str))
    status = summary.get("status", "unknown")
    raise typer.Exit(code=0 if status == "converged" else 1)


if __name__ == "__main__":
    app()
