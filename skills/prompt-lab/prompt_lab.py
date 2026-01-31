#!/usr/bin/env python3
"""
Prompt Lab: Systematic prompt engineering with ground truth evaluation.

Architecture:
  Stage 1: LLM extraction with vocabulary presented in prompt
  Stage 2: Pydantic validation to detect hallucinated outputs
  Stage 3: SELF-CORRECTION LOOP - If invalid tags detected, send assistant
           correction message back to LLM asking it to fix its output

This three-stage approach ensures:
  - LLM knows valid options (vocabulary in prompt)
  - Invalid outputs are detected (Pydantic validation)
  - LLM gets a chance to self-correct before we reject
  - Metrics track correction rounds and success rate

Integration:
  - Iteration rounds (like /code-review)
  - Task-monitor integration for quality gates
"""
import asyncio
import json
import random
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Ensure this directory is importable when running as a script
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    import typer
    from rich.console import Console
    from rich.table import Table
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "typer", "pydantic", "rich", "-q"])
    import typer
    from rich.console import Console
    from rich.table import Table

# Absolute imports for script compatibility
from config import (
    SKILL_DIR,
    F1_THRESHOLD,
    CORRECTION_SUCCESS_THRESHOLD,
    QRA_SCORE_THRESHOLD,
    ensure_dirs,
)
from models import TaxonomyResponse, parse_llm_response, parse_qra_response, parse_qra_items_response
from llm import call_llm, call_llm_with_correction, call_llm_raw
from evaluation import (
    TestCase,
    EvalResult,
    EvalSummary,
    load_prompt,
    load_ground_truth,
    load_models_config,
    save_eval_results,
    count_sentences,
    check_keywords,
)
from qra_evaluation import (
    QRATestCase,
    QRAResult,
    QRAGroundedTestCase,
    QRAGroundedResult,
    QRAEvalSummary,
    load_qra_ground_truth,
    load_qra_grounded_truth,
    AmbiguityGate,
    check_entity_anchoring,
)
from sparta_connector import SpartaConnector, SpartaTestCase
from prompt_extractor import PromptExtractor
from citation_validator import (
    validate_citations,
    check_duplicate_answers,
    analyze_question_diversity,
)
from ground_truth import (
    collect_all_samples,
    build_keyword_ground_truth,
    build_llm_ground_truth,
)
from optimization import (
    analyze_results,
    generate_improvement_suggestions,
    save_analysis_report,
    collect_error_cases,
    build_optimization_prompt,
    apply_prompt_improvement,
    save_optimization_report,
    save_auto_iterate_report,
)
from memory_integration import TaxonomyMemory, enhance_prompt_with_memory
from model_memory import (
    get_model_memory,
    record_eval_result,
    get_model_recommendations,
    seed_known_observations,
)
from utils import notify_task_monitor

# Create Typer app
app = typer.Typer(help="Prompt Lab: Systematic prompt engineering with self-correction")
console = Console()


