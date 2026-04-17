#!/usr/bin/env python3
"""
Self-improvement cycle for Table Strategy Classifier.

Orchestrates the continuous learning loop:
1. Extract tables from PDF corpus
2. Collect successful strategies from S05 outputs
3. Train GRPO model with execution feedback
4. Deploy updated model to S05
5. Repeat nightly

Can be scheduled via cron or systemd timer.
"""

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import typer
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "typer", "-q"],
        env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
    )
    import typer

from loguru import logger

app = typer.Typer(help="Self-improvement cycle for Table Strategy Classifier")

# Paths
SKILL_DIR = Path(__file__).parent.parent
DATA_DIR = SKILL_DIR / "data"
MODELS_DIR = SKILL_DIR / "models"
LOGS_DIR = SKILL_DIR / "logs"

# Default extractor path
EXTRACTOR_PATH = Path(os.environ.get(
    "EXTRACTOR_PATH",
    str(Path.home() / "workspace/experiments/extractor")
))


def run_command(cmd: list[str], cwd: Path = None) -> tuple[bool, str]:
    """Run a command and return success status and output."""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd or SKILL_DIR,
            capture_output=True,
            text=True,
            timeout=3600  # 1 hour timeout
        )
        return result.returncode == 0, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return False, "Command timed out"
    except Exception as e:
        return False, str(e)


def run_extraction(
    corpus_dir: Path,
    output_dir: Path,
    limit: int = 1000,
) -> tuple[bool, dict]:
    """Run S05 extraction on PDF corpus."""
    logger.info(f"Running extraction on {limit} PDFs from {corpus_dir}")

    # Find PDFs
    pdfs = list(corpus_dir.glob("**/*.pdf"))[:limit]
    if not pdfs:
        return False, {"error": "No PDFs found"}

    logger.info(f"Found {len(pdfs)} PDFs to process")

    # Run extractor
    success_count = 0
    failed_count = 0

    for i, pdf in enumerate(pdfs):
        if i % 100 == 0:
            logger.info(f"Progress: {i}/{len(pdfs)}")

        try:
            result = subprocess.run(
                [
                    sys.executable, "-m", "extractor.pipeline.cli",
                    "extract",
                    "--input", str(pdf),
                    "--output-dir", str(output_dir),
                    "--stages", "01,02,03,04,05",  # Run through S05
                ],
                cwd=EXTRACTOR_PATH,
                capture_output=True,
                text=True,
                timeout=120,
            )

            if result.returncode == 0:
                success_count += 1
            else:
                failed_count += 1

        except Exception as e:
            failed_count += 1
            logger.debug(f"Failed to process {pdf}: {e}")

    return True, {
        "total": len(pdfs),
        "success": success_count,
        "failed": failed_count,
    }


def collect_training_data(
    results_dir: Path,
    corpus_dir: Path,
    output_file: Path,
    limit: int = 5000,
) -> tuple[bool, int]:
    """Collect training data from extraction results."""
    logger.info(f"Collecting training data from {results_dir}")

    success, output = run_command([
        sys.executable, "scripts/collect_training_data.py",
        "collect",
        "--corpus", str(corpus_dir),
        "--extractor-results", str(results_dir),
        "--output", str(output_file),
        "--limit", str(limit),
    ])

    if not success:
        logger.error(f"Collection failed: {output}")
        return False, 0

    # Count examples
    if output_file.exists():
        count = sum(1 for _ in output_file.open())
        return True, count

    return False, 0


