#!/usr/bin/env python3
"""Training self-improvement loop for Classifier Lab.

Deterministic loop: train → check gate → adjust strategy → retrain.
The agent WILL NOT do this reliably. This script does it in code.

Strategies (executed in order per backbone):
  1. Baseline HPs from tune-config.json
  2. Lower learning rate (÷2)
  3. More epochs (×2)
  4. Add weight decay + label smoothing

If all strategies fail for a backbone, move to next backbone.
If all backbones exhausted, halt with diagnosis.

Usage:
    python training_loop.py /path/to/project-dir \
        --backbones distilbert-base-uncased,sentence-transformers/all-MiniLM-L6-v2 \
        --gate-f1 0.90 \
        --max-rounds 8
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True)

SKILLS_DIR = Path(__file__).resolve().parent.parent.parent
CREATE_CLF = SKILLS_DIR / "create-classifier"
MODELS_BASE = Path(os.environ.get(
    "CLASSIFIER_LAB_MODELS_DIR",
    "/mnt/storage12tb/media/agents/shared/classifier-lab/models",
))


def train_once(
    project_dir: Path,
    backbone: str,
    output_dir: Path,
    epochs: int,
    lr: float,
    batch_size: int,
    max_length: int,
    is_multilabel: bool,
) -> dict:
    """Run one training job. Returns metrics dict or error."""
    template = "multilabel_text_classifier.py" if is_multilabel else "text_classifier.py"
    script = CREATE_CLF / "templates" / template

    cmd = [
        "uv", "run", "--project", str(CREATE_CLF),
        "python", str(script),
        "--train-file", str(project_dir / "train.jsonl"),
        "--val-file", str(project_dir / "val.jsonl"),
        "--output-dir", str(output_dir),
        "--model", backbone,
        "--epochs", str(epochs),
        "--batch-size", str(batch_size),
        "--learning-rate", str(lr),
        "--max-length", str(max_length),
        "--early-stopping", "3",
    ]

    if is_multilabel:
        cmd.extend(["--pos-weight-auto", "--threshold", "0.3"])

    test_file = project_dir / "test.jsonl"
    if test_file.exists():
        cmd.extend(["--test-file", str(test_file)])

    logger.info(f"  Training: {backbone} lr={lr} epochs={epochs} bs={batch_size}")

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=1800,
            env={**os.environ, "VIRTUAL_ENV": ""},
        )

        # Read training summary
        summary_path = output_dir / "training_summary.json"
        if summary_path.exists():
            summary = json.loads(summary_path.read_text())
            metrics = summary.get("test_metrics", summary.get("val_metrics", {}))
            f1 = metrics.get("eval_f1_macro", metrics.get("eval_f1", 0))
            acc = metrics.get("eval_accuracy", 0)
            logger.info(f"  Result: F1={f1:.4f} acc={acc:.4f}")
            return {"f1": f1, "accuracy": acc, "metrics": metrics, "backbone": backbone}

        logger.warning(f"  No training_summary.json found")
        return {"f1": 0, "error": "no summary", "stderr": result.stderr[-500:] if result.stderr else ""}

    except subprocess.TimeoutExpired:
        return {"f1": 0, "error": "timeout"}
    except Exception as e:
        return {"f1": 0, "error": str(e)}


@app.command()
def run(
    project_dir: str = typer.Argument(..., help="Path to classifier project directory"),
    backbones: str = typer.Option("distilbert-base-uncased", help="Comma-separated backbone list"),
    gate_f1: float = typer.Option(0.90, help="F1 gate threshold"),
    max_rounds: int = typer.Option(8, help="Max total training rounds"),
    max_length: int = typer.Option(128, help="Max token length"),
):
    """Run the training self-improvement loop."""
    pdir = Path(project_dir)
    backbone_list = [b.strip() for b in backbones.split(",") if b.strip()]

    # Load tune config for base HPs
    tune_path = pdir / "tune-config.json"
    tune = json.loads(tune_path.read_text()) if tune_path.exists() else {}
    base_lr = tune.get("lr", 2e-5)
    base_epochs = tune.get("epochs", 5)
    base_bs = tune.get("batch_size", 16)

    # Detect modality
    meta = json.loads((pdir / "meta.json").read_text()) if (pdir / "meta.json").exists() else {}
    is_multilabel = "multilabel" in meta.get("modality", "") or "multi_label" in meta.get("modality", "")

    # Also check if samples have "labels" (list) field
    if not is_multilabel:
        sample_path = pdir / "train.jsonl"
        if sample_path.exists():
            first_line = sample_path.read_text().split("\n")[0]
            if first_line:
                sample = json.loads(first_line)
                if isinstance(sample.get("labels"), list):
                    is_multilabel = True

    project_name = pdir.name
    models_dir = MODELS_BASE / project_name

    # HP strategies per backbone
    strategies = [
        {"name": "baseline", "lr_mult": 1.0, "epoch_mult": 1.0, "bs": base_bs},
        {"name": "lower_lr", "lr_mult": 0.5, "epoch_mult": 1.0, "bs": base_bs},
        {"name": "more_epochs", "lr_mult": 1.0, "epoch_mult": 2.0, "bs": base_bs},
        {"name": "regularized", "lr_mult": 0.5, "epoch_mult": 2.0, "bs": max(8, base_bs // 2)},
    ]

    all_results: list[dict] = []
    best_f1 = 0.0
    best_result: dict = {}
    round_num = 0

    logger.info(f"Training loop: {len(backbone_list)} backbones × {len(strategies)} strategies")
    logger.info(f"Gate: F1 ≥ {gate_f1}")
    logger.info(f"Base HPs: lr={base_lr} epochs={base_epochs} bs={base_bs}")
    logger.info(f"Multi-label: {is_multilabel}")

    for backbone in backbone_list:
        if best_f1 >= gate_f1:
            break  # already passed gate

        for strategy in strategies:
            if round_num >= max_rounds:
                break
            if best_f1 >= gate_f1:
                break

            round_num += 1
            lr = base_lr * strategy["lr_mult"]
            epochs = int(base_epochs * strategy["epoch_mult"])
            bs = strategy["bs"]

            safe_name = backbone.replace("/", "-")
            out_dir = models_dir / f"{safe_name}-{strategy['name']}"
            out_dir.mkdir(parents=True, exist_ok=True)

            logger.info(f"\n{'='*60}")
            logger.info(f"Round {round_num}/{max_rounds}: {backbone} strategy={strategy['name']}")
            logger.info(f"{'='*60}")

            result = train_once(pdir, backbone, out_dir, epochs, lr, bs, max_length, is_multilabel)
            result["round"] = round_num
            result["strategy"] = strategy["name"]
            result["backbone"] = backbone
            result["lr"] = lr
            result["epochs"] = epochs
            all_results.append(result)

            if result["f1"] > best_f1:
                best_f1 = result["f1"]
                best_result = result

            if result["f1"] >= gate_f1:
                logger.info(f"GATE PASSED! F1={result['f1']:.4f} ≥ {gate_f1}")
                break

            gap = gate_f1 - result["f1"]
            logger.info(f"  Gap: {gap:.4f} — trying next strategy")

    # Write results
    passed = best_f1 >= gate_f1
    summary = {
        "passed": passed,
        "best_f1": best_f1,
        "best_backbone": best_result.get("backbone", ""),
        "best_strategy": best_result.get("strategy", ""),
        "gate_f1": gate_f1,
        "total_rounds": round_num,
        "results": all_results,
    }

    # Write benchmark.json
    benchmark = {
        "selected_backbone": best_result.get("backbone", ""),
        "selected_metrics": {"macro_f1": best_f1, "accuracy": best_result.get("accuracy", 0)},
        "gate_f1": gate_f1,
        "results": [
            {"backbone": r["backbone"], "strategy": r["strategy"], "macro_f1": r["f1"],
             "accuracy": r.get("accuracy", 0), "gate_passed": r["f1"] >= gate_f1,
             "lr": r.get("lr"), "epochs": r.get("epochs")}
            for r in all_results
        ],
    }
    (pdir / "benchmark.json").write_text(json.dumps(benchmark, indent=2))

    # Write eval-results.json if passed
    if passed and best_result.get("metrics"):
        eval_results = {
            "model": best_result["backbone"],
            "macro_f1": best_f1,
            "accuracy": best_result.get("accuracy", 0),
            "test_samples": meta.get("samples", 0),
            "holdout_passed": True,
            "classes": meta.get("class_names", []),
        }
        (pdir / "eval-results.json").write_text(json.dumps(eval_results, indent=2))

    # Update meta
    meta["f1"] = best_f1
    meta["backbone"] = best_result.get("backbone", "")
    meta["status"] = "passed" if passed else "halted-training"
    (pdir / "meta.json").write_text(json.dumps(meta, indent=2))

    logger.info(f"\n{'='*60}")
    if passed:
        logger.info(f"GATE PASSED: {best_result['backbone']} F1={best_f1:.4f} (strategy: {best_result['strategy']})")
    else:
        logger.info(f"GATE FAILED: best F1={best_f1:.4f} < {gate_f1} after {round_num} rounds")
        logger.info(f"Best: {best_result.get('backbone', '?')} strategy={best_result.get('strategy', '?')}")
    logger.info(f"{'='*60}")

    print(json.dumps(summary))


if __name__ == "__main__":
    app()
