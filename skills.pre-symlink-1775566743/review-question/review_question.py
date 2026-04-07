#!/usr/bin/env python3
"""review-question: F36-grounded persona question generation + conversation execution.

Usage:
    python review_question.py generate --persona margaret --count 12
    python review_question.py validate questions.json
    python review_question.py converse questions.json
    python review_question.py run --persona margaret --count 12
"""
from __future__ import annotations
import os

import datetime
import json
import subprocess
import time
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from config import CONVERSATIONS_DIR, PERSONAS, RESULTS_DIR

app = typer.Typer(add_completion=False, help="F36-grounded persona question review")
console = Console()


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------

@app.command()
def generate(
    persona: str = typer.Option(..., help="Persona key: margaret or jennifer"),
    count: int = typer.Option(12, help="Number of questions to generate"),
    output: Optional[Path] = typer.Option(None, help="Output JSON path"),
) -> None:
    """Generate F36-grounded questions for a persona via /scillm."""
    from generators import generate_questions, save_questions

    if persona not in PERSONAS:
        console.print(f"[red]Unknown persona: {persona}. Choose from: {list(PERSONAS.keys())}[/red]")
        raise typer.Exit(1)

    questions = generate_questions(persona, count)
    if not questions:
        console.print("[red]No questions generated — check /scillm availability[/red]")
        raise typer.Exit(1)

    out = output or RESULTS_DIR / f"questions_{persona}.json"
    save_questions(questions, out)
    console.print(f"[green]Generated {len(questions)} questions -> {out}[/green]")

    # Preview
    for i, q in enumerate(questions, 1):
        console.print(f"  {i}. [{q.difficulty}] {q.question[:100]}...")


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------

@app.command()
def validate(
    questions_file: Path = typer.Argument(..., help="Path to questions JSON"),
    output: Optional[Path] = typer.Option(None, help="Output markdown path"),
    skip_llm: bool = typer.Option(False, help="Skip LLM-based gates (naturalness, difficulty)"),
) -> None:
    """Validate questions through 6 quality gates."""
    from generators import load_questions
    from validators import validate_question

    questions = load_questions(questions_file)
    console.print(f"Validating {len(questions)} questions from {questions_file}")

    results = []
    pass_count = 0

    for i, q in enumerate(questions, 1):
        v = validate_question(
            question=q.question,
            difficulty=q.difficulty,
            f36_category=q.f36_category,
            persona_key=q.persona,
            skip_llm=skip_llm,
        )
        results.append(v)
        if v.all_passed:
            pass_count += 1

        # Print summary
        status_color = "green" if v.all_passed else "red"
        console.print(f"  Q{i} [{status_color}]{v.summary}[/{status_color}]")
        console.print(f"      {q.question[:100]}")
        for g in v.gates:
            icon = "[green]Y[/green]" if g.passed else "[red]N[/red]"
            console.print(f"      {icon} {g.gate}: {g.reason[:80]}")

    console.print(f"\n[bold]{pass_count}/{len(questions)} passed all gates[/bold]")

    # Write markdown report
    out = output or RESULTS_DIR / f"review_{questions_file.stem}.md"
    _write_validation_report(results, questions, out)
    console.print(f"Report: {out}")


def _write_validation_report(
    results: list, questions: list, output: Path
) -> None:
    """Write validation results as markdown."""
    output.parent.mkdir(parents=True, exist_ok=True)
    persona_key = questions[0].persona if questions else "unknown"
    persona = PERSONAS.get(persona_key)
    name = persona.name if persona else persona_key

    lines = [
        f"# Question Review: {name} -- F36 Grounded Questions",
        f"Generated: {datetime.date.today()} | Persona: {name} "
        f"| Questions: {len(questions)}",
        "",
    ]

    for i, (q, v) in enumerate(zip(questions, results), 1):
        status = "PASS" if v.all_passed else "FAIL"
        lines.append(f"## Q{i} [{status} {v.passed_count}/{v.total_count}] {q.difficulty.title()}")
        lines.append(f'"{q.question}"')
        gate_parts = []
        for g in v.gates:
            icon = "Y" if g.passed else "N"
            gate_parts.append(f"{icon}{g.gate}")
        lines.append(f"Gates: {' '.join(gate_parts)}")

        # Show fix suggestion for failed gates
        for g in v.gates:
            if not g.passed:
                lines.append(f"  FIX ({g.gate}): {g.reason}")
        lines.append("")

    output.write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# converse
