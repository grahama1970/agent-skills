"""Cost estimation and comparison functions for LLM providers.

Contains:
- estimate_batch_cost: Detailed cost breakdown for a batch job
- find_cheapest_provider: Find cheapest across all providers
- format_cost_table: Text table formatting
- get_provider_pricing: Lookup pricing by model ID
- parse_pricing_from_dogpile: Parse pricing from dogpile research output
"""
import re
from typing import Optional

from pricing_data import (
    BatchProviderPricing,
    ProviderPricing,
    PRICING_CACHE,
)


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
