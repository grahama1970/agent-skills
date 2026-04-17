#!/usr/bin/env python3
"""Core benchmark engine: run N models on a task, measure accuracy/latency/memory.

Adapted from classifier-lab/scripts/benchmark.py.

Usage:
    python benchmark.py benchmark --task qra-validator --models "qwen2.5-0.5b,qwen2.5-1.5b"
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import typer
from loguru import logger

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

SKILL_DIR = Path(__file__).resolve().parent.parent
CREATE_GPT_DIR = SKILL_DIR.parent / "create-gpt"
sys.path.insert(0, str(CREATE_GPT_DIR))

from task_spec import load_task_spec, DATA_DIR, MODELS_DIR

app = typer.Typer(add_completion=False)

# Model shorthand → full name mapping
MODEL_ALIASES = {
    "qwen2.5-0.5b": "Qwen/Qwen2.5-0.5B-Instruct",
    "qwen2.5-1.5b": "Qwen/Qwen2.5-1.5B-Instruct",
    "qwen3-0.6b": "Qwen/Qwen3-0.6B",
    "smollm2-1.7b": "HuggingFaceTB/SmolLM2-1.7B-Instruct",
}


def resolve_model_name(name: str) -> str:
    """Resolve shorthand model name to full HF ID."""
    return MODEL_ALIASES.get(name.lower().strip(), name.strip())


def load_eval_data(task_name: str, eval_file: Optional[Path] = None) -> list[dict]:
    """Load evaluation dataset for a task."""
    if eval_file and eval_file.exists():
        with open(eval_file) as f:
            return [json.loads(line) for line in f if line.strip()]

    # Try val, then holdout, then train
    for split in ["val", "holdout", "train"]:
        path = DATA_DIR / task_name / "sft" / f"{split}.jsonl"
        if path.exists():
            with open(path) as f:
                data = [json.loads(line) for line in f if line.strip()]
            if data:
                return data[:100]  # Cap at 100 for benchmarking

    return []


def benchmark_model(
    model_name: str,
    eval_data: list[dict],
    spec,
    model_path: Optional[Path] = None,
    mode: str = "hf",
) -> Dict[str, Any]:
    """Benchmark a single model on eval data.

    Returns dict with accuracy, format_valid, latency stats, VRAM, tokens/sec.
    """
    latencies = []
    format_valid = 0
    correct = 0
    total = len(eval_data)

    if total == 0:
        return {
            "model": model_name,
            "status": "failed",
            "error": "No eval data",
        }

    try:
        sys.path.insert(0, str(CREATE_GPT_DIR / "scripts"))
        from infer import infer_hf, infer_gguf, infer_ollama

        for item in eval_data:
            user_input, expected = _extract_input_output(item)

            # Run inference
            start = time.time()
            try:
                if mode == "ollama":
                    result = infer_ollama(spec.name, user_input, model_name=model_name)
                elif mode == "gguf" and model_path:
                    result = infer_gguf(spec.name, user_input, model_path)
                else:
                    result = infer_hf(spec.name, user_input, model_path)
            except Exception as e:
                logger.warning(f"Inference failed for example: {e}")
                latencies.append(0)
                continue

            latency = (time.time() - start) * 1000
            latencies.append(latency)

            output = result.get("output", {})

            # Check format validity — model produced parseable dict
            if isinstance(output, dict) and output:
                format_valid += 1

            # Check accuracy — cascade-aware comparison:
            # - enum fields (grade, tags): exact match
            # - numeric fields (confidence): ±0.2 tolerance
            # - text fields (rationale): rapidfuzz token_set_ratio
            # - array fields: set overlap (Jaccard)
            if isinstance(output, dict) and isinstance(expected, dict):
                correct += _cascade_accuracy(output, expected)

        # Compute stats
        valid_latencies = [l for l in latencies if l > 0]
        sorted_lat = sorted(valid_latencies) if valid_latencies else [0]

        def percentile(data, p):
            if not data:
                return 0
            idx = int(len(data) * p / 100)
            return data[min(idx, len(data) - 1)]

        # VRAM estimation
        vram_mb = _estimate_vram(model_name)

        return {
            "model": model_name,
            "status": "ok",
            "accuracy": correct / total if total > 0 else 0,
            "format_valid": format_valid / total if total > 0 else 0,
            "latency_p50_ms": percentile(sorted_lat, 50),
            "latency_p95_ms": percentile(sorted_lat, 95),
            "latency_p99_ms": percentile(sorted_lat, 99),
            "latency_mean_ms": sum(valid_latencies) / len(valid_latencies) if valid_latencies else 0,
            "vram_mb": vram_mb,
            "total_examples": total,
            "valid_inferences": len(valid_latencies),
        }

    except Exception as e:
        return {
            "model": model_name,
            "status": "failed",
            "error": str(e),
            "accuracy": 0.0,
            "format_valid": 0.0,
        }


def benchmark_scillm(
    eval_data: list[dict],
    spec,
) -> Dict[str, Any]:
    """Benchmark via /scillm Chutes API."""
    latencies = []
    format_valid = 0
    correct = 0
    total = len(eval_data)

    try:
        scillm_dir = SKILL_DIR.parent / "scillm"
        sys.path.insert(0, str(scillm_dir))
        from batch import quick_completion

        for item in eval_data:
            user_input, expected = _extract_input_output(item)

            prompt_parts = []
            if spec.system_prompt:
                prompt_parts.append(spec.system_prompt)
            prompt_parts.append(f"\nInput:\n{user_input}")

            start = time.time()
            try:
                result_text = quick_completion(
                    prompt="\n".join(prompt_parts),
                    json_mode=True,
                    timeout=30,
                )
                output = json.loads(result_text)
            except Exception:
                output = {}

            latency = (time.time() - start) * 1000
            latencies.append(latency)

            if isinstance(output, dict) and output:
                format_valid += 1

            if isinstance(output, dict) and isinstance(expected, dict):
                correct += _cascade_accuracy(output, expected)

        sorted_lat = sorted(latencies) if latencies else [0]

        def percentile(data, p):
            if not data:
                return 0
            idx = int(len(data) * p / 100)
            return data[min(idx, len(data) - 1)]

        return {
            "model": "deepseek-v3.2-prompted",
            "status": "ok",
            "accuracy": correct / total if total > 0 else 0,
            "format_valid": format_valid / total if total > 0 else 0,
            "latency_p50_ms": percentile(sorted_lat, 50),
            "latency_p95_ms": percentile(sorted_lat, 95),
            "latency_mean_ms": sum(latencies) / len(latencies) if latencies else 0,
            "vram_mb": 0,
            "cost_per_1k": 0.12,
            "total_examples": total,
        }

    except Exception as e:
        return {
            "model": "deepseek-v3.2-prompted",
            "status": "failed",
            "error": str(e),
        }


def _cascade_accuracy(output: dict, expected: dict) -> float:
    """Cascade-aware accuracy: GPTs provide rationale, not structured classification.

    Scoring strategy per field type:
    - enum fields (grade, tags): exact match (1.0 or 0.0)
    - numeric fields (confidence): ±0.2 tolerance
    - text fields (rationale, etc): rapidfuzz token_set_ratio / 100
    - array fields (tags): Jaccard set overlap
    - boolean fields: exact match
    """
    from rapidfuzz import fuzz

    if not expected:
        return 0.0

    scores = []
    for key, exp_val in expected.items():
        out_val = output.get(key)
        if out_val is None:
            scores.append(0.0)
            continue

        # Array fields (tags) — Jaccard set overlap
        if isinstance(exp_val, list) and isinstance(out_val, list):
            exp_set = set(str(v).lower() for v in exp_val)
            out_set = set(str(v).lower() for v in out_val)
            if exp_set or out_set:
                scores.append(len(exp_set & out_set) / len(exp_set | out_set))
            else:
                scores.append(1.0)
        # Numeric fields — tolerance ±0.2
        elif isinstance(exp_val, (int, float)) and isinstance(out_val, (int, float)):
            scores.append(1.0 if abs(exp_val - out_val) <= 0.2 else 0.0)
        # Boolean fields — exact match
        elif isinstance(exp_val, bool):
            scores.append(1.0 if out_val == exp_val else 0.0)
        # String fields — fuzzy match for rationale, exact for enums
        elif isinstance(exp_val, str) and isinstance(out_val, str):
            # Short enum-like values (grade: PASS/WARN/FAIL) — exact match
            if len(exp_val) <= 10 and exp_val.isupper():
                scores.append(1.0 if out_val.strip().upper() == exp_val else 0.0)
            else:
                # Free-text rationale — fuzzy match
                scores.append(fuzz.token_set_ratio(exp_val, str(out_val)) / 100.0)
        else:
            # Fallback: exact match
            scores.append(1.0 if out_val == exp_val else 0.0)

    return sum(scores) / len(scores) if scores else 0.0


def _extract_input_output(item: dict) -> tuple:
    """Extract user input and expected output from eval data.

    Handles both formats:
    - Simple: {"input": "...", "output": {...}}
    - HF messages: {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}
    """
    # HF messages format
    if "messages" in item and isinstance(item["messages"], list):
        user_input = ""
        expected = {}
        for msg in item["messages"]:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "user":
                user_input = content
            elif role == "assistant":
                try:
                    expected = json.loads(content)
                except (json.JSONDecodeError, TypeError):
                    expected = {"text": content}
        return user_input, expected

    # Simple input/output format
    user_input = item.get("input", "")
    if isinstance(user_input, dict):
        user_input = json.dumps(user_input)

    expected = item.get("output", {})
    if isinstance(expected, str):
        try:
            expected = json.loads(expected)
        except json.JSONDecodeError:
            expected = {"text": expected}

    return user_input, expected


def _estimate_vram(model_name: str) -> int:
    """Estimate VRAM usage based on model size."""
    name_lower = model_name.lower()
    if "0.5b" in name_lower:
        return 600
    elif "0.6b" in name_lower:
        return 700
    elif "1.5b" in name_lower:
        return 1200
    elif "1.7b" in name_lower:
        return 1400
    elif "7b" in name_lower:
        return 5000
    return 2000


@app.command("benchmark")
def benchmark_cmd(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    models: str = typer.Option(..., "--models", "-m", help="Comma-separated model names"),
    eval_file: Optional[Path] = typer.Option(None, "--eval-file"),
    output_json: Optional[Path] = typer.Option(None, "--output", "-o"),
    include_scillm: bool = typer.Option(False, "--include-scillm"),
):
    """Benchmark multiple models on a task."""
    spec = load_task_spec(task)
    eval_data = load_eval_data(task, eval_file)

    if not eval_data:
        logger.error(f"No evaluation data found for task: {task}")
        raise typer.Exit(code=1)

    logger.info(f"Benchmarking {task} with {len(eval_data)} examples")

    model_list = [m.strip() for m in models.split(",") if m.strip()]
    results = []

    monitor = TaskClient(f"gpt-lab/benchmark/{task}", total=len(model_list), description=f"Benchmarking {task}") if TaskClient else None

    for model_name in model_list:
        full_name = resolve_model_name(model_name)
        logger.info(f"Benchmarking: {full_name}")

        # Check for GGUF model first (preferred for benchmarking trained models)
        gguf_dir = MODELS_DIR / task / "gguf"
        gguf_files = list(gguf_dir.glob("*.gguf")) if gguf_dir.exists() else []
        finetuned_path = MODELS_DIR / task / "sft"

        if model_name == "trained":
            # Shorthand: --models trained → prefer Ollama (long-running), fallback GGUF, then SFT
            result = benchmark_model(f"embry/{task}", eval_data, spec, mode="ollama")
        elif model_name.endswith("-gguf") and gguf_files:
            result = benchmark_model(model_name, eval_data, spec, gguf_files[0], mode="gguf")
        elif model_name.endswith("-finetuned") and finetuned_path.exists():
            result = benchmark_model(model_name, eval_data, spec, finetuned_path)
        else:
            result = benchmark_model(full_name, eval_data, spec)

        results.append(result)
        logger.info(
            f"  {result.get('status')}: accuracy={result.get('accuracy', 0):.4f}, "
            f"latency_p50={result.get('latency_p50_ms', 0):.0f}ms"
        )
        if monitor:
            monitor.update(item=f"{model_name} acc={result.get('accuracy', 0):.4f}")

    if include_scillm:
        logger.info("Benchmarking: deepseek-v3.2-prompted (via /scillm)")
        scillm_result = benchmark_scillm(eval_data, spec)
        results.append(scillm_result)

    # Select winner
    viable = [r for r in results if r.get("status") == "ok"]
    if viable:
        winner = sorted(
            viable,
            key=lambda r: (r.get("accuracy", 0), -r.get("latency_p50_ms", 9999)),
            reverse=True,
        )[0]
    else:
        winner = None

    report = {
        "status": "ok" if winner else "failed",
        "task": task,
        "selected_model": winner["model"] if winner else None,
        "selected_metrics": {
            "accuracy": winner.get("accuracy", 0),
            "latency_p50_ms": winner.get("latency_p50_ms", 0),
        } if winner else None,
        "results": results,
        "eval_examples": len(eval_data),
    }

    print(json.dumps(report, indent=2))

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2))

    if monitor:
        monitor.finish(success=winner is not None)

    if not winner:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
