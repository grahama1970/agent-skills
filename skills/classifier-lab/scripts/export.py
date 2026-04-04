#!/usr/bin/env python3
"""Export a trained classifier model to various formats.

Copies the best_model artifacts and optionally converts to ONNX/GGUF.
Writes export-status.json to the project directory.

Usage:
    python export.py /path/to/project --format safetensors
    python export.py /path/to/project --format onnx
    python export.py /path/to/project --model distilbert-base-uncased --format safetensors --push-to-hf
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import typer
from loguru import logger

app = typer.Typer(no_args_is_help=True)

MODELS_BASE = Path("/mnt/storage12tb/media/agents/shared/classifier-lab/models")
EXPORT_BASE = Path("/mnt/storage12tb/media/agents/shared/classifier-lab/exports")


def _find_best_model(project_dir: Path, backbone: str | None) -> Path | None:
    """Find the best_model directory for a project."""
    # If backbone specified, look directly
    if backbone:
        model_dir = MODELS_BASE / project_dir.name / backbone / "best_model"
        if model_dir.exists():
            return model_dir

    # Read benchmark.json for selected backbone
    bench_path = project_dir / "benchmark.json"
    if bench_path.exists():
        bench = json.loads(bench_path.read_text())
        selected = bench.get("selected_backbone", "")
        if selected:
            model_dir = MODELS_BASE / project_dir.name / selected / "best_model"
            if model_dir.exists():
                return model_dir

    # Scan for any best_model directory
    proj_models = MODELS_BASE / project_dir.name
    if proj_models.exists():
        for backbone_dir in proj_models.iterdir():
            best = backbone_dir / "best_model"
            if best.exists() and (best / "model.safetensors").exists():
                return best

    return None


def _export_safetensors(model_dir: Path, export_dir: Path) -> list[str]:
    """Copy safetensors model as-is (already in correct format)."""
    artifacts = []
    for f in model_dir.iterdir():
        if f.is_file():
            shutil.copy2(f, export_dir / f.name)
            artifacts.append(f.name)
    return artifacts


def _export_onnx(model_dir: Path, export_dir: Path) -> list[str]:
    """Export model to ONNX format."""
    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        import torch

        model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir))

        dummy = tokenizer("This is a test", return_tensors="pt", padding="max_length", truncation=True, max_length=128)
        onnx_path = export_dir / "model.onnx"

        torch.onnx.export(
            model,
            (dummy["input_ids"], dummy["attention_mask"]),
            str(onnx_path),
            input_names=["input_ids", "attention_mask"],
            output_names=["logits"],
            dynamic_axes={"input_ids": {0: "batch", 1: "seq"}, "attention_mask": {0: "batch", 1: "seq"}, "logits": {0: "batch"}},
            opset_version=14,
        )

        # Copy tokenizer + config too
        for f in ["config.json", "tokenizer.json", "tokenizer_config.json", "label_map.json"]:
            src = model_dir / f
            if src.exists():
                shutil.copy2(src, export_dir / f)

        artifacts = ["model.onnx"]
        artifacts.extend(f for f in ["config.json", "tokenizer.json", "tokenizer_config.json", "label_map.json"] if (export_dir / f).exists())
        return artifacts
    except Exception as e:
        logger.error(f"ONNX export failed: {e}")
        # Fallback: copy safetensors
        logger.info("Falling back to safetensors copy")
        return _export_safetensors(model_dir, export_dir)


def _push_to_hf(export_dir: Path, project_name: str) -> str | None:
    """Push exported model to HuggingFace Hub."""
    import os
    token = os.environ.get("HF_TOKEN", "")
    if not token:
        logger.warning("HF_TOKEN not set — skipping push")
        return None

    try:
        from huggingface_hub import HfApi
        api = HfApi(token=token)
        repo_id = f"embry/{project_name}"
        api.create_repo(repo_id, exist_ok=True, private=True)
        api.upload_folder(folder_path=str(export_dir), repo_id=repo_id)
        logger.info(f"Pushed to https://huggingface.co/{repo_id}")
        return repo_id
    except Exception as e:
        logger.error(f"HF push failed: {e}")
        return None


@app.command()
def export(
    project_dir: str = typer.Argument(..., help="Path to project directory"),
    model: str = typer.Option("", "--model", help="Backbone name (auto-detected from benchmark.json if not set)"),
    format: str = typer.Option("safetensors", "--format", help="Export format: safetensors, onnx"),
    push_to_hf: bool = typer.Option(False, "--push-to-hf", help="Push to HuggingFace Hub"),
):
    """Export a trained model."""
    pdir = Path(project_dir)
    if not pdir.exists():
        logger.error(f"Project directory not found: {pdir}")
        raise typer.Exit(1)

    model_dir = _find_best_model(pdir, model or None)
    if not model_dir:
        logger.error(f"No trained model found for {pdir.name}")
        print(json.dumps({"error": f"No trained model found for {pdir.name}", "status": "failed"}))
        raise typer.Exit(1)

    logger.info(f"Exporting {pdir.name} from {model_dir} as {format}")

    # Create export directory
    export_dir = EXPORT_BASE / pdir.name / format
    export_dir.mkdir(parents=True, exist_ok=True)

    if format == "onnx":
        artifacts = _export_onnx(model_dir, export_dir)
    else:
        artifacts = _export_safetensors(model_dir, export_dir)

    # Copy model card if it exists
    card_path = pdir / "model-card.md"
    if card_path.exists():
        shutil.copy2(card_path, export_dir / "README.md")
        artifacts.append("README.md")

    # Push to HF if requested
    hf_repo = None
    if push_to_hf:
        hf_repo = _push_to_hf(export_dir, pdir.name)

    status = {
        "status": "exported",
        "format": format,
        "export_dir": str(export_dir),
        "artifacts": artifacts,
        "model_source": str(model_dir),
        "hf_repo": hf_repo,
    }

    # Write to project dir
    (pdir / "export-status.json").write_text(json.dumps(status, indent=2))
    logger.info(f"Exported {len(artifacts)} artifacts to {export_dir}")

    print(json.dumps(status))


if __name__ == "__main__":
    app()
