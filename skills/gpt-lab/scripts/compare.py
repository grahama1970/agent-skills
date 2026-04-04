#!/usr/bin/env python3
"""Fine-tuned vs prompted comparison analysis.

Answers: "Is fine-tuning worth it for this task?"

Verdict decision tree:
  accuracy delta < -5%                    → NOT_WORTH_IT
  accuracy delta >= -2% AND speedup >= 5x → WORTH_IT
  otherwise                               → MARGINAL

Usage:
    python compare.py compare --task qra-validator \
        --finetuned models/qra-validator/model.gguf \
        --prompted deepseek-v3.2
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.console import Console

SKILL_DIR = Path(__file__).resolve().parent.parent
CREATE_GPT_DIR = SKILL_DIR.parent / "create-gpt"
sys.path.insert(0, str(CREATE_GPT_DIR))

from task_spec import load_task_spec

app = typer.Typer(add_completion=False)
console = Console()


def compute_verdict(
    finetuned_metrics: dict,
    prompted_metrics: dict,
) -> dict:
    """Compute the fine-tuning verdict.

    Returns comparison dict with verdict, accuracy_delta, speedup, cost_savings.
    """
    ft_acc = finetuned_metrics.get("accuracy", 0)
    pt_acc = prompted_metrics.get("accuracy", 0)
    ft_lat = finetuned_metrics.get("latency_p50_ms", 1)
    pt_lat = prompted_metrics.get("latency_p50_ms", 1)
    pt_cost = prompted_metrics.get("cost_per_1k", 0.12)

    accuracy_delta = ft_acc - pt_acc
    speedup = pt_lat / ft_lat if ft_lat > 0 else 0

    # Verdict decision tree
    if accuracy_delta < -0.05:
        verdict = "NOT_WORTH_IT"
    elif accuracy_delta >= -0.02 and speedup >= 5:
        verdict = "WORTH_IT"
    else:
        verdict = "MARGINAL"

    return {
        "finetuning_verdict": verdict,
        "accuracy_delta": round(accuracy_delta, 4),
        "finetuned_accuracy": ft_acc,
        "prompted_accuracy": pt_acc,
        "speedup": f"{speedup:.1f}x",
        "speedup_raw": round(speedup, 1),
        "finetuned_latency_ms": ft_lat,
        "prompted_latency_ms": pt_lat,
        "cost_savings": f"${pt_cost}/1K calls",
        "cost_per_1k_prompted": pt_cost,
    }


@app.command("compare")
def compare_cmd(
    task: str = typer.Option(..., "--task", "-t", help="Task name"),
    finetuned: Path = typer.Option(..., "--finetuned", "-f", help="Path to fine-tuned model"),
    prompted: str = typer.Option("deepseek-v3.2", "--prompted", "-p", help="Prompted model name"),
    eval_file: Optional[Path] = typer.Option(None, "--eval-file"),
    mock: bool = typer.Option(False, "--mock"),
    output_json: Optional[Path] = typer.Option(None, "--output", "-o"),
):
    """Compare fine-tuned model vs prompted model on a task."""
    spec = load_task_spec(task)

    sys.path.insert(0, str(SKILL_DIR / "scripts"))
    from benchmark import load_eval_data, benchmark_model, benchmark_scillm

    eval_data = load_eval_data(task, eval_file)
    if not eval_data and not mock:
        logger.error(f"No eval data for task: {task}")
        raise typer.Exit(code=1)

    if not eval_data and mock:
        eval_data = [{"input": f"test {i}", "output": {"valid": True}} for i in range(20)]

    console.print(f"[bold]Comparing fine-tuned vs prompted for: {task}[/bold]")
    console.print(f"Fine-tuned: {finetuned}")
    console.print(f"Prompted: {prompted}")
    console.print(f"Eval examples: {len(eval_data)}")
    console.print()

    # Benchmark fine-tuned
    if mock:
        import random
        finetuned_metrics = {
            "model": str(finetuned),
            "status": "ok",
            "accuracy": 0.85 + random.random() * 0.10,
            "format_valid": 0.95 + random.random() * 0.05,
            "latency_p50_ms": 150 + random.random() * 100,
            "vram_mb": 1200,
        }
        prompted_metrics = {
            "model": prompted,
            "status": "ok",
            "accuracy": 0.88 + random.random() * 0.10,
            "format_valid": 0.98,
            "latency_p50_ms": 2000 + random.random() * 1000,
            "cost_per_1k": 0.12,
        }
    else:
        console.print("  Benchmarking fine-tuned model...")
        # Determine mode based on file extension
        mode = "gguf" if finetuned.suffix == ".gguf" or finetuned.name.endswith(".gguf") else "hf"
        finetuned_metrics = benchmark_model(
            str(finetuned), eval_data, spec, finetuned, mode
        )

        console.print("  Benchmarking prompted model via /scillm...")
        prompted_metrics = benchmark_scillm(eval_data, spec)

    # Compute verdict
    comparison = compute_verdict(finetuned_metrics, prompted_metrics)

    # Display
    console.print(f"\n{'=' * 60}")
    console.print("[bold]COMPARISON RESULTS[/bold]")
    console.print(f"{'=' * 60}")

    verdict_color = {
        "WORTH_IT": "green",
        "NOT_WORTH_IT": "red",
        "MARGINAL": "yellow",
    }.get(comparison["finetuning_verdict"], "white")

    console.print(f"\nVerdict: [{verdict_color}][bold]{comparison['finetuning_verdict']}[/bold][/{verdict_color}]")
    console.print(f"\nFine-tuned accuracy: {comparison['finetuned_accuracy']:.4f}")
    console.print(f"Prompted accuracy:   {comparison['prompted_accuracy']:.4f}")
    console.print(f"Accuracy delta:      {comparison['accuracy_delta']:+.4f}")
    console.print(f"Speedup:             {comparison['speedup']}")
    console.print(f"Cost savings:        {comparison['cost_savings']}")

    # Full report
    report = {
        "status": "ok",
        "task": task,
        "selected_model": str(finetuned) if comparison["finetuning_verdict"] == "WORTH_IT" else prompted,
        "selected_metrics": finetuned_metrics if comparison["finetuning_verdict"] == "WORTH_IT" else prompted_metrics,
        "results": [finetuned_metrics, prompted_metrics],
        "comparison": comparison,
    }

    print(json.dumps(report, indent=2))

    if output_json:
        output_json.parent.mkdir(parents=True, exist_ok=True)
        output_json.write_text(json.dumps(report, indent=2))


if __name__ == "__main__":
    app()
