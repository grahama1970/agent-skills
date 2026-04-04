"""Live validation: run all 12 question_bank questions through the evidence case pipeline.

Saves per-question JSON + aggregate report + eval-compatible output.

Usage:
    python run_question_bank.py [--output-dir /tmp/evidence-case-v2-results]
    python run_question_bank.py --check-regression  # compare against baseline
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from question_bank import QUESTIONS, TestQuestion
from runner import EvidenceCaseRunner
from report import render_markdown_report

app = typer.Typer()
console = Console()

OUTPUT_DIR = Path("/tmp/evidence-case-v2-results")
STATE_DIR = Path(__file__).parent / "state"
BASELINE_FILE = STATE_DIR / "eval_baseline.json"


def _run_one(runner: EvidenceCaseRunner, q: TestQuestion, idx: int) -> dict:
    """Run a single question and return the result with metadata."""
    start = time.monotonic()
    try:
        result = runner.run(
            claim_text=q.question,
            category=q.category_hint,
            show_progress=False,
        )
    except Exception as exc:
        logger.error("Q{:02d} crashed: {}", idx, exc)
        result = {
            "claim": {"text": q.question, "category": q.category_hint, "id": f"error_{idx}"},
            "verdict": {"state": "not_satisfied", "grade": "F", "score": 0.0},
            "answer": f"CRASH: {exc}",
            "gate_trace": [],
            "gates_passed": 0,
            "gates_total": 0,
        }
    elapsed = time.monotonic() - start

    # Annotate with expected values
    result["_meta"] = {
        "question_index": idx,
        "persona": q.persona,
        "difficulty": q.difficulty,
        "expected_answerable": q.expected_answerable,
        "category_hint": q.category_hint,
        "rationale": q.rationale,
        "elapsed_sec": round(elapsed, 2),
    }

    # Determine correctness
    verdict_state = result.get("verdict", {}).get("state", "unknown")
    expected = q.expected_answerable
    if expected == "yes":
        correct = verdict_state == "satisfied"
    elif expected == "no":
        correct = verdict_state in ("not_satisfied",) or result.get("needs_clarification", False)
    elif expected == "inconclusive":
        # Q10/Q11: must be INCONCLUSIVE (not false-positive SATISFIED)
        correct = verdict_state == "inconclusive"
    elif expected == "maybe":
        correct = True  # inconclusive/decomposition/clarification all acceptable
    else:
        correct = None

    result["_meta"]["correct"] = correct
    result["_meta"]["verdict_state"] = verdict_state
    return result


def _build_report(results: list[dict], elapsed_total: float) -> str:
    """Build aggregate validation report."""
    lines = []
    lines.append("# Evidence Case v3 (Technique-Centric) — Live Validation Report")
    lines.append(f"\n**Date**: {time.strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"**Total time**: {elapsed_total:.1f}s")
    lines.append(f"**Questions**: {len(results)}")
    lines.append("")

    # Accuracy
    correct = sum(1 for r in results if r.get("_meta", {}).get("correct"))
    total = len(results)
    accuracy = correct / total if total else 0
    lines.append(f"## Accuracy: {correct}/{total} ({accuracy:.0%})")
    lines.append("")

    # False positives (expected=no but got satisfied)
    fp = [r for r in results if r["_meta"]["expected_answerable"] == "no"
          and r["_meta"]["verdict_state"] == "satisfied"]
    lines.append(f"**False positives**: {len(fp)}")
    for r in fp:
        lines.append(f"  - Q{r['_meta']['question_index']:02d}: {r['claim']['text'][:60]}...")

    # False negatives (expected=yes but got not_satisfied)
    fn = [r for r in results if r["_meta"]["expected_answerable"] == "yes"
          and r["_meta"]["verdict_state"] == "not_satisfied"]
    lines.append(f"**False negatives**: {len(fn)}")
    for r in fn:
        q_idx = r['_meta']['question_index']
        stopped = r.get('stopped_at_gate', '?')
        lines.append(f"  - Q{q_idx:02d}: stopped at {stopped} — {r['claim']['text'][:60]}...")

    lines.append("")

    # Per-question table
    lines.append("## Per-Question Results")
    lines.append("")
    lines.append("| Q# | Difficulty | Expected | Got | Gates | Stopped At | Correct | Time |")
    lines.append("|-----|-----------|----------|-----|-------|------------|---------|------|")
    for r in results:
        m = r["_meta"]
        stopped = r.get("stopped_at_gate", "—")
        icon = "YES" if m["correct"] else "NO"
        lines.append(
            f"| Q{m['question_index']:02d} | {m['difficulty']} | {m['expected_answerable']} "
            f"| {m['verdict_state']} | {r.get('gates_passed', 0)}/{r.get('gates_total', 0)} "
            f"| {stopped or '—'} | {icon} | {m['elapsed_sec']:.1f}s |"
        )
    lines.append("")

    # Gate failure distribution
    gate_failures: dict[str, int] = {}
    for r in results:
        stopped = r.get("stopped_at_gate")
        if stopped:
            gate_failures[stopped] = gate_failures.get(stopped, 0) + 1
    if gate_failures:
        lines.append("## Gate Failure Distribution")
        lines.append("")
        for gate, count in sorted(gate_failures.items(), key=lambda x: -x[1]):
            lines.append(f"- {gate}: {count} questions stopped here")
        lines.append("")

    # Per-difficulty accuracy
    lines.append("## Accuracy by Difficulty")
    lines.append("")
    for diff in ("easy", "medium", "hard"):
        subset = [r for r in results if r["_meta"]["difficulty"] == diff]
        if subset:
            diff_correct = sum(1 for r in subset if r["_meta"]["correct"])
            lines.append(f"- {diff}: {diff_correct}/{len(subset)} ({diff_correct/len(subset):.0%})")
    lines.append("")

    return "\n".join(lines)


@app.command()
def run(
    output_dir: str = typer.Option(str(OUTPUT_DIR), "--output-dir", "-o"),
    json_output: bool = typer.Option(False, "--json"),
    check_regression: bool = typer.Option(False, "--check-regression",
                                          help="Compare against baseline and exit 1 if accuracy drops > threshold"),
    save_baseline: bool = typer.Option(False, "--save-baseline",
                                       help="Save results as the new eval baseline"),
) -> None:
    """Run all 12 question_bank questions through the evidence case pipeline."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    runner = EvidenceCaseRunner()
    results = []
    total_start = time.monotonic()

    for idx, q in enumerate(QUESTIONS, 1):
        console.print(f"\n[bold cyan]Q{idx:02d}/{len(QUESTIONS)}[/] [{q.difficulty}] {q.question[:80]}...")
        result = _run_one(runner, q, idx)
        results.append(result)

        # Save per-question JSON
        q_path = out / f"q{idx:02d}.json"
        q_path.write_text(json.dumps(result, indent=2, default=str))

        # Also save the markdown report for this question
        try:
            report_md = render_markdown_report(result)
            (out / f"q{idx:02d}_report.md").write_text(report_md)
        except Exception:
            pass

        m = result["_meta"]
        icon = "[green]CORRECT[/]" if m["correct"] else "[red]WRONG[/]"
        console.print(f"  {icon} expected={m['expected_answerable']} got={m['verdict_state']} "
                      f"gates={result.get('gates_passed', 0)}/{result.get('gates_total', 0)} "
                      f"({m['elapsed_sec']:.1f}s)")

    total_elapsed = time.monotonic() - total_start

    # Save aggregate report
    report = _build_report(results, total_elapsed)
    report_path = out / "REPORT.md"
    report_path.write_text(report)

    # Save all results as JSON
    all_path = out / "all_results.json"
    all_path.write_text(json.dumps(results, indent=2, default=str))

    # Compute summary
    correct = sum(1 for r in results if r["_meta"]["correct"])
    accuracy = correct / len(results) if results else 0
    false_positives = sum(1 for r in results if r["_meta"]["expected_answerable"] == "no"
                          and r["_meta"]["verdict_state"] == "satisfied")
    false_negatives = sum(1 for r in results if r["_meta"]["expected_answerable"] == "yes"
                          and r["_meta"]["verdict_state"] == "not_satisfied")

    # Build wrong questions map
    wrong_questions = {}
    for r in results:
        m = r["_meta"]
        if not m["correct"]:
            q_key = f"q{m['question_index']:02d}"
            wrong_questions[q_key] = {
                "expected": m["expected_answerable"],
                "got": m["verdict_state"],
                "type": "false_positive" if m["expected_answerable"] in ("no", "inconclusive")
                        and m["verdict_state"] == "satisfied" else "false_negative",
            }

    summary = {
        "version": 1,
        "date": time.strftime("%Y-%m-%d"),
        "accuracy": round(accuracy, 3),
        "correct": correct,
        "total": len(results),
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "wrong_questions": wrong_questions,
        "elapsed_sec": round(total_elapsed, 2),
        "output_dir": str(out),
    }

    # Print summary
    console.print(f"\n[bold]Results: {correct}/{len(results)} correct ({accuracy:.0%})[/]")
    console.print(f"Report: {report_path}")
    console.print(f"Results: {all_path}")

    if json_output:
        print(json.dumps(summary, indent=2))

    # Save as baseline if requested
    if save_baseline:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        baseline = {**summary, "regression_threshold": 0.08}
        BASELINE_FILE.write_text(json.dumps(baseline, indent=2))
        console.print(f"[green]Saved baseline: {BASELINE_FILE}[/]")

    # Check regression against baseline
    if check_regression:
        if not BASELINE_FILE.exists():
            console.print("[yellow]No baseline file found — skipping regression check[/]")
            return

        baseline = json.loads(BASELINE_FILE.read_text())
        baseline_accuracy = baseline.get("accuracy", 0)
        threshold = baseline.get("regression_threshold", 0.08)
        drop = baseline_accuracy - accuracy

        if drop > threshold:
            console.print(f"[bold red]REGRESSION: accuracy dropped {drop:.1%} "
                          f"(baseline={baseline_accuracy:.0%}, current={accuracy:.0%}, threshold={threshold:.0%})[/]")
            sys.exit(1)
        else:
            console.print(f"[green]No regression: baseline={baseline_accuracy:.0%}, "
                          f"current={accuracy:.0%} (threshold={threshold:.0%})[/]")


if __name__ == "__main__":
    app()