# ---------------------------------------------------------------------------

@app.command()
def converse(
    questions_file: Path = typer.Argument(..., help="Path to validated questions JSON"),
    output: Optional[Path] = typer.Option(None, help="Output directory for conversations"),
) -> None:
    """Execute conversation threads: persona asks Brandon, capture turns + metrics."""
    from conversation import execute_conversation, save_conversation
    from generators import load_questions

    questions = load_questions(questions_file)
    out_dir = output or CONVERSATIONS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    console.print(f"Executing {len(questions)} conversations -> {out_dir}")

    threads = []
    for i, q in enumerate(questions, 1):
        console.print(f"\n--- Conversation {i}/{len(questions)} ---")
        try:
            thread = execute_conversation(q)
            save_conversation(thread, out_dir)
            threads.append(thread)
            console.print(
                f"  [green]{thread.grade}[/green] ({thread.composite_score:.2f}) "
                f"| {len(thread.turns)} turns | {thread.final_verdict}"
            )
        except (RuntimeError, OSError, ValueError, KeyError) as e:
            console.print(f"  [red]ERROR: {e}[/red]")
            logger.exception(f"Conversation {i} failed")

    # Summary table
    if threads:
        _print_summary_table(threads)


def _print_summary_table(threads: list) -> None:
    """Print summary table of conversation results."""
    table = Table(title="Conversation Results")
    table.add_column("Session", style="dim")
    table.add_column("Questioner")
    table.add_column("Difficulty")
    table.add_column("Grade", style="bold")
    table.add_column("Score")
    table.add_column("Turns")
    table.add_column("Verdict")

    for t in threads:
        grade_style = {"A": "green", "B+": "green", "B": "yellow", "C": "yellow"}.get(
            t.grade, "red"
        )
        table.add_row(
            t.session_id[:30],
            t.questioner,
            t.question.difficulty,
            f"[{grade_style}]{t.grade}[/{grade_style}]",
            f"{t.composite_score:.2f}",
            str(len(t.turns)),
            t.final_verdict,
        )

    console.print(table)


# ---------------------------------------------------------------------------
# run (full pipeline)
# ---------------------------------------------------------------------------

@app.command()
def run(
    persona: str = typer.Option(..., help="Persona key: margaret or jennifer"),
    count: int = typer.Option(12, help="Number of questions to generate"),
    output: Optional[Path] = typer.Option(None, help="Output directory"),
    skip_llm_validation: bool = typer.Option(
        False, "--skip-llm-validation", help="Skip LLM gates during validation"
    ),
) -> None:
    """Full pipeline: generate -> validate -> converse -> save."""
    from conversation import execute_conversation, save_conversation
    from generators import generate_questions, save_questions
    from validators import validate_question

    if persona not in PERSONAS:
        console.print(f"[red]Unknown persona: {persona}[/red]")
        raise typer.Exit(1)

    out_dir = output or CONVERSATIONS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Generate
    console.print(f"\n[bold]Step 1: Generating {count} questions for {PERSONAS[persona].name}[/bold]")
    questions = generate_questions(persona, count)
    if not questions:
        console.print("[red]No questions generated[/red]")
        raise typer.Exit(1)

    q_path = RESULTS_DIR / f"questions_{persona}.json"
    save_questions(questions, q_path)
    console.print(f"  Generated {len(questions)} questions -> {q_path}")

    # Step 2: Validate
    console.print(f"\n[bold]Step 2: Validating questions[/bold]")
    valid_questions = []
    for i, q in enumerate(questions, 1):
        v = validate_question(
            question=q.question,
            difficulty=q.difficulty,
            f36_category=q.f36_category,
            persona_key=q.persona,
            skip_llm=skip_llm_validation,
        )
        status = "[green]PASS[/green]" if v.all_passed else "[red]FAIL[/red]"
        console.print(f"  Q{i} {status} {v.summary}: {q.question[:80]}...")
        if v.all_passed:
            valid_questions.append(q)

    console.print(f"  {len(valid_questions)}/{len(questions)} passed validation")

    if not valid_questions:
        console.print("[red]No questions passed validation — check generation prompts[/red]")
        raise typer.Exit(1)

    # Step 3: Converse
    console.print(f"\n[bold]Step 3: Executing {len(valid_questions)} conversations[/bold]")
    threads = []
    for i, q in enumerate(valid_questions, 1):
        console.print(f"\n  --- Conversation {i}/{len(valid_questions)} ---")
        try:
            thread = execute_conversation(q)
            save_conversation(thread, out_dir)
            threads.append(thread)
            console.print(
                f"  [green]{thread.grade}[/green] ({thread.composite_score:.2f}) "
                f"| {len(thread.turns)} turns | {thread.final_verdict}"
            )
        except (RuntimeError, OSError, ValueError, KeyError) as e:
            console.print(f"  [red]ERROR: {e}[/red]")

    if threads:
        _print_summary_table(threads)
        console.print(f"\n[bold green]Done! {len(threads)} conversations saved to {out_dir}[/bold green]")