@app.command()
def eval(
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p", help="Prompt name"),
    model: str = typer.Option("deepseek", "--model", "-m", help="Model to use"),
    cases: int = typer.Option(0, "--cases", "-n", help="Number of cases (0=all)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-case details"),
    max_corrections: int = typer.Option(2, "--max-corrections", help="Max self-correction rounds"),
    task_name: str = typer.Option("", "--task-name", help="Task-monitor task name for quality gate"),
    no_correction: bool = typer.Option(False, "--no-correction", help="Disable self-correction loop"),
):
    """Run evaluation with a prompt and model.

    Uses self-correction loop: if LLM outputs invalid tags, sends correction
    message back to model asking it to fix its output.
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

    console.print(f"[bold]Evaluating prompt '{prompt}' with model '{model}'[/bold]")
    console.print(f"Test cases: {len(test_cases)}")
    if not no_correction:
        console.print(f"Self-correction: enabled (max {max_corrections} rounds)")
    console.print()

    results = []

    async def run_eval():
        for tc in test_cases:
            user_msg = user_template.format(name=tc.name, description=tc.description)

            try:
                if no_correction:
                    content, latency = await call_llm(system_prompt, user_msg, model_config)
                    validated, rejected = parse_llm_response(content)
                    correction_rounds = 0
                    correction_success = len(rejected) == 0
                else:
                    llm_result = await call_llm_with_correction(
                        system_prompt, user_msg, model_config,
                        max_correction_rounds=max_corrections
                    )
                    validated = llm_result.validated or TaxonomyResponse()
                    rejected = llm_result.rejected_tags
                    latency = llm_result.total_latency_ms
                    correction_rounds = llm_result.correction_rounds
                    correction_success = llm_result.success

                result = EvalResult(
                    case_id=tc.id,
                    predicted_conceptual=validated.conceptual,
                    predicted_tactical=validated.tactical,
                    expected_conceptual=tc.expected_conceptual,
                    expected_tactical=tc.expected_tactical,
                    rejected_tags=rejected,
                    confidence=validated.confidence,
                    latency_ms=latency,
                    correction_rounds=correction_rounds,
                    correction_success=correction_success,
                )
                results.append(result)

                if verbose:
                    status = "[green]PASS[/green]" if result.f1 >= 0.8 else "[yellow]PARTIAL[/yellow]" if result.f1 > 0 else "[red]FAIL[/red]"
                    correction_info = f" (corrected x{correction_rounds})" if correction_rounds > 0 else ""
                    console.print(f"  {tc.id}: {status} F1={result.f1:.2f}{correction_info}")
                    console.print(f"    Expected: C={tc.expected_conceptual} T={tc.expected_tactical}")
                    console.print(f"    Got:      C={validated.conceptual} T={validated.tactical}")
                    if rejected:
                        console.print(f"    [dim]Rejected tags: {rejected}[/dim]")
                else:
                    correction_info = f" x{correction_rounds}" if correction_rounds > 0 else ""
                    console.print(f"  {tc.id}: F1={result.f1:.2f}{correction_info}")

            except Exception as e:
                console.print(f"  [red]{tc.id}: ERROR - {e}[/red]")
                results.append(EvalResult(
                    case_id=tc.id,
                    predicted_conceptual=[],
                    predicted_tactical=[],
                    expected_conceptual=tc.expected_conceptual,
                    expected_tactical=tc.expected_tactical,
                    rejected_tags=["ERROR"],
                    confidence=0,
                    latency_ms=0,
                    correction_rounds=0,
                    correction_success=False,
                ))

    asyncio.run(run_eval())

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
    passed = summary.avg_f1 >= F1_THRESHOLD and summary.correction_success_rate >= CORRECTION_SUCCESS_THRESHOLD
    if passed:
        console.print("\n[green]QUALITY GATE PASSED[/green]")
    else:
        console.print("\n[red]QUALITY GATE FAILED[/red]")
        if summary.avg_f1 < F1_THRESHOLD:
            console.print(f"  - F1 score {summary.avg_f1:.3f} < {F1_THRESHOLD} threshold")
        if summary.correction_success_rate < CORRECTION_SUCCESS_THRESHOLD:
            console.print(f"  - Correction success {summary.correction_success_rate:.1%} < {CORRECTION_SUCCESS_THRESHOLD:.0%} threshold")

    if task_name:
        notify_task_monitor(task_name, passed, summary)

    results_file = save_eval_results(summary, results, passed, SKILL_DIR)
    console.print(f"\nResults saved to: {results_file}")

    # Record result in model memory for future recommendations
    model_mem = get_model_memory()
    if model_mem.enabled:
        observation = f"F1={summary.avg_f1:.3f}, corrections={summary.total_correction_rounds}"
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



@app.command()
def compare(
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p", help="Prompt name"),
    models: str = typer.Option("deepseek", "--models", "-m", help="Comma-separated model names"),
):
    """Compare multiple models on the same prompt."""
    model_list = [m.strip() for m in models.split(",")]

    console.print(f"[bold]Comparing {len(model_list)} models on prompt '{prompt}'[/bold]")
    console.print()

    for model in model_list:
        console.print(f"[bold cyan]--- {model} ---[/bold cyan]")
        eval(prompt=prompt, model=model, cases=0, verbose=False)
        console.print()


@app.command()
def list_prompts():
    """List available prompts."""
    prompts_dir = SKILL_DIR / "prompts"
    if prompts_dir.exists():
        for f in prompts_dir.glob("*.txt"):
            console.print(f"  {f.stem}")
    else:
        console.print("No prompts found. Run 'eval' to create default.")


@app.command()
def show_prompt(name: str = typer.Argument(..., help="Prompt name")):
    """Show a prompt's content."""
    prompt_file = SKILL_DIR / "prompts" / f"{name}.txt"
    if prompt_file.exists():
        console.print(prompt_file.read_text())
    else:
        console.print(f"[red]Prompt '{name}' not found[/red]")


