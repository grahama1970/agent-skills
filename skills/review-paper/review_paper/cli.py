"""CLI entry point for /review-paper: review, diagnose, improve, batch."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

import typer
from loguru import logger
from rich.console import Console

from .metrics import compute_diagnostics, compute_humanization
from .models import AnalysisResult, BatchResult
from .parser import parse_paper
from .persona import evaluate_persona_alignment, load_personas
from .llm_review import (
    gateway_available,
    generate_review_prompts,
    rewrite_flagged_sentences,
    run_batch_llm_review,
    run_gateway_llm_review,
    scillm_available,
)
from .reporter import (
    build_revision_plan,
    emit_json_line,
    render_markdown_report,
    write_outputs,
)
from .task_monitor_client import ReviewPaperTaskClient

app = typer.Typer(no_args_is_help=True, pretty_exceptions_show_locals=False)
console = Console()


def analyze_paper(path: Path, personas_path: Optional[Path]) -> AnalysisResult:
    logger.info("Parsing {}", path)
    paper = parse_paper(path)
    logger.info(
        "Parsed {} sections, {} paragraphs",
        len(paper.sections),
        sum(len(s.paragraphs) for s in paper.sections),
    )

    diagnostics = compute_diagnostics(paper)
    humanization = compute_humanization(paper, diagnostics)
    logger.info("Humanization score: {:.3f}", humanization.humanization_score)

    personas = load_personas(personas_path)
    persona_alignment, cross_score, cross_issues = evaluate_persona_alignment(
        paper, personas,
    )

    result = AnalysisResult(
        paper=paper,
        diagnostics=diagnostics,
        humanization=humanization,
        persona_alignment=persona_alignment,
        revision_plan=[],
        cross_persona_consistency=cross_score,
        cross_persona_issues=cross_issues,
    )
    result.revision_plan = build_revision_plan(result)
    return result


@app.command()
def review(
    paper_path: Path = typer.Argument(
        ..., exists=True, readable=True, help="Path to paper file",
    ),
    personas: Optional[Path] = typer.Option(
        None, "--personas", exists=True, readable=True,
        help="YAML/JSON persona config",
    ),
    json_out: Optional[Path] = typer.Option(
        None, "--json-out", help="Write diagnostics JSON",
    ),
    report_out: Optional[Path] = typer.Option(
        None, "--report-out", help="Write markdown report",
    ),
    headless: bool = typer.Option(
        False, "--headless", help="Headless mode for paper-lab integration",
    ),
) -> None:
    """Review a paper: parse, diagnose, score humanization, check persona alignment.

    In interactive mode (default), generates structured LLM review prompts
    that the calling agent (Claude/Pi) processes in-context.

    In headless mode (--headless), runs LLM review via /assistant gateway
    cascade (heuristic → classifier → GPT → scillm) and outputs full JSON
    for paper-lab convergence loops.
    """
    result = analyze_paper(paper_path, personas)

    if headless and gateway_available():
        # Headless: run full LLM review through /assistant gateway
        result = run_gateway_llm_review(result)
        write_outputs(result, json_out, report_out, None)
        print(json.dumps(json.loads(result.model_dump_json()), indent=2))
    elif headless:
        # Headless fallback: include prompts for external processing
        prompts = generate_review_prompts(result)
        write_outputs(result, json_out, report_out, None)
        output = json.loads(result.model_dump_json())
        output["review_prompts"] = prompts
        print(json.dumps(output, indent=2))
    else:
        # Interactive: agent processes prompts in-context
        prompts = generate_review_prompts(result)
        write_outputs(result, json_out, report_out, None)
        console.print(render_markdown_report(result))
        console.print("\n[bold]--- LLM Review Prompts ---[/bold]")
        console.print(f"[dim]System prompt:[/dim] {len(prompts['system'])} chars")
        for key, prompt in prompts.items():
            if key == "system":
                continue
            console.print(f"\n[bold cyan]{key}[/bold cyan]")
            console.print(prompt)


@app.command()
def diagnose(
    paper_path: Path = typer.Argument(
        ..., exists=True, readable=True, help="Path to paper file",
    ),
    personas: Optional[Path] = typer.Option(
        None, "--personas", exists=True, readable=True,
        help="YAML/JSON persona config",
    ),
    json_out: Optional[Path] = typer.Option(
        None, "--json-out", help="Write diagnostics JSON",
    ),
    report_out: Optional[Path] = typer.Option(
        None, "--report-out", help="Write markdown report",
    ),
) -> None:
    """Quick diagnostics: deterministic metrics only, no LLM calls."""
    result = analyze_paper(paper_path, personas)
    write_outputs(result, json_out, report_out, None)
    console.print(render_markdown_report(result))


@app.command()
def improve(
    paper_path: Path = typer.Argument(
        ..., exists=True, readable=True, help="Path to paper file",
    ),
    personas: Optional[Path] = typer.Option(
        None, "--personas", exists=True, readable=True,
        help="YAML/JSON persona config",
    ),
    json_out: Optional[Path] = typer.Option(
        None, "--json-out", help="Write diagnostics JSON",
    ),
    report_out: Optional[Path] = typer.Option(
        None, "--report-out", help="Write markdown report",
    ),
    rewrite_out: Optional[Path] = typer.Option(
        None, "--rewrite-out", help="Write normalized output copy",
    ),
    strict_no_fact_changes: bool = typer.Option(
        True, "--strict-no-fact-changes/--allow-fact-changes",
        help="Preserve source text when emitting rewritten output",
    ),
) -> None:
    """Review and produce a humanized rewrite (fact-safe by default).

    Uses the /assistant gateway cascade with the humanization-rewriter task
    to rewrite AI-flagged sentences while preserving all facts.
    """
    result = analyze_paper(paper_path, personas)
    if strict_no_fact_changes and rewrite_out is None:
        rewrite_out = paper_path.with_name(
            f"{paper_path.stem}.normalized{paper_path.suffix}",
        )

    # Run LLM review for richer diagnostics before rewriting
    if gateway_available():
        result = run_gateway_llm_review(result)

    write_outputs(result, json_out, report_out, None)

    # Rewrite flagged sentences via gateway cascade
    if rewrite_out:
        rewritten_text = rewrite_flagged_sentences(result)
        rewrite_out.write_text(rewritten_text, encoding="utf-8")

    console.print(render_markdown_report(result))
    if rewrite_out:
        console.print(f"[green]Wrote humanized output:[/green] {rewrite_out}")


@app.command()
def batch(
    items_file: Path = typer.Argument(
        ..., exists=True, readable=True,
        help="Text file with one paper path per line",
    ),
    personas: Optional[Path] = typer.Option(
        None, "--personas", exists=True, readable=True,
        help="YAML/JSON persona config",
    ),
    output_dir: Path = typer.Option(
        Path("outputs"), "--output-dir",
        help="Directory for reports and JSON outputs",
    ),
    task_monitor: bool = typer.Option(
        True, "--task-monitor/--no-task-monitor",
        help="Enable task-monitor integration",
    ),
    json_stream: bool = typer.Option(
        False, "--json-stream", help="Emit NDJSON per item",
    ),
    llm: bool = typer.Option(
        False, "--llm", help="Run LLM review via scillm (batch mode)",
    ),
) -> None:
    """Batch review multiple papers with task-monitor tracking.

    With --llm, runs LLM-powered section reviews via scillm/Chutes
    for cheap parallel completions across the corpus.
    """
    if llm and not gateway_available() and not scillm_available():
        logger.warning("--llm requested but neither gateway nor scillm available, skipping LLM review")
        llm = False
    paths = [
        Path(line.strip())
        for line in items_file.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    output_dir.mkdir(parents=True, exist_ok=True)
    client = ReviewPaperTaskClient(
        task_name=items_file.stem, total_items=len(paths),
    )
    if task_monitor:
        client.start_session()
    successes = 0
    failures = 0

    for path in paths:
        start = time.perf_counter()
        batch_result: BatchResult
        try:
            result = analyze_paper(path, personas)
            if llm:
                if gateway_available():
                    result = run_gateway_llm_review(result)
                else:
                    result = run_batch_llm_review(result)
            j_out = output_dir / f"{path.stem}.diagnostics.json"
            r_out = output_dir / f"{path.stem}.report.md"
            write_outputs(result, j_out, r_out, None)
            elapsed = int((time.perf_counter() - start) * 1000)
            batch_result = BatchResult(
                path=path, success=True, analysis=result, timing_ms=elapsed,
            )
            successes += 1
            if task_monitor:
                client.accomplishment(f"Reviewed {path.name}")
        except Exception as exc:
            logger.error("Failed to review {}: {}", path, exc)
            elapsed = int((time.perf_counter() - start) * 1000)
            batch_result = BatchResult(
                path=path, success=False, error=str(exc), timing_ms=elapsed,
            )
            failures += 1
        finally:
            if task_monitor:
                client.update()

        payload = {
            "item": str(batch_result.path),
            "success": batch_result.success,
            "timing_ms": batch_result.timing_ms,
            "error": batch_result.error,
        }
        if batch_result.success and batch_result.analysis is not None:
            payload["humanization_score"] = (
                batch_result.analysis.humanization.humanization_score
            )
            payload["cross_persona_consistency"] = (
                batch_result.analysis.cross_persona_consistency
            )
            payload["revision_items"] = len(batch_result.analysis.revision_plan)
            if batch_result.analysis.overall_score > 0:
                payload["overall_score"] = batch_result.analysis.overall_score
        if json_stream:
            emit_json_line(payload)
        else:
            console.print(json.dumps(payload, indent=2))

    if task_monitor:
        client.finish(
            notes=f"Completed batch: {successes} succeeded, {failures} failed",
        )


if __name__ == "__main__":
    app()
