"""CLI for SPARTA stress testing.

Usage:
    # Run conversation simulator (multi-turn sessions, graded + archived)
    python -m sparta_stress_test.cli simulate --count 50

    # Run flat question bank stress test (legacy)
    python -m sparta_stress_test.cli run --count 100

    # Generate question bank from SPARTA data
    python -m sparta_stress_test.cli generate-bank --output fixtures/sparta_stress_test.json

    # Show results report
    python -m sparta_stress_test.cli report --last-run

    # Show blame analysis (which skills need fixing)
    python -m sparta_stress_test.cli blame --last-run
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional

try:
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path.home() / ".pi" / "skills"))
    from common.task_monitor import TaskClient
except ImportError:
    TaskClient = None

import typer
from loguru import logger
from rich.console import Console
from rich.table import Table

from . import conversation_sim, grader, question_bank, question_miner, question_quality, runner  # noqa: F401
from sparta_stress_test.cli_display import (
    display_blame_report as _display_blame_report,
    display_evidence_case_summary as _display_evidence_case_summary,
    display_session_summary as _display_session_summary,
    display_summary as _display_summary,
)

app = typer.Typer(
    name="sparta-stress-test",
    help="Stress test the full SPARTA query pipeline.",
)
console = Console()

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


@app.command()
def run(
    count: int = typer.Option(50, "--count", "-n", help="Number of questions to run"),
    difficulty: Optional[str] = typer.Option(None, "--difficulty", "-d",
        help="Filter by difficulty: simple/medium/complex/ambiguous/flawed"),
    persona: Optional[str] = typer.Option(None, "--persona", "-p",
        help="Filter by persona name"),
    seed: Optional[int] = typer.Option(None, "--seed", help="Random seed for reproducibility"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSONL path"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model override (sets CHUTES_TEXT_MODEL)"),
):
    """Run stress test questions through the full SPARTA pipeline."""
    if model:
        import os
        os.environ["CHUTES_TEXT_MODEL"] = model
        os.environ["CHUTES_MODEL_ID"] = model

    # Load question bank
    try:
        bank = question_bank.load_bank()
    except FileNotFoundError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(1)

    # Sample questions
    questions = question_bank.sample(bank, count=count, difficulty=difficulty,
                                      persona=persona, seed=seed)
    typer.echo(f"Running {len(questions)} questions (from bank of {len(bank)})")
    if difficulty:
        typer.echo(f"  Difficulty filter: {difficulty}")
    if persona:
        typer.echo(f"  Persona filter: {persona}")

    # Run
    monitor = TaskClient("sparta-stress-run", total=len(questions)) if TaskClient else None
    start = time.monotonic()
    results = runner.run_batch(questions, verbose=verbose)
    elapsed = time.monotonic() - start
    if monitor:
        monitor.finish()

    # Aggregate
    summary = grader.aggregate_grades([r["grade"] for r in results])

    # Display results
    _display_summary(summary, elapsed)

    # Save results
    if output is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output = RESULTS_DIR / f"stress_test_{timestamp}.jsonl"
    runner.save_results(results, output)

    # Also save summary
    summary_path = output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, default=str))


@app.command()
def simulate(
    count: int = typer.Option(50, "--count", "-n", help="Number of conversation sessions"),
    difficulty: Optional[str] = typer.Option(None, "--difficulty", "-d",
        help="Filter seed questions by difficulty"),
    persona: Optional[str] = typer.Option(None, "--persona", "-p",
        help="Filter by persona name"),
    brandon: bool = typer.Option(True, "--brandon/--no-brandon",
        help="Use Brandon /scillm grading (Tier 2) vs heuristic only"),
    archive: bool = typer.Option(True, "--archive/--no-archive",
        help="Submit sessions to /episodic-archiver"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSONL path"),
    mine_fresh: bool = typer.Option(True, "--mine/--bank",
        help="Mine fresh questions via /scillm (default) or use existing bank"),
    seeds_file: Optional[Path] = typer.Option(None, "--seeds-file",
        help="JSON file with pre-built seed questions (overrides --mine/--bank)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="LLM model override (sets CHUTES_TEXT_MODEL)"),
):
    """Run multi-turn conversation stress tests (recommended).

    Each session simulates a 4-turn conversation:
      Turn 1: Margaret/Jennifer asks a question
      Turn 2: SPARTA answers via QRA lookup
      Turn 3: Persona evaluates and follows up or pushes back
      Turn 4: SPARTA responds to follow-up

    Brandon grades the full session. /episodic-archiver captures the
    exchange for cross-session learning and blame attribution.

    Failing sessions (C/F) get blame analysis identifying which skill
    in the chain needs fixing (SPARTA QRAs, persona prompts, intent mapper,
    memory taxonomy, learn-datalake, extractor, NLG synthesis).
    """
    if model:
        import os
        os.environ["CHUTES_TEXT_MODEL"] = model
        os.environ["CHUTES_MODEL_ID"] = model

    # Get seed questions — seeds file takes priority over mine/bank
    if seeds_file and seeds_file.exists():
        import json as _json
        questions = _json.loads(seeds_file.read_text())
        typer.echo(f"Loaded {len(questions)} seed questions from {seeds_file}")
    elif mine_fresh:
        typer.echo(f"Mining {count} seed questions via /scillm personas...")
        questions = question_miner.mine_all(total=count)
    else:
        try:
            bank = question_bank.load_bank()
            questions = question_bank.sample(bank, count=count, difficulty=difficulty,
                                              persona=persona)
        except FileNotFoundError as e:
            typer.echo(f"Error: {e}. Run generate-bank first or use --mine.", err=True)
            raise typer.Exit(1)

    # Filter if requested
    if difficulty and mine_fresh:
        questions = [q for q in questions if q.get("difficulty") == difficulty]
    if persona and mine_fresh:
        questions = [q for q in questions if persona.lower() in q.get("persona", "").lower()]

    if not questions:
        typer.echo("No questions match the filters.", err=True)
        raise typer.Exit(1)

    questions = questions[:count]
    typer.echo(f"Running {len(questions)} conversation sessions...")
    typer.echo(f"  Brandon grading: {'Tier 2 /scillm' if brandon else 'Tier 0 heuristic'}")
    typer.echo(f"  Archival: {'enabled' if archive else 'disabled'}")

    # Run sessions
    monitor = TaskClient("sparta-stress-simulate", total=len(questions)) if TaskClient else None
    start = time.monotonic()
    sessions = conversation_sim.run_batch_sessions(
        questions,
        use_brandon_grading=brandon,
        archive=archive,
        verbose=verbose,
    )
    elapsed = time.monotonic() - start
    if monitor:
        monitor.finish()

    # Aggregate results
    summary = conversation_sim.aggregate_sessions(sessions)
    _display_session_summary(summary, elapsed)

    # Blame analysis for failing sessions
    failing = [s for s in sessions if s.grade and s.grade.grade in ("C", "F")]
    if failing:
        blame_report = conversation_sim.aggregate_blame(sessions)
        _display_blame_report(blame_report)

    # Save
    if output is None:
        output = conversation_sim.save_sessions(sessions)
    else:
        conversation_sim.save_sessions(sessions, output)

    # Save summary
    summary_path = (output if isinstance(output, Path) else Path(str(output))).with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2, default=str))

    typer.echo(f"\nSaved to {output}")

    # ---------------------------------------------------------------
    # NON-NEGOTIABLE: Shadow-LEGO Post-Run Pipeline
    #
    # After every batch, the Tier 2 LLM MUST rate a statistically
    # significant stratified sample and feed results to /assistant
    # shadow.jsonl so ModelFactory.auto_improve() closes the loop.
    # Without this, the run produces dead data that feeds nothing.
    # ---------------------------------------------------------------
    typer.echo("\n--- Shadow-LEGO Post-Run Pipeline ---")
    try:
        lego_summary = conversation_sim.shadow_lego_post_run(sessions)
        typer.echo(f"  Sample size: {lego_summary.get('sample_size', 0)}")
        typer.echo(f"  Rated: {lego_summary.get('rated_count', 0)}")
        typer.echo(f"  Agreement: {lego_summary.get('agreement_ci_95', 'N/A')}")
        typer.echo(f"  Shadow entries: {lego_summary.get('shadow_entries_written', 0)}")
        typer.echo(f"  Recommendation: {lego_summary.get('recommendation', 'N/A')}")
    except Exception as e:
        typer.echo(f"  Shadow-LEGO pipeline FAILED: {e}", err=True)
        typer.echo("  This is a NON-NEGOTIABLE gate — investigate and rerun.", err=True)


@app.command(name="evidence-case")
def evidence_case(
    count: int = typer.Option(50, "--count", "-n", help="Number of questions to run"),
    difficulty: Optional[str] = typer.Option(None, "--difficulty", "-d",
        help="Filter by difficulty: simple/medium/complex/ambiguous/flawed"),
    persona: Optional[str] = typer.Option(None, "--persona", "-p",
        help="Filter by persona name"),
    seed: Optional[int] = typer.Option(None, "--seed", help="Random seed for reproducibility"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="Output JSONL path"),
    bank_file: Optional[Path] = typer.Option(None, "--bank", "-b",
        help="Path to grounded question bank JSON (default: evidence_case_grounded.json)"),
    grounded: bool = typer.Option(False, "--grounded", "-g",
        help="Use the agent-crafted grounded question bank instead of the mined bank"),
):
    """Stress test the evidence case pipeline against the question bank.

    Runs each question through build_evidence_case() (6-gate deterministic
    pre-validation) and checks whether the classification matches expectations.

    Two modes:
      --grounded / -g : Use agent-crafted grounded bank (evidence_case_grounded.json)
                        Each question has verified expected_classification from ArangoDB.
                        85% grounded (answers exist), 15% ungrounded (test NO_MATCH/CLARIFY).

      (default)       : Use the mined question bank (sparta_stress_test.json)
                        Maps expected_action -> acceptable classifications:
                          QUERY    -> ANSWERABLE or PARTIALLY_ANSWERABLE or DECOMPOSE
                          CLARIFY  -> NEEDS_CLARIFICATION
                          NO_MATCH -> INVALID_IDS or NO_COVERAGE

    This is the singular way to verify that evidence case generation works
    across all question types — F36 datalake, SPARTA controls, ambiguous,
    and flawed questions.
    """
    import random

    # Import evidence_case from review-question skill
    review_q_dir = Path(__file__).resolve().parent.parent.parent / "review-question"
    sys.path.insert(0, str(review_q_dir))
    try:
        from evidence_case import build_evidence_case
    except ImportError as e:
        typer.echo(f"Error: Cannot import evidence_case from {review_q_dir}: {e}", err=True)
        raise typer.Exit(1)

    # Determine which bank to use
    use_grounded = grounded or bank_file is not None

    if use_grounded:
        # Load grounded bank
        if bank_file is None:
            bank_file = Path(__file__).resolve().parent.parent / "fixtures" / "evidence_case_grounded.json"
        if not bank_file.exists():
            typer.echo(f"Error: Grounded bank not found: {bank_file}", err=True)
            raise typer.Exit(1)
        with open(bank_file) as f:
            grounded_data = json.load(f)
        all_questions = grounded_data["questions"]

        # Filter by difficulty
        if difficulty:
            all_questions = [q for q in all_questions if q.get("difficulty") == difficulty]

        # Sample
        if seed is not None:
            random.seed(seed)
        questions = all_questions[:count] if len(all_questions) <= count else random.sample(all_questions, count)
        typer.echo(f"Running {len(questions)} evidence cases (grounded bank: {len(grounded_data['questions'])} total)")
    else:
        # Load mined question bank
        try:
            bank = question_bank.load_bank()
        except FileNotFoundError as e:
            typer.echo(f"Error: {e}", err=True)
            raise typer.Exit(1)

        questions = question_bank.sample(bank, count=count, difficulty=difficulty,
                                          persona=persona, seed=seed)
        typer.echo(f"Running {len(questions)} evidence cases (mined bank: {len(bank)} total)")

    # Classification mapping: expected_action -> acceptable evidence case classifications
    ACTION_TO_CLASSIFICATIONS = {
        "QUERY": {"ANSWERABLE", "PARTIALLY_ANSWERABLE", "DECOMPOSE"},
        "CLARIFY": {"NEEDS_CLARIFICATION"},
        "NO_MATCH": {"INVALID_IDS", "NO_COVERAGE", "NEEDS_CLARIFICATION"},
    }

    # Run evidence cases
    monitor = TaskClient("sparta-evidence-case", total=len(questions)) if TaskClient else None
    start = time.monotonic()
    results = []
    passed = 0
    failed = 0
    errors = 0
    classification_counts: dict[str, int] = {}
    difficulty_stats: dict[str, dict] = {}

    for i, q in enumerate(questions):
        q_text = q.get("question", "")
        diff = q.get("difficulty", "unknown")
        q_id = q.get("id", f"q{i}")

        # Determine expected action based on bank type
        if use_grounded:
            expected_action = q.get("expected_action", "QUERY")
            # Grounded bank may specify exact expected_classification
            expected_exact = q.get("expected_classification")
        else:
            expected_action = q.get("expected_action", "QUERY")
            expected_exact = None

        try:
            case = build_evidence_case(q_text, recursive=False)
            classification = case.classification
        except Exception as exc:
            classification = "ERROR"
            case = None
            errors += 1
            if verbose:
                typer.echo(f"  ERROR [{q_id}]: {exc}")

        # Check match — grounded bank can use exact classification or action mapping
        if expected_exact:
            # Grounded bank: exact match OR same action-family is acceptable
            acceptable = ACTION_TO_CLASSIFICATIONS.get(expected_action, set())
            match = classification == expected_exact or classification in acceptable
        else:
            # Mined bank: action mapping only
            acceptable = ACTION_TO_CLASSIFICATIONS.get(expected_action, set())
            match = classification in acceptable

        if match:
            passed += 1
        else:
            failed += 1

        # Track stats
        classification_counts[classification] = classification_counts.get(classification, 0) + 1

        if diff not in difficulty_stats:
            difficulty_stats[diff] = {"total": 0, "passed": 0, "failed": 0, "classifications": {}}
        difficulty_stats[diff]["total"] += 1
        if match:
            difficulty_stats[diff]["passed"] += 1
        else:
            difficulty_stats[diff]["failed"] += 1
        difficulty_stats[diff]["classifications"][classification] = (
            difficulty_stats[diff]["classifications"].get(classification, 0) + 1
        )

        # Verbose output
        if verbose or not match:
            status = "PASS" if match else "FAIL"
            gate_str = ""
            dl_str = ""
            qra_str = ""
            if case:
                gate_str = " ".join(f"G{g.gate}:{'Y' if g.passed else 'N'}" for g in case.gates)
                qra_str = f"QRAs={case.total_qras}"
                if case.datalake_connections:
                    cats = [c.category for c in case.datalake_connections[:3]]
                    shared = set()
                    for c in case.datalake_connections:
                        shared.update(c.shared_bridges.keys())
                    dl_str = f" DL:{','.join(cats)}"
                    if shared:
                        dl_str += f" bridges:{','.join(sorted(shared)[:3])}"

            typer.echo(
                f"  {status} [{q_id}] {diff:>9} | "
                f"{expected_action:>8}→{classification:>22} | "
                f"{gate_str} {qra_str}{dl_str}"
            )
            if not match and not verbose:
                typer.echo(f"    Q: {q_text[:100]}")

        # Result record
        result = {
            "id": q_id,
            "question": q_text[:200],
            "difficulty": diff,
            "expected_action": expected_action,
            "classification": classification,
            "match": match,
        }
        if case:
            result["total_qras"] = case.total_qras
            result["avg_grounding"] = case.avg_grounding
            result["gates"] = [
                {"gate": g.gate, "passed": g.passed, "time_ms": round(g.time_ms)}
                for g in case.gates
            ]
            result["datalake_connections"] = [
                {
                    "category": c.category,
                    "avg_graph_score": round(c.avg_graph_score, 3),
                    "shared_bridges": list(c.shared_bridges.keys()),
                    "connected_controls": len(c.connected_controls),
                }
                for c in case.datalake_connections
            ]
            result["elapsed_ms"] = round(case.total_time_ms)

        results.append(result)

        if monitor:
            monitor.update(completed=i + 1, current_item=q_id)

    elapsed = time.monotonic() - start
    if monitor:
        monitor.finish()

    # Display summary
    _display_evidence_case_summary(
        passed, failed, errors, len(questions),
        classification_counts, difficulty_stats, elapsed,
    )

    # Save results
    if output is None:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        output = RESULTS_DIR / f"evidence_case_{timestamp}.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    # Summary JSON
    summary_path = output.with_suffix(".summary.json")
    summary_path.write_text(json.dumps({
        "timestamp": time.time(),
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "total": len(questions),
        "pass_rate": passed / len(questions) if questions else 0,
        "classifications": classification_counts,
        "by_difficulty": difficulty_stats,
        "elapsed_s": round(elapsed, 1),
    }, indent=2))

    typer.echo(f"\nSaved to {output}")
    raise typer.Exit(0 if failed == 0 else 1)




@app.command()
def blame(
    last_run: bool = typer.Option(False, "--last-run", help="Analyze most recent session run"),
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="Specific sessions JSONL"),
):
    """Show blame analysis — which skills need fixing based on failing sessions.

    Reads session results and shows the distribution of blame across pipeline
    components: SPARTA QRAs, persona prompts, intent mapper, memory taxonomy,
    learn-datalake, extractor, NLG synthesis, question quality.
    """
    sessions_dir = conversation_sim.SESSIONS_DIR

    if path:
        sessions_path = path
    elif last_run:
        if not sessions_dir.exists():
            typer.echo("No sessions directory. Run simulate first.")
            raise typer.Exit(1)
        files = sorted(sessions_dir.glob("sessions_*.jsonl"), reverse=True)
        if not files:
            typer.echo("No session results found.")
            raise typer.Exit(1)
        sessions_path = files[0]
    else:
        typer.echo("Specify --last-run or --path <file>")
        raise typer.Exit(1)

    # Load sessions
    sessions_data = []
    with open(sessions_path) as f:
        for line in f:
            if line.strip():
                sessions_data.append(json.loads(line))

    # Count blame
    blame_counts = {}
    fix_suggestions = []
    for sd in sessions_data:
        b = sd.get("blame")
        if not b:
            continue
        primary = b.get("primary_blame", "unknown")
        blame_counts[primary] = blame_counts.get(primary, 0) + 1
        for fix in b.get("fix_suggestions", []):
            fix_suggestions.append({"blame": primary, "fix": fix})

    if not blame_counts:
        typer.echo("No blame data found. Sessions may not have been analyzed.")
        return

    # Display
    table = Table(title="Blame Attribution (Failing Sessions)")
    table.add_column("Skill/Component", style="bold")
    table.add_column("Failures", justify="right")
    table.add_column("% of Failures", justify="right")

    total = sum(blame_counts.values())
    for component, count in sorted(blame_counts.items(), key=lambda x: -x[1]):
        pct = count / total * 100
        style = "red" if pct > 30 else "yellow" if pct > 15 else "green"
        table.add_row(component, str(count), f"{pct:.0f}%", style=style)

    console.print(table)

    if fix_suggestions:
        typer.echo("\nTop Fix Suggestions:")
        seen = set()
        for fs in fix_suggestions[:15]:
            key = fs["fix"][:80]
            if key not in seen:
                seen.add(key)
                typer.echo(f"  [{fs['blame']}] {fs['fix']}")




@app.command(name="generate-bank")
def generate_bank(
    output: Path = typer.Option(
        question_bank.DEFAULT_BANK, "--output", "-o",
        help="Output JSON path for question bank",
    ),
    count: int = typer.Option(1000, "--count", "-n", help="Total questions to generate"),
    legacy: bool = typer.Option(False, "--legacy", help="Use old template-fill generator"),
):
    """Generate the question bank from ArangoDB data sources.

    Mines questions from 4 sources:
      A. F-36 lessons with taxonomy
      B. SPARTA QRAs (adversarial variants)
      C. F-36 specific claims (requirement IDs, thresholds)
      D. Taxonomy-driven gap questions

    Each question passes a 7-criterion quality gate before inclusion.
    """
    typer.echo(f"Generating {count} questions...")

    if legacy:
        typer.echo("Using legacy template-fill generator")
        bank = _generate_full_bank(count)
    else:
        bank = _generate_mined_bank(count)

    # Validate
    errors = question_bank.validate_bank(bank)
    if errors:
        typer.echo(f"WARNING: {len(errors)} validation errors:", err=True)
        for e in errors[:10]:
            typer.echo(f"  {e}", err=True)

    # Save
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(bank, f, indent=2)

    stats = question_bank.bank_stats(bank)
    typer.echo(f"\nGenerated {stats['total']} questions:")
    typer.echo(f"  By difficulty: {stats['by_difficulty']}")
    typer.echo(f"  By persona: {stats['by_persona']}")
    typer.echo(f"  By action: {stats['by_action']}")

    # Show bridge distribution for mined banks
    if not legacy:
        dist_report = question_quality.report_distribution(bank)
        typer.echo(f"  Bridge distribution: {dist_report['bridge_distribution']}")
        typer.echo(f"  By source: {dist_report['by_source']}")

    typer.echo(f"\nSaved to {output}")


def _generate_mined_bank(total: int = 1000) -> list[dict]:
    """Generate question bank via data-mining pipeline."""
    from sparta_stress_test.cli_bank_generator import generate_mined_bank
    return generate_mined_bank(total, question_miner, question_quality)


@app.command()
def report(
    last_run: bool = typer.Option(False, "--last-run", help="Show most recent run"),
    path: Optional[Path] = typer.Option(None, "--path", "-p", help="Specific results file"),
):
    """Display a graded results report."""
    if path:
        results_path = path
    elif last_run:
        # Find most recent results file
        if not RESULTS_DIR.exists():
            typer.echo("No results directory found. Run a stress test first.")
            raise typer.Exit(1)
        files = sorted(RESULTS_DIR.glob("stress_test_*.jsonl"), reverse=True)
        if not files:
            typer.echo("No results found. Run a stress test first.")
            raise typer.Exit(1)
        results_path = files[0]
    else:
        typer.echo("Specify --last-run or --path <file>")
        raise typer.Exit(1)

    # Load results
    results = []
    with open(results_path) as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))

    summary = grader.aggregate_grades([r["grade"] for r in results])
    _display_summary(summary, elapsed=None)

    # Show failures
    failures = [r for r in results if r.get("grade", {}).get("grade", "") in ("C", "F")]
    if failures:
        typer.echo(f"\n--- Failures ({len(failures)}) ---")
        for f in failures[:20]:
            grade_str = f.get("grade", {}).get("grade", "?")
            diff = f.get("difficulty", "?")
            exp = f.get("expected_action", "?")
            act = f.get("actual_action", "?")
            q = f.get("question_text", f.get("question", "?"))
            typer.echo(
                f"  {grade_str} | {diff:>9} | "
                f"{exp:>8}→{act:>8} | "
                f"{q[:70]}"
            )




from sparta_stress_test.cli_bank_generator import generate_full_bank as _generate_full_bank


if __name__ == "__main__":
    app()
