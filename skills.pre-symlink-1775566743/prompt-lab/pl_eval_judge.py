"""Generic judge prompt evaluation CLI command.

Evaluates prompts that output a verdict (PASS/FAIL/AMBIGUOUS etc.)
against ground truth. Unlike `eval` which is taxonomy-specific, this
works with any prompt + ground truth that uses the verdict pattern.

Ground truth format (in ground_truth/{name}.json):
    [
        {"input": "...", "expected_output": "PASS", "metadata": {...}},
        ...
    ]
    OR
    {"cases": [{"input": "...", "expected_output": "FAIL"}, ...]}

The prompt file (prompts/{name}.txt) is used as the system prompt.
Each case's `input` field is sent as the user message.
The LLM response is parsed as JSON and the `verdict` field is compared
to `expected_output`.
"""
import asyncio
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import typer
from rich.table import Table

from config import SKILL_DIR, ensure_dirs
from evaluation import load_models_config
from llm import call_provider
from model_memory import get_model_memory, record_eval_result
from utils import notify_task_monitor

from pl_app import app, console


def _load_judge_ground_truth(name: str, skill_dir: Path) -> list[dict]:
    """Load ground truth for judge evaluation.

    Supports two formats:
      - Flat array: [{"input": ..., "expected_output": ...}, ...]
      - Wrapped:    {"cases": [{"input": ..., "expected_output": ...}, ...]}
    """
    gt_file = skill_dir / "ground_truth" / f"{name}.json"
    if not gt_file.exists():
        raise FileNotFoundError(f"Ground truth not found: {gt_file}")

    data = json.loads(gt_file.read_text())
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "cases" in data:
        return data["cases"]
    raise ValueError(f"Invalid ground truth format in {gt_file}")


def _parse_verdict(response_text: str) -> dict:
    """Parse JSON verdict from LLM response, handling markdown fences."""
    text = response_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"verdict": "PARSE_ERROR", "confidence": 0.0, "rationale": f"Failed to parse: {text[:200]}"}


def _compute_class_metrics(predictions: list[str], labels: list[str], classes: list[str]) -> dict:
    """Compute per-class precision, recall, F1 and macro averages."""
    metrics = {}
    for cls in classes:
        tp = sum(1 for p, l in zip(predictions, labels) if p == cls and l == cls)
        fp = sum(1 for p, l in zip(predictions, labels) if p == cls and l != cls)
        fn = sum(1 for p, l in zip(predictions, labels) if p != cls and l == cls)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        metrics[cls] = {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn}

    # Macro averages (only over classes present in labels)
    present_classes = [c for c in classes if any(l == c for l in labels)]
    if present_classes:
        metrics["macro_precision"] = sum(metrics[c]["precision"] for c in present_classes) / len(present_classes)
        metrics["macro_recall"] = sum(metrics[c]["recall"] for c in present_classes) / len(present_classes)
        metrics["macro_f1"] = sum(metrics[c]["f1"] for c in present_classes) / len(present_classes)
    else:
        metrics["macro_precision"] = 0.0
        metrics["macro_recall"] = 0.0
        metrics["macro_f1"] = 0.0

    return metrics


