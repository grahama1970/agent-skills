"""
Provider Pricing - Fetch and compare costs across LLM providers.

Thin assembler: imports from pricing_models, pricing_core, pricing_providers
and re-exports all public names for backward compatibility.

Usage:
    from provider_pricing import get_batch_cost_comparison

    result = await get_batch_cost_comparison(
        model_pattern="deepseek-v3.2",
        num_requests=90000,
        avg_input_tokens=400,
        avg_output_tokens=600,
    )
"""
import asyncio
import json
import sys

# Re-export everything from sub-modules
from pricing_models import (
    BatchProviderPricing,
    ProviderPricing,
    PRICING_CACHE,
    CHUTES_AVAILABLE,
    ChutesClient,
    RUNPOD_AVAILABLE,
    RunPodCalculator,
    SKILLS_DIR,
    OPS_CHUTES_DIR,
    OPS_RUNPOD_DIR,
    OPS_RUNPOD_ALT,
)

from pricing_core import (
    get_provider_pricing,
    estimate_batch_cost,
    find_cheapest_provider,
    format_cost_table,
    load_cached_pricing,
    save_cached_pricing,
    parse_pricing_from_dogpile,
    research_pricing_with_dogpile,
    find_cheapest_for_model,
    PRICING_CACHE_FILE,
)

from pricing_providers import (
    fetch_openrouter_pricing,
    fetch_chutes_pricing,
    fetch_live_chutes_pricing,
    get_chutes_quota,
    get_chutes_model_status,
    get_chutes_balance,
    get_runpod_cost_estimates,
    get_runpod_cost_estimate,
    get_batch_cost_comparison,
)


# =============================================================================
# CLI INTERFACE
# =============================================================================

if __name__ == "__main__":
    import typer

    app = typer.Typer()

    @app.command()
    def main(
        model: str = typer.Argument("deepseek-v3.2", help="Model pattern"),
        requests: int = typer.Option(90000, "--requests", "-n", help="Number of requests"),
        avg_input: int = typer.Option(400, "--avg-input", help="Avg input tokens per request"),
        avg_output: int = typer.Option(600, "--avg-output", help="Avg output tokens per request"),
        dogpile: bool = typer.Option(False, "--dogpile", help="Use dogpile for pricing research"),
        live: bool = typer.Option(False, "--live", help="Fetch live pricing from APIs"),
    ):
        if dogpile:
            result = asyncio.run(research_pricing_with_dogpile(model, refresh=True))
            print(json.dumps(result, indent=2))
        else:
            result = asyncio.run(get_batch_cost_comparison(
                model_pattern=model,
                num_requests=requests,
                avg_input_tokens=avg_input,
                avg_output_tokens=avg_output,
                use_live_pricing=live,
            ))

            if result.get("found"):
                print(result["table"])
                print()
                print(f"CHEAPEST: {result['cheapest']['provider']} - ${result['cheapest']['total_cost']:.2f}")
                if result.get("savings_vs_second", 0) > 0:
                    print(f"Savings vs next: ${result['savings_vs_second']:.2f}")
            else:
                print(f"Error: {result.get('error')}")

    app()
