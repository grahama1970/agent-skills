"""
Core pricing estimation and comparison functions.

Provides batch cost estimation, cheapest-provider search,
cost table formatting, dogpile-based price research, and disk caching.
"""
import os
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from pricing_models import (
    BatchProviderPricing,
    ProviderPricing,
    PRICING_CACHE,
)
from loguru import logger


def get_provider_pricing(model_id: str, provider: Optional[str] = None) -> list[ProviderPricing]:
    """
    Get pricing for a model across all providers (or a specific provider).

    Args:
        model_id: Model ID (e.g., "deepseek-ai/DeepSeek-V3.2-TEE")
        provider: Optional specific provider to check

    Returns:
        List of ProviderPricing objects
    """
    results = []

    providers_to_check = [provider] if provider else PRICING_CACHE.keys()

    for prov in providers_to_check:
        if prov not in PRICING_CACHE:
            continue
        for cached_model, pricing in PRICING_CACHE[prov].items():
            # Match exact or partial model ID
            if model_id.lower() in cached_model.lower() or cached_model.lower() in model_id.lower():
                results.append(pricing)

    return results


def estimate_batch_cost(
    pricing: BatchProviderPricing,
    input_tokens: int,
    output_tokens: int,
    num_requests: Optional[int] = None,
    avg_input_per_request: Optional[int] = None,
    avg_output_per_request: Optional[int] = None,
) -> dict:
    """
    Estimate cost and time for a batch job.

    Args:
        pricing: BatchProviderPricing object
        input_tokens: Total input tokens (prompts)
        output_tokens: Total output tokens (responses)
        num_requests: Optional number of requests (for better time estimates)
        avg_input_per_request: Optional avg input tokens per request
        avg_output_per_request: Optional avg output tokens per request

    Returns:
        Dict with detailed cost breakdown, time estimate, and token stats
    """
    total_tokens = input_tokens + output_tokens

    # Calculate per-token costs
    input_cost = (input_tokens / 1_000_000) * pricing.input_price_per_m
    output_cost = (output_tokens / 1_000_000) * pricing.output_price_per_m
    api_cost = input_cost + output_cost

    # Apply batch discount if available
    if pricing.batch_api_available and pricing.batch_discount > 0:
        batch_cost = api_cost * (1 - pricing.batch_discount)
    else:
        batch_cost = api_cost

    # Effective throughput accounts for concurrent connections
    concurrent = pricing.concurrent_connections if hasattr(pricing, 'concurrent_connections') else 1
    concurrent = concurrent or 1

    # Self-hosted: calculate based on time, not tokens
    if pricing.hourly_cost:
        # RunPod: tokens_per_sec is total system throughput (already accounts for GPUs)
        time_seconds = output_tokens / pricing.tokens_per_sec
        time_hours = time_seconds / 3600
        infra_cost = time_hours * pricing.hourly_cost
        total_cost = infra_cost
        cost_type = "hourly"
    else:
        # API pricing: multiply by concurrent connections for effective throughput
        effective_throughput = pricing.tokens_per_sec * concurrent
        total_cost = batch_cost
        time_seconds = output_tokens / effective_throughput
        time_hours = time_seconds / 3600
        cost_type = "per_token"

    # Calculate requests if not provided
    if num_requests is None and avg_output_per_request:
        num_requests = output_tokens // avg_output_per_request

    # Infer averages if we have request count
    if num_requests and num_requests > 0:
        avg_input = avg_input_per_request or (input_tokens // num_requests)
        avg_output = avg_output_per_request or (output_tokens // num_requests)
    else:
        avg_input = avg_input_per_request
        avg_output = avg_output_per_request
        num_requests = None

    return {
        "provider": pricing.provider,
        "model_id": pricing.model_id,
        # Token breakdown
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "input_tokens_m": round(input_tokens / 1_000_000, 2),
        "output_tokens_m": round(output_tokens / 1_000_000, 2),
        # Cost breakdown
        "input_cost": round(input_cost, 2),
        "output_cost": round(output_cost, 2),
        "api_cost": round(api_cost, 2),
        "batch_discount": pricing.batch_discount if pricing.batch_api_available else 0,
        "batch_cost": round(batch_cost, 2) if pricing.batch_api_available else None,
        "infra_cost": round(pricing.hourly_cost * time_hours, 2) if pricing.hourly_cost else None,
        "total_cost": round(total_cost, 2),
        "cost_type": cost_type,
        # Pricing rates
        "input_price_per_m": pricing.input_price_per_m,
        "output_price_per_m": pricing.output_price_per_m,
        "hourly_rate": pricing.hourly_cost,
        # Time estimates
        "estimated_seconds": round(time_seconds, 0),
        "estimated_hours": round(time_hours, 2),
        "tokens_per_sec": pricing.tokens_per_sec,
        "concurrent_connections": pricing.concurrent_connections,
        # Request stats (if available)
        "num_requests": num_requests,
        "avg_input_per_request": avg_input,
        "avg_output_per_request": avg_output,
        # Quality metrics
        "batch_api_available": pricing.batch_api_available,
        "reliability_score": pricing.reliability_score,
        "notes": pricing.notes,
    }


def find_cheapest_provider(
    model_pattern: str,
    input_tokens: int,
    output_tokens: int,
) -> list[dict]:
    """
    Find cheapest provider for a model across all available providers.

    Args:
        model_pattern: Model name pattern to match (e.g., "deepseek-v3.2")
        input_tokens: Total input tokens for the batch
        output_tokens: Total output tokens for the batch

    Returns:
        List of cost estimates sorted by total_cost (cheapest first)
    """
    # Find all matching pricing entries
    all_pricing = []
    for provider, models in PRICING_CACHE.items():
        for model_id, pricing in models.items():
            if model_pattern.lower() in model_id.lower():
                all_pricing.append(pricing)

    # Calculate costs for each
    estimates = []
    for pricing in all_pricing:
        estimate = estimate_batch_cost(pricing, input_tokens, output_tokens)
        estimates.append(estimate)

    # Sort by total cost
    estimates.sort(key=lambda x: x["total_cost"])

    return estimates


def format_cost_table(estimates: list[dict]) -> str:
    """Format cost estimates as a simple text table."""
    if not estimates:
        return "No pricing data available"

    lines = [
        "Provider         | Model                      | Cost     | Time   | Notes",
        "-----------------|----------------------------|----------|--------|------",
    ]

    for e in estimates:
        provider = e["provider"][:15].ljust(15)
        model = e["model_id"][:26].ljust(26)
        cost = f"${e['total_cost']:.2f}".rjust(8)
        time = f"{e['estimated_hours']:.1f}h" if e["estimated_hours"] else "N/A"
        time = time.rjust(6)
        notes = e["notes"][:30] if e["notes"] else ""
        lines.append(f"{provider} | {model} | {cost} | {time} | {notes}")

    return "\n".join(lines)


# Cache file for dogpile-researched pricing
PRICING_CACHE_FILE = Path(__file__).parent / ".pricing_cache.json"


def load_cached_pricing() -> dict:
    """Load cached pricing from disk."""
    if PRICING_CACHE_FILE.exists():
        try:
            with open(PRICING_CACHE_FILE) as f:
                data = json.load(f)
                # Check if cache is less than 24 hours old
                cached_at = datetime.fromisoformat(data.get("cached_at", "2000-01-01"))
                if (datetime.now() - cached_at).total_seconds() < 86400:
                    return data.get("pricing", {})
        except Exception as e:
            logger.debug("value lookup failed: {}", e)
    return {}


def save_cached_pricing(pricing: dict) -> None:
    """Save pricing to disk cache."""
    try:
        with open(PRICING_CACHE_FILE, "w") as f:
            json.dump({
                "cached_at": datetime.now().isoformat(),
                "pricing": pricing,
            }, f, indent=2)
    except Exception as e:
        logger.debug("formatting failed: {}", e)


def parse_pricing_from_dogpile(dogpile_output: str) -> list[dict]:
    """
    Parse pricing information from dogpile research output.

    Extracts pricing patterns like:
    - "$0.25 per million input tokens"
    - "$0.38/M output"
    - "input: $0.25, output: $0.38"
    """
    pricing_entries = []

    # Common provider patterns
    provider_patterns = [
        (r"chutes\.ai|chutes", "chutes"),
        (r"openrouter", "openrouter"),
        (r"deepseek\s+api|deepseek\s+direct", "deepseek"),
        (r"runpod|self-hosted", "runpod"),
        (r"together\.ai|together", "together"),
        (r"fireworks\.ai|fireworks", "fireworks"),
        (r"anyscale", "anyscale"),
    ]

    # Price extraction patterns
    price_patterns = [
        # $X.XX per million input/output
        r"\$(\d+\.?\d*)\s*(?:per\s+)?(?:million|M|1M)\s*(input|output|prompt|completion)",
        # input: $X.XX, output: $X.XX
        r"(input|prompt)[:\s]+\$(\d+\.?\d*)",
        r"(output|completion)[:\s]+\$(\d+\.?\d*)",
        # $X.XX/$X.XX (input/output)
        r"\$(\d+\.?\d*)\s*/\s*\$(\d+\.?\d*)\s*(?:per\s+)?(?:M|million|1M)",
    ]

    lines = dogpile_output.split("\n")
    current_provider = None

    for line in lines:
        line_lower = line.lower()

        # Detect provider context
        for pattern, provider_name in provider_patterns:
            if re.search(pattern, line_lower):
                current_provider = provider_name
                break

        # Look for pricing in this line
        for pattern in price_patterns:
            matches = re.findall(pattern, line_lower)
            if matches and current_provider:
                entry = {
                    "provider": current_provider,
                    "source": "dogpile",
                    "raw_line": line.strip()[:100],
                }

                for match in matches:
                    if isinstance(match, tuple):
                        if len(match) == 2:
                            if match[0] in ("input", "prompt"):
                                entry["input_price_per_m"] = float(match[1])
                            elif match[0] in ("output", "completion"):
                                entry["output_price_per_m"] = float(match[1])
                            else:
                                # $X.XX per M input/output format
                                price = float(match[0])
                                token_type = match[1]
                                if token_type in ("input", "prompt"):
                                    entry["input_price_per_m"] = price
                                else:
                                    entry["output_price_per_m"] = price
                        elif len(match) == 2:
                            # $X/$Y format
                            entry["input_price_per_m"] = float(match[0])
                            entry["output_price_per_m"] = float(match[1])

                if entry.get("input_price_per_m") or entry.get("output_price_per_m"):
                    pricing_entries.append(entry)

    return pricing_entries


async def research_pricing_with_dogpile(
    model_name: str,
    batch_tokens: int = 90_000_000,
    refresh: bool = False,
) -> list[dict]:
    """
    Use /dogpile skill to research current pricing for a model.

    Args:
        model_name: Model name to research (e.g., "DeepSeek V3.2")
        batch_tokens: Total batch size for cost estimation
        refresh: Force refresh even if cache is valid

    Returns:
        List of pricing estimates from various providers
    """
    # Check cache first
    if not refresh:
        cached = load_cached_pricing()
        if model_name.lower() in [k.lower() for k in cached.keys()]:
            return cached.get(model_name, [])

    # Build dogpile query
    query = f"{model_name} API pricing 2026 per million tokens Chutes OpenRouter DeepSeek"

    # Call dogpile skill
    dogpile_path = Path.home() / ".claude/skills/dogpile/run.sh"
    if not dogpile_path.exists():
        # Fallback to pi-mono location
        dogpile_path = Path(__file__).resolve().parent.parent / "dogpile" / "run.sh"

    if not dogpile_path.exists():
        # Return static cache if dogpile not available
        return find_cheapest_provider(model_name, batch_tokens // 2, batch_tokens // 2)

    try:
        result = subprocess.run(
            [str(dogpile_path), "search", query, "--no-tui"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=dogpile_path.parent,
            env={k: v for k, v in os.environ.items() if k != 'VIRTUAL_ENV'},
        )

        if result.returncode == 0:
            parsed = parse_pricing_from_dogpile(result.stdout)
            if parsed:
                # Convert to cost estimates
                estimates = []
                for p in parsed:
                    if p.get("input_price_per_m") and p.get("output_price_per_m"):
                        input_tokens = batch_tokens // 2
                        output_tokens = batch_tokens // 2
                        input_cost = (input_tokens / 1_000_000) * p["input_price_per_m"]
                        output_cost = (output_tokens / 1_000_000) * p["output_price_per_m"]
                        estimates.append({
                            "provider": p["provider"],
                            "model_id": model_name,
                            "input_price_per_m": p["input_price_per_m"],
                            "output_price_per_m": p["output_price_per_m"],
                            "input_cost": round(input_cost, 2),
                            "output_cost": round(output_cost, 2),
                            "total_cost": round(input_cost + output_cost, 2),
                            "source": "dogpile",
                            "notes": p.get("raw_line", ""),
                        })

                # Cache results
                cached = load_cached_pricing()
                cached[model_name] = estimates
                save_cached_pricing(cached)

                estimates.sort(key=lambda x: x["total_cost"])
                return estimates

    except subprocess.TimeoutExpired:
        pass
    except Exception as e:
        logger.debug("value lookup failed: {}", e)

    # Fallback to static cache
    return find_cheapest_provider(model_name, batch_tokens // 2, batch_tokens // 2)


async def find_cheapest_for_model(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
    use_dogpile: bool = False,
) -> dict:
    """
    Find the cheapest provider for a specific model.

    Args:
        model_name: Model name or pattern
        input_tokens: Total input tokens for batch
        output_tokens: Total output tokens for batch
        use_dogpile: Whether to use dogpile for fresh pricing research

    Returns:
        Dict with cheapest provider info and cost comparison table
    """
    total_tokens = input_tokens + output_tokens

    if use_dogpile:
        estimates = await research_pricing_with_dogpile(model_name, total_tokens)
    else:
        estimates = find_cheapest_provider(model_name, input_tokens, output_tokens)

    if not estimates:
        return {
            "found": False,
            "error": f"No pricing found for model: {model_name}",
        }

    cheapest = estimates[0]

    return {
        "found": True,
        "cheapest": cheapest,
        "all_providers": estimates,
        "table": format_cost_table(estimates),
        "savings_vs_second": (
            round(estimates[1]["total_cost"] - cheapest["total_cost"], 2)
            if len(estimates) > 1 else 0
        ),
    }