@app.command("eval-judge")
def eval_judge(
    prompt: str = typer.Option(..., "--prompt", "-p", help="Prompt name (loads prompts/{name}.txt and ground_truth/{name}.json)"),
    model: str = typer.Option("deepseek", "--model", "-m", help="Model to use"),
    cases: int = typer.Option(0, "--cases", "-n", help="Number of cases (0=all)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-case details"),
    f1_threshold: float = typer.Option(0.75, "--f1-threshold", help="Macro F1 quality gate threshold"),
    task_name: str = typer.Option("", "--task-name", help="Task-monitor task name for quality gate"),
):
    """Evaluate a judge prompt against ground truth verdicts.

    Generic evaluation for any prompt that outputs JSON with a `verdict` field.
    Loads system prompt from prompts/{name}.txt and ground truth from
    ground_truth/{name}.json.

    Computes per-class precision/recall/F1 for each verdict label and
    checks macro F1 against the quality gate threshold.
    """
    ensure_dirs()
    models_config = load_models_config()

    if model not in models_config:
        console.print(f"[red]Model '{model}' not found. Available: {list(models_config.keys())}[/red]")
        raise typer.Exit(1)

    model_config = models_config[model]

    # Load prompt (full file as system prompt)
    prompt_file = SKILL_DIR / "prompts" / f"{prompt}.txt"
    if not prompt_file.exists():
        console.print(f"[red]Prompt not found: {prompt_file}[/red]")
        raise typer.Exit(1)
    system_prompt = prompt_file.read_text().strip()

    # Load ground truth
    try:
        gt_cases = _load_judge_ground_truth(prompt, SKILL_DIR)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    if cases > 0:
        gt_cases = gt_cases[:cases]

    console.print(f"[bold]Evaluating judge prompt '{prompt}' with model '{model}'[/bold]")
    console.print(f"Test cases: {len(gt_cases)}")

    # Tally expected distribution
    expected_dist = Counter(c["expected_output"] for c in gt_cases)
    console.print(f"Expected distribution: {dict(expected_dist)}")
    console.print()

    # Run evaluation
    results = []

    async def run_eval():
        for i, case in enumerate(gt_cases):
            user_msg = case["input"]
            expected = case["expected_output"]
            meta = case.get("metadata", {})

            try:
                content, latency = await call_provider(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    model_config=model_config,
                    max_tokens=512,
                    temperature=0.0,
                )
                parsed = _parse_verdict(content)
                predicted = parsed.get("verdict", "PARSE_ERROR")
                confidence = parsed.get("confidence", 0.0)
                rationale = parsed.get("rationale", "")
            except Exception as e:
                predicted = "ERROR"
                confidence = 0.0
                rationale = str(e)
                latency = 0.0

            correct = predicted == expected
            results.append({
                "case_id": meta.get("_key", f"case_{i}"),
                "expected": expected,
                "predicted": predicted,
                "correct": correct,
                "confidence": confidence,
                "rationale": rationale,
                "latency_ms": latency,
            })

            if verbose:
                status = "[green]OK[/green]" if correct else "[red]MISS[/red]"
                console.print(f"  [{i+1}/{len(gt_cases)}] {status} expected={expected} got={predicted} conf={confidence:.2f}")
                if not correct:
                    console.print(f"    rationale: {rationale[:120]}")

    asyncio.run(run_eval())

    # Compute metrics
    predictions = [r["predicted"] for r in results]
    labels = [r["expected"] for r in results]
    all_classes = sorted(set(predictions + labels))

    metrics = _compute_class_metrics(predictions, labels, all_classes)
    accuracy = sum(1 for r in results if r["correct"]) / len(results) if results else 0.0

    # Display results
    console.print()
    console.print("[bold]Per-Class Metrics[/bold]")

    class_table = Table()
    class_table.add_column("Verdict", style="cyan")
    class_table.add_column("Precision", style="green")
    class_table.add_column("Recall", style="green")
    class_table.add_column("F1", style="green")
    class_table.add_column("TP", style="dim")
    class_table.add_column("FP", style="dim")
    class_table.add_column("FN", style="dim")

    for cls in all_classes:
        m = metrics[cls]
        class_table.add_row(
            cls,
            f"{m['precision']:.3f}",
            f"{m['recall']:.3f}",
            f"{m['f1']:.3f}",
            str(m["tp"]),
            str(m["fp"]),
            str(m["fn"]),
        )

    console.print(class_table)

    console.print()
    summary_table = Table()
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")
    summary_table.add_row("Accuracy", f"{accuracy:.3f}")
    summary_table.add_row("Macro Precision", f"{metrics['macro_precision']:.3f}")
    summary_table.add_row("Macro Recall", f"{metrics['macro_recall']:.3f}")
    summary_table.add_row("Macro F1", f"{metrics['macro_f1']:.3f}")
    summary_table.add_row("Avg Latency", f"{sum(r['latency_ms'] for r in results) / len(results):.0f}ms")
    summary_table.add_row("Avg Confidence", f"{sum(r['confidence'] for r in results) / len(results):.2f}")
    console.print(summary_table)

    # Confusion matrix
    console.print()
    console.print("[bold]Confusion Matrix[/bold]")
    cm_table = Table(title="predicted →")
    cm_table.add_column("expected ↓", style="cyan")
    for cls in all_classes:
        cm_table.add_column(cls, style="dim")
    for exp_cls in all_classes:
        row = []
        for pred_cls in all_classes:
            count = sum(1 for p, l in zip(predictions, labels) if p == pred_cls and l == exp_cls)
            row.append(f"[bold]{count}[/bold]" if count > 0 else "0")
        cm_table.add_row(exp_cls, *row)
    console.print(cm_table)

    # Quality gate
    macro_f1 = metrics["macro_f1"]
    passed = macro_f1 >= f1_threshold

    console.print()
    if passed:
        console.print(f"[green]QUALITY GATE PASSED[/green] (macro F1 {macro_f1:.3f} >= {f1_threshold})")
    else:
        console.print(f"[red]QUALITY GATE FAILED[/red] (macro F1 {macro_f1:.3f} < {f1_threshold})")

    if task_name:
        notify_task_monitor(task_name, passed, {"macro_f1": macro_f1, "accuracy": accuracy})

    # Save results
    results_dir = SKILL_DIR / "results"
    results_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_file = results_dir / f"{prompt}_{model}_{ts}.json"
    results_data = {
        "prompt": prompt,
        "model": model,
        "timestamp": datetime.now().isoformat(),
        "passed": passed,
        "metrics": {
            "accuracy": accuracy,
            "macro_precision": metrics["macro_precision"],
            "macro_recall": metrics["macro_recall"],
            "macro_f1": macro_f1,
        },
        "per_class": {
            cls: {k: v for k, v in metrics[cls].items()}
            for cls in all_classes
        },
        "cases": results,
    }
    results_file.write_text(json.dumps(results_data, indent=2))
    console.print(f"\nResults saved to: {results_file}")

    # Record in model memory
    model_mem = get_model_memory()
    if model_mem.enabled:
        observation = f"Judge eval: macro_F1={macro_f1:.3f}, accuracy={accuracy:.3f}"
        observation += f" - {'PASSED' if passed else 'FAILED'} quality gate"
        record_eval_result(
            memory=model_mem,
            model_alias=model,
            model_id=model_config.get("model", model),
            prompt_type=f"judge_{prompt}",
            f1_score=macro_f1,
            latency_ms=sum(r["latency_ms"] for r in results) / len(results),
            observation=observation,
            details=f"Prompt: {prompt}, Cases: {len(gt_cases)}, Accuracy: {accuracy:.3f}",
        )
        console.print("[dim]Recorded to model memory[/dim]")

    if not passed:
        raise typer.Exit(1)
