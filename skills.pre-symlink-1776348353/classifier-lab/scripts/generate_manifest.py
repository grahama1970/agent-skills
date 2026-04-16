#!/usr/bin/env python3
"""Generate a /thunderdome manifest from a Classifier Lab project.

Reads project config and creates a YAML manifest for concurrent
backbone racing via thunderdome.

Usage:
    python generate_manifest.py /path/to/project-dir [--output manifest.yaml]
"""
import json
import sys
from pathlib import Path

import typer
import yaml
from loguru import logger

app = typer.Typer(no_args_is_help=True)


@app.command()
def generate(
    project_dir: str = typer.Argument(..., help="Path to classifier project directory"),
    output: str = typer.Option("", help="Output path for manifest (default: project-dir/thunderdome-manifest.yaml)"),
):
    """Generate a thunderdome manifest from project config."""
    pdir = Path(project_dir)

    meta = json.loads((pdir / "meta.json").read_text()) if (pdir / "meta.json").exists() else {}
    tune = json.loads((pdir / "tune-config.json").read_text()) if (pdir / "tune-config.json").exists() else {}

    project_name = meta.get("name", pdir.name)
    modality = meta.get("modality", "text")
    goal = meta.get("goal", f"{modality} classification")

    # Get backbones
    backbones = tune.get("backbones", [])
    if isinstance(backbones, str):
        backbones = [b.strip() for b in backbones.split(",") if b.strip()]
    if not backbones:
        defaults = {
            "text": ["distilbert-base-uncased", "sentence-transformers/all-MiniLM-L6-v2"],
            "vision": ["efficientnet_b0", "convnext_tiny"],
            "tabular": ["gradient_boosting", "random_forest"],
        }
        backbones = defaults.get(modality, defaults["text"])

    gate_f1 = tune.get("gate_f1", 0.90)
    lr = tune.get("lr", 2e-5)
    epochs = tune.get("epochs", 10)
    batch_size = tune.get("batch_size", 16)
    max_length = tune.get("max_length", 128)

    # Build strategies — one per backbone
    # Strategies match thunderdome's Strategy dataclass fields exactly
    strategies = []
    for backbone in backbones:
        safe_name = backbone.replace("/", "-").replace(".", "-")
        strategies.append({
            "name": safe_name,
            "modality": modality,
            "backbones": backbone,
            "epochs": epochs,
            "lr": lr,
            "batch_size": batch_size,
            "dropout": 0.1,
            "weight_decay": 0.01,
            "label_smoothing": 0.0,
            "mixup_alpha": 0.0,
            "cutmix_alpha": 0.0,
            "random_erasing": 0.0,
        })

    manifest = {
        "name": project_name,
        "description": f"Classifier tournament for: {goal}",
        "data_dir": str(pdir),
        "skill": "classifier-lab",
        "scoring": {
            "metric_path": "$.selected_metrics.macro_f1",
            "metric_regex": r"macro_f1[\:\s=]+([0-9.]+)",
            "gate_threshold": gate_f1,
            "direction": "higher_better",
        },
        "convergence": {
            "max_rounds": min(len(backbones) * 2, 10),
            "n_strategies": len(strategies),
            "plateau_window": 3,
            "plateau_epsilon": 0.02,
        },
        "strategies": strategies,
        "variables": {
            "data_dir": str(pdir),
            "modality": modality,
            "gate_f1": gate_f1,
        },
        "dogpile_on_failure": True,
        "memory_scope": "classifier-lab",
    }

    out_path = Path(output) if output else pdir / "thunderdome-manifest.yaml"
    out_path.write_text(yaml.dump(manifest, default_flow_style=False, sort_keys=False))

    logger.info(f"Manifest written to {out_path}")
    logger.info(f"  Strategies: {len(strategies)} ({', '.join(backbones)})")
    logger.info(f"  Gate: F1 ≥ {gate_f1}")

    print(json.dumps({"path": str(out_path), "strategies": len(strategies), "backbones": backbones}))


if __name__ == "__main__":
    app()
