#!/usr/bin/env python3
"""Evaluation harness for task-specific GPTs with quality gates.

Adapted from create-intent-map/scripts/evaluate.py.

Usage:
    python evaluate.py run --task qra-validator --mock
    python evaluate.py run --task qra-validator --model models/qra-validator/sft
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from task_spec import load_task_spec, DATA_DIR, MODELS_DIR

app = typer.Typer(add_completion=False)


def load_jsonl(path: Path) -> list[dict]:
    """Load JSONL file."""
    data = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def validate_output_schema(output: dict, schema: dict) -> tuple[bool, list[str]]:
    """Validate output against JSON schema."""
    issues = []

    if not schema:
        return True, []

    try:
        import jsonschema
        jsonschema.validate(output, schema)
        return True, []
    except ImportError:
        # Fallback: manual required-field check
        required = schema.get("required", [])
        for field in required:
            if field not in output:
                issues.append(f"Missing required field: {field}")
        return len(issues) == 0, issues
    except Exception as e:
        issues.append(str(e))
        return False, issues


def compute_metrics(
    predictions: list[dict],
    references: list[dict],
    output_schema: dict,
) -> dict:
    """Compute evaluation metrics for task-specific GPT predictions.

    Args:
        predictions: List of {"input": ..., "output": parsed_dict, "raw_output": str}
        references: List of {"input": ..., "output": expected_dict}
        output_schema: JSON Schema for output validation

    Returns:
        Dictionary of metric name -> value
    """
    total = len(predictions)
    if total == 0:
        return {"accuracy": 0.0, "format_valid": 0.0, "total": 0}

    format_valid = 0
    exact_match = 0
    field_scores = {}

    for pred, ref in zip(predictions, references):
        pred_out = pred.get("output", {})
        ref_out = ref.get("output", {})

        if isinstance(pred_out, str):
            try:
                pred_out = json.loads(pred_out)
            except json.JSONDecodeError:
                pred_out = {}
        if isinstance(ref_out, str):
            try:
                ref_out = json.loads(ref_out)
            except json.JSONDecodeError:
                ref_out = {}

        # Format validity
        valid, _ = validate_output_schema(pred_out, output_schema)
        if valid and pred_out:
            format_valid += 1

        # Exact match
        if pred_out == ref_out:
            exact_match += 1

        # Per-field accuracy
        if isinstance(ref_out, dict):
            for key, ref_val in ref_out.items():
                if key not in field_scores:
                    field_scores[key] = {"correct": 0, "total": 0}
                field_scores[key]["total"] += 1
                pred_val = pred_out.get(key) if isinstance(pred_out, dict) else None
                if pred_val == ref_val:
                    field_scores[key]["correct"] += 1

    # Compute field accuracies
    field_accuracies = {}
    for key, counts in field_scores.items():
        field_accuracies[key] = counts["correct"] / counts["total"] if counts["total"] > 0 else 0.0

    # Overall accuracy = average of per-field accuracies (or exact match if no fields)
    if field_accuracies:
        accuracy = sum(field_accuracies.values()) / len(field_accuracies)
    else:
        accuracy = exact_match / total

    return {
        "accuracy": accuracy,
        "exact_match": exact_match / total,
        "format_valid": format_valid / total,
        "total_examples": total,
        "field_accuracies": field_accuracies,
    }


def check_thresholds(metrics: dict, thresholds: dict) -> tuple[bool, list[str]]:
    """Check if metrics meet the task's eval thresholds.

    Returns (passed, list of failure reasons).
    """
    failures = []
    for metric, threshold in thresholds.items():
        if metric == "latency_p50_ms":
            continue  # Latency checked separately during inference
        value = metrics.get(metric, 0)
        if value < threshold:
            failures.append(f"{metric}: {value:.3f} < {threshold:.3f}")
    return len(failures) == 0, failures


def _mock_evaluate(spec, test_data: list[dict]) -> list[dict]:
    """Mock evaluation (no GPU required)."""
    import random

    predictions = []
    for item in test_data:
        output = item.get("output", {})
        if isinstance(output, str):
            try:
                output = json.loads(output)
            except json.JSONDecodeError:
                output = {}

        # Simulate imperfect predictions
        pred_output = dict(output) if isinstance(output, dict) else {}
        if random.random() < 0.15:  # 15% error rate
            if pred_output:
                key = random.choice(list(pred_output.keys()))
                pred_output[key] = "WRONG"

        predictions.append({
            "input": item.get("input", ""),
            "output": pred_output,
            "raw_output": json.dumps(pred_output),
        })
    return predictions


def _real_evaluate(spec, test_data: list[dict], model_path: Path) -> list[dict]:
    """Real evaluation using trained model."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    logger.info(f"Loading model from {model_path}")

    tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base = AutoModelForCausalLM.from_pretrained(
        spec.base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )

    # Try loading as PEFT model, fall back to base
    try:
        model = PeftModel.from_pretrained(base, str(model_path))
    except Exception:
        model = base
    model.eval()

    predictions = []
    for item in test_data:
        user_input = item.get("input", "")
        # Handle messages format (from prepare_data.py output)
        if not user_input and "messages" in item:
            for msg in item["messages"]:
                if msg.get("role") == "user":
                    user_input = msg["content"]
                    break
        if isinstance(user_input, dict):
            user_input = json.dumps(user_input)

        messages = []
        if spec.system_prompt:
            messages.append({"role": "system", "content": spec.system_prompt})
        messages.append({"role": "user", "content": user_input})

        prompt = tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=spec.max_seq_length,
                temperature=0.1,
                do_sample=True,
                pad_token_id=tokenizer.pad_token_id,
            )

        generated = tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True
        )

        # Parse JSON output
        import re
        parsed = {}
        try:
            parsed = json.loads(generated.strip())
        except json.JSONDecodeError:
            match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', generated, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        predictions.append({
            "input": user_input,
            "output": parsed,
            "raw_output": generated,
        })

    return predictions


