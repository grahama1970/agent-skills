#!/usr/bin/env python3
"""Run eval questions against a trained classifier model.

Loads the best model from the project's model directory,
runs inference on each eval question, compares predicted vs expected.

Usage:
    python run_eval_questions.py /path/to/project-dir

Reads: eval-questions.json, meta.json, benchmark.json
Outputs: JSON array of {id, text, expected, predicted, passed, confidence}
"""
import json
import os
import sys
from pathlib import Path

from loguru import logger

MODELS_BASE = Path(os.environ.get(
    "CLASSIFIER_LAB_MODELS_DIR",
    "/mnt/storage12tb/media/agents/shared/classifier-lab/models",
))


def find_best_model(project_dir: Path) -> Path | None:
    """Find the best trained model directory for this project."""
    project_name = project_dir.name

    # Check benchmark.json for the selected backbone
    bench_path = project_dir / "benchmark.json"
    if bench_path.exists():
        bench = json.loads(bench_path.read_text())
        backbone = bench.get("selected_backbone", "")
        if backbone:
            # Try exact match and safe name
            for name in [backbone, backbone.replace("/", "-")]:
                model_dir = MODELS_BASE / project_name / name / "best_model"
                if model_dir.exists() and (model_dir / "model.safetensors").exists():
                    return model_dir
                # Also check strategy subdirs
                parent = MODELS_BASE / project_name / name
                if parent.exists():
                    for sub in sorted(parent.iterdir()):
                        best = sub if sub.name == "best_model" else sub / "best_model"
                        if best.exists() and (best / "model.safetensors").exists():
                            return best

    # Fallback: scan model dirs for any best_model
    project_models = MODELS_BASE / project_name
    if project_models.exists():
        for backbone_dir in sorted(project_models.iterdir()):
            best = backbone_dir / "best_model"
            if best.exists() and (best / "model.safetensors").exists():
                return best

    return None


def run_eval(project_dir: str) -> None:
    """Load model, run eval questions, output results."""
    pdir = Path(project_dir)

    # Find model
    model_dir = find_best_model(pdir)
    if not model_dir:
        print(json.dumps({"error": "No trained model found", "results": []}))
        sys.exit(1)

    logger.info(f"Loading model from {model_dir}")

    # Load eval questions
    questions_path = pdir / "eval-questions.json"
    if not questions_path.exists():
        print(json.dumps({"error": "No eval-questions.json", "results": []}))
        sys.exit(1)

    data = json.loads(questions_path.read_text())
    questions = data.get("questions", [])
    if not questions:
        print(json.dumps({"error": "No questions", "results": []}))
        sys.exit(1)

    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    import torch

    tokenizer = AutoTokenizer.from_pretrained(str(model_dir))
    model = AutoModelForSequenceClassification.from_pretrained(str(model_dir))
    model.eval()

    # Load label mapping if available
    label_map_path = model_dir / "label_map.json"
    id2label = {}
    if label_map_path.exists():
        lm = json.loads(label_map_path.read_text())
        id2label = lm.get("id2label", {})

    # Also check config.json for id2label
    config_path = model_dir / "config.json"
    if not id2label and config_path.exists():
        config = json.loads(config_path.read_text())
        id2label = config.get("id2label", {})

    # Run inference
    results = []
    for q in questions:
        text = q.get("text", "")
        expected = q.get("expected", "")
        if not text:
            results.append({"id": q.get("id", ""), "text": text, "expected": expected, "predicted": None, "passed": None, "confidence": 0})
            continue

        try:
            inputs = tokenizer(text[:512], return_tensors="pt", truncation=True, max_length=512)
            # Remove token_type_ids if model doesn't accept it (e.g., DistilBERT)
            if "distilbert" in str(model_dir).lower():
                inputs.pop("token_type_ids", None)

            with torch.no_grad():
                logits = model(**inputs).logits

            probs = torch.softmax(logits, dim=-1)[0]
            pred_idx = probs.argmax().item()
            confidence = probs[pred_idx].item()

            # Map index to label name
            predicted = id2label.get(str(pred_idx), id2label.get(pred_idx, f"LABEL_{pred_idx}"))

            passed = predicted.lower().strip() == expected.lower().strip()
            results.append({
                "id": q.get("id", ""),
                "text": text,
                "expected": expected,
                "predicted": predicted,
                "passed": passed,
                "confidence": round(confidence, 4),
            })
        except Exception as e:
            logger.warning(f"Inference failed for '{text[:50]}': {e}")
            results.append({"id": q.get("id", ""), "text": text, "expected": expected, "predicted": None, "passed": None, "confidence": 0, "error": str(e)})

    passed_count = sum(1 for r in results if r["passed"] is True)
    failed_count = sum(1 for r in results if r["passed"] is False)
    logger.info(f"Results: {passed_count} passed, {failed_count} failed, {len(results)} total")

    print(json.dumps(results))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: run_eval_questions.py <project-dir>"}))
        sys.exit(1)
    run_eval(sys.argv[1])