@app.command()
def history(
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p", help="Prompt name"),
):
    """View evaluation history for a prompt."""
    results_dir = SKILL_DIR / "results"
    if not results_dir.exists():
        console.print("No results found.")
        return

    pattern = f"{prompt}_*.json"
    result_files = sorted(results_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    if not result_files:
        console.print(f"No results found for prompt '{prompt}'")
        return

    console.print(f"[bold]History for prompt '{prompt}'[/bold]\n")

    table = Table()
    table.add_column("Timestamp", style="dim")
    table.add_column("Model", style="cyan")
    table.add_column("F1", style="green")
    table.add_column("Corrections", style="yellow")
    table.add_column("Status")

    for rf in result_files[:10]:
        data = json.loads(rf.read_text())
        metrics = data.get("metrics", {})
        passed = data.get("passed", metrics.get("avg_f1", 0) >= 0.8)

        table.add_row(
            data.get("timestamp", "")[:19],
            data.get("model", ""),
            f"{metrics.get('avg_f1', 0):.3f}",
            str(metrics.get("correction_rounds", 0)),
            "[green]PASS[/green]" if passed else "[red]FAIL[/red]",
        )

    console.print(table)


@app.command("eval-qra")
def eval_qra(
    prompt: str = typer.Option("qra_v1", "--prompt", "-p", help="QRA prompt name"),
    model: str = typer.Option("deepseek", "--model", "-m", help="Model to use"),
    cases: int = typer.Option(0, "--cases", "-n", help="Number of cases (0=all)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-case details"),
):
    """Evaluate QRA (Question-Reasoning-Answer) generation quality."""
    ensure_dirs()
    models_config = load_models_config()

    if model not in models_config:
        console.print(f"[red]Model '{model}' not found. Available: {list(models_config.keys())}[/red]")
        raise typer.Exit(1)

    model_config = models_config[model]
    system_prompt, user_template = load_prompt(prompt, SKILL_DIR)
    test_cases = load_qra_ground_truth(SKILL_DIR)

    if not test_cases:
        console.print("[red]No QRA ground truth found. Create ground_truth/qra.json[/red]")
        raise typer.Exit(1)

    if cases > 0:
        test_cases = test_cases[:cases]

    console.print(f"[bold]Evaluating QRA prompt '{prompt}' with model '{model}'[/bold]")
    console.print(f"Test cases: {len(test_cases)}")
    console.print()

    results = []

    async def run_qra_eval():
        for tc in test_cases:
            user_msg = user_template.format(
                name=tc.name,
                description=tc.description,
                collection=tc.collection,
                type=tc.item_type,
            )

            try:
                import time
                start = time.perf_counter()

                content, _ = await call_llm(system_prompt, user_msg, model_config)
                latency = (time.perf_counter() - start) * 1000

                qra = parse_qra_response(content)

                q_hits = check_keywords(qra.get("question", ""), tc.question_keywords)
                r_hits = check_keywords(qra.get("reasoning", ""), tc.reasoning_keywords)
                r_sentences = count_sentences(qra.get("reasoning", ""))

                result = QRAResult(
                    case_id=tc.id,
                    question=qra.get("question", ""),
                    reasoning=qra.get("reasoning", ""),
                    answer=qra.get("answer", ""),
                    confidence=qra.get("confidence", 0),
                    question_keyword_hits=q_hits,
                    question_keyword_total=len(tc.question_keywords),
                    reasoning_keyword_hits=r_hits,
                    reasoning_keyword_total=len(tc.reasoning_keywords),
                    reasoning_sentences=r_sentences,
                    latency_ms=latency,
                )
                results.append(result)

                if verbose:
                    status = "[green]GOOD[/green]" if result.overall_score >= 0.7 else "[yellow]PARTIAL[/yellow]" if result.overall_score > 0.3 else "[red]WEAK[/red]"
                    console.print(f"  {tc.id}: {status} Score={result.overall_score:.2f}")
                    console.print(f"    Q: {result.question[:80]}...")
                else:
                    console.print(f"  {tc.id}: Score={result.overall_score:.2f}")

            except Exception as e:
                console.print(f"  [red]{tc.id}: ERROR - {e}[/red]")

    asyncio.run(run_qra_eval())

    if results:
        avg_score = sum(r.overall_score for r in results) / len(results)

        console.print()
        console.print("[bold]Summary[/bold]")

        table = Table()
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Overall Score", f"{avg_score:.3f}")

        console.print(table)

        passed = avg_score >= QRA_SCORE_THRESHOLD
        if passed:
            console.print("\n[green]QRA QUALITY GATE PASSED[/green]")
        else:
            console.print("\n[red]QRA QUALITY GATE FAILED[/red]")

        if not passed:
            raise typer.Exit(1)


@app.command()
def analyze(
    results_file: Optional[Path] = typer.Option(None, "--results", "-r", help="Results JSON to analyze"),
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p", help="Prompt to analyze results for"),
    suggest_improvements: bool = typer.Option(True, "--suggest/--no-suggest", help="Generate improvement suggestions"),
):
    """Analyze previous evaluation results and suggest prompt improvements."""
    results_dir = SKILL_DIR / "results"

    if results_file:
        if not results_file.exists():
            console.print(f"[red]Results file not found: {results_file}[/red]")
            raise typer.Exit(1)
        results_files = [results_file]
    else:
        pattern = f"{prompt}_*.json"
        results_files = sorted(results_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        if not results_files:
            console.print(f"[red]No results found for prompt '{prompt}'[/red]")
            raise typer.Exit(1)

    console.print(f"[bold]Analyzing {len(results_files)} result file(s)[/bold]\n")

    analysis = analyze_results(results_files, prompt)

    console.print("[bold cyan]Error Pattern Analysis[/bold cyan]")
    if analysis["total_rejected"] > 0:
        console.print("\nMost common invalid tags:")
        for tag, count in analysis["most_common_errors"]:
            console.print(f"  {tag}: {count}x")

    if suggest_improvements and analysis["rejected_counts"]:
        console.print("\n[bold cyan]Suggested Improvements[/bold cyan]")
        from collections import Counter
        suggestions = generate_improvement_suggestions(Counter(analysis["rejected_counts"]))
        for i, suggestion in enumerate(suggestions, 1):
            console.print(f"  {i}. {suggestion}")

    analysis_file = save_analysis_report(analysis, SKILL_DIR)
    console.print(f"\nAnalysis saved to: {analysis_file}")


@app.command()
def optimize(
    prompt: str = typer.Option("taxonomy_v1", "--prompt", "-p", help="Prompt to optimize"),
    model: str = typer.Option("deepseek", "--model", "-m", help="Model for optimization suggestions"),
):
    """Use LLM to suggest prompt optimizations based on error patterns."""
    results_dir = SKILL_DIR / "results"
    pattern = f"{prompt}_*.json"
    results_files = sorted(results_dir.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)

    if not results_files:
        console.print(f"[red]No results found for prompt '{prompt}'. Run 'eval' first.[/red]")
        raise typer.Exit(1)

    error_cases = collect_error_cases(results_files)
    if not error_cases:
        console.print("[green]No significant errors found. Prompt appears to be working well.[/green]")
        return

    console.print(f"[bold]Analyzing {len(error_cases)} error cases for optimization[/bold]\n")

    models_config = load_models_config()
    model_config = models_config.get(model, {})
    system_prompt, _ = load_prompt(prompt, SKILL_DIR)

    optimization_prompt = build_optimization_prompt(system_prompt, error_cases)

    console.print("Generating optimization suggestions...")

    async def get_suggestions():
        messages = [
            {"role": "system", "content": "You are an expert prompt engineer. Analyze prompts and suggest improvements."},
            {"role": "user", "content": optimization_prompt},
        ]
        return await call_llm_raw(messages, model_config, max_tokens=1024)

    suggestions = asyncio.run(get_suggestions())

    if "error" in suggestions:
        console.print(f"[red]Failed to generate suggestions: {suggestions['error']}[/red]")
        return

    console.print("\n[bold cyan]Optimization Suggestions[/bold cyan]")
    for i, suggestion in enumerate(suggestions.get("improvements", []), 1):
        console.print(f"  {i}. {suggestion}")

    opt_file = save_optimization_report(prompt, len(error_cases), suggestions, SKILL_DIR)
    console.print(f"\nOptimization suggestions saved to: {opt_file}")


@app.command("build-ground-truth")
def build_ground_truth_cmd(
    output: str = typer.Option("taxonomy_large", "--output", "-o", help="Output ground truth name"),
    attck_count: int = typer.Option(15, "--attck", help="Number of ATT&CK samples"),
    nist_count: int = typer.Option(15, "--nist", help="Number of NIST samples"),
    cwe_count: int = typer.Option(10, "--cwe", help="Number of CWE samples"),
    d3fend_count: int = typer.Option(10, "--d3fend", help="Number of D3FEND samples"),
    seed: int = typer.Option(42, "--seed", help="Random seed for reproducibility"),
):
    """Build stratified ground truth from SPARTA data sources."""
    random.seed(seed)
    ensure_dirs()

    console.print(f"[bold]Building ground truth with stratified sampling[/bold]")

    samples, counts = collect_all_samples(attck_count, nist_count, cwe_count, d3fend_count)
    console.print(f"Total samples: {len(samples)}")

    gt_file = build_keyword_ground_truth(output, samples, counts, seed, SKILL_DIR)
    console.print(f"\n[green]Ground truth saved to: {gt_file}[/green]")
    console.print("[yellow]Review and refine the expected labels before using for evaluation[/yellow]")


@app.command("build-llm-ground-truth")
def build_llm_ground_truth_cmd(
    output: str = typer.Option("taxonomy_llm", "--output", "-o", help="Output ground truth name"),
    model: str = typer.Option("deepseek-v3.2", "--model", "-m", help="Model for label generation"),
    prompt: str = typer.Option("taxonomy_v2", "--prompt", "-p", help="Prompt to use"),
    attck_count: int = typer.Option(15, "--attck", help="Number of ATT&CK samples"),
    nist_count: int = typer.Option(15, "--nist", help="Number of NIST samples"),
    cwe_count: int = typer.Option(10, "--cwe", help="Number of CWE samples"),
    d3fend_count: int = typer.Option(10, "--d3fend", help="Number of D3FEND samples"),
    confidence_threshold: float = typer.Option(0.7, "--threshold", help="Flag cases below this confidence"),
    seed: int = typer.Option(42, "--seed", help="Random seed for reproducibility"),
    store_memory: bool = typer.Option(True, "--memory/--no-memory", help="Store extractions in memory"),
    use_few_shot: bool = typer.Option(False, "--few-shot", help="Use memory for few-shot context"),
):
    """Build ground truth using LLM predictions with confidence flagging.

    Integrates with /memory skill to store extractions as they complete,
    enabling few-shot context for future extractions.
    """
    random.seed(seed)
    ensure_dirs()

    models_config = load_models_config()
    if model not in models_config:
        console.print(f"[red]Model '{model}' not found[/red]")
        raise typer.Exit(1)

    model_config = models_config[model]

    # Initialize memory integration
    memory = TaxonomyMemory() if (store_memory or use_few_shot) else None
    if memory and memory.enabled:
        console.print(f"[dim]Memory integration: {'store + few-shot' if use_few_shot else 'store only'}[/dim]")
    elif store_memory or use_few_shot:
        console.print(f"[dim]Memory unavailable (standalone mode)[/dim]")

    console.print(f"[bold]Building LLM-based ground truth[/bold]")
    console.print(f"Model: {model}, Prompt: {prompt}")

    samples, counts = collect_all_samples(attck_count, nist_count, cwe_count, d3fend_count)
    console.print(f"Total samples: {len(samples)}")

    system_prompt, user_template = load_prompt(prompt, SKILL_DIR)
    cases = []
    flagged_count = 0
    memory_stored = 0

    async def generate_labels():
        nonlocal flagged_count, memory_stored

        for i, sample in enumerate(samples):
            # Optionally enhance prompt with few-shot examples from memory
            effective_prompt = system_prompt
            if use_few_shot and memory and memory.enabled:
                effective_prompt = enhance_prompt_with_memory(
                    system_prompt, sample['name'], sample['description'], memory
                )

            user_msg = user_template.format(name=sample['name'], description=sample['description'])

            try:
                llm_result = await call_llm_with_correction(
                    effective_prompt, user_msg, model_config, max_correction_rounds=2
                )

                if llm_result.validated:
                    validated = llm_result.validated
                    conceptual = validated.conceptual
                    tactical = validated.tactical
                    confidence = validated.confidence
                else:
                    conceptual, tactical, confidence = [], [], 0.0

                needs_review = (
                    confidence < confidence_threshold or
                    not conceptual or
                    not tactical or
                    llm_result.correction_rounds > 0
                )

                if needs_review:
                    flagged_count += 1

                # Store successful high-confidence extractions in memory
                if store_memory and memory and memory.enabled:
                    if conceptual and tactical and confidence >= 0.85 and not needs_review:
                        stored = memory.learn_extraction(
                            name=sample['name'],
                            description=sample['description'],
                            conceptual=conceptual,
                            tactical=tactical,
                            confidence=confidence,
                        )
                        if stored:
                            memory_stored += 1

                cases.append({
                    "id": sample["id"],
                    "input": {"name": sample["name"], "description": sample["description"]},
                    "expected": {"conceptual": conceptual, "tactical": tactical},
                    "metadata": {
                        "collection": sample["collection"],
                        "llm_confidence": confidence,
                        "correction_rounds": llm_result.correction_rounds,
                        "needs_review": needs_review,
                    },
                    "notes": f"LLM-generated from {sample['collection']}" + (" [REVIEW]" if needs_review else ""),
                })

                status = "!" if needs_review else "+"
                console.print(f"  [{i+1}/{len(samples)}] {status} {sample['id']}")

            except Exception as e:
                console.print(f"  [{i+1}/{len(samples)}] x {sample['id']}: ERROR - {e}")
                cases.append({
                    "id": sample["id"],
                    "input": {"name": sample["name"], "description": sample["description"]},
                    "expected": {"conceptual": [], "tactical": []},
                    "metadata": {"collection": sample["collection"], "error": str(e), "needs_review": True},
                    "notes": f"ERROR: {e}",
                })
                flagged_count += 1

    asyncio.run(generate_labels())

    gt_file = build_llm_ground_truth(
        output, cases, counts, seed, model, prompt, confidence_threshold, flagged_count, SKILL_DIR
    )
    console.print(f"\n[green]Ground truth saved to: {gt_file}[/green]")
    if flagged_count > 0:
        console.print(f"[yellow]{flagged_count} cases flagged for review[/yellow]")
    if memory_stored > 0:
        console.print(f"[dim]{memory_stored} high-confidence extractions stored in memory[/dim]")


@app.command("models")
def list_models(
    capability: str = typer.Option("", "--cap", "-c", help="Filter by capability: json, reasoning, agentic, coding"),
    recommend: bool = typer.Option(False, "--recommend", "-r", help="Show recommendations from memory"),
    prompt_type: str = typer.Option("taxonomy", "--type", "-t", help="Prompt type for recommendations"),
):
    """List available models with metrics and recommendations."""
    import json as json_module
    models_file = SKILL_DIR / "models.json"

    if not models_file.exists():
        console.print("[red]models.json not found[/red]")
        raise typer.Exit(1)

    models = json_module.loads(models_file.read_text())

    # Show recommendations if requested
    if recommend:
        model_mem = get_model_memory()
        if model_mem.enabled:
            console.print(get_model_recommendations(model_mem, prompt_type))
        else:
            console.print("[dim]Model memory not available[/dim]")
        console.print()

    # Build table
    table = Table(title="Chutes Models")
    table.add_column("Alias", style="cyan")
    table.add_column("Params", style="green")
    table.add_column("Quant", style="yellow")
    table.add_column("Arch")
    table.add_column("Experts")
    table.add_column("Context")
    table.add_column("JSON")
    table.add_column("Caps", style="dim")

    for alias, config in models.items():
        if alias.startswith("_"):
            continue
        if not isinstance(config, dict):
            continue

        # Filter by capability
        if capability:
            cap_map = {
                "json": "json_mode",
                "reasoning": "reasoning",
                "agentic": "agentic",
                "coding": "coding",
            }
            cap_key = cap_map.get(capability, capability)
            if not config.get(cap_key):
                continue

        params = config.get("params_b", "?")
        active = config.get("active_params_b")
        quant = config.get("quantization", "?")
        arch = config.get("architecture", "?")
        experts = config.get("experts")
        experts_active = config.get("experts_active")
        ctx = config.get("context_k", "?")
        json_mode = "✓" if config.get("json_mode") else "✗"

        caps = []
        if config.get("reasoning"):
            caps.append("reason")
        if config.get("thinking_mode"):
            caps.append("think")
        if config.get("agentic"):
            caps.append("agent")
        if config.get("coding"):
            caps.append("code")
        if config.get("taxonomy_f1"):
            caps.append(f"F1:{config['taxonomy_f1']}")

        param_str = f"{params}B" if not active else f"{params}B/{active}B"
        expert_str = f"{experts_active}/{experts}" if experts else "-"
        ctx_str = f"{ctx}K" if ctx != "?" else "?"
        caps_str = ", ".join(caps)

        table.add_row(alias, param_str, quant, arch, expert_str, ctx_str, json_mode, caps_str)

    console.print(table)


@app.command("seed-memory")
def seed_memory():
    """Seed model memory with known observations."""
    model_mem = get_model_memory()
    if not model_mem.enabled:
        console.print("[yellow]Model memory not available (standalone mode)[/yellow]")
        return

    stored = seed_known_observations(model_mem)
    console.print(f"[green]Seeded {stored} known observations into model memory[/green]")


@app.command("extract-prompts")
def extract_prompts(
    file: Path = typer.Option(..., "--file", "-f", help="Python file to extract from"),
    output: Path = typer.Option(Path("prompts"), "--output", "-o", help="Output directory"),
):
    """Extract prompts from Python file (variables ending in _PROMPT)."""
    ensure_dirs()
    console.print(f"[bold]Extracting prompts from {file}[/bold]")
    
    try:
        extractor = PromptExtractor()
        prompts = extractor.extract_from_file(file)
        extractor.save_prompts(prompts, output, prefix=f"{file.stem}_")
        
        console.print(f"[green]Extracted {len(prompts)} prompts to {output}[/green]")
        for name in prompts:
            console.print(f"  - {name}")
            
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command("test-sparta")
def test_sparta(
    prompt_file: Path = typer.Option(None, "--prompt-file", "-f", help="Python file with prompts"),
    run_id: str = typer.Option("run-recovery-verify", "--run-id", "-r", help="SPARTA Run ID"),
    cases: int = typer.Option(100, "--cases", "-n", help="Number of test cases"),
    phase: int = typer.Option(0, "--phase", help="SPARTA phase (0=Rel, 1=Control)"),
    db_path: Path = typer.Option(
        Path("/home/graham/workspace/experiments/sparta/data/runs/run-recovery-verify/sparta.duckdb"),
        "--db-path", help="Path to SPARTA DuckDB"
    ),
    threshold: float = typer.Option(0.85, "--threshold", "-t", help="Grounding threshold"),
):
    """End-to-End SPARTA QRA Test with real data."""
    ensure_dirs()
    console.print(f"[bold]SPARTA QRA Test[/bold]")
    console.print(f"DB: {db_path}")
    
    # Load prompt (either from file or default)
    system_prompt = ""
    if prompt_file:
        try:
            prompts = PromptExtractor.extract_from_file(prompt_file)
            # Heuristic to find the right prompt
            # If phase 0, look for TACTIC_CONTROL_PROMPT, else SIMPLE_SYSTEM_PROMPT
            target = "TACTIC_CONTROL_PROMPT" if phase == 0 else "SIMPLE_SYSTEM_PROMPT"
            if target in prompts:
                system_prompt = prompts[target]
                console.print(f"[green]Loaded {target} from {prompt_file}[/green]")
            else:
                # Fallback to first available or error
                system_prompt = list(prompts.values())[0] 
                console.print(f"[yellow]Warning: {target} not found, using first available prompt[/yellow]")
        except Exception as e:
            console.print(f"[red]Failed to load prompt file: {e}[/red]")
            raise typer.Exit(1)
    else:
        # Load default prompt
        s, _ = load_prompt("qra_grounded_v1", SKILL_DIR)
        system_prompt = s
        console.print("[blue]Using default prompt: qra_grounded_v1[/blue]")

    # Connect to DB
    try:
        connector = SpartaConnector(db_path)
        test_cases = connector.fetch_test_cases(limit=cases, phase=phase)
        console.print(f"Fetched {len(test_cases)} test cases")
    except Exception as e:
        console.print(f"[red]DB Connection Error: {e}[/red]")
        raise typer.Exit(1)

    if not test_cases:
        console.print("[yellow]No test cases found.[/yellow]")
        raise typer.Exit(0)

    # Run Eval
    models_config = load_models_config()
    model_config = models_config.get("chutes-deepseek", models_config.get("deepseek")) # Prefer chutes if avail
    if not model_config:
        model_config = list(models_config.values())[0]
        console.print(f"[yellow]Using fallback model: {model_config['model']}[/yellow]")
    
    results = []
    
    async def run_eval():
        for tc in test_cases:
            # Construct user message based on test case type
            # Note: The system prompt from SPARTA usually expects specific context injection
            # For this test, we might need a template. 
            # If using extracted SPARTA prompt, it often expects raw JSON context or specific format.
            # We'll try to emulate the SPARTA pipeline context construction simply here.
            
            # Simple emulation of context construction for the user message
            if phase == 0:
                 user_msg = f"""Generate QRAs about how this control relates to the technique in space systems.
The TACTIC HIERARCHY below is the anchor.

PROMPT CONTEXT:
{json.dumps({
    "tactic_hierarchy": {
        "technique": {
            **tc.source_control,
            "knowledge_from_urls": tc.knowledge_excerpts
        }
    },
    "related_control": tc.target_control,
}, indent=2)}
"""
            else:
                user_msg = f"""Generate factual questions about this SPARTA control.
Control:
{json.dumps({
    **tc.source_control,
    "knowledge_excerpts": tc.knowledge_excerpts
}, indent=2)}
"""

            try:
                content, latency = await call_llm(system_prompt, user_msg, model_config)
                qra_items_model = parse_qra_items_response(content)
                qra_items = qra_items_model.items
                
                # Validation
                citation_validation = validate_citations(qra_items, " ".join(tc.knowledge_excerpts), threshold)
                
                # Ambiguity & Anchoring
                ambiguity_passes = 0
                anchoring_passes = 0
                common_missing = []
                
                for item in qra_items:
                    q = item.get("question", "")
                    # Ambiguity
                    if AmbiguityGate.check(q, tc.context_keywords)["ok"]:
                        ambiguity_passes += 1
                    
                    # Anchoring
                    anchoring = check_entity_anchoring(q, tc.context_keywords)
                    if anchoring["anchored"]:
                        anchoring_passes += 1
                    else:
                        common_missing.extend(anchoring["missing_entities"])

                ambiguity_rate = ambiguity_passes / len(qra_items) if qra_items else 1.0
                anchoring_rate = anchoring_passes / len(qra_items) if qra_items else 1.0
                
                # Check duplicates
                duplicates = check_duplicate_answers(qra_items)
                diversity = analyze_question_diversity(qra_items)
                
                results.append(QRAGroundedResult(
                    case_id=tc.id,
                    qra_items=qra_items,
                    source_text=" ".join(tc.knowledge_excerpts)[:100], # Trucated for display
                    latency_ms=latency,
                    total_qras=len(qra_items),
                    citation_grounding_rate=citation_validation.grounding_rate,
                    hallucination_count=citation_validation.ungrounded_citations,
                    duplicate_count=len(duplicates),
                    question_type_distribution=diversity["question_type_distribution"],
                    persona_distribution=diversity["persona_distribution"],
                    confidence_distribution=diversity["confidence_distribution"],
                    question_type_coverage=diversity["question_type_coverage"],
                    ambiguity_pass_rate=ambiguity_rate,
                    entity_anchoring_rate=anchoring_rate,
                    missing_entities_common=list(set(common_missing))
                ))
                
                console.print(f"  {tc.id}: {len(qra_items)} QRAs | Gnd: {citation_validation.grounding_rate:.0%} | Amb: {ambiguity_rate:.0%} | Anch: {anchoring_rate:.0%}")

            except Exception as e:
                console.print(f"  [red]{tc.id} Error: {e}[/red]")

    asyncio.run(run_eval())
    
    # Summary
    summary = QRAEvalSummary(
        prompt_name=prompt_file.name if prompt_file else "default",
        model_name=model_config['model'],
        timestamp=datetime.now().isoformat(),
        results=results,
    )
    
    table = Table(title="SPARTA QRA Test Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_column("Components", style="yellow")
    
    table.add_row("Ambiguity Gate Pass", f"{summary.avg_ambiguity_pass_rate:.1%}", "Length, Keyword Context")
    table.add_row("Entity Anchoring", f"{summary.avg_entity_anchoring_rate:.1%}", "Explicit Entity Naming")
    table.add_row("Citation Grounding", f"{summary.avg_citation_grounding_rate:.1%}", "Verbatim Excerpts")
    table.add_row("Total Generated", str(summary.total_qras_generated), "")
    
    console.print(table)


if __name__ == "__main__":
    app()