@app.command()
def run(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    model_path: Optional[Path] = typer.Option(None, "--model", "-m"),
    test_file: Optional[Path] = typer.Option(None, "--test-file"),
    holdout: bool = typer.Option(False, "--holdout", help="Use holdout set instead of val"),
    mock: bool = typer.Option(False, "--mock", help="Mock evaluation"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """Run evaluation on test/holdout set with quality gates."""
    spec = load_task_spec(task)

    if test_file is None:
        split_name = "holdout" if holdout else "val"
        test_file = DATA_DIR / spec.name / "sft" / f"{split_name}.jsonl"

    if not test_file.exists():
        logger.error(f"Test file not found: {test_file}")
        raise typer.Exit(code=1)

    if model_path is None:
        model_path = MODELS_DIR / spec.name / "sft"

    test_data = load_jsonl(test_file)
    logger.info(f"Loaded {len(test_data)} test examples from {test_file}")

    # Generate predictions
    if mock:
        predictions = _mock_evaluate(spec, test_data)
    else:
        predictions = _real_evaluate(spec, test_data, model_path)

    # Compute metrics
    # Build references from test data
    references = []
    for item in test_data:
        out = item.get("output", {})
        if isinstance(out, str):
            try:
                out = json.loads(out)
            except json.JSONDecodeError:
                out = {}
        # Also check messages format
        if not out and "messages" in item:
            for msg in item["messages"]:
                if msg.get("role") == "assistant":
                    try:
                        out = json.loads(msg["content"])
                    except (json.JSONDecodeError, TypeError):
                        out = msg.get("content", "")
        references.append({"input": item.get("input", ""), "output": out})

    metrics = compute_metrics(predictions, references, spec.output_schema)

    # Check thresholds
    passed, failures = check_thresholds(metrics, spec.eval_thresholds)

    # Report
    logger.info("\n" + "=" * 50)
    logger.info("EVALUATION RESULTS")
    logger.info("=" * 50)

    for key, value in metrics.items():
        if isinstance(value, float):
            threshold = spec.eval_thresholds.get(key)
            status = ""
            if threshold:
                status = " PASS" if value >= threshold else f" FAIL (need {threshold:.2f})"
            logger.info(f"  {key}: {value:.4f}{status}")
        elif key != "field_accuracies":
            logger.info(f"  {key}: {value}")

    if metrics.get("field_accuracies"):
        logger.info("  Field accuracies:")
        for field, acc in metrics["field_accuracies"].items():
            logger.info(f"    {field}: {acc:.4f}")

    logger.info("=" * 50)
    if passed:
        logger.info("EVALUATION PASSED")
    else:
        logger.error("EVALUATION FAILED")
        for f in failures:
            logger.error(f"  - {f}")

    # Save results
    results = {
        "task": spec.name,
        "model_path": str(model_path),
        "test_file": str(test_file),
        "metrics": metrics,
        "passed": passed,
        "failures": failures,
        "thresholds": spec.eval_thresholds,
    }

    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(results, indent=2))
        logger.info(f"Results saved to {output_file}")

    raise typer.Exit(code=0 if passed else 1)


if __name__ == "__main__":
    app()
