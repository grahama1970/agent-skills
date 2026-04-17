#!/usr/bin/env python3
"""Shadow agreement benchmark: analyze shadow.jsonl for teacher-local agreement.

Reads existing shadow entries (already collected by the cascade during normal
operation) and computes agreement metrics. No new inference is needed — the
shadow entries contain both local_grade and teacher_grade from when the cascade
ran in shadow mode.

Usage:
    python shadow_benchmark.py run --task sparta_stress_grading
    python shadow_benchmark.py run --all
    python shadow_benchmark.py summary
"""

from __future__ import annotations

import json
import math
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from loguru import logger

SHADOW_PATH = Path.home() / ".pi" / "assistant" / "shadow.jsonl"
SKILL_DIR = Path(__file__).resolve().parent.parent
RESULTS_DIR = SKILL_DIR / "results"

app = typer.Typer(add_completion=False)


def load_shadow_entries(task: Optional[str] = None) -> list[dict]:
    """Load shadow entries, optionally filtered by task."""
    if not SHADOW_PATH.exists():
        logger.error(f"Shadow file not found: {SHADOW_PATH}")
        return []

    entries = []
    with open(SHADOW_PATH) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if task and entry.get("task") != task:
                continue
            entries.append(entry)

    return entries


def compute_kappa(y_true: list[str], y_pred: list[str]) -> float:
    """Compute Cohen's kappa between two label sequences."""
    if not y_true or not y_pred or len(y_true) != len(y_pred):
        return 0.0

    n = len(y_true)
    labels = sorted(set(y_true) | set(y_pred))
    p_o = sum(1 for a, b in zip(y_true, y_pred) if a == b) / n
    p_e = sum(
        (sum(1 for x in y_true if x == l) / n)
        * (sum(1 for x in y_pred if x == l) / n)
        for l in labels
    )
    if p_e >= 1.0:
        return 1.0 if p_o >= 1.0 else 0.0
    return (p_o - p_e) / (1.0 - p_e)


def compute_entropy(labels: list[str]) -> float:
    """Compute Shannon entropy (base 2). Low entropy = mode collapse."""
    if not labels:
        return 0.0
    n = len(labels)
    counts = Counter(labels)
    return -sum((c / n) * math.log2(c / n) for c in counts.values() if c > 0)


def wilson_lower(p: float, n: int, z: float = 1.96) -> float:
    """Wilson score 95% lower bound."""
    if n == 0:
        return 0.0
    denom = 1 + z * z / n
    center = p + z * z / (2 * n)
    spread = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return (center - spread) / denom


def compute_confusion(y_true: list[str], y_pred: list[str]) -> dict:
    """Compute per-grade confusion matrix stats."""
    labels = sorted(set(y_true) | set(y_pred))
    result = {}
    for label in labels:
        tp = sum(1 for t, p in zip(y_true, y_pred) if t == label and p == label)
        fp = sum(1 for t, p in zip(y_true, y_pred) if t != label and p == label)
        fn = sum(1 for t, p in zip(y_true, y_pred) if t == label and p != label)
        result[label] = {"tp": tp, "fp": fp, "fn": fn}
    return result


def analyze_task(entries: list[dict], task: str) -> Optional[dict]:
    """Analyze shadow agreement for a single task."""
    paired = [e for e in entries if e.get("local_grade") and e.get("teacher_grade")]
    if not paired:
        return None

    teacher = [str(e["teacher_grade"]).strip().upper() for e in paired]
    local = [str(e["local_grade"]).strip().upper() for e in paired]

    agreed = sum(1 for t, l in zip(teacher, local) if t == l)
    rate = agreed / len(paired)

    return {
        "task": task,
        "timestamp": datetime.now().isoformat(),
        "n_total": len(entries),
        "n_paired": len(paired),
        "n_teacher_only": len(entries) - len(paired),
        "agreement_rate": round(rate, 4),
        "wilson_lower_95": round(wilson_lower(rate, len(paired)), 4),
        "kappa": round(compute_kappa(teacher, local), 4),
        "entropy_local": round(compute_entropy(local), 4),
        "entropy_teacher": round(compute_entropy(teacher), 4),
        "per_grade": compute_confusion(teacher, local),
        "grade_distribution": {
            "teacher": dict(Counter(teacher)),
            "local": dict(Counter(local)),
        },
        "tier_distribution": dict(Counter(e.get("local_tier", -1) for e in paired)),
    }


@app.command()
def run(
    task: Optional[str] = typer.Option(None, help="Task name (omit for --all)"),
    all_tasks: bool = typer.Option(False, "--all", help="Analyze all tasks"),
    output: Optional[Path] = typer.Option(None, help="Override output path"),
):
    """Analyze shadow agreement from existing shadow.jsonl data."""
    entries = load_shadow_entries(task if not all_tasks else None)
    if not entries:
        logger.error("No shadow entries found")
        raise typer.Exit(1)

    if all_tasks or task is None:
        tasks = sorted(set(e.get("task", "") for e in entries if e.get("task")))
    else:
        tasks = [task]

    results = {}
    for t in tasks:
        task_entries = [e for e in entries if e.get("task") == t]
        result = analyze_task(task_entries, t)
        if result:
            results[t] = result

    if not results:
        logger.error("No tasks with paired local+teacher grades found")
        raise typer.Exit(1)

    # Save results
    if output:
        out_path = output
    else:
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = RESULTS_DIR / f"shadow_benchmark_{ts}.json"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    logger.info(f"Results saved to {out_path}")

    # Print summary
    print(f"\n{'='*60}")
    print(f"Shadow Agreement Benchmark")
    print(f"{'='*60}")
    for t, r in sorted(results.items(), key=lambda x: -x[1]["n_paired"]):
        print(f"\n  {t}")
        print(f"    Paired:    {r['n_paired']}/{r['n_total']}")
        print(f"    Agreement: {r['agreement_rate']:.1%}")
        print(f"    Kappa:     {r['kappa']:.4f}")
        print(f"    Entropy:   {r['entropy_local']:.4f}")
        print(f"    Wilson 95: {r['wilson_lower_95']:.4f}")
        print(f"    Teacher:   {r['grade_distribution']['teacher']}")
        print(f"    Local:     {r['grade_distribution']['local']}")
        print(f"    Tiers:     {r['tier_distribution']}")

    total_paired = sum(r["n_paired"] for r in results.values())
    total_entries = len(entries)
    print(f"\n  Total: {total_paired} paired / {total_entries} entries")
    print(f"  Output: {out_path}")

    # JSON to stdout for piping
    print(json.dumps(results))


@app.command()
def summary():
    """Print quick summary of shadow.jsonl without detailed analysis."""
    entries = load_shadow_entries()
    if not entries:
        logger.error("No shadow entries found")
        raise typer.Exit(1)

    tasks = Counter(e.get("task", "") for e in entries)
    print(f"\nShadow entries: {len(entries)} across {len(tasks)} tasks\n")
    for task, count in tasks.most_common():
        has_local = sum(
            1 for e in entries if e.get("task") == task and e.get("local_grade")
        )
        agreed = sum(1 for e in entries if e.get("task") == task and e.get("agreed"))
        status = "paired" if has_local > 0 else "teacher-only"
        agr = f", {agreed}/{has_local} agreed" if has_local else ""
        print(f"  {task}: {count} ({has_local} local{agr}) [{status}]")


if __name__ == "__main__":
    app()
