"""pdf-lab CLI implementation chunk 2.

Loaded by pdf_lab.py to keep source files below 800 lines.
"""

from dotenv import load_dotenv

load_dotenv()

def _print_compare_result(result: dict, verbose: bool = False) -> None:
    """Pretty-print a comparison result."""
    fixture_id = result.get("fixture_id", "unknown")
    score = result.get("overall_score", 0)

    typer.echo(f"\n{'='*60}")
    typer.echo(f"pdf-lab Compare: {fixture_id}")
    typer.echo(f"{'='*60}")
    typer.echo(f"Overall Score: {score:.2%}")
    typer.echo()

    # Section delta
    sd = result.get("section_delta", {})
    typer.echo(f"  Sections:  expected={sd.get('expected', '?')}  got={sd.get('got', '?')}  "
               f"matched={sd.get('title_matched', '?')}  missed={sd.get('title_missed', '?')}  "
               f"score={sd.get('score', 0):.2%}")

    # Block delta
    bd = result.get("block_delta", {})
    typer.echo(f"  Blocks:    expected={bd.get('expected', '?')}  actual={bd.get('actual', '?')}  "
               f"type_match={bd.get('type_matches', '?')}  misclass={bd.get('misclassified', '?')}  "
               f"score={bd.get('score', 0):.2%}")

    # Table delta
    td = result.get("table_delta", {})
    typer.echo(f"  Tables:    real={td.get('expected_real', '?')}  false={td.get('expected_false', '?')}  "
               f"extracted={td.get('extracted', '?')}  "
               f"score={td.get('score', 0):.2%}")

    # Figure delta
    fd = result.get("figure_delta", {})
    typer.echo(f"  Figures:   expected={fd.get('expected', '?')}  got={fd.get('got', '?')}  "
               f"score={fd.get('score', 0):.2%}")

    # Requirement delta
    rd = result.get("requirement_delta", {})
    typer.echo(f"  Reqs:      real={rd.get('expected_real', '?')}  false={rd.get('expected_false', '?')}  "
               f"matched={rd.get('matched_real', '?')}  "
               f"score={rd.get('score', 0):.2%}")

    # Profile delta
    pd_delta = result.get("profile_delta", {})
    typer.echo(f"  Profile:   {pd_delta.get('matches', '?')}/{pd_delta.get('total', '?')} fields match  "
               f"score={pd_delta.get('score', 0):.2%}")

    if verbose:
        typer.echo(f"\n--- Profile Details ---")
        for key, detail in pd_delta.get("details", {}).items():
            status = "OK" if detail.get("match") else "MISMATCH"
            typer.echo(f"  {key}: expected={detail.get('expected')} got={detail.get('got')} [{status}]")

        typer.echo(f"\n--- Block Type Counts (GT) ---")
        for t, c in sorted(result.get("block_delta", {}).get("gt_type_counts", {}).items()):
            typer.echo(f"  {t}: {c}")

        typer.echo(f"\n--- Block Type Counts (Extracted) ---")
        for t, c in sorted(result.get("block_delta", {}).get("ext_type_counts", {}).items()):
            typer.echo(f"  {t}: {c}")

        typer.echo(f"\n--- Tricks ---")
        for trick in result.get("tricks", []):
            typer.echo(f"  - {trick}")

    typer.echo(f"{'='*60}")


@app.command()
def synthetic(
    patterns: str = typer.Option("[]", help="Pattern list as JSON array"),
    output: Optional[Path] = typer.Option(None, help="Output PDF path"),
    sections: int = typer.Option(8, help="Target section count"),
    tables: int = typer.Option(2, help="Target table count"),
    figures: int = typer.Option(1, help="Target figure count"),
):
    """Generate a synthetic reproduction PDF from patterns."""
    try:
        pattern_list = json.loads(patterns)
    except json.JSONDecodeError:
        # Try comma-separated
        pattern_list = [p.strip() for p in patterns.split(",") if p.strip()]

    if not pattern_list:
        logger.warning("No patterns specified. Using default test patterns.")
        pattern_list = ["section_undersegmentation", "missed_tables"]

    pdf_path, spec = generate_synthetic(
        patterns=pattern_list,
        target_sections=sections,
        target_tables=tables,
        target_figures=figures,
        output_path=output,
    )

    typer.echo(f"Generated: {pdf_path}")
    typer.echo(f"Spec: {json.dumps(spec.to_dict(), indent=2)}")