# ---------------------------------------------------------------------------
# evidence-case (deterministic pre-validation)
# ---------------------------------------------------------------------------

@app.command("evidence-case")
def evidence_case(
    question: str = typer.Option(..., "--question", "-q", help="Question to build evidence case for"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output markdown path"),
    no_recursive: bool = typer.Option(False, "--no-recursive", help="Disable recursive decomposition"),
    max_depth: int = typer.Option(2, "--max-depth", help="Max recursion depth for decomposition"),
) -> None:
    """Build a deterministic evidence case for a question.

    Runs 5 gates (all DB access via /memory):
      1. Extract entities (/memory intent)
      2. Verify existence (/memory count)
      3. Check relationships (/memory trace)
      4. Decompose (connected components)
      5. Formalize + count QRAs

    Classification: ANSWERABLE | INVALID_IDS | NO_COVERAGE | NEEDS_CLARIFICATION | DECOMPOSE
    """
    from evidence_case import build_evidence_case

    console.print(f"[bold]Building evidence case...[/bold]")
    console.print(f"  Question: {question[:100]}...")

    try:
        case = build_evidence_case(
            question,
            recursive=not no_recursive,
            max_depth=max_depth,
        )
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        console.print(f"[red]Evidence case failed: {exc}[/red]")
        raise typer.Exit(1)

    # Print gate results
    for g in case.gates:
        icon = "[green]Y[/green]" if g.passed else "[red]N[/red]"
        time_str = f"{g.time_ms:.0f}ms" if g.time_ms >= 1 else "<1ms"
        console.print(f"  {icon} Gate {g.gate}: {g.name} ({time_str})")

    # Print entities
    if case.entities:
        console.print(f"\n  [bold]Entities:[/bold]")
        for e in case.entities:
            status = "[green]exists[/green]" if e.exists else "[red]missing[/red]"
            qra_info = f" ({e.qra_count} QRAs, grounding={e.avg_grounding:.2f})" if e.exists else ""
            console.print(f"    {e.entity_id}: {status}{qra_info}")
            if not e.exists and e.suggestions:
                console.print(f"      Did you mean: {', '.join(e.suggestions[:5])}?")

    # Print relationships
    if case.relationships:
        console.print(f"\n  [bold]Relationships:[/bold]")
        for r in case.relationships:
            if r.found:
                via = f" via {r.via[0]}" if r.via else ""
                console.print(f"    [green]{r.source} -> {r.target}: {r.hops}hop{via}[/green]")
            else:
                console.print(f"    [yellow]{r.source} -> {r.target}: no path[/yellow]")

    # Print sub-cases
    if case.sub_cases:
        console.print(f"\n  [bold]Sub-Cases:[/bold]")
        for i, sc in enumerate(case.sub_cases, 1):
            color = "green" if sc.classification == "ANSWERABLE" else "yellow"
            console.print(f"    {i}. [{color}]{sc.classification}[/{color}] {sc.question[:80]}")

    # Classification
    class_color = {
        "ANSWERABLE": "green",
        "INVALID_IDS": "red",
        "NO_COVERAGE": "yellow",
        "NEEDS_CLARIFICATION": "yellow",
        "DECOMPOSE": "cyan",
        "PARTIALLY_ANSWERABLE": "yellow",
    }.get(case.classification, "white")

    console.print(
        f"\n  [bold {class_color}]Classification: {case.classification}[/bold {class_color}]"
        f" ({case.total_time_ms:.0f}ms)"
    )

    # Write markdown
    md = case.to_markdown()
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md)
        console.print(f"\n  Report: {output}")
    else:
        out_path = RESULTS_DIR / f"evidence_case_{int(time.time())}.md"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(md)
        console.print(f"\n  Report: {out_path}")


