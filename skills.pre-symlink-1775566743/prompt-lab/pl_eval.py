"""Prompt evaluation CLI command."""
import asyncio
from datetime import datetime
from typing import List, Optional

import typer
from rich.table import Table

from config import SKILL_DIR, F1_THRESHOLD, CORRECTION_SUCCESS_THRESHOLD, ensure_dirs
from models import TaxonomyResponse
from llm import call_llm, call_llm_with_correction
from evaluation import EvalResult, EvalSummary, load_prompt, load_ground_truth, load_models_config, save_eval_results
from model_memory import get_model_memory, record_eval_result, get_model_recommendations
from utils import notify_task_monitor

from pl_app import app, console


@app.command()
def eval(
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p", help="Prompt name"),
    model: str = typer.Option("deepseek", "--model", "-m", help="Model to use"),
    cases: int = typer.Option(0, "--cases", "-n", help="Number of cases (0=all)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-case details"),
    max_corrections: int = typer.Option(2, "--max-corrections", help="Max self-correction rounds"),
    task_name: str = typer.Option("", "--task-name", help="Task-monitor task name for quality gate"),
    no_correction: bool = typer.Option(False, "--no-correction", help="Disable self-correction loop"),
    first_attempt_only: bool = typer.Option(
        False,
        "--first-attempt-only",
        help="Run single-call (no correction) AND corrected eval; gate on first_attempt_f1",
    ),
):
    """Run evaluation with a prompt and model.

    Uses self-correction loop: if LLM outputs invalid tags, sends correction
    message back to model asking it to fix its output.

    When --first-attempt-only is set, runs both a single-call (no correction)
    pass and a corrected pass, tracking first_attempt_f1 vs corrected_f1 so
    the human can see the improvement gap.  The quality gate checks
    first_attempt_f1, not corrected_f1.
    """
    ensure_dirs()
    models_config = load_models_config()

    if model not in models_config:
        console.print(f"[red]Model '{model}' not found. Available: {list(models_config.keys())}[/red]")
        raise typer.Exit(1)

    model_config = models_config[model]

    # Load prompt and ground truth
    system_prompt, user_template = load_prompt(prompt, SKILL_DIR)
    test_cases = load_ground_truth("taxonomy", SKILL_DIR)

    if cases > 0:
        test_cases = test_cases[:cases]

    # Check memory for model recommendations before running
    model_mem = get_model_memory()
    if model_mem.enabled:
        recs = get_model_recommendations(model_mem, "taxonomy")
        if recs and "No model recommendations" not in recs:
            # Check if chosen model has known failures
            failures = model_mem.recall_failures(model, k=3)
            if failures:
                console.print(f"[yellow]Note: '{model}' has {len(failures)} known failure(s) in memory[/yellow]")

    console.print(f"[bold]Evaluating prompt '{prompt}' with model '{model}'[/bold]")
    console.print(f"Test cases: {len(test_cases)}")
    if first_attempt_only:
        console.print("Mode: first-attempt-only (single call vs corrected, gate on first_attempt_f1)")
    elif not no_correction:
        console.print(f"Self-correction: enabled (max {max_corrections} rounds)")
    console.print()

    results: List[EvalResult] = []
    # first_attempt_results holds single-call results when --first-attempt-only is used
    first_attempt_results: List[EvalResult] = []
    requests = []
    for tc in test_cases:
        requests.append({
            "system": system_prompt,
            "user": user_template.format(name=tc.name, description=tc.description)
        })

    async def run_eval():
        if first_attempt_only:
            # --- Pass 1: single call, no correction (measures raw prompt quality) ---
            from models import parse_llm_response
            for tc in test_cases:
                user_msg = user_template.format(name=tc.name, description=tc.description)
                content, latency = await call_llm(system_prompt, user_msg, model_config)
                validated, rejected = parse_llm_response(content)
                fa_validated = validated or TaxonomyResponse()
                first_attempt_results.append(EvalResult(
                    case_id=tc.id,
                    predicted_conceptual=fa_validated.conceptual,
                    predicted_tactical=fa_validated.tactical,
                    expected_conceptual=tc.expected_conceptual,
                    expected_tactical=tc.expected_tactical,
                    rejected_tags=rejected,
                    confidence=fa_validated.confidence,
                    latency_ms=latency,
                ))
            # --- Pass 2: with self-correction (measures corrected quality) ---
            for tc in test_cases:
                user_msg = user_template.format(name=tc.name, description=tc.description)
                llm_result = await call_llm_with_correction(
                    system_prompt, user_msg, model_config,
                    max_correction_rounds=max_corrections,
                )
                validated = llm_result.validated or TaxonomyResponse()
                results.append(EvalResult(
                    case_id=tc.id,
                    predicted_conceptual=validated.conceptual,
                    predicted_tactical=validated.tactical,
                    expected_conceptual=tc.expected_conceptual,
                    expected_tactical=tc.expected_tactical,
                    rejected_tags=llm_result.rejected_tags,
                    confidence=validated.confidence,
                    latency_ms=llm_result.total_latency_ms,
                    correction_rounds=llm_result.correction_rounds,
                    correction_success=llm_result.success,
                ))
        elif no_correction:
            from llm import call_llm_batch
            llm_results = await call_llm_batch(requests, model_config)
            for i, res in enumerate(llm_results):
                tc = test_cases[i]
                validated = res.validated or TaxonomyResponse()
                results.append(EvalResult(
                    case_id=tc.id,
                    predicted_conceptual=validated.conceptual,
                    predicted_tactical=validated.tactical,
                    expected_conceptual=tc.expected_conceptual,
                    expected_tactical=tc.expected_tactical,
                    rejected_tags=res.rejected_tags,
                    confidence=validated.confidence,
                    latency_ms=res.total_latency_ms,
                ))
        else:
            for tc in test_cases:
                user_msg = user_template.format(name=tc.name, description=tc.description)
                llm_result = await call_llm_with_correction(
                    system_prompt, user_msg, model_config,
                    max_correction_rounds=max_corrections
                )
                validated = llm_result.validated or TaxonomyResponse()
                results.append(EvalResult(
                    case_id=tc.id,
                    predicted_conceptual=validated.conceptual,
                    predicted_tactical=validated.tactical,
                    expected_conceptual=tc.expected_conceptual,
                    expected_tactical=tc.expected_tactical,
                    rejected_tags=llm_result.rejected_tags,
                    confidence=validated.confidence,
                    latency_ms=llm_result.total_latency_ms,
                    correction_rounds=llm_result.correction_rounds,
                    correction_success=llm_result.success,
                ))

    asyncio.run(run_eval())

    # Compute first_attempt_f1 if applicable
    first_attempt_f1: Optional[float] = None
    if first_attempt_only and first_attempt_results:
        first_attempt_f1 = (
            sum(r.f1 for r in first_attempt_results) / len(first_attempt_results)
        )

    # Summary
    summary = EvalSummary(
        prompt_name=prompt,
        model_name=model,
        timestamp=datetime.now().isoformat(),
        results=results,
    )

    console.print()
    console.print("[bold]Summary[/bold]")

    table = Table()
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")

    if first_attempt_only and first_attempt_f1 is not None:
        # Show the gap between raw prompt quality and corrected quality
        corrected_f1 = summary.avg_f1
        gain = corrected_f1 - first_attempt_f1
        table.add_row("First-Attempt F1 (no correction)", f"{first_attempt_f1:.3f}")
        table.add_row("Corrected F1 (with correction)", f"{corrected_f1:.3f}")
        gain_str = f"+{gain:.3f}" if gain >= 0 else f"{gain:.3f}"
        table.add_row("Correction Gain", gain_str)
        table.add_row("-" * 20, "-" * 10)
    else:
        table.add_row("Avg F1", f"{summary.avg_f1:.3f}")

    table.add_row("Conceptual Precision", f"{summary.avg_conceptual_precision:.3f}")
    table.add_row("Conceptual Recall", f"{summary.avg_conceptual_recall:.3f}")
    table.add_row("Tactical Precision", f"{summary.avg_tactical_precision:.3f}")
    table.add_row("Tactical Recall", f"{summary.avg_tactical_recall:.3f}")
    table.add_row("Total Rejected Tags", str(summary.total_rejected))
    table.add_row("Avg Latency", f"{summary.avg_latency_ms:.0f}ms")

    if not no_correction:
        table.add_row("-" * 20, "-" * 10)
        table.add_row("Correction Rounds", str(summary.total_correction_rounds))
        table.add_row("Cases Needing Correction", str(summary.cases_needing_correction))
        table.add_row("Correction Success Rate", f"{summary.correction_success_rate:.1%}")

    console.print(table)

    # Quality gate check
    # When --first-attempt-only: gate on first_attempt_f1 (not corrected_f1)
    if first_attempt_only and first_attempt_f1 is not None:
        passed = first_attempt_f1 >= F1_THRESHOLD
    else:
        passed = summary.avg_f1 >= F1_THRESHOLD and summary.correction_success_rate >= CORRECTION_SUCCESS_THRESHOLD

    if passed:
        console.print("\n[green]QUALITY GATE PASSED[/green]")
    else:
        console.print("\n[red]QUALITY GATE FAILED[/red]")
        if first_attempt_only and first_attempt_f1 is not None:
            console.print(f"  - First-attempt F1 {first_attempt_f1:.3f} < {F1_THRESHOLD} threshold")
        else:
            if summary.avg_f1 < F1_THRESHOLD:
                console.print(f"  - F1 score {summary.avg_f1:.3f} < {F1_THRESHOLD} threshold")
            if summary.correction_success_rate < CORRECTION_SUCCESS_THRESHOLD:
                console.print(f"  - Correction success {summary.correction_success_rate:.1%} < {CORRECTION_SUCCESS_THRESHOLD:.0%} threshold")

    if task_name:
        notify_task_monitor(task_name, passed, summary)

    results_file = save_eval_results(
        summary, results, passed, SKILL_DIR, first_attempt_f1=first_attempt_f1
    )
    console.print(f"\nResults saved to: {results_file}")

    # Regression detection: compare to previous eval of the same prompt
    _check_regression(prompt, summary)

    # Record result in model memory for future recommendations
    model_mem = get_model_memory()
    if model_mem.enabled:
        fa_note = f", first_attempt_f1={first_attempt_f1:.3f}" if first_attempt_f1 is not None else ""
        observation = f"F1={summary.avg_f1:.3f}, corrections={summary.total_correction_rounds}{fa_note}"
        if passed:
            observation += " - PASSED quality gate"
        else:
            observation += " - FAILED quality gate"

        record_eval_result(
            memory=model_mem,
            model_alias=model,
            model_id=model_config.get("model", model),
            prompt_type="taxonomy",
            f1_score=summary.avg_f1,
            latency_ms=summary.avg_latency_ms,
            observation=observation,
            details=f"Prompt: {prompt}, Cases: {len(test_cases)}, Rejected: {summary.total_rejected}",
        )
        console.print(f"[dim]Recorded to model memory[/dim]")

    if not passed:
        raise typer.Exit(1)