def train_model(
    train_file: Path,
    eval_file: Path,
    corpus_dir: Path,
    sft_epochs: int = 3,
    grpo_epochs: int = 5,
) -> tuple[bool, Path]:
    """Train model with SFT warmup + GRPO."""
    logger.info("Starting SFT warmup")

    # SFT Warmup
    success, output = run_command([
        sys.executable, "scripts/train_sft.py",
        "train",
        "--train-file", str(train_file),
        "--eval-file", str(eval_file),
        "--epochs", str(sft_epochs),
    ])

    if not success:
        logger.error(f"SFT training failed: {output}")
        return False, None

    logger.info("Starting GRPO training")

    # GRPO
    success, output = run_command([
        sys.executable, "scripts/train_grpo.py",
        "grpo",
        "--checkpoint", str(MODELS_DIR / "table-classifier-sft" / "model.pth"),
        "--train-file", str(train_file),
        "--corpus-dir", str(corpus_dir),
        "--epochs", str(grpo_epochs),
    ])

    if not success:
        logger.error(f"GRPO training failed: {output}")
        return False, None

    return True, MODELS_DIR / "table-classifier-grpo"


def evaluate_model(model_path: Path, eval_file: Path) -> tuple[bool, dict]:
    """Evaluate model on holdout set."""
    logger.info(f"Evaluating model at {model_path}")

    metrics_file = LOGS_DIR / "eval_metrics.json"

    success, output = run_command([
        sys.executable, "scripts/evaluate.py",
        "run",
        "--model-path", str(model_path),
        "--eval-file", str(eval_file),
        "--output-file", str(metrics_file),
    ])

    if not success:
        logger.error(f"Evaluation failed: {output}")
        return False, {}

    if metrics_file.exists():
        return True, json.loads(metrics_file.read_text())

    return False, {}


def deploy_model(model_path: Path) -> bool:
    """Export and deploy model for S05 integration."""
    logger.info("Deploying model to S05")

    final_path = MODELS_DIR / "table-classifier-final"

    success, output = run_command([
        sys.executable, "scripts/inference.py",
        "export",
        "--model-path", str(model_path),
        "--output-path", str(final_path),
    ])

    if not success:
        logger.error(f"Export failed: {output}")
        return False

    # Copy to extractor path if configured
    extractor_models = EXTRACTOR_PATH / "models"
    if extractor_models.exists():
        import shutil
        dest = extractor_models / "table-strategy-classifier"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(final_path, dest)
        logger.info(f"Deployed to {dest}")

    return True


