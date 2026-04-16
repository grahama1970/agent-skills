"""Ground truth and analysis CLI commands."""
import asyncio
import json
import random
from pathlib import Path
from typing import Optional

import typer

from config import SKILL_DIR, ensure_dirs
from llm import call_llm_raw, call_llm_with_correction
from evaluation import load_prompt, load_models_config
from ground_truth import collect_all_samples, build_keyword_ground_truth, build_llm_ground_truth
from optimization import (
    analyze_results,
    generate_improvement_suggestions,
    save_analysis_report,
    collect_error_cases,
    build_optimization_prompt,
    save_optimization_report,
)
from memory_integration import TaxonomyMemory, enhance_prompt_with_memory

from pl_app import app, console


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
def suggest_optimizations(
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