# ---------------------------------------------------------------------------
# review (delegates to /review-conversation)
# ---------------------------------------------------------------------------

@app.command()
def review(
    conversations_dir: Optional[Path] = typer.Argument(None, help="Conversations directory"),
) -> None:
    """Show conversation results (delegates to /review-conversation for JSONL)."""
    cdir = conversations_dir or CONVERSATIONS_DIR
    if not cdir.exists():
        console.print(f"[red]No conversations found at {cdir}[/red]")
        raise typer.Exit(1)

    md_files = sorted(cdir.glob("*.md"))
    if not md_files:
        console.print("[yellow]No markdown conversation files found[/yellow]")
        raise typer.Exit(0)

    console.print(f"[bold]{len(md_files)} conversation(s) in {cdir}[/bold]\n")
    for f in md_files:
        console.print(f"  {f.name}")

    # Show the most recent one
    latest = md_files[-1]
    console.print(f"\n[bold]Latest: {latest.name}[/bold]\n")
    console.print(latest.read_text())


# ---------------------------------------------------------------------------
# sanity
# ---------------------------------------------------------------------------

@app.command()
def sanity() -> None:
    """Basic validation that the skill is correctly configured."""
    checks = []

    # Config loads
    try:
        from config import F36_CATEGORIES, PERSONAS
        checks.append(("Config", True, f"{len(PERSONAS)} personas, {len(F36_CATEGORIES)} categories"))
    except (ImportError, AttributeError, ValueError) as e:
        checks.append(("Config", False, str(e)))

    # Validators load
    try:
        from validators import validate_question
        checks.append(("Validators", True, "6 gates available"))
    except (ImportError, AttributeError) as e:
        checks.append(("Validators", False, str(e)))

    # Generators load
    try:
        from generators import generate_questions
        checks.append(("Generators", True, "OK"))
    except (ImportError, AttributeError) as e:
        checks.append(("Generators", False, str(e)))

    # Conversation module loads
    try:
        from conversation import execute_conversation
        checks.append(("Conversation", True, "OK"))
    except (ImportError, AttributeError) as e:
        checks.append(("Conversation", False, str(e)))

    # F36 datalake exists
    from config import F36_DATALAKE_ROOT
    if F36_DATALAKE_ROOT.exists():
        cats = [d.name for d in F36_DATALAKE_ROOT.iterdir() if d.is_dir() and d.name[0].isdigit()]
        checks.append(("F36 Datalake", True, f"{len(cats)} categories at {F36_DATALAKE_ROOT}"))
    else:
        checks.append(("F36 Datalake", False, f"Not found at {F36_DATALAKE_ROOT}"))

    # Memory service reachable (via Unix socket)
    try:
        import httpx
        transport = httpx.HTTPTransport(uds="/run/user/1000/embry/memory.sock")
        with httpx.Client(transport=transport, base_url="http://localhost", timeout=15.0) as client:
            resp = client.post("/query", json={"aql": "RETURN LENGTH(sparta_qra)", "bind_vars": {}})
            resp.raise_for_status()
            count_data = resp.json()
            qra_count = count_data[0] if isinstance(count_data, list) else count_data.get("count", 0)
            checks.append(("Memory", True, f"sparta_qra count={qra_count}"))
    except Exception as e:
        checks.append(("Memory", False, str(e)))

    # Print results
    table = Table(title="review-question Sanity Check")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Details")

    all_pass = True
    for name, ok, detail in checks:
        style = "green" if ok else "red"
        table.add_row(name, f"[{style}]{'PASS' if ok else 'FAIL'}[/{style}]", detail)
        if not ok:
            all_pass = False

    console.print(table)

    if all_pass:
        console.print("\n[bold green]All checks passed[/bold green]")
    else:
        console.print("\n[bold yellow]Some checks failed — skill may still work with degraded features[/bold yellow]")


if __name__ == "__main__":
    app()
