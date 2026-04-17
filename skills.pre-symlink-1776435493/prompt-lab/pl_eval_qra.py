"""QRA evaluation CLI command."""
import asyncio
import json
import time

import typer
from rich.table import Table

from config import SKILL_DIR, QRA_SCORE_THRESHOLD, ensure_dirs
from models import parse_qra_response
from llm import call_llm
from evaluation import load_prompt, load_models_config, count_sentences, check_keywords
from qra_evaluation import QRAResult, load_qra_ground_truth

from pl_app import app, console


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


