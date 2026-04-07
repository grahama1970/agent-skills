#!/usr/bin/env python3
"""Classifier Lab full pipeline — runs all steps in sequence.

This is the single entry point. No agent decisions. The pipeline runs:
  1. Pre-flight: check project has a name + modality
  2. Data sufficiency check → if insufficient, run data_enrichment.py
  3. Training loop → training_loop.py with backbones from tune-config or defaults
  4. Write results to project dir for Classifier Lab UX

Usage:
    python pipeline.py /path/to/project-dir [--gate-f1 0.90] [--max-training-rounds 8]
"""
import json
import subprocess
import sys
from pathlib import Path

import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True)

SCRIPTS_DIR = Path(__file__).resolve().parent


def run_script(name: str, args: list[str], timeout: int = 600) -> tuple[int, str]:
    """Run a sibling script and return (returncode, stdout)."""
    script = SCRIPTS_DIR / name
    cmd = ["uv", "run", "--project", str(SCRIPTS_DIR.parent), "python", str(script), *args]
    logger.info(f"Running: {name} {' '.join(args[:3])}...")
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        logger.warning(f"  {name} exited with code {result.returncode}")
        if result.stderr:
            logger.warning(f"  stderr: {result.stderr[-300:]}")
    return result.returncode, result.stdout


@app.command()
def run(
    project_dir: str = typer.Argument(..., help="Path to classifier project directory"),
    gate_f1: float = typer.Option(0.90, help="F1 gate threshold"),
    max_training_rounds: int = typer.Option(8, help="Max training rounds"),
    min_per_class: int = typer.Option(50, help="Min samples per class"),
    max_length: int = typer.Option(128, help="Max token length for training"),
):
    """Run the full Classifier Lab pipeline."""
    pdir = Path(project_dir)
    if not pdir.exists():
        logger.error(f"Project not found: {pdir}")
        raise typer.Exit(1)

    meta = json.loads((pdir / "meta.json").read_text()) if (pdir / "meta.json").exists() else {}
    project_name = meta.get("name", pdir.name)

    logger.info(f"{'='*60}")
    logger.info(f"CLASSIFIER LAB PIPELINE: {project_name}")
    logger.info(f"Gate: F1 ≥ {gate_f1}")
    logger.info(f"{'='*60}")

    # ── Step 1: Pre-flight ──────────────────────────────────────
    logger.info("\n[1/3] PRE-FLIGHT CHECK")

    if not (pdir / "samples.jsonl").exists() and not (pdir / "train.jsonl").exists():
        logger.error("No training data (samples.jsonl or train.jsonl)")
        meta["status"] = "halted-no-data"
        (pdir / "meta.json").write_text(json.dumps(meta, indent=2))
        print(json.dumps({"status": "halted", "reason": "no training data"}))
        raise typer.Exit(1)

    # ── Step 2: Data sufficiency + enrichment ──────────────────
    logger.info("\n[2/3] DATA SUFFICIENCY CHECK")

    rc, out = run_script("data_enrichment.py", [
        str(pdir), "--min-per-class", str(min_per_class), "--max-iterations", "3",
    ], timeout=300)

    # Parse enrichment result
    enrichment_result = {}
    for line in out.strip().split("\n"):
        try:
            enrichment_result = json.loads(line)
        except json.JSONDecodeError:
            pass

    if enrichment_result.get("status") == "abandoned":
        logger.error(f"Data enrichment exhausted — project abandoned")
        logger.error(f"Available: {enrichment_result.get('total_train', '?')}, needed: {enrichment_result.get('required', '?')}")
        meta["status"] = "abandoned"
        meta["abandon_reason"] = "Data insufficient after enrichment"
        (pdir / "meta.json").write_text(json.dumps(meta, indent=2))
        print(json.dumps({"status": "abandoned", "reason": "data insufficient after enrichment", **enrichment_result}))
        raise typer.Exit(1)

    if enrichment_result.get("status") == "sufficient":
        logger.info(f"Data sufficient: {enrichment_result.get('total_train', '?')} samples")
    else:
        logger.warning(f"Data enrichment returned unexpected status: {enrichment_result.get('status')}")

    # Ensure train/val/test splits exist
    if not (pdir / "train.jsonl").exists():
        logger.info("Splitting samples.jsonl into train/val/test...")
        import random
        samples = [json.loads(l) for l in (pdir / "samples.jsonl").read_text().splitlines() if l.strip()]
        random.seed(42)
        random.shuffle(samples)
        n = len(samples)
        splits = {"train": samples[:int(n*0.8)], "val": samples[int(n*0.8):int(n*0.9)], "test": samples[int(n*0.9):]}
        for name, data in splits.items():
            with open(pdir / f"{name}.jsonl", "w") as f:
                for s in data:
                    f.write(json.dumps({**s, "split": name}) + "\n")
        logger.info(f"Split: train={len(splits['train'])}, val={len(splits['val'])}, test={len(splits['test'])}")

    # ── Step 3: Training loop ──────────────────────────────────
    logger.info("\n[3/3] TRAINING LOOP")

    # Get backbones from tune-config or defaults
    tune = json.loads((pdir / "tune-config.json").read_text()) if (pdir / "tune-config.json").exists() else {}
    backbones = tune.get("backbones", "distilbert-base-uncased,sentence-transformers/all-MiniLM-L6-v2")
    if isinstance(backbones, list):
        backbones = ",".join(backbones)

    rc, out = run_script("training_loop.py", [
        str(pdir),
        "--backbones", backbones,
        "--gate-f1", str(gate_f1),
        "--max-rounds", str(max_training_rounds),
        "--max-length", str(max_length),
    ], timeout=1800)

    # Parse training result
    training_result = {}
    for line in out.strip().split("\n"):
        try:
            training_result = json.loads(line)
        except json.JSONDecodeError:
            pass

    if training_result.get("passed"):
        logger.info(f"GATE PASSED: {training_result.get('best_backbone')} F1={training_result.get('best_f1', 0):.4f}")
        meta["status"] = "passed"
    else:
        logger.info(f"GATE FAILED: best F1={training_result.get('best_f1', 0):.4f} after {training_result.get('total_rounds', 0)} rounds")
        meta["status"] = "halted-training"

    meta["f1"] = training_result.get("best_f1", 0)
    meta["backbone"] = training_result.get("best_backbone", "")
    (pdir / "meta.json").write_text(json.dumps(meta, indent=2))

    logger.info(f"\n{'='*60}")
    logger.info(f"PIPELINE COMPLETE: {meta['status']}")
    logger.info(f"{'='*60}")

    print(json.dumps({"status": meta["status"], **training_result}))


if __name__ == "__main__":
    app()
