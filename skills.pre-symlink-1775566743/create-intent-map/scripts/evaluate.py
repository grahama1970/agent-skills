#!/usr/bin/env python3
"""Evaluation harness for SPARTA Intent Mapper.

Evaluates trained models on a holdout test set with comprehensive metrics.

Usage:
    python evaluate.py run --model models/intent-mapper-grpo --test-file data/eval/test.jsonl
    python evaluate.py split --input data/sft/all.jsonl --train-ratio 0.85
"""

import json
import random
from pathlib import Path
from typing import Optional

import torch
import typer
from loguru import logger

app = typer.Typer()

# Evaluation thresholds
PASS_THRESHOLDS = {
    "accuracy": 0.80,           # Action prediction accuracy
    "entity_f1": 0.70,          # Entity extraction F1
    "avg_grounding": 0.75,      # Average grounding score of results
    "relevance": 0.70,          # LLM judge relevance
    "format_valid": 0.95,       # Valid JSON output rate
}


def load_jsonl(path: Path) -> list[dict]:
    """Load JSONL file."""
    data = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                data.append(json.loads(line))
    return data


def save_jsonl(data: list[dict], path: Path):
    """Save to JSONL file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for item in data:
            f.write(json.dumps(item) + "\n")


@app.command()
def split(
    input_file: Path = typer.Option(..., "--input", "-i", help="Input JSONL file"),
    output_dir: Path = typer.Option(Path("data"), "--output", "-o"),
    train_ratio: float = typer.Option(0.85, "--train-ratio", "-r"),
    seed: int = typer.Option(42, "--seed", "-s"),
):
    """Split data into train/eval sets.

    Ensures no data leakage between training and evaluation.
    """
    random.seed(seed)

    data = load_jsonl(input_file)
    random.shuffle(data)

    split_idx = int(len(data) * train_ratio)
    train_data = data[:split_idx]
    eval_data = data[split_idx:]

    # Save splits
    train_path = output_dir / "sft" / "train.jsonl"
    eval_path = output_dir / "eval" / "test.jsonl"

    save_jsonl(train_data, train_path)
    save_jsonl(eval_data, eval_path)

    logger.info(f"Split {len(data)} examples:")
    logger.info(f"  Train: {len(train_data)} -> {train_path}")
    logger.info(f"  Eval:  {len(eval_data)} -> {eval_path}")


def compute_metrics(
    predictions: list[dict],
    references: list[dict],
    executor=None,
    judge=None,
) -> dict:
    """Compute comprehensive evaluation metrics.

    Args:
        predictions: List of {"input": query, "output": predicted_spec}
        references: List of {"input": query, "output": expected_spec}
        executor: Optional ArangoDB executor for grounding eval
        judge: Optional LLM judge for relevance eval

    Returns:
        Dictionary of metric name -> value
    """
    from rewards.execution import QuerySpec

    metrics = {
        "total": len(predictions),
        "action_correct": 0,
        "entity_tp": 0,
        "entity_fp": 0,
        "entity_fn": 0,
        "format_valid": 0,
        "grounding_scores": [],
        "relevance_scores": [],
    }

    for pred, ref in zip(predictions, references):
        pred_spec = pred.get("output", {})
        ref_spec = ref.get("output", {})

        # Normalize specs
        if isinstance(pred_spec, str):
            try:
                pred_spec = json.loads(pred_spec)
            except json.JSONDecodeError:
                pred_spec = {}
        if isinstance(ref_spec, str):
            try:
                ref_spec = json.loads(ref_spec)
            except json.JSONDecodeError:
                ref_spec = {}

        # Format validity
        if pred_spec and "action" in pred_spec:
            metrics["format_valid"] += 1

        # Action accuracy
        pred_action = pred_spec.get("action", "")
        ref_action = ref_spec.get("action", "QUERY")
        if pred_action == ref_action:
            metrics["action_correct"] += 1

        # Entity F1
        pred_entities = set(pred_spec.get("entities", []))
        ref_entities = set(ref_spec.get("entities", []))

        tp = len(pred_entities & ref_entities)
        fp = len(pred_entities - ref_entities)
        fn = len(ref_entities - pred_entities)

        metrics["entity_tp"] += tp
        metrics["entity_fp"] += fp
        metrics["entity_fn"] += fn

        # Execution-based metrics (if executor provided)
        if executor and pred_spec.get("action") == "QUERY":
            try:
                spec = QuerySpec(pred_spec)
                results = executor.execute(spec)
                if results:
                    avg_grounding = sum(r.get("grounding_score", 0) for r in results) / len(results)
                    metrics["grounding_scores"].append(avg_grounding)

                    # Relevance (if judge provided)
                    if judge:
                        query = pred.get("input", "")
                        relevance = judge.score(query, results)
                        metrics["relevance_scores"].append(relevance)
            except Exception as e:
                logger.warning(f"Execution failed: {e}")

    # Compute final metrics
    total = metrics["total"]

    accuracy = metrics["action_correct"] / total if total > 0 else 0
    format_valid = metrics["format_valid"] / total if total > 0 else 0

    # Entity F1
    precision = metrics["entity_tp"] / (metrics["entity_tp"] + metrics["entity_fp"]) if (metrics["entity_tp"] + metrics["entity_fp"]) > 0 else 0
    recall = metrics["entity_tp"] / (metrics["entity_tp"] + metrics["entity_fn"]) if (metrics["entity_tp"] + metrics["entity_fn"]) > 0 else 0
    entity_f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # Grounding and relevance
    avg_grounding = sum(metrics["grounding_scores"]) / len(metrics["grounding_scores"]) if metrics["grounding_scores"] else 0
    avg_relevance = sum(metrics["relevance_scores"]) / len(metrics["relevance_scores"]) if metrics["relevance_scores"] else 0

    return {
        "accuracy": accuracy,
        "entity_f1": entity_f1,
        "entity_precision": precision,
        "entity_recall": recall,
        "format_valid": format_valid,
        "avg_grounding": avg_grounding,
        "relevance": avg_relevance,
        "total_examples": total,
        "grounding_count": len(metrics["grounding_scores"]),
        "relevance_count": len(metrics["relevance_scores"]),
    }


def check_thresholds(metrics: dict, thresholds: dict = None) -> tuple[bool, list[str]]:
    """Check if metrics meet thresholds.

    Returns:
        (passed, list of failure reasons)
    """
    thresholds = thresholds or PASS_THRESHOLDS
    failures = []

    for metric, threshold in thresholds.items():
        value = metrics.get(metric, 0)
        if value < threshold:
            failures.append(f"{metric}: {value:.3f} < {threshold:.3f}")

    return len(failures) == 0, failures


@app.command()
def run(
    model_path: Path = typer.Option(..., "--model", "-m", help="Path to trained model"),
    test_file: Path = typer.Option(..., "--test-file", "-t", help="Evaluation JSONL file"),
    base_model: str = typer.Option("deepseek-ai/DeepSeek-R1-Distill-Qwen-7B", "--base-model"),
    output_file: Optional[Path] = typer.Option(None, "--output", "-o", help="Save results JSON"),
    use_execution: bool = typer.Option(True, "--execution/--no-execution"),
    mock_execution: bool = typer.Option(False, "--mock-execution"),
    batch_size: int = typer.Option(8, "--batch-size", "-b"),
):
    """Run evaluation on test set.

    Computes all metrics and checks against pass thresholds.
    """
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    logger.info(f"Loading model from {model_path}")

    # Load model
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base = AutoModelForCausalLM.from_pretrained(
        base_model,
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(base, str(model_path))
    model.eval()

    # Load test data
    test_data = load_jsonl(test_file)
    logger.info(f"Loaded {len(test_data)} test examples")

    # System prompt
    from train_grpo import SYSTEM_PROMPT, format_prompt

    # Generate predictions
    predictions = []

    for item in test_data:
        query = item["input"]
        messages = format_prompt(query)

        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        with torch.no_grad():
            outputs = model.generate(
                **inputs,
                max_new_tokens=512,
                temperature=0.1,
                do_sample=True,
                pad_token_id=tokenizer.pad_token_id,
            )

        generated = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

        # Try to parse as JSON
        try:
            spec = json.loads(generated.strip())
        except json.JSONDecodeError:
            # Try extracting JSON from response
            import re
            match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', generated, re.DOTALL)
            if match:
                try:
                    spec = json.loads(match.group())
                except Exception:
                    spec = {}
            else:
                spec = {}

        predictions.append({
            "input": query,
            "output": spec,
            "raw_output": generated,
        })

    # Get executor and judge if needed
    executor = None
    judge = None

    if use_execution:
        from rewards.execution import get_executor
        from rewards.relevance import get_judge

        executor = get_executor(mock=mock_execution)
        judge = get_judge(mock=mock_execution)

    # Compute metrics
    metrics = compute_metrics(predictions, test_data, executor, judge)

    # Check thresholds
    passed, failures = check_thresholds(metrics)

    # Report
    logger.info("\n" + "=" * 50)
    logger.info("EVALUATION RESULTS")
    logger.info("=" * 50)

    for key, value in metrics.items():
        if isinstance(value, float):
            threshold = PASS_THRESHOLDS.get(key)
            status = ""
            if threshold:
                status = " ✓" if value >= threshold else f" ✗ (need {threshold:.2f})"
            logger.info(f"  {key}: {value:.4f}{status}")
        else:
            logger.info(f"  {key}: {value}")

    logger.info("=" * 50)
    if passed:
        logger.info("✓ EVALUATION PASSED")
    else:
        logger.error("✗ EVALUATION FAILED")
        for f in failures:
            logger.error(f"  - {f}")

    # Save results
    results = {
        "model_path": str(model_path),
        "test_file": str(test_file),
        "metrics": metrics,
        "passed": passed,
        "failures": failures,
        "thresholds": PASS_THRESHOLDS,
        "predictions": predictions[:10],  # Sample for debugging
    }

    if output_file:
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(results, f, indent=2)
        logger.info(f"Results saved to {output_file}")

    # Clean up
    if judge and hasattr(judge, 'close'):
        judge.close()

    # Return exit code
    raise typer.Exit(code=0 if passed else 1)


@app.command()
def quick_check(
    model_path: Path = typer.Option(..., "--model", "-m"),
    queries: list[str] = typer.Option(None, "--query", "-q"),
):
    """Quick sanity check with a few queries."""
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from peft import PeftModel

    # Default test queries
    if not queries:
        queries = [
            "How do I detect command injection in spacecraft uplink?",
            "What is the weather in Paris?",
            "Explain RF jamming countermeasures for satellites",
        ]

    tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        "deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        torch_dtype=torch.bfloat16,
        device_map="auto",
        trust_remote_code=True,
    )
    model = PeftModel.from_pretrained(base, str(model_path))
    model.eval()

    from train_grpo import format_prompt

    for query in queries:
        messages = format_prompt(query)
        prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)

        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=256, temperature=0.1)

        generated = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)

        print(f"\nQuery: {query}")
        print(f"Output: {generated[:500]}")
        print("-" * 50)


if __name__ == "__main__":
    app()