@app.command()
def metrics(
    sample_size: int = typer.Option(100, help="Number of sections to sample"),
    retrieval: bool = typer.Option(False, help="Run retrieval evaluation"),
    output_json: Path = typer.Option(None, help="Write JSON report to file"),
):
    """Run integrity checks and optional retrieval evaluation, then report."""
    from lib.integrity import check_integrity
    from lib.metrics_models import VerificationReport
    from lib.metrics_report import render_markdown, render_json, store_report

    summary, issues = check_integrity(sample_size=sample_size)
    retrieval_metrics = None
    if retrieval:
        from lib.retrieval_eval import build_auto_judgements, evaluate_retrieval
        judgements = build_auto_judgements()
        retrieval_metrics = evaluate_retrieval(judgements)
    report = VerificationReport(
        integrity_summary=summary,
        integrity_issues=issues,
        retrieval_metrics=retrieval_metrics,
    )
    typer.echo(render_markdown(report))
    store_report(report)
    if output_json:
        output_json.write_text(render_json(report))
        typer.echo(f"JSON report written to {output_json}")


@app.command()
def status():
    """Show recent tuning results from local data."""
    data_dir = Path(os.environ.get("PDF_LAB_DATA", Path.home() / ".pi" / "pdf-lab"))
    events_file = data_dir / "convergence_events.jsonl"

    typer.echo("=== pdf-lab Status ===\n")

    if events_file.exists():
        lines = events_file.read_text().strip().split("\n")
        recent = lines[-10:]  # Last 10 events
        typer.echo(f"Total convergence events: {len(lines)}")
        typer.echo(f"\nRecent events:")
        for line in recent:
            try:
                event = json.loads(line)
                ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(event["timestamp"]))
                tags = event.get("tags", [])
                pattern_tags = [t for t in tags if t.startswith("pattern:")]
                typer.echo(f"  {ts} | {' '.join(pattern_tags)}")
            except Exception:
                continue
    else:
        typer.echo("No convergence events yet. Run 'pdf-lab tune' to start.")

    # Show git history
    typer.echo("\nGit commits:")
    try:
        result = subprocess.run(
            ["git", "log", "--all", "--oneline", "--grep=pdf-lab:", "-5"],
            cwd=str(EXTRACTOR_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.stdout.strip():
            typer.echo(result.stdout)
        else:
            typer.echo("  No pdf-lab commits found.")
    except Exception:
        typer.echo("  (git log unavailable)")


@app.command(name="status-report")
def status_report(
    manifest: Optional[Path] = typer.Option(None, help="Workflow manifest JSON"),
    triage: Optional[Path] = typer.Option(None, help="Human triage queue JSON"),
    comparison: Optional[Path] = typer.Option(None, help="JSON comparison artifact"),
    extraction: Optional[Path] = typer.Option(None, help="Full extraction artifact"),
    toc_audit: Optional[Path] = typer.Option(None, help="TOC audit artifact"),
    evidence_manifest: Optional[Path] = typer.Option(None, help="Promoted evidence crop manifest"),
    memory_qa: Optional[Path] = typer.Option(None, help="Memory/Qdrant final QA report"),
    second_pass_backlog: Optional[Path] = typer.Option(None, help="Agent second-pass engineering backlog JSON"),
    public_dir: Path = typer.Option(
        Path("${HOME}/workspace/experiments/pi-mono/packages/ux-lab/public"),
        help="UX Lab public directory used to discover default PDF Lab artifacts",
    ),
    output: Optional[Path] = typer.Option(None, "--out", help="HTML report output path"),
    json_output: Optional[Path] = typer.Option(None, "--json-out", help="JSON report output path"),
    stdout_json: bool = typer.Option(False, "--json", help="Print JSON report to stdout"),
):
    """Create an artifact-derived PDF Lab status / definition-of-done report.

    This command is deliberately conservative: missing artifacts, unresolved
    human triage, suppressed agent findings, and sample-only evidence coverage
    are all surfaced as blockers instead of being treated as success.
    """
    discovered = default_paths(public_dir)
    paths = StatusReportPaths(
        manifest=manifest or discovered.manifest,
        triage=triage or discovered.triage,
        comparison=comparison or discovered.comparison,
        extraction=extraction or discovered.extraction,
        toc_audit=toc_audit or discovered.toc_audit,
        evidence_manifest=evidence_manifest or discovered.evidence_manifest,
        memory_qa=memory_qa or discovered.memory_qa,
        second_pass_backlog=second_pass_backlog or discovered.second_pass_backlog,
    )
    report = build_status_report(paths)

    if json_output:
        json_output.parent.mkdir(parents=True, exist_ok=True)
        json_output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")

    if stdout_json:
        typer.echo(json.dumps(report, indent=2, sort_keys=True))
        return

    output_path = output or Path("/tmp/pdf-lab-status-report.html")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_html(report), encoding="utf-8")

    summary = report["summary"]
    blockers = report["blockers"]
    typer.echo("pdf-lab status report created")
    typer.echo(f"  html: {output_path}")
    if json_output:
        typer.echo(f"  json: {json_output}")
    typer.echo(f"  parity: {summary.get('parity_accuracy', 'unknown')}")
    typer.echo(f"  human triage cards: {summary.get('human_triage_task_count', 'unknown')}")
    typer.echo(f"  blockers: {len(blockers)}")


@app.command(name="memory-qa")
def memory_qa(
    extraction: Optional[Path] = typer.Option(None, help="Full extraction artifact"),
    evidence_manifest: Optional[Path] = typer.Option(None, help="Promoted evidence crop manifest"),
    output: Optional[Path] = typer.Option(None, "--out", help="Memory/Qdrant QA report output path"),
    public_dir: Path = typer.Option(
        Path("${HOME}/workspace/experiments/pi-mono/packages/ux-lab/public"),
        help="UX Lab public directory used to discover default PDF Lab artifacts",
    ),
    sample_size: int = typer.Option(8, help="Number of evidence elements to check through Qdrant recall"),
    apply_memory: bool = typer.Option(False, "--apply-memory", help="Persist evidence metadata to ArangoDB memory before checking Qdrant"),
):
    """Build the final Memory/Qdrant PDF-element recall QA artifact.

    This is the standard post-triage agent QA gate. It uses real PDF Lab
    extraction/evidence artifacts and reports failure when crops, memory upsert,
    text vectors, visual vectors, or recall checks are incomplete.
    """
    discovered = default_paths(public_dir)
    evidence_path = evidence_manifest or discovered.evidence_manifest
    if evidence_path is None:
        typer.echo("No evidence manifest configured; regenerate/promote evidence artifacts first.", err=True)
        raise typer.Exit(1)

    output_path = output or (public_dir / "pdf-lab-memory-qa-report.json")
    report = write_memory_qa_report(MemoryQaConfig(
        extraction_path=extraction or discovered.extraction,
        evidence_manifest_path=evidence_path,
        output_path=output_path,
        public_root=public_dir,
        sample_size=sample_size,
        apply_memory=apply_memory,
    ))

    summary = report["summary"]
    typer.echo(f"Memory/Qdrant QA passed: {report['passed']}")
    typer.echo(f"Evidence coverage: {summary['evidence_elements']} / {summary['extraction_elements']}")
    typer.echo(f"Text indexed: {summary['text_indexed_elements']}")
    typer.echo(f"Visual indexed: {summary['visual_indexed_elements']}")
    typer.echo(f"Sample checks: {summary['sample_checks_passed']} / {summary['sample_checks']}")
    typer.echo(f"Wrote: {output_path}")


@app.command(name="coverage-loop")
def coverage_loop(
    status_report_path: Optional[Path] = typer.Option(None, "--status-report", help="Artifact-derived PDF Lab status report JSON"),
    public_dir: Path = typer.Option(
        Path("${HOME}/workspace/experiments/pi-mono/packages/ux-lab/public"),
        help="UX Lab public directory containing promoted PDF Lab artifacts",
    ),
    project_knowledge: Path = typer.Option(
        Path("${HOME}/workspace/experiments/pdf_oxide/PROJECT_KNOWLEDGE.md"),
        help="PDF Lab project-knowledge file containing anti-drift loop policy",
    ),
    active_plan: Optional[Path] = typer.Option(None, "--active-plan", help="Current repair/regenerate orchestration plan"),
    output: Optional[Path] = typer.Option(None, "--out", help="Coverage loop artifact output path"),
    history: Optional[Path] = typer.Option(None, "--history", help="Coverage loop JSONL history path"),
    no_history: bool = typer.Option(False, "--no-history", help="Do not append this generation to loop history"),
    stdout_json: bool = typer.Option(False, "--json", help="Print JSON artifact to stdout"),
):
    """Generate the PDF Lab Coverage anti-hallucination loop artifact.

    The output records whether Coverage is complete, needs a new/amended plan,
    or must stop for interview/dogpile because the same blocker persisted.
    """
    status_path = status_report_path or (public_dir / "pdf-lab-status-report.json")
    out_path = output or (public_dir / "pdf-lab-coverage-loop.json")
    artifact = build_coverage_loop(
        CoverageLoopConfig(
            status_report_path=status_path,
            project_knowledge_path=project_knowledge,
            active_plan_path=active_plan,
            output_path=out_path,
            history_path=history,
        ),
        append_history=not no_history,
    )

    if stdout_json:
        typer.echo(json.dumps(artifact, indent=2, sort_keys=True))
        return

    typer.echo("pdf-lab coverage loop artifact created")
    typer.echo(f"  json: {out_path}")
    typer.echo(f"  next_action: {artifact['next_action']}")
    typer.echo(f"  blocker_signature: {artifact['blocker_signature']}")
    typer.echo(f"  same_blocker_streak: {artifact['same_blocker_streak']}")


@app.command()
def rollback(
    sha: str = typer.Option(..., help="Commit SHA to revert"),
):
    """Rollback a specific pdf-lab fix by SHA."""
    typer.echo(f"Rolling back commit {sha}...")

    try:
        # Verify it's a pdf-lab commit
        result = subprocess.run(
            ["git", "log", "--format=%s", "-1", sha],
            cwd=str(EXTRACTOR_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if "pdf-lab:" not in result.stdout:
            typer.echo(f"Commit {sha} is not a pdf-lab commit. Aborting.")
            raise typer.Exit(1)

        # Revert
        result = subprocess.run(
            ["git", "revert", "--no-edit", sha],
            cwd=str(EXTRACTOR_ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            typer.echo(f"Successfully reverted {sha}")
        else:
            typer.echo(f"Revert failed: {result.stderr}")
            raise typer.Exit(1)

    except subprocess.TimeoutExpired:
        typer.echo("Git command timed out.")
        raise typer.Exit(1)


@app.command(name="regression-check")
def regression_check(
    baseline: Path = typer.Option(..., help="Baseline comparison.json (pre-fix)"),
    candidate: Path = typer.Option(..., help="Candidate comparison.json (post-fix)"),
    target_class: Optional[str] = typer.Option(
        None,
        help="Defect-vector dimension the fix targets; must strictly decrease",
    ),
    output: Optional[Path] = typer.Option(
        None, help="Write pdf_lab.regression_verdict.v1 JSON here"
    ),
):
    """Deterministic defect-vector regression referee for a repair.

    Exits 0 only when no blocking dimension worsened, matched_expected did
    not decrease, and (when given) --target-class strictly decreased.
    """
    from lib.regression import run_regression_check

    verdict = run_regression_check(
        baseline, candidate, target_class=target_class, output_path=output
    )
    typer.echo(json.dumps(verdict, indent=2, ensure_ascii=False))
    if verdict["verdict"] != "PASS":
        raise typer.Exit(1)


@app.command()
def answer(
    book: Optional[Path] = typer.Option(None, help="Question book JSONL path"),
    mode: str = typer.Option("auto", help="Interview mode: auto, html, tui"),
    output: Optional[Path] = typer.Option(None, help="Save answer book to this path"),
):
    """Review and answer deferred questions from an overnight batch run.

    Opens the question book in /interview for the human to answer all at once.
    Saves answers to an answer book for replay on the next batch run.
    """
    questions = load_question_book(book)
    if not questions:
        typer.echo("No deferred questions found. Nothing to review.")
        return

    typer.echo(f"Found {len(questions)} deferred questions from batch run.")
    typer.echo("Opening /interview for review...\n")

    guidance_map = run_batch_interview(book_path=book, mode=mode)

    if not guidance_map:
        typer.echo("No answers collected (interview cancelled or failed).")
        return

    answered = sum(1 for g in guidance_map.values() if g.escalated)
    typer.echo(f"\nAnswered: {answered}/{len(questions)}")

    # Save answer book
    answer_path = save_answer_book(guidance_map, book_path=output)
    typer.echo(f"Answer book saved: {answer_path}")
    typer.echo(f"\nTo replay: pdf-lab tune <pdf> --answers {answer_path}")

    # Offer to clear the question book
    clear_question_book(book)
    typer.echo("Question book cleared.")


@app.command(name="book")
def show_book(
    book: Optional[Path] = typer.Option(None, help="Question book JSONL path"),
    output_json: bool = typer.Option(False, "--json", help="JSON output"),
):
    """Show pending deferred questions from the question book."""
    questions = load_question_book(book)
    if not questions:
        typer.echo("No deferred questions. Run a batch with --question-book to generate.")
        return

    if output_json:
        typer.echo(json.dumps([q.to_dict() for q in questions], indent=2))
        return

    typer.echo(f"=== pdf-lab Question Book: {len(questions)} questions ===\n")
    for i, q in enumerate(questions):
        typer.echo(f"  [{i+1}/{len(questions)}] {q.pdf_name}")
        typer.echo(f"    Reason: {q.reason}")
        typer.echo(f"    Delta: {q.delta_summary.get('overall_delta', '?')}")
        typer.echo(f"    Patterns: {', '.join(q.patterns) or 'none'}")
        typer.echo(f"    Screenshots: {len(q.screenshots)}")
        typer.echo()

    typer.echo(f"Run 'pdf-lab answer' to review and answer all questions.")


def _try_auto_delta(pdf: Path) -> ExtractionDelta:
    """Try to compute delta automatically by finding pipeline output."""
    # Look for pipeline output in common locations
    candidates = [
        pdf.parent / "pipeline_output",
        pdf.parent / "data" / "results" / "pipeline",
        Path("data/results/pipeline"),
    ]

    for candidate in candidates:
        profile = candidate / "00_profile_detector" / "profile.json"
        structural = candidate / "11_json_exporter" / "structural.json"
        if profile.exists() and structural.exists():
            return compute_delta_from_json(profile, structural)

    # Return empty delta (will trigger "looks good" or diagnosis)
    logger.warning("Could not find pipeline output. Using empty delta.")
    return ExtractionDelta()


def _parse_page_list(pages: str) -> list[int]:
    """Parse comma-separated pages and ranges, e.g. 1,4,9-12."""
    parsed: list[int] = []
    for part in pages.split(","):
        token = part.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start, end = int(start_text), int(end_text)
            if end < start:
                raise ValueError(f"Invalid page range: {token}")
            parsed.extend(range(start, end + 1))
        else:
            parsed.append(int(token))
    if not parsed:
        raise ValueError("No pages provided")
    if any(page < 1 for page in parsed):
        raise ValueError("Pages are 1-based and must be positive")
    return sorted(set(parsed))


def _print_tune_result(result: TuneResult) -> None:
    """Pretty-print a tune result."""
    typer.echo(f"\n{'='*60}")
    typer.echo(f"pdf-lab Convergence Result: {result.status.upper()}")
    typer.echo(f"{'='*60}")
    typer.echo(f"Delta: {result.delta_before:.2f} -> {result.delta_after:.2f}")
    typer.echo(f"Iterations: {result.iterations}")

    if result.diagnosis:
        typer.echo(f"Root cause: {result.diagnosis.root_cause}")
        typer.echo(f"Patterns: {', '.join(result.diagnosis.patterns)}")

    if result.runtime_params:
        typer.echo(f"\nRuntime params (per-PDF tuning):")
        for key, value in result.runtime_params.items():
            typer.echo(f"  {key}: {value}")

    if result.write_back_result:
        wb = result.write_back_result
        typer.echo(f"\nWrite-back: {wb.status}")
        if wb.changes:
            typer.echo(f"Code changes:")
            for c in wb.changes:
                typer.echo(f"  [{c.tier}] {c.file}: {c.description}")
        if wb.branch:
            typer.echo(f"Branch: {wb.branch}")
        if wb.commit_sha:
            typer.echo(f"Commit: {wb.commit_sha[:12]}")

    if result.synthetic_path:
        typer.echo(f"\nSynthetic PDF: {result.synthetic_path}")

    typer.echo(f"{'='*60}")


def main():
    app()


if __name__ == "__main__":
    main()
