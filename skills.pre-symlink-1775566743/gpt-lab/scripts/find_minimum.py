#!/usr/bin/env python3
"""Find the smallest model meeting an accuracy threshold.

Adapted from prompt-lab/pl_find_minimum.py.

Tests base models smallest-first, stopping at first model meeting threshold.
Recommends the minimum viable base model for /create-gpt fine-tuning.

Usage:
    python find_minimum.py find-minimum --task qra-validator --threshold 0.85
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

SKILL_DIR = Path(__file__).resolve().parent.parent
CREATE_GPT_DIR = SKILL_DIR.parent / "create-gpt"
sys.path.insert(0, str(CREATE_GPT_DIR))

from task_spec import load_task_spec

app = typer.Typer(add_completion=False)
console = Console()

# Ordered smallest-first for find-minimum search
CANDIDATE_MODELS = [
    {"name": "Qwen/Qwen2.5-0.5B-Instruct", "params_b": 0.5},
    {"name": "Qwen/Qwen3-0.6B", "params_b": 0.6},
    {"name": "Qwen/Qwen2.5-1.5B-Instruct", "params_b": 1.5},
    {"name": "HuggingFaceTB/SmolLM2-1.7B-Instruct", "params_b": 1.7},
    {"name": "Qwen/Qwen2.5-3B-Instruct", "params_b": 3.0},
    {"name": "Qwen/Qwen2.5-7B-Instruct", "params_b": 7.0},
    {"name": "Qwen/Qwen2.5-14B-Instruct", "params_b": 14.0},
    {"name": "Qwen/Qwen2.5-32B-Instruct", "params_b": 32.0},
]


def _quick_sft_eval(
    model_name: str,
    spec,
    eval_data: list[dict],
    max_examples: int = 100,
    mock: bool = False,
) -> dict:
    """Quick SFT on a few examples and evaluate.

    For find-minimum, we do minimal training to test if the model can
    learn the task pattern at all.
    """
    if mock:
        import random
        # Simulate: bigger models do better
        params_b = next(
            (m["params_b"] for m in CANDIDATE_MODELS if m["name"] == model_name),
            1.0,
        )
        base_acc = 0.5 + params_b * 0.2 + random.random() * 0.1
        accuracy = min(0.98, base_acc)
        format_valid = min(0.99, 0.7 + params_b * 0.15 + random.random() * 0.05)
        latency = 50 + (params_b * 100) + random.random() * 50

        return {
            "model": model_name,
            "accuracy": accuracy,
            "format_valid": format_valid,
            "latency_ms": latency,
            "status": "ok",
            "mock": True,
        }

    # Use Ollama for zero-shot eval (pull model if needed, test via API)
    try:
        import subprocess
        import httpx

        # Map HF model names to Ollama model names
        OLLAMA_MODEL_MAP = {
            "Qwen/Qwen2.5-0.5B-Instruct": "qwen2.5:0.5b",
            "Qwen/Qwen3-0.6B": "qwen3:0.6b",
            "Qwen/Qwen2.5-1.5B-Instruct": "qwen2.5:1.5b",
            "HuggingFaceTB/SmolLM2-1.7B-Instruct": "smollm2:1.7b",
            "Qwen/Qwen2.5-3B-Instruct": "qwen2.5:3b",
            "Qwen/Qwen2.5-7B-Instruct": "qwen2.5:7b",
            "Qwen/Qwen2.5-14B-Instruct": "qwen2.5:14b",
            "Qwen/Qwen2.5-32B-Instruct": "qwen2.5:32b",
        }
        ollama_name = OLLAMA_MODEL_MAP.get(model_name)
        if not ollama_name:
            raise ValueError(f"No Ollama mapping for {model_name}")

        # Pull model if not already available
        logger.info(f"Ensuring Ollama model {ollama_name} is available...")
        subprocess.run(
            ["docker", "exec", "ollama-inference", "ollama", "pull", ollama_name],
            timeout=600, check=True, capture_output=True,
        )

        # Benchmark via Ollama API
        sys.path.insert(0, str(CREATE_GPT_DIR / "scripts"))
        from benchmark import benchmark_model
        result = benchmark_model(
            ollama_name,
            eval_data[:max_examples],
            spec,
            mode="ollama",
        )
        return result
    except Exception as e:
        logger.warning(f"Ollama eval failed for {model_name}: {e}")
        return {
            "model": model_name,
            "status": "failed",
            "error": str(e),
            "accuracy": 0.0,
        }


@app.command("find-minimum")
def find_minimum(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    threshold: float = typer.Option(0.85, "--threshold"),
    max_models: int = typer.Option(8, "--max-models"),
    mock: bool = typer.Option(False, "--mock"),
    output_json: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """Find the smallest model meeting the accuracy threshold.

    Tests models from smallest to largest, stopping at first model
    that meets the threshold.
    """
    spec = load_task_spec(task)

    from benchmark import load_eval_data
    eval_data = load_eval_data(task)

    if not eval_data and not mock:
        logger.error(f"No eval data for task: {task}")
        raise typer.Exit(code=1)

    if not eval_data and mock:
        eval_data = [{"input": f"test {i}", "output": {"valid": True}} for i in range(20)]

    console.print(f"[bold]Finding minimum model for: {task}[/bold]")
    console.print(f"Threshold: {threshold*100:.0f}%")
    console.print(f"Eval examples: {len(eval_data)}")
    console.print()

    results = []
    winner = None

    for candidate in CANDIDATE_MODELS[:max_models]:
        model_name = candidate["name"]
        params_b = candidate["params_b"]

        console.print(f"  Testing [bold]{model_name}[/bold] ({params_b}B)...")

        result = _quick_sft_eval(model_name, spec, eval_data, mock=mock)
        results.append(result)

        accuracy = result.get("accuracy", 0)
        status = "[green]PASS[/green]" if accuracy >= threshold else "[red]FAIL[/red]"
        console.print(
            f"    {status} accuracy={accuracy*100:.0f}% "
            f"format={result.get('format_valid', 0)*100:.0f}%"
        )

        if accuracy >= threshold:
            winner = result
            console.print(f"\n[green]Found minimum model: {model_name} ({params_b}B)[/green]")
            break

    # Summary table
    console.print(f"\n{'=' * 60}")
    console.print("[bold]SUMMARY[/bold]")

    table = Table("Model", "Size", "Accuracy", "Format%", "Status")
    for r in results:
        style = "green" if r.get("accuracy", 0) >= threshold else ""
        table.add_row(
            r.get("model", "?"),
            f"{next((m['params_b'] for m in CANDIDATE_MODELS if m['name'] == r.get('model')), '?')}B",
            f"{r.get('accuracy', 0)*100:.0f}%",
            f"{r.get('format_valid', 0)*100:.0f}%",
            r.get("status", "?"),
            style=style,
        )
    console.print(table)

    if winner:
        console.print(f"\n[bold green]RECOMMENDED: {winner['model']}[/bold green]")
    else:
        console.print(f"\n[red]No model met the {threshold*100:.0f}% threshold[/red]")

    # Save results
    output = {
        "task": task,
        "threshold": threshold,
        "winner": winner,
        "all_results": results,
        "recommendation": winner["model"] if winner else None,
    }

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(output, indent=2))

    if not winner:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