def _check_regression(prompt: str, current: EvalSummary) -> None:
    """Compare current eval to the most recent previous eval for the same prompt.

    Warns on F1 regression > 0.05. Does not block — just alerts.
    """
    import json
    results_dir = SKILL_DIR / "results"
    if not results_dir.exists():
        return

    pattern = f"{prompt}_*.json"
    result_files = sorted(results_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    # Need at least 2 results (current + previous) to compare
    # Current result was just saved, so it's index 0 — previous is index 1
    if len(result_files) < 2:
        return

    try:
        prev_data = json.loads(result_files[1].read_text())
        prev_f1 = prev_data.get("metrics", {}).get("avg_f1", 0.0)
    except (json.JSONDecodeError, KeyError):
        return

    delta = current.avg_f1 - prev_f1
    if delta < -0.05:
        console.print(
            f"\n[bold red]REGRESSION DETECTED[/bold red]: F1 dropped {abs(delta):.3f} "
            f"({prev_f1:.3f} → {current.avg_f1:.3f}) vs previous eval"
        )
        console.print(f"  Previous: {result_files[1].name}")
    elif delta > 0.05:
        console.print(
            f"\n[bold green]IMPROVEMENT[/bold green]: F1 improved {delta:.3f} "
            f"({prev_f1:.3f} → {current.avg_f1:.3f})"
        )
