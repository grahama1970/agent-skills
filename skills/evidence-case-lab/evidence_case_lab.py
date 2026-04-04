"""Evidence case lab — convergence loop for /create-evidence-case.

Commands:
  run      — Execute question bank, produce results.json + REPORT.md
  diagnose — Classify results, surface grounding warnings for human review
  correct  — Record human correction ("that SATISFIED is actually wrong")
  converge — Full loop: run → diagnose → track metrics per cycle

Inputs: Question bank from batch_50_f36.py (or custom JSON).
Outputs: results.json, REPORT.md, state/convergence.jsonl, state/corrections.jsonl
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from diagnosis import DiagnosisResult, diagnose_results
from lab_report import write_report as _write_report

app = typer.Typer(
    name="evidence-case-lab",
    help="Self-improving evidence case convergence loop.",
    no_args_is_help=True,
)
console = Console()

SKILL_DIR = Path(__file__).resolve().parent
STATE_DIR = SKILL_DIR / "state"
STATE_DIR.mkdir(exist_ok=True)

CONVERGENCE_LOG = STATE_DIR / "convergence.jsonl"
CORRECTIONS_LOG = STATE_DIR / "corrections.jsonl"
LAST_RESULTS = STATE_DIR / "last_results.json"
EVAL_BASELINE = STATE_DIR / "eval_baseline.json"

# Import paths for create-evidence-case
EVIDENCE_CASE_DIR = SKILL_DIR.parent / "create-evidence-case"
if str(EVIDENCE_CASE_DIR) not in sys.path:
    sys.path.insert(0, str(EVIDENCE_CASE_DIR))


def _load_question_bank() -> list[dict[str, Any]]:
    """Load question bank from batch_50_f36.py or state/questions.json."""
    custom = STATE_DIR / "questions.json"
    if custom.exists():
        return json.loads(custom.read_text())

    # Try importing from create-evidence-case
    try:
        from batch_50_f36 import QUESTIONS
        return QUESTIONS
    except ImportError:
        logger.warning("No question bank found. Create state/questions.json.")
        return []


def _run_single(question_entry: dict[str, Any]) -> dict[str, Any]:
    """Run a single evidence case and return result with expected verdict."""
    from runner import EvidenceCaseRunner
    from evidence_case import _apply_plausibility_gate

    question = question_entry.get("question", "")
    expected = question_entry.get("expected", "unknown")
    qid = question_entry.get("id", "?")

    runner = EvidenceCaseRunner()
    try:
        result = runner.run(question, show_progress=False)
        result = _apply_plausibility_gate(result, question, show_progress=False)
    except Exception as exc:
        import traceback
        tb = traceback.format_exc()
        logger.error("Runner failed for {}: {}\n{}", qid, exc, tb)
        result = {
            "verdict": {"state": "error"},
            "gate_trace": [],
            "error_type": type(exc).__name__,
            "error_msg": str(exc),
            "error_traceback": tb,
        }

    verdict = result.get("verdict", {})
    actual = verdict.get("state", "error") if isinstance(verdict, dict) else "error"

    # Extract grounding evidence from step data
    grounding_evidence = {}
    for step in result.get("gate_trace", []):
        if step.get("gate") == "step_2_recall":
            grounding_evidence = step.get("data", {}).get("grounding_evidence", {})
            break

    out = {
        "id": qid,
        "question": question,
        "expected": expected,
        "actual_verdict": actual,
        "grade": verdict.get("grade", "?") if isinstance(verdict, dict) else "?",
        "grounding_evidence": grounding_evidence,
        "gate_trace": result.get("gate_trace", []),
        "gates_passed": result.get("gates_passed", 0),
        "gates_total": result.get("gates_total", 0),
        "step_timings": result.get("step_timings", []),
        "total_ms": result.get("total_ms", 0),
        "poison_type": question_entry.get("poison_type"),
        "source": question_entry.get("source", "?"),
        "difficulty": question_entry.get("difficulty", "?"),
        "category": question_entry.get("category", "?"),
    }
    if actual == "error":
        out["error_type"] = result.get("error_type", "unknown")
        out["error_msg"] = result.get("error_msg", "")
        out["error_traceback"] = result.get("error_traceback", "")
    return out


# ---------------------------------------------------------------------------
# run — execute question bank
# ---------------------------------------------------------------------------

@app.command()
def run(
    output: Path = typer.Option(STATE_DIR / "last_results.json", "--output", "-o"),
    questions_file: Path | None = typer.Option(None, "--questions", "-q"),
) -> None:
    """Execute question bank, produce results.json + REPORT.md."""
    if questions_file and questions_file.exists():
        questions = json.loads(questions_file.read_text())
    else:
        questions = _load_question_bank()

    if not questions:
        console.print("[red]No questions found.[/]")
        raise typer.Exit(1)

    console.print(f"[bold]Running {len(questions)} questions...[/]")
    results: list[dict[str, Any]] = []

    for i, q_entry in enumerate(questions, 1):
        qid = q_entry.get("id", i)
        console.print(f"  [{i}/{len(questions)}] {qid}: {q_entry.get('question', '?')[:60]}...")
        result = _run_single(q_entry)
        results.append(result)

        # Show inline verdict
        expected = result["expected"]
        actual = result["actual_verdict"]
        ms = result.get("total_ms", 0)
        match = expected == actual or (expected == "not_satisfied" and actual == "inconclusive")
        icon = "[green]OK[/]" if match else "[red]MISMATCH[/]"
        time_str = f" ({ms:.0f}ms)" if ms else ""
        console.print(f"    {icon} expected={expected} actual={actual}{time_str}")

    # Save results
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, indent=2, default=str))
    console.print(f"\n[bold]Results saved to {output}[/]")

    # Generate REPORT.md
    diag = diagnose_results(results)
    report_path = output.parent / "REPORT.md"
    _write_report(diag, results, report_path)
    console.print(f"Report saved to {report_path}")

    # Print summary
    s = diag.summary()
    console.print(f"\n[bold]Summary:[/] {s['correct']}/{s['total']} correct, "
                  f"{s['grounding_warnings']} grounding warnings, "
                  f"{s['false_positives']} FP, {s['false_negatives']} FN, "
                  f"{s['grounding_failures']} grounding failures")

    if s["needs_human_review"] > 0:
        console.print(f"\n[bold yellow]{s['needs_human_review']} item(s) need human review.[/]")
        console.print("[dim]Run 'diagnose' for details, 'correct' to record feedback.[/]")


# ---------------------------------------------------------------------------
# diagnose — classify results for human review
# ---------------------------------------------------------------------------

@app.command()
def diagnose(
    results_file: Path = typer.Option(LAST_RESULTS, "--results", "-r"),
) -> None:
    """Classify results and surface items needing human review."""
    if not results_file.exists():
        console.print("[red]No results file. Run 'run' first.[/]")
        raise typer.Exit(1)

    results = json.loads(results_file.read_text())
    diag = diagnose_results(results)
    s = diag.summary()

    # --- Grounding warnings first — this is what the human reads ---
    if diag.grounding_warnings:
        console.print()
        console.print(f"[bold yellow]═══ SATISFIED WITH GROUNDING WARNINGS "
                      f"({len(diag.grounding_warnings)}) ═══[/]")
        console.print()
        console.print("[dim]These verdicts are SATISFIED but the grounding evidence "
                      "suggests they may be wrong.[/]")
        console.print("[dim]Review each one and run 'correct' if the verdict is wrong.[/]")
        console.print()

        for i, item in enumerate(diag.grounding_warnings, 1):
            qid = item.get("id", "?")
            question = item.get("question", "?")[:90]
            detail = item.get("detail", "")
            names = item.get("unresolved_names", [])
            ratio = item.get("grounding_ratio", 1.0)

            console.print(f"  [bold yellow]{i}. [{qid}][/] {question}")
            console.print(f"     [yellow]{detail}[/]")
            if names:
                console.print(f"     Unresolved: [red]{', '.join(names)}[/]")
            console.print(f"     Grounding ratio: {ratio:.0%}")
            console.print()

    # --- Hard errors ---
    if diag.grounding_failures or diag.false_positives:
        console.print(f"[bold red]═══ HARD ERRORS ({len(diag.grounding_failures) + len(diag.false_positives)}) ═══[/]")
        console.print()
        for item in diag.grounding_failures + diag.false_positives:
            qid = item.get("id", "?")
            question = item.get("question", "?")[:90]
            cause = item.get("root_cause", "?")
            detail = item.get("detail", "")
            names = item.get("unresolved_names", [])

            console.print(f"  [bold red][{qid}][/] {question}")
            console.print(f"     [{cause}] {detail}")
            if names:
                console.print(f"     Unresolved: [red]{', '.join(names)}[/]")
            console.print()

    if diag.false_negatives:
        console.print(f"[bold cyan]═══ FALSE NEGATIVES ({len(diag.false_negatives)}) ═══[/]")
        console.print()
        for item in diag.false_negatives:
            qid = item.get("id", "?")
            question = item.get("question", "?")[:90]
            console.print(f"  [{qid}] {question}")
            console.print(f"     Expected satisfied, got {item.get('actual', '?')}")
            console.print()

    # --- Summary table ---
    console.print()
    table = Table(title="Diagnosis Summary")
    table.add_column("Category", style="cyan")
    table.add_column("Count", style="bold", justify="right")
    table.add_column("Action")

    table.add_row(
        "Grounding Warnings",
        f"[yellow]{len(diag.grounding_warnings)}[/]",
        "Human reviews — may be false positives",
    )
    table.add_row(
        "Hard Errors (FP + Grounding)",
        f"[red]{len(diag.false_positives) + len(diag.grounding_failures)}[/]",
        "Known wrong — expected != actual",
    )
    table.add_row(
        "False Negatives",
        f"[cyan]{len(diag.false_negatives)}[/]",
        "Missed real questions",
    )
    table.add_row(
        "Technique Scatter",
        str(len(diag.technique_scatter)),
        "Too many unrelated techniques",
    )
    table.add_row(
        "Correct",
        f"[green]{len(diag.correct)}[/]",
        "",
    )
    table.add_row(
        "[bold]Needs Human Review[/]",
        f"[bold]{s['needs_human_review']}[/]",
        "[bold]Run 'correct' to record feedback[/]",
    )

    console.print(table)
    print(json.dumps(s, indent=2))


# ---------------------------------------------------------------------------
# correct — record human feedback
# ---------------------------------------------------------------------------

@app.command()
def correct(
    question_id: str = typer.Argument(..., help="Question ID to correct (from diagnose output)"),
    verdict: str = typer.Argument(..., help="Correct verdict: satisfied, not_satisfied, inconclusive"),
    reason: str = typer.Option("", "--reason", "-r", help="Why the original verdict was wrong"),
    results_file: Path = typer.Option(LAST_RESULTS, "--results"),
) -> None:
    """Record a human correction for a question verdict.

    When the human sees a grounding warning and decides the verdict is wrong,
    this records the correction so the system can learn from it.

    Example:
      correct ADV1 not_satisfied --reason "X23-MUSTARD is fabricated"
    """
    if verdict not in ("satisfied", "not_satisfied", "inconclusive"):
        console.print(f"[red]Invalid verdict: {verdict}. Use: satisfied, not_satisfied, inconclusive[/]")
        raise typer.Exit(1)

    # Find the question in results
    original = None
    if results_file.exists():
        results = json.loads(results_file.read_text())
        for r in results:
            if r.get("id") == question_id:
                original = r
                break

    correction = {
        "question_id": question_id,
        "corrected_verdict": verdict,
        "reason": reason,
        "timestamp": time.time(),
        "original_verdict": original.get("actual_verdict", "?") if original else "?",
        "original_grade": original.get("grade", "?") if original else "?",
        "question": original.get("question", "?") if original else "?",
        "grounding_evidence": original.get("grounding_evidence", {}) if original else {},
    }

    # Append to corrections log
    with open(CORRECTIONS_LOG, "a") as f:
        f.write(json.dumps(correction, default=str) + "\n")

    console.print(f"[green]Correction recorded:[/]")
    console.print(f"  Question: {question_id}")
    console.print(f"  Was: {correction['original_verdict']} → Now: {verdict}")
    if reason:
        console.print(f"  Reason: {reason}")
    console.print(f"  Saved to: {CORRECTIONS_LOG}")

    # Show correction count
    corrections = CORRECTIONS_LOG.read_text().strip().split("\n") if CORRECTIONS_LOG.exists() else []
    console.print(f"\n[dim]Total corrections recorded: {len(corrections)}[/]")


@app.command()
def corrections(
    show_all: bool = typer.Option(False, "--all", "-a", help="Show all corrections"),
) -> None:
    """Show recorded human corrections."""
    if not CORRECTIONS_LOG.exists():
        console.print("[dim]No corrections recorded yet.[/]")
        return

    entries = []
    for line in CORRECTIONS_LOG.read_text().strip().split("\n"):
        if line.strip():
            entries.append(json.loads(line))

    if not entries:
        console.print("[dim]No corrections recorded yet.[/]")
        return

    table = Table(title=f"Human Corrections ({len(entries)} total)")
    table.add_column("ID", style="cyan")
    table.add_column("Was", style="red")
    table.add_column("Now", style="green")
    table.add_column("Reason")
    table.add_column("When")

    display = entries if show_all else entries[-10:]
    for e in display:
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(e.get("timestamp", 0)))
        table.add_row(
            e.get("question_id", "?"),
            e.get("original_verdict", "?"),
            e.get("corrected_verdict", "?"),
            (e.get("reason", "") or "")[:50],
            ts,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# converge — iterative loop
# ---------------------------------------------------------------------------

@app.command()
def converge(
    max_cycles: int = typer.Option(5, "--max-cycles", "-n"),
    questions_file: Path | None = typer.Option(None, "--questions", "-q"),
) -> None:
    """Full loop: run → diagnose → track metrics. Agent/human adjusts between cycles."""
    console.print(f"[bold]Convergence loop (max {max_cycles} cycles)[/]")

    diag = DiagnosisResult()
    results: list[dict[str, Any]] = []

    for cycle in range(1, max_cycles + 1):
        console.print(f"\n{'='*60}")
        console.print(f"[bold]Cycle {cycle}/{max_cycles}[/]")
        console.print(f"{'='*60}")

        # Run
        cycle_results_file = STATE_DIR / f"results_cycle_{cycle}.json"
        if questions_file and questions_file.exists():
            questions = json.loads(questions_file.read_text())
        else:
            questions = _load_question_bank()

        if not questions:
            console.print("[red]No questions.[/]")
            break

        results = []
        for i, q_entry in enumerate(questions, 1):
            result = _run_single(q_entry)
            results.append(result)

        cycle_results_file.write_text(json.dumps(results, indent=2, default=str))

        # Diagnose
        diag = diagnose_results(results)
        s = diag.summary()

        # Log to convergence.jsonl
        cycle_entry = {
            "cycle": cycle,
            "timestamp": time.time(),
            **s,
        }
        with open(CONVERGENCE_LOG, "a") as f:
            f.write(json.dumps(cycle_entry, default=str) + "\n")

        console.print(f"  Correct: {s['correct']}/{s['total']}")
        console.print(f"  Grounding warnings: {s['grounding_warnings']}")
        console.print(f"  FP: {s['false_positives']}, FN: {s['false_negatives']}, "
                      f"Grounding failures: {s['grounding_failures']}")
        console.print(f"  [bold]Needs human review: {s['needs_human_review']}[/]")

        # Check convergence criteria
        if s["false_positives"] == 0 and s["grounding_failures"] == 0:
            satisfied_count = sum(1 for r in results
                                 if r["actual_verdict"] == "satisfied"
                                 and r["expected"] == "satisfied")
            real_count = sum(1 for r in results if r["expected"] == "satisfied")
            satisfied_rate = satisfied_count / real_count if real_count > 0 else 0
            console.print(f"  Real satisfied rate: {satisfied_rate:.1%}")

            if satisfied_rate >= 0.85 and s["grounding_warnings"] == 0:
                console.print(f"\n[bold green]CONVERGED at cycle {cycle}![/]")
                console.print("  - 0 adversarial false positives")
                console.print("  - 0 grounding warnings")
                console.print(f"  - {satisfied_rate:.1%} real question satisfaction (>= 85%)")
                break
            elif satisfied_rate >= 0.85:
                console.print(f"\n[yellow]Near-converged: {s['grounding_warnings']} "
                              f"grounding warning(s) need human review[/]")

        if s["errors"] == 0 and s["grounding_warnings"] == 0:
            console.print(f"\n[bold green]CONVERGED at cycle {cycle} (0 errors, 0 warnings)![/]")
            break

        # Check for regression from previous cycle
        if cycle > 1:
            prev_file = STATE_DIR / f"results_cycle_{cycle-1}.json"
            if prev_file.exists():
                prev = json.loads(prev_file.read_text())
                prev_diag = diagnose_results(prev)
                prev_s = prev_diag.summary()
                if s["errors"] > prev_s["errors"]:
                    console.print(f"  [red]REGRESSION: errors {prev_s['errors']} → {s['errors']}[/]")

        console.print(f"\n  [dim]Waiting for agent/human adjustments before next cycle...[/]")
        console.print(f"  [dim]Run 'diagnose' to review, 'correct' to record feedback[/]")

    # Final report
    _write_report(diag, results, STATE_DIR / "REPORT.md")
    console.print(f"\nFinal report: {STATE_DIR / 'REPORT.md'}")


if __name__ == "__main__":
    app()
