#!/usr/bin/env python3
"""VRAM, throughput, and latency distribution profiling for a single model.

Usage:
    python profile.py profile --model models/qra-validator/model.gguf --samples 100
    python profile.py profile --task qra-validator --samples 50
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

SKILL_DIR = Path(__file__).resolve().parent.parent
CREATE_GPT_DIR = SKILL_DIR.parent / "create-gpt"
sys.path.insert(0, str(CREATE_GPT_DIR))

from task_spec import load_task_spec, MODELS_DIR

app = typer.Typer(add_completion=False)


def _generate_sample_inputs(spec, n: int) -> list[str]:
    """Generate sample inputs for profiling."""
    samples = []

    # Try loading from eval data
    from benchmark import load_eval_data
    eval_data = load_eval_data(spec.name)
    for item in eval_data[:n]:
        inp = item.get("input", "")
        if isinstance(inp, dict):
            inp = json.dumps(inp)
        samples.append(inp)

    # Pad with synthetic inputs if needed
    while len(samples) < n:
        if spec.input_schema:
            sample = {}
            for key, prop in spec.input_schema.get("properties", {}).items():
                if prop.get("type") == "string":
                    sample[key] = f"sample_{key}_{len(samples)}"
                elif prop.get("type") == "number":
                    sample[key] = len(samples) * 0.1
                elif prop.get("type") == "boolean":
                    sample[key] = True
            samples.append(json.dumps(sample))
        else:
            samples.append(f"Sample input {len(samples)}")

    return samples[:n]


@app.command("profile")
def profile_cmd(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    model_path: Optional[Path] = typer.Option(None, "--model", "-m"),
    samples: int = typer.Option(100, "--samples", "-n"),
    mode: str = typer.Option("gguf", "--mode", help="gguf or hf"),
    output_json: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """Profile a model's latency, throughput, and resource usage."""
    spec = load_task_spec(task)

    if model_path is None:
        if mode == "gguf":
            model_path = MODELS_DIR / spec.name / "gguf"
        else:
            model_path = MODELS_DIR / spec.name / "sft"

    logger.info(f"Profiling: {task} ({mode})")
    logger.info(f"Model: {model_path}")
    logger.info(f"Samples: {samples}")

    inputs = _generate_sample_inputs(spec, samples)

    sys.path.insert(0, str(CREATE_GPT_DIR / "scripts"))
    from infer import infer_gguf, infer_hf

    # Warmup
    logger.info("Warmup run...")
    try:
        if mode == "gguf":
            infer_gguf(task, inputs[0], model_path)
        else:
            infer_hf(task, inputs[0], model_path)
    except Exception as e:
        logger.warning(f"Warmup failed: {e}")

    # Profile
    latencies = []
    errors = 0
    total_tokens = 0

    logger.info(f"Running {samples} inferences...")
    overall_start = time.time()

    for i, inp in enumerate(inputs):
        try:
            start = time.time()
            if mode == "gguf":
                result = infer_gguf(task, inp, model_path)
            else:
                result = infer_hf(task, inp, model_path)
            latency = (time.time() - start) * 1000
            latencies.append(latency)

            # Estimate tokens
            raw = result.get("raw", "")
            total_tokens += len(raw.split())
        except Exception as e:
            errors += 1
            if errors <= 3:
                logger.warning(f"Inference {i} failed: {e}")

    overall_time = time.time() - overall_start

    if not latencies:
        logger.error("All inferences failed")
        raise typer.Exit(code=1)

    sorted_lat = sorted(latencies)

    def pct(data, p):
        idx = int(len(data) * p / 100)
        return data[min(idx, len(data) - 1)]

    # VRAM check
    vram_mb = 0
    try:
        import torch
        if torch.cuda.is_available():
            vram_mb = torch.cuda.max_memory_allocated() / (1024 * 1024)
    except ImportError:
        pass

    report = {
        "task": task,
        "model": str(model_path),
        "mode": mode,
        "samples": len(latencies),
        "errors": errors,
        "latency": {
            "p50_ms": pct(sorted_lat, 50),
            "p95_ms": pct(sorted_lat, 95),
            "p99_ms": pct(sorted_lat, 99),
            "mean_ms": statistics.mean(latencies),
            "std_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
            "min_ms": min(latencies),
            "max_ms": max(latencies),
        },
        "throughput": {
            "requests_per_sec": len(latencies) / overall_time if overall_time > 0 else 0,
            "tokens_per_sec": total_tokens / overall_time if overall_time > 0 else 0,
            "total_time_sec": overall_time,
        },
        "resources": {
            "vram_mb": vram_mb,
        },
    }

    print(json.dumps(report, indent=2))

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    app()
