#!/usr/bin/env python3
"""Run 50-question stress test with evidence collection.

Collects entity extraction + recall evidence for each question.
Outputs JSON evidence files for agent review.

Usage:
    PYTHONPATH=/home/graham/workspace/experiments/memory/src uv run python run_stress_test.py
    PYTHONPATH=/home/graham/workspace/experiments/memory/src uv run python run_stress_test.py --count 5
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from collect import (
    collect_entities,
    collect_recall,
    collect_topic,
    decompose_sentence,
    group_by_technique,
)
from runner import EvidenceCaseRunner

app = typer.Typer()
console = Console()

QUESTIONS_FILE = Path(__file__).parent.parent.parent.parent / "workspace/experiments/memory/.claude/skills/evidence-case-lab/state/questions.json"
ALT_QUESTIONS = Path(__file__).parent.parent.parent / "evidence-case-lab/state/questions.json"
OUTPUT_DIR = Path("/tmp/evidence-stress-test")


def _load_questions(path: str = "") -> list[dict]:
    """Load questions from JSON file."""
    if path and Path(path).exists():
        return json.loads(Path(path).read_text())

    for candidate in [QUESTIONS_FILE, ALT_QUESTIONS]:
        if candidate.exists():
            return json.loads(candidate.read_text())

    # Fallback: load from batch_50_f36.py
    from batch_50_f36 import ADVERSARIAL_QUESTIONS, load_real_questions
    real = load_real_questions()
    adv = ADVERSARIAL_QUESTIONS
    questions = []
    for i, q in enumerate(real):
        questions.append({
            "id": f"R{i+1:02d}",
            "question": q["question"],
            "expected": "satisfied",
            "category": q.get("category", "auto"),
        })
    for i, q in enumerate(adv):
        questions.append({
            "id": f"ADV{i+1:02d}",
            "question": q["question"],
            "expected": q.get("expected_verdict", "not_satisfied"),
            "poison_type": q.get("poison_type", ""),
            "rationale": q.get("rationale", ""),
        })
    return questions


@app.command()
def run(
    questions_file: str = typer.Option("", "--questions", "-q"),
    count: int = typer.Option(0, "--count", "-n", help="Limit to first N questions"),
    runner_mode: bool = typer.Option(False, "--runner", help="Use EvidenceCaseRunner (deterministic)"),
    output_dir: str = typer.Option(str(OUTPUT_DIR), "--output", "-o"),
) -> None:
    """Run stress test — collect evidence for all questions."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    questions = _load_questions(questions_file)
    if count > 0:
        questions = questions[:count]

    console.print(f"[bold]Running {len(questions)} questions[/]")

    if runner_mode:
        runner = EvidenceCaseRunner()

    results = []
    t_total = time.monotonic()

    for i, q in enumerate(questions):
        qid = q.get("id", f"Q{i+1:02d}")
        question_text = q["question"]
        t0 = time.monotonic()

        console.print(f"\n[bold cyan]{'='*60}[/]")
        console.print(f"[bold]{qid}[/] ({i+1}/{len(questions)})")
        console.print(f"[dim]{question_text[:100]}...[/]")

        if runner_mode:
            result = runner.run(question_text, category=q.get("category", "auto"), show_progress=True)
            elapsed = time.monotonic() - t0
            results.append({
                "id": qid,
                "question": question_text,
                "expected": q.get("expected", "satisfied"),
                "verdict": result.get("verdict", {}).get("state", "unknown"),
                "grade": result.get("verdict", {}).get("grade", "?"),
                "elapsed_s": round(elapsed, 1),
                "gates": result.get("gate_trace", []),
                "runner_result": result,
            })
        else:
            # Evidence collection mode — agent decides later
            entities = collect_entities(question_text)
            qras = collect_recall(question_text)
            technique_groups = group_by_technique(qras) if qras else {}
            topic = collect_topic(question_text)
            elapsed = time.monotonic() - t0

            evidence = {
                "id": qid,
                "question": question_text,
                "expected": q.get("expected", "satisfied"),
                "elapsed_s": round(elapsed, 1),
                "grounding_ok": entities.get("grounding_ok", True),
                "headline": entities.get("headline", ""),
                "controls": entities.get("controls", []),
                "warnings": entities.get("warnings", []),
                "resolution_map": entities.get("resolution_map", {}),
                "unresolved_terms": entities.get("unresolved_terms", []),
                "qra_count": len(qras),
                "techniques": list(technique_groups.keys()),
                "technique_qra_counts": {k: len(v) for k, v in technique_groups.items()},
                "topic": topic,
                "top_qras": [
                    {"control_id": r.get("control_id", ""), "question": r.get("question", "")[:100], "score": r.get("score", 0)}
                    for r in qras[:5]
                ],
            }
            results.append(evidence)

            # Print summary
            status = "[green]GROUNDED[/]" if entities.get("grounding_ok") else "[red]UNGROUNDED[/]"
            console.print(f"  {status} | {len(qras)} QRAs | {len(technique_groups)} techniques | {elapsed:.1f}s")

            fab_warnings = [w for w in entities.get("warnings", []) if w.get("category") == "fabricated_id"]
            corpus_warnings = [w for w in entities.get("warnings", []) if w.get("category") == "not_in_corpus"]
            if fab_warnings:
                console.print(f"  [red]Fabricated IDs: {', '.join(w['term'] for w in fab_warnings)}[/]")
            if corpus_warnings:
                terms = [w["term"] for w in corpus_warnings if len(w["term"]) > 10]
                if terms:
                    console.print(f"  [yellow]Not in corpus: {', '.join(terms[:3])}[/]")

    total_elapsed = time.monotonic() - t_total

    # Write results
    results_file = out / "evidence_results.json"
    results_file.write_text(json.dumps(results, indent=2, default=str))
    console.print(f"\n[bold green]Results written to {results_file}[/]")
    console.print(f"[bold]Total: {total_elapsed:.1f}s for {len(questions)} questions[/]")

    # Summary table
    table = Table(title="Stress Test Evidence Summary")
    table.add_column("ID", style="cyan")
    table.add_column("Grounded", style="green")
    table.add_column("QRAs")
    table.add_column("Techniques")
    table.add_column("Expected")
    table.add_column("Time")
    table.add_column("Key Warnings")

    for r in results:
        grounded = r.get("grounding_ok", r.get("verdict") == "satisfied")
        g_str = "[green]Yes[/]" if grounded else "[red]No[/]"
        qra_count = r.get("qra_count", len(r.get("gates", [])))
        techs = len(r.get("techniques", []))
        expected = r.get("expected", "?")
        elapsed = r.get("elapsed_s", 0)

        warnings = []
        for w in r.get("warnings", []):
            if w.get("category") == "fabricated_id":
                warnings.append(f"[red]{w['term']}[/]")
            elif w.get("category") == "not_in_corpus" and len(w.get("term", "")) > 10:
                warnings.append(f"[yellow]{w['term'][:20]}[/]")

        table.add_row(
            r.get("id", "?"),
            g_str,
            str(qra_count),
            str(techs),
            expected,
            f"{elapsed:.1f}s",
            ", ".join(warnings[:2]) or "-",
        )

    console.print(table)


if __name__ == "__main__":
    app()