@app.command()
def cycle(
    corpus_dir: Path = typer.Option(..., help="PDF corpus directory"),
    results_dir: Path = typer.Option(
        DATA_DIR / "extraction_results",
        help="Extraction results directory"
    ),
    extract_limit: int = typer.Option(1000, help="PDFs to extract per cycle"),
    collect_limit: int = typer.Option(5000, help="Max training examples"),
    sft_epochs: int = typer.Option(3, help="SFT warmup epochs"),
    grpo_epochs: int = typer.Option(5, help="GRPO epochs"),
    skip_extraction: bool = typer.Option(False, help="Skip extraction phase"),
    skip_training: bool = typer.Option(False, help="Skip training phase"),
    skip_deploy: bool = typer.Option(False, help="Skip deployment phase"),
):
    """
    Run full self-improvement cycle.

    Steps:
    1. Extract tables from corpus (optional)
    2. Collect training data
    3. Train SFT + GRPO
    4. Evaluate on holdout
    5. Deploy if thresholds met

    Examples:
        ./run.sh self-improve --corpus-dir /data/pdfs --extract-limit 1000
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)

    cycle_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    cycle_log = LOGS_DIR / f"cycle_{cycle_id}.log"

    logger.add(cycle_log)
    logger.info(f"Starting self-improvement cycle {cycle_id}")

    # Phase 1: Extraction
    if not skip_extraction:
        logger.info("Phase 1: Extraction")
        success, stats = run_extraction(corpus_dir, results_dir, extract_limit)
        if not success:
            logger.error("Extraction phase failed")
            raise typer.Exit(1)
        logger.info(f"Extraction complete: {stats}")
    else:
        logger.info("Skipping extraction phase")

    # Phase 2: Data Collection
    logger.info("Phase 2: Data Collection")
    collected_file = DATA_DIR / "labels" / f"collected_{cycle_id}.jsonl"
    success, count = collect_training_data(
        results_dir, corpus_dir, collected_file, collect_limit
    )
    if not success or count < 100:
        logger.error(f"Insufficient training data: {count} examples")
        raise typer.Exit(1)
    logger.info(f"Collected {count} training examples")

    # Split data
    logger.info("Splitting data")
    run_command([
        sys.executable, "scripts/evaluate.py",
        "split",
        "--input-file", str(collected_file),
        "--train-ratio", "0.85",
    ])

    train_file = DATA_DIR / "labels" / "train.jsonl"
    eval_file = DATA_DIR / "labels" / "eval.jsonl"

    # Phase 3: Training
    if not skip_training:
        logger.info("Phase 3: Training")
        success, model_path = train_model(
            train_file, eval_file, corpus_dir,
            sft_epochs, grpo_epochs
        )
        if not success:
            logger.error("Training phase failed")
            raise typer.Exit(1)
        logger.info(f"Training complete: {model_path}")
    else:
        logger.info("Skipping training phase")
        model_path = MODELS_DIR / "table-classifier-grpo"

    # Phase 4: Evaluation
    logger.info("Phase 4: Evaluation")
    success, metrics = evaluate_model(model_path, eval_file)
    if not success:
        logger.error("Evaluation phase failed")
        raise typer.Exit(1)

    logger.info(f"Evaluation metrics: {metrics}")

    # Check thresholds
    strategy_acc = metrics.get("strategy_accuracy", 0)
    param_mae = metrics.get("param_mae", 100)

    thresholds_met = strategy_acc >= 0.85 and param_mae <= 5.0

    if not thresholds_met:
        logger.warning(
            f"Thresholds not met: accuracy={strategy_acc:.2%}, MAE={param_mae:.2f}"
        )
        logger.info("Model not deployed. Consider more training data or epochs.")
        raise typer.Exit(1)

    # Phase 5: Deployment
    if not skip_deploy:
        logger.info("Phase 5: Deployment")
        success = deploy_model(model_path)
        if not success:
            logger.error("Deployment failed")
            raise typer.Exit(1)
        logger.info("Deployment complete!")
    else:
        logger.info("Skipping deployment phase")

    # Summary
    logger.info(f"""
{'='*50}
Self-Improvement Cycle Complete
{'='*50}
Cycle ID: {cycle_id}
Training examples: {count}
Strategy accuracy: {strategy_acc:.2%}
Parameter MAE: {param_mae:.2f}
Thresholds met: {thresholds_met}
Log file: {cycle_log}
{'='*50}
    """)


@app.command()
def schedule(
    corpus_dir: Path = typer.Option(..., help="PDF corpus directory"),
    nights: int = typer.Option(7, help="Number of nightly cycles"),
    hour: int = typer.Option(2, help="Hour to run (0-23)"),
):
    """
    Schedule nightly self-improvement cycles.

    Creates a cron job or systemd timer (prints instructions).

    Examples:
        ./run.sh self-improve schedule --corpus-dir /data/pdfs --nights 7
    """
    skill_path = SKILL_DIR.resolve()
    cron_cmd = f"0 {hour} * * * cd {skill_path} && ./run.sh self-improve --corpus-dir {corpus_dir}"

    print(f"""
To schedule nightly self-improvement:

Option 1: Cron (add to crontab -e)
{cron_cmd}

Option 2: Systemd Timer
Create /etc/systemd/system/table-classifier.service:

[Unit]
Description=Table Strategy Classifier Self-Improvement
After=network.target

[Service]
Type=oneshot
WorkingDirectory={skill_path}
ExecStart={skill_path}/run.sh self-improve --corpus-dir {corpus_dir}
User={os.environ.get('USER', 'root')}

[Install]
WantedBy=multi-user.target

And /etc/systemd/system/table-classifier.timer:

[Unit]
Description=Run table classifier improvement nightly

[Timer]
OnCalendar=*-*-* {hour:02d}:00:00
Persistent=true

[Install]
WantedBy=timers.target

Then: sudo systemctl enable --now table-classifier.timer
    """)


if __name__ == "__main__":
    app()
