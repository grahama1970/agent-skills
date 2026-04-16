"""Find minimum model CLI command."""
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table

from config import GROUND_TRUTH_DIR, PROMPTS_DIR, RESULTS_DIR, ensure_dirs
from llm import call_provider
from evaluation import load_models_config

from pl_app import app, console
from loguru import logger


@app.command("find-minimum")
def find_minimum(
    ground_truth: str = typer.Option(..., "--ground-truth", "-g", help="Ground truth JSON file"),
    threshold: float = typer.Option(0.80, "--threshold", "-t", help="Minimum accuracy threshold"),
    prompt_file: str = typer.Option(None, "--prompt", "-p", help="Optional prompt file"),
    prefer_local: bool = typer.Option(True, "--prefer-local/--no-prefer-local", help="Prefer local Ollama over Chutes"),
    max_models: int = typer.Option(10, "--max-models", help="Max models to test"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show per-case details"),
    with_cost: bool = typer.Option(False, "--with-cost", "-c", help="Show cost comparison across providers"),
    # Batch estimation parameters - REQUIRED for accurate cost estimates
    num_requests: int = typer.Option(90000, "--num-requests", "-n", help="Number of requests in batch (e.g., 90000 QRAs)"),
    avg_input_tokens: int = typer.Option(400, "--avg-input", help="Average input tokens per request (prompt)"),
    avg_output_tokens: int = typer.Option(600, "--avg-output", help="Average output tokens per request (response)"),
    use_dogpile: bool = typer.Option(False, "--dogpile", help="Use /dogpile to research fresh pricing"),
):
    """
    Find the smallest model that meets accuracy threshold.

    Tests models from smallest to largest, stopping at first model that meets
    the threshold. Supports both Chutes API and local Ollama models.

    Strategy:
      1. Load models sorted by params_b (smallest first)
      2. For each model, run ground truth evaluation
      3. Stop at first model meeting threshold
      4. Report recommended model

    With --with-cost:
      Compares pricing across providers (Chutes, OpenRouter, DeepSeek, RunPod).
      REQUIRES accurate batch estimates:
        --num-requests: Total requests (e.g., 90000 QRAs)
        --avg-input: Average prompt tokens per request
        --avg-output: Average response tokens per request

    Example:
      # Basic model search
      ./run.sh find-minimum -g queryspec.json -t 0.80

      # With cost comparison for 90K QRAs batch
      ./run.sh find-minimum -g queryspec.json --with-cost \\
        --num-requests 90000 --avg-input 400 --avg-output 600

      # Use dogpile for fresh pricing
      ./run.sh find-minimum -g queryspec.json --with-cost --dogpile
    """
    from llm import call_provider
    import httpx

    ensure_dirs()
    models_config = load_models_config()

    # Load ground truth
    gt_path = Path(GROUND_TRUTH_DIR) / ground_truth if not Path(ground_truth).is_absolute() else Path(ground_truth)
    if not gt_path.exists():
        console.print(f"[red]Ground truth not found: {gt_path}[/red]")
        raise typer.Exit(1)

    with open(gt_path) as f:
        gt_data = json.load(f)

    test_cases = gt_data.get("cases", [])
    if not test_cases:
        console.print("[red]No test cases found in ground truth[/red]")
        raise typer.Exit(1)

    # Load prompt if specified
    system_prompt = ""
    if prompt_file:
        prompt_path = Path(PROMPTS_DIR) / prompt_file if not Path(prompt_file).is_absolute() else Path(prompt_file)
        if prompt_path.exists():
            system_prompt = prompt_path.read_text()

    # Sort models by size (params_b), filtering for those with size info
    sized_models = []
    for name, config in models_config.items():
        if name.startswith("_"):  # Skip metadata keys
            continue
        params = config.get("params_b", float("inf"))
        provider = config.get("provider", "chutes")
        is_local = config.get("local", provider == "ollama")

        # Apply prefer_local filter
        if prefer_local and not is_local:
            continue
        if not prefer_local and is_local:
            continue

        sized_models.append((params, name, config))

    sized_models.sort(key=lambda x: x[0])
    sized_models = sized_models[:max_models]

    console.print(f"[bold]Finding minimum model for {len(test_cases)} test cases[/bold]")
    console.print(f"Threshold: {threshold*100:.0f}% accuracy")
    console.print(f"Models to test: {len(sized_models)}")
    console.print()

    results = []

    async def test_single_model(model_name: str, model_config: dict) -> dict:
        """Test a single model against all cases."""
        provider = model_config.get("provider", "chutes")
        params = model_config.get("params_b", "?")

        console.print(f"  Testing [bold]{model_name}[/bold] ({params}B, {provider})...")

        json_ok = 0
        action_ok = 0
        total_time = 0
        errors = []

        for tc in test_cases:
            query = tc.get("input", tc.get("query", ""))
            expected = tc.get("expected", {})
            expected_action = expected.get("action", expected.get("grade", tc.get("expected_action", "")))

            # Build prompt
            if system_prompt:
                prompt = system_prompt + f"\n\nUser: {query}"
            else:
                prompt = query

            messages = [{"role": "user", "content": prompt}]
            if system_prompt:
                messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ]

            try:
                content, latency = await call_provider(messages, model_config)
                total_time += latency

                # Parse JSON
                parsed = None
                try:
                    parsed = json.loads(content.strip())
                    json_ok += 1
                except json.JSONDecodeError:
                    # Try extracting JSON from text
                    start = content.find('{')
                    if start >= 0:
                        depth = 0
                        for i, char in enumerate(content[start:], start):
                            if char == '{': depth += 1
                            elif char == '}':
                                depth -= 1
                                if depth == 0:
                                    try:
                                        parsed = json.loads(content[start:i+1])
                                        json_ok += 1
                                        break
                                    except Exception as e:
                                        logger.debug("JSON parse failed: {}", e)

                # Check action — try "action" first, fall back to "grade" for grader-style prompts
                if parsed and expected_action:
                    actual = parsed.get("action") or parsed.get("grade")
                    if actual == expected_action:
                        action_ok += 1
                    elif verbose:
                        errors.append(f"{tc.get('id', '?')}: {actual} vs {expected_action}")

            except Exception as e:
                if verbose:
                    errors.append(f"{tc.get('id', '?')}: {str(e)[:50]}")

        n = len(test_cases)
        json_rate = json_ok / n if n > 0 else 0
        action_acc = action_ok / n if n > 0 else 0

        return {
            "model": model_name,
            "provider": provider,
            "params_b": params,
            "json_rate": json_rate,
            "action_acc": action_acc,
            "total_time": total_time,
            "errors": errors,
        }

    async def run_tests():
        for params, model_name, model_config in sized_models:
            try:
                result = await test_single_model(model_name, model_config)
                results.append(result)

                status = "[green]PASS[/green]" if result["action_acc"] >= threshold else "[red]FAIL[/red]"
                console.print(f"    {status} JSON={result['json_rate']*100:.0f}% Action={result['action_acc']*100:.0f}% ({result['total_time']/1000:.1f}s)")

                if result["errors"] and verbose:
                    for err in result["errors"][:3]:
                        console.print(f"      [dim]{err}[/dim]")

                # Stop early if we found a passing model
                if result["action_acc"] >= threshold:
                    console.print(f"\n[green]✓ Found minimum model: {model_name} ({params}B)[/green]")
                    return result

            except Exception as e:
                console.print(f"    [red]ERROR: {e}[/red]")

        return None

    winner = asyncio.run(run_tests())

    # Print summary
    console.print("\n" + "="*60)
    console.print("[bold]SUMMARY[/bold]")
    console.print("="*60)

    table = Table("Model", "Size", "Provider", "JSON%", "Action%", "Time")
    for r in results:
        style = "green" if r["action_acc"] >= threshold else ""
        table.add_row(
            r["model"],
            f"{r['params_b']}B",
            r["provider"],
            f"{r['json_rate']*100:.0f}%",
            f"{r['action_acc']*100:.0f}%",
            f"{r['total_time']/1000:.1f}s",
            style=style,
        )
    console.print(table)

    if winner:
        console.print(f"\n[bold green]RECOMMENDED: {winner['model']}[/bold green]")
        console.print(f"  Size: {winner['params_b']}B")
        console.print(f"  Provider: {winner['provider']}")
        console.print(f"  Accuracy: {winner['action_acc']*100:.0f}%")

        # Cost comparison across providers
        cost_result = None
        if with_cost:
            from provider_pricing import get_batch_cost_comparison

            console.print("\n" + "="*60)
            console.print("[bold]BATCH COST COMPARISON ACROSS PROVIDERS[/bold]")
            console.print("="*60)

            # Calculate total tokens from request parameters
            total_input = num_requests * avg_input_tokens
            total_output = num_requests * avg_output_tokens

            if use_dogpile:
                console.print("[dim]Researching pricing with /dogpile...[/dim]")

            cost_result = asyncio.run(
                get_batch_cost_comparison(
                    model_pattern=winner['model'],
                    num_requests=num_requests,
                    avg_input_tokens=avg_input_tokens,
                    avg_output_tokens=avg_output_tokens,
                    use_live_pricing=not use_dogpile,  # Use live API unless dogpile requested
                )
            )

            if cost_result.get("found"):
                # Show batch details
                console.print(f"\n[bold]Batch Details:[/bold]")
                console.print(f"  Requests: {num_requests:,}")
                console.print(f"  Avg input tokens: {avg_input_tokens}")
                console.print(f"  Avg output tokens: {avg_output_tokens}")
                console.print(f"  Total input: {total_input:,} ({total_input/1_000_000:.1f}M)")
                console.print(f"  Total output: {total_output:,} ({total_output/1_000_000:.1f}M)")
                console.print()

                # Create rich table for cost comparison
                cost_table = Table(
                    "Provider", "Model", "In $/M", "Out $/M",
                    "Est. Cost", "Est. Time", "Notes",
                    title="Provider Cost Comparison"
                )

                for i, est in enumerate(cost_result["estimates"]):
                    style = "green bold" if i == 0 else ""
                    in_price = est.get('input_price_per_m', 0)
                    out_price = est.get('output_price_per_m', 0)

                    cost_table.add_row(
                        est["provider"],
                        est.get("model_id", winner['model'])[:25],
                        f"${in_price:.2f}" if in_price else "N/A",
                        f"${out_price:.2f}" if out_price else "N/A",
                        f"${est['total_cost']:.2f}",
                        f"{est.get('estimated_hours', 0):.1f}h" if est.get('estimated_hours') else "N/A",
                        (est.get("notes", "") or "")[:25],
                        style=style,
                    )

                console.print(cost_table)

                cheapest = cost_result["cheapest"]
                console.print(f"\n[bold green]RECOMMENDED PROVIDER: {cheapest['provider']}[/bold green]")
                console.print(f"  Model: {cheapest.get('model_id', winner['model'])}")
                console.print(f"  Estimated cost: ${cheapest['total_cost']:.2f}")
                if cheapest.get("estimated_hours"):
                    console.print(f"  Estimated time: {cheapest['estimated_hours']:.1f}h")
                if cheapest.get("input_price_per_m"):
                    console.print(f"  Pricing: ${cheapest['input_price_per_m']:.2f}/${cheapest['output_price_per_m']:.2f} per 1M tokens")

                if cost_result.get("savings_vs_second", 0) > 0:
                    console.print(f"  [dim]Savings vs next: ${cost_result['savings_vs_second']:.2f}[/dim]")
            else:
                console.print(f"[yellow]Could not find pricing for {winner['model']}[/yellow]")

        # Save result
        output = {
            "timestamp": datetime.now().isoformat(),
            "threshold": threshold,
            "winner": winner,
            "all_results": results,
        }

        if cost_result and cost_result.get("found"):
            output["cost_comparison"] = {
                "num_requests": num_requests,
                "avg_input_tokens": avg_input_tokens,
                "avg_output_tokens": avg_output_tokens,
                "total_input_tokens": cost_result["input_tokens"],
                "total_output_tokens": cost_result["output_tokens"],
                "total_tokens": cost_result["total_tokens"],
                "cheapest_provider": cost_result["cheapest"],
                "all_providers": cost_result["estimates"],
            }

        output_path = RESULTS_DIR / f"find_minimum_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)
        console.print(f"\nResults saved to {output_path}")
    else:
        console.print(f"\n[red]No model met the {threshold*100:.0f}% threshold[/red]")
        raise typer.Exit(1)


